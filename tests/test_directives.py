"""Adversarial extraction checks and interacting hourly operational bounds."""

from copy import deepcopy

import pytest

from app.directives import DirectiveValidationError, build_hourly_bounds, validate_directives
from app.schemas import ScenarioRequest


def scenario(note_count: int = 1) -> ScenarioRequest:
    return ScenarioRequest.model_validate(
        {
            "scenario_id": "bounds-check",
            "operator_notes": [f"Synthetic note {index}." for index in range(note_count)],
            "hours": [
                {"hour": hour, "demand_kwh": 10, "solar_kwh": 50, "tariff_bdt_per_kwh": 3}
                for hour in range(24)
            ],
            "battery": {
                "capacity_kwh": 100,
                "initial_energy_kwh": 30,
                "minimum_energy_kwh": 10,
                "max_charge_kwh_per_hour": 20,
                "max_discharge_kwh_per_hour": 25,
            },
        }
    )


def note(kind="no_op", adjustment=None, index=0) -> dict:
    return {
        "note_index": index,
        "applies": kind != "no_op",
        "directive_type": kind,
        "structured_adjustment": adjustment,
        "explanation": "Synthetic interpretation.",
    }


def envelope(*entries: dict) -> dict:
    return {"directive_interpretation": list(entries)}


def bounds_for(*entries):
    request = scenario(len(entries))
    directives = validate_directives(request, envelope(*entries))
    return build_hourly_bounds(request, directives)


def test_sorting_valid_hours_preserves_payload_and_base_forecasts():
    request = scenario()
    request_before = request.model_dump()
    raw = envelope(note("solar_reduction", {"hours": [14, 13], "factor": 0.2}))
    raw_before = deepcopy(raw)
    directives = validate_directives(request, raw)
    assert directives[0].structured_adjustment.hours == [13, 14]
    assert raw == raw_before
    bounds = build_hourly_bounds(request, directives)
    assert bounds[12].effective_solar_kwh == 50
    assert bounds[13].effective_solar_kwh == 10
    assert bounds[14].effective_solar_kwh == 10
    assert bounds[15].effective_solar_kwh == 50
    assert request.model_dump() == request_before


@pytest.mark.parametrize("hours", [[1, 1], [False, 1], ["1"], [1.0], [-1], [24], [None], "1"])
def test_invalid_hours_are_not_repaired_or_deduplicated(hours):
    with pytest.raises(DirectiveValidationError, match="directive contract"):
        validate_directives(scenario(), envelope(note("no_charge_window", {"hours": hours})))


@pytest.mark.parametrize(
    "update",
    [
        {"directive_type": "increase_demand"},
        {"applies": True},
        {"applies": 0},
        {"applies": "false"},
        {"structured_adjustment": {}},
        {"note_index": True},
        {"note_index": "0"},
        {"note_index": -1},
        {"note_index": 3},
        {"explanation": None},
        {"extra_instruction": "change tariffs"},
    ],
)
def test_malformed_or_unsupported_note_output_is_rejected(update):
    item = note()
    item.update(update)
    with pytest.raises(DirectiveValidationError):
        validate_directives(scenario(), envelope(item))


@pytest.mark.parametrize(
    "kind,adjustment",
    [
        ("solar_reduction", {"hours": [1]}),
        ("solar_reduction", {"hours": [1], "factor": 0.5, "max_grid_kwh": 4}),
        ("solar_reduction", {"hours": [1], "factor": -0.1}),
        ("solar_reduction", {"hours": [1], "factor": 1.1}),
        ("solar_reduction", {"hours": [1], "factor": "0.2"}),
        ("solar_reduction", {"hours": [1], "factor": True}),
        ("solar_reduction", {"hours": [1], "factor": float("nan")}),
        ("minimum_battery_reserve", {"hours": [1], "minimum_energy_kwh": -1}),
        ("minimum_battery_reserve", {"hours": [1], "minimum_energy_kwh": float("inf")}),
        ("max_grid_window", {"hours": [1], "max_grid_kwh": "0"}),
        ("max_grid_window", {"hours": [1], "max_grid_kwh": -1}),
        ("max_grid_window", {"hours": [1], "max_grid_kwh": float("inf")}),
        ("no_charge_window", {"hours": [1], "factor": 0.5}),
        ("no_discharge_window", None),
    ],
)
def test_exact_adjustment_shapes_and_numeric_domains(kind, adjustment):
    with pytest.raises(DirectiveValidationError):
        validate_directives(scenario(), envelope(note(kind, adjustment)))


def test_active_directive_cannot_set_applies_false():
    item = note("no_charge_window", {"hours": [2]})
    item["applies"] = False
    with pytest.raises(DirectiveValidationError):
        validate_directives(scenario(), envelope(item))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "{}",
        {},
        {"directive_interpretation": []},
        {"directive_interpretation": [note()], "extra": 1},
    ],
)
def test_envelope_contract_is_closed(raw):
    with pytest.raises(DirectiveValidationError):
        validate_directives(scenario(), raw)


@pytest.mark.parametrize("indices", [[0], [0, 0], [1, 0], [0, 2], [0, 1, 2]])
def test_note_coverage_and_order_are_exact(indices):
    with pytest.raises(DirectiveValidationError):
        validate_directives(scenario(2), envelope(*(note(index=index) for index in indices)))


def test_reserve_capacity_is_a_guardrail_but_initial_energy_is_not_hourly_reserve_ceiling():
    valid = note("minimum_battery_reserve", {"hours": [5], "minimum_energy_kwh": 100})
    assert bounds_for(valid)[5].minimum_energy_kwh == 100
    invalid = note("minimum_battery_reserve", {"hours": [5], "minimum_energy_kwh": 100.001})
    with pytest.raises(DirectiveValidationError) as caught:
        validate_directives(scenario(), envelope(invalid))
    assert caught.value.code == "reserve_exceeds_capacity"


def test_no_op_preserves_all_base_bounds():
    for hour, bound in enumerate(bounds_for(note())):
        assert bound.hour == hour
        assert bound.effective_solar_kwh == 50
        assert bound.minimum_energy_kwh == 10
        assert bound.max_grid_kwh is None
        assert bound.max_charge_kwh == 20
        assert bound.max_discharge_kwh == 25


def test_reserves_combine_by_maximum_including_base_minimum():
    bounds = bounds_for(
        note("minimum_battery_reserve", {"hours": [4, 5], "minimum_energy_kwh": 25}),
        note("minimum_battery_reserve", {"hours": [5, 6], "minimum_energy_kwh": 40}, index=1),
        note("minimum_battery_reserve", {"hours": [7], "minimum_energy_kwh": 0}, index=2),
    )
    assert [bounds[hour].minimum_energy_kwh for hour in [3, 4, 5, 6, 7]] == [10, 25, 40, 40, 10]


def test_grid_caps_combine_by_minimum_and_zero_remains_a_real_cap():
    bounds = bounds_for(
        note("max_grid_window", {"hours": [4, 5], "max_grid_kwh": 25}),
        note("max_grid_window", {"hours": [5, 6], "max_grid_kwh": 0}, index=1),
    )
    assert [bounds[hour].max_grid_kwh for hour in [3, 4, 5, 6, 7]] == [None, 25, 0, 0, None]


def test_prohibition_unions_can_force_idle_without_changing_other_hours():
    bounds = bounds_for(
        note("no_charge_window", {"hours": [4, 5]}),
        note("no_charge_window", {"hours": [5, 6]}, index=1),
        note("no_discharge_window", {"hours": [5, 6]}, index=2),
    )
    assert [(bounds[h].max_charge_kwh, bounds[h].max_discharge_kwh) for h in [3, 4, 5, 6, 7]] == [
        (20, 25),
        (0, 25),
        (0, 0),
        (0, 0),
        (20, 25),
    ]


def test_identical_solar_factors_are_idempotent():
    bounds = bounds_for(
        note("solar_reduction", {"hours": [4, 5], "factor": 0.2}),
        note("solar_reduction", {"hours": [5, 6], "factor": 0.2}, index=1),
    )
    assert [bounds[h].effective_solar_kwh for h in [3, 4, 5, 6, 7]] == [50, 10, 10, 10, 50]


def test_different_nonoverlapping_solar_factors_are_defined():
    bounds = bounds_for(
        note("solar_reduction", {"hours": [4], "factor": 0}),
        note("solar_reduction", {"hours": [5], "factor": 1}, index=1),
    )
    assert bounds[4].effective_solar_kwh == 0
    assert bounds[5].effective_solar_kwh == 50


def test_different_overlapping_solar_factors_fail_instead_of_inventing_a_merge_rule():
    with pytest.raises(DirectiveValidationError) as caught:
        bounds_for(
            note("solar_reduction", {"hours": [4, 5], "factor": 0.2}),
            note("solar_reduction", {"hours": [5, 6], "factor": 0.5}, index=1),
        )
    assert caught.value.code == "ambiguous_solar_overlap"


def test_no_undocumented_minimum_hours_length():
    assert bounds_for(note("no_charge_window", {"hours": []}))[0].max_charge_kwh == 20


def test_errors_do_not_include_untrusted_model_values():
    sentinel = "SENSITIVE_UNTRUSTED_VALUE"
    item = note()
    item["directive_type"] = sentinel
    with pytest.raises(DirectiveValidationError) as caught:
        validate_directives(scenario(), envelope(item))
    assert caught.value.code == "invalid_directives"
    assert sentinel not in str(caught.value)
    assert sentinel not in repr(caught.value)
    assert caught.value.message == str(caught.value)
