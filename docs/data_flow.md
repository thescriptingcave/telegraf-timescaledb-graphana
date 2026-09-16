# Data Flow

This document describes every byte that moves through the lab: where it is
born, how it is transformed, how it is stored, and how it is displayed.

All data is **synthetic**. Nothing here is real patient data. See
[`docs/synthetic_data.md`](synthetic_data.md) for how the simulation is seeded
and controlled.

## Pipeline at a glance

```
 pure physiology (ground truth)
   │  PhysiologyEngine (mean-reversion + oxygen coupling + scenario effects)
   ▼
 true state per tick  ──────────────────────────────────► vitals_truth (offline)
   │
   ▼  DeviceSimulator (noise, precision, latency, dropout, faults)
 observed event ──► backfill path ──► vitals / readings (COY bulk load)
                   ─► live path     ─► Telegraf exec ─► outputs.postgresql ─► vitals
                                                     
                              ▲
   Grafana (Postgres datasource) reads vitals / vitals_derived / vitals_hourly
```

There are two producers and one consumer:

| Arm | Producer | Writes | Runs |
| --- | --- | --- | --- |
| **Backfill** | `scripts/generate_history.py` | `vitals`, `vitals_truth`, `readings`, dimensions | On demand (`make generate-data`) |
| **Live** | `scripts/stream_vitals.py` + Telegraf | `vitals` | Continuously, every 10 s |
| **View** | Grafana | reads only | Browser dashboard |

## The shared simulation core

Both arms reuse the same library under `src/healthcare_timeseries_lab/`:

1. **`PhysiologyEngine.next_state()`** produces one *true* physiological state
   per tick: HR, SpO2, RR, temperature, systolic/diastolic BP. It applies
   per-patient baselines, circadian modulation, mean-reversion noise, and
   scenario effects, and couples SpO2 deficits back into heart rate and
   respiration with a short lag.
2. **`DeviceSimulator.observe()`** turns a true state into an *observed*
   event: measurement noise, precision/rounding, sensor latency, spikes,
   random dropout, and optional disconnect/flatline windows. It also stamps a
   `quality_code` (`GOOD`/`DEGRADED`/`POOR`/`LOST`).
3. **`ScenarioEngine.active_conditions()`** interpolates scenario severity
   over time so conditions onset, progress, plateau, and recover.

Both arms share the **ward registry** (`scripts/ward_registry.py`): six
patient admissions, deterministic UUID namespaces, the off-monitor windows,
and the nominal tick.

## Timing model

| Constant | Value | Meaning |
| --- | --- | --- |
| `NOMINAL_TICK` | 10 s | Simulation tick between states |
| `LOOP_SKIP_PROBABILITY` | 0.10 | Fraction of ticks that emit no event (irregularity) |
| Off-monitor windows | 06:00–06:45, 18:30–19:15 UTC | Handover/transport; no events emitted |
| `SCENARIO_TICK_SECONDS` | 60 | Live arm advances this much scenario time per run |
| Live interval | 10 s | Telegraf invokes the exec input |

Because the live arm advances 60 s of scenario time every real 10 s, the live
feed runs **6× real time** by default (`SCENARIO_TICK_SECONDS=60`).

## Arm 1 — 30-day backfill (`generate_history.py`)

1. Reads `DATABASE_URL` from `.env` (defaults to the local compose instance).
2. Assumes schema exists (from `sql/ddl/00_init.sql`, applied by
   `init_db.py` or first-boot init).
3. Upserts **dimension tables** (`patients`, `encounters`).
4. For each admission, in-process simulation iterates every 10 s tick from
   `admitted_at` to `discharged_at`:
   - engine → true state → a `vitals_truth` row + 6 "truth" `readings`;
   - device → an observed event (subject to skip + off-monitor + dropout) →
     a `vitals` row + 6 "observed" `readings`.
5. Rows are buffered and bulk-loaded through temporary staging tables with
   `COPY FROM STDIN`, then `INSERT ... ON CONFLICT DO NOTHING` into the real
   tables. This makes the load **idempotent**: rerunning with the same seeds
   produces the same event IDs and changes nothing.
6. Background policy jobs (cagg refresh, compression) are paused during the
   load and resumed afterwards to avoid contention.
7. On completion the `vitals_hourly` continuous aggregate is refreshed in
   full.

Observed load (6 patients, January 2026): ~165 s wall time,
~4k–8.5k ticks/s per patient.

| Table | Rows after backfill |
| --- | --- |
| `vitals_truth` | 942,840 |
| `vitals` | ~791,550 (≈84% of ticks) |
| `readings` | ~10.4M (6 per truth tick + 6 per observed event) |

## Arm 2 — live stream (`stream_vitals.py` + Telegraf)

1. Telegraf's `[[inputs.exec]]` runs `python3 /app/scripts/stream_vitals.py`
   every 10 s with an 8 s timeout.
2. For each patient the script:
   - loads a per-patient JSON **checkpoint** from `STREAM_STATE_DIR` (the
     mounted `state/` volume, `/app/state` in the container);
   - advances the simulation by one scenario tick (default 60 s);
   - persists the new checkpoint atomically (`.json.tmp` + `os.replace`);
   - prints one **Influx line-protocol** line per emitted event.
3. Telegraf parses the lines (`data_format = "influx"`) and the
   `[[outputs.postgresql]]` plugin maps tags→columns and fields→columns of the
   `vitals` hypertable. The timestamp lands in `vitals.time`.
4. The output plugin is configured **never to mutate schema**
   (`create_templates = []`, `add_column_templates = []`), so it can only
   write rows that match the backfill-created schema.

The live feed continues the timeline immediately after the backfill
(`2026-01-31T00:00Z` onward), reusing the same deterministic ID scheme so
retries are idempotent (`ON CONFLICT (time, event_id) DO NOTHING`).

Checkpoints snapshot engine RNG state, device RNG state, the loop RNG, last
true state, and the oxygen-coupling history — so every run is resumable and
re-running a checkpoint reproduces the identical tick.

## Arm 3 — read paths (Grafana)

Every Grafana panel is a `rawSql` query against the single TimescaleDB
datasource:

- Channel time series → `vitals` filtered by `$patient` and `$__timeFilter`,
  aggregated with `$__timeGroup` and restricted to
  `quality_code IN ('GOOD','DEGRADED','POOR')`.
- Derived vitals → `vitals_derived` (MAP, pulse pressure, shock index).
- The hourly rollup panel → `vitals_hourly` continuous aggregate.

The dashboard refresh is 30 s; the default time window is
`2026-01-01 → now`, in UTC.

## Data volume sanity

- 6 channels per event × 2 sources (truth + observed).
- ~259,200 ticks per full-stay patient (30 days at 10 s).
- ~942,840 truth rows and ~10.4M reading rows for the whole January ward.

## References

- Schema: [`sql/ddl/00_init.sql`](../sql/ddl/00_init.sql)
- Backfill loader: [`scripts/generate_history.py`](../scripts/generate_history.py)
- Live producer: [`scripts/stream_vitals.py`](../scripts/stream_vitals.py)
- Telegraf: [`infra/telegraf/telegraf.conf`](../infra/telegraf/telegraf.conf)
- Grafana dashboard: [`grafana/provisioning/dashboards/ward-vitals.json`](../grafana/provisioning/dashboards/ward-vitals.json)