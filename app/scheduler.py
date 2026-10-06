from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db import connect
from app.security import iso


def _daily_time_from_cron(expr: str) -> tuple[int, int] | None:
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    if dom != "*" or month != "*" or dow != "*":
        return None
    if not minute.isdigit() or not hour.isdigit():
        return None
    return int(hour), int(minute)


def create_due_daily_tasks() -> int:
    created = 0
    with connect() as con:
        configs = con.execute(
            """
            SELECT c.*, a.game
            FROM task_configs c
            JOIN game_accounts a ON a.id = c.game_account_id
            WHERE c.enabled = 1 AND a.enabled = 1
            """
        ).fetchall()
        for cfg in configs:
            hm = _daily_time_from_cron(cfg["schedule_cron"])
            if hm is None:
                continue
            hour, minute = hm
            try:
                tz = ZoneInfo(cfg["timezone"])
            except ZoneInfoNotFoundError:
                fallback_offsets = {
                    "Asia/Shanghai": timedelta(hours=8),
                    "UTC": timedelta(0),
                }
                if cfg["timezone"] not in fallback_offsets:
                    raise
                tz = timezone(fallback_offsets[cfg["timezone"]], name=cfg["timezone"])
            now_local = datetime.now(tz)
            scheduled_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now_local < scheduled_local:
                continue
            scheduled_for = scheduled_local.astimezone(timezone.utc).isoformat()
            exists = con.execute(
                """
                SELECT id
                FROM tasks
                WHERE game = ? AND source = 'schedule' AND scheduled_for = ?
                LIMIT 1
                """,
                (cfg["game"], scheduled_for),
            ).fetchone()
            if exists:
                continue
            snapshot = dict(cfg)
            cur_time = iso()
            con.execute(
                """
                INSERT INTO tasks(game, source, scheduled_for, status, config_snapshot_json, created_at, updated_at)
                VALUES (?, 'schedule', ?, 'queued', ?, ?, ?)
                """,
                (cfg["game"], scheduled_for, json.dumps(snapshot, ensure_ascii=False), cur_time, cur_time),
            )
            created += 1
    return created


async def scheduler_loop() -> None:
    while True:
        try:
            create_due_daily_tasks()
        except Exception as exc:
            print(f"[scheduler] {exc}")
        await asyncio.sleep(60)
