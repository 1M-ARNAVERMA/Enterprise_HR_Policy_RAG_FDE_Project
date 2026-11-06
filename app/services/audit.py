import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import get_settings


settings = get_settings()


def init_db() -> None:
    settings_path = settings.audit_db_path
    Path(settings_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings_path)
    con.execute(
        """CREATE TABLE IF NOT EXISTS query_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            source_used TEXT NOT NULL,
            trace_json TEXT NOT NULL
        )"""
    )
    con.commit()
    con.close()



def write_audit(question: str, source_used: str, trace: list[str]) -> None:
    con = sqlite3.connect(settings.audit_db_path)
    con.execute(
        "INSERT INTO query_audit(created_at, question, source_used, trace_json) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), question, source_used, json.dumps(trace)),
    )
    con.commit()
    con.close()