import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from smishing_backend.api.contracts import ContributionInput
from smishing_backend.api.rate_limit import RateLimiter, limited_contribution
from smishing_backend.api.validation import contribution_error_handler
from smishing_backend.config import Settings


def test_limit_expiration_and_logs(caplog):
    now = [1.0]
    limiter = RateLimiter(1, 2, clock=lambda: now[0])
    try:
        assert limiter.admit("192.0.2.1") is None
        assert limiter.admit("192.0.2.1") == 60
        assert limiter.admit("192.0.2.2") is None
        assert limiter.admit("192.0.2.3") == 60
        assert len(limiter.counts) == 2
        assert all(isinstance(key, bytes) and len(key) == 32 for key in limiter.counts)
        now[0] = 61.0
        limiter.expire()
        assert limiter.counts == {} and limiter.salt == b""
        assert limiter.admit("192.0.2.1") is None
        assert "192.0.2." not in caplog.text
    finally:
        limiter.close()


def test_timer_expires_without_request():
    cleared = threading.Event()

    class ObservedLimiter(RateLimiter):
        def expire(self):
            super().expire()
            cleared.set()

    limiter = ObservedLimiter(1, 1, window=0.02)
    try:
        limiter.admit("192.0.2.1")
        assert cleared.wait(2)
        assert limiter.counts == {} and limiter.salt == b"" and limiter.total == 0
    finally:
        limiter.close()


def test_concurrent_global_limit():
    limiter = RateLimiter(100, 3)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(limiter.admit, [f"192.0.2.{i}" for i in range(30)]))
        assert results.count(None) == 3
        assert len(limiter.counts) == 3
    finally:
        limiter.close()


def test_429_before_body_or_handler():
    app = FastAPI()
    app.state.settings = Settings(api_key=SecretStr("synthetic"))
    app.state.rate_limiter = RateLimiter(1, 1)
    app.add_exception_handler(HTTPException, contribution_error_handler)
    calls = []

    @app.post("/limit")
    def submit(payload: Annotated[ContributionInput, Depends(limited_contribution)]):
        calls.append(True)
        return {"ok": True}

    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/limit",
                    headers={"X-API-Key": "synthetic"},
                    json={
                        "text": "Sintético",
                        "label": "safe",
                        "model_version": "1.0.0",
                    },
                ).status_code
                == 200
            )
            response = client.post(
                "/limit", headers={"X-API-Key": "synthetic"}, content=b"bad"
            )
            assert response.status_code == 429
            assert int(response.headers["Retry-After"]) > 0
            assert calls == [True]
    finally:
        app.state.rate_limiter.close()
