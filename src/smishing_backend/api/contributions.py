from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.routing import APIRoute

from smishing_backend.api.contracts import (
    ContributionBatchResult,
    ContributionCreated,
    ContributionInput,
    ContributionResult,
    contract_app,
)
from smishing_backend.api.rate_limit import limited_batch, limited_contribution
from smishing_backend.api.validation import fail
from smishing_backend.domain.contributions import (
    ContributionRepository,
    DuplicateContribution,
    Label,
    NewContribution,
    UnknownModelVersion,
    receive_contribution,
)
from smishing_backend.domain.privacy import ResidualPersonalData
from smishing_backend.domain.text import content_hash
from smishing_backend.logging import audit

router = APIRouter()
proposal = contract_app()
contract_paths = proposal.openapi()["paths"]
operation = contract_paths["/api/v1/contributions"]["post"]
batch_operation = contract_paths["/api/v1/contributions/batch"]["post"]


def _contract_route(path: str) -> APIRoute:
    return next(
        route
        for route in proposal.routes
        if isinstance(route, APIRoute) and route.path == path
    )


contract_route = _contract_route("/api/v1/contributions")
batch_contract_route = _contract_route("/api/v1/contributions/batch")


@router.post(
    "/api/v1/contributions",
    status_code=201,
    response_model=ContributionCreated,
    description=operation["description"],
    responses=contract_route.responses,
    operation_id=operation["operationId"],
    openapi_extra={"requestBody": operation["requestBody"]},
)
def contribute(
    request: Request,
    payload: Annotated[ContributionInput, Depends(limited_contribution)],
) -> ContributionCreated:
    if request.url.scheme != "https":
        raise fail(400)
    try:
        saved = receive_contribution(
            NewContribution(
                payload.text,
                content_hash(payload.text),
                (Label(payload.label, payload.model_version),),
            ),
            request.app.state.repository,
        )
    except DuplicateContribution:
        raise fail(409) from None
    except (ResidualPersonalData, UnknownModelVersion):
        raise fail(422) from None
    audit.info("contribution_accepted")
    return ContributionCreated(id=saved.id, status=saved.status)


def _receive_item(
    item: ContributionInput | None, repository: ContributionRepository, index: int
) -> ContributionResult:
    """Store one contribution; the outcome never repeats the text or the error."""
    if item is None:
        audit.info("contribution_rejected")
        return ContributionResult(
            index=index, status="rejected", reason="invalid_contribution"
        )
    try:
        receive_contribution(
            NewContribution(
                item.text,
                content_hash(item.text),
                (Label(item.label, item.model_version),),
            ),
            repository,
        )
    except DuplicateContribution:
        audit.info("contribution_rejected")
        return ContributionResult(index=index, status="duplicate")
    except ResidualPersonalData:
        audit.info("contribution_rejected")
        return ContributionResult(
            index=index, status="rejected", reason="not_anonymized"
        )
    except UnknownModelVersion:
        audit.info("contribution_rejected")
        return ContributionResult(
            index=index, status="rejected", reason="unknown_model_version"
        )
    audit.info("contribution_accepted")
    return ContributionResult(index=index, status="accepted")


@router.post(
    "/api/v1/contributions/batch",
    status_code=200,
    response_model=ContributionBatchResult,
    response_model_exclude_none=True,
    description=batch_operation["description"],
    responses=batch_contract_route.responses,
    operation_id=batch_operation["operationId"],
    openapi_extra={"requestBody": batch_operation["requestBody"]},
)
def contribute_batch(
    request: Request,
    items: Annotated[list[ContributionInput | None], Depends(limited_batch)],
) -> ContributionBatchResult:
    if request.url.scheme != "https":
        raise fail(400)
    # Each item commits on its own. A storage failure (503) leaves earlier items
    # saved; resending the batch reports them as duplicates, so it is idempotent.
    repository = request.app.state.repository
    return ContributionBatchResult(
        results=[
            _receive_item(item, repository, index) for index, item in enumerate(items)
        ]
    )
