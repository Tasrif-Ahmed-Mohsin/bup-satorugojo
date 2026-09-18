"""Runtime configuration from the environment.

Credential values are read here and never written to logs, errors, responses or
handoff documents. Only presence is ever reported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path: Path = _ENV_FILE) -> None:
    """Fill missing environment variables from a local ``.env`` file.

    Deployments set real environment variables; this only helps local runs.
    An existing variable always wins, and nothing read here is logged.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")


def _number(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value != value or value in (float("inf"), float("-inf")) or value < minimum:
        return default
    return value


def _count(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


@dataclass(frozen=True)
class Settings:
    """Deadlines are budgets this service enforces, not provider guarantees."""

    api_key: str
    base_url: str
    model: str
    request_deadline_seconds: float
    model_phase_seconds: float
    model_attempt_seconds: float
    connect_timeout_seconds: float
    max_output_tokens: int
    max_attempts: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_settings() -> Settings:
    load_env_file()
    return Settings(
        api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip(),
        # The published per-request limit is 30 seconds; stop before it so a
        # controlled error still has time to be written and sent.
        request_deadline_seconds=_number("GRIDWISE_REQUEST_DEADLINE", 25.0, 1.0),
        model_phase_seconds=_number("GRIDWISE_MODEL_PHASE", 20.0, 1.0),
        model_attempt_seconds=_number("GRIDWISE_MODEL_ATTEMPT", 9.0, 1.0),
        connect_timeout_seconds=_number("GRIDWISE_CONNECT_TIMEOUT", 5.0, 0.5),
        max_output_tokens=_count("GRIDWISE_MAX_OUTPUT_TOKENS", 1024, 256, 8192),
        # One retry, not a hidden sequence of provider-side retries.
        max_attempts=_count("GRIDWISE_MAX_ATTEMPTS", 2, 1, 3),
    )
