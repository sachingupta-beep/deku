"""Response-shape helpers shared by every task's substeps.

instruction.md pins list endpoints to a JSON array, but tolerating the common
`{"items": [...]}` envelope costs one function and removes a class of false
negatives that has nothing to do with the capability being measured.
"""

from __future__ import annotations

import json
from typing import Any

LIST_KEYS = ("items", "data", "results", "records")


def items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(v, dict) for v in value):
                return value
    raise AssertionError(
        f"expected a list response, got {type(payload).__name__}: {str(payload)[:300]}"
    )


def flatten(payload: Any) -> str:
    """Lowercased flat text of a JSON payload, for substring assertions."""
    return json.dumps(payload, default=str).lower()
