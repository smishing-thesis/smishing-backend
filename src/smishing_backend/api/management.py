"""Research operations in the main Swagger, separate from the mobile paths."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)
from sqlalchemy.exc import SQLAlchemyError

from smishing_backend.api.admin_security import (
    ADMIN_PREFIX,
    admin_bearer,
    management_error,
)
from smishing_backend.api.contracts import ModelVersion
from smishing_backend.api.validation import read_json
from smishing_backend.data.repositories.contribution_queries import ContributionFilters
from smishing_backend.domain.administration import ManagementError
from smishing_backend.domain.quarantine import InvalidTransition
from smishing_backend.review_contract import ReviewCreated, ReviewInput


class ManagementRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except (RequestValidationError, ValidationError):
                return management_error(422)
            except ManagementError as exc:
                return management_error(exc.status)
            except InvalidTransition:
                return management_error(409)
            except HTTPException as exc:
                return management_error(exc.status_code)
            except SQLAlchemyError:
                return management_error(503)

        return handle


management_router = APIRouter(
    prefix=ADMIN_PREFIX,
    route_class=ManagementRoute,
    dependencies=[Depends(admin_bearer)],
)
router = APIRouter(tags=["Administración de aportes"])


class FilterQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    status: Literal["pending", "accepted", "rejected"] | None = None
    received_from: AwareDatetime | None = None
    received_to: AwareDatetime | None = None
    reviewed_from: AwareDatetime | None = None
    reviewed_to: AwareDatetime | None = None
    category: Literal["safe", "smishing"] | None = None
    source: Literal["device", "manual"] | None = None
    model_version: ModelVersion | None = None
    reason: Literal["quality_checked", "invalid_content", "out_of_scope"] | None = None
    has_risk: bool | None = None
    order: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def chronological(self):
        for start, end in (
            (self.received_from, self.received_to),
            (self.reviewed_from, self.reviewed_to),
        ):
            if start is not None and end is not None and start > end:
                raise ValueError("Invalid date range")
        return self

    def filters(self) -> ContributionFilters:
        return ContributionFilters(
            **self.model_dump(include=set(ContributionFilters.__dataclass_fields__))
        )


class ListingQuery(FilterQuery):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class ListedContribution(BaseModel):
    id: UUID
    text: str
    content_hash: str
    status: Literal["pending", "accepted", "rejected"]
    received_at: datetime
    reviewed_at: datetime | None
    review_reason: str | None
    category: Literal["safe", "smishing"]
    source: Literal["device", "manual"]
    automatic_label: Literal["safe", "smishing"]
    model_version: str
    risk_signals: list[str]


@router.get("/contributions", response_model=list[ListedContribution])
def listing(request: Request, query: Annotated[ListingQuery, Query()]):
    return request.app.state.management.list_contributions(
        query.filters(), query.limit, query.offset
    )


@router.delete("/contributions/{contribution_id}", status_code=204)
def delete_contribution(request: Request, contribution_id: UUID):
    request.app.state.management.delete("contributions", contribution_id)
    return Response(status_code=204)


@router.patch(
    "/contributions/{contribution_id}/review",
    response_model=ReviewCreated,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ReviewInput.model_json_schema()}
            },
        }
    },
)
async def review_contribution(request: Request, contribution_id: UUID):
    from starlette.concurrency import run_in_threadpool

    payload = ReviewInput.model_validate(await read_json(request, 2048))
    reviewed = await run_in_threadpool(
        request.app.state.reviews.decide,
        contribution_id,
        request.state.administrative_actor,
        payload.to_decision(),
    )
    return asdict(reviewed)


management_router.include_router(router)
