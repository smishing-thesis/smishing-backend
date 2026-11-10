"""Private management API. Never mounted in the Android contribution service."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from smishing_backend.api.contracts import ContributionInput
from smishing_backend.config import Settings
from smishing_backend.data.connection import create_database_engine
from smishing_backend.data.repositories.administration import (
    PostgresAdministrationRepository,
)
from smishing_backend.data.risk_config import policy_from_settings
from smishing_backend.domain.administration import (
    AdministrationRepository,
    ManagementError,
)
from smishing_backend.domain.contributions import (
    DuplicateContribution,
    UnknownModelVersion,
)
from smishing_backend.domain.model_catalog import (
    InvalidModelPublication,
    ModelVersionConflict,
)
from smishing_backend.domain.privacy import (
    AnonymizationUnavailable,
    ResidualPersonalData,
    load_name_detector,
)
from smishing_backend.domain.text import normalize_text
from smishing_backend.review_auth import (
    ReviewGate,
    ReviewSettings,
    validate_review_credentials,
)


class AdminSettings(ReviewSettings):
    model_config = SettingsConfigDict(env_prefix="SMISHING_ADMIN_", extra="ignore")


class EntityResponse(BaseModel):
    id: UUID


class ContributionResponse(EntityResponse):
    text: str
    content_hash: str
    received_at: datetime
    review_status: str
    reviewed_at: datetime | None
    review_reason: str | None


class LabelResponse(EntityResponse):
    message_id: UUID
    category: str
    source: str
    model_version_id: UUID | None
    created_at: datetime


class ModelResponse(EntityResponse):
    version_tag: str
    generated_at: datetime
    training_set: str
    hyperparameters: str
    accuracy: Decimal
    precision_score: Decimal
    recall: Decimal
    f1_score: Decimal


def normalized(value: str) -> str:
    value = normalize_text(value)
    if not value:
        raise ValueError("Empty normalized text")
    return value


class ContributionCreate(ContributionInput):
    _normalize = field_validator("text")(normalized)


class TextChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: Annotated[str, Field(min_length=1, max_length=2048)]
    _normalize = field_validator("text")(normalized)


class LabelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message_id: Annotated[UUID, Field(strict=False)]
    category: Literal["safe", "smishing"]
    source: Literal["device", "manual"]
    model_version_id: Annotated[UUID | None, Field(strict=False)] = None


class LabelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["safe", "smishing"] | None = None
    model_version_id: Annotated[UUID | None, Field(strict=False)] = None


class ModelPublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    release_tag: Annotated[
        str,
        Field(
            max_length=21,
            pattern=r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?$",
        ),
    ]


def create_admin_app(
    settings: AdminSettings | None = None,
    database: Settings | None = None,
    repository: AdministrationRepository | None = None,
    reviewers: ReviewSettings | None = None,
) -> FastAPI:
    configured = settings if settings is not None else AdminSettings()
    public = database if database is not None else Settings()
    review = reviewers if reviewers is not None else ReviewSettings()
    validate_review_credentials(configured, public)
    if {key.get_secret_value() for key in configured.credentials.values()} & {
        key.get_secret_value() for key in review.credentials.values()
    }:
        raise RuntimeError(
            "Administrative credentials must differ from reviewer credentials"
        )

    @asynccontextmanager
    async def lifespan(app):
        load_name_detector()
        engine = None
        if repository is None:
            engine = create_database_engine(public.database_url)
            app.state.management = PostgresAdministrationRepository(
                engine, policy_from_settings(public)
            )
        else:
            app.state.management = repository
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(
        title="Smishing Corpus — administración", version="1.0.0", lifespan=lifespan
    )
    app.add_middleware(
        ReviewGate,
        credentials=configured.credentials,
        prefixes=("/api/v1",),
        max_body=16384,
    )
    bearer = HTTPBearer(auto_error=False)

    def routes(resource, create_schema, put_schema, patch_schema, response_schema):
        path = "/api/v1/" + resource
        dependencies = [Depends(bearer)]

        def listing(
            request: Request,
            limit: Annotated[int, Query(ge=1, le=100)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ):
            return request.app.state.management.list(resource, limit, offset)

        def detail(identity: UUID, request: Request):
            return request.app.state.management.get(resource, identity)

        def create(payload: BaseModel, request: Request):
            return request.app.state.management.create(resource, payload.model_dump())

        def replace(identity: UUID, payload: BaseModel, request: Request):
            return request.app.state.management.change(
                resource, identity, payload.model_dump()
            )

        def patch(identity: UUID, payload: BaseModel, request: Request):
            values = payload.model_dump(exclude_unset=True)
            if not values or ("category" in values and values["category"] is None):
                raise ManagementError(422)
            return request.app.state.management.change(resource, identity, values)

        def remove(identity: UUID, request: Request):
            request.app.state.management.delete(resource, identity)
            return Response(status_code=204)

        for endpoint, schema in [
            (create, create_schema),
            (replace, put_schema),
            (patch, patch_schema),
        ]:
            endpoint.__annotations__["payload"] = schema
        for method, suffix, endpoint, response, status in [
            ("GET", "", listing, list.__class_getitem__(response_schema), 200),
            ("GET", "/{identity}", detail, response_schema, 200),
            ("POST", "", create, response_schema, 201),
            ("PUT", "/{identity}", replace, response_schema, 200),
            ("PATCH", "/{identity}", patch, response_schema, 200),
            ("DELETE", "/{identity}", remove, None, 204),
        ]:
            app.add_api_route(
                path + suffix,
                cast(Callable[..., Any], endpoint),
                methods=[method],
                response_model=response,
                status_code=status,
                dependencies=dependencies,
                tags=[resource],
                operation_id=resource.replace("-", "_")
                + "_"
                + method.lower()
                + ("_detail" if suffix else "_collection"),
            )

    routes(
        "contributions",
        ContributionCreate,
        TextChange,
        TextChange,
        ContributionResponse,
    )
    routes("message-labels", LabelCreate, LabelCreate, LabelPatch, LabelResponse)
    routes(
        "model-versions",
        ModelPublicationInput,
        ModelPublicationInput,
        ModelPublicationInput,
        ModelResponse,
    )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "service_unavailable",
                    "message": "Servicio no disponible.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(ManagementError)
    @app.exception_handler(RequestValidationError)
    @app.exception_handler(HTTPException)
    @app.exception_handler(IntegrityError)
    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(DuplicateContribution)
    @app.exception_handler(UnknownModelVersion)
    @app.exception_handler(ResidualPersonalData)
    @app.exception_handler(AnonymizationUnavailable)
    @app.exception_handler(InvalidModelPublication)
    @app.exception_handler(ModelVersionConflict)
    async def failure(request, exc):
        if isinstance(exc, ManagementError):
            status = exc.status
        elif isinstance(exc, HTTPException):
            status = exc.status_code
        elif isinstance(
            exc, (IntegrityError, DuplicateContribution, ModelVersionConflict)
        ):
            status = 409
        elif isinstance(exc, (SQLAlchemyError, AnonymizationUnavailable)):
            status = 503
        else:
            status = 422
        return JSONResponse(
            {
                "error": {
                    "code": "management_error",
                    "message": "La operación no se pudo completar.",
                }
            },
            status_code=status,
        )

    return app


app = create_admin_app()
