"""Corpus normalization, independent from model preprocessing."""

import hashlib
import unicodedata


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        " " if unicodedata.category(char) in {"Cc", "Cf"} else char for char in text
    )
    return " ".join(text.split())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
