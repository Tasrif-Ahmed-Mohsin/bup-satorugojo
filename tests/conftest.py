import copy
import json
from pathlib import Path

import pytest

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "BUP_CSE_FEST_2026_Participant_Docs"
    / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)


@pytest.fixture(scope="session")
def public_cases():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.fixture
def first_case(public_cases):
    return copy.deepcopy(public_cases[0])


@pytest.fixture
def anyio_backend():
    """Run async provider-boundary tests on asyncio only."""
    return "asyncio"
