from typing import Annotated

from fastapi import APIRouter, Depends, Request

from smishing_backend.api.contracts import (
    ContributionCreated,
    ContributionInput,
    contract_app,
)
from smishing_backend.api.rate_limit import limited_contribution
from smishing_backend.api.validation import fail
from smishing_backend.domain.contributions import (
    DuplicateContribution,
    Label,
    NewContribution,
    receive_contribution,
)
from smishing_backend.domain.text import content_hash

router = APIRouter()
proposal = contract_app()
operation = proposal.openapi()["paths"]["/api/v1/contributions"]["post"]
contract_route = next(
    route for route in proposal.routes if route.path == "/api/v1/contributions"
)


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
    return ContributionCreated(id=saved.id, status=saved.status)
