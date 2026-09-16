# CI/CD

## Current state

**There is no CI/CD pipeline today.** The repository is a local-first learning
lab: quality gates are runnable by hand via the `Makefile`, and nothing
pushes to a hosted build system. The gates that *do* exist are:

```bash
make lint            # uv run ruff check .
make test            # uv run pytest
make verify          # uv run python -m scripts.verify   (needs a live DB)
```

All three are green on `main` at the time of writing.

## The building blocks already in the repo

Whatever pipeline you choose, the stages map to existing, deterministic
commands:

| Stage | Command | Needs |
| --- | --- | --- |
| Lock/environment | `uv sync` (uses committed `uv.lock`) | – |
| Lint | `make lint` | – |
| Unit tests | `make test` | – |
| Setup stack | `make infra-up` | Docker |
| Apply schema | `make init` | TS healthy |
| Load data | `make generate-data` | TS |
| Verify data | `make verify` | TS |
| Dashboard smoke | curl Grafana `/api/health` + check datasource | Grafana |
| Down | `make infra-down` | – |

Because the loader and verifier are idempotent and deterministic, the data
stage is reproducible in CI on every run.

## Proposed pipeline (blueprint)

A GitHub Actions workflow implied by the repo's layout. Treat this as the
target; it is **not yet implemented** (no `.github/workflows/` exists).

```yaml
name: lab-ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v6
      - name: Install deps
        run: uv sync --frozen
      - name: Lint
        run: make lint
      - name: Unit tests
        run: make test

  integration:
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Seed .env from template
        run: |
          cp .env.example .env
          # generate real-but-ephemeral values, do not commit them
      - name: Start stack
        run: make infra-up
      - name: Apply schema
        run: make init
      - name: Backfill 30-day ward
        run: make generate-data
      - name: Integrity verify
        run: make verify
      - name: Smoke-test Grafana
        run: |
          curl -fsS http://localhost:3000/api/health
          curl -fsS "http://localhost:3000/api/datasources/name/TimescaleDB"
      - name: Teardown
        run: make infra-down

  security-scans:            # aspirational
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Secret scan
        run: |
          # e.g. gitleaks detect --source . --verbose
      - name: Dependency audit
        run: |
          uv audit          # advisory check on uv.lock
      - name: Container scan
        run: |
          # e.g. docker scout cves timescale/timescaledb:2.29.2-pg17
```

### Design notes for the pipeline

- **Determinism makes integration cheap.** The backfill always produces the
  same 942,840 truth rows from the same commit, so `verify` is a stable
  gate, not a flaky one.
- **Secrets discipline.** CI should synthesize `.env` from `.env.example`
  with ephemeral values and reuse the *same* values across the job; never
  mutate the committed `.env.example`.
- **Pin images.** Prefer digests over `:latest` for Grafana and pinned tags
  for TimescaleDB/Telegraf; add a container CVE scan stage when moving beyond
  a personal lab.
- **Idempotency as a CI feature.** Re-running `generate-data` is a no-op, so a
  broken nightly can simply re-run.

### Local "CI" without GitHub

Until a hosted pipeline is desired, the same flow is a one-liner:
```bash
make lint && make test && make infra-up && make init \
  && make generate-data && make verify && make infra-down
```

## Suggested milestones

1. **M1 — Local gate script:** commit a `scripts/ci.sh` that runs the
   one-liner above; wire `make ci` to it.
2. **M2 — GitHub Actions `quality` job:** lint + unit tests on every PR.
3. **M3 — `integration` job:** full stack + data + verify on `main` push.
4. **M4 — scans:** gitleaks + `uv audit` + container scan; image digests.
5. **M5 — deploy (optional):** nightly rebuild of the demo stack on a
   remote host with `.env` injected from a secret store.

## References

- [Testing](testing.md)
- [Security](security.md)
- [Infrastructure](infrastructure.md)
- [`Makefile`](../Makefile)