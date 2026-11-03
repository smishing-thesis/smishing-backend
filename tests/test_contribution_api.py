import socket
import ssl
import subprocess
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from smishing_backend.api.contracts import contract_app
from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.main import create_app

PAYLOAD = {
    "text": "Aporte sintético [URL]",
    "label": "smishing",
    "model_version": "1.0.0",
}
HEADERS = {"X-API-Key": "synthetic"}


@pytest.fixture
def application(pg):
    return create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )


def test_runtime_schema_matches_contract(application):
    schema = application.openapi()
    proposal = contract_app().openapi()
    assert (
        schema["paths"]["/api/v1/contributions"]
        == proposal["paths"]["/api/v1/contributions"]
    )
    for name, value in proposal["components"]["schemas"].items():
        assert schema["components"]["schemas"][name] == value


def test_complete_flow_and_rejections(application, pg):
    with TestClient(application, base_url="https://testserver") as client:
        assert client.post("/api/v1/contributions", json=PAYLOAD).status_code == 401
        assert (
            client.post(
                "/api/v1/contributions",
                headers=HEADERS,
                json={**PAYLOAD, "device_id": "forbidden"},
            ).status_code
            == 422
        )
        response = client.post("/api/v1/contributions", headers=HEADERS, json=PAYLOAD)
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        assert set(response.json()) == {"id", "status"}
        assert PAYLOAD["text"] not in response.text
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 1
        assert conn.scalar(select(labels.c.value)) == "smishing"
        assert conn.scalar(select(model_versions.c.version)) == "1.0.0"


def test_plain_http_cannot_store(application, pg):
    with TestClient(application) as client:
        assert (
            client.post(
                "/api/v1/contributions", headers=HEADERS, json=PAYLOAD
            ).status_code
            == 400
        )
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 0


def test_real_https_with_verified_certificate(application, tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(
        application,
        ssl_certfile=str(cert),
        ssl_keyfile=str(key),
        access_log=False,
        log_config=None,
        proxy_headers=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert server.started
        with httpx.Client(
            verify=ssl.create_default_context(cafile=str(cert)), trust_env=False
        ) as client:
            response = client.post(
                f"https://127.0.0.1:{port}/api/v1/contributions",
                headers=HEADERS,
                json=PAYLOAD,
            )
        assert response.status_code == 201
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    assert not thread.is_alive()
