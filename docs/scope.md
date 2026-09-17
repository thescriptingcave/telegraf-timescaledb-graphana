# Scope

This project is a **synthetic ward vitals learning lab**: a deterministic
data+monitoring stack that demonstrates a realistic time-series pipeline
end-to-end on a laptop.

> ⚠️ **All data is synthetic.** There are no real patients, no PII, and no
> production systems here. The names, conditions, and monitors are fictional.

## In scope

### What the lab does
- Generates a **30-day backfilled ward dataset** for January 2026
  (6 patients, 6 vitals channels, 10 s nominal tick).
- Streams a **live continuation** of the same simulation through **Telegraf**
  into the same **TimescaleDB** hypertable.
- Renders a **Grafana dashboard** (native Postgres datasource) showing live
  and historical vitals, derived vitals, and hourly rollups.
- Ships a **curriculum of 23 read-only SQL lessons** (beginner / intermediate /
  advanced) against the real dataset, indexed in
  [`sql/dql/README.md`](../sql/dql/README.md).

### Simulation realism delivered
- Physiology engine with mean reversion, circadian modulation, and
  SpO2→heart-rate/respiration coupling.
- Scenario engine with onset / progression / plateau / recovery severity arcs
  (hypoxemia, tachycardia, hypertension, fever, post-op desaturation).
- Device layer: measurement noise, precision/rounding, sensor latency, spikes,
  random dropout, disconnect and flatline fault windows, quality codes.
- Ward sampling: off-monitor windows, loop irregularity, deterministic per-
  patient seeding.

### Tooling delivered
- Docker Compose stack (TimescaleDB, Telegraf, Grafana) with provisioning and
  health-gated startup.
- Makefile orchestration, pytest suite, ruff linting, `uv` dependency
  management.
- Idempotent backfill, resumable live stream, integrity verification.

## Out of scope (explicitly not delivered here)

- **Real patient data or any clinical use.** Nothing in this lab can or should
  inform care.
- **Production / multi-host deployment.** Single Docker Compose host only.
- **FHIR/HL7 interoperability.** An early prototype was consciously dropped
  and removed from the codebase; the lab stores telemetry in TimescaleDB's
  relational schema, not FHIR resources.
- **Alerting / paging.** No Alertmanager, PagerDuty, or notification channels.
- **Authn/authz beyond defaults.** Grafana admin credentials come from `.env`;
  no SSO, no LDAP, no multi-tenancy.
- **High availability / replication / clustering.** Single-node TimescaleDB.
- **Data retention administration UI.** Compression policies exist; there is
  no retention/archival workflow beyond them.
- **UI beyond Grafana.** No custom front end, no APIs.

## Personas (who this lab is for)

| Persona | Use |
| --- | --- |
| **SQL learner** | Works through `sql/dql/` lessons against real-shaped data |
| **Time-series engineer** | Studies hypertables, caggs, compression, ingest paths |
| **Monitoring learner** | Watches Telegraf exec + TimescaleDB + Grafana end-to-end |
| **Simulation hobbyist** | Tweaks the deterministic engine/scenario parameters |

## Acceptance framing

The lab is "done enough" when, from a clean clone:

1. `make infra-up` starts all three services (TS healthy first).
2. `make generate-data` loads the full January ward idempotently.
3. `make verify` reports **All good**.
4. Grafana shows backfilled + live-updating data for any of the six patients.
5. `uv run pytest` greens the suite and `uv run ruff check .` passes.

## Non-functional boundaries

- Runtime: single host, ~165 s to regenerate the whole month.
- Footprint: Docker Desktop + local `.env`; `state/` and the named TS volume
  are the only persistent state.
- Environments: macOS/Docker first-class; any Docker host should work.

## References

- [Architecture](architecture.md)
- [Data flow](data_flow.md)
- [Testing](testing.md)