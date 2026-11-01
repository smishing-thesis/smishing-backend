"""FastAPI application entry point."""

from fastapi import FastAPI

from smishing_backend.api.health import router as health_router
from smishing_backend.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Smishing Backend")
    app.state.settings = settings if settings is not None else Settings()
    app.include_router(health_router)
    return app


app = create_app()
