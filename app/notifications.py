from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import time
import urllib.parse

import requests

from app.config import get_settings
from app.db import connect
from app.security import iso


_tenant_token_cache: tuple[str, float] | None = None


def _sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_feishu_text(text: str, task_run_id: int | None = None, event_type: str = "manual") -> bool:
    settings = get_settings()
    if not settings.feishu_webhook_url:
        _record(task_run_id, event_type, "skipped", "FEISHU_WEBHOOK_URL is empty")
        return False

    payload: dict = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if settings.feishu_webhook_secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _sign(timestamp, settings.feishu_webhook_secret)

    try:
        resp = requests.post(settings.feishu_webhook_url, json=payload, timeout=10)
        ok = resp.ok
        message_id = None
        error = None
        try:
            body = resp.json()
            message_id = json.dumps(body, ensure_ascii=False)[:500]
            if not ok or body.get("code") not in (0, None):
                error = message_id
        except Exception:
            if not ok:
                error = resp.text[:500]
        _record(task_run_id, event_type, "sent" if ok and not error else "failed", error, message_id)
        return ok and not error
    except Exception as exc:
        _record(task_run_id, event_type, "failed", str(exc))
        return False


def _get_tenant_access_token() -> str:
    global _tenant_token_cache
    settings = get_settings()
    now = time.time()
    if _tenant_token_cache and _tenant_token_cache[1] > now + 60:
        return _tenant_token_cache[0]
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET are required for image messages")

    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") not in (0, None) or not body.get("tenant_access_token"):
        raise RuntimeError(f"Feishu token request failed: {json.dumps(body, ensure_ascii=False)[:500]}")
    token = body["tenant_access_token"]
    _tenant_token_cache = (token, now + int(body.get("expire", 7200)))
    return token


def send_feishu_image(
    image: bytes,
    filename: str,
    task_run_id: int | None = None,
    event_type: str = "starrail_login_qr",
) -> bool:
    settings = get_settings()
    if not settings.feishu_app_id or not settings.feishu_app_secret or not settings.feishu_receive_id:
        _record(
            task_run_id,
            event_type,
            "skipped",
            "FEISHU_APP_ID, FEISHU_APP_SECRET and FEISHU_RECEIVE_ID are required for image messages",
        )
        return False

    try:
        token = _get_tenant_access_token()
        upload_resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": (filename, io.BytesIO(image), "image/png")},
            timeout=30,
        )
        upload_resp.raise_for_status()
        upload_body = upload_resp.json()
        if upload_body.get("code") not in (0, None) or not upload_body.get("data", {}).get("image_key"):
            raise RuntimeError(f"Feishu image upload failed: {json.dumps(upload_body, ensure_ascii=False)[:500]}")

        image_key = upload_body["data"]["image_key"]
        message_resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": settings.feishu_receive_id_type},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "receive_id": settings.feishu_receive_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
            },
            timeout=15,
        )
        message_resp.raise_for_status()
        message_body = message_resp.json()
        if message_body.get("code") not in (0, None):
            raise RuntimeError(f"Feishu image message failed: {json.dumps(message_body, ensure_ascii=False)[:500]}")
        _record(
            task_run_id,
            event_type,
            "sent",
            provider_message_id=json.dumps(message_body, ensure_ascii=False)[:500],
        )
        return True
    except Exception as exc:
        _record(task_run_id, event_type, "failed", str(exc))
        return False


def _record(
    task_run_id: int | None,
    event_type: str,
    status: str,
    error_message: str | None = None,
    provider_message_id: str | None = None,
) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO notification_deliveries(
                task_run_id, channel, event_type, status, provider_message_id,
                error_message, sent_at, created_at
            )
            VALUES (?, 'feishu', ?, ?, ?, ?, ?, ?)
            """,
            (
                task_run_id,
                event_type,
                status,
                provider_message_id,
                error_message,
                iso() if status == "sent" else None,
                iso(),
            ),
        )


def console_run_url(run_id: int) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return urllib.parse.urljoin(base + "/", f"runs/{run_id}")
