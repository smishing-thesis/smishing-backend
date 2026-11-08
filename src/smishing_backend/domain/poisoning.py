"""Heuristic corpus signals, never a classification or attribution of an attacker."""

import hashlib
from dataclasses import dataclass

from smishing_backend.domain.text import normalize_text

SIGNALS = ("similarity_burst", "label_conflict", "class_shift", "evaluation_similarity")


@dataclass(frozen=True)
class ObservedContribution:
    text: str
    label: str


@dataclass(frozen=True)
class PoisoningPolicy:
    window_seconds: int = 300
    history_limit: int = 500
    similarity_threshold: float = 0.9
    similar_count: int = 5
    min_text_length: int = 30
    min_baseline: int = 20
    min_recent: int = 10
    class_delta: float = 0.4
    evaluation_threshold: float = 0.9
    evaluation_references: tuple[frozenset[str], ...] = ()


def fingerprint(text: str) -> frozenset[str]:
    folded = normalize_text(text).casefold()
    return frozenset(
        hashlib.sha256(folded[i : i + 3].encode("utf-8")).hexdigest()
        for i in range(max(0, len(folded) - 2))
    )


def similarity(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def assess(
    text: str,
    label: str,
    recent: list[ObservedContribution],
    baseline: list[ObservedContribution],
    policy: PoisoningPolicy,
) -> tuple[str, ...]:
    flags = []
    if len(text) >= policy.min_text_length:
        value = fingerprint(text)
        near = sum(
            len(row.text) >= policy.min_text_length
            and similarity(value, fingerprint(row.text)) >= policy.similarity_threshold
            for row in recent
        )
        if near + 1 >= policy.similar_count:
            flags.append("similarity_burst")
        if any(
            similarity(value, reference) >= policy.evaluation_threshold
            for reference in policy.evaluation_references
        ):
            flags.append("evaluation_similarity")
    if len(baseline) >= policy.min_baseline and len(recent) + 1 >= policy.min_recent:
        old_ratio = sum(row.label == "smishing" for row in baseline) / len(baseline)
        new_ratio = (
            sum(row.label == "smishing" for row in recent) + (label == "smishing")
        ) / (len(recent) + 1)
        if abs(new_ratio - old_ratio) >= policy.class_delta:
            flags.append("class_shift")
    return tuple(flags)
