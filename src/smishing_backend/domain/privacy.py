"""Residual verification against versioned sms-anonymizer rules; never rewrites SMS."""

import json
import re
import threading
from functools import lru_cache
from importlib.resources import files

RULES = json.loads(
    files("smishing_backend.domain")
    .joinpath("resources/anonymization-1.3.0.json")
    .read_text()
)
RULES_VERSION = RULES["rules_version"]
MODEL_NAME = "es_core_news_lg"
MODEL_VERSION = "3.8.0"
_regexes = tuple(
    re.compile(rule["pattern"], re.IGNORECASE)
    for rule in RULES["text_rules"]
    if rule["kind"] == "regex"
)
_placeholders = re.compile(
    "|".join(re.escape(rule["placeholder"]) for rule in RULES["text_rules"])
)
_lock = threading.Lock()


class ResidualPersonalData(Exception):
    """A generic rejection with no matching text or spans attached."""


class AnonymizationUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def load_name_detector():
    try:
        import spacy

        detector = spacy.load(
            MODEL_NAME,
            exclude=["parser", "morphologizer", "attribute_ruler", "lemmatizer"],
        )
        if (
            detector.meta.get("version") != MODEL_VERSION
            or "ner" not in detector.pipe_names
        ):
            raise AnonymizationUnavailable()
        return detector
    except Exception:  # noqa: BLE001 - fail closed without exposing third-party input diagnostics
        raise AnonymizationUnavailable() from None


def assert_anonymized(text: str) -> None:
    # Only documented placeholders are removed from the detection view.
    view = _placeholders.sub(" ", text)
    if any(pattern.search(view) for pattern in _regexes):
        raise ResidualPersonalData()
    with _lock:
        try:
            doc = load_name_detector()(view)
            contains_person = any(entity.label_ == "PER" for entity in doc.ents)
        except AnonymizationUnavailable:
            raise
        except Exception:  # noqa: BLE001 - fail closed without exposing third-party input diagnostics
            raise AnonymizationUnavailable() from None
    if contains_person:
        raise ResidualPersonalData()
