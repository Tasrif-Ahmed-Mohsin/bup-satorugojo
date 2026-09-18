"""Solve the public cases with the LP and compare cost against the references.

The organizer's structured directives are supplied as trusted test input so
this checks the optimizer alone, with no language model in the path. It is a
local verification tool: it is never imported by the application, and no public
phrase, scenario identifier or reference schedule reaches the served pipeline.
"""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.directives import DirectiveValidationError, validate_directives
from app.jsonio import JsonPayloadError, load_json
from app.optimizer import OptimizerError, optimize_scenario
from app.replay import replay_response
from app.schemas import ScenarioRequest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES = (
    ROOT / "BUP_CSE_FEST_2026_Participant_Docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)
TOLERANCE = 0.01


def solve_reference_pack(path: Path, tolerance: float = TOLERANCE) -> dict:
    source = path.read_bytes()
    pack = load_json(source)
    results = []
    for case in pack["cases"]:
        row = {"case_id": case["id"], "solved": False, "errors": []}
        try:
            scenario = ScenarioRequest.model_validate(case["input"])
            reference = case["expected_output"]
            directives = validate_directives(
                scenario, {"directive_interpretation": reference["directive_interpretation"]}
            )
            started = perf_counter()
            response = optimize_scenario(scenario, directives, tolerance=tolerance)
            row["seconds"] = perf_counter() - started
            # Replay again against the independently annotated reference meaning.
            replay = replay_response(
                scenario,
                response,
                tolerance=tolerance,
                trusted_directives=reference["directive_interpretation"],
            )
            reference_cost = reference["total_cost_bdt"]
            row.update(
                {
                    "solved": True,
                    "valid": replay.valid,
                    "cost_bdt": response["total_cost_bdt"],
                    "reference_cost_bdt": reference_cost,
                    "cost_difference_bdt": response["total_cost_bdt"] - reference_cost,
                    "total_grid_kwh": response["total_grid_kwh"],
                    "peak_grid_kwh": response["peak_grid_kwh"],
                    "errors": list(replay.errors),
                }
            )
            if abs(row["cost_difference_bdt"]) > tolerance:
                row["errors"].append("cost differs from the reference beyond tolerance")
        except OptimizerError as error:
            row["errors"].append(f"optimizer: {error.code}")
        except DirectiveValidationError as error:
            row["errors"].append(f"directives: {error.code}")
        except (ValidationError, JsonPayloadError, KeyError):
            row["errors"].append("invalid_reference")
        row["passed"] = bool(row["solved"] and row.get("valid") and not row["errors"])
        results.append(row)
    return {
        "check": "public_case_lp_cost_comparison",
        "limitation": (
            "Uses the organizer's structured directives as trusted input. "
            "It checks the optimizer, not language interpretation or a live API."
        ),
        "tolerance_bdt": tolerance,
        "sample_sha256": hashlib.sha256(source).hexdigest(),
        "passed": sum(row["passed"] for row in results),
        "total": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument("--report", type=Path, help="Optional local JSON report destination")
    args = parser.parse_args()
    report = solve_reference_pack(args.samples, args.tolerance)
    print("Public case LP solve and cost comparison (no model calls)")
    for row in report["results"]:
        state = "PASS" if row["passed"] else "FAIL"
        if row["solved"]:
            print(
                f"{state} {row['case_id']}: cost={row['cost_bdt']} "
                f"reference={row['reference_cost_bdt']} "
                f"difference={row['cost_difference_bdt']} "
                f"solved in {row['seconds'] * 1000:.1f} ms"
            )
        else:
            print(f"{state} {row['case_id']}: not solved")
        for error in row["errors"]:
            print(f"  {error}")
    print(
        f"{report['passed']}/{report['total']} public cases solved, replayed "
        f"and matched within {report['tolerance_bdt']} BDT."
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
