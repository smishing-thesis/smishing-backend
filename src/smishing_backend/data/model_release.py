"""Read only aggregate fields from the model repository's published metadata."""

import hashlib
import json
import re
import subprocess
from datetime import datetime

from smishing_backend.domain.model_catalog import (
    InvalidModelPublication,
    ModelPublication,
)

MODEL_REPOSITORY = "smishing-thesis/charcnn-smishing-model"
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?")
HYPERPARAMETERS = frozenset(
    {
        "embedding_dim",
        "conv_filters",
        "kernel_size",
        "dense_units",
        "maxlen",
        "optimizer",
        "loss",
        "epochs",
        "batch_size",
        "early_stopping_patience",
        "early_stopping_monitor",
        "class_weight",
        "val_fraction",
        "target_fpr",
    }
)
VALIDATION_METRICS = frozenset(
    {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "fpr",
        "balanced_accuracy",
        "tp",
        "fp",
        "tn",
        "fn",
    }
)
EXTERNAL_METRICS = frozenset({"n", "detected", "recall_at_threshold", "median_score"})


def parse_publication(
    release: dict, training: dict, evaluation: dict
) -> ModelPublication:
    try:
        version = training["model_version"]
        if (
            not isinstance(version, str)
            or not VERSION.fullmatch(version)
            or len(version) > 20
        ):
            raise ValueError
        tag = release["tag_name"]
        url = f"https://github.com/{MODEL_REPOSITORY}/releases/tag/{tag}"
        if (
            tag != "v" + version
            or release.get("html_url") != url
            or release.get("draft")
        ):
            raise ValueError
        if (
            evaluation["model_version"] != version
            or evaluation["model_sha256"] != training["model_sha256"]
        ):
            raise ValueError
        for digest in [training["model_sha256"], training["dataset_sha256"]]:
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError
        dates = [
            datetime.fromisoformat(training["trained_at"].replace("Z", "+00:00")),
            datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")),
        ]
        if any(date.tzinfo is None for date in dates) or dates[0] > dates[1]:
            raise ValueError
        corpus = training["corpus_version"]
        if not isinstance(corpus, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", corpus
        ):
            raise ValueError
        parameters = {key: training["hyperparameters"][key] for key in HYPERPARAMETERS}
        if any(
            isinstance(v, bool) or not isinstance(v, (str, int, float))
            for v in parameters.values()
        ):
            raise ValueError
        if any(
            isinstance(v, str) and not re.fullmatch(r"[A-Za-z0-9_. -]{1,64}", v)
            for v in parameters.values()
        ):
            raise ValueError
        metrics = {
            "validation": {
                key: evaluation["validation_metrics_at_threshold"][key]
                for key in VALIDATION_METRICS
            },
            "external": {
                key: evaluation["external_imc25_peru"][key] for key in EXTERNAL_METRICS
            },
            "threshold": evaluation["threshold"],
        }
        numbers = [
            *metrics["validation"].values(),
            *metrics["external"].values(),
            metrics["threshold"],
        ]
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0
            for v in numbers
        ):
            raise ValueError
        if any(
            not 0 <= metrics["validation"][key] <= 1
            for key in ("accuracy", "precision", "recall", "f1")
        ):
            raise ValueError
        # Do not persist dataset_path, training history, robustness-suite SMS or unknown fields.
        facts = {
            "version": version,
            "trained_at": dates[0].isoformat(),
            "published_at": dates[1].isoformat(),
            "corpus_version": corpus,
            "dataset_sha256": training["dataset_sha256"],
            "hyperparameters": parameters,
            "metrics": metrics,
            "release_tag": tag,
            "release_url": url,
        }
        digest = hashlib.sha256(
            json.dumps(
                facts, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        return ModelPublication(
            version,
            dates[0],
            dates[1],
            corpus,
            training["dataset_sha256"],
            parameters,
            metrics,
            tag,
            url,
            digest,
        )
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        raise InvalidModelPublication(
            "Invalid or inconsistent model publication metadata"
        ) from None


def _gh_json(endpoint: str, asset: bool = False) -> dict:
    args = ["gh", "api", endpoint]
    if asset:
        args += ["-H", "Accept: application/octet-stream"]
    try:
        result = subprocess.run(args, capture_output=True, timeout=60, check=True)
        if len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (OSError, subprocess.SubprocessError, ValueError):
        raise InvalidModelPublication(
            "Cannot read model release; check GitHub CLI access"
        ) from None


def read_github_publication(tag: str) -> ModelPublication:
    if not tag.startswith("v") or not VERSION.fullmatch(tag[1:]) or len(tag) > 21:
        raise InvalidModelPublication("Invalid release tag")
    release = _gh_json(f"repos/{MODEL_REPOSITORY}/releases/tags/{tag}")
    assets = {}
    for name in ["training_metadata.json", "evaluation.json"]:
        matching = [a for a in release.get("assets", []) if a.get("name") == name]
        if len(matching) != 1 or not isinstance(matching[0].get("id"), int):
            raise InvalidModelPublication("Missing or ambiguous release metadata asset")
        assets[name] = _gh_json(
            f"repos/{MODEL_REPOSITORY}/releases/assets/{matching[0]['id']}", asset=True
        )
    return parse_publication(
        release, assets["training_metadata.json"], assets["evaluation.json"]
    )
