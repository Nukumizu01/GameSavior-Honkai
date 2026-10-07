from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import connect
from app.deps import require_user
from app.security import iso

router = APIRouter(prefix="/starrail", tags=["starrail"])


def _qr_path():
    return get_settings().starrail_log_dir / "qrcode_login.png"


def _control_dir() -> Path:
    return get_settings().starrail_control_dir


def _switch_request_path() -> Path:
    return _control_dir() / "switch_login.json"


def _switch_status_path() -> Path:
    return _control_dir() / "switch_login.status.json"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@router.get("/login-qr/status")
def login_qr_status(_: dict = Depends(require_user)):
    path = _qr_path()
    if not path.is_file():
        return {"available": False, "updated_at": None, "age_seconds": None}

    updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {
        "available": True,
        "updated_at": updated_at.isoformat(),
        "age_seconds": max(0, int((datetime.now(timezone.utc) - updated_at).total_seconds())),
    }


@router.get("/login-qr")
def login_qr(_: dict = Depends(require_user)):
    path = _qr_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Login QR code is not available")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@router.post("/login-switch")
def request_login_switch(_: dict = Depends(require_user)):
    with connect() as con:
        active_run = con.execute(
            """
            SELECT r.id
            FROM task_runs r
            JOIN tasks t ON t.id = r.task_id
            WHERE t.game = ? AND r.status IN ('claimed', 'running')
            LIMIT 1
            """,
            ("starrail",),
        ).fetchone()
    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="崩铁任务正在运行，请任务结束后再切换登录",
        )

    control_dir = _control_dir()
    control_dir.mkdir(parents=True, exist_ok=True)
    request_path = _switch_request_path()
    if request_path.exists():
        pending = _read_json(request_path) or {}
        return {
            "ok": True,
            "status": "pending",
            "request_id": pending.get("request_id"),
            "requested_at": pending.get("requested_at"),
        }

    request = {
        "action": "switch_login",
        "request_id": uuid4().hex,
        "requested_at": iso(),
    }
    temporary_path = control_dir / f".{request_path.name}.{request['request_id']}.tmp"
    try:
        temporary_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(request_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {"ok": True, "status": "pending", **request}


@router.get("/login-switch/status")
def login_switch_status(_: dict = Depends(require_user)):
    request = _read_json(_switch_request_path())
    if request:
        return {"status": "pending", **request}

    result = _read_json(_switch_status_path())
    if result:
        return result
    return {"status": "idle"}
