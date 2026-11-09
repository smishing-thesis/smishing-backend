import json
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from smishing_backend.api.contracts import MAX_BODY_BYTES, ContributionInput
from smishing_backend.api.validation import (
    contribution_error_handler,
    validate_contribution,
)
from smishing_backend.domain.text import content_hash

VALID = {
    "text": "Mensaje sintético [URL]",
    "label": "smishing",
    "model_version": "1.0.0",
}


@pytest.fixture
def client():
    app = FastAPI()
    app.add_exception_handler(HTTPException, contribution_error_handler)

    @app.post("/validate")
    def validate(payload: Annotated[ContributionInput, Depends(validate_contribution)]):
        return {"hash": content_hash(payload.text)}

    return TestClient(app)


@pytest.mark.parametrize(
    "text",
    ["a", "x" * 2048, "á", "a\u0301", "\t prueba \r\n sintética ", "[PHONE] [NAME]"],
)
def test_valid(client, text):
    result = client.post("/validate", json={**VALID, "text": text})
    assert result.status_code == 200
    assert result.json() == {"hash": content_hash(text)}


@pytest.mark.parametrize(
    "change",
    [
        {"text": ""},
        {"text": " \t\u200b "},
        {"text": "x" * 2049},
        {"text": 1},
        {"text": None},
        {"text": []},
        {"text": "\ud800"},
        {"label": "unknown"},
        {"label": True},
        {"model_version": "v1"},
        {"model_version": "1.2.3\n"},
        {"model_version": "1.2.3+private"},
        {"model_version": "1.2.3-"},
        {"model_version": 1},
        {"device_id": "synthetic"},
    ],
)
def test_invalid_fields(client, change):
    response = client.post(
        "/validate",
        content=json.dumps({**VALID, **change}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_contribution",
            "message": "El aporte no cumple el contrato.",
        }
    }


@pytest.mark.parametrize("field", VALID)
def test_missing(client, field):
    payload = VALID.copy()
    del payload[field]
    assert client.post("/validate", json=payload).status_code == 422


@pytest.mark.parametrize(
    "body,media,status",
    [
        (b"\xff", "application/json", 400),
        (b"{}", "text/plain", 400),
        (b"{}", "application/json; charset=latin1", 400),
        (b'{"text":1,"text":2}', "application/json", 400),
        (b"{", "application/json", 400),
        (b"NaN", "application/json", 400),
        (b"[]", "application/json", 422),
        (b" " * (MAX_BODY_BYTES + 1), "application/json", 413),
    ],
)
def test_bad_envelope(client, body, media, status):
    response = client.post("/validate", content=body, headers={"content-type": media})
    assert response.status_code == status
    assert set(response.json()) == {"error"}


def test_normalization():
    assert content_hash("  café\n prueba\x00 ") == content_hash("cafe\u0301 prueba")


def test_stream_limit_without_content_length(client):
    def chunks():
        yield b" " * MAX_BODY_BYTES
        yield b"x"

    assert (
        client.post(
            "/validate", content=chunks(), headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
