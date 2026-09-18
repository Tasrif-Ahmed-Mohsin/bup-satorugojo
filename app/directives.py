"""Validate untrusted model interpretations and derive explicit hourly bounds."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas import (
    Directive,
    DirectiveEnvelope,
    MaxGridAdjustment,
    MinimumBatteryReserveAdjustment,
    ScenarioRequest,
    SolarReductionAdjustment,
)

_ERROR_MESSAGES = {
    "invalid_directives": "The model interpretation does not satisfy the directive contract.",
    "note_count_mismatch": "The model interpretation must cover every operator note exactly once.",
    "reserve_exceeds_capacity": "An interpreted battery reserve exceeds battery capacity.",
    "ambiguous_solar_overlap": "Different solar factors overlap; the published rules do not define their combination.",
}


class DirectiveValidationError(ValueError):
    """Only static, safe messages cross the model-validation boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)


def _sort_valid_adjustment_hours(raw: object) -> object:
    """Sort valid hour identities without changing, inventing, or deduplicating any."""
    if type(raw) is not dict:
        return raw
    entries = raw.get("directive_interpretation")
    if type(entries) is not list:
        return raw
    result = dict(raw)
    normalized_entries = []
    for entry in entries:
        if type(entry) is not dict:
            normalized_entries.append(entry)
            continue
        item = dict(entry)
        adjustment = item.get("structured_adjustment")
        if type(adjustment) is dict:
            adjustment_copy = dict(adjustment)
            hours = adjustment_copy.get("hours")
            if (
                type(hours) is list
                and all(type(hour) is int and 0 <= hour <= 23 for hour in hours)
                and len(set(hours)) == len(hours)
            ):
                adjustment_copy["hours"] = sorted(hours)
            item["structured_adjustment"] = adjustment_copy
        normalized_entries.append(item)
    result["directive_interpretation"] = normalized_entries
    return result


def validate_directives(scenario: ScenarioRequest, raw: object) -> list[Directive]:
    """Return one validated entry per note; never replace failed notes with no_op."""
    try:
        envelope = DirectiveEnvelope.model_validate(_sort_valid_adjustment_hours(raw))
    except ValidationError:
        raise DirectiveValidationError("invalid_directives") from None
    directives = envelope.directive_interpretation
    if len(directives) != len(scenario.operator_notes):
        raise DirectiveValidationError("note_count_mismatch")
    for directive in directives:
        adjustment = directive.structured_adjustment
        if (
            isinstance(adjustment, MinimumBatteryReserveAdjustment)
            and adjustment.minimum_energy_kwh > scenario.battery.capacity_kwh
        ):
            raise DirectiveValidationError("reserve_exceeds_capacity")
    return directives


@dataclass(frozen=True)
class HourBounds:
    hour: int
    effective_solar_kwh: float
    minimum_energy_kwh: float
    max_grid_kwh: float | None
    max_charge_kwh: float
    max_discharge_kwh: float


def build_hourly_bounds(scenario: ScenarioRequest, directives: list[Directive]) -> list[HourBounds]:
    """Apply supported bounds; reject unspecified overlapping solar semantics.

    Reserves combine by maximum, grid caps by minimum, and prohibitions by union.
    An identical repeated solar factor applies once, not multiplicatively.
    """
    if not all(isinstance(directive, Directive) for directive in directives):
        raise DirectiveValidationError("invalid_directives")
    directives = validate_directives(
        scenario,
        {"directive_interpretation": [directive.model_dump() for directive in directives]},
    )
    battery = scenario.battery
    factors: list[float | None] = [None] * 24
    reserves = [battery.minimum_energy_kwh] * 24
    caps: list[float | None] = [None] * 24
    charge_limits = [battery.max_charge_kwh_per_hour] * 24
    discharge_limits = [battery.max_discharge_kwh_per_hour] * 24
    for directive in directives:
        adjustment = directive.structured_adjustment
        if adjustment is None:
            continue
        for hour in adjustment.hours:
            if isinstance(adjustment, SolarReductionAdjustment):
                existing = factors[hour]
                if existing is not None and existing != adjustment.factor:
                    raise DirectiveValidationError("ambiguous_solar_overlap")
                factors[hour] = adjustment.factor
            elif isinstance(adjustment, MinimumBatteryReserveAdjustment):
                reserves[hour] = max(reserves[hour], adjustment.minimum_energy_kwh)
            elif isinstance(adjustment, MaxGridAdjustment):
                caps[hour] = (
                    adjustment.max_grid_kwh
                    if caps[hour] is None
                    else min(caps[hour], adjustment.max_grid_kwh)
                )
            elif directive.directive_type == "no_charge_window":
                charge_limits[hour] = 0.0
            elif directive.directive_type == "no_discharge_window":
                discharge_limits[hour] = 0.0

    return [
        HourBounds(
            hour=item.hour,
            effective_solar_kwh=item.solar_kwh
            * (1.0 if factors[item.hour] is None else factors[item.hour]),
            minimum_energy_kwh=reserves[item.hour],
            max_grid_kwh=caps[item.hour],
            max_charge_kwh=charge_limits[item.hour],
            max_discharge_kwh=discharge_limits[item.hour],
        )
        for item in scenario.hours
    ]
