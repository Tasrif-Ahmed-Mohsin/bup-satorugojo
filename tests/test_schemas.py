"""Contract tests exercise coercion hazards and ordering without any model calls."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas import Directive, OptimizationResponse, ScenarioRequest


def request_payload() -> dict:
    return {
        "scenario_id": "schema-check",
        "operator_notes": ["The menu changes tomorrow."],
        "hours": [
            {"hour": hour, "demand_kwh": 10, "solar_kwh": 2, "tariff_bdt_per_kwh": 3}
            for hour in range(24)
        ],
        "battery": {
            "capacity_kwh": 100,
            "initial_energy_kwh": 30,
            "minimum_energy_kwh": 10,
            "max_charge_kwh_per_hour": 20,
            "max_discharge_kwh_per_hour": 20,
        },
    }


def response_payload() -> dict:
    return {
        "scenario_id": "schema-check",
        "directive_interpretation": [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "No effect today.",
            }
        ],
        "hourly_plan": [
            {
                "hour": hour,
                "grid_kwh": 8,
                "solar_used_kwh": 2,
                "battery_action": "idle",
                "battery_kwh": 0,
                "battery_energy_after_kwh": 30,
            }
            for hour in range(24)
        ],
        "total_grid_kwh": 192,
        "total_cost_bdt": 576,
        "peak_grid_kwh": 8,
        "plan_summary": "Solar supplies part of demand; the battery remains idle.",
    }


def test_input_hour_identity_is_sorted_without_reordering_caller_data():
    payload = request_payload()
    payload["hours"].reverse()
    original = deepcopy(payload)
    scenario = ScenarioRequest.model_validate(payload)
    assert [hour.hour for hour in scenario.hours] == list(range(24))
    assert payload == original
    assert scenario.hours[0].demand_kwh == 10.0


def test_ignores_harmless_input_metadata_at_all_request_levels():
    payload = request_payload()
    payload["metadata"] = {"source": "synthetic"}
    payload["hours"][0]["weather_label"] = "sunny"
    payload["battery"]["label"] = "campus"
    result = ScenarioRequest.model_validate(payload).model_dump()
    assert "metadata" not in result
    assert "weather_label" not in result["hours"][0]
    assert "label" not in result["battery"]


@pytest.mark.parametrize("bad", [True, False, "10", None, float("nan"), float("inf"), -1, 10**400])
@pytest.mark.parametrize("field", ["demand_kwh", "solar_kwh", "tariff_bdt_per_kwh"])
def test_rejects_non_json_or_out_of_domain_hour_numbers(field, bad):
    payload = request_payload()
    payload["hours"][0][field] = bad
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(payload)


@pytest.mark.parametrize("bad", [True, 0.5, "0", -1, 24])
def test_hour_identifiers_are_strict_integers(bad):
    payload = request_payload()
    payload["hours"][0]["hour"] = bad
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(payload)


@pytest.mark.parametrize("mode", ["duplicate", "missing", "extra"])
def test_requires_one_input_entry_per_hour(mode):
    payload = request_payload()
    if mode == "duplicate":
        payload["hours"][23]["hour"] = 22
    elif mode == "missing":
        payload["hours"].pop()
    else:
        payload["hours"].append(deepcopy(payload["hours"][0]))
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(payload)


@pytest.mark.parametrize("notes", [[], [""], [" \n\t"], [1], [True], ["note"] * 4, "note"])
def test_requires_one_to_three_nonempty_note_strings(notes):
    payload = request_payload()
    payload["operator_notes"] = notes
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(payload)


@pytest.mark.parametrize(
    "update",
    [
        {"initial_energy_kwh": 9},
        {"initial_energy_kwh": 101},
        {"minimum_energy_kwh": 31},
        {"capacity_kwh": -1},
        {"max_charge_kwh_per_hour": True},
        {"max_discharge_kwh_per_hour": "20"},
        {"capacity_kwh": float("inf")},
    ],
)
def test_battery_domains_and_cross_field_bounds(update):
    payload = request_payload()
    payload["battery"].update(update)
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(payload)


def test_zero_capacity_and_rates_are_permitted():
    payload = request_payload()
    payload["battery"] = {key: 0 for key in payload["battery"]}
    assert ScenarioRequest.model_validate(payload).battery.capacity_kwh == 0


def test_response_survives_json_roundtrip():
    response = OptimizationResponse.model_validate(response_payload())
    restored = OptimizationResponse.model_validate_json(response.model_dump_json())
    assert restored == response


@pytest.mark.parametrize("position", ["top", "hour", "directive"])
def test_outgoing_contract_forbids_extra_fields(position):
    payload = response_payload()
    target = (
        payload
        if position == "top"
        else payload["hourly_plan" if position == "hour" else "directive_interpretation"][0]
    )
    target["unpublished"] = 123
    with pytest.raises(ValidationError):
        OptimizationResponse.model_validate(payload)


@pytest.mark.parametrize("mode", ["reversed", "duplicate", "missing"])
def test_outgoing_plan_order_is_not_silently_repaired(mode):
    payload = response_payload()
    if mode == "reversed":
        payload["hourly_plan"].reverse()
    elif mode == "duplicate":
        payload["hourly_plan"][23]["hour"] = 22
    else:
        payload["hourly_plan"].pop()
    with pytest.raises(ValidationError):
        OptimizationResponse.model_validate(payload)


@pytest.mark.parametrize(
    "update",
    [
        {"battery_kwh": 0.001},
        {"battery_action": "charging"},
        {"grid_kwh": -0.001},
        {"solar_used_kwh": "2"},
        {"battery_energy_after_kwh": float("nan")},
    ],
)
def test_outgoing_actions_and_numbers_are_strict(update):
    payload = response_payload()
    payload["hourly_plan"][0].update(update)
    with pytest.raises(ValidationError):
        OptimizationResponse.model_validate(payload)


def test_directive_model_requires_canonical_hours_for_output():
    with pytest.raises(ValidationError):
        Directive.model_validate(
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [15, 14]},
                "explanation": "Charging unavailable.",
            }
        )
