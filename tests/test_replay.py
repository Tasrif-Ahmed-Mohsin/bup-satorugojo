"""Replay acceptance checks using public references and independent counterexamples."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from math import fsum
from pathlib import Path

import pytest

from app.replay import replay_response
from app.schemas import HourPlan, ScenarioRequest


@pytest.fixture(scope="module")
def public_cases():
    sample = (
        Path(__file__).resolve().parents[1]
        / "BUP_CSE_FEST_2026_Participant_Docs"
        / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
    )
    return json.loads(sample.read_text(encoding="utf-8"))["cases"]


def _directive(kind="no_op", adjustment=None, index=0):
    return {
        "note_index": index,
        "applies": kind != "no_op",
        "directive_type": kind,
        "structured_adjustment": adjustment,
        "explanation": "Synthetic test interpretation.",
    }


def _flat():
    request = {
        "scenario_id": "synthetic-replay",
        "operator_notes": ["An unrelated announcement."],
        "hours": [
            {"hour": h, "demand_kwh": 10, "solar_kwh": 0, "tariff_bdt_per_kwh": 1}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 20,
            "initial_energy_kwh": 10,
            "minimum_energy_kwh": 0,
            "max_charge_kwh_per_hour": 10,
            "max_discharge_kwh_per_hour": 10,
        },
    }
    response = {
        "scenario_id": "synthetic-replay",
        "directive_interpretation": [_directive()],
        "hourly_plan": [
            {
                "hour": h,
                "grid_kwh": 10,
                "solar_used_kwh": 0,
                "battery_action": "idle",
                "battery_kwh": 0,
                "battery_energy_after_kwh": 10,
            }
            for h in range(24)
        ],
        "total_grid_kwh": 240,
        "total_cost_bdt": 240,
        "peak_grid_kwh": 10,
        "plan_summary": "Supply constant demand while the battery remains idle.",
    }
    return request, response


def _metrics(request, response):
    rates = {item["hour"]: item["tariff_bdt_per_kwh"] for item in request["hours"]}
    response["total_grid_kwh"] = fsum(row["grid_kwh"] for row in response["hourly_plan"])
    response["total_cost_bdt"] = fsum(
        row["grid_kwh"] * rates[row["hour"]] for row in response["hourly_plan"]
    )
    response["peak_grid_kwh"] = max(row["grid_kwh"] for row in response["hourly_plan"])


def _replay(request, response, **kwargs):
    return replay_response(ScenarioRequest.model_validate(request), response, **kwargs)


@pytest.mark.parametrize("case_index", range(10))
def test_public_references_after_complete_json_round_trip(public_cases, case_index):
    case = public_cases[case_index]
    payload = json.loads(json.dumps(case["expected_output"], allow_nan=False))
    report = _replay(
        case["input"],
        payload,
        trusted_directives=case["expected_output"]["directive_interpretation"],
        tolerance=1e-9,
    )
    assert report.valid, report.errors
    assert report.total_cost_bdt == case["expected_output"]["total_cost_bdt"]
    assert report.total_grid_kwh == case["expected_output"]["total_grid_kwh"]
    assert report.peak_grid_kwh == case["expected_output"]["peak_grid_kwh"]


def test_shuffled_input_uses_hour_identity_and_never_mutates_payload(public_cases):
    case = deepcopy(public_cases[0])
    case["input"]["hours"].reverse()
    before = deepcopy(case)
    assert _replay(case["input"], case["expected_output"]).valid
    assert case == before


@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf"), -0.01])
def test_rejects_non_json_or_invalid_numeric_values(value):
    request, response = _flat()
    response["hourly_plan"][0]["grid_kwh"] = value
    report = _replay(request, response)
    assert not report.valid
    assert report.errors == ("response schema is invalid",)


@pytest.mark.parametrize("field", ["total_grid_kwh", "total_cost_bdt", "peak_grid_kwh"])
def test_recomputed_metrics_detect_forgery(field):
    request, response = _flat()
    response[field] += 0.02
    report = _replay(request, response)
    assert not report.valid
    assert f"{field}: reported value mismatch" in report.errors


def test_energy_balance_is_independent_of_reported_totals():
    request, response = _flat()
    response["hourly_plan"][3]["grid_kwh"] += 2
    _metrics(request, response)
    report = _replay(request, response)
    assert not report.valid
    assert "hour 3: energy balance mismatch" in report.errors


def test_state_is_reconstructed_instead_of_trusting_previous_report():
    request, response = _flat()
    # Adjacent states differ by only 0.005, but idle battery state is constant.
    for h in range(23):
        response["hourly_plan"][h]["battery_energy_after_kwh"] += (h + 1) * 0.005
    report = _replay(request, response)
    assert not report.valid
    assert "hour 3: battery state mismatch" in report.errors


def test_adjacent_emitted_states_are_checked_even_when_each_is_near_true_state():
    request, response = _flat()
    # Each reported state is within 0.01 of the reconstructed state, but adjacent
    # idle states differ by 0.018 and violate the emitted transition equation.
    for h, row in enumerate(response["hourly_plan"]):
        row["battery_energy_after_kwh"] = 10 + (0.009 if h % 2 == 0 else -0.009)
    report = _replay(request, response)
    assert not report.valid
    assert "hour 1: emitted battery transition mismatch" in report.errors
    assert not any("battery state mismatch" in error for error in report.errors)


def test_final_neutrality_even_when_every_transition_and_balance_is_correct():
    request, response = _flat()
    response["hourly_plan"][0].update(battery_action="charge", battery_kwh=1, grid_kwh=11)
    for row in response["hourly_plan"]:
        row["battery_energy_after_kwh"] = 11
    _metrics(request, response)
    report = _replay(request, response)
    assert "reconstructed final battery violates neutrality" in report.errors
    assert "reported final battery violates neutrality" in report.errors
    assert not any("state mismatch" in error for error in report.errors)


@pytest.mark.parametrize(
    "actual,reported,expected",
    [(0.018, 0.009, "reconstructed"), (0.009, 0.018, "reported")],
)
def test_checks_both_reconstructed_and_reported_capacity(actual, reported, expected):
    request, response = _flat()
    request["battery"]["capacity_kwh"] = 10
    response["hourly_plan"][0].update(
        battery_action="charge",
        battery_kwh=actual,
        grid_kwh=10 + actual,
        battery_energy_after_kwh=10 + reported,
    )
    response["hourly_plan"][1].update(
        battery_action="discharge",
        battery_kwh=actual,
        grid_kwh=10 - actual,
    )
    _metrics(request, response)
    report = _replay(request, response)
    assert not report.valid
    assert f"hour 0: {expected} battery above capacity" in report.errors


def test_reserve_applies_after_hour_not_before_hour():
    request, response = _flat()
    request["battery"]["initial_energy_kwh"] = 0
    request["operator_notes"] = ["Keep five kWh after hour zero."]
    response["directive_interpretation"] = [
        _directive("minimum_battery_reserve", {"hours": [0], "minimum_energy_kwh": 5})
    ]
    for row in response["hourly_plan"]:
        row["battery_energy_after_kwh"] = 0
    response["hourly_plan"][0].update(
        battery_action="charge", battery_kwh=5, grid_kwh=15, battery_energy_after_kwh=5
    )
    response["hourly_plan"][1].update(battery_action="discharge", battery_kwh=5, grid_kwh=5)
    _metrics(request, response)
    assert _replay(request, response).valid


def test_forced_solar_curtailment_and_zero_capacity_are_valid():
    request, response = _flat()
    request["battery"] = {key: 0 for key in request["battery"]}
    request["hours"][0]["solar_kwh"] = 20
    response["hourly_plan"][0].update(solar_used_kwh=10, grid_kwh=0)
    for row in response["hourly_plan"]:
        row["battery_energy_after_kwh"] = 0
    _metrics(request, response)
    assert _replay(request, response).valid


def test_solar_reduction_is_applied_to_original_forecast():
    request, response = _flat()
    request["hours"][0]["solar_kwh"] = 10
    response["directive_interpretation"] = [
        _directive("solar_reduction", {"hours": [0], "factor": 0.2})
    ]
    response["hourly_plan"][0].update(solar_used_kwh=3, grid_kwh=7)
    _metrics(request, response)
    report = _replay(request, response)
    assert "hour 0: available solar exceeded" in report.errors


@pytest.mark.parametrize("second_factor,valid", [(0.5, True), (0.2, False)])
def test_overlapping_solar_identical_is_idempotent_different_is_unsupported(second_factor, valid):
    request, response = _flat()
    request["operator_notes"] *= 2
    request["hours"][0]["solar_kwh"] = 10
    response["directive_interpretation"] = [
        _directive("solar_reduction", {"hours": [0], "factor": 0.5}, 0),
        _directive("solar_reduction", {"hours": [0], "factor": second_factor}, 1),
    ]
    response["hourly_plan"][0].update(solar_used_kwh=5, grid_kwh=5)
    _metrics(request, response)
    report = _replay(request, response)
    assert report.valid is valid
    if not valid:
        assert "hour 0: differing overlapping solar factors are unsupported" in report.errors


@pytest.mark.parametrize("kind", ["no_charge_window", "no_discharge_window"])
def test_action_prohibitions_are_enforced(kind):
    request, response = _flat()
    response["directive_interpretation"] = [_directive(kind, {"hours": [0]})]
    sign = 1 if kind == "no_charge_window" else -1
    response["hourly_plan"][0].update(
        battery_action="charge" if sign == 1 else "discharge",
        battery_kwh=1,
        grid_kwh=10 + sign,
        battery_energy_after_kwh=10 + sign,
    )
    response["hourly_plan"][1].update(
        battery_action="discharge" if sign == 1 else "charge",
        battery_kwh=1,
        grid_kwh=10 - sign,
    )
    _metrics(request, response)
    report = _replay(request, response)
    assert not report.valid
    assert any("prohibited" in error for error in report.errors)


def test_both_prohibitions_allow_idle():
    request, response = _flat()
    request["operator_notes"] *= 2
    response["directive_interpretation"] = [
        _directive("no_charge_window", {"hours": [0]}, 0),
        _directive("no_discharge_window", {"hours": [0]}, 1),
    ]
    assert _replay(request, response).valid


def test_overlapping_grid_caps_use_stricter_limit():
    request, response = _flat()
    request["operator_notes"] *= 2
    response["directive_interpretation"] = [
        _directive("max_grid_window", {"hours": [0], "max_grid_kwh": 9}, 0),
        _directive("max_grid_window", {"hours": [0], "max_grid_kwh": 15}, 1),
    ]
    report = _replay(request, response)
    assert "hour 0: grid cap exceeded" in report.errors


def test_overlapping_reserves_use_stricter_limit():
    request, response = _flat()
    request["operator_notes"] *= 2
    response["directive_interpretation"] = [
        _directive("minimum_battery_reserve", {"hours": [0], "minimum_energy_kwh": 11}, 0),
        _directive("minimum_battery_reserve", {"hours": [0], "minimum_energy_kwh": 5}, 1),
    ]
    report = _replay(request, response)
    assert "hour 0: reconstructed battery below reserve" in report.errors


def test_rate_limit_checked_independently_of_state_and_balance():
    request, response = _flat()
    request["battery"]["max_charge_kwh_per_hour"] = 0.5
    response["hourly_plan"][0].update(
        battery_action="charge", battery_kwh=1, grid_kwh=11, battery_energy_after_kwh=11
    )
    response["hourly_plan"][1].update(battery_action="discharge", battery_kwh=1, grid_kwh=9)
    _metrics(request, response)
    report = _replay(request, response)
    assert report.errors == ("hour 0: charge rate exceeded",)


def test_trusted_directives_catch_semantic_mismatch_without_comparing_explanations():
    request, response = _flat()
    trusted = [_directive("max_grid_window", {"hours": [0], "max_grid_kwh": 20})]
    # Both interpretations permit this plan; only trusted semantics show the lie.
    assert _replay(request, response).valid
    report = _replay(request, response, trusted_directives=trusted)
    assert "reported directive meaning differs from trusted directives" in report.errors
    response["directive_interpretation"] = deepcopy(trusted)
    response["directive_interpretation"][0]["explanation"] = "Different wording is fine."
    assert _replay(request, response, trusted_directives=trusted).valid


def test_trusted_solar_factor_does_not_use_kwh_tolerance():
    request, response = _flat()
    response["directive_interpretation"] = [
        _directive("solar_reduction", {"hours": [0], "factor": 0.2})
    ]
    trusted = [_directive("solar_reduction", {"hours": [0], "factor": 0.205})]
    report = _replay(request, response, trusted_directives=trusted)
    assert not report.valid


def test_trusted_mode_also_enforces_reported_cap_without_stacking_tolerances():
    request, response = _flat()
    request["hours"][0]["solar_kwh"] = 1
    response["directive_interpretation"] = [
        _directive("max_grid_window", {"hours": [0], "max_grid_kwh": 8.991})
    ]
    trusted = [_directive("max_grid_window", {"hours": [0], "max_grid_kwh": 9})]
    response["hourly_plan"][0].update(grid_kwh=9.009, solar_used_kwh=0.991)
    _metrics(request, response)
    report = _replay(request, response, trusted_directives=trusted)
    assert not report.valid
    assert "reported schedule: hour 0: grid cap exceeded" in report.errors
    assert not any("meaning differs" in error for error in report.errors)


def test_absolute_tolerance_does_not_grow_with_magnitude():
    request, response = _flat()
    for source, row in zip(request["hours"], response["hourly_plan"]):
        source["demand_kwh"] = row["grid_kwh"] = 1e12
    _metrics(request, response)
    response["total_grid_kwh"] += 1
    report = _replay(request, response)
    assert "total_grid_kwh: reported value mismatch" in report.errors


def test_finite_inputs_with_overflowing_cost_produce_safe_error():
    request, response = _flat()
    request["hours"][0].update(demand_kwh=1e200, tariff_bdt_per_kwh=1e200)
    response["hourly_plan"][0]["grid_kwh"] = 1e200
    response.update(total_grid_kwh=1e200, peak_grid_kwh=1e200, total_cost_bdt=1e200)
    report = _replay(request, response)
    assert not report.valid
    assert report.total_cost_bdt is None
    assert "total_cost_bdt: recomputed value is nonfinite" in report.errors


@pytest.mark.parametrize("tolerance", [True, "0.01", -1, float("nan"), float("inf")])
def test_invalid_tolerance_returns_controlled_failure(tolerance):
    request, response = _flat()
    assert _replay(request, response, tolerance=tolerance).errors == (
        "replay tolerance is invalid",
    )


def test_errors_do_not_echo_untrusted_values_and_report_is_immutable():
    request, response = _flat()
    response["scenario_id"] = "untrusted-sensitive-marker"
    report = _replay(request, response)
    assert report.errors == ("scenario_id mismatch",)
    assert "untrusted-sensitive-marker" not in repr(report)
    with pytest.raises(FrozenInstanceError):
        report.valid = True


def test_mutated_nested_models_cannot_bypass_numeric_validation():
    request, response = _flat()
    row = HourPlan.model_validate(response["hourly_plan"][0])
    row.grid_kwh = "untrusted-sensitive-marker"
    response["hourly_plan"][0] = row
    report = _replay(request, response)
    assert report.errors == ("response schema is invalid",)
    assert "untrusted-sensitive-marker" not in repr(report)


def test_missing_note_and_reserve_above_capacity_are_rejected():
    request, response = _flat()
    request["operator_notes"] *= 2
    report = _replay(request, response)
    assert "reported directives: note coverage or order mismatch" in report.errors
    request["operator_notes"].pop()
    response["directive_interpretation"] = [
        _directive("minimum_battery_reserve", {"hours": [0], "minimum_energy_kwh": 21})
    ]
    report = _replay(request, response)
    assert "reported directives: reserve exceeds battery capacity" in report.errors


@pytest.mark.parametrize("mutation", ["idle", "duplicate_hour", "unknown_action", "duplicate_note"])
def test_malformed_complete_response_is_rejected(mutation):
    request, response = _flat()
    if mutation == "idle":
        response["hourly_plan"][0]["battery_kwh"] = 1
    elif mutation == "duplicate_hour":
        response["hourly_plan"][1]["hour"] = 0
    elif mutation == "unknown_action":
        response["hourly_plan"][0]["battery_action"] = "export"
    else:
        response["directive_interpretation"] *= 2
    assert _replay(request, response).errors == ("response schema is invalid",)
