import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

from fastapi.testclient import TestClient
from pydantic import SecretStr

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.logging import (
    PrivateFormatter,
    RetainedEventHandler,
    audit,
    logging_config,
)
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
    assert handler["()"] is RetainedEventHandler
    assert config["root"]["handlers"] == ["private_file"]
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


def test_retention_cleans_old_active_and_archives_on_startup(tmp_path):
    active = tmp_path / "events.jsonl"
    active.write_text("OLD_SYNTHETIC_EVENT")
    old_time = time.time() - 10 * 86400
    os.utime(active, (old_time, old_time))
    today = datetime.now(UTC).date()
    stale = tmp_path / f"events.jsonl.{today - timedelta(days=9)}"
    stale.write_text("expired")
    fresh = tmp_path / f"events.jsonl.{today - timedelta(days=1)}"
    fresh.write_text("retained")
    other = tmp_path / "unrelated.jsonl.2000-01-01"
    other.write_text("untouched")
    handler = RetainedEventHandler(str(active))
    try:
        assert active.read_text() == ""
        assert not stale.exists()
        assert fresh.read_text() == "retained" and other.read_text() == "untouched"
        assert not any(
            "OLD_SYNTHETIC_EVENT" in p.read_text() for p in tmp_path.iterdir()
        )
    finally:
        handler.close()


def test_retention_expires_without_any_log_event_and_worker_stops(tmp_path):
    handler = RetainedEventHandler(
        str(tmp_path / "events.jsonl"), cleanup_interval=0.02
    )
    stale = tmp_path / "events.jsonl.2000-01-01"
    stale.write_text("expired")
    deadline = time.monotonic() + 2
    try:
        while stale.exists() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert not stale.exists()
    finally:
        handler.close()
    assert not handler._worker.is_alive()


def test_storage_failure_does_not_print_raw_record(tmp_path, capsys, monkeypatch):
    import pytest

    handler = RetainedEventHandler(str(tmp_path / "events.jsonl"))
    record = logging.LogRecord(
        "dependency", logging.INFO, "", 0, "SYNTHETIC_PRIVATE %s", ("192.0.2.42",), None
    )
    try:
        with pytest.raises(RuntimeError, match="Private log storage unavailable"):
            handler.handleError(record)
        assert "SYNTHETIC_PRIVATE" not in capsys.readouterr().err
    finally:
        handler.close()


def test_supported_logging_configuration_writes_only_private_file(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import logging, logging.config, sys; from smishing_backend.logging import logging_config; logging.config.dictConfig(logging_config(Path(sys.argv[1]))); logging.warning('SYNTHETIC_PRIVATE %s', '192.0.2.42'); logging.shutdown()",
            str(tmp_path),
        ],
        capture_output=True,
        check=True,
        timeout=5,
    )
    assert result.stdout == result.stderr == b""
    content = (tmp_path / "events.jsonl").read_text()
    assert "SYNTHETIC_PRIVATE" not in content and "192.0.2.42" not in content
    assert json.loads(content)["event"] == "runtime_event"
