from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PhysiologicalState:
    timestamp: datetime

    heart_rate_bpm: float
    spo2_pct: float
    respiration_rate_bpm: float
    temperature_c: float
    systolic_bp_mmhg: float
    diastolic_bp_mmhg: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        if not 25 <= self.heart_rate_bpm <= 220:
            raise ValueError("heart rate is outside physiological bounds")

        if not 50 <= self.spo2_pct <= 100:
            raise ValueError("SpO2 is outside physiological bounds")

        if not 4 <= self.respiration_rate_bpm <= 60:
            raise ValueError("respiration rate is outside physiological bounds")

        if not 30 <= self.temperature_c <= 43:
            raise ValueError("temperature is outside physiological bounds")

        if not 50 <= self.systolic_bp_mmhg <= 240:
            raise ValueError("systolic blood pressure is outside physiological bounds")

        if not 25 <= self.diastolic_bp_mmhg <= 150:
            raise ValueError("diastolic blood pressure is outside physiological bounds")

        if self.systolic_bp_mmhg <= self.diastolic_bp_mmhg:
            raise ValueError(
                "systolic blood pressure must be greater than diastolic"
            )