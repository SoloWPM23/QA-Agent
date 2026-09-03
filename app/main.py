"""FastAPI entry point for the web UI and API (M5).

The app mounts the static vanilla-JS frontend under ``/static``, serves
``index.html`` at ``/``, and includes the async job API routes under ``/api``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.web import routes as web_routes

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def create_app() -> FastAPI:
    """Build a FastAPI application instance (testable factory)."""
    app = FastAPI(title="AI QA Agent", version="0.1.0")

    app.include_router(web_routes.router, prefix="/api")
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/openapi")
    def openapi_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "openapi.html")

    return app


app = create_app()
