# Security

This is a **synthetic-data learning lab**. Treat it as a dev environment, not
a hardened production deployment. This page states what is currently true,
what it is safe to assume, and what a follow-up hardening pass should add.

## Threat model

Realistic threat model for this lab:

- Accidental exposure of local credentials (Grafana admin, DB password).
- Accidental use of *real* clinical data in a "synthetic" pipeline
  (a compliance error, not a realistic one here).
- Local network snooping between the user's host and the exposed service
  ports.
- Supply-chain risk from pulling third-party images (`timescaledb`,
  `grafana/grafana-oss`, `telegraf`) and Python packages.

Realistically NOT in threat model: multi-tenant abuse, internet-exposed
attacks, insider attacks on a disposable lab.

## What the repo already does

### Secrets handling
- `.env` holds real passwords and is **gitignored**.
- `.env.example` is committed with placeholder values
  (`change-me-in-.env`), so cloning the repo reveals no secrets.
- Grafana's datasource stores the DB password in `secureJsonData` (API-side
  encrypted), not the URL/user fields.
- Telegraf receives the DB password via the `TELEGRAF_PGPASSWORD` env var
  (interpolated into the connection string); `.env` is passed via
  `env_file`, not embedded in committed config.
- The **runbook**: copy `.env.example → .env`, fill real values, never commit
  `.env`.

### Synthetic-data discipline
- README and code documents state plainly: **all data is synthetic**.
- The ward registry (`scripts/ward_registry.py`) is the single source of
  truth for the six fictional patients; no external data is ingested.
- An early FHIR prototype was removed during development; no clinical
  interoperability code runs in this lab.

### Least-privilege posture (partial)
- TimescaleDB exposes only the app database (`POSTGRES_DB`); connection
  params are set in `.env`.
- Telegraf's `outputs.postgresql` is configured to **never mutate schema**
  (`create_templates = []`, `add_column_templates = []`), so a mis-shaped
  point cannot create tables/columns.
- Dependency versions are locked (`uv.lock`), reproducible via `uv sync`.

## Current weaknesses / accepted risks

| Risk | Detail | Mitigation while it is a lab |
| --- | --- | --- |
| Ports exposed to LAN | `5432`, `3000` bind `0.0.0.0` | Host firewall / only run when needed |
| No TLS | Grafana and Postgres are plaintext | Localhost-only or VPN for anything shared |
| Grafana default auth | Admin from `.env`; no SSO/MFA | Long random password; don't share |
| DB superuser used for dashboards | Grafana logs in as `POSTGRES_USER` (superuser) | Create a read-only Grafana role for tighter setups |
| `state/` host perms | `chmod 755` (world-write was never needed: the Telegraf container runs as root, so the bind mount is writable either way) | Revisit ownership if the exec plugin is moved to an unprivileged user |
| Exec plugin runs in stream | Telegraf executes `python3` inside the container as root | Confine to the read-only-mounted scripts/src; consider dropping caps / a dedicated user |
| Image supply chain | Pinned-ish public images (Grafana now pinned by digest, versioned TS/Telegraf) | Scan with `docker scout` / Trivy in CI (see [`ci_cd.md`](ci_cd.md)) |
| Python dependencies | Only `psycopg`, `python-dotenv` + dev deps | `uv.lock`; audit with `uv audit` |

## Recommended hardening (if this moved toward shared / prod-like use)

1. Bind services to `127.0.0.1` (or a VPN) in `docker-compose.yml`; add TLS
   (reverse proxy + certs) for Grafana.
2. Create a **dedicated read-only Postgres role** for Grafana and a write-only
   role for Telegraf (own schema), instead of the superuser everywhere.
3. Run Telegraf's exec — and the `python3` stream — as a dedicated
   unprivileged user, then grant that user ownership of the `state/` mount
   (currently 755 and written as container root).
4. Add an **image policy**: pinned digests + `docker scout cve` /
   Trivy scan in the CI gate (see [`ci_cd.md`](ci_cd.md)).
5. Add cross-checks that **prove synthetic data flow**: assert no real-world
   identifiers/names ever enter the ingest path (the lab already keys
   everything off the deterministic registry).
6. Add `secretslint`/`gitleaks` to the pipeline so `.env`-style secrets
   cannot be committed.

## Operational rules of thumb

- Never commit `.env` (`.gitignore` covers it).
- Rotate `POSTGRES_PASSWORD`, `TELEGRAF_PGPASSWORD`, and the Grafana admin
  password between shared demos.
- If the machine is on a shared network, prefer `make infra-down` when not
  actively working, or firewall the tab.
- Because the database has no TLS, don't reach it from another machine over
  untrusted networks.

## References

- [Infrastructure](infrastructure.md)
- [Reliability](reliability.md)
- [CI/CD](ci_cd.md)