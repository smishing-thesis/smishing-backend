"""Supported runner for the public API: local TLS, or behind a TLS-terminating proxy."""

import os
from pathlib import Path

import uvicorn

from smishing_backend.config import Settings
from smishing_backend.logging import logging_config


def main():
    # The proxy mode is chosen with SMISHING_BEHIND_TLS_PROXY; off by default.
    if Settings().behind_tls_proxy:
        # The platform terminates TLS and forwards HTTP to the port it expects (8000 is
        # the App Service default for Python). The application must be reachable only
        # through that proxy; see docs/deployment.md.
        address: dict = {
            "host": os.environ.get("SMISHING_HOST", "0.0.0.0"),
            "port": int(
                os.environ.get("PORT")
                or os.environ.get("WEBSITES_PORT")
                or os.environ.get("SMISHING_PORT", "8000")
            ),
        }
    else:
        address = {
            "host": "127.0.0.1",
            "port": int(os.environ.get("SMISHING_PORT", "8443")),
            "ssl_certfile": os.environ["TLS_CERT_PATH"],
            "ssl_keyfile": os.environ["TLS_KEY_PATH"],
        }
    uvicorn.run(
        "smishing_backend.main:app",
        **address,
        access_log=False,
        proxy_headers=False,
        log_config=logging_config(
            Path(os.environ.get("SMISHING_LOG_DIR", "var/log/smishing-backend"))
        ),
    )


if __name__ == "__main__":
    main()
