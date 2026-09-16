from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PatientProfile:
    patient_id: UUID
    age: int
    sex: str

    baseline_heart_rate_bpm: float
    baseline_spo2_pct: float
    baseline_respiration_rate_bpm: float
    baseline_temperature_c: float
    baseline_systolic_bp_mmhg: float
    baseline_diastolic_bp_mmhg: float

    variability_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.age <= 0:
            raise ValueError("age must be greater than zero")

        if not self.sex.strip():
            raise ValueError("sex must not be empty")

        if self.baseline_heart_rate_bpm <= 0:
            raise ValueError("baseline heart rate must be greater than zero")

        if not 0 < self.baseline_spo2_pct <= 100:
            raise ValueError("baseline SpO2 must be between 0 and 100")

        if self.baseline_respiration_rate_bpm <= 0:
            raise ValueError("baseline respiration rate must be greater than zero")

        if self.baseline_temperature_c <= 0:
            raise ValueError("baseline temperature must be greater than zero")

        if self.baseline_systolic_bp_mmhg <= 0:
            raise ValueError("baseline systolic blood pressure must be greater than zero")

        if self.baseline_diastolic_bp_mmhg <= 0:
            raise ValueError("baseline diastolic blood pressure must be greater than zero")

        if self.baseline_systolic_bp_mmhg <= self.baseline_diastolic_bp_mmhg:
            raise ValueError(
                "baseline systolic blood pressure must be greater than diastolic"
            )

        if self.variability_factor <= 0:
            raise ValueError("variability_factor must be greater than zero")