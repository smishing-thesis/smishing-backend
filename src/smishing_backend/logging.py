"""Allowlisted event logs: never interpolate arbitrary runtime messages."""

import json
import logging
import logging.config
import re
import threading
import time
from datetime import UTC, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

EVENTS = frozenset(
    {"contribution_accepted", "contribution_rejected", "service_unavailable"}
)
audit = logging.getLogger("smishing_backend.audit")


class RetainedEventHandler(TimedRotatingFileHandler):
    """Seven UTC calendar days; maintenance does not depend on new requests."""

    def __init__(self, filename: str, cleanup_interval: float = 60):
        super().__init__(
            filename, when="midnight", backupCount=6, utc=True, encoding="utf-8"
        )
        self._stop = threading.Event()
        self._cleanup_interval = cleanup_interval
        self.retention_error = False
        self._maintain()
        self._worker = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._worker.start()

    def _maintain(self):
        self.acquire()
        try:
            if self._stop.is_set():
                return
            if time.time() >= self.rolloverAt:
                self.doRollover()
            cutoff = datetime.now(UTC).date() - timedelta(days=6)
            active = Path(self.baseFilename)
            pattern = re.compile(re.escape(active.name) + r"\.(\d{4}-\d{2}-\d{2})")
            for path in active.parent.iterdir():
                match = pattern.fullmatch(path.name)
                if match and path.is_file() and not path.is_symlink():
                    try:
                        day = datetime.strptime(match[1], "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if day < cutoff:
                        path.unlink()
            self.retention_error = False
        finally:
            self.release()

    def _cleanup_loop(self):
        while not self._stop.wait(self._cleanup_interval):
            try:
                self._maintain()
            except OSError:
                self.retention_error = True

    def emit(self, record):
        try:
            self._maintain()
        except OSError:
            raise RuntimeError("Private log retention unavailable") from None
        super().emit(record)

    def handleError(self, record):
        # logging's default error path prints the unformatted message and args.
        raise RuntimeError("Private log storage unavailable") from None

    def close(self):
        self._stop.set()
        worker = getattr(self, "_worker", None)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2)
        super().close()


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
                "()": RetainedEventHandler,
                "filename": str(directory / "events.jsonl"),
                "formatter": "private",
            },
        },
        "root": {"handlers": ["private_file"], "level": "INFO"},
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
