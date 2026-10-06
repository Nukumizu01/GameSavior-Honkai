from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.config import get_settings
from app.db import connect
from app.security import utcnow


def run_retention() -> dict:
    settings = get_settings()
    cutoff = (utcnow() - timedelta(days=settings.retention_days)).isoformat()
    deleted_files = 0
    deleted_rows = 0
    with connect() as con:
        rows = con.execute("SELECT id, storage_path FROM artifacts WHERE expires_at < ?", (cutoff,)).fetchall()
        for row in rows:
            path = Path(row["storage_path"])
            try:
                if path.exists():
                    path.unlink()
                    deleted_files += 1
            finally:
                con.execute("DELETE FROM artifacts WHERE id = ?", (row["id"],))
                deleted_rows += 1
        con.execute(
            """
            DELETE FROM log_events
            WHERE task_run_id IN (
                SELECT id FROM task_runs WHERE created_at < ?
            )
            """,
            (cutoff,),
        )
    return {"cutoff": cutoff, "deleted_files": deleted_files, "deleted_artifact_rows": deleted_rows}
