"""Exact GridWise JSON contracts and deterministic structural validation.

Request metadata is ignored; model interpretations and successful responses are
closed contracts. Numerical JSON values are never coerced from strings or bools.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


def _finite_number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("A finite JSON number is required.")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValueError("A finite JSON number is required.") from None
    if not math.isfinite(number):
        raise ValueError("A finite JSON number is required.")
    return number


NonNegativeNumber = Annotated[float, BeforeValidator(_finite_number), Field(ge=0)]
SolarFactor = Annotated[float, BeforeValidator(_finite_number), Field(ge=0, le=1)]
HourIndex = Annotated[StrictInt, Field(ge=0, le=23)]
NoteIndex = Annotated[StrictInt, Field(ge=0, le=2)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HourInput(RequestModel):
    hour: HourIndex
    demand_kwh: NonNegativeNumber
    solar_kwh: NonNegativeNumber
    tariff_bdt_per_kwh: NonNegativeNumber


class Battery(RequestModel):
    capacity_kwh: NonNegativeNumber
    initial_energy_kwh: NonNegativeNumber
    minimum_energy_kwh: NonNegativeNumber
    max_charge_kwh_per_hour: NonNegativeNumber
    max_discharge_kwh_per_hour: NonNegativeNumber

    @model_validator(mode="after")
    def check_energy_order(self) -> Self:
        if not (self.minimum_energy_kwh <= self.initial_energy_kwh <= self.capacity_kwh):
            raise ValueError("Battery energy must satisfy minimum <= initial <= capacity.")
        return self


class ScenarioRequest(RequestModel):
    scenario_id: StrictStr
    operator_notes: Annotated[list[StrictStr], Field(min_length=1, max_length=3)]
    hours: Annotated[list[HourInput], Field(min_length=24, max_length=24)]
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def check_notes(cls, notes: list[str]) -> list[str]:
        if any(not note.strip() for note in notes):
            raise ValueError("Operator notes must be non-empty strings.")
        return notes

    @field_validator("hours")
    @classmethod
    def check_and_order_hours(cls, hours: list[HourInput]) -> list[HourInput]:
        if {item.hour for item in hours} != set(range(24)):
            raise ValueError("Request hours must contain every integer from 0 through 23 once.")
        return sorted(hours, key=lambda item: item.hour)


class WindowAdjustment(ContractModel):
    # The source contract does not specify a minimum array length. Do not add one.
    hours: list[HourIndex]

    @field_validator("hours")
    @classmethod
    def check_ordered_unique_hours(cls, hours: list[int]) -> list[int]:
        if hours != sorted(set(hours)):
            raise ValueError("Directive hours must be unique and in ascending order.")
        return hours


class SolarReductionAdjustment(WindowAdjustment):
    factor: SolarFactor


class MinimumBatteryReserveAdjustment(WindowAdjustment):
    minimum_energy_kwh: NonNegativeNumber


class MaxGridAdjustment(WindowAdjustment):
    max_grid_kwh: NonNegativeNumber


Adjustment = (
    SolarReductionAdjustment
    | MinimumBatteryReserveAdjustment
    | MaxGridAdjustment
    | WindowAdjustment
)
DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]


class Directive(ContractModel):
    note_index: NoteIndex
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Adjustment | None
    explanation: StrictStr

    @model_validator(mode="after")
    def check_type_and_adjustment(self) -> Self:
        if self.directive_type == "no_op":
            if self.applies or self.structured_adjustment is not None:
                raise ValueError("no_op requires applies=false and a null adjustment.")
            return self
        expected_types = {
            "solar_reduction": SolarReductionAdjustment,
            "minimum_battery_reserve": MinimumBatteryReserveAdjustment,
            "no_charge_window": WindowAdjustment,
            "no_discharge_window": WindowAdjustment,
            "max_grid_window": MaxGridAdjustment,
        }
        # Exact type matters: a factor/cap/reserve is not a plain window shape.
        if (
            not self.applies
            or type(self.structured_adjustment) is not expected_types[self.directive_type]
        ):
            raise ValueError(
                "An active directive requires applies=true and its exact adjustment shape."
            )
        return self


def _check_directive_order(directives: list[Directive]) -> list[Directive]:
    if [item.note_index for item in directives] != list(range(len(directives))):
        raise ValueError("Directive entries must be in consecutive note_index order.")
    return directives


class DirectiveEnvelope(ContractModel):
    directive_interpretation: Annotated[list[Directive], Field(min_length=1, max_length=3)]

    @field_validator("directive_interpretation")
    @classmethod
    def check_directive_order(cls, directives: list[Directive]) -> list[Directive]:
        return _check_directive_order(directives)


class HourPlan(ContractModel):
    hour: HourIndex
    grid_kwh: NonNegativeNumber
    solar_used_kwh: NonNegativeNumber
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: NonNegativeNumber
    battery_energy_after_kwh: NonNegativeNumber

    @model_validator(mode="after")
    def check_idle_magnitude(self) -> Self:
        if self.battery_action == "idle" and self.battery_kwh != 0:
            raise ValueError("An idle battery action must have zero magnitude.")
        return self


class OptimizationResponse(ContractModel):
    scenario_id: StrictStr
    directive_interpretation: Annotated[list[Directive], Field(min_length=1, max_length=3)]
    hourly_plan: Annotated[list[HourPlan], Field(min_length=24, max_length=24)]
    total_grid_kwh: NonNegativeNumber
    total_cost_bdt: NonNegativeNumber
    peak_grid_kwh: NonNegativeNumber
    plan_summary: StrictStr

    @field_validator("directive_interpretation")
    @classmethod
    def check_directive_order(cls, directives: list[Directive]) -> list[Directive]:
        return _check_directive_order(directives)

    @field_validator("hourly_plan")
    @classmethod
    def check_plan_order(cls, plan: list[HourPlan]) -> list[HourPlan]:
        if [item.hour for item in plan] != list(range(24)):
            raise ValueError("Plan entries must be in exact chronological order from 0 through 23.")
        return plan
