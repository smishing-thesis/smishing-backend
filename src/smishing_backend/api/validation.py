"""Bounded parsing without returning or logging supplied values."""

import json
from email.message import Message

from fastapi import HTTPException, Request
from pydantic import ValidationError

from smishing_backend.api.contracts import (
    ERRORS,
    MAX_BATCH_BODY_BYTES,
    MAX_BATCH_ITEMS,
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


async def read_json(request: Request, limit: int) -> object:
    """Check the media type and read at most `limit` bytes as strict UTF-8 JSON."""
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
        if len(body) + len(chunk) > limit:
            raise fail(413)
        body.extend(chunk)
    try:
        return json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON constant")),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise fail(400) from None


def parse_contribution(raw: object) -> ContributionInput | None:
    """Return the contribution, or None when it breaks the contract."""
    # Normalize before checking character limits and hashing, but reject surrogates.
    if isinstance(raw, dict) and isinstance(raw.get("text"), str):
        try:
            raw["text"].encode("utf-8", errors="strict")
        except UnicodeError:
            return None
        raw["text"] = normalize_text(raw["text"])
    try:
        return ContributionInput.model_validate(raw)
    except ValidationError:
        return None


async def validate_contribution(request: Request) -> ContributionInput:
    contribution = parse_contribution(await read_json(request, MAX_BODY_BYTES))
    if contribution is None:
        raise fail(422)
    return contribution


async def read_batch(request: Request) -> list[object]:
    """Read the batch envelope; each item is validated separately afterwards."""
    raw = await read_json(request, MAX_BATCH_BODY_BYTES)
    if not isinstance(raw, dict) or set(raw) != {"contributions"}:
        raise fail(422)
    items = raw["contributions"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH_ITEMS:
        raise fail(422)
    return items


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
