"""Small, dependency-free secret redaction helpers."""

from __future__ import annotations

import os
from collections.abc import Iterable


_SECRET_ENV_NAMES = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "WANDB_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


def active_secret_values(extra: Iterable[str] = ()) -> tuple[str, ...]:
    values = [os.environ.get(name, "") for name in _SECRET_ENV_NAMES]
    values.extend(extra)
    # Tiny values cause destructive redaction of ordinary prose.
    return tuple(sorted({value for value in values if len(value) >= 4}, key=len, reverse=True))


def redact_secrets(text: object, *, extra: Iterable[str] = ()) -> str:
    result = str(text)
    for secret in active_secret_values(extra):
        result = result.replace(secret, "[REDACTED]")
    return result
