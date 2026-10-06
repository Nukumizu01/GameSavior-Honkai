from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from app.config import get_settings
from app.db import connect, row_to_dict
from app.deps import SESSION_COOKIE_NAME, require_user
from app.security import expires_in, hash_token, iso, new_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    settings = get_settings()
    with connect() as con:
        user = con.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (body.username,)).fetchone()
        if user is None or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = new_token()
        expires_at = expires_in(settings.session_ttl_hours)
        con.execute(
            "INSERT INTO sessions(user_id, token_hash, expires_at, last_seen_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], hash_token(token), expires_at, iso(), iso()),
        )
        con.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (iso(), iso(), user["id"]))
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            max_age=settings.session_ttl_hours * 60 * 60,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
            path="/",
        )
        return {"access_token": token, "token_type": "bearer", "expires_at": expires_at}


@router.post("/logout")
def logout(
    response: Response,
    user: dict = Depends(require_user),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization and authorization.startswith("Bearer ")
        else session_cookie
    )
    if token:
        with connect() as con:
            con.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ?",
                (iso(), hash_token(token)),
            )
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"ok": True, "user": user["username"]}


@router.get("/me")
def me(user: dict = Depends(require_user)):
    return {"user": {"id": user["id"], "username": user["username"], "last_login_at": user["last_login_at"]}}
