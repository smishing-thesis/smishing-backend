"""Proxy mode for App Service and the exported requirements; synthetic data only."""

import re
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from smishing_backend import server
from smishing_backend.api.proxy import ForwardedProto
from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions
from smishing_backend.main import create_app

BATCH = "/api/v1/contributions/batch"
SINGLE = "/api/v1/contributions"
HEADERS = {"X-API-Key": "synthetic"}
ITEM = {
    "text": "Aporte sintético <URL>",
    "label": "smishing",
    "model_version": "1.0.0",
}


def scheme_app():
    app = FastAPI()
    app.add_middleware(ForwardedProto)

    @app.get("/scheme")
    def scheme(request: Request):
        return {"scheme": request.url.scheme}

    return app


def test_only_a_single_https_header_marks_the_request_secure():
    with TestClient(scheme_app(), base_url="http://testserver") as client:
        assert client.get("/scheme").json() == {"scheme": "http"}
        for value in ("https", " HTTPS ", "Https"):
            response = client.get("/scheme", headers={"X-Forwarded-Proto": value})
            assert response.json() == {"scheme": "https"}
        for value in ("http", "https,http", "http,https", "wss", ""):
            response = client.get("/scheme", headers={"X-Forwarded-Proto": value})
            assert response.json() == {"scheme": "http"}
        twice = client.get(
            "/scheme", headers=[("X-Forwarded-Proto", "https")] * 2
        )  # repeated header
        assert twice.json() == {"scheme": "http"}


def test_runner_keeps_local_tls_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: calls.append(k))
    monkeypatch.delenv("SMISHING_BEHIND_TLS_PROXY", raising=False)
    monkeypatch.setenv("TLS_CERT_PATH", "cert.pem")
    monkeypatch.setenv("TLS_KEY_PATH", "key.pem")
    server.main()
    (options,) = calls
    assert options["host"] == "127.0.0.1" and options["port"] == 8443
    assert options["ssl_certfile"] == "cert.pem" and options["ssl_keyfile"] == "key.pem"
    assert options["access_log"] is False and options["proxy_headers"] is False


def test_runner_in_proxy_mode_needs_no_certificate(monkeypatch):
    calls = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: calls.append(k))
    monkeypatch.setenv("SMISHING_BEHIND_TLS_PROXY", "true")
    for name in ("TLS_CERT_PATH", "TLS_KEY_PATH", "PORT", "WEBSITES_PORT"):
        monkeypatch.delenv(name, raising=False)
    server.main()
    (options,) = calls
    assert options["host"] == "0.0.0.0" and options["port"] == 8000
    assert "ssl_certfile" not in options and "ssl_keyfile" not in options
    assert options["access_log"] is False and options["proxy_headers"] is False


@pytest.mark.parametrize(
    ("env", "port"),
    [
        ({"PORT": "8123"}, 8123),
        ({"WEBSITES_PORT": "8124"}, 8124),
        ({"PORT": "8123", "WEBSITES_PORT": "8124"}, 8123),
        ({"SMISHING_PORT": "8125"}, 8125),
    ],
)
def test_proxy_mode_port_comes_from_the_platform(monkeypatch, env, port):
    calls = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: calls.append(k))
    monkeypatch.setenv("SMISHING_BEHIND_TLS_PROXY", "1")
    for name in ("PORT", "WEBSITES_PORT", "SMISHING_PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    server.main()
    assert calls[0]["port"] == port


def test_requirements_match_the_lock_and_exclude_development_tools():
    lock = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
    versions = {p["name"]: p["version"] for p in lock["package"]}
    text = Path("requirements.txt").read_text(encoding="utf-8")
    pinned = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", text, flags=re.MULTILINE)
    assert len(pinned) > 20
    for name, version in pinned:
        assert versions[name.lower().replace("_", "-")] == version, name
    names = {name.lower() for name, _ in pinned}
    assert {"fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg"} <= names
    assert not names & {"pytest", "ruff", "mypy"}
    assert "es-core-news-lg @ https://" in text


@pytest.fixture
def proxied(pg):
    def build(**changes):
        return create_app(
            Settings(api_key=SecretStr("synthetic"), behind_tls_proxy=True, **changes),
            PostgresContributionRepository(pg),
        )

    return build


def count(pg):
    with pg.connect() as conn:
        return conn.scalar(select(func.count()).select_from(contributions))


def test_proxy_mode_accepts_forwarded_https_and_nothing_else(proxied, pg):
    batch = {"contributions": [ITEM]}
    with TestClient(proxied(), base_url="http://testserver") as client:
        for headers in (
            HEADERS,
            {**HEADERS, "X-Forwarded-Proto": "http"},
            {**HEADERS, "X-Forwarded-Proto": "https,http"},
        ):
            assert client.post(BATCH, headers=headers, json=batch).status_code == 400
            assert client.post(SINGLE, headers=headers, json=ITEM).status_code == 400
    assert count(pg) == 0
    with TestClient(proxied(), base_url="http://testserver") as client:
        secure = {**HEADERS, "X-Forwarded-Proto": "https"}
        response = client.post(BATCH, headers=secure, json=batch)
        assert response.status_code == 200
        assert response.json() == {"results": [{"index": 0, "status": "accepted"}]}
        assert client.post(SINGLE, headers=secure, json=ITEM).status_code == 409
    assert count(pg) == 1


def test_the_header_is_ignored_when_proxy_mode_is_off(pg):
    application = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    with TestClient(application, base_url="http://testserver") as client:
        secure = {**HEADERS, "X-Forwarded-Proto": "https"}
        assert client.post(SINGLE, headers=secure, json=ITEM).status_code == 400
    assert count(pg) == 0


def test_proxy_mode_never_uses_the_forwarded_address(proxied):
    application = proxied(rate_limit_per_minute=1, global_rate_limit_per_minute=5)
    with TestClient(application, base_url="http://testserver") as client:
        for index in range(5):
            headers = {
                **HEADERS,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": f"203.0.113.{index}",
                "X-Real-IP": f"203.0.113.{index}",
            }
            item = {**ITEM, "text": f"Sintético {index} <URL>"}
            assert client.post(SINGLE, headers=headers, json=item).status_code == 201
        # One bucket, sized like the global quota, however many forwarded addresses.
        limiter = application.state.rate_limiter
        assert len(limiter.counts) == 1 and limiter.per_network == 5
        refused = client.post(
            SINGLE,
            headers={**HEADERS, "X-Forwarded-Proto": "https"},
            json={**ITEM, "text": "Otro <URL>"},
        )
        assert refused.status_code == 429
