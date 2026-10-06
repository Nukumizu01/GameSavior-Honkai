from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import connect, row_to_dict
from app.deps import require_user

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
def get_run(run_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        run = row_to_dict(con.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,)).fetchone())
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"run": run}


@router.get("/{run_id}/events")
def get_events(run_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        rows = con.execute("SELECT * FROM log_events WHERE task_run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        return {"events": [dict(r) for r in rows]}


@router.get("/{run_id}/artifacts")
def get_artifacts(run_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        rows = con.execute("SELECT * FROM artifacts WHERE task_run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        return {"artifacts": [dict(r) for r in rows]}


@router.get("/{run_id}/artifacts/{artifact_id}/content")
def get_artifact_content(
    run_id: int,
    artifact_id: int,
    _: dict = Depends(require_user),
):
    with connect() as con:
        artifact = con.execute(
            "SELECT * FROM artifacts WHERE id = ? AND task_run_id = ?",
            (artifact_id, run_id),
        ).fetchone()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    settings = get_settings()
    root = settings.artifact_dir.resolve()
    path = Path(artifact["storage_path"]).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found")

    media_type = artifact["mime_type"]
    if not media_type or media_type == "application/octet-stream":
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=60"},
    )
