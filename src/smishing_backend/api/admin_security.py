"""Authenticate management requests before FastAPI parses the body."""

import hmac

from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smishing_backend.api.rate_limit import RateLimiter

ADMIN_PREFIX = "/api/v1/admin"
admin_bearer = HTTPBearer(scheme_name="AdministrativeBearer", auto_error=False)


def management_error(status: int, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "management_error",
                "message": "La operación no se pudo completar.",
            }
        },
        status_code=status,
        headers={"Cache-Control": "no-store"} | (headers or {}),
    )


class AdministrativeGate:
    def __init__(self, app: ASGIApp, credentials: dict):
        self.app = app
        self.credentials = tuple(
            (identity, value.get_secret_value().encode())
            for identity, value in credentials.items()
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (
            path == ADMIN_PREFIX or path.startswith(ADMIN_PREFIX + "/")
        ):
            await self.app(scope, receive, send)
            return

        async def private_send(message: Message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        credentials = [
            value for name, value in scope["headers"] if name == b"authorization"
        ]
        identity = None
        if len(credentials) == 1:
            scheme, _, token = credentials[0].partition(b" ")
            if scheme.lower() == b"bearer" and token:
                for actor, expected in self.credentials:
                    if hmac.compare_digest(token, expected):
                        identity = actor
        if identity is None:
            if self.credentials:
                failed: RateLimiter = scope["app"].state.failed_admin_limiter
                retry = failed.admit("failed")
                if retry is not None:
                    await management_error(429, {"Retry-After": str(retry)})(
                        scope, receive, private_send
                    )
                    return
            await management_error(401, {"WWW-Authenticate": "Bearer"})(
                scope, receive, private_send
            )
            return
        if scope["scheme"] != "https":
            await management_error(400)(scope, receive, private_send)
            return
        limiter: RateLimiter = scope["app"].state.admin_limiter
        retry = limiter.admit(identity)
        if retry is not None:
            await management_error(429, {"Retry-After": str(retry)})(
                scope, receive, private_send
            )
            return

        scope.setdefault("state", {})["administrative_actor"] = identity
        await self.app(scope, receive, private_send)
