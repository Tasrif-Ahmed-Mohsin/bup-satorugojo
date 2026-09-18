"""Replay the organizer's reference outputs. This does not solve the scenarios."""

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.directives import DirectiveValidationError, build_hourly_bounds, validate_directives
from app.jsonio import JsonPayloadError, dump_json, load_json
from app.replay import replay_response
from app.schemas import ScenarioRequest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES = (
    ROOT / "BUP_CSE_FEST_2026_Participant_Docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)


def check_reference_pack(path: Path) -> dict:
    source = path.read_bytes()
    pack = load_json(source)
    results = []
    for case in pack["cases"]:
        try:
            scenario = ScenarioRequest.model_validate(case["input"])
            payload = load_json(dump_json(case["expected_output"]))
            directives = validate_directives(
                scenario, {"directive_interpretation": payload["directive_interpretation"]}
            )
            build_hourly_bounds(scenario, directives)
            replay = replay_response(scenario, payload)
            results.append(
                {
                    "case_id": case["id"],
                    "valid": replay.valid,
                    "notes": len(scenario.operator_notes),
                    "hours": len(payload["hourly_plan"]),
                    "recalculated_cost_bdt": replay.total_cost_bdt,
                    "errors": list(replay.errors),
                }
            )
        except (ValidationError, DirectiveValidationError, JsonPayloadError, KeyError):
            results.append({"case_id": case["id"], "valid": False, "errors": ["invalid_reference"]})
    return {
        "check": "offline_reference_replay",
        "limitation": "Verifies reference validity; does not establish optimizer or LLM correctness.",
        "sample_sha256": hashlib.sha256(source).hexdigest(),
        "passed": sum(row["valid"] for row in results),
        "total": len(results),
        "note_count": sum(row.get("notes", 0) for row in results),
        "hour_count": sum(row.get("hours", 0) for row in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--report", type=Path, help="Optional local JSON report destination")
    args = parser.parse_args()
    report = check_reference_pack(args.samples)
    print("Offline reference replay (no solver or model calls)")
    for row in report["results"]:
        state = "PASS" if row["valid"] else "FAIL"
        print(f"{state} {row['case_id']}: cost={row.get('recalculated_cost_bdt')}")
        for error in row["errors"]:
            print(f"  {error}")
    print(
        f"{report['passed']}/{report['total']} references passed; "
        f"{report['note_count']} notes; {report['hour_count']} hours."
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
