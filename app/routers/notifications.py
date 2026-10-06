from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import connect
from app.deps import require_user
from app.notifications import send_feishu_image, send_feishu_text
from app.retention import run_retention
from app.config import get_settings

router = APIRouter(tags=["ops"])


@router.get("/notifications")
def list_notifications(_: dict = Depends(require_user)):
    with connect() as con:
        rows = con.execute("SELECT * FROM notification_deliveries ORDER BY created_at DESC LIMIT 100").fetchall()
        return {"notifications": [dict(r) for r in rows]}


@router.post("/notifications/test")
def test_notification(_: dict = Depends(require_user)):
    ok = send_feishu_text("【游戏自动化控制台】飞书通知测试成功。", event_type="test")
    return {"ok": ok}


@router.post("/notifications/test-login-qr")
def test_login_qr(_: dict = Depends(require_user)):
    settings = get_settings()
    path = settings.starrail_log_dir / "qrcode_login.png"
    if not path.is_file():
        return {"ok": False, "detail": "当前没有可发送的崩铁登录二维码"}
    ok = send_feishu_image(
        path.read_bytes(),
        path.name,
        event_type="starrail_login_qr_manual",
    )
    return {"ok": ok}


@router.post("/maintenance/retention/run")
def retention(_: dict = Depends(require_user)):
    return run_retention()


@router.get("/system/health")
def health(_: dict = Depends(require_user)):
    return {"ok": True}


@router.get("/system/storage")
def storage(_: dict = Depends(require_user)):
    settings = get_settings()
    total = 0
    files = 0
    if settings.artifact_dir.exists():
        for path in settings.artifact_dir.rglob("*"):
            if path.is_file():
                files += 1
                total += path.stat().st_size
    return {"artifact_dir": str(settings.artifact_dir), "files": files, "bytes": total}
