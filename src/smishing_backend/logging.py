"""Allowlisted event logs: never interpolate arbitrary runtime messages."""

import json
import logging
import logging.config
from datetime import UTC, datetime
from pathlib import Path

EVENTS = frozenset(
    {"contribution_accepted", "contribution_rejected", "service_unavailable"}
)
audit = logging.getLogger("smishing_backend.audit")


class PrivateFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = "runtime_event"
        if (
            record.name == "smishing_backend.audit"
            and isinstance(record.msg, str)
            and record.msg in EVENTS
        ):
            event = record.msg
        # Do not call getMessage, formatException or formatStack. Do not include extras.
        return json.dumps(
            {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "event": event,
            }
        )


def logging_config(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"private": {"()": PrivateFormatter}},
        "handlers": {
            "private_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(directory / "events.jsonl"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 6,
                "utc": True,
                "encoding": "utf-8",
                "formatter": "private",
            },
            "private_console": {
                "class": "logging.StreamHandler",
                "formatter": "private",
            },
        },
        "root": {"handlers": ["private_file", "private_console"], "level": "INFO"},
        "loggers": {
            name: {"handlers": [], "propagate": True, "level": "INFO"}
            for name in [
                "uvicorn",
                "uvicorn.error",
                "uvicorn.access",
                "httpx",
                "sqlalchemy",
                "smishing_backend.audit",
            ]
        },
    }
