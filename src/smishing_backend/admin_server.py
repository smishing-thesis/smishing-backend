"""TLS runner for the separate internal administration API."""

import os
from pathlib import Path

import uvicorn

from smishing_backend.logging import logging_config


def main():
    uvicorn.run(
        "smishing_backend.admin:app",
        host="127.0.0.1",
        port=int(os.environ.get("SMISHING_ADMIN_PORT", "8445")),
        ssl_certfile=os.environ["TLS_CERT_PATH"],
        ssl_keyfile=os.environ["TLS_KEY_PATH"],
        access_log=False,
        proxy_headers=False,
        log_config=logging_config(
            Path(os.environ.get("SMISHING_LOG_DIR", "var/log/smishing-admin"))
        ),
    )


if __name__ == "__main__":
    main()
