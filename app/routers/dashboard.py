from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import connect
from app.deps import require_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(_: dict = Depends(require_user)):
    with connect() as con:
        games = [dict(r) for r in con.execute("SELECT * FROM game_accounts ORDER BY game").fetchall()]
        workers = [dict(r) for r in con.execute("SELECT * FROM workers ORDER BY name").fetchall()]
        recent = [
            dict(r)
            for r in con.execute(
                """
                SELECT *
                FROM tasks
                ORDER BY created_at DESC
                LIMIT 10
                """
            ).fetchall()
        ]
    return {"games": games, "workers": workers, "recent_tasks": recent}
