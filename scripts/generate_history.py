"""Backfill the 30-day ward dataset into TimescaleDB.

Runs the full physiology + device + scenario engine in-process for every
admission window (Jan 1-30, 2026), applies the ward sampling policy (10 s
nominal ticks, seeded irregular skips, daily off-monitor windows, circadian
modulation), then bulk-loads:

  - vitals       observed telemetry (VitalsTelemetryEvent)
  - vitals_truth pre-device true physiology (one row per tick)
  - readings     long-format channel rows for both sources
  - patients / encounters dimension rows (upserted)

On-conflict clauses make the load idempotent: given the same seeded inputs,
re-running produces the identical event_ids and is a no-op. After the load the
vitals_hourly continuous aggregate is refreshed in full.

Usage: uv run python scripts/generate_history.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from healthcare_timeseries_lab.device.simulator import DeviceSimulator
from healthcare_timeseries_lab.physiology.engine import PhysiologyEngine
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from healthcare_timeseries_lab.scenarios.engine import ScenarioEngine
from healthcare_timeseries_lab.telemetry.events import VitalsTelemetryEvent
from scripts.ward_registry import (
    CHANNEL_UNITS,
    LIVE_SCENARIO_START,
    NOMINAL_TICK,
    WARD_ADMISSIONS,
    PatientAdmission,
    event_id_for,
    in_off_monitor_window,
    truth_id_for,
)

ROOT = Path(__file__).resolve().parent.parent

LOOP_SKIP_PROBABILITY = 0.10
_BATCH_SIZE = 40_000
_LOOP_SKIP_XOR = 0x5F3759DF

VITALS_COLUMNS = (
    "event_id, time, patient_id, mrn, device_id, sequence_number, scenario, "
    "quality_code, device_status, heart_rate_bpm, spo2_pct, "
    "respiration_rate_bpm, temperature_c, systolic_bp_mmhg, diastolic_bp_mmhg"
)
TRUTH_COLUMNS = (
    "event_id, time, patient_id, mrn, sequence_number, scenario, "
    "heart_rate_bpm, spo2_pct, respiration_rate_bpm, temperature_c, "
    "systolic_bp_mmhg, diastolic_bp_mmhg"
)
READINGS_COLUMNS = (
    "time, patient_id, mrn, sequence_number, channel, unit, value, source, "
    "quality_code"
)


def _space_for(admission: PatientAdmission) -> str:
    return "  " * len(admission.display_name)


def initial_state(admission: PatientAdmission) -> PhysiologicalState:
    base = admission.baseline
    return PhysiologicalState(
        timestamp=admission.admitted_at - NOMINAL_TICK,
        heart_rate_bpm=base.baseline_heart_rate_bpm,
        spo2_pct=base.baseline_spo2_pct,
        respiration_rate_bpm=base.baseline_respiration_rate_bpm,
        temperature_c=base.baseline_temperature_c,
        systolic_bp_mmhg=base.baseline_systolic_bp_mmhg,
        diastolic_bp_mmhg=base.baseline_diastolic_bp_mmhg,
    )


def simulate_admission(
    admission: PatientAdmission,
    *,
    extra_seed: int = 0,
) -> Iterator[tuple[object | None, tuple, list[tuple]]]:
    """Yield one (vitals_row | None, truth_row, readings_rows) per tick."""
    seed = admission.seed ^ extra_seed

    engine = PhysiologyEngine(random.Random(seed))
    device = DeviceSimulator(
        config=admission.bedside_config(),
        rng=random.Random(seed),
    )
    scenario = ScenarioEngine(
        simulation_start_time=admission.admitted_at,
        conditions=admission.conditions,
    )
    loop_rng = random.Random(seed ^ _LOOP_SKIP_XOR)

    simulation_id = admission.simulation_id
    patient_id = admission.patient_id
    device_id = admission.device_id
    mrn = admission.mrn
    label = admission.scenario_label

    previous = initial_state(admission)
    maximum = admission.backfill_ticks()
    _trace = os.getenv("GH_TRACE") == "1"

    for sequence in range(1, maximum + 1):
        timestamp = admission.admitted_at + sequence * NOMINAL_TICK
        if _trace and sequence % 10_000 == 0:
            print(
                f"[trace] {admission.mrn} seq={sequence:>7,} "
                f"elapsed={time.perf_counter():.1f}",
                flush=True,
            )

        previous = engine.next_state(
            patient=admission.profile_at(timestamp),
            previous_state=previous,
            timestamp=timestamp,
            active_conditions=scenario.active_conditions(timestamp),
        )

        truth = (
            truth_id_for(simulation_id, sequence),
            timestamp,
            patient_id,
            mrn,
            sequence,
            label,
            previous.heart_rate_bpm,
            previous.spo2_pct,
            previous.respiration_rate_bpm,
            previous.temperature_c,
            previous.systolic_bp_mmhg,
            previous.diastolic_bp_mmhg,
        )

        reads: list[tuple] = []
        for channel in CHANNEL_UNITS:
            reads.append(
                (
                    timestamp,
                    patient_id,
                    mrn,
                    sequence,
                    channel,
                    CHANNEL_UNITS[channel],
                    getattr(previous, channel),
                    "truth",
                    "TRUTH",
                )
            )

        event: VitalsTelemetryEvent | None = None
        if not in_off_monitor_window(timestamp) and loop_rng.random() >= LOOP_SKIP_PROBABILITY:
            event = device.observe(
                state=previous,
                simulation_id=simulation_id,
                patient_id=patient_id,
                device_id=device_id,
                sequence_number=sequence,
                event_id=event_id_for(simulation_id, sequence),
            )

        vitals_row: tuple | None = None
        if event is not None:
            vitals_row = (
                event.event_id,
                event.event_time,
                event.patient_id,
                mrn,
                event.device_id,
                event.sequence_number,
                label,
                event.quality_code,
                event.device_status,
                event.heart_rate_bpm,
                event.spo2_pct,
                event.respiration_rate_bpm,
                event.temperature_c,
                event.systolic_bp_mmhg,
                event.diastolic_bp_mmhg,
            )
            for channel in CHANNEL_UNITS:
                reads.append(
                    (
                        event.event_time,
                        patient_id,
                        mrn,
                        event.sequence_number,
                        channel,
                        CHANNEL_UNITS[channel],
                        getattr(event, channel),
                        "observed",
                        event.quality_code,
                    )
                )

        yield vitals_row, truth, reads

        if sequence % max(1, maximum // 20) == 0:
            sys.stdout.write(_space_for(admission))
            sys.stdout.write(f"\r  {mrn} {sequence:>7,}/{maximum:,} ticks")
            sys.stdout.flush()
        del event, reads


def _copy_rows(cur: psycopg.Cursor, table: str, columns: str, rows: list[tuple]) -> None:
    if not rows:
        return
    # Text-format COPY: binary COPY in psycopg3 dumps Python ints as int4,
    # which corrupts int8 columns such as sequence_number.
    sql = f"COPY {table} ({columns}) FROM STDIN"
    with cur.copy(sql) as copy:
        for row in rows:
            copy.write_row(row)


def _flush_buffers(
    conn: psycopg.Connection,
    buf_v: list[tuple],
    buf_t: list[tuple],
    buf_r: list[tuple],
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        _copy_rows(cur, "_stag_vitals", VITALS_COLUMNS, buf_v)
        _copy_rows(cur, "_stag_truth", TRUTH_COLUMNS, buf_t)
        _copy_rows(cur, "_stag_readings", READINGS_COLUMNS, buf_r)
        cur.execute(
            "INSERT INTO vitals SELECT * FROM _stag_vitals "
            "ON CONFLICT (time, event_id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO vitals_truth SELECT * FROM _stag_truth "
            "ON CONFLICT (time, event_id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO readings (time, patient_id, mrn, sequence_number, "
            "channel, unit, value, source, quality_code) "
            "SELECT time, patient_id, mrn, sequence_number, channel, unit, "
            "value, source, quality_code FROM _stag_readings "
            "ON CONFLICT (time, patient_id, channel, sequence_number) "
            "DO NOTHING"
        )
        cur.execute("TRUNCATE _stag_vitals, _stag_truth, _stag_readings")


def ingest_admissions(conn: psycopg.Connection) -> dict[str, int]:
    # Create staging tables once per session. ON COMMIT PRESERVE ROWS keeps
    # them alive across the short per-flush transactions.
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _stag_vitals (LIKE vitals) ON COMMIT PRESERVE ROWS")
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _stag_truth (LIKE vitals_truth) ON COMMIT PRESERVE ROWS")
        cur.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _stag_readings ("
            "time TIMESTAMPTZ, patient_id UUID, mrn TEXT, "
            "sequence_number BIGINT, channel TEXT, unit TEXT, "
            "value DOUBLE PRECISION, source TEXT, quality_code TEXT) "
            "ON COMMIT PRESERVE ROWS"
        )

    # Pause background cagg/compression policies so they don't contend
    # with the high-volume bulk load.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT job_id, schedule_interval FROM timescaledb_information.jobs "
            "WHERE proc_name IN "
            "('policy_refresh_continuous_aggregate', 'policy_compression')"
        )
        paused_jobs = cur.fetchall()
        for jid, orig_interval in paused_jobs:
            cur.execute("SELECT alter_job(%s, schedule_interval => INTERVAL '100 years')", (jid,))
    try:
        totals = _ingest_body(conn)
    finally:
        with conn.cursor() as cur:
            for jid, orig_interval in paused_jobs:
                cur.execute("SELECT alter_job(%s, schedule_interval => %s)", (jid, orig_interval))

    print("Refreshing vitals_hourly continuous aggregate ...")
    with conn.cursor() as cur:
        cur.execute("CALL refresh_continuous_aggregate('vitals_hourly', NULL, NULL)")

    return totals


def _ingest_body(conn: psycopg.Connection) -> dict[str, int]:
    print("Upserting patients / encounters ...")
    with conn.transaction(), conn.cursor() as cur:
        for admission in WARD_ADMISSIONS:
            cur.execute(
                "INSERT INTO patients (patient_id, mrn, display_name, age, sex, "
                "simulation_id, scenario_label, admitted_at, discharged_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (patient_id) DO NOTHING",
                (
                    admission.patient_id,
                    admission.mrn,
                    admission.display_name,
                    admission.age,
                    admission.sex,
                    admission.simulation_id,
                    admission.scenario_label,
                    admission.admitted_at,
                    admission.discharged_at,
                ),
            )
            cur.execute(
                "INSERT INTO encounters (patient_id, device_id, started_at, "
                "ended_at, floor, room) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (patient_id, started_at) DO NOTHING",
                (
                    admission.patient_id,
                    admission.device_id,
                    admission.admitted_at,
                    admission.discharged_at,
                    admission.floor,
                    admission.room,
                ),
            )

    totals: dict[str, int] = {"vitals": 0, "vitals_truth": 0, "readings": 0}

    for admission in WARD_ADMISSIONS:
        print(f"\n{admission.display_name} ({admission.mrn}, {admission.scenario_label})")
        started = time.perf_counter()

        buf_v: list[tuple] = []
        buf_t: list[tuple] = []
        buf_r: list[tuple] = []

        gen = simulate_admission(admission)
        for vitals_row, truth, reads in gen:
            if vitals_row is not None:
                buf_v.append(vitals_row)
            buf_t.append(truth)
            buf_r.extend(reads)
            if len(buf_t) >= _BATCH_SIZE:
                _flush_buffers(conn, buf_v, buf_t, buf_r)
                buf_v, buf_t, buf_r = [], [], []

        _flush_buffers(conn, buf_v, buf_t, buf_r)

        elapsed = time.perf_counter() - started
        print(f"\n  done in {elapsed:.1f}s (~{admission.backfill_ticks() / elapsed:.0f} ticks/s)")

    totals["vitals"] = _table_rows(conn, "vitals")
    totals["vitals_truth"] = _table_rows(conn, "vitals_truth")
    totals["readings"] = _table_rows(conn, "readings")
    return totals


def _table_rows(conn: psycopg.Connection, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return int(cur.fetchone()[0])


def main() -> int:
    load_dotenv(ROOT / ".env")
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres@localhost:5432/telemetry",
    )

    print("Starting 30-day backfill")
    print(f"  timeline: Jan 1 2026 00:00Z -> Jan 31 2026 00:00Z (live continues at {LIVE_SCENARIO_START:%Y-%m-%d %H:%M}Z)")
    print(f"  patients: {len(WARD_ADMISSIONS)}, nominal tick: {NOMINAL_TICK.total_seconds():.0f}s, skip p={LOOP_SKIP_PROBABILITY}")

    started = time.perf_counter()
    # autocommit keeps the *_stag temp tables session-scoped (not ON COMMIT
    # DROP) so _flush_buffers can use them across many short transactions.
    with psycopg.connect(url, autocommit=True) as conn:
        totals = ingest_admissions(conn)
    elapsed = time.perf_counter() - started

    print("\nLoad complete.")
    print(f"  vitals:       {totals['vitals']:>10,}")
    print(f"  vitals_truth: {totals['vitals_truth']:>10,}")
    print(f"  readings:     {totals['readings']:>10,}")
    print(f"  elapsed:      {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())