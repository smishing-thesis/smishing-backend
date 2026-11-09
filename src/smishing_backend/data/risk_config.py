import json
import re

from smishing_backend.config import Settings
from smishing_backend.domain.poisoning import PoisoningPolicy


def policy_from_settings(settings: Settings) -> PoisoningPolicy:
    references: tuple[frozenset[str], ...] = ()
    path = settings.poison_evaluation_fingerprints_path
    if path is not None:
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("format") != "char-ngrams-v1" or data.get("n") != 3:
                raise ValueError
            values = data["references"]
            if not isinstance(values, list) or not 1 <= len(values) <= 100:
                raise ValueError
            for row in values:
                if (
                    not isinstance(row, list)
                    or not 1 <= len(row) <= 2048
                    or any(
                        not isinstance(value, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", value)
                        for value in row
                    )
                ):
                    raise ValueError
            references = tuple(frozenset(row) for row in values)
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            raise RuntimeError("Invalid evaluation fingerprint configuration") from None
    if (
        settings.poison_min_baseline + settings.poison_min_recent
        > settings.poison_history_limit
    ):
        raise RuntimeError(
            "Poisoning history limit is smaller than its required samples"
        )
    return PoisoningPolicy(
        settings.poison_window_seconds,
        settings.poison_history_limit,
        settings.poison_similarity_threshold,
        settings.poison_similar_count,
        settings.poison_min_text_length,
        settings.poison_min_baseline,
        settings.poison_min_recent,
        settings.poison_class_delta,
        settings.poison_evaluation_threshold,
        references,
    )
