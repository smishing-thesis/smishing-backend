"""Proposed v1 wire contract. No persistence or inference is implemented here."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import FastAPI
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_BODY_BYTES = 16384
MAX_TEXT_LENGTH = 2048
MAX_BATCH_ITEMS = 20
MAX_BATCH_BODY_BYTES = MAX_BODY_BYTES * MAX_BATCH_ITEMS
ModelVersion = Annotated[
    str,
    StringConstraints(
        strict=True,
        max_length=20,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?$",
    ),
]


class ContributionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_LENGTH)]
    label: Literal["safe", "smishing"]
    model_version: ModelVersion


class ContributionCreated(BaseModel):
    id: UUID
    status: Literal["pending"]


class ContributionBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contributions: Annotated[
        list[ContributionInput], Field(min_length=1, max_length=MAX_BATCH_ITEMS)
    ]


class ContributionResult(BaseModel):
    """Outcome of one contribution; never carries ids, text or received values."""

    index: Annotated[int, Field(ge=0, lt=MAX_BATCH_ITEMS)]
    status: Literal["accepted", "duplicate", "rejected"]
    reason: (
        Literal["not_anonymized", "unknown_model_version", "invalid_contribution"]
        | None
    ) = None


class ContributionBatchResult(BaseModel):
    results: list[ContributionResult]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


ERRORS = {
    503: ("service_unavailable", "Servicio no disponible."),
    400: ("invalid_request", "Se requiere JSON UTF-8 válido."),
    401: ("unauthorized", "Credencial ausente o inválida."),
    409: ("duplicate_contribution", "El aporte ya existe."),
    413: ("body_too_large", "El cuerpo supera el límite permitido."),
    422: ("invalid_contribution", "El aporte no cumple el contrato."),
    429: ("rate_limited", "Límite temporal de aportes excedido."),
}


def contract_app() -> FastAPI:
    """Schema-only app: never mounted or used to acknowledge contributions."""
    proposal = FastAPI(title="Smishing Backend", version="1.1.0")

    def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
        built: dict[int | str, dict[str, Any]] = {
            status: {
                "model": ErrorResponse,
                "description": ERRORS[status][1],
                "content": {
                    "application/json": {
                        "example": {
                            "error": {
                                "code": ERRORS[status][0],
                                "message": ERRORS[status][1],
                            }
                        }
                    }
                },
            }
            for status in statuses
        }
        built[429]["headers"] = {
            "Retry-After": {"schema": {"type": "integer", "minimum": 1}}
        }
        return built

    responses = error_responses(*ERRORS)
    batch_responses = error_responses(*(s for s in ERRORS if s != 409))
    key = APIKeyHeader(name="X-API-Key", auto_error=False)

    from fastapi import Depends

    @proposal.post(
        "/api/v1/contributions",
        status_code=201,
        response_model=ContributionCreated,
        responses=responses,
        description="Aporte optativo ya anonimizado. Inferencia exclusivamente local en Android. Máximo 16384 bytes de cuerpo JSON UTF-8; texto de 1 a 2048 puntos Unicode tras normalización.",
        dependencies=[Depends(key)],
    )
    def contribute(payload: ContributionInput) -> ContributionCreated:
        raise NotImplementedError("Schema only")

    @proposal.post(
        "/api/v1/contributions/batch",
        status_code=200,
        response_model=ContributionBatchResult,
        response_model_exclude_none=True,
        responses=batch_responses,
        description=(
            "Hasta 20 aportes optativos ya anonimizados por solicitud, con un "
            "resultado por aporte (accepted, duplicate o rejected con un motivo "
            "genérico) en el mismo orden. Cada aporte se procesa por separado: uno "
            "rechazado no afecta a los demás y un duplicado indica que reenviar es "
            "seguro. La cuota cuenta aportes, no solicitudes. Máximo 327680 bytes "
            "de cuerpo JSON UTF-8; cada texto de 1 a 2048 puntos Unicode tras "
            "normalización. Un error de almacenamiento (503) afecta a todo el lote: "
            "reenviarlo es seguro."
        ),
        dependencies=[Depends(key)],
    )
    def contribute_batch(payload: ContributionBatchInput) -> ContributionBatchResult:
        raise NotImplementedError("Schema only")

    return proposal
