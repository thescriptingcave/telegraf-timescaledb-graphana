# Telegraf + TimescaleDB + Grafana — Ward Vitals Lab

A synthetic ward vitals lab on a lean monitoring stack: a deterministic,
**seeded** physiology/device engine emits a **30-day backfilled dataset** into
**TimescaleDB**, and **Telegraf** streams a **live** continuation of the same
simulation into the same hypertable, with **Grafana** (native Postgres
datasource) rendering the dashboard.

This is a learning lab. **All data is synthetic** — no real patients.

Full documentation lives in [`docs/`](docs/README.md).
Detailed setup steps are in [`docs/infrastructure.md`](docs/infrastructure.md).