"""JSON serialization helpers."""

import math


def json_safe(value):
    """Recursively replace non-finite floats (NaN, inf, -inf) with None.

    JSON does not support NaN/Infinity; ``JSON.parse`` on the frontend
    rejects them.  This helper walks dicts / lists / tuples and normalizes
    every non-finite float to ``None`` before ``json.dumps``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value
