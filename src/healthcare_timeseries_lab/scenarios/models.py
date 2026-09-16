from dataclasses import dataclass
from enum import StrEnum


class ConditionPhase(StrEnum):
    BASELINE = "BASELINE"
    ONSET = "ONSET"
    PROGRESSION = "PROGRESSION"
    PLATEAU = "PLATEAU"
    INTERVENTION = "INTERVENTION"
    RECOVERY = "RECOVERY"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class PhysiologicalEffect:
    heart_rate_delta_bpm: float = 0.0
    spo2_delta_pct: float = 0.0
    respiration_rate_delta_bpm: float = 0.0
    temperature_delta_c: float = 0.0
    systolic_bp_delta_mmhg: float = 0.0
    diastolic_bp_delta_mmhg: float = 0.0


@dataclass(frozen=True)
class ActiveCondition:
    name: str
    phase: ConditionPhase
    severity: float
    effect: PhysiologicalEffect

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("condition name must not be empty")

        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be between 0.0 and 1.0")