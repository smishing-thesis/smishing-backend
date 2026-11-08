from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, update

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, labels
from smishing_backend.main import create_app

PAYLOAD = {
    "text": "Mensaje sintético [URL]",
    "label": "smishing",
    "model_version": "1.0.0",
}


@pytest.mark.parametrize(
    "text",
    [
        PAYLOAD["text"],
        "  Mensaje\n sintético\t [URL]  ",
        "Mensaje sinte\u0301tico [URL]",
    ],
)
@pytest.mark.parametrize("status", ["pending", "accepted", "rejected"])
def test_duplicates_do_not_disclose_status(pg, text, status):
    app = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    with TestClient(
        app, base_url="https://testserver", headers={"X-API-Key": "synthetic"}
    ) as client:
        assert client.post("/api/v1/contributions", json=PAYLOAD).status_code == 201
        with pg.begin() as conn:
            conn.execute(update(contributions).values(status=status))
        response = client.post("/api/v1/contributions", json={**PAYLOAD, "text": text})
        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "duplicate_contribution",
                "message": "El aporte ya existe.",
            }
        }
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 1
        assert conn.scalar(select(func.count()).select_from(labels)) == 1


def test_concurrent_duplicate_requests(pg):
    app = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    barrier = Barrier(2)
    with TestClient(
        app, base_url="https://testserver", headers={"X-API-Key": "synthetic"}
    ) as client:

        def send(_):
            barrier.wait(timeout=5)
            return client.post("/api/v1/contributions", json=PAYLOAD).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(send, range(2))) == [201, 409]
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 1
        assert conn.scalar(select(func.count()).select_from(labels)) == 1
