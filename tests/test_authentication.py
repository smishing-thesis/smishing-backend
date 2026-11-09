from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from smishing_backend.api.authentication import authenticated_contribution
from smishing_backend.api.contracts import ContributionInput
from smishing_backend.api.validation import contribution_error_handler
from smishing_backend.config import Settings


@pytest.fixture
def gate():
    app = FastAPI()
    app.state.settings = Settings(
        api_key=None, api_keys=[SecretStr("synthetic-old"), SecretStr("synthetic-new")]
    )
    app.state.calls = 0
    app.add_exception_handler(HTTPException, contribution_error_handler)

    @app.post("/gate")
    def submit(
        payload: Annotated[ContributionInput, Depends(authenticated_contribution)],
    ):
        app.state.calls += 1
        return {"ok": True}

    return app, TestClient(app)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": "wrong"},
        {"X-API-Key": ""},
        [("X-API-Key", "synthetic-new"), ("X-API-Key", "wrong")],
    ],
)
def test_unauthorized_before_parsing_and_domain(gate, headers):
    app, client = gate
    response = client.post("/gate", headers=headers, content=b"invalid json")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert app.state.calls == 0


@pytest.mark.parametrize("key", ["synthetic-old", "synthetic-new"])
def test_valid_key(gate, key):
    app, client = gate
    response = client.post(
        "/gate",
        headers={"X-API-Key": key},
        json={"text": "Texto sintético", "label": "safe", "model_version": "1.0.0"},
    )
    assert response.status_code == 200
    assert app.state.calls == 1


def test_rotation_and_fail_closed(gate, monkeypatch):
    app, client = gate
    monkeypatch.setenv("SMISHING_API_KEYS", '["synthetic-new"]')
    app.state.settings = Settings(api_key=None)
    assert (
        client.post("/gate", headers={"X-API-Key": "synthetic-old"}).status_code == 401
    )
    assert (
        client.post("/gate", headers={"X-API-Key": "synthetic-new"}).status_code == 400
    )
    assert "synthetic-new" not in repr(app.state.settings)
    app.state.settings = Settings(api_key=None, api_keys=[])
    assert (
        client.post("/gate", headers={"X-API-Key": "synthetic-new"}).status_code == 401
    )
