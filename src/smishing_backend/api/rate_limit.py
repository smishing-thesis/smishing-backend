"""Single-process fixed-window limits with expiring, keyed network counters."""

import hashlib
import hmac
import math
import secrets
import threading
import time
from typing import Annotated

from fastapi import Depends, Request

from smishing_backend.api.authentication import require_application
from smishing_backend.api.contracts import ContributionInput
from smishing_backend.api.validation import fail, validate_contribution


class RateLimiter:
    def __init__(
        self,
        per_network: int,
        global_limit: int,
        window: float = 60,
        clock=time.monotonic,
    ):
        self.per_network = per_network
        self.global_limit = global_limit
        self.window = window
        self.clock = clock
        self.lock = threading.Lock()
        self.counts: dict[bytes, int] = {}
        self.total = 0
        self.deadline = 0.0
        self.salt = b""
        self.timer: threading.Timer | None = None

    def _clear(self):
        self.counts.clear()
        self.salt = b""
        self.total = 0
        self.deadline = 0.0

    def expire(self):
        with self.lock:
            if self.clock() >= self.deadline:
                self._clear()

    def close(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self._clear()

    def admit(self, network: str) -> int | None:
        with self.lock:
            now = self.clock()
            if now >= self.deadline:
                if self.timer:
                    self.timer.cancel()
                self._clear()
                self.deadline = now + self.window
                self.salt = secrets.token_bytes(32)
                self.timer = threading.Timer(self.window, self.expire)
                self.timer.daemon = True
                self.timer.start()
            retry = max(1, math.ceil(self.deadline - now))
            # Stop before allocating a new bucket; memory is bounded by global_limit.
            if self.total >= self.global_limit:
                return retry
            key = hmac.digest(self.salt, network.encode(), hashlib.sha256)
            if self.counts.get(key, 0) >= self.per_network:
                return retry
            self.counts[key] = self.counts.get(key, 0) + 1
            self.total += 1
            return None


async def limited_contribution(
    request: Request, authenticated: Annotated[None, Depends(require_application)]
) -> ContributionInput:
    # Only the immediate peer is trusted. Do not consume user-controlled forwarding headers.
    peer = request.client.host if request.client else "unknown"
    retry = request.app.state.rate_limiter.admit(peer)
    if retry is not None:
        error = fail(429)
        error.headers = {"Retry-After": str(retry)}
        raise error
    return await validate_contribution(request)
