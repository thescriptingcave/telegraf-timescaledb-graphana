# Architecture

## Overview

A **synthetic ward vitals lab**: a deterministic physiology/device simulation
feeds a time-series database, a metrics agent streams a live continuation of
the same simulation, and a dashboard visualizes both. It is a learning
environment — all data is synthetic.

```
┌─────────────────────── SIMULATION LIBRARY (Python) ───────────────────────┐
│ src/healthcare_timeseries_lab/                                            │
│   patients/  patient profiles + baselines                                 │
│   physiology/ mean-reversion engine + oxygen coupling + bounds            │
│   scenarios/  condition phases + severity interpolation (library)         │
│   device/     noise, precision, latency, dropout, faults, quality codes   │
│   telemetry/  VitalsTelemetryEvent (observed, Influx-serializable)       │
│   runtime/    SimulationClock                                             │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │
              (10 s ticks; uuid5 identities; registry-driven)
                               │
        ┌──────────────────────┼───────────────────────────┐
        ▼                      ▼                           ▼
  scripts/generate_history  scripts/stream_vitals        scripts/verify
  30-day backfill           live producer (Influx)       integrity gates
  ├─ COPY→stag→ON CONFLICT  └→ Telegraf inputs.exec
  └─ vitals/vitals_truth/       └→ outputs.postgresql
     readings + dims                 │
        │                            │
        └──────────┬─────────────────┘
                   ▼
        ┌───────────────────────┐
        │  TimescaleDB (Postgres│  hypertables: vitals, vitals_truth, readings
        │  + TimescaleDB ext)   │  view: vitals_derived; cagg: vitals_hourly
        └───────────┬───────────┘
                    │ (native Postgres datasource, provisioning files)
                    ▼
              ┌───────────┐
              │  Grafana  │  ward-vitals dashboard ($patient template)
              └───────────┘
```

## Architectural decisions

### 1. Two arms, one shared simulation core
Backfill (offline, bulk) and live (online, streaming) are two thin wrappers
over the same library. This guarantees the live feed is a seamless extension
of the historical record — same ticks, same IDs, same physics.

### 2. Determinism as a first-class property
- Every identity is a UUIDv5 of stable inputs (registry + MRN + sequence).
- Every stochastic stream is seeded (`admission.seed`, derived from the
  patient UUID).
- The live producer snapshots RNG state into checkpoints, making each run
  resumable and reproducible.
*Consequence:* idempotent ingestion (`ON CONFLICT DO NOTHING`), reproducible
tests, and stable SQL lessons with zero configuration.

### 3. TimescaleDB as the single store
No separate message bus. Telegraf writes directly to the `vitals` hypertable;
Grafana reads the same store. Derived analytics (MAP, pulse pressure, shock
index) are computed in a view; hourly aggregation lives in a continuous
aggregate; old chunks are compressed. This keeps the learning surface small
while still demonstrating the distinguishing TimescaleDB features.

### 4. Schema ownership lives in SQL, not in agents
`sql/ddl/00_init.sql` is the source of truth. Telegraf is explicitly
configured to never `CREATE` or `ALTER` (`create_templates = []`,
`add_column_templates = []`), so the schema cannot drift through ingestion.

### 5. Configuration via `.env` + Makefile
Secrets and tunables live in a gitignored `.env`; orchestration is a thin
Makefile. Machine-specific values (passwords) never enter committed
configuration.

### 6. Provisioning-by-file for Grafana
Datasource, dashboard provider, and dashboard JSON are committed and mounted
read-only — the dashboard is reproducible from a clean clone with no manual
UI steps.

## Component responsibilities

| Component | Responsibility | Key files |
| --- | --- | --- |
| **Registry** | Single source of truth: 6 patients, windows, scenarios, ID scheme | `scripts/ward_registry.py` |
| **PhysiologyEngine** | Produce true physiology with mean-reversion + coupling | `src/.../physiology/engine.py` |
| **ScenarioEngine** | Encode condition severity arcs | `src/.../scenarios/{engine,library}.py` |
| **DeviceSimulator** | Map true → observed with faults | `src/.../device/simulator.py` |
| **Backfill loader** | Bulk-load the 30-day ward | `scripts/generate_history.py` |
| **Live producer** | Emit Influx lines, checkpoint per patient | `scripts/stream_vitals.py` |
| **Telegraf** | Exec the producer every 10 s; write to TS | `infra/telegraf/telegraf.conf` |
| **TimescaleDB** | Store, aggregate, compress | `sql/ddl/00_init.sql` |
| **Grafana** | Render dashboards | `grafana/provisioning/…` |
| **Verify** | Post-load integrity gate | `scripts/verify.py` |

## Technology choices

| Choice | Rationale |
| --- | --- |
| Python 3.12 + `uv` | Fast, locked, reproducible env; stdlib simulation code |
| `psycopg` (v3) | Async-C aware COPY, autocommit staging, text-format COPY for int8 |
| TimescaleDB 2.29 / PG 17 | Hypertables, caggs, compression, pushdown |
| Telegraf 1.39 | `inputs.exec` + `outputs.postgresql`, no custom shim needed |
| Grafana OSS | Native Postgres datasource, file-provisioning |

## Directory map

```
docker-compose.yml     service topology
infra/telegraf/        image + config (exec → postgresql)
grafana/provisioning/  datasource + dashboards
sql/ddl               schema (boot-time + idempotent apply)
sql/dql/<tier>/       read-only lessons (beginner/intermediate/advanced)
scripts/              orchestrators (init, generate, stream, verify, registry)
src/healthcare_timeseries_lab/  simulation library
archive/              non-active prototype (FHIR), intentionally not wired in
state/                live-checkpoint volume (gitignored)
```

## Runtime behaviors worth noting

- **6× real-time live arm**: `SCENARIO_TICK_SECONDS=60` scenario seconds per
  10 s real run advances the feed quickly for demo purposes.
- **Offline-only tables**: `vitals_truth` and `readings` are populated only by
  the backfill; the live arm writes `vitals` alone (see
  [Data flow](data_flow.md) and [Reliability](reliability.md)).
- **Health-gated startup**: Telegraf and Grafana wait for TimescaleDB's
  `pg_isready` healthcheck before starting.

## References

- [Scope](scope.md)
- [Data flow](data_flow.md)
- [Data model](data_model.md)
- [Infrastructure](infrastructure.md)
- [Reliability](reliability.md)
- [Security](security.md)
- [Testing](testing.md)