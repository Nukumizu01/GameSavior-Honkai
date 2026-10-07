from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Cookie, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.deps import SESSION_COOKIE_NAME, get_session_user
from app.routers import auth, dashboard, games, notifications, runs, starrail, tasks, worker
from app.scheduler import scheduler_loop


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    web_dir = Path(__file__).parent.parent / "web"

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        asyncio.create_task(scheduler_loop())

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(games.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(worker.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(starrail.router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root(session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
        return RedirectResponse(
            "/dashboard" if get_session_user(session_cookie) else "/login",
            status_code=303,
        )

    @app.get("/login", include_in_schema=False)
    def login_page(session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
        if get_session_user(session_cookie):
            return RedirectResponse("/dashboard", status_code=303)
        return FileResponse(web_dir / "login.html", headers={"Cache-Control": "no-store"})

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_page(session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
        return (
            FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-store"})
            if get_session_user(session_cookie)
            else RedirectResponse("/login", status_code=303)
        )

    @app.get("/settings", include_in_schema=False)
    def settings_page(session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
        return (
            FileResponse(
                web_dir / "settings.html",
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
            )
            if get_session_user(session_cookie)
            else RedirectResponse("/login", status_code=303)
        )

    @app.get("/runs/{run_id}", include_in_schema=False)
    def run_detail_page(
        run_id: int,
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ):
        return (
            FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-store"})
            if get_session_user(session_cookie)
            else RedirectResponse("/login", status_code=303)
        )

    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
