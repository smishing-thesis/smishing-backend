"""Proposed v1 wire contract. No persistence or inference is implemented here."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import FastAPI
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, StringConstraints

MAX_BODY_BYTES = 16384
MAX_TEXT_LENGTH = 2048
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
    proposal = FastAPI(title="Smishing Backend", version="1.0.0")
    responses: dict[int | str, dict[str, Any]] = {
        status: {
            "model": ErrorResponse,
            "description": message,
            "content": {
                "application/json": {
                    "example": {"error": {"code": code, "message": message}}
                }
            },
        }
        for status, (code, message) in ERRORS.items()
    }
    responses[429]["headers"] = {
        "Retry-After": {"schema": {"type": "integer", "minimum": 1}}
    }
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

    return proposal
