"""Batch envelope, per-item parsing and quota per contribution; synthetic data."""

import json
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from smishing_backend.api.contracts import (
    MAX_BATCH_BODY_BYTES,
    MAX_BATCH_ITEMS,
    MAX_BODY_BYTES,
    ContributionInput,
)
from smishing_backend.api.rate_limit import RateLimiter, limited_batch
from smishing_backend.api.validation import contribution_error_handler
from smishing_backend.config import Settings

HEADERS = {"X-API-Key": "synthetic", "content-type": "application/json"}
ITEM = {
    "text": "Aporte sintético <URL>",
    "label": "smishing",
    "model_version": "1.0.0",
}
INVALID_ENVELOPE = {
    "empty": {"contributions": []},
    "too_many": {"contributions": [ITEM] * (MAX_BATCH_ITEMS + 1)},
    "missing": {},
    "extra_member": {"contributions": [ITEM], "device_id": "synthetic"},
    "not_a_list": {"contributions": ITEM},
    "null": {"contributions": None},
    "root_list": [ITEM],
}


def make_app(per_network=100, global_limit=100):
    app = FastAPI()
    app.state.settings = Settings(api_key=SecretStr("synthetic"))
    app.state.rate_limiter = RateLimiter(per_network, global_limit)
    app.add_exception_handler(HTTPException, contribution_error_handler)

    @app.post("/batch")
    def batch(items: Annotated[list[ContributionInput | None], Depends(limited_batch)]):
        return {
            "valid": [item is not None for item in items],
            "texts": [item.text for item in items if item],
        }

    return app


@pytest.fixture
def app():
    application = make_app()
    yield application
    application.state.rate_limiter.close()


def post(app, body, headers=HEADERS):
    with TestClient(app) as client:
        return client.post("/batch", headers=headers, content=json.dumps(body))


def test_cost_is_all_or_nothing():
    limiter = RateLimiter(5, 8)
    try:
        assert limiter.admit("192.0.2.1", 3) is None
        assert limiter.admit("192.0.2.1", 3) == 60  # 6 > 5 per network
        assert limiter.admit("192.0.2.1", 2) is None  # nothing was taken above
        assert limiter.admit("192.0.2.2", 4) == 60  # 9 > 8 global
        assert limiter.admit("192.0.2.2", 3) is None
        assert limiter.total == 8 and len(limiter.counts) == 2
    finally:
        limiter.close()


def test_valid_batch_keeps_order_and_marks_each_item(app):
    response = post(
        app,
        {
            "contributions": [
                ITEM,
                {**ITEM, "label": "unknown"},
                {**ITEM, "text": " á "},
                {**ITEM, "text": "\ud800"},
                {**ITEM, "device_id": "synthetic"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] == [True, False, True, False, False]
    assert response.json()["texts"] == [ITEM["text"], "á"]


@pytest.mark.parametrize("name", INVALID_ENVELOPE)
def test_invalid_envelope_is_422(app, name):
    response = post(app, INVALID_ENVELOPE[name])
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_contribution",
            "message": "El aporte no cumple el contrato.",
        }
    }


def test_maximum_batch_is_accepted(app):
    response = post(app, {"contributions": [ITEM] * MAX_BATCH_ITEMS})
    assert response.status_code == 200
    assert len(response.json()["valid"]) == MAX_BATCH_ITEMS


def test_transport_rules_match_single_endpoint(app):
    with TestClient(app) as client:
        for headers in (
            {**HEADERS, "content-type": "text/plain"},
            {**HEADERS, "content-type": "application/json; charset=latin-1"},
        ):
            response = client.post("/batch", headers=headers, content=b"{}")
            assert response.status_code == 400
        for body in (
            b"not json",
            b'{"contributions": [], "contributions": []}',
            b"\xff",
        ):
            response = client.post("/batch", headers=HEADERS, content=body)
            assert response.status_code == 400
        no_key = client.post(
            "/batch", headers={"content-type": "application/json"}, content=b"{}"
        )
        assert no_key.status_code == 401


def test_body_limit_is_per_batch_not_per_item(app):
    assert MAX_BATCH_BODY_BYTES == MAX_BODY_BYTES * MAX_BATCH_ITEMS
    large = {"contributions": [{**ITEM, "text": "x" * 2048}] * MAX_BATCH_ITEMS}
    # Far above the single-contribution limit, within the batch limit.
    assert len(json.dumps(large)) > MAX_BODY_BYTES
    assert post(app, large).status_code == 200
    with TestClient(app) as client:
        response = client.post(
            "/batch",
            headers=HEADERS,
            content=b'{"contributions":[],"x":"' + b"a" * MAX_BATCH_BODY_BYTES + b'"}',
        )
    assert response.status_code == 413
    assert "aaaa" not in response.text


def test_quota_counts_contributions_and_rejects_whole_batch():
    app = make_app(per_network=25, global_limit=100)
    try:
        assert post(app, {"contributions": [ITEM] * 20}).status_code == 200
        refused = post(app, {"contributions": [ITEM] * 6})
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) > 0
        assert refused.json()["error"]["code"] == "rate_limited"
        # The refused batch took only its first unit, so four more still fit.
        assert post(app, {"contributions": [ITEM] * 4}).status_code == 200
    finally:
        app.state.rate_limiter.close()


def test_429_comes_before_reading_the_body():
    app = make_app(per_network=1, global_limit=1)
    try:
        assert post(app, {"contributions": [ITEM]}).status_code == 200
        with TestClient(app) as client:
            garbage = client.post("/batch", headers=HEADERS, content=b"\xff")
        assert garbage.status_code == 429
    finally:
        app.state.rate_limiter.close()
