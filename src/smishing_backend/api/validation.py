"""Bounded parsing without returning or logging supplied values."""

import json
from email.message import Message

from fastapi import HTTPException, Request
from pydantic import ValidationError

from smishing_backend.api.contracts import (
    ERRORS,
    MAX_BODY_BYTES,
    ContributionInput,
)
from smishing_backend.domain.text import normalize_text
from smishing_backend.logging import audit


def fail(status: int) -> HTTPException:
    code, message = ERRORS[status]
    return HTTPException(status, detail={"code": code, "message": message})


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


async def validate_contribution(request: Request) -> ContributionInput:
    if len(request.headers.getlist("content-type")) != 1:
        raise fail(400)
    media = Message()
    media["content-type"] = request.headers["content-type"]
    if media.get_content_type().lower() != "application/json":
        raise fail(400)
    params = (media.get_params() or [])[1:]
    if any(k.lower() != "charset" or v.lower() != "utf-8" for k, v in params):
        raise fail(400)
    if (
        len(params) > 1
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise fail(400)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise fail(413)
        body.extend(chunk)
    try:
        raw = json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON constant")),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise fail(400) from None
    # Normalize before checking character limits and hashing, but reject surrogates.
    if isinstance(raw, dict) and isinstance(raw.get("text"), str):
        try:
            raw["text"].encode("utf-8", errors="strict")
        except UnicodeError:
            raise fail(422) from None
        raw["text"] = normalize_text(raw["text"])
    try:
        return ContributionInput.model_validate(raw)
    except ValidationError:
        raise fail(422) from None


async def contribution_error_handler(request: Request, exc: Exception):
    from fastapi.responses import JSONResponse

    assert isinstance(exc, HTTPException)
    if exc.status_code in ERRORS:
        audit.info("contribution_rejected")
        code, message = ERRORS[exc.status_code]
        return JSONResponse(
            {"error": {"code": code, "message": message}},
            status_code=exc.status_code,
            headers=exc.headers,
        )
    return JSONResponse({"detail": "Request failed"}, status_code=exc.status_code)
