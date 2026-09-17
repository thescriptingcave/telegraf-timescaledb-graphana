# Documentation

Everything about **Telegraf + TimescaleDB + Grafana — Ward Vitals Lab**.
This is a synthetic-data learning project; **nothing on any page is real
patient data**.

| Document | Answers |
| --- | --- |
| [Scope](scope.md) | What this project is, delivers, and deliberately does not deliver |
| [Architecture](architecture.md) | High-level components and the key design decisions |
| [Data flow](data_flow.md) | Where data comes from and how it moves through the pipeline |
| [Data model](data_model.md) | Tables, hypertables, views, aggregates, compression, IDs |
| [Synthetic data](synthetic_data.md) | How the deterministic dataset is generated and controlled |
| [SQL lessons](../sql/dql/README.md) | Course map and index of the read-only SQL curriculum |
| [Infrastructure](infrastructure.md) | Docker Compose services, env vars, Makefile, boot sequence |
| [Reliability](reliability.md) | Idempotency, checkpointing, failure modes, verification |
| [Security](security.md) | Secrets handling, current posture, weak spots, hardening |
| [Testing](testing.md) | Test suite, invariants, how to run the gates |
| [CI/CD](ci_cd.md) | Current state (none) and a blueprint pipeline |

## Quick start

```bash
cp .env.example .env          # fill in real values
make infra-up                 # TimescaleDB (healthy) → Telegraf + Grafana
make init                     # apply schema idempotently
make generate-data            # backfill the 30-day January ward
make verify                   # integrity gate → "All good"
make dashboard                # open Grafana (http://localhost:3000)
```

Live vitals begin streaming into the same `vitals` hypertable as soon as
Telegraf starts — no extra step needed.

## Good first reads

1. [Scope](scope.md) — is this lab for you?
2. [Architecture](architecture.md) — the mental model.
3. [Data flow](data_flow.md) — backfill vs. live arms.
4. [Infrastructure](infrastructure.md) — how to run it.