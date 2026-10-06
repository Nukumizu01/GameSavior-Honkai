from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.security import hash_password, iso


def connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def init_db() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with connect() as con:
        con.executescript(schema_path.read_text(encoding="utf-8"))
        settings = get_settings()
        settings.artifact_dir.mkdir(parents=True, exist_ok=True)
        existing = con.execute("SELECT id FROM users LIMIT 1").fetchone()
        if existing is None:
            now = iso()
            con.execute(
                """
                INSERT INTO users(username, password_hash, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (settings.admin_username, hash_password(settings.admin_password), now, now),
            )
        for game, name, mode in (
            ("genshin", "原神云原神", "cloud_genshin"),
            ("starrail", "崩铁", "cloud_starrail"),
        ):
            enabled = int(
                settings.enable_genshin if game == "genshin" else settings.enable_starrail
            )
            con.execute(
                """
                INSERT OR IGNORE INTO game_accounts(game, display_name, enabled, runtime_mode, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?, ?)
                """,
                (game, name, mode, iso(), iso()),
            )
            con.execute(
                "UPDATE game_accounts SET enabled = ?, updated_at = ? WHERE game = ?",
                (enabled, iso(), game),
            )
            account = con.execute("SELECT id FROM game_accounts WHERE game = ?", (game,)).fetchone()
            default_time = "40 4 * * *" if game == "genshin" else "20 4 * * *"
            con.execute(
                """
                INSERT OR IGNORE INTO task_configs(
                    game_account_id, enabled, timezone, schedule_cron, timeout_seconds,
                    max_retries, retry_delay_seconds, task_options_json, screenshot_policy, updated_at
                )
                VALUES (?, 1, 'Asia/Shanghai', ?, 3600, 1, 600, '{}', 'failure_only', ?)
                """,
                (account["id"], default_time, iso()),
            )
