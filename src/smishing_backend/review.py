"""Separate operator-only API; never mounted in the public contribution app."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from smishing_backend.config import Settings
from smishing_backend.data.connection import create_database_engine
from smishing_backend.data.repositories.review import PostgresReviewRepository
from smishing_backend.domain.quarantine import InvalidTransition
from smishing_backend.domain.review import ReviewRepository
from smishing_backend.review_auth import (
    ReviewGate,
    ReviewSettings,
    validate_review_credentials,
)
from smishing_backend.review_contract import ReviewCreated, ReviewInput


class FlagAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirm: Literal[True]


class PendingContribution(BaseModel):
    id: UUID
    text: str
    received_at: datetime


def create_review_app(
    settings: ReviewSettings | None = None,
    database: Settings | None = None,
    repository: ReviewRepository | None = None,
) -> FastAPI:
    configured = settings if settings is not None else ReviewSettings()
    public = database if database is not None else Settings()
    validate_review_credentials(configured, public)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = None
        if repository is None:
            engine = create_database_engine(public.database_url)
            app.state.repository = PostgresReviewRepository(engine)
        else:
            app.state.repository = repository
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(
        title="Smishing Corpus — revisión interna", version="1.0.0", lifespan=lifespan
    )
    app.add_middleware(ReviewGate, credentials=configured.credentials)
    bearer = HTTPBearer(auto_error=False)

    @app.get(
        "/reviews/pending",
        response_model=list[PendingContribution],
        dependencies=[Depends(bearer)],
    )
    def pending(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50):
        return request.app.state.repository.pending(limit)

    @app.post(
        "/reviews/{contribution_id}",
        status_code=201,
        response_model=ReviewCreated,
        dependencies=[Depends(bearer)],
    )
    def decide(contribution_id: UUID, payload: ReviewInput, request: Request):
        result = request.app.state.repository.decide(
            contribution_id, request.state.reviewer_id, payload.to_decision()
        )
        return asdict(result)

    @app.get("/reviews/flagged", dependencies=[Depends(bearer)])
    def flagged(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50):
        return request.app.state.repository.flagged(limit)

    @app.post(
        "/reviews/{contribution_id}/flags/acknowledge", dependencies=[Depends(bearer)]
    )
    def acknowledge(
        contribution_id: UUID, payload: FlagAcknowledgement, request: Request
    ):
        count = request.app.state.repository.acknowledge(
            contribution_id, request.state.reviewer_id
        )
        return {"reviewed_flags": count}

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_review",
                    "message": "La revisión no cumple el contrato.",
                }
            },
            status_code=422,
        )

    @app.exception_handler(InvalidTransition)
    async def conflict(request: Request, exc: InvalidTransition):
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_transition",
                    "message": "La revisión no está permitida.",
                }
            },
            status_code=409,
        )

    @app.exception_handler(SQLAlchemyError)
    async def storage(request: Request, exc: SQLAlchemyError):
        return JSONResponse(
            {
                "error": {
                    "code": "service_unavailable",
                    "message": "Servicio no disponible.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: Exception):
        assert isinstance(exc, HTTPException)
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_review",
                    "message": "Solicitud de revisión inválida.",
                }
            },
            status_code=exc.status_code,
        )

    return app


app = create_review_app()
