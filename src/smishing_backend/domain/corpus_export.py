"""Stable corpus serialization; no database, network or model inference."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass

LABELS = {"safe": 0, "smishing": 1}
FORMAT_VERSION = "smishing-backend-corpus-v1"
COLUMNS = ("text", "label", "label_origin", "model_version", "corpus_version")


class InvalidCorpusExport(Exception):
    pass


@dataclass(frozen=True)
class CorpusArtifact:
    version: str
    count: int
    csv_bytes: bytes
    manifest_bytes: bytes


def render_corpus(rows: list[dict]) -> CorpusArtifact:
    content = []
    for row in rows:
        text, value, origin, model = (
            row.get(key) for key in ("text", "label", "label_origin", "model_version")
        )
        if (
            not isinstance(text, str)
            or not text
            or value not in LABELS
            or origin not in {"manual", "device"}
        ):
            raise InvalidCorpusExport("Invalid accepted corpus record")
        if not isinstance(model, str) or not model:
            raise InvalidCorpusExport("Invalid accepted corpus provenance")
        content.append(
            {
                "text": text,
                "label": LABELS[value],
                "label_origin": origin,
                "model_version": model,
            }
        )
    content.sort(
        key=lambda row: (
            hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
            row["text"],
            row["label"],
            row["label_origin"],
            row["model_version"],
        )
    )
    canonical = json.dumps(
        {"format": FORMAT_VERSION, "rows": content},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    version = "backend-" + hashlib.sha256(canonical).hexdigest()
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({**row, "corpus_version": version} for row in content)
    csv_bytes = output.getvalue().encode("utf-8")
    manifest = {
        "format": FORMAT_VERSION,
        "corpus_version": version,
        "rows": len(content),
        "file": "corpus.csv",
        "sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "label_mapping": LABELS,
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return CorpusArtifact(version, len(content), csv_bytes, manifest_bytes)
