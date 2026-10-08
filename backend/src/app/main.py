"""API entry point: `create_app()` for ASGI servers and tests, `run()` for the CLI."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.api.errors import register_error_handlers
from app.api.v1.router import api_v1_router
from app.core.config import Settings, get_settings
from app.core.lifecycle import make_lifespan
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="AI Detector API",
        version=__version__,
        lifespan=make_lifespan(settings),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1_router)
    return app


def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
    )
