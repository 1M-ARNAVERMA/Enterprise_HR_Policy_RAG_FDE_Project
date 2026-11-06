import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Header
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.rag.workflow import ask
from app.rag.vectorstore import add_documents
from app.services.ingestion import load_file, chunk_documents, SUPPORTED
from app.services.audit import write_audit

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

settings = get_settings()

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000)


@router.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@router.post("/chat")
def chat(payload: ChatRequest):
    try:
        result = ask(payload.question)
        write_audit(payload.question, result["source_used"], result.get("trace", []))
        return {
            "answer": result["answer"],
            "source_used": result["source_used"],
            "trace": result.get("trace", []),
            "citations": result.get("citations", []),
            "rewritten_query": result.get("current_query", payload.question),

        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc




@router.post("/ingest")
async def ingest(file: UploadFile = File(...), x_admin_key: str = Header(default="")):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Supported: {', '.join(sorted(SUPPORTED))}")

    upload_dir = Path(settings.upload_dir)
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / filename
        dest.write_bytes(await file.read())
    except OSError as exc:
        logger.exception("Could not save uploaded document %s", filename)
        raise HTTPException(
            status_code=500,
            detail="Could not save the uploaded document. Check the Vercel function logs.",
        ) from exc

    try:
        docs = load_file(dest)
        chunks = chunk_documents(docs)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="The uploaded document contains no extractable text.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not parse uploaded document %s", filename)
        raise HTTPException(
            status_code=422,
            detail="Could not read this document. Check that it is a valid, non-empty supported file.",
        ) from exc

    try:
        ids = add_documents(chunks)
    except Exception as exc:
        logger.exception("Could not index uploaded document %s", filename)
        raise HTTPException(
            status_code=502,
            detail=(
                "Document parsing succeeded, but embedding or Pinecone indexing failed. "
                "Check OPENAI_API_KEY, PINECONE_API_KEY, index dimensions, and Vercel function logs."
            ),
        ) from exc

    return {"message": "Document indexed", "file": filename, "chunks": len(chunks), "ids_created": len(ids)}
