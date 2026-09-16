"""Live ward vitals producer — the Telegraf exec target.

Invoked by Telegraf's [[inputs.exec]] every 10s. For each patient it:

  1. loads or creates a checkpoint in STREAM_STATE_DIR/<mrn>.json
  2. advances the simulation by exactly one scenario tick
     (SCENARIO_TICK_SECONDS of scenario time per run; default 60s/run -> 6x)
  3. prints one Influx line-protocol line per emitted vitals event (or nothing)
  4. atomically persists the checkpoint

Checkpoints snapshot the full engine/device RNG state, the last true state,
and the oxygen-coupling history, so every run is deterministic and resumable:
re-running the same checkpoint reproduces the identical tick, and Telegraf
retries are idempotent (`event_id` PK + ON CONFLICT DO NOTHING on insert).

The live feed continues the ward timeline right after the 30-day backfill
(i.e. from 2026-01-31T00:00Z onward). Runs only need the Python stdlib plus
the lab source on PYTHONPATH — no database connection.

Census semantics (1.0): the live arm has no admission/discharge lifecycle.
`discharged_at` in the registry bounds the backfill only; the live arm is a
next-day continuation of the same six-patient census, so no patient is ever
"discharged" from the stream and no new patient is admitted at runtime.

Usage (container):  python3 /app/scripts/stream_vitals.py
Debug (host):       uv run python scripts/stream_vitals.py
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from healthcare_timeseries_lab.device.models import VITAL_CHANNELS
from healthcare_timeseries_lab.device.simulator import DeviceSimulator
from healthcare_timeseries_lab.physiology.engine import (
    OxygenDeficitObservation,
    PhysiologyEngine,
)
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from healthcare_timeseries_lab.scenarios.engine import ScenarioEngine
from scripts.ward_registry import (
    LIVE_SCENARIO_START,
    NOMINAL_TICK,
    WARD_ADMISSIONS,
    PatientAdmission,
    event_id_for,
    in_off_monitor_window,
)

STATE_DIR = Path(os.getenv("STREAM_STATE_DIR", "./state"))
SCENARIO_TICK_SECONDS = int(os.getenv("SCENARIO_TICK_SECONDS", "60"))
LOOP_SKIP_PROBABILITY = 0.10
_LOOP_SKIP_XOR = 0x5F3759DF


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _rng_from_state(state: list) -> random.Random:
    """Rebuild a Random from its JSON-serialized getstate() list."""
    rng = random.Random()
    rng.setstate((state[0], tuple(state[1]), state[2]))
    return rng


def initial_checkpoint(admission: PatientAdmission) -> dict:
    """A clean continuation point right after the backfill ends."""
    base = admission.baseline
    previous_time = LIVE_SCENARIO_START - NOMINAL_TICK
    seed = admission.seed

    return {
        "mrn": admission.mrn,
        "scenario_time": _iso(LIVE_SCENARIO_START),
        "sequence_number": admission.backfill_ticks(),
        "previous_time": _iso(previous_time),
        "previous_state": {
            "heart_rate_bpm": base.baseline_heart_rate_bpm,
            "spo2_pct": base.baseline_spo2_pct,
            "respiration_rate_bpm": base.baseline_respiration_rate_bpm,
            "temperature_c": base.baseline_temperature_c,
            "systolic_bp_mmhg": base.baseline_systolic_bp_mmhg,
            "diastolic_bp_mmhg": base.baseline_diastolic_bp_mmhg,
        },
        "engine_rng": list(random.Random(seed).getstate()),
        "loop_rng": list(random.Random(seed ^ _LOOP_SKIP_XOR).getstate()),
        "device_rng": list(random.Random(seed).getstate()),
        "device_start_time": None,
        "device_last_observed": {},
        "device_flatline_anchor": {},
        "oxygen_deficit": [],
    }


def _previous_state(admission: PatientAdmission, cp: dict) -> PhysiologicalState:
    return PhysiologicalState(
        timestamp=_parse(cp["previous_time"]),
        **{channel: cp["previous_state"][channel] for channel in VITAL_CHANNELS},
    )


def _restore_engine(admission: PatientAdmission, cp: dict) -> tuple[PhysiologyEngine, random.Random]:
    rng = _rng_from_state(cp["engine_rng"])
    engine = PhysiologyEngine(rng)
    engine._oxygen_deficit_history = deque(
        OxygenDeficitObservation(_parse(ts), deficit)
        for ts, deficit in cp["oxygen_deficit"]
    )
    return engine, rng


def _restore_device(
    admission: PatientAdmission,
    cp: dict,
) -> tuple[DeviceSimulator, random.Random]:
    rng = _rng_from_state(cp["device_rng"])
    device = DeviceSimulator(config=admission.bedside_config(), rng=rng)
    device._start_time = _parse(cp["device_start_time"]) if cp["device_start_time"] else None
    device._last_observed = dict(cp["device_last_observed"])
    device._flatline_anchor = dict(cp["device_flatline_anchor"])
    return device, rng


def advance(
    admission: PatientAdmission,
    cp: dict,
    *,
    scenario_tick: timedelta,
    skip_probability: float,
) -> tuple[object | None, dict]:
    """Advance one scenario tick; return (VitalsTelemetryEvent | None, new cp)."""
    tick_time = _parse(cp["scenario_time"]) + scenario_tick
    sequence_number = cp["sequence_number"] + 1

    engine, engine_rng = _restore_engine(admission, cp)
    device, device_rng = _restore_device(admission, cp)
    loop_rng = _rng_from_state(cp["loop_rng"])
    scenario = ScenarioEngine(
        simulation_start_time=admission.admitted_at,
        conditions=admission.conditions,
    )

    state = engine.next_state(
        patient=admission.profile_at(tick_time),
        previous_state=_previous_state(admission, cp),
        timestamp=tick_time,
        active_conditions=scenario.active_conditions(tick_time),
    )

    emit = not (
        in_off_monitor_window(tick_time)
        or loop_rng.random() < skip_probability
    )
    event = None
    if emit:
        event = device.observe(
            state=state,
            simulation_id=admission.simulation_id,
            patient_id=admission.patient_id,
            device_id=admission.device_id,
            sequence_number=sequence_number,
            event_id=event_id_for(admission.simulation_id, sequence_number),
        )

    new_cp = {
        "mrn": admission.mrn,
        "scenario_time": _iso(tick_time),
        "sequence_number": sequence_number,
        "previous_time": _iso(tick_time),
        "previous_state": {channel: getattr(state, channel) for channel in VITAL_CHANNELS},
        "engine_rng": list(engine_rng.getstate()),
        "loop_rng": list(loop_rng.getstate()),
        "device_rng": list(device_rng.getstate()),
        "device_start_time": _iso(device._start_time) if device._start_time else None,
        "device_last_observed": dict(device._last_observed),
        "device_flatline_anchor": dict(device._flatline_anchor),
        "oxygen_deficit": [
            [_iso(obs.timestamp), obs.deficit]
            for obs in engine._oxygen_deficit_history
        ],
    }
    return event, new_cp


def _emit_line(event: object, admission: PatientAdmission) -> str:
    tags = {
        "event_id": str(event.event_id),
        "mrn": admission.mrn,
        "patient_id": str(event.patient_id),
        "device_id": str(event.device_id),
        "scenario": admission.scenario_label,
        "quality_code": event.quality_code,
        "device_status": event.device_status,
        "sequence_number": event.sequence_number,
    }

    fields = {
        "heart_rate_bpm": event.heart_rate_bpm,
        "spo2_pct": event.spo2_pct,
        "respiration_rate_bpm": event.respiration_rate_bpm,
        "temperature_c": event.temperature_c,
        "systolic_bp_mmhg": event.systolic_bp_mmhg,
        "diastolic_bp_mmhg": event.diastolic_bp_mmhg,
    }
    tag_part = ",".join(f"{k}={v}" for k, v in tags.items())
    field_part = ",".join(f"{k}={v:g}" for k, v in fields.items())
    timestamp_ns = int(event.event_time.timestamp() * 1_000_000_000)
    return f"vitals,{tag_part} {field_part} {timestamp_ns}"


def advance_and_emit(admission: PatientAdmission, scenario_tick: timedelta) -> str | None:
    state_dir = STATE_DIR
    path = state_dir / f"{admission.mrn}.json"

    state_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        cp = json.loads(path.read_text(encoding="utf-8"))
    else:
        cp = initial_checkpoint(admission)

    event, new_cp = advance(
        admission,
        cp,
        scenario_tick=scenario_tick,
        skip_probability=LOOP_SKIP_PROBABILITY,
    )

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(new_cp, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

    return _emit_line(event, admission) if event is not None else None


def main() -> int:
    scenario_tick = timedelta(seconds=SCENARIO_TICK_SECONDS)
    emitted = 0

    for admission in WARD_ADMISSIONS:
        line = advance_and_emit(admission, scenario_tick)
        if line is not None:
            print(line)
            emitted += 1

    print(f"# emitted={emitted} scenario_tick_s={SCENARIO_TICK_SECONDS:.0f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())