"""Scheme handling for a proxy that terminates TLS in front of the application."""

from starlette.types import ASGIApp, Receive, Scope, Send


class ForwardedProto:
    """Mark the request as HTTPS only when the proxy says so, exactly once.

    Only X-Forwarded-Proto is read. X-Forwarded-For and the client address are never
    used, so no network identity reaches the application. Without the header, or with
    anything other than a single "https", the scheme stays "http" and the contribution
    routes answer 400. Valid only when the application port is reachable solely through
    the proxy.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            values = [
                value
                for name, value in scope["headers"]
                if name == b"x-forwarded-proto"
            ]
            if len(values) == 1 and values[0].strip().lower() == b"https":
                scope = {**scope, "scheme": "https"}
        await self.app(scope, receive, send)
