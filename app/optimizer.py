"""Continuous linear program for the GridWise 24-hour schedule.

The published rules describe a lossless battery, so grid import, solar use,
signed battery flow and end-of-hour energy are continuous. The scheduling
problem is therefore a linear program. No binary variables, conversion
efficiency, degradation cost or peak penalty is introduced: the only objective
stated by the source is the cost of imported grid electricity.

A solved schedule is never trusted on the solver's word. The complete response
is constructed, serialized, decoded and independently replayed by ``app.replay``
before it is returned, and the decoded payload is returned unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isfinite

import numpy as np
from scipy.optimize import linprog

from app.directives import HourBounds, build_hourly_bounds
from app.jsonio import JsonPayloadError, dump_json, load_json
from app.replay import replay_response
from app.schemas import Directive, ScenarioRequest

HOURS = 24
GRID = 0
SOLAR = HOURS
BATTERY = 2 * HOURS
ENERGY = 3 * HOURS
VARIABLES = 4 * HOURS

# Solver artifacts below this magnitude are treated as an exact zero.
_SNAP = 1e-9
# Our own reconstruction must agree with the solver far inside the published
# 0.01 tolerance. A larger disagreement means the solver result is unusable.
_REPAIR = 1e-6

_ERROR_MESSAGES = {
    "infeasible_scenario": "No schedule satisfies the scenario and its directives.",
    "solver_failed": "The scheduling solver did not return a usable optimal result.",
    "invalid_schedule": "The generated schedule failed independent verification.",
}


class OptimizerError(ValueError):
    """Only static, safe messages cross the optimizer boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)


@dataclass(frozen=True)
class Schedule:
    """Hourly decisions reconstructed from the solver result by exact arithmetic."""

    grid_kwh: tuple[float, ...]
    solar_used_kwh: tuple[float, ...]
    battery_delta_kwh: tuple[float, ...]
    battery_energy_after_kwh: tuple[float, ...]
    effective_solar_kwh: tuple[float, ...]


def _snap(value: float, low: float, high: float | None) -> float:
    """Clip into the variable's own box bounds and remove signed-zero noise."""
    if value < low:
        value = low
    if high is not None and value > high:
        value = high
    if -_SNAP < value < _SNAP:
        return 0.0
    return value


def _build_program(
    scenario: ScenarioRequest, bounds: list[HourBounds]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[float, float | None]]]:
    battery = scenario.battery
    hours = {item.hour: item for item in scenario.hours}
    limits = {item.hour: item for item in bounds}

    cost = np.zeros(VARIABLES)
    for h in range(HOURS):
        cost[GRID + h] = hours[h].tariff_bdt_per_kwh

    # 24 hourly balances, 24 state transitions, and one final neutrality row.
    a_eq = np.zeros((2 * HOURS + 1, VARIABLES))
    b_eq = np.zeros(2 * HOURS + 1)
    for h in range(HOURS):
        a_eq[h, GRID + h] = 1.0
        a_eq[h, SOLAR + h] = 1.0
        a_eq[h, BATTERY + h] = -1.0
        b_eq[h] = hours[h].demand_kwh

    a_eq[HOURS, ENERGY + 0] = 1.0
    a_eq[HOURS, BATTERY + 0] = -1.0
    b_eq[HOURS] = battery.initial_energy_kwh
    for h in range(1, HOURS):
        a_eq[HOURS + h, ENERGY + h] = 1.0
        a_eq[HOURS + h, ENERGY + h - 1] = -1.0
        a_eq[HOURS + h, BATTERY + h] = -1.0

    a_eq[2 * HOURS, ENERGY + HOURS - 1] = 1.0
    b_eq[2 * HOURS] = battery.initial_energy_kwh

    variable_bounds: list[tuple[float, float | None]] = [(0.0, None)] * VARIABLES
    for h in range(HOURS):
        limit = limits[h]
        variable_bounds[GRID + h] = (0.0, limit.max_grid_kwh)
        variable_bounds[SOLAR + h] = (0.0, limit.effective_solar_kwh)
        # The default nonnegative lower bound would prohibit discharging.
        variable_bounds[BATTERY + h] = (-limit.max_discharge_kwh, limit.max_charge_kwh)
        variable_bounds[ENERGY + h] = (limit.minimum_energy_kwh, battery.capacity_kwh)
    return cost, a_eq, b_eq, variable_bounds


def _solve(
    cost: np.ndarray,
    a_eq: np.ndarray,
    b_eq: np.ndarray,
    variable_bounds: list[tuple[float, float | None]],
    a_ub: np.ndarray | None = None,
    b_ub: np.ndarray | None = None,
) -> np.ndarray:
    result = linprog(
        cost,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=variable_bounds,
        method="highs",
    )
    if result.status == 2:
        raise OptimizerError("infeasible_scenario")
    if not result.success or result.status != 0 or result.x is None:
        raise OptimizerError("solver_failed")
    values = np.asarray(result.x, dtype=float)
    if values.shape != (VARIABLES,) or not np.all(np.isfinite(values)):
        raise OptimizerError("solver_failed")
    return values


def _refine(
    values: np.ndarray,
    cost: np.ndarray,
    a_eq: np.ndarray,
    b_eq: np.ndarray,
    variable_bounds: list[tuple[float, float | None]],
) -> np.ndarray:
    """Break ties between equally cheap schedules; never accept a dearer one.

    Zero or equal tariffs leave the cost objective indifferent between paid
    grid import and free solar, so a cost-optimal schedule can still arrive
    with pointless imports. This second pass minimises total grid energy while
    holding cost at the optimum. Minimising imports is not a stated objective
    and it actively opposes battery arbitrage, so the refined schedule is kept
    only when it costs no more than the first one: the row slack exists purely
    so the constraint stays feasible inside the solver's own tolerance, never
    as a cost allowance. Any failure keeps the first optimal solution.
    """
    optimal_cost = float(cost @ values)
    if not isfinite(optimal_cost):
        return values
    slack = max(1e-7, abs(optimal_cost) * 1e-9)
    total_grid = np.zeros(VARIABLES)
    total_grid[GRID : GRID + HOURS] = 1.0
    try:
        refined = _solve(
            total_grid,
            a_eq,
            b_eq,
            variable_bounds,
            a_ub=cost.reshape(1, VARIABLES),
            b_ub=np.array([optimal_cost + slack]),
        )
    except OptimizerError:
        return values
    refined_cost = float(cost @ refined)
    # Only representation-level noise is tolerated, not the feasibility slack.
    if not isfinite(refined_cost) or refined_cost > optimal_cost + max(
        1e-12, abs(optimal_cost) * 1e-12
    ):
        return values
    return refined


def _reconstruct(
    scenario: ScenarioRequest, bounds: list[HourBounds], values: np.ndarray
) -> Schedule:
    """Rebuild the schedule so the energy balance and battery state are exact.

    Grid import is derived from the hourly balance and battery energy from the
    running total of the emitted battery movements, so the schedule satisfies
    those identities by construction rather than by solver tolerance. Solver
    output disagreeing with this reconstruction by more than ``_REPAIR`` is
    rejected instead of published.
    """
    battery = scenario.battery
    hours = {item.hour: item for item in scenario.hours}
    limits = {item.hour: item for item in bounds}

    grid: list[float] = []
    solar_used: list[float] = []
    deltas: list[float] = []
    energy: list[float] = []
    for h in range(HOURS):
        limit = limits[h]
        delta = _snap(float(values[BATTERY + h]), -limit.max_discharge_kwh, limit.max_charge_kwh)
        used = _snap(float(values[SOLAR + h]), 0.0, limit.effective_solar_kwh)
        imported = hours[h].demand_kwh + delta - used
        if not isfinite(imported):
            raise OptimizerError("solver_failed")
        if abs(imported - float(values[GRID + h])) > _REPAIR:
            raise OptimizerError("solver_failed")
        if imported < 0.0:
            if imported < -_REPAIR:
                raise OptimizerError("solver_failed")
            imported = 0.0
        cap = limit.max_grid_kwh
        if cap is not None and imported > cap:
            if imported - cap > _REPAIR:
                raise OptimizerError("solver_failed")
            imported = cap
        imported = _snap(imported, 0.0, None)

        deltas.append(delta)
        state = fsum([battery.initial_energy_kwh, *deltas])
        if not isfinite(state):
            raise OptimizerError("solver_failed")
        if state < 0.0:
            if state < -_REPAIR:
                raise OptimizerError("solver_failed")
            state = 0.0
        if state < limit.minimum_energy_kwh - _REPAIR or state > battery.capacity_kwh + _REPAIR:
            raise OptimizerError("solver_failed")

        grid.append(imported)
        solar_used.append(used)
        energy.append(state)

    if abs(energy[-1] - battery.initial_energy_kwh) > _REPAIR:
        raise OptimizerError("solver_failed")
    return Schedule(
        grid_kwh=tuple(grid),
        solar_used_kwh=tuple(solar_used),
        battery_delta_kwh=tuple(deltas),
        battery_energy_after_kwh=tuple(energy),
        effective_solar_kwh=tuple(limits[h].effective_solar_kwh for h in range(HOURS)),
    )


def solve_schedule(scenario: ScenarioRequest, bounds: list[HourBounds]) -> Schedule:
    """Return the minimum grid-cost schedule for already validated hourly bounds."""
    cost, a_eq, b_eq, variable_bounds = _build_program(scenario, bounds)
    values = _solve(cost, a_eq, b_eq, variable_bounds)
    values = _refine(values, cost, a_eq, b_eq, variable_bounds)
    return _reconstruct(scenario, bounds, values)


def warm_up() -> bool:
    """Pay the solver's first-call setup at startup, not on a judged request.

    The first HiGHS solve in a fresh process is markedly slower than the rest,
    which would otherwise land on whoever calls the service first.
    """
    cost = np.zeros(VARIABLES)
    a_eq = np.zeros((1, VARIABLES))
    a_eq[0, GRID] = 1.0
    try:
        _solve(cost, a_eq, np.zeros(1), [(0.0, 1.0)] * VARIABLES)
    except OptimizerError:
        return False
    return True


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _format(value: float) -> str:
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def build_summary(
    scenario: ScenarioRequest,
    directives: list[Directive],
    schedule: Schedule,
    total_grid: float,
    total_cost: float,
    peak_grid: float,
) -> str:
    """Describe the checked numbers only; never echo operator note text."""
    active = [item for item in directives if item.directive_type != "no_op"]
    parts: list[str] = []
    if active:
        kinds = sorted({item.directive_type.replace("_", " ") for item in active})
        parts.append(
            f"Applies {len(active)} of {_count(len(directives), 'operator note')} "
            f"as scheduling constraints ({', '.join(kinds)})."
        )
    else:
        reviewed = "1 was" if len(directives) == 1 else f"{len(directives)} were"
        parts.append(f"No operator note changes the schedule; {reviewed} reviewed.")
    parts.append(
        f"Imports {_format(total_grid)} kWh from the grid for "
        f"{_format(total_cost)} BDT, peaking at {_format(peak_grid)} kWh in one hour."
    )
    charging = sum(1 for delta in schedule.battery_delta_kwh if delta > 0)
    discharging = sum(1 for delta in schedule.battery_delta_kwh if delta < 0)
    if charging or discharging:
        parts.append(
            f"Charges in {_count(charging, 'hour')} and discharges in "
            f"{_count(discharging, 'hour')}, "
            f"ending at the initial {_format(scenario.battery.initial_energy_kwh)} kWh."
        )
    else:
        parts.append(
            f"Leaves the battery idle at {_format(scenario.battery.initial_energy_kwh)} kWh."
        )
    curtailed = fsum(schedule.effective_solar_kwh) - fsum(schedule.solar_used_kwh)
    if curtailed > 0.01:
        parts.append(f"Curtails {_format(curtailed)} kWh of usable solar.")
    return " ".join(parts)


def build_response(
    scenario: ScenarioRequest, directives: list[Directive], schedule: Schedule
) -> dict:
    """Assemble the exact successful response contract from emitted values."""
    tariff = {item.hour: item.tariff_bdt_per_kwh for item in scenario.hours}
    hourly_plan = []
    for h in range(HOURS):
        delta = schedule.battery_delta_kwh[h]
        if delta > 0:
            action, magnitude = "charge", delta
        elif delta < 0:
            action, magnitude = "discharge", -delta
        else:
            action, magnitude = "idle", 0.0
        hourly_plan.append(
            {
                "hour": h,
                "grid_kwh": schedule.grid_kwh[h],
                "solar_used_kwh": schedule.solar_used_kwh[h],
                "battery_action": action,
                "battery_kwh": magnitude,
                "battery_energy_after_kwh": schedule.battery_energy_after_kwh[h],
            }
        )

    total_grid = fsum(schedule.grid_kwh)
    total_cost = fsum(schedule.grid_kwh[h] * tariff[h] for h in range(HOURS))
    peak_grid = max(schedule.grid_kwh)
    if not (isfinite(total_grid) and isfinite(total_cost) and isfinite(peak_grid)):
        raise OptimizerError("solver_failed")
    return {
        "scenario_id": scenario.scenario_id,
        "directive_interpretation": [
            item.model_dump(mode="python", warnings=False) for item in directives
        ],
        "hourly_plan": hourly_plan,
        "total_grid_kwh": total_grid,
        "total_cost_bdt": total_cost,
        "peak_grid_kwh": peak_grid,
        "plan_summary": build_summary(
            scenario, directives, schedule, total_grid, total_cost, peak_grid
        ),
    }


def optimize_scenario(
    scenario: ScenarioRequest, directives: list[Directive], *, tolerance: float = 0.01
) -> dict:
    """Solve, serialize, decode and independently replay before returning.

    The returned object is the decoded response that passed replay. Callers
    must send it unchanged: recomputing or reformatting any field after this
    point would publish something the checker never saw.
    """
    bounds = build_hourly_bounds(scenario, directives)
    schedule = solve_schedule(scenario, bounds)
    response = build_response(scenario, directives, schedule)
    try:
        decoded = load_json(dump_json(response))
    except JsonPayloadError:
        raise OptimizerError("invalid_schedule") from None
    report = replay_response(scenario, decoded, tolerance=tolerance)
    if not report.valid:
        raise OptimizerError("invalid_schedule")
    return decoded
