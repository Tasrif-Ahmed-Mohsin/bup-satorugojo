"""Strict JSON boundaries shared by local tooling and the future provider adapter."""

import json
from typing import Any


class JsonPayloadError(ValueError):
    """A JSON document cannot safely be interpreted; never include its contents."""


def _reject_constant(_: str) -> None:
    raise JsonPayloadError("Nonfinite JSON numbers are not allowed.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise JsonPayloadError("Duplicate JSON object fields are not allowed.")
        result[name] = value
    return result


def load_json(payload: str | bytes) -> Any:
    """Reject ambiguous duplicate fields and nonstandard NaN/Infinity literals."""
    try:
        return json.loads(
            payload, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise JsonPayloadError("Invalid JSON document.") from exc


def dump_json(payload: Any) -> str:
    """Preserve float precision; never serialize nonfinite values as JSON."""
    try:
        return json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise JsonPayloadError("Payload cannot be represented as finite JSON.") from exc
