# Data Model

The lab stores a synthetic ward's vitals telemetry in **TimescaleDB**
(PostgreSQL 17 + the TimescaleDB extension). All DDL lives in
[`sql/ddl/00_init.sql`](../sql/ddl/00_init.sql) and is applied idempotently by
`scripts/init_db.py` or the container's first-boot init scripts.

## Core concepts

- Three **hypertables** (`vitals`, `vitals_truth`, `readings`) partitioned by
  `time` into 1-day chunks.
- Two **dimension tables** (`patients`, `encounters`) for the ward roster.
- One **live view** (`vitals_derived`) computed at query time.
- One **continuous aggregate** (`vitals_hourly`) for stable hourly queries.
- **Compression** enabled on `vitals` and `readings` for chunks older than
  3 days.

## ER overview

```
patients 1 ────► many encounters (admission → device → room window)
patients 1 ────► many vitals       (observed telemetry, hypertable)
patients 1 ────► many vitals_truth (true physiology, hypertable)
patients 1 ────► many readings     (long-format channel rows, hypertable)
```

## Dimension tables

### `patients`

| Column | Type | Notes |
| --- | --- | --- |
| `patient_id` | UUID PK | Deterministic (see below) |
| `mrn` | TEXT UNIQUE | `W10001` … `W10006` |
| `display_name` | TEXT | Synthetic name |
| `age` / `sex` | INT / TEXT | Demographics |
| `simulation_id` | UUID | Identifies the January simulation |
| `scenario_label` | TEXT | e.g. `progressive_hypoxemia` |
| `admitted_at` / `discharged_at` | TIMESTAMPTZ | Admission window |

### `encounters`

| Column | Type | Notes |
| --- | --- | --- |
| `encounter_id` | BIGINT identity PK | Surrogate |
| `patient_id` | UUID FK → patients | ON DELETE CASCADE |
| `device_id` | UUID | Device linked to the visit |
| `started_at` / `ended_at` | TIMESTAMPTZ | Bounded by the admission window |
| `floor` / `room` | TEXT | Location |
| UNIQUE | `(patient_id, started_at)` | One encounter per admission start |

## Hypertables

### `vitals` — observed telemetry

Written by **both** the backfill and the live stream.

| Column | Type | Notes |
| --- | --- | --- |
| `event_id` | UUID | Part of PK; idempotency key |
| `time` | TIMESTAMPTZ | Partition column; part of PK |
| `patient_id` | UUID FK → patients | |
| `mrn` | TEXT | Denormalized for dashboard convenience |
| `device_id` | UUID | |
| `sequence_number` | BIGINT | Monotonic per simulation |
| `scenario` | TEXT | Scenario label |
| `quality_code` | TEXT | `GOOD`/`DEGRADED`/`POOR`/`LOST` |
| `device_status` | TEXT | `CONNECTED`/`DISCONNECTED` |
| 6 vitals columns | DOUBLE PRECISION | See channel table below |

- `PRIMARY KEY (time, event_id)` — TimescaleDB requires the partition column
  in every unique index; the composite PK also makes the
  `ON CONFLICT (time, event_id) DO NOTHING` load idempotent.
- Indexes: `(patient_id, time DESC)`, `(time DESC)`.

### `vitals_truth` — pre-device true physiology

Written only by the **offline backfill** (one row per tick).

Same 6-channel layout plus `event_id`, `time`, `patient_id`, `mrn`,
`sequence_number`, `scenario`; **no** device-layer columns. Composite PK
`(time, event_id)`. Index `(patient_id, time DESC)`.

### `readings` — long format

One row per **channel** per event, for both sources (`source` = `truth` |
`observed`). This is the "clean" form for SQL lessons and channel-level
analysis.

| Column | Type | Notes |
| --- | --- | --- |
| `reading_id` | BIGINT identity | Part of PK |
| `time` | TIMESTAMPTZ | Partition column |
| `patient_id` | UUID FK → patients | |
| `mrn` | TEXT | |
| `sequence_number` | BIGINT | |
| `channel` | TEXT | Channel name |
| `unit` | TEXT | UCUM-ish unit |
| `value` | DOUBLE PRECISION | |
| `source` | TEXT | `truth` or `observed` |
| `quality_code` | TEXT | |
| PK | `(time, reading_id)` | |
| UNIQUE | `(time, patient_id, channel, sequence_number)` | Prevents duplication in both source rows |

Index `(patient_id, channel, time DESC)`.

## Channel catalog

| Channel | Unit | Physiological bounds | Monitor rounding |
| --- | --- | --- | --- |
| `heart_rate_bpm` | bpm | 25–220 | 0 d.p. |
| `spo2_pct` | % | 50–100 | 0 d.p. |
| `respiration_rate_bpm` | bpm | 4–60 | 0 d.p. |
| `temperature_c` | °C | 30–43 | 1 d.p. |
| `systolic_bp_mmhg` | mmHg | 50–240 | 0 d.p. |
| `diastolic_bp_mmhg` | mmHg | 25–150 | 0 d.p. |

Invariant (enforced by `PhysiologicalState` and `PatientProfile`):
`systolic > diastolic`.

## Derived view — `vitals_derived`

A read-only view over `vitals` that adds three real-time derived fields:

| Field | Formula |
| --- | --- |
| `map_mmhg` | `(2·systolic + diastolic) / 3` |
| `pulse_pressure_mmhg` | `systolic − diastolic` |
| `shock_index` | `heart_rate / systolic` |

## Continuous aggregate — `vitals_hourly`

`time_bucket(1 hour)` over `vitals`, grouped by `(patient_id, mrn, scenario)`:

- `n` (count)
- `avg`/`min`/`max` of heart rate
- `avg`/`min` of SpO2
- `avg` of respiration rate, temperature, and both blood pressures

Refresh policy: start offset 3 days back, end offset 1 hour before now, run
hourly. The dashboard's hourly rollup panel reads from it.

## Compression

| Hypertable | Order by | Segment by | Policy |
| --- | --- | --- | --- |
| `vitals` | `time DESC` | `patient_id, scenario` | Compress chunks older than 3 days |
| `readings` | `time DESC` | `patient_id, channel` | (compression enabled, policy shared) |

Compression keeps the January dataset small in the warm store while demo
queries still hit uncompressed recent chunks.

## Deterministic identifiers

All IDs are **UUIDv5**, derived from fixed namespaces in
`scripts/ward_registry.py`:

```
ROOT_NS   = uuid5(uuid5("telegraf-timescaledb-lab"), "ward")
EVENT_NS  = uuid5(ROOT_NS, "events")
TRUTH_NS  = uuid5(ROOT_NS, "truth")

patient_id    = uuid5(ROOT_NS, f"patient:{mrn}")
device_id     = uuid5(ROOT_NS, f"device:{mrn}")
simulation_id = uuid5(ROOT_NS, f"simulation:{mrn}:2026-01")
event_id      = uuid5(EVENT_NS, f"{simulation_id}:{sequence}")
truth_id      = uuid5(TRUTH_NS, f"{simulation_id}:{sequence}")
```

Because every ID is a pure function of stable inputs, backfill, live stream,
and SQL lessons all agree, and rerunning any producer is safe.

## Timeline values (registry)

| Constant | Value |
| --- | --- |
| `BACKFILL_START` | `2026-01-01T00:00Z` |
| `BACKFILL_END` / `LIVE_SCENARIO_START` | `2026-01-31T00:00Z` |
| `NOMINAL_TICK` | 10 s |
| Daily off-monitor windows | 06:00–06:45, 18:30–19:15 UTC |
| Patients | 6 (`W10001`–`W10006`) |

## References

- [Data flow](data_flow.md)
- [Infrastructure](infrastructure.md)
- [`sql/ddl/00_init.sql`](../sql/ddl/00_init.sql)
- [`scripts/ward_registry.py`](../scripts/ward_registry.py)