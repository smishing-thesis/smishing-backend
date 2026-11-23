"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from smishing_backend.api.contracts import contract_app
from smishing_backend.api.contributions import router as contribution_router
from smishing_backend.api.health import router as health_router
from smishing_backend.api.proxy import ForwardedProto
from smishing_backend.api.rate_limit import RateLimiter
from smishing_backend.api.validation import contribution_error_handler
from smishing_backend.config import Settings
from smishing_backend.data.connection import create_database_engine
from smishing_backend.data.repositories.poisoning import RiskAwareContributionRepository
from smishing_backend.data.risk_config import policy_from_settings
from smishing_backend.domain.contributions import ContributionRepository
from smishing_backend.domain.privacy import AnonymizationUnavailable, load_name_detector
from smishing_backend.logging import audit


class CorpusFastAPI(FastAPI):
    def openapi(self):
        schema = super().openapi()
        proposal = contract_app().openapi()
        for key, value in proposal["components"].items():
            schema.setdefault("components", {}).setdefault(key, {}).update(value)
        return schema


def create_app(
    settings: Settings | None = None, repository: ContributionRepository | None = None
) -> FastAPI:
    configured = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_name_detector()
        engine = None
        if repository is None:
            engine = create_database_engine(configured.database_url)
            app.state.repository = RiskAwareContributionRepository(
                engine, policy_from_settings(configured)
            )
        else:
            app.state.repository = repository
        # Behind the proxy every request comes from the same immediate peer, so the
        # per-network quota would be the global one anyway; make that explicit.
        per_network = (
            configured.global_rate_limit_per_minute
            if configured.behind_tls_proxy
            else configured.rate_limit_per_minute
        )
        app.state.rate_limiter = RateLimiter(
            per_network, configured.global_rate_limit_per_minute
        )
        try:
            yield
        finally:
            app.state.rate_limiter.close()
            if engine is not None:
                engine.dispose()

    app = CorpusFastAPI(title="Smishing Backend", version="1.1.0", lifespan=lifespan)
    app.state.settings = configured
    if configured.behind_tls_proxy:
        app.add_middleware(ForwardedProto)
    app.include_router(health_router)
    app.include_router(contribution_router)
    app.add_exception_handler(HTTPException, contribution_error_handler)

    @app.exception_handler(AnonymizationUnavailable)
    @app.exception_handler(SQLAlchemyError)
    async def storage_error(request: Request, exc: SQLAlchemyError):
        audit.info("service_unavailable")
        return JSONResponse(
            {
                "error": {
                    "code": "service_unavailable",
                    "message": "Servicio no disponible.",
                }
            },
            status_code=503,
        )

    return app


app = create_app()
