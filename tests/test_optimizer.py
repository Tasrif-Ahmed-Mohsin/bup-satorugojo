"""Analytical boundary checks and public reference cost comparisons for the LP.

Reference directives are used only as trusted test inputs. No public phrase,
scenario identifier, or reference schedule is consulted by application code.
"""

import json
import random
from math import fsum
from pathlib import Path

import pytest

from app.directives import DirectiveValidationError, build_hourly_bounds, validate_directives
from app.jsonio import dump_json, load_json
from app.optimizer import OptimizerError, optimize_scenario, solve_schedule
from app.replay import replay_response
from app.schemas import OptimizationResponse, ScenarioRequest

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "BUP_CSE_FEST_2026_Participant_Docs"
    / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)
PUBLIC_CASES = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["cases"]
PUBLISHED_TOLERANCE = 0.01
# Analytical expectations are exact, so allow only representation-level noise.
EXACT = 1e-9


def _series(value):
    if isinstance(value, (int, float)):
        return [float(value)] * 24
    assert len(value) == 24
    return [float(item) for item in value]


def _battery(capacity, initial, minimum=0, charge=0, discharge=0):
    return {
        "capacity_kwh": capacity,
        "initial_energy_kwh": initial,
        "minimum_energy_kwh": minimum,
        "max_charge_kwh_per_hour": charge,
        "max_discharge_kwh_per_hour": discharge,
    }


def _scenario(demand, *, solar=0, tariff=1, battery=None, notes=None, shuffle_seed=None):
    demands, solars, tariffs = _series(demand), _series(solar), _series(tariff)
    hours = [
        {
            "hour": hour,
            "demand_kwh": demands[hour],
            "solar_kwh": solars[hour],
            "tariff_bdt_per_kwh": tariffs[hour],
        }
        for hour in range(24)
    ]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(hours)
    return ScenarioRequest.model_validate(
        {
            "scenario_id": "analytic-case",
            "operator_notes": list(notes or ["An unrelated campus announcement."]),
            "hours": hours,
            "battery": battery or _battery(0, 0),
        }
    )


def _directive(kind="no_op", adjustment=None, index=0):
    return {
        "note_index": index,
        "applies": kind != "no_op",
        "directive_type": kind,
        "structured_adjustment": adjustment,
        "explanation": "Synthetic test interpretation.",
    }


def _optimize(scenario, raw_directives=None):
    raw = raw_directives or [_directive()]
    directives = validate_directives(scenario, {"directive_interpretation": raw})
    return optimize_scenario(scenario, directives)


def _column(response, field):
    return [row[field] for row in response["hourly_plan"]]


def _signed_battery(response):
    return [
        row["battery_kwh"] if row["battery_action"] == "charge" else -row["battery_kwh"]
        for row in response["hourly_plan"]
    ]


# --- Public reference comparison -------------------------------------------------


@pytest.mark.parametrize("case", PUBLIC_CASES, ids=[case["id"] for case in PUBLIC_CASES])
def test_public_reference_cost_is_matched(case):
    """Solve each public case from its trusted directives and compare cost only."""
    scenario = ScenarioRequest.model_validate(case["input"])
    reference = case["expected_output"]
    directives = validate_directives(
        scenario, {"directive_interpretation": reference["directive_interpretation"]}
    )
    response = _optimize(scenario, [item.model_dump() for item in directives])

    # Never worse than the organizer's plan, and no cheaper than its optimum.
    assert response["total_cost_bdt"] <= reference["total_cost_bdt"] + PUBLISHED_TOLERANCE
    assert response["total_cost_bdt"] == pytest.approx(
        reference["total_cost_bdt"], abs=PUBLISHED_TOLERANCE
    )


@pytest.mark.parametrize("case", PUBLIC_CASES, ids=[case["id"] for case in PUBLIC_CASES])
def test_public_reference_schedule_replays_against_trusted_meaning(case):
    """The generated schedule must satisfy the independently annotated directives."""
    scenario = ScenarioRequest.model_validate(case["input"])
    reference = case["expected_output"]
    response = _optimize(scenario, reference["directive_interpretation"])
    report = replay_response(
        scenario,
        response,
        trusted_directives=reference["directive_interpretation"],
    )
    assert report.valid, report.errors


# --- Contract, precision and independence ---------------------------------------


def test_response_survives_serialization_and_schema_validation():
    scenario = _scenario(10, tariff=2)
    response = _optimize(scenario)
    decoded = load_json(dump_json(response))
    assert decoded == response
    OptimizationResponse.model_validate(decoded)
    assert replay_response(scenario, decoded).valid


def test_totals_are_recomputed_from_the_emitted_plan():
    tariffs = [1 + (hour % 5) for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(50, 20, 0, 10, 10))
    response = _optimize(scenario)
    grid = _column(response, "grid_kwh")
    assert response["total_grid_kwh"] == pytest.approx(fsum(grid), abs=EXACT)
    assert response["total_cost_bdt"] == pytest.approx(
        fsum(grid[hour] * tariffs[hour] for hour in range(24)), abs=EXACT
    )
    assert response["peak_grid_kwh"] == pytest.approx(max(grid), abs=EXACT)


def test_unordered_request_hours_produce_the_same_schedule():
    tariffs = [1 + (hour % 7) for hour in range(24)]
    battery = _battery(60, 30, 10, 12, 12)
    ordered = _optimize(_scenario(15, tariff=tariffs, battery=battery))
    shuffled = _optimize(_scenario(15, tariff=tariffs, battery=battery, shuffle_seed=7))
    assert shuffled["hourly_plan"] == ordered["hourly_plan"]
    assert shuffled["total_cost_bdt"] == ordered["total_cost_bdt"]


def test_battery_returns_to_its_initial_energy():
    tariffs = [10 if 12 <= hour < 18 else 1 for hour in range(24)]
    scenario = _scenario(20, tariff=tariffs, battery=_battery(100, 45, 5, 25, 25))
    response = _optimize(scenario)
    assert response["hourly_plan"][-1]["battery_energy_after_kwh"] == pytest.approx(45, abs=EXACT)
    assert fsum(_signed_battery(response)) == pytest.approx(0.0, abs=EXACT)


def test_every_hour_has_exactly_one_battery_action():
    tariffs = [8 if hour >= 12 else 2 for hour in range(24)]
    response = _optimize(_scenario(10, tariff=tariffs, battery=_battery(80, 0, 0, 10, 10)))
    for row in response["hourly_plan"]:
        assert row["battery_action"] in {"charge", "discharge", "idle"}
        assert row["battery_kwh"] >= 0
        if row["battery_action"] == "idle":
            assert row["battery_kwh"] == 0


def test_summary_reports_checked_numbers_without_echoing_note_text():
    marker = "ZZ-OPERATOR-MARKER-42"
    scenario = _scenario(10, notes=[f"Unrelated announcement {marker}."])
    response = _optimize(scenario)
    assert marker not in response["plan_summary"]
    assert scenario.operator_notes[0] not in response["plan_summary"]
    assert "240" in response["plan_summary"]


# --- Analytical optima -----------------------------------------------------------


def test_flat_demand_without_a_battery_costs_demand_times_tariff():
    response = _optimize(_scenario(10, tariff=2))
    assert response["total_cost_bdt"] == pytest.approx(24 * 10 * 2, abs=EXACT)
    assert response["total_grid_kwh"] == pytest.approx(240, abs=EXACT)
    assert all(row["battery_action"] == "idle" for row in response["hourly_plan"])


def test_flat_tariff_gives_a_battery_no_arbitrage_value():
    """A neutral battery cannot reduce cost when every hour costs the same."""
    response = _optimize(_scenario(10, tariff=3, battery=_battery(100, 50, 0, 25, 25)))
    assert response["total_cost_bdt"] == pytest.approx(24 * 10 * 3, abs=EXACT)


def test_two_tariff_arbitrage_reaches_the_analytical_optimum():
    """Cheap hours charge 100 kWh and expensive hours discharge it: 720 - 400."""
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 0, 0, 10, 10))
    response = _optimize(scenario)
    assert response["total_cost_bdt"] == pytest.approx(320, abs=EXACT)
    # A neutral battery leaves total import at total demand, so the split
    # between the two tariff blocks is fixed even though the exact charge and
    # discharge hours are not: 220 kWh cheap plus 20 kWh dear costs 320 BDT.
    grid = _column(response, "grid_kwh")
    assert response["total_grid_kwh"] == pytest.approx(240, abs=EXACT)
    assert fsum(grid[12:]) == pytest.approx(20, abs=EXACT)
    assert fsum(_signed_battery(response)) == pytest.approx(0.0, abs=EXACT)


def test_hourly_charge_rate_caps_the_arbitrage_benefit():
    """A 5 kWh/hour charge rate stores at most 60 kWh, worth 60 x 4 BDT."""
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 0, 0, 5, 10))
    assert _optimize(scenario)["total_cost_bdt"] == pytest.approx(720 - 240, abs=EXACT)


def test_capacity_caps_the_arbitrage_benefit():
    """A 40 kWh battery stores at most 40 kWh, worth 40 x 4 BDT."""
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(40, 0, 0, 10, 10))
    assert _optimize(scenario)["total_cost_bdt"] == pytest.approx(720 - 160, abs=EXACT)


def test_initial_charge_is_spent_early_and_restored_before_midnight():
    """Expensive hours first: discharge 100 kWh, then recharge it cheaply."""
    tariffs = [5 if hour < 12 else 1 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 100, 0, 10, 10))
    response = _optimize(scenario)
    assert response["total_cost_bdt"] == pytest.approx(320, abs=EXACT)
    assert response["hourly_plan"][-1]["battery_energy_after_kwh"] == pytest.approx(100, abs=EXACT)


def test_free_solar_is_preferred_over_grid_import_at_zero_tariff():
    """Zero tariffs leave cost indifferent; the plan must still not waste solar."""
    scenario = _scenario(10, solar=10, tariff=0)
    response = _optimize(scenario)
    assert response["total_cost_bdt"] == pytest.approx(0, abs=EXACT)
    assert response["total_grid_kwh"] == pytest.approx(0, abs=EXACT)
    assert fsum(_column(response, "solar_used_kwh")) == pytest.approx(240, abs=EXACT)


# --- Directive boundaries --------------------------------------------------------


def test_solar_reduction_factor_reduces_usable_solar():
    """An 80% reduction leaves factor 0.2: 100 kWh of solar covers only 20 kWh."""
    solar = [100 if hour == 12 else 0 for hour in range(24)]
    scenario = _scenario(100, solar=solar)
    reduced = _optimize(
        scenario, [_directive("solar_reduction", {"hours": [12], "factor": 0.2})]
    )
    assert _column(reduced, "grid_kwh")[12] == pytest.approx(80, abs=EXACT)
    assert _column(reduced, "solar_used_kwh")[12] == pytest.approx(20, abs=EXACT)

    unreduced = _optimize(scenario)
    assert _column(unreduced, "grid_kwh")[12] == pytest.approx(0, abs=EXACT)
    assert reduced["total_cost_bdt"] > unreduced["total_cost_bdt"]


def test_surplus_solar_is_curtailed_and_never_exported():
    """Hour 0 offers 100 kWh but only a 5 kWh charge can absorb any of it."""
    solar = [100 if hour == 0 else 0 for hour in range(24)]
    demand = [5 if hour == 1 else 0 for hour in range(24)]
    scenario = _scenario(demand, solar=solar, battery=_battery(10, 0, 0, 5, 5))
    response = _optimize(scenario)
    assert response["total_cost_bdt"] == pytest.approx(0, abs=EXACT)
    assert response["total_grid_kwh"] == pytest.approx(0, abs=EXACT)
    assert _column(response, "solar_used_kwh")[0] == pytest.approx(5, abs=EXACT)
    assert response["hourly_plan"][0]["battery_action"] == "charge"
    assert response["hourly_plan"][1]["battery_action"] == "discharge"
    assert "Curtails 95 kWh" in response["plan_summary"]


def test_grid_cap_forces_the_battery_to_be_charged_in_advance():
    """Hour 12 may import nothing, so its demand must be stored beforehand."""
    scenario = _scenario(10, battery=_battery(50, 0, 0, 10, 10))
    response = _optimize(
        scenario, [_directive("max_grid_window", {"hours": [12], "max_grid_kwh": 0})]
    )
    assert _column(response, "grid_kwh")[12] == pytest.approx(0, abs=EXACT)
    assert response["hourly_plan"][12]["battery_action"] == "discharge"
    assert response["hourly_plan"][12]["battery_kwh"] == pytest.approx(10, abs=EXACT)
    assert response["hourly_plan"][11]["battery_energy_after_kwh"] >= 10 - EXACT
    assert response["total_grid_kwh"] == pytest.approx(240, abs=EXACT)


def test_partial_grid_cap_is_respected_every_hour():
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 0, 0, 10, 10))
    capped = list(range(12))
    response = _optimize(
        scenario,
        [_directive("max_grid_window", {"hours": capped, "max_grid_kwh": 12})],
    )
    grid = _column(response, "grid_kwh")
    assert all(grid[hour] <= 12 + EXACT for hour in capped)
    # Charging is limited to 2 kWh/hour for 12 hours, so only 24 kWh shifts.
    assert response["total_cost_bdt"] == pytest.approx(720 - 24 * 4, abs=EXACT)


def test_minimum_reserve_binds_after_each_listed_hour():
    """A reserve raises cost because stored energy cannot be spent when dear."""
    tariffs = [10 if 5 <= hour <= 10 else 1 for hour in range(24)]
    battery = _battery(100, 50, 0, 25, 25)
    scenario = _scenario(20, tariff=tariffs, battery=battery)
    window = [5, 6, 7, 8, 9, 10]
    reserved = _optimize(
        scenario,
        [
            _directive(
                "minimum_battery_reserve", {"hours": window, "minimum_energy_kwh": 50}
            )
        ],
    )
    unreserved = _optimize(scenario)
    states = _column(reserved, "battery_energy_after_kwh")
    assert all(states[hour] >= 50 - EXACT for hour in window)
    assert reserved["total_cost_bdt"] > unreserved["total_cost_bdt"]
    assert min(_column(unreserved, "battery_energy_after_kwh")[hour] for hour in window) < 50


def test_reserve_applies_after_the_listed_hour_not_before_it():
    """Hour 4 may still fall below the reserve that first binds at hour 5."""
    tariffs = [10 if hour == 4 else 1 for hour in range(24)]
    scenario = _scenario(20, tariff=tariffs, battery=_battery(100, 60, 0, 25, 25))
    response = _optimize(
        scenario,
        [_directive("minimum_battery_reserve", {"hours": [5], "minimum_energy_kwh": 60})],
    )
    states = _column(response, "battery_energy_after_kwh")
    assert states[4] < 60
    assert states[5] >= 60 - EXACT


def test_no_charge_window_removes_the_arbitrage_opportunity():
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 0, 0, 10, 10))
    response = _optimize(
        scenario, [_directive("no_charge_window", {"hours": list(range(12))})]
    )
    assert response["total_cost_bdt"] == pytest.approx(720, abs=EXACT)
    assert all(
        row["battery_action"] != "charge" for row in response["hourly_plan"][:12]
    )


def test_no_discharge_window_blocks_spending_stored_energy():
    tariffs = [5 if hour < 12 else 1 for hour in range(24)]
    scenario = _scenario(10, tariff=tariffs, battery=_battery(100, 100, 0, 10, 10))
    response = _optimize(
        scenario, [_directive("no_discharge_window", {"hours": list(range(12))})]
    )
    assert response["total_cost_bdt"] == pytest.approx(720, abs=EXACT)


def test_overlapping_prohibitions_force_an_idle_hour():
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    scenario = _scenario(
        10,
        tariff=tariffs,
        battery=_battery(100, 50, 0, 10, 10),
        notes=["No charging at noon.", "No discharging at noon."],
    )
    response = _optimize(
        scenario,
        [
            _directive("no_charge_window", {"hours": [12]}, index=0),
            _directive("no_discharge_window", {"hours": [12]}, index=1),
        ],
    )
    assert response["hourly_plan"][12]["battery_action"] == "idle"
    assert response["hourly_plan"][12]["battery_kwh"] == 0


def test_overlapping_reserves_combine_by_maximum():
    tariffs = [10 if hour == 8 else 1 for hour in range(24)]
    scenario = _scenario(
        20,
        tariff=tariffs,
        battery=_battery(100, 80, 0, 25, 25),
        notes=["Keep 40 kWh in reserve.", "Keep 70 kWh in reserve."],
    )
    response = _optimize(
        scenario,
        [
            _directive(
                "minimum_battery_reserve", {"hours": [8], "minimum_energy_kwh": 40}, index=0
            ),
            _directive(
                "minimum_battery_reserve", {"hours": [8], "minimum_energy_kwh": 70}, index=1
            ),
        ],
    )
    assert _column(response, "battery_energy_after_kwh")[8] >= 70 - EXACT


def test_overlapping_grid_caps_combine_by_minimum():
    scenario = _scenario(
        10,
        battery=_battery(50, 25, 0, 10, 10),
        notes=["Cap imports at 8 kWh.", "Cap imports at 4 kWh."],
    )
    response = _optimize(
        scenario,
        [
            _directive("max_grid_window", {"hours": [6], "max_grid_kwh": 8}, index=0),
            _directive("max_grid_window", {"hours": [6], "max_grid_kwh": 4}, index=1),
        ],
    )
    assert _column(response, "grid_kwh")[6] <= 4 + EXACT


# --- Rejected and infeasible scenarios -------------------------------------------


def test_zero_rate_battery_stays_idle_all_day():
    tariffs = [1 if hour < 12 else 5 for hour in range(24)]
    response = _optimize(_scenario(10, tariff=tariffs, battery=_battery(100, 50, 0, 0, 0)))
    assert all(row["battery_action"] == "idle" for row in response["hourly_plan"])
    assert response["total_cost_bdt"] == pytest.approx(720, abs=EXACT)


def test_zero_grid_cap_without_stored_energy_is_infeasible():
    scenario = _scenario(10)
    with pytest.raises(OptimizerError) as error:
        _optimize(scenario, [_directive("max_grid_window", {"hours": [0], "max_grid_kwh": 0})])
    assert error.value.code == "infeasible_scenario"


def test_reserve_above_initial_energy_at_the_final_hour_is_infeasible():
    """Final energy must equal the initial level, so hour 23 cannot be raised."""
    scenario = _scenario(10, battery=_battery(100, 10, 0, 10, 10))
    with pytest.raises(OptimizerError) as error:
        _optimize(
            scenario,
            [_directive("minimum_battery_reserve", {"hours": [23], "minimum_energy_kwh": 50})],
        )
    assert error.value.code == "infeasible_scenario"


def test_reserve_unreachable_within_the_charge_rate_is_infeasible():
    """5 kWh/hour cannot lift a 10 kWh battery to 90 kWh by hour 1."""
    scenario = _scenario(10, battery=_battery(100, 10, 0, 5, 5))
    with pytest.raises(OptimizerError) as error:
        _optimize(
            scenario,
            [_directive("minimum_battery_reserve", {"hours": [1], "minimum_energy_kwh": 90})],
        )
    assert error.value.code == "infeasible_scenario"


def test_reserve_above_capacity_is_rejected_before_solving():
    scenario = _scenario(10, battery=_battery(50, 25, 0, 10, 10))
    with pytest.raises(DirectiveValidationError) as error:
        _optimize(
            scenario,
            [_directive("minimum_battery_reserve", {"hours": [3], "minimum_energy_kwh": 60})],
        )
    assert error.value.code == "reserve_exceeds_capacity"


def test_differing_overlapping_solar_factors_are_rejected_before_solving():
    scenario = _scenario(
        10,
        solar=20,
        notes=["Solar down to 40% at noon.", "Solar down to 70% at noon."],
    )
    with pytest.raises(DirectiveValidationError) as error:
        _optimize(
            scenario,
            [
                _directive("solar_reduction", {"hours": [12], "factor": 0.4}, index=0),
                _directive("solar_reduction", {"hours": [12], "factor": 0.7}, index=1),
            ],
        )
    assert error.value.code == "ambiguous_solar_overlap"


def test_optimizer_error_messages_stay_static_and_input_free():
    scenario = _scenario(10, notes=["ZZ-OPERATOR-MARKER-42 blackout at midnight."])
    with pytest.raises(OptimizerError) as error:
        _optimize(scenario, [_directive("max_grid_window", {"hours": [0], "max_grid_kwh": 0})])
    assert "ZZ-OPERATOR-MARKER-42" not in str(error.value)
    assert str(error.value) == "No schedule satisfies the scenario and its directives."


# --- Direct solver interface -----------------------------------------------------


def test_solve_schedule_reports_effective_solar_after_directives():
    solar = [40 if hour == 9 else 0 for hour in range(24)]
    scenario = _scenario(50, solar=solar)
    directives = validate_directives(
        scenario,
        {
            "directive_interpretation": [
                _directive("solar_reduction", {"hours": [9], "factor": 0.25})
            ]
        },
    )
    schedule = solve_schedule(scenario, build_hourly_bounds(scenario, directives))
    assert schedule.effective_solar_kwh[9] == pytest.approx(10, abs=EXACT)
    assert schedule.solar_used_kwh[9] == pytest.approx(10, abs=EXACT)
    assert schedule.grid_kwh[9] == pytest.approx(40, abs=EXACT)


def test_solve_schedule_keeps_battery_energy_consistent_with_its_movements():
    tariffs = [2 if hour % 2 else 9 for hour in range(24)]
    scenario = _scenario(12, tariff=tariffs, battery=_battery(60, 30, 5, 15, 15))
    directives = validate_directives(scenario, {"directive_interpretation": [_directive()]})
    schedule = solve_schedule(scenario, build_hourly_bounds(scenario, directives))
    running = scenario.battery.initial_energy_kwh
    for hour in range(24):
        running = fsum([running, schedule.battery_delta_kwh[hour]])
        assert schedule.battery_energy_after_kwh[hour] == pytest.approx(running, abs=EXACT)
        assert 5 - EXACT <= schedule.battery_energy_after_kwh[hour] <= 60 + EXACT


# --- Randomized robustness -------------------------------------------------------


def _random_case(rng):
    capacity = round(rng.uniform(0, 300), 2)
    initial = round(rng.uniform(0, capacity), 2)
    battery = _battery(
        capacity,
        initial,
        round(rng.uniform(0, initial), 2) if initial else 0.0,
        round(rng.uniform(0, 80), 2),
        round(rng.uniform(0, 80), 2),
    )
    demand = [round(rng.uniform(0, 250), 2) for _ in range(24)]
    solar = [round(rng.uniform(0, 200), 2) for _ in range(24)]
    tariff = [round(rng.choice([0.0, 0.5, rng.uniform(1, 40)]), 3) for _ in range(24)]
    kinds = [
        "no_op",
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
    ]
    raw = []
    for index in range(rng.randint(1, 3)):
        kind = rng.choice(kinds)
        hours = sorted(rng.sample(range(24), rng.randint(0, 6)))
        if kind == "solar_reduction":
            adjustment = {"hours": hours, "factor": round(rng.uniform(0, 1), 3)}
        elif kind == "minimum_battery_reserve":
            adjustment = {
                "hours": hours,
                "minimum_energy_kwh": round(rng.uniform(0, capacity * 1.2), 2),
            }
        elif kind == "max_grid_window":
            adjustment = {"hours": hours, "max_grid_kwh": round(rng.uniform(0, 200), 2)}
        elif kind in ("no_charge_window", "no_discharge_window"):
            adjustment = {"hours": hours}
        else:
            adjustment = None
        raw.append(_directive(kind, adjustment, index=index))
    notes = [f"Synthetic operator note {index}." for index in range(len(raw))]
    return _scenario(demand, solar=solar, tariff=tariff, battery=battery, notes=notes), raw


def test_random_scenarios_either_replay_cleanly_or_fail_in_a_controlled_way():
    """Every generated schedule must satisfy the checker; nothing may escape raw."""
    rng = random.Random(20260918)
    solved = controlled = 0
    for _ in range(150):
        scenario, raw = _random_case(rng)
        try:
            response = _optimize(scenario, raw)
        except (OptimizerError, DirectiveValidationError):
            controlled += 1
            continue
        report = replay_response(scenario, response, trusted_directives=raw)
        assert report.valid, report.errors
        solved += 1
    # Both outcomes must actually occur, or the sweep is not exercising much.
    assert solved > 50
    assert controlled > 5
