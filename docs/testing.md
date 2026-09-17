# Testing

The lab ships an automated test suite and a lint gate. All tests run against
the simulation code and repository structure **without a live Docker stack** —
they are deterministic, fast, and dependency-light.

## Running the gates

```bash
uv run pytest        # full suite
uv run ruff check .  # lint (imports unused, style, sanity)
```

From the Makefile: `make test`, `make lint`.

Both gates are green on `main` (97 tests passing at the time of writing).

## Suite map (`tests/`)

| File | Focus | What it proves |
| --- | --- | --- |
| `test_device.py` | Device layer | Dropout never fabricates values; precision/rounding; flatline freezes a channel and flags `POOR`; disconnect freezes values and marks `LOST` |
| `test_physiology.py` | Physiology engine | Determinism per seed (same seed ⇒ identical states, different seed ⇒ different); states stay inside physiological bounds; hypoxemia drops SpO2 and raises HR; a stable patient stays quiet |
| `test_history.py` | Backfill generator | Deterministic slice; row shapes (12-col truth, 15-col vitals, 6/12 readings); full-stay tick counts and the 6·ticks + 6·vitals invariant; off-monitor windows contain no emitted events |
| `test_registry.py` | Ward registry | Six unique admissions; consistent patient IDs between profile and admission; ordered windows; distinct event/truth namespaces; deterministic distinct seeds; hypoxemia severity tracks the timeline; conditions resolve after recovery; live start equals backfill end |
| `test_stream_cp.py` | Live producer / checkpoints | Clean continuation checkpoint; `advance` is pure + deterministic; survival through JSON round-trip; time/sequence advance; `advance_and_emit` prints a parseable Influx line and writes the next checkpoint |
| `test_lessons.py` | SQL lessons | Every lesson file exists with lesson/tier headers; lessons are read-only (no INSERT/UPDATE/DELETE/CREATE/…); every lesson references lab schema tables |

## Quality expectations (the "invariants")

Beyond unit assertions, the suite hard-codes the data contracts the
application must honour:

- **Deterministic reproducibility** — same seed ⇒ identical rows/events, on
  disk and in memory.
- **Physiological plausibility** — every emitted state stays inside the bounds
  defined by `PhysiologicalState` (HR 25–220, SpO2 50–100, RR 4–60, temp
  30–43, systolic 50–240 > diastolic 25–150).
- **Loss accounting** — observed vitals stay in 70–95% of ticks (design
  target ~85%).
- **Idempotency keys** — `(time, event_id)` uniqueness and distinct
  event/truth namespaces.
- **Lesson safety** — DQL files may only read.

## Integration-grade checks (not in pytest)

The repository's *database* gates live in the scripts, run manually or in CI
after the stack is up:

| Gate | Command | Checks |
| --- | --- | --- |
| Schema apply | `make init` | DDL applies idempotently |
| Backfill load | `make generate-data` | Inserts all 6 patients, refreshes cagg |
| Integrity verify | `make verify` | Row counts, invariants, timeline, referential integrity, derived view, hourly aggregate (see [Data flow](data_flow.md) and [Reliability](reliability.md)) |

A future CI run could chain: `infra-up → init → generate-data → verify →
pytest → lint` as one integration job (see [`ci_cd.md`](ci_cd.md)).

## Testing philosophy

1. **No Docker needed for unit tests** – keep the fast gate fast.
2. **Seed everything** – RNG state is explicit so failures are reproducible.
3. **Assert contracts, not pixels** – row shapes, invariants, IDs, bounds.
4. **SQL lessons are tested as artifacts** – structure, headers, read-only
   rule, and schema references.
5. **Database invariants are verified by a separate script** – the simulator
   tests never fake a live database.

## References

- [CI/CD](ci_cd.md)
- [Reliability](reliability.md)
- [`pyproject.toml`](../pyproject.toml)
- [`Makefile`](../Makefile)