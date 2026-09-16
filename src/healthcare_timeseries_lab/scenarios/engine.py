from dataclasses import dataclass
from datetime import datetime, timedelta

from healthcare_timeseries_lab.scenarios.models import (
    ActiveCondition,
    ConditionPhase,
    PhysiologicalEffect,
)


@dataclass(frozen=True)
class ScenarioPhaseDefinition:
    phase: ConditionPhase
    start_offset: timedelta
    end_offset: timedelta
    start_severity: float
    end_severity: float

    def __post_init__(self) -> None:
        if self.start_offset < timedelta(0):
            raise ValueError("start_offset must not be negative")

        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")

        if not 0.0 <= self.start_severity <= 1.0:
            raise ValueError("start_severity must be between 0.0 and 1.0")

        if not 0.0 <= self.end_severity <= 1.0:
            raise ValueError("end_severity must be between 0.0 and 1.0")


@dataclass(frozen=True)
class ConditionDefinition:
    name: str
    effect: PhysiologicalEffect
    phases: tuple[ScenarioPhaseDefinition, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("condition name must not be empty")

        if not self.phases:
            raise ValueError("condition must contain at least one phase")

        previous_end: timedelta | None = None

        for phase in self.phases:
            if previous_end is not None and phase.start_offset < previous_end:
                raise ValueError("condition phases must not overlap")

            previous_end = phase.end_offset


class ScenarioEngine:
    def __init__(
        self,
        *,
        simulation_start_time: datetime,
        conditions: tuple[ConditionDefinition, ...],
    ) -> None:
        if simulation_start_time.tzinfo is None:
            raise ValueError("simulation_start_time must be timezone-aware")

        self._simulation_start_time = simulation_start_time
        self._conditions = conditions

    def active_conditions(
        self,
        timestamp: datetime,
    ) -> list[ActiveCondition]:
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        elapsed = timestamp - self._simulation_start_time

        if elapsed < timedelta(0):
            return []

        active: list[ActiveCondition] = []

        for definition in self._conditions:
            phase = self._find_phase(
                definition=definition,
                elapsed=elapsed,
            )

            if phase is None:
                continue

            severity = self._interpolate_severity(
                phase=phase,
                elapsed=elapsed,
            )

            active.append(
                ActiveCondition(
                    name=definition.name,
                    phase=phase.phase,
                    severity=severity,
                    effect=definition.effect,
                )
            )

        return active

    @staticmethod
    def _find_phase(
        *,
        definition: ConditionDefinition,
        elapsed: timedelta,
    ) -> ScenarioPhaseDefinition | None:
        for phase in definition.phases:
            if phase.start_offset <= elapsed < phase.end_offset:
                return phase

        return None

    @staticmethod
    def _interpolate_severity(
        *,
        phase: ScenarioPhaseDefinition,
        elapsed: timedelta,
    ) -> float:
        phase_duration = phase.end_offset - phase.start_offset
        phase_elapsed = elapsed - phase.start_offset

        progress = (
            phase_elapsed.total_seconds()
            / phase_duration.total_seconds()
        )

        return (
            phase.start_severity
            + (
                phase.end_severity
                - phase.start_severity
            )
            * progress
        )