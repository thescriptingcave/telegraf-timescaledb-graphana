"""Ward registry: the single source of truth for the synthetic ward.

Holds every patient, their admission window, scenario conditions, device
profile, and the deterministic identifier scheme used across the backfill,
the live stream, and the SQL lessons.

Nothing here is real patient data. Every row in the lab descends from
``PatientProfile`` baselines + scenario condition effects, driven by seeded
RNG streams (see ``docs/synthetic_data.md``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from healthcare_timeseries_lab.device import default_bedside_monitor_config
from healthcare_timeseries_lab.device.models import DeviceSimulationConfig
from healthcare_timeseries_lab.patients.models import PatientProfile
from healthcare_timeseries_lab.scenarios.engine import (
    ConditionDefinition,
    ScenarioPhaseDefinition,
)
from healthcare_timeseries_lab.scenarios.models import (
    ConditionPhase,
    PhysiologicalEffect,
)

# ---------------------------------------------------------------------------
# Deterministic identifier namespace
# ---------------------------------------------------------------------------

ROOT_NS = uuid5(
    uuid5(UUID("00000000-0000-0000-0000-000000000001"), "telegraf-timescaledb-lab"),
    "ward",
)
EVENT_NS = uuid5(ROOT_NS, "events")
TRUTH_NS = uuid5(ROOT_NS, "truth")

# The backfilled ward timeline: Jan 1 00:00 -> Jan 31 00:00 (UTC), 2026.
BACKFILL_START = datetime(2026, 1, 1, tzinfo=UTC)
BACKFILL_END = datetime(2026, 1, 31, tzinfo=UTC)

NOMINAL_TICK = timedelta(seconds=10)


def patient_id_for(mrn: str) -> UUID:
    return uuid5(ROOT_NS, f"patient:{mrn}")


def device_id_for(mrn: str) -> UUID:
    return uuid5(ROOT_NS, f"device:{mrn}")


def simulation_id_for(mrn: str) -> UUID:
    return uuid5(ROOT_NS, f"simulation:{mrn}:2026-01")


def event_id_for(simulation_id: UUID, sequence_number: int) -> UUID:
    return uuid5(EVENT_NS, f"{simulation_id}:{sequence_number}")


def truth_id_for(simulation_id: UUID, sequence_number: int) -> UUID:
    return uuid5(TRUTH_NS, f"{simulation_id}:{sequence_number}")


# ---------------------------------------------------------------------------
# Channel metadata (used to build the long-format `readings` table)
# ---------------------------------------------------------------------------

CHANNEL_UNITS: dict[str, str] = {
    "heart_rate_bpm": "bpm",
    "spo2_pct": "%",
    "respiration_rate_bpm": "bpm",
    "temperature_c": "°C",
    "systolic_bp_mmhg": "mmHg",
    "diastolic_bp_mmhg": "mmHg",
}

CHANNEL_LABELS: dict[str, str] = {
    "heart_rate_bpm": "Heart rate",
    "spo2_pct": "SpO2",
    "respiration_rate_bpm": "Respiration rate",
    "temperature_c": "Temperature",
    "systolic_bp_mmhg": "Systolic BP",
    "diastolic_bp_mmhg": "Diastolic BP",
}

# ---------------------------------------------------------------------------
# Scenario condition builders (30-day shelf lives, plus short-stay variants)
# ---------------------------------------------------------------------------


def _phase(
    start: float,
    end: float,
    severity_start: float,
    severity_end: float | None = None,
    phase: ConditionPhase | None = None,
) -> ScenarioPhaseDefinition:
    if severity_end is None:
        severity_end = severity_start
    phase = phase or ConditionPhase.BASELINE
    return ScenarioPhaseDefinition(
        phase=phase,
        start_offset=timedelta(hours=start),
        end_offset=timedelta(hours=end),
        start_severity=severity_start,
        end_severity=severity_end,
    )


def progressive_hypoxemia_long() -> tuple[ConditionDefinition, ...]:
    """Naomi: a 30-day hypoxemia arc with a late recovery (days 20-22)."""
    return (
        ConditionDefinition(
            name="hypoxemia",
            effect=PhysiologicalEffect(spo2_delta_pct=-10.0),
            phases=(
                _phase(0.0, 6.0, 0.0, 0.3, ConditionPhase.ONSET),
                _phase(6.0, 48.0, 0.3, 1.0, ConditionPhase.PROGRESSION),
                _phase(48.0, 480.0, 1.0, 1.0, ConditionPhase.PLATEAU),
                _phase(480.0, 528.0, 1.0, 0.0, ConditionPhase.RECOVERY),
            ),
        ),
    )


def tachycardia_long() -> tuple[ConditionDefinition, ...]:
    """Cole: persistent tachycardia that only partially resolves."""
    return (
        ConditionDefinition(
            name="tachycardia",
            effect=PhysiologicalEffect(heart_rate_delta_bpm=40.0),
            phases=(
                _phase(0.0, 6.0, 0.0, 0.2, ConditionPhase.ONSET),
                _phase(6.0, 72.0, 0.2, 1.0, ConditionPhase.PROGRESSION),
                _phase(72.0, 576.0, 1.0, 1.0, ConditionPhase.PLATEAU),
                _phase(576.0, 624.0, 1.0, 0.5, ConditionPhase.RECOVERY),
            ),
        ),
    )


def late_hypoxemia() -> tuple[ConditionDefinition, ...]:
    """Marcus: a short stay that turns hypoxemic from day ~3."""
    return (
        ConditionDefinition(
            name="hypoxemia",
            effect=PhysiologicalEffect(spo2_delta_pct=-8.0),
            phases=(
                _phase(60.0, 66.0, 0.0, 0.4, ConditionPhase.ONSET),
                _phase(66.0, 78.0, 0.4, 1.0, ConditionPhase.PROGRESSION),
                _phase(78.0, 96.0, 1.0, 1.0, ConditionPhase.PLATEAU),
                _phase(96.0, 108.0, 1.0, 0.0, ConditionPhase.RECOVERY),
            ),
        ),
    )


def hypertensive_episode() -> tuple[ConditionDefinition, ...]:
    """Fatima: a hypertensive episode mid-stay."""
    return (
        ConditionDefinition(
            name="hypertension",
            effect=PhysiologicalEffect(
                systolic_bp_delta_mmhg=45.0,
                diastolic_bp_delta_mmhg=25.0,
            ),
            phases=(
                _phase(60.0, 66.0, 0.0, 0.3, ConditionPhase.ONSET),
                _phase(66.0, 80.0, 0.3, 1.0, ConditionPhase.PROGRESSION),
                _phase(80.0, 120.0, 1.0, 1.0, ConditionPhase.PLATEAU),
                _phase(120.0, 140.0, 1.0, 0.0, ConditionPhase.RECOVERY),
            ),
        ),
    )


def postop_desaturation() -> tuple[ConditionDefinition, ...]:
    """Diego: a transient post-op desaturation plus a low-grade fever."""
    return (
        ConditionDefinition(
            name="desaturation",
            effect=PhysiologicalEffect(spo2_delta_pct=-9.0),
            phases=(
                _phase(40.0, 46.0, 0.0, 0.5, ConditionPhase.ONSET),
                _phase(46.0, 50.0, 0.5, 1.0, ConditionPhase.PROGRESSION),
                _phase(50.0, 54.0, 1.0, 1.0, ConditionPhase.PLATEAU),
                _phase(54.0, 60.0, 1.0, 0.0, ConditionPhase.RECOVERY),
            ),
        ),
        ConditionDefinition(
            name="fever",
            effect=PhysiologicalEffect(temperature_delta_c=1.5),
            phases=(
                _phase(20.0, 26.0, 0.0, 0.6, ConditionPhase.ONSET),
                _phase(26.0, 78.0, 0.6, 0.6, ConditionPhase.PLATEAU),
                _phase(78.0, 84.0, 0.6, 0.0, ConditionPhase.RECOVERY),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Patient roster
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatientAdmission:
    mrn: str
    display_name: str
    sex: str
    age: int
    scenario_label: str
    baseline: PatientProfile
    admitted_at: datetime
    discharged_at: datetime
    conditions: tuple[ConditionDefinition, ...]
    floor: str
    room: str

    @property
    def patient_id(self) -> UUID:
        return patient_id_for(self.mrn)

    @property
    def device_id(self) -> UUID:
        return device_id_for(self.mrn)

    @property
    def simulation_id(self) -> UUID:
        return simulation_id_for(self.mrn)

    @property
    def seed(self) -> int:
        return int(self.patient_id.int % (2**31))

    def bedside_config(self) -> DeviceSimulationConfig:
        return replace(default_bedside_monitor_config(), seed=self.seed)

    def backfill_ticks(self) -> int:
        duration = self.discharged_at - self.admitted_at
        return int(duration.total_seconds() / NOMINAL_TICK.total_seconds())

    def profile_at(self, timestamp: datetime) -> PatientProfile:
        """Circadian-modulated profile: HR/RR breathe with the clock-of-day."""
        hour = timestamp.hour
        factor = 1.0 + 0.04 * math.cos(2 * math.pi * (hour - 9) / 24)
        return replace(
            self.baseline,
            baseline_heart_rate_bpm=self.baseline.baseline_heart_rate_bpm * factor,
            baseline_respiration_rate_bpm=self.baseline.baseline_respiration_rate_bpm * factor,
        )


def _profile(patient_id: UUID, age: int, sex: str, hr: float, spo2: float, rr: float, temp: float, sys: float, dia: float) -> PatientProfile:
    return PatientProfile(
        patient_id=patient_id,
        age=age,
        sex=sex,
        baseline_heart_rate_bpm=hr,
        baseline_spo2_pct=spo2,
        baseline_respiration_rate_bpm=rr,
        baseline_temperature_c=temp,
        baseline_systolic_bp_mmhg=sys,
        baseline_diastolic_bp_mmhg=dia,
    )


WARD_ADMISSIONS: tuple[PatientAdmission, ...] = (
    PatientAdmission(
        mrn="W10001",
        display_name="Naomi Nunez",
        sex="F",
        age=52,
        scenario_label="progressive_hypoxemia",
        baseline=_profile(patient_id_for("W10001"), 52, "F", 72, 97, 14, 36.8, 118, 74),
        admitted_at=BACKFILL_START,
        discharged_at=BACKFILL_END,
        conditions=progressive_hypoxemia_long(),
        floor="2",
        room="204",
    ),
    PatientAdmission(
        mrn="W10002",
        display_name="Cole Bennett",
        sex="M",
        age=68,
        scenario_label="tachycardia",
        baseline=_profile(patient_id_for("W10002"), 68, "M", 76, 96, 15, 37.0, 128, 78),
        admitted_at=BACKFILL_START,
        discharged_at=BACKFILL_END,
        conditions=tachycardia_long(),
        floor="2",
        room="207",
    ),
    PatientAdmission(
        mrn="W10003",
        display_name="Ivy Park",
        sex="F",
        age=47,
        scenario_label="stable",
        baseline=_profile(patient_id_for("W10003"), 47, "F", 68, 98, 13, 36.6, 110, 70),
        admitted_at=BACKFILL_START,
        discharged_at=BACKFILL_END,
        conditions=(),
        floor="3",
        room="312",
    ),
    PatientAdmission(
        mrn="W10004",
        display_name="Marcus Reed",
        sex="M",
        age=61,
        scenario_label="late_hypoxemia",
        baseline=_profile(patient_id_for("W10004"), 61, "M", 74, 96, 14, 36.7, 122, 76),
        admitted_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
        discharged_at=datetime(2026, 1, 8, 12, 0, tzinfo=UTC),
        conditions=late_hypoxemia(),
        floor="2",
        room="210",
    ),
    PatientAdmission(
        mrn="W10005",
        display_name="Fatima Al-Rashid",
        sex="F",
        age=83,
        scenario_label="hypertensive_episode",
        baseline=_profile(patient_id_for("W10005"), 83, "F", 70, 95, 15, 36.9, 142, 82),
        admitted_at=datetime(2026, 1, 12, 14, 0, tzinfo=UTC),
        discharged_at=datetime(2026, 1, 20, 8, 0, tzinfo=UTC),
        conditions=hypertensive_episode(),
        floor="4",
        room="401",
    ),
    PatientAdmission(
        mrn="W10006",
        display_name="Diego Ramirez",
        sex="M",
        age=29,
        scenario_label="postop_desaturation",
        baseline=_profile(patient_id_for("W10006"), 29, "M", 72, 97, 14, 36.8, 118, 76),
        admitted_at=datetime(2026, 1, 22, 10, 0, tzinfo=UTC),
        discharged_at=datetime(2026, 1, 28, 16, 0, tzinfo=UTC),
        conditions=postop_desaturation(),
        floor="4",
        room="412",
    ),
)


def admission_for(mrn: str) -> PatientAdmission:
    for admission in WARD_ADMISSIONS:
        if admission.mrn == mrn:
            return admission
    raise KeyError(f"unknown MRN {mrn!r}")


# ---------------------------------------------------------------------------
# Ward sampling policy (shared by backfill and live stream)
# ---------------------------------------------------------------------------

# Daily off-monitor windows (UTC): handover/transport — no events emitted.
_OFF_MONITOR_DAILY: tuple[tuple[int, int, int, int], ...] = (
    (6, 0, 6, 45),
    (18, 30, 19, 15),
)

LIVE_SCENARIO_START = BACKFILL_END


def in_off_monitor_window(timestamp: datetime) -> bool:
    minutes = timestamp.hour * 60 + timestamp.minute
    return any(
        (sh * 60 + sm) <= minutes < (eh * 60 + em)
        for (sh, sm, eh, em) in _OFF_MONITOR_DAILY
    )


def __all__():
    pass