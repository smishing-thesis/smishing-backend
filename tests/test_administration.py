from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from smishing_backend.admin import AdminSettings, create_admin_app
from smishing_backend.config import Settings
from smishing_backend.data.model_release import parse_publication
from smishing_backend.data.repositories.administration import (
    PostgresAdministrationRepository,
)
from smishing_backend.data.repositories.review import PostgresReviewRepository
from smishing_backend.data.schema import (
    labels,
    model_versions,
    risk_flags,
)
from smishing_backend.domain.poisoning import PoisoningPolicy, fingerprint
from smishing_backend.domain.review import ReviewDecision
from smishing_backend.main import create_app
from smishing_backend.review_auth import ReviewSettings

AUTH = {"Authorization": "Bearer synthetic-admin"}
PATH = "/api/v1/"
PAYLOAD = {
    "text": "Aporte sintético para administrar <URL>",
    "label": "safe",
    "model_version": "1.0.0",
}


@pytest.fixture
def system(pg, monkeypatch, published_metadata):
    from smishing_backend.data.repositories import administration

    publication = parse_publication(*published_metadata)
    monkeypatch.setattr(
        administration,
        "read_github_publication",
        lambda tag: replace(
            publication,
            version=tag[1:],
            release_tag=tag,
            release_url=f"https://github.com/smishing-thesis/charcnn-smishing-model/releases/tag/{tag}",
            metadata_sha256=tag.ljust(64, "0"),
        ),
    )
    policy = PoisoningPolicy(
        evaluation_references=(
            fingerprint(
                "Referencia sintética para cambiar contenido de un aporte <URL>"
            ),
        )
    )
    repo = PostgresAdministrationRepository(pg, policy)
    app = create_admin_app(
        AdminSettings(credentials={"admin-demo": SecretStr("synthetic-admin")}),
        Settings(api_key=SecretStr("synthetic-app")),
        repo,
        ReviewSettings(credentials={"reviewer-demo": SecretStr("synthetic-review")}),
    )
    with TestClient(app, base_url="https://testserver") as client:
        client.headers.update(AUTH)
        yield client, repo


def new_contribution(client):
    response = client.post(PATH + "contributions", json=PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize(
    "resource", ["contributions", "message-labels", "model-versions"]
)
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_credentials_before_body_for_every_admin_method(system, resource, method):
    client, _ = system
    url = (
        PATH
        + resource
        + ("/" + str(uuid4()) if method in {"PUT", "PATCH", "DELETE"} else "")
    )
    for headers in [
        {},
        {"Authorization": "Bearer synthetic-app"},
        {"Authorization": "Bearer synthetic-review"},
    ]:
        with TestClient(client.app, base_url="https://testserver") as unauthorized:
            assert (
                unauthorized.request(
                    method, url, headers=headers, content=b"invalid json"
                ).status_code
                == 401
            )


def test_contribution_crud_normalization_duplicates_readonly_and_risk(system, pg):
    client, _ = system
    cid = new_contribution(client)
    assert client.get(PATH + "contributions").json()[0]["id"] == cid
    assert (
        client.get(PATH + "contributions", params={"limit": 1, "offset": 1}).json()
        == []
    )
    assert (
        client.get(PATH + "contributions/" + cid).json()["review_status"] == "pending"
    )
    assert (
        client.put(
            PATH + "contributions/" + cid,
            json={"text": "  Texto sintético   modificado "},
        ).json()["text"]
        == "Texto sintético modificado"
    )
    response = client.patch(
        PATH + "contributions/" + cid,
        json={"text": "Referencia sintética para cambiar contenido de un aporte <URL>"},
    )
    assert response.status_code == 200
    with pg.connect() as conn:
        assert conn.scalar(select(risk_flags.c.code)) == "evaluation_similarity"
    assert (
        client.patch(
            PATH + "contributions/" + cid, json={"review_status": "accepted"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            PATH + "contributions/" + cid,
            json={"text": "Correo sintético prueba@example.invalid"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            PATH + "contributions", json={**PAYLOAD, "text": response.json()["text"]}
        ).status_code
        == 409
    )
    assert client.delete(PATH + "contributions/" + cid).status_code == 204
    assert client.get(PATH + "contributions/" + cid).status_code == 404
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(labels)) == 0
        assert conn.scalar(select(func.count()).select_from(risk_flags)) == 0


def test_labels_crud_constraints_and_terminal_reviews(system, pg):
    client, _ = system
    cid = new_contribution(client)
    original = client.get(PATH + "message-labels").json()[0]
    assert client.delete(PATH + "message-labels/" + original["id"]).status_code == 409
    data = {"message_id": cid, "category": "smishing", "source": "manual"}
    created = client.post(PATH + "message-labels", json=data)
    assert created.status_code == 201, created.text
    lid = created.json()["id"]
    assert created.json()["model_version_id"] is None
    assert client.get(PATH + "message-labels/" + lid).status_code == 200
    assert (
        client.put(
            PATH + "message-labels/" + lid, json={**data, "category": "safe"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            PATH + "message-labels/" + lid, json={"category": "smishing"}
        ).status_code
        == 200
    )
    assert client.patch(PATH + "message-labels/" + lid, json={}).status_code == 422
    assert client.delete(PATH + "message-labels/" + lid).status_code == 204
    assert (
        client.post(
            PATH + "message-labels", json={**data, "source": "device"}
        ).status_code
        == 422
    )
    with pg.connect() as conn:
        mid = str(conn.scalar(select(model_versions.c.id)))
    assert (
        client.post(
            PATH + "message-labels", json={**data, "model_version_id": mid}
        ).status_code
        == 422
    )
    assert (
        client.post(
            PATH + "message-labels",
            json={**data, "source": "device", "model_version_id": mid},
        ).status_code
        == 409
    )
    PostgresReviewRepository(pg).decide(
        cid,
        "reviewer-demo",
        ReviewDecision("accepted", "quality_checked", "safe", True),
    )
    assert (
        client.patch(
            PATH + "contributions/" + cid, json={"text": "Cambio sintético prohibido"}
        ).status_code
        == 409
    )
    assert client.post(PATH + "message-labels", json=data).status_code == 409
    assert client.delete(PATH + "message-labels/" + original["id"]).status_code == 409
    assert client.delete(PATH + "contributions/" + cid).status_code == 204


def test_models_crud_preserves_publication_and_referenced_model(system):
    client, _ = system
    original = client.get(PATH + "model-versions").json()[0]
    created = client.post(PATH + "model-versions", json={"release_tag": "v2.0.0"})
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    assert created.json()["version_tag"] == "2.0.0"
    assert client.get(PATH + "model-versions/" + identity).status_code == 200
    assert (
        client.put(
            PATH + "model-versions/" + identity, json={"release_tag": "v3.0.0"}
        ).json()["version_tag"]
        == "3.0.0"
    )
    assert (
        client.patch(
            PATH + "model-versions/" + identity, json={"release_tag": "v4.0.0"}
        ).json()["version_tag"]
        == "4.0.0"
    )
    new_contribution(client)
    assert client.delete(PATH + "model-versions/" + original["id"]).status_code == 409
    assert (
        client.put(
            PATH + "model-versions/" + original["id"], json={"release_tag": "v5.0.0"}
        ).status_code
        == 409
    )
    assert client.delete(PATH + "model-versions/" + identity).status_code == 204
    assert client.get(PATH + "model-versions/" + identity).status_code == 404


@pytest.mark.parametrize(
    "resource", ["contributions", "message-labels", "model-versions"]
)
def test_missing_errors_no_input_echo_and_http_body_limit(system, resource):
    client, _ = system
    identity = str(uuid4())
    assert client.get(PATH + resource + "/" + identity).status_code == 404
    assert client.delete(PATH + resource + "/" + identity).status_code == 404
    invalid = client.post(
        PATH + resource, json={"text": "SYNTHETIC_PRIVATE", "id": identity}
    )
    assert invalid.status_code == 422 and "SYNTHETIC_PRIVATE" not in invalid.text
    assert client.post(PATH + resource, content=b" " * 16385).status_code == 413
    assert client.get("http://testserver" + PATH + resource).status_code == 400


def test_admin_credentials_separate_and_public_contract_unchanged(system):
    client, _ = system
    schema = client.app.openapi()
    for resource in ["contributions", "message-labels", "model-versions"]:
        assert set(schema["paths"][PATH + resource]) == {"get", "post"}
        assert set(schema["paths"][PATH + resource + "/{identity}"]) == {
            "get",
            "put",
            "patch",
            "delete",
        }
    public = create_app(Settings()).openapi()
    assert set(public["paths"][PATH + "contributions"]) == {"post"}
    with pytest.raises(RuntimeError):
        create_admin_app(
            AdminSettings(credentials={"admin": SecretStr("shared")}),
            Settings(api_key=SecretStr("shared")),
        )
    with pytest.raises(RuntimeError):
        create_admin_app(
            AdminSettings(credentials={"admin": SecretStr("shared")}),
            Settings(),
            reviewers=ReviewSettings(credentials={"reviewer": SecretStr("shared")}),
        )


def test_duplicate_edit_rolls_back_text_and_hash(system):
    client, _ = system
    cid = new_contribution(client)
    second = client.post(
        PATH + "contributions",
        json={**PAYLOAD, "text": "Otro aporte sintético distinto <URL>"},
    ).json()
    original = client.get(PATH + "contributions/" + cid).json()
    assert (
        client.put(
            PATH + "contributions/" + cid, json={"text": second["text"]}
        ).status_code
        == 409
    )
    assert client.get(PATH + "contributions/" + cid).json() == original


def test_admin_real_https_with_verified_certificate(system, tmp_path):
    import socket
    import ssl
    import subprocess
    import threading
    import time

    import httpx
    import uvicorn

    app = system[0].app
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
    base = f"https://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            access_log=False,
            log_config=None,
            proxy_headers=False,
        )
    )
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
            verify=ssl.create_default_context(cafile=str(cert)),
            trust_env=False,
            base_url=base,
        ) as client:
            assert client.get(PATH + "contributions").status_code == 401
            response = client.post(PATH + "contributions", headers=AUTH, json=PAYLOAD)
            assert response.status_code == 201
            cid = response.json()["id"]
            assert (
                client.get(PATH + "contributions/" + cid, headers=AUTH).status_code
                == 200
            )
            assert (
                client.patch(
                    PATH + "contributions/" + cid,
                    headers=AUTH,
                    json={"text": "Texto sintético para prueba TLS <URL>"},
                ).status_code
                == 200
            )
            assert (
                client.delete(PATH + "contributions/" + cid, headers=AUTH).status_code
                == 204
            )
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
    assert not thread.is_alive()
