from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db import connect, row_to_dict
from app.deps import require_user
from app.security import iso

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    game: str
    source: str = "manual"
    run_after: str | None = None
    options: dict = {}


@router.post("")
def create_task(body: TaskCreate, _: dict = Depends(require_user)):
    with connect() as con:
        cfg = con.execute(
            """
            SELECT c.*
            FROM task_configs c JOIN game_accounts a ON a.id = c.game_account_id
            WHERE a.game = ? AND a.enabled = 1
            """,
            (body.game,),
        ).fetchone()
        if cfg is None:
            raise HTTPException(status_code=404, detail="Game is disabled or config not found")
        snapshot = dict(cfg)
        snapshot["manual_options"] = body.options
        now = iso()
        cur = con.execute(
            """
            INSERT INTO tasks(game, source, scheduled_for, status, config_snapshot_json, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?, ?)
            """,
            (body.game, body.source, body.run_after or now, json.dumps(snapshot, ensure_ascii=False), now, now),
        )
        return {"task_id": cur.lastrowid, "status": "queued"}


@router.get("")
def list_tasks(
    game: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_user),
):
    clauses = []
    params = []
    if game:
        clauses.append("game = ?")
        params.append(game)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as con:
        rows = con.execute(f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
        return {"tasks": [dict(r) for r in rows]}


@router.get("/{task_id}")
def get_task(task_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        task = row_to_dict(con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        runs = [dict(r) for r in con.execute("SELECT * FROM task_runs WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()]
        return {"task": task, "runs": runs}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        task = con.execute("SELECT id, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in {"queued", "claimed", "running"}:
            return {"ok": True, "status": task["status"], "already_finished": True}

        now = iso()
        con.execute(
            "UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        active_runs = con.execute(
            "SELECT id FROM task_runs WHERE task_id = ? AND status IN ('claimed','running')",
            (task_id,),
        ).fetchall()
        for run in active_runs:
            con.execute(
                """
                UPDATE task_runs
                SET status = 'cancelled', error_code = 'TASK_CANCELLED',
                    error_message = 'Cancellation requested by user', updated_at = ?
                WHERE id = ?
                """,
                (now, run["id"]),
            )
            con.execute(
                """
                INSERT INTO log_events(
                    task_run_id, level, event_type, stage, code, message, payload_json, created_at
                )
                VALUES (?, 'warning', 'cancel_requested', 'control', 'TASK_CANCELLED', ?, '{}', ?)
                """,
                (run["id"], "Cancellation requested by user.", now),
            )
        return {"ok": True, "status": "cancelled", "active_runs": len(active_runs)}


@router.post("/{task_id}/retry")
def retry_task(task_id: int, _: dict = Depends(require_user)):
    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        cur = con.execute(
            """
            INSERT INTO tasks(game, source, scheduled_for, status, config_snapshot_json, retry_of_task_id, created_at, updated_at)
            VALUES (?, 'manual_retry', ?, 'queued', ?, ?, ?, ?)
            """,
            (task["game"], iso(), task["config_snapshot_json"], task_id, iso(), iso()),
        )
        return {"task_id": cur.lastrowid, "status": "queued"}
