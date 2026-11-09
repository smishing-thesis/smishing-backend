"""TLS runner for the separate internal review API."""

import os
from pathlib import Path

import uvicorn

from smishing_backend.logging import logging_config


def main():
    uvicorn.run(
        "smishing_backend.review:app",
        host="127.0.0.1",
        port=int(os.environ.get("SMISHING_REVIEW_PORT", "8444")),
        ssl_certfile=os.environ["TLS_CERT_PATH"],
        ssl_keyfile=os.environ["TLS_KEY_PATH"],
        access_log=False,
        proxy_headers=False,
        log_config=logging_config(
            Path(os.environ.get("SMISHING_LOG_DIR", "var/log/smishing-review"))
        ),
    )


if __name__ == "__main__":
    main()
