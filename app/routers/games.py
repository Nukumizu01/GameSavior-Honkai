from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import connect, row_to_dict
from app.deps import require_user
from app.security import iso
from app.script_settings import normalize_script_overrides, normalized_script_settings, script_schema

router = APIRouter(prefix="/games", tags=["games"])


class ScriptSettings(BaseModel):
    cloud_game_enabled: bool = True
    browser_headless_enabled: bool = True
    browser_headless_restart_on_not_logged_in: bool = False
    after_finish: str = Field(
        default="Exit",
        pattern=r"^(None|Exit|Shutdown|Sleep|Hibernate|Restart|Logoff|TurnOffDisplay|RunScript|Loop|Stay)$",
    )
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class GameConfigUpdate(BaseModel):
    enabled: bool
    timezone: str = "Asia/Shanghai"
    schedule_cron: str = Field(pattern=r"^[0-9*,/\- ]+$")
    timeout_seconds: int = Field(ge=60, le=21600)
    max_retries: int = Field(ge=0, le=5)
    retry_delay_seconds: int = Field(ge=60, le=86400)
    task_options: dict[str, Any] = Field(default_factory=dict)
    script_settings: ScriptSettings = Field(default_factory=ScriptSettings)
    screenshot_policy: str = Field(pattern=r"^(failure_only|all|none)$")


def _decode_options(raw_value: str | None) -> tuple[dict, dict]:
    try:
        raw = json.loads(raw_value or "{}")
    except json.JSONDecodeError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    script = raw.get("_script", {})
    custom = raw.get("custom", raw)
    if not isinstance(script, dict):
        script = {}
    if not isinstance(custom, dict):
        custom = {}
    return script, custom


@router.get("")
def list_games(_: dict = Depends(require_user)):
    with connect() as con:
        return {"games": [dict(r) for r in con.execute("SELECT * FROM game_accounts ORDER BY game").fetchall()]}


@router.get("/{game}/config")
def get_config(game: str, _: dict = Depends(require_user)):
    with connect() as con:
        row = con.execute(
            """
            SELECT c.*, a.game, a.display_name
            FROM task_configs c
            JOIN game_accounts a ON a.id = c.game_account_id
            WHERE a.game = ?
            """,
            (game,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Game config not found")
        item = row_to_dict(row)
        script_settings, custom_task_options = _decode_options(item.pop("task_options_json"))
        item["script_settings"] = normalized_script_settings(script_settings)
        item["custom_task_options"] = custom_task_options
        # Keep this field for older clients; new clients should use the two explicit fields.
        item["task_options"] = custom_task_options
        return item


@router.get("/{game}/script-schema")
def get_script_schema(game: str, _: dict = Depends(require_user)):
    if game != "starrail":
        raise HTTPException(status_code=404, detail="Script settings are not available for this game")
    return script_schema()


@router.put("/{game}/config")
def update_config(game: str, body: GameConfigUpdate, _: dict = Depends(require_user)):
    with connect() as con:
        account = con.execute("SELECT id FROM game_accounts WHERE game = ?", (game,)).fetchone()
        if account is None:
            raise HTTPException(status_code=404, detail="Game not found")
        script_settings = body.script_settings.model_dump()
        script_settings["config_overrides"] = normalize_script_overrides(
            script_settings.get("config_overrides")
        )
        con.execute(
            """
            UPDATE task_configs
            SET enabled = ?, timezone = ?, schedule_cron = ?, timeout_seconds = ?,
                max_retries = ?, retry_delay_seconds = ?, task_options_json = ?,
                screenshot_policy = ?, updated_at = ?
            WHERE game_account_id = ?
            """,
            (
                int(body.enabled),
                body.timezone,
                body.schedule_cron,
                body.timeout_seconds,
                body.max_retries,
                body.retry_delay_seconds,
                json.dumps(
                    {
                        "_script": script_settings,
                        "custom": body.task_options,
                    },
                    ensure_ascii=False,
                ),
                body.screenshot_policy,
                iso(),
                account["id"],
            ),
        )
        return {"ok": True}
