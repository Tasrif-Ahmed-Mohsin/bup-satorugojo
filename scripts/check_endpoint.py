"""Run the organizer's public sample cases against a running GridWise API.

This is the public-sample test procedure. It posts each sample input to
``/optimize-energy`` exactly as a judge would, then checks the returned plan
with the independent replay checker against the organizer's annotated
directives and compares the recalculated cost with the published one.

Expected result against a correctly configured service::

    10/10 public cases: HTTP 200, valid against the organizer's directives,
    cost equal to the published cost.

The reference answers are used only here, on the checking side. The service
never sees them.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.replay import replay_response
from app.schemas import ScenarioRequest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES = (
    ROOT / "BUP_CSE_FEST_2026_Participant_Docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)
TOLERANCE = 0.01


def _get(url: str, timeout: float) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None


def _post(url: str, body: dict, timeout: float) -> tuple[int, object]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        except ValueError:
            return error.code, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        status, body = _get(f"{base}/health", args.timeout)
    except (urllib.error.URLError, OSError):
        print(f"FAIL {base}/health is unreachable")
        return 1
    print(f"GET /health -> {status} {json.dumps(body)}")

    cases = json.loads(args.samples.read_text(encoding="utf-8"))["cases"]
    passed = 0
    for case in cases:
        started = time.perf_counter()
        try:
            status, body = _post(f"{base}/optimize-energy", case["input"], args.timeout)
        except (urllib.error.URLError, OSError):
            print(f"FAIL {case['id']}: request did not complete")
            continue
        seconds = time.perf_counter() - started
        if status != 200 or not isinstance(body, dict):
            code = body.get("error", {}).get("code") if isinstance(body, dict) else None
            print(f"FAIL {case['id']}: HTTP {status} {code}")
            continue
        scenario = ScenarioRequest.model_validate(case["input"])
        reference = case["expected_output"]
        report = replay_response(
            scenario,
            body,
            tolerance=TOLERANCE,
            trusted_directives=reference["directive_interpretation"],
        )
        difference = body["total_cost_bdt"] - reference["total_cost_bdt"]
        ok = report.valid and abs(difference) <= TOLERANCE
        passed += ok
        print(
            f"{'PASS' if ok else 'FAIL'} {case['id']}: cost={body['total_cost_bdt']} "
            f"published={reference['total_cost_bdt']} in {seconds:.2f}s"
        )
        for error in report.errors:
            print(f"  {error}")
    print(
        f"{passed}/{len(cases)} public cases: HTTP 200, valid against the organizer's "
        "directives, cost equal to the published cost."
    )
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
