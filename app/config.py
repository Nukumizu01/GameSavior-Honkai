from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The shared .env also contains script-specific Worker variables.
    # Ignore those here so the API can restart without rejecting them.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Game Automation Console"
    domain: str = "game.example.com"
    app_base_url: str = "http://127.0.0.1:8080"
    database_path: Path = Path("./data/app.db")
    artifact_dir: Path = Path("./data/artifacts")
    retention_days: int = 30

    admin_username: str = "admin"
    admin_password: str = "change-me-now"
    session_ttl_hours: int = 168
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    worker_token: str = "change-worker-token-now"

    feishu_webhook_url: str | None = None
    feishu_webhook_secret: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_receive_id: str | None = None
    feishu_receive_id_type: str = "chat_id"

    enable_genshin: bool = False
    enable_starrail: bool = True
    genshin_command: str | None = None
    genshin_workdir: Path | None = None
    starrail_command: str | None = None
    starrail_workdir: Path | None = None
    starrail_log_dir: Path = Path("./starrail/logs")
    starrail_login_qr_path: Path = Path("./data/starrail/qrcode_login.png")
    starrail_control_dir: Path = Path("./starrail/control")
    worker_poll_seconds: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
