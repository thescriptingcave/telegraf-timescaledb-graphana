# Infrastructure

The lab runs as a three-service **Docker Compose** stack. Everything needed to
reproduce the stack is in the repository root; the cosmetic instructions below
match the `Makefile` targets.

## Services

| Service | Image / build | Port | Volumes | Health |
| --- | --- | --- | --- | --- |
| `timescaledb` | `timescale/timescaledb:2.29.2-pg17` | `5432:5432` | `timescale_data` (named), `./sql/ddl` → `/docker-entrypoint-initdb.d` | `pg_isready` |
| `telegraf` | build `./infra/telegraf` | – | `./state` → `/app/state`, `telegraf.conf` (ro), `./scripts` → `/app/scripts` (ro), `./src` → `/app/src` (ro) | depends on TS **healthy** |
| `grafana` | `grafana/grafana-oss:latest` | `3000:3000` | `./grafana/provisioning` (ro) | depends on TS **healthy** |

`docker-compose.yml`:

- Sets a Compose project name `telegraf-timescaledb-graphana` (container
  prefix `telegraf-timescaledb-graphana-`).
- All services load environment from `.env` (`env_file`).
- Telegraf and Grafana `depends_on` TimescaleDB with `condition:
  service_healthy`, so they only start after the database is ready.

## Environment variables (`.env`, gitignored)

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | TS, Grafana | DB superuser for init/dashboard |
| `POSTGRES_PASSWORD` | TS, Grafana | DB password |
| `POSTGRES_DB` | TS, Telegraf, Grafana | Database name (`telemetry`) |
| `TELEGRAF_PGPASSWORD` | Telegraf | DB password used by `outputs.postgresql` |
| `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD` | Grafana | Admin login |
| `DATABASE_URL` | Host scripts | psycopg connection for `init_db` / `generate_history` / `verify` |
| `STREAM_STATE_DIR` | Live producer | Checkpoint directory |
| `SCENARIO_TICK_SECONDS` | Live producer | Scenario time per live run (default 60) |

`.env.example` documents the shape with placeholder values; it is committed,
`.env` itself is not.

> **Telegraf in-container override:** the container sets
> `STREAM_STATE_DIR=/app/state` explicitly so Telegraf's exec (which runs with
> CWD `/`) writes checkpoints into the mounted `state/` volume rather than the
> root filesystem. Host-side `make stream-local` keeps `.env`'s `./state`.

## Database provisioning

- On first boot, `/docker-entrypoint-initdb.d/00_init.sql` (mounted from
  `sql/ddl/`) creates the extension, tables, hypertables, view, continuous
  aggregate, and compression.
- The same DDL is re-appliable/repairable via
  `uv run python -m scripts.init_db` (`make init`) — every statement is
  guarded (`IF NOT EXISTS`, `CREATE OR REPLACE`, `DO` blocks).

## Telegraf

See [`infra/telegraf/telegraf.conf`](../infra/telegraf/telegraf.conf):

```
[agent]          interval 10s, flush 10s, omit_hostname = true
[[inputs.exec]]  python3 /app/scripts/stream_vitals.py, 10s, 8s timeout, influx
[[outputs.postgresql]] → timescaledb, schema public, no template mutations
```

Key points:
- `omit_hostname = true` — the default `host` tag has no `vitals` column; the
  output is configured never to alter schema (`create_templates = []`,
  `add_column_templates = []`).
- The image is `telegraf:1.39-alpine` with `python3` added
  (`infra/telegraf/Dockerfile`).

## Grafana

Provisioned entirely from files (no manual setup):

- **Datasource** (`grafana/provisioning/datasources/timescale.yaml`):
  Postgres, URL `timescaledb:5432`, `uid: timescale`, `timescaledb: true`,
  credentials from `${POSTGRES_USER}` / `${POSTGRES_PASSWORD}` (password held
  in `secureJsonData`), default datasource.
- **Dashboard provider** (`grafana/provisioning/dashboards/dashboards.yaml`):
  folder `Ward`, scans the provisioning dashboards dir every 30 s.
- **Dashboard** (`ward-vitals.json`): 9 panels (HR/SpO2/RR/temp/BP,
  MAP & pulse pressure, shock index, latest SpO2 stat, hourly rollup) with a
  `$patient` template variable (`SELECT mrn FROM patients ORDER BY mrn`).

## Makefile targets

| Target | Command |
| --- | --- |
| `make infra-up` | `docker compose up -d --build` |
| `make infra-down` | `docker compose down` |
| `make infra-logs` | Follow logs for the three services |
| `make dashboard` | Print Grafana URL + login hint |
| `make init` | Apply DDL (`uv run python -m scripts.init_db`) |
| `make generate-data` | 30-day backfill (`uv run python -m scripts.generate_history`) |
| `make verify` | Integrity checks (`uv run python -m scripts.verify`) |
| `make stream-local` | Run the live producer on the host |
| `make test` | `uv run pytest` |
| `make lint` | `uv run ruff check .` |

## Boot sequence

1. `cp .env.example .env` and fill real values.
2. `make infra-up` — TS first (`pg_isready`), then Telegraf + Grafana.
3. `make init` (idempotent; usually already applied at first boot).
4. `make generate-data` — load the 30-day history.
5. `make verify` — confirm invariants.
6. `make dashboard` — browse Grafana; live data now streams in alongside.

## Layout

```
docker-compose.yml               service definitions
.env / .env.example              config + secrets (example committed)
sql/ddl/00_init.sql              schema, applied at boot + idempotently
sql/dql/<tier>/                  read-only SQL lessons
infra/telegraf/                  Telegraf image + config
grafana/provisioning/            datasource, provider, dashboard JSON
scripts/                         backfill, live producer, init, verify, registry
src/healthcare_timeseries_lab/   simulation library
state/                           live-stream checkpoints (gitignored)
tests/                           pytest suite
```

## References

- [Architecture](architecture.md)
- [Data flow](data_flow.md)
- [Reliability](reliability.md)
- [`docker-compose.yml`](../docker-compose.yml)