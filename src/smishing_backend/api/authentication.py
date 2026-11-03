"""Application credential gate; contains no device identity."""

import hmac
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from smishing_backend.api.contracts import ContributionInput
from smishing_backend.api.validation import fail, validate_contribution

credential_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_application(
    request: Request,
    credential: Annotated[str | None, Security(credential_header)],
) -> None:
    settings = request.app.state.settings
    keys = list(settings.api_keys)
    if settings.api_key is not None:
        keys.append(settings.api_key)
    if len(request.headers.getlist("x-api-key")) != 1 or not credential:
        raise fail(401)
    supplied = credential.encode("utf-8")
    accepted = False
    for key in keys:
        expected = key.get_secret_value().encode("utf-8")
        accepted |= bool(expected) and hmac.compare_digest(supplied, expected)
    if not accepted:
        raise fail(401)


async def authenticated_contribution(
    request: Request, authenticated: Annotated[None, Depends(require_application)]
) -> ContributionInput:
    # Parse the body only after authentication. No domain or repository call here.
    return await validate_contribution(request)
