import csv
import hashlib
import importlib.util
import io
from importlib.machinery import SourceFileLoader
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, update
from test_management import ADMIN, DECISION, MOBILE, PATH, REVIEWER, contribute
from test_management import client as client

from smishing_backend.data.repositories.poisoning import flag_content
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.data.schema import contributions

CSV = "/api/v1/admin/corpus/accepted.csv"


def test_final_corpus_http_and_real_model_reader(client, pg, tmp_path):
    removed_by_state = contribute(client, "Aporte sintético todavía pendiente <URL>")
    rejected = contribute(client, "Aporte sintético fuera del alcance <URL>")
    legacy = contribute(client, "Aporte de prueba histórica sin revisión manual")
    flagged = contribute(client, "Aporte sintético con una alerta posterior")
    selected = [
        contribute(client, "Aporte sintético con etiqueta manual segura"),
        contribute(client, "Aporte sintético de aviso clasificado <URL>"),
    ]
    client.patch(
        f"{PATH}/{rejected}/review",
        headers=ADMIN,
        json={**DECISION, "decision": "rejected", "reason": "out_of_scope"},
    )
    with pg.begin() as connection:
        connection.execute(
            update(contributions)
            .where(contributions.c.id == UUID(legacy))
            .values(
                status="accepted",
                reviewed_at=func.now(),
                review_reason="quality_checked",
            )
        )
    for identity, label in [
        (flagged, "safe"),
        (selected[0], "safe"),
        (selected[1], "smishing"),
    ]:
        response = client.patch(
            f"{PATH}/{identity}/review",
            headers=ADMIN,
            json={**DECISION, "label": label},
        )
        assert response.status_code == 200
    with pg.begin() as connection:
        flag_content(connection, UUID(flagged), "label_conflict")
    for credential in ({}, MOBILE, REVIEWER):
        assert client.get(CSV, headers=credential).status_code == 401
    first = client.get(CSV, headers=ADMIN)
    second = client.get(CSV, headers=ADMIN)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-corpus-rows"] == "2"
    assert first.headers["x-corpus-excluded"] == "2"
    version = first.headers["x-corpus-version"]
    date = first.headers["x-corpus-date"]
    assert (
        first.headers["content-disposition"]
        == f'attachment; filename="corpus-{date}-{version}.csv"'
    )
    assert first.content.startswith(b"text,label,") and b"\r\n" not in first.content
    rows = list(csv.DictReader(io.StringIO(first.text)))
    assert {row["label"] for row in rows} == {"0", "1"}
    assert {row["model_version"] for row in rows} == {"1.0.0"}
    assert {row["label_origin"] for row in rows} == {"manual"}
    assert {row["corpus_version"] for row in rows} == {version}
    assert all(
        identity.encode() not in first.content
        for identity in [removed_by_state, rejected, legacy, flagged, *selected]
    )
    assert "operador" not in first.text
    assert len(PostgresQuarantineRepository(pg).accepted_for_training()) == 3
    source = Path("tests/compat/charcnn-sources-b9c72dc.py.txt")
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == "2302f3c51b816e613aff3558112d7da1bcef42b25e3e3435f414d91824622b0a"
    )
    loader = SourceFileLoader("real_model_reader", str(source))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    path = tmp_path / "synthetic.csv"
    path.write_bytes(first.content)
    frame = module.load_local_legit_corpus(path)
    assert len(frame) == 2 and set(frame["y"]) == {0, 1}


def test_empty_final_corpus(client):
    response = client.get(CSV, headers=ADMIN)
    assert response.status_code == 200 and response.headers["x-corpus-rows"] == "0"
    assert response.content == b"text,label,label_origin,model_version,corpus_version\n"
