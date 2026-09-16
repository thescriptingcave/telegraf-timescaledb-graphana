from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from healthcare_timeseries_lab.physiology.models import PhysiologicalState


@dataclass(frozen=True)
class VitalsTelemetryEvent:
    event_id: UUID
    simulation_id: UUID
    patient_id: UUID
    device_id: UUID

    event_time: datetime
    sequence_number: int

    heart_rate_bpm: float
    spo2_pct: float
    respiration_rate_bpm: float
    temperature_c: float
    systolic_bp_mmhg: float
    diastolic_bp_mmhg: float

    device_status: str = "CONNECTED"
    quality_code: str = "GOOD"

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")

        if self.sequence_number < 1:
            raise ValueError("sequence_number must be greater than zero")

    @classmethod
    def from_physiological_state(
        cls,
        *,
        event_id: UUID,
        simulation_id: UUID,
        patient_id: UUID,
        device_id: UUID,
        sequence_number: int,
        state: PhysiologicalState,
    ) -> "VitalsTelemetryEvent":
        return cls(
            event_id=event_id,
            simulation_id=simulation_id,
            patient_id=patient_id,
            device_id=device_id,
            event_time=state.timestamp,
            sequence_number=sequence_number,
            heart_rate_bpm=state.heart_rate_bpm,
            spo2_pct=state.spo2_pct,
            respiration_rate_bpm=state.respiration_rate_bpm,
            temperature_c=state.temperature_c,
            systolic_bp_mmhg=state.systolic_bp_mmhg,
            diastolic_bp_mmhg=state.diastolic_bp_mmhg,
        )