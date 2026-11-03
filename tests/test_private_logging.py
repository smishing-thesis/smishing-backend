import json
import logging
from logging.handlers import TimedRotatingFileHandler

from fastapi.testclient import TestClient
from pydantic import SecretStr

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.logging import PrivateFormatter, audit, logging_config
from smishing_backend.main import create_app


def test_accepted_and_rejected_logs_do_not_contain_text_or_addresses(pg, tmp_path):
    path = tmp_path / "events.jsonl"
    handler = TimedRotatingFileHandler(path, when="midnight", backupCount=6, utc=True)
    handler.setFormatter(PrivateFormatter())
    original_level = audit.level
    audit.setLevel(logging.INFO)
    audit.addHandler(handler)
    secret = "Texto sintético singular privado"
    app = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    try:
        with TestClient(
            app, base_url="https://testserver", client=("192.0.2.42", 12345)
        ) as client:
            assert (
                client.post(
                    "/api/v1/contributions",
                    headers={"X-API-Key": "synthetic"},
                    json={"text": secret, "label": "safe", "model_version": "1.0.0"},
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/v1/contributions",
                    headers={"X-API-Key": "synthetic"},
                    json={"text": secret, "device_id": "synthetic-device"},
                ).status_code
                == 422
            )
        try:
            raise RuntimeError(secret + " 192.0.2.42 synthetic-device")
        except RuntimeError:
            audit.exception(
                "untrusted %s", secret, extra={"device": "synthetic-device"}
            )
        handler.flush()
        contents = path.read_text()
        assert all(
            value not in contents
            for value in [
                secret,
                "192.0.2.42",
                "synthetic-device",
                "synthetic",
                "RuntimeError",
                "Traceback",
            ]
        )
        events = [json.loads(line) for line in contents.splitlines()]
        assert [event["event"] for event in events] == [
            "contribution_accepted",
            "contribution_rejected",
            "runtime_event",
        ]
        assert all(set(event) == {"time", "event"} for event in events)
    finally:
        audit.removeHandler(handler)
        audit.setLevel(original_level)
        handler.close()


def test_retention_and_server_logger_config(tmp_path):
    config = logging_config(tmp_path)
    handler = config["handlers"]["private_file"]
    assert (
        handler["backupCount"] == 6 and handler["when"] == "midnight" and handler["utc"]
    )
    assert all(
        logger["handlers"] == [] and logger["propagate"]
        for logger in config["loggers"].values()
    )
    formatter = PrivateFormatter()
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s"',
        ("192.0.2.42", "private"),
        None,
    )
    assert json.loads(formatter.format(record))["event"] == "runtime_event"
