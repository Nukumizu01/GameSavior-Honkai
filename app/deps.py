from __future__ import annotations

from fastapi import Cookie, Header, HTTPException, status

from app.config import get_settings
from app.db import connect, row_to_dict
from app.security import hash_token, iso


SESSION_COOKIE_NAME = "game_console_session"


def require_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif session_cookie:
        token = session_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token_hash = hash_token(token)
    with connect() as con:
        row = con.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
              AND sessions.revoked_at IS NULL
              AND sessions.expires_at > ?
              AND users.is_active = 1
            """,
            (token_hash, iso()),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        con.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (iso(), token_hash))
        return row_to_dict(row)


def require_worker(x_worker_token: str | None = Header(default=None)) -> None:
    expected = get_settings().worker_token
    if not x_worker_token or x_worker_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token")
