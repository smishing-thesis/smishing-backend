"""Health service."""

from typing import Literal


def health_status() -> Literal["ok"]:
    return "ok"
