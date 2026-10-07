from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.db import connect, row_to_dict
from app.deps import require_worker
from app.notifications import console_run_url, send_feishu_image, send_feishu_text
from app.security import iso, utcnow

router = APIRouter(prefix="/worker", tags=["worker"], dependencies=[Depends(require_worker)])


class RegisterRequest(BaseModel):
    worker_key: str
    name: str
    worker_type: str
    version: str | None = None
    capabilities: dict = {}


class HeartbeatRequest(BaseModel):
    worker_key: str
    status: str = "online"
    current_run_id: int | None = None


class EventRequest(BaseModel):
    level: str = "info"
    event_type: str
    stage: str | None = None
    code: str | None = None
    message: str
    payload: dict = {}


class FinishRequest(BaseModel):
    status: str
    error_code: str | None = None
    error_message: str | None = None
    summary: dict = {}


@router.post("/register")
def register(body: RegisterRequest):
    now = iso()
    recovered_runs = 0
    with connect() as con:
        previous_runs = con.execute(
            """
            SELECT r.id, r.task_id
            FROM task_runs r
            JOIN workers w ON w.id = r.worker_id
            WHERE w.worker_key = ? AND r.status IN ('claimed', 'running')
            """,
            (body.worker_key,),
        ).fetchall()
        for previous_run in previous_runs:
            con.execute(
                """
                UPDATE task_runs
                SET finished_at = ?, status = 'failed',
                    error_code = 'WORKER_RESTARTED',
                    error_message = 'Worker restarted before the previous run finished',
                    summary_json = ?, updated_at = ?
                WHERE id = ? AND status IN ('claimed', 'running')
                """,
                (
                    now,
                    json.dumps({"recovered_on_worker_register": True}, ensure_ascii=False),
                    now,
                    previous_run["id"],
                ),
            )
            con.execute(
                """
                UPDATE tasks
                SET status = 'failed', updated_at = ?
                WHERE id = ? AND status IN ('claimed', 'running')
                """,
                (now, previous_run["task_id"]),
            )
            con.execute(
                """
                INSERT INTO log_events(
                    task_run_id, level, event_type, stage, code, message, payload_json, created_at
                )
                VALUES (?, 'warning', 'run_recovered', 'worker_startup', 'WORKER_RESTARTED', ?, ?, ?)
                """,
                (
                    previous_run["id"],
                    "Previous run was marked failed because the Worker restarted.",
                    json.dumps({"worker_key": body.worker_key}, ensure_ascii=False),
                    now,
                ),
            )
            recovered_runs += 1
        con.execute(
            """
            INSERT INTO workers(worker_key, name, worker_type, version, status, last_heartbeat_at, capabilities_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'online', ?, ?, ?, ?)
            ON CONFLICT(worker_key) DO UPDATE SET
                name = excluded.name,
                worker_type = excluded.worker_type,
                version = excluded.version,
                status = 'online',
                last_heartbeat_at = excluded.last_heartbeat_at,
                capabilities_json = excluded.capabilities_json,
                updated_at = excluded.updated_at
            """,
            (
                body.worker_key,
                body.name,
                body.worker_type,
                body.version,
                now,
                json.dumps(body.capabilities, ensure_ascii=False),
                now,
                now,
            ),
        )
    return {"ok": True, "recovered_runs": recovered_runs}


@router.post("/heartbeat")
def heartbeat(body: HeartbeatRequest):
    with connect() as con:
        con.execute(
            "UPDATE workers SET status = ?, last_heartbeat_at = ?, updated_at = ? WHERE worker_key = ?",
            (body.status, iso(), iso(), body.worker_key),
        )
    return {"ok": True}


@router.get("/jobs/next")
def next_job(worker_key: str):
    with connect() as con:
        worker = con.execute("SELECT * FROM workers WHERE worker_key = ?", (worker_key,)).fetchone()
        if worker is None:
            raise HTTPException(status_code=404, detail="Worker not registered")

        game_filter = "genshin" if "genshin" in worker["worker_type"] else "starrail"
        task = con.execute(
            """
            SELECT *
            FROM tasks
            WHERE status = 'queued' AND game = ? AND scheduled_for <= ?
            ORDER BY scheduled_for ASC, id ASC
            LIMIT 1
            """,
            (game_filter, iso()),
        ).fetchone()
        if task is None:
            return {"job": None}

        now = iso()
        claim = con.execute(
            "UPDATE tasks SET status = 'claimed', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now, task["id"]),
        )
        if claim.rowcount != 1:
            return {"job": None}
        cur = con.execute(
            """
            INSERT INTO task_runs(task_id, worker_id, started_at, status, created_at, updated_at)
            VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (task["id"], worker["id"], now, now, now),
        )
        con.execute("UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?", (now, task["id"]))
        return {"job": {"task": dict(task), "run_id": cur.lastrowid}}


@router.get("/runs/{run_id}/control")
def run_control(run_id: int):
    row = None
    with connect() as con:
        row = con.execute(
            """
            SELECT r.id, r.status AS run_status, t.status AS task_status
            FROM task_runs r JOIN tasks t ON t.id = r.task_id
            WHERE r.id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    cancelled = row["run_status"] == "cancelled" or row["task_status"] == "cancelled"
    return {
        "run_id": run_id,
        "cancelled": cancelled,
        "run_status": row["run_status"],
        "task_status": row["task_status"],
    }


@router.post("/runs/{run_id}/events")
def add_event(run_id: int, body: EventRequest):
    with connect() as con:
        run = con.execute("SELECT id FROM task_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        con.execute(
            """
            INSERT INTO log_events(task_run_id, level, event_type, stage, code, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                body.level,
                body.event_type,
                body.stage,
                body.code,
                body.message,
                json.dumps(body.payload, ensure_ascii=False),
                iso(),
            ),
        )
    return {"ok": True}


@router.post("/runs/{run_id}/artifacts")
async def upload_artifact(
    run_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
):
    settings = get_settings()
    content = await file.read()
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(file.filename or "artifact.bin").suffix or ".bin"
    run_dir = settings.artifact_dir / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / f"{kind}-{digest[:12]}{suffix}"
    target.write_bytes(content)
    expires_at = (utcnow() + timedelta(days=settings.retention_days)).isoformat()
    with connect() as con:
        con.execute(
            """
            INSERT INTO artifacts(task_run_id, kind, storage_path, mime_type, size_bytes, sha256, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, kind, str(target), file.content_type, len(content), digest, iso(), expires_at),
        )
    return {"ok": True, "sha256": digest, "path": str(target)}


@router.post("/starrail/login-qr")
async def send_starrail_login_qr(
    file: UploadFile = File(...),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Login QR image is empty")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Login QR image is too large")

    # The API stores an independent copy for the dashboard.  Keeping it apart
    # from the worker's watched file prevents its own write from triggering a
    # duplicate upload and notification.
    qr_path = get_settings().starrail_login_qr_path
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = qr_path.with_suffix(".png.tmp")
    try:
        temporary_path.write_bytes(content)
        temporary_path.replace(qr_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    ok = send_feishu_image(
        content,
        file.filename or "starrail-login-qr.png",
        event_type="starrail_login_qr",
    )
    return {"ok": ok, "updated_at": iso()}


@router.post("/runs/{run_id}/finish")
def finish_run(run_id: int, body: FinishRequest):
    if body.status not in {"succeeded", "failed", "timeout", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    with connect() as con:
        run = row_to_dict(con.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,)).fetchone())
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        now = iso()
        cancelled = run["status"] == "cancelled"
        if not cancelled:
            task = con.execute("SELECT status FROM tasks WHERE id = ?", (run["task_id"],)).fetchone()
            cancelled = task is not None and task["status"] == "cancelled"
        final_status = "cancelled" if cancelled else body.status
        final_error_code = "TASK_CANCELLED" if cancelled else body.error_code
        final_error_message = "Cancellation requested by user" if cancelled else body.error_message
        con.execute(
            """
            UPDATE task_runs
            SET finished_at = ?, status = ?, error_code = ?, error_message = ?, summary_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                now,
                final_status,
                final_error_code,
                final_error_message,
                json.dumps(body.summary, ensure_ascii=False),
                now,
                run_id,
            ),
        )
        con.execute(
            """
            UPDATE tasks SET status = ?, updated_at = ?
            WHERE id = ? AND status IN ('queued','claimed','running')
            """,
            (final_status, now, run["task_id"]),
        )
    if final_status == "succeeded":
        duration_ms = body.summary.get("duration_ms")
        duration_text = f"\n耗时：{round(duration_ms / 1000)} 秒" if isinstance(duration_ms, (int, float)) else ""
        text = (
            "【游戏自动化控制台】任务完成\n"
            f"Run ID：{run_id}{duration_text}\n"
            f"查看：{console_run_url(run_id)}"
        )
        send_feishu_text(text, task_run_id=run_id, event_type="succeeded")
    elif final_status in {"failed", "timeout"}:
        text = (
            f"【游戏自动化控制台】任务{final_status}\n"
            f"Run ID：{run_id}\n"
            f"错误：{final_error_code or 'UNKNOWN'} {final_error_message or ''}\n"
            f"查看：{console_run_url(run_id)}"
        )
        send_feishu_text(text, task_run_id=run_id, event_type=final_status)
    return {"ok": True, "status": final_status}


@router.post("/runs/{run_id}/stop-ack")
def stop_ack(run_id: int):
    return {"ok": True, "run_id": run_id}
