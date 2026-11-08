"""Publish a complete, content-addressed export directory atomically."""

import os
import tempfile
from pathlib import Path

from smishing_backend.domain.corpus_export import CorpusArtifact, InvalidCorpusExport


def write_corpus(artifact: CorpusArtifact, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / artifact.version
    files = {"corpus.csv": artifact.csv_bytes, "manifest.json": artifact.manifest_bytes}

    def matches():
        return target.is_dir() and all(
            (target / name).is_file() and (target / name).read_bytes() == payload
            for name, payload in files.items()
        )

    if target.exists():
        if not matches():
            raise InvalidCorpusExport(
                "Existing export does not match its content version"
            )
        return target / "corpus.csv"
    with tempfile.TemporaryDirectory(prefix=".corpus-", dir=directory) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir(mode=0o700)
        for name, payload in files.items():
            fd = os.open(staging / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        try:
            staging.rename(target)
        except OSError:
            if not matches():
                raise InvalidCorpusExport(
                    "Cannot publish the complete corpus export"
                ) from None
    return target / "corpus.csv"
