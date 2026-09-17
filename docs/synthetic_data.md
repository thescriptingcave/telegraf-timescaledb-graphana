# Synthetic Data

Everything in this lab is fabricated. There are no real patients, no real
monitors, no real observations. This page explains *how* the synthetic dataset
is designed so that it is reproducible, teachable, and clearly non-clinical.

## The ward (fictional)

Six fictional patients are admitted across January 2026. Their profiles live
in `scripts/ward_registry.py`.

| MRN | Display name | Age | Scenario | Admissions |
| --- | --- | --- | --- | --- |
| `W10001` | Naomi Nunez | 52 | `progressive_hypoxemia` | Jan 1 → Jan 31 (full) |
| `W10002` | Cole Bennett | 68 | `tachycardia` | Jan 1 → Jan 31 (full) |
| `W10003` | Ivy Park | 47 | `stable` | Jan 1 → Jan 31 (full) |
| `W10004` | Marcus Reed | 61 | `late_hypoxemia` | Jan 3 → Jan 8 |
| `W10005` | Fatima Al-Rashid | 83 | `hypertensive_episode` | Jan 12 → Jan 20 |
| `W10006` | Diego Ramirez | 29 | `postop_desaturation` | Jan 22 → Jan 28 |

Each patient has baselines for HR, SpO2, RR, temperature, and systolic/
diastolic BP, plus a `variability_factor`.

### Census lifecycle (1.0 semantics)

`admitted_at`/`discharged_at` bound the **historical (backfill) horizon**:
the offline loader generates exactly the ticks inside each admission window
and closes the matching `encounters`. The **live arm**, however, has no
admission/discharge lifecycle in 1.0 — it is a *next-day ward continuation*
of the same fixed census. It keeps advancing the same six patients past
`2026-01-31T00:00Z` (the moment the backfill ends) so the dashboard always
has a live feed to show. Discharges recorded in the registry therefore apply
to the backfilled history, not to the live stream; no new patients are
admitted at runtime.

## Why "deterministic + seeded"?

Every stochastic component draws from a seeded generator so the *entire
dataset* is reproducible bit-for-bit:

- `admission.seed = int(patient_id.int % 2³¹)` — derived from the patient's
  deterministic UUID, so it is stable across runs and tools.
- The backfill, the live stream, and the tests that compare them all derive
  their RNG streams from that seed.

Re-running `make generate-data` on the same commit produces identical event
IDs and is a no-op (conflict-free).

## How physiology is synthesized

1. **Baselines** chosen from plausible adult ranges (e.g. HR 68–76 bpm,
   SpO2 95–98%, temp 36.6–37.0 °C).
2. **Circadian modulation**: HR and RR breathe with the time-of-day via a
   cosine around a 09:00 peak (`±4%`, see `PatientAdmission.profile_at`).
3. **Mean reversion**: each channel drifts toward its (baseline + condition
   effect) target with per-channel reversion strength and noise standard
   deviation (`PhysiologyEngine`).
4. **Oxygen coupling**: an SpO2 deficit raises heart rate (×1.2) and
   respiration (×0.6), lagged by 60 s / 30 s, so hypoxemia "looks" clinical.
5. **Bounds**: `PhysiologicalState` clamps every channel to physiological
   ranges (HR 25–220, SpO2 50–100, RR 4–60, temp 30–43, SBP 50–240,
   SBP > DBP).

## How scenarios add structure

A condition is a timeline of phases — `ONSET → PROGRESSION → PLATEAU →
RECOVERY` — each with `start/end offset` and `start/end severity`. Severity
interpolates linearly within a phase; effects scale with severity
(`scenarios/engine.py`). The library ships:

- `progressive_hypoxemia` (SpO2 −10 scale, long 30-day arcs plus short-stay
  variants)
- `tachycardia` (HR +40 scale, partial recovery)
- `hypertensive_episode` (SBP +45 / DBP +25)
- `postop_desaturation` + low-grade `fever` (temp +1.5)
- a fully stable patient (Ivy) as a control

## How observed telemetry differs from truth

The device layer (`device/simulator.py`) turns each true state into an
observed event:

| Effect | Default |
| --- | --- |
| White noise per channel | HR 0.4, SpO2 0.25, RR 0.2, temp 0.02, SBP 0.5, DBP 0.4 |
| Precision/rounding | 0 d.p. for HR/SpO2/RR/BP; 1 d.p. for temperature |
| Sensor latency | ~0.5 s |
| Spike probability / amplitude | 0.3% / ±4 bpm (HR), ±2 (SpO2) |
| Dropout probability | 0.5% |
| Clock skew, disconnect/flatline windows | 0 by default; configurable |

Quality codes summarize the outcome: `GOOD`, `DEGRADED` (drift/spike),
`POOR` (flatline), `LOST` (disconnect).

## Ward sampling policy

- Nominal 10 s tick; ~10% of ticks emit nothing (loop irregularity).
- Daily off-monitor windows 06:00–06:45 and 18:30–19:15 UTC emit nothing
  (handover/transport).
- The live arm advances 60 s per run by default (`SCENARIO_TICK_SECONDS`),
  i.e. runs 6× real time.

Together these produce ~84% of ticks in the observed `vitals` table
(verification gate accepts 70–95%).

## Volumes (January ward, 6 patients)

| Table | Rows |
| --- | --- |
| `vitals_truth` | 942,840 (exactly one per 10 s tick in each admission window) |
| `vitals` | ~791,550 observed events |
| `readings` | ~10.4M (6 channels × truth + 6 channels × observed) |

## Identity scheme

All IDs are UUIDv5 from fixed namespaces (`scripts/ward_registry.py`), so the
backfill, the Telegraf live stream, and the SQL lessons reference exactly the
same patients/events. See [Data model](data_model.md).

## Making it clearly synthetic

- Fictional names and MRNs (`W1xxxx`), flagged in code and docs.
- Every artifact descends from the registry — there is no external import
  path, so nothing real can accidentally enter the pipeline.
- No clinical interoperability (FHIR/HL7) code is present; a prototype was
  removed during development.

## References

- [Architecture](architecture.md)
- [Data flow](data_flow.md)
- [Data model](data_model.md)
- [`scripts/ward_registry.py`](../scripts/ward_registry.py)
- [`src/healthcare_timeseries_lab/`](../src/healthcare_timeseries_lab/)