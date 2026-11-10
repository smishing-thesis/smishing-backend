"""Reviewer credentials are separate from app credentials and contributor identity."""

import hmac
import re

from fastapi import HTTPException
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import JSONResponse

from smishing_backend.config import Settings


class ReviewSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMISHING_REVIEW_", extra="ignore")
    credentials: dict[str, SecretStr] = Field(default_factory=dict)


def validate_review_credentials(settings: ReviewSettings, public: Settings) -> None:
    keys = [value.get_secret_value() for value in settings.credentials.values()]
    app_keys = [value.get_secret_value() for value in public.api_keys]
    if public.api_key:
        app_keys.append(public.api_key.get_secret_value())
    if (
        any(
            not re.fullmatch(r"[a-z0-9_-]{1,64}", name) for name in settings.credentials
        )
        or any(not key for key in keys)
        or len(keys) != len(set(keys))
        or set(keys) & set(app_keys)
    ):
        raise RuntimeError(
            "Reviewer identifiers and credentials must be unique and separate from app credentials"
        )


class ReviewGate:
    def __init__(
        self,
        app,
        credentials: dict[str, SecretStr],
        prefixes=("/reviews",),
        max_body=2048,
    ):
        self.app = app
        self.credentials = credentials
        self.prefixes = prefixes
        self.max_body = max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.prefixes):
            return await self.app(scope, receive, send)
        headers = [
            value.decode("latin-1")
            for name, value in scope["headers"]
            if name.lower() == b"authorization"
        ]
        reviewer = None
        if len(headers) == 1:
            parts = headers[0].split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1]:
                for identifier, key in self.credentials.items():
                    if hmac.compare_digest(
                        parts[1].encode(), key.get_secret_value().encode()
                    ):
                        reviewer = identifier
        if reviewer is None:
            response = JSONResponse(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "Credencial de revisor ausente o inválida.",
                    }
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            return await response(scope, receive, send)
        if scope["scheme"] != "https":
            response = JSONResponse(
                {"error": {"code": "https_required", "message": "Se requiere HTTPS."}},
                status_code=400,
            )
            return await response(scope, receive, send)
        scope.setdefault("state", {})["reviewer_id"] = reviewer
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_body:
                    raise HTTPException(413)
            return message

        return await self.app(scope, bounded_receive, send)
