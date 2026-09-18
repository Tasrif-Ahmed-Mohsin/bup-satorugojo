"""Independent checks of a complete, decoded GridWise response.

This module deliberately does not use the directive-to-optimizer bounds builder.
Without trusted directives it checks internal consistency, not language accuracy
or optimality. With trusted directives it also compares structured meanings
(excluding explanations), then checks the schedule against the trusted meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isclose, isfinite
from typing import Iterable

from pydantic import ValidationError

from app.schemas import Directive, DirectiveEnvelope, OptimizationResponse, ScenarioRequest


@dataclass(frozen=True)
class ReplayReport:
    valid: bool
    errors: tuple[str, ...]
    total_grid_kwh: float | None
    total_cost_bdt: float | None
    peak_grid_kwh: float | None


def _failure(message: str) -> ReplayReport:
    return ReplayReport(False, (message,), None, None, None)


def _finite_sum(values: Iterable[float]) -> float | None:
    try:
        result = fsum(values)
    except (ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _close(left: float, right: float, tolerance: float) -> bool:
    return isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _above(value: float, limit: float, tolerance: float) -> bool:
    return value > limit and not _close(value, limit, tolerance)


def _below(value: float, limit: float, tolerance: float) -> bool:
    return value < limit and not _close(value, limit, tolerance)


def _check_directives(
    directives: list[Directive], scenario: ScenarioRequest, label: str, errors: list[str]
) -> None:
    if [item.note_index for item in directives] != list(range(len(scenario.operator_notes))):
        errors.append(f"{label}: note coverage or order mismatch")
    for item in directives:
        if item.directive_type == "minimum_battery_reserve":
            if item.structured_adjustment.minimum_energy_kwh > scenario.battery.capacity_kwh:
                errors.append(f"{label}: reserve exceeds battery capacity")


def _same_meaning(left: Directive, right: Directive, tolerance: float) -> bool:
    if (left.note_index, left.applies, left.directive_type) != (
        right.note_index,
        right.applies,
        right.directive_type,
    ):
        return False
    a, b = left.structured_adjustment, right.structured_adjustment
    if a is None or b is None:
        return a is None and b is None
    if a.hours != b.hours:
        return False
    if left.directive_type == "solar_reduction":
        # A kWh tolerance is not a dimensionless-factor tolerance. Only allow
        # representation-level noise here; larger differences affect solar.
        return _close(a.factor, b.factor, 1e-12)
    if left.directive_type == "minimum_battery_reserve":
        return _close(a.minimum_energy_kwh, b.minimum_energy_kwh, tolerance)
    if left.directive_type == "max_grid_window":
        return _close(a.max_grid_kwh, b.max_grid_kwh, tolerance)
    return True


def replay_response(
    scenario: ScenarioRequest,
    payload: object,
    *,
    tolerance: float = 0.01,
    trusted_directives: object | None = None,
) -> ReplayReport:
    """Validate a response without changing it or trusting its reported state.

    ``payload`` is normally the result of decoding the final response JSON.
    ``trusted_directives`` may be a list of directive dictionaries or models
    from independently annotated reference data. It is never inferred from
    scenario IDs or operator-note phrases. Factor comparisons use 1e-12;
    physical quantities and directive energy values use the absolute tolerance.
    Errors contain fixed labels and validated hour numbers, never source text.
    """
    if type(tolerance) not in (int, float):
        return _failure("replay tolerance is invalid")
    try:
        if not isfinite(tolerance) or tolerance < 0:
            return _failure("replay tolerance is invalid")
    except OverflowError:
        return _failure("replay tolerance is invalid")

    try:
        if not isinstance(scenario, ScenarioRequest):
            return _failure("scenario schema is invalid")
        # Revalidation also protects callers passing mutated model instances.
        scenario = ScenarioRequest.model_validate(
            scenario.model_dump(mode="python", warnings=False)
        )
    except (ValidationError, TypeError, ValueError, OverflowError):
        return _failure("scenario schema is invalid")

    try:
        if isinstance(payload, OptimizationResponse):
            payload = payload.model_dump(mode="python", warnings=False)
        response = OptimizationResponse.model_validate(payload)
        # Nested Pydantic instances may skip validation on the first pass.
        # Revalidate primitive values without emitting serializer warnings that
        # could echo untrusted data from a mutated/constructed model instance.
        response = OptimizationResponse.model_validate(
            response.model_dump(mode="python", warnings=False)
        )
    except (ValidationError, TypeError, ValueError, OverflowError):
        return _failure("response schema is invalid")

    errors: list[str] = []
    if response.scenario_id != scenario.scenario_id:
        errors.append("scenario_id mismatch")
    reported = response.directive_interpretation
    _check_directives(reported, scenario, "reported directives", errors)
    active = reported
    if trusted_directives is not None:
        try:
            if not isinstance(trusted_directives, (list, tuple)):
                return _failure("trusted directive schema is invalid")
            raw = [
                item.model_dump(mode="python", warnings=False)
                if isinstance(item, Directive)
                else item
                for item in trusted_directives
            ]
            trusted_envelope = DirectiveEnvelope.model_validate({"directive_interpretation": raw})
            trusted = DirectiveEnvelope.model_validate(
                trusted_envelope.model_dump(mode="python", warnings=False)
            ).directive_interpretation
        except (ValidationError, TypeError, ValueError, OverflowError):
            return _failure("trusted directive schema is invalid")
        _check_directives(trusted, scenario, "trusted directives", errors)
        if len(reported) != len(trusted) or any(
            not _same_meaning(left, right, tolerance) for left, right in zip(reported, trusted)
        ):
            errors.append("reported directive meaning differs from trusted directives")
        # Check the response's OWN claimed directives as well as the trusted
        # interpretation. Two tolerance allowances must not combine into a
        # larger violation of a reported rule. This additional call has no
        # trusted_directives argument, so recursion stops after one level.
        reported_report = replay_response(scenario, response, tolerance=tolerance)
        errors.extend(f"reported schedule: {error}" for error in reported_report.errors)
        active = trusted

    physical_start = len(errors)
    battery = scenario.battery
    hours = {item.hour: item for item in scenario.hours}
    solar = [hours[h].solar_kwh for h in range(24)]
    reserve = [battery.minimum_energy_kwh] * 24
    grid_cap: list[float | None] = [None] * 24
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    solar_factor: dict[int, float] = {}

    # Independent interpretation of each supported rule, without shared bounds.
    for item in active:
        adjustment = item.structured_adjustment
        kind = item.directive_type
        if kind == "no_op":
            continue
        for h in adjustment.hours:
            if kind == "solar_reduction":
                if h in solar_factor and solar_factor[h] != adjustment.factor:
                    errors.append(f"hour {h}: differing overlapping solar factors are unsupported")
                else:
                    solar_factor[h] = adjustment.factor
                    solar[h] = hours[h].solar_kwh * adjustment.factor
            elif kind == "minimum_battery_reserve":
                reserve[h] = max(reserve[h], adjustment.minimum_energy_kwh)
            elif kind == "max_grid_window":
                cap = adjustment.max_grid_kwh
                grid_cap[h] = cap if grid_cap[h] is None else min(grid_cap[h], cap)
            elif kind == "no_charge_window":
                no_charge.add(h)
            elif kind == "no_discharge_window":
                no_discharge.add(h)

    deltas: list[float] = []
    reconstructed: float | None = battery.initial_energy_kwh
    previous_reported = battery.initial_energy_kwh
    for row in response.hourly_plan:
        h = row.hour
        charge = row.battery_kwh if row.battery_action == "charge" else 0.0
        discharge = row.battery_kwh if row.battery_action == "discharge" else 0.0
        deltas.append(charge - discharge)
        emitted_next = _finite_sum((previous_reported, charge, -discharge))
        if emitted_next is None:
            errors.append(f"hour {h}: emitted battery transition arithmetic is nonfinite")
        elif not _close(row.battery_energy_after_kwh, emitted_next, tolerance):
            errors.append(f"hour {h}: emitted battery transition mismatch")
        previous_reported = row.battery_energy_after_kwh
        # Reconstruct from initial energy and ALL actions. Never restart from
        # row.battery_energy_after_kwh; small per-hour lies otherwise accumulate.
        reconstructed = _finite_sum((battery.initial_energy_kwh, *deltas))
        if reconstructed is None:
            errors.append(f"hour {h}: reconstructed battery energy is nonfinite")
        else:
            if not _close(row.battery_energy_after_kwh, reconstructed, tolerance):
                errors.append(f"hour {h}: battery state mismatch")
            if _below(reconstructed, reserve[h], tolerance):
                errors.append(f"hour {h}: reconstructed battery below reserve")
            if _above(reconstructed, battery.capacity_kwh, tolerance):
                errors.append(f"hour {h}: reconstructed battery above capacity")
        if _below(row.battery_energy_after_kwh, reserve[h], tolerance):
            errors.append(f"hour {h}: reported battery below reserve")
        if _above(row.battery_energy_after_kwh, battery.capacity_kwh, tolerance):
            errors.append(f"hour {h}: reported battery above capacity")
        if _above(charge, battery.max_charge_kwh_per_hour, tolerance):
            errors.append(f"hour {h}: charge rate exceeded")
        if _above(discharge, battery.max_discharge_kwh_per_hour, tolerance):
            errors.append(f"hour {h}: discharge rate exceeded")
        if h in no_charge and not _close(charge, 0.0, tolerance):
            errors.append(f"hour {h}: prohibited charging")
        if h in no_discharge and not _close(discharge, 0.0, tolerance):
            errors.append(f"hour {h}: prohibited discharging")
        if _above(row.solar_used_kwh, solar[h], tolerance):
            errors.append(f"hour {h}: available solar exceeded")
        if grid_cap[h] is not None and _above(row.grid_kwh, grid_cap[h], tolerance):
            errors.append(f"hour {h}: grid cap exceeded")
        residual = _finite_sum(
            (row.grid_kwh, row.solar_used_kwh, discharge, -hours[h].demand_kwh, -charge)
        )
        if residual is None:
            errors.append(f"hour {h}: energy balance arithmetic is nonfinite")
        elif not _close(residual, 0.0, tolerance):
            errors.append(f"hour {h}: energy balance mismatch")

    if reconstructed is None or not _close(reconstructed, battery.initial_energy_kwh, tolerance):
        errors.append("reconstructed final battery violates neutrality")
    if not _close(
        response.hourly_plan[-1].battery_energy_after_kwh,
        battery.initial_energy_kwh,
        tolerance,
    ):
        errors.append("reported final battery violates neutrality")

    total_grid = _finite_sum(row.grid_kwh for row in response.hourly_plan)
    total_cost = _finite_sum(
        row.grid_kwh * hours[row.hour].tariff_bdt_per_kwh for row in response.hourly_plan
    )
    peak_grid = max(row.grid_kwh for row in response.hourly_plan)
    for name, actual in (
        ("total_grid_kwh", total_grid),
        ("total_cost_bdt", total_cost),
        ("peak_grid_kwh", peak_grid),
    ):
        if actual is None:
            errors.append(f"{name}: recomputed value is nonfinite")
        elif not _close(getattr(response, name), actual, tolerance):
            errors.append(f"{name}: reported value mismatch")

    if trusted_directives is not None:
        errors[physical_start:] = (
            f"trusted schedule: {error}" for error in errors[physical_start:]
        )
    return ReplayReport(not errors, tuple(errors), total_grid, total_cost, peak_grid)
