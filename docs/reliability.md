# Reliability

This is a single-host learning lab, but the data plane was designed with
recovery and idempotency in mind so it can be restarted, replayed, and
re-verified without corruption.

## Idempotent ingestion

Everything that writes data is safe to run more than once:

- **Deterministic IDs.** `event_id`, `truth_id`, and the simulation UUIDs are
  pure UUIDv5 functions of (namespace, MRN, sequence). A retry produces the
  *same* row identity, never a duplicate.
- **`ON CONFLICT DO NOTHING`.** Backfill inserts into `vitals`,
  `vitals_truth`, and `readings` are guarded by the composite keys
  (`time, event_id` and `time, patient_id, channel, sequence_number`).
- **Telegraf writes** collide on `(time, event_id)` and are discarded on
  conflict, so an exec retry mid-write cannot double-insert.

## Live-stream checkpointing

`stream_vitals.py` persists one JSON checkpoint per MRN in the mounted
`state/` volume:

- Checkpoints snapshot the engine/device/loop RNG states, the last true
  physiological state, and the oxygen-coupling history.
- **Atomic persistence:** write `*.json.tmp`, then `os.replace()` — a crash
  midway never leaves a torn checkpoint.
- **Resumable:** a failed or interrupted run restarts from the last good
  checkpoint; re-running the same checkpoint reproduces the identical tick.
- The container override `STREAM_STATE_DIR=/app/state` keeps checkpoints in
  the Docker volume-mounted `state/` directory and out of the image layer.

## Startup ordering

- TimescaleDB exposes a `pg_isready` healthcheck; Telegraf and Grafana gate
  startup on `depends_on: condition: service_healthy`.
- The schema mounts into `/docker-entrypoint-initdb.d` for first boot and is
  additionally re-appliable via `make init` without disrupting data
  (`IF NOT EXISTS` guards).

## Background job handling during bulk load

The backfill pauses the continuous-aggregate refresh and compression jobs for
the load window, then restores their original schedules. This avoids
contention between high-volume `COPY` inserts and policy jobs.

## Failure modes and mitigations

| Failure | Mitigation |
| --- | --- |
| Exec command crashes | Telegraf retries every 10 s; checkpoint is atomic; conflict-free insert |
| Pod/container restart | Named volume `timescale_data` persists the database; `state/` volume persists checkpoints |
| Corrupt/partial backfill | Rerun `make generate-data` — identical IDs, no-op conflicts |
| Schema drift / missing table | `outputs.postgresql` will never `ALTER` (`add_column_templates = []`); run `make init` |
| Live stream can't write state dir | `STREAM_STATE_DIR` absolute path + world-writable `state/` for the container user |
| Unexpected `host` tag | `omit_hostname = true` in `[agent]` prevents dropped rows |

## Detection and verification

- `make verify` (`scripts/verify.py`) checks: table row counts, exact
  `vitals_truth` total against the registry (942,840), the readings invariant,
  vitals-loss ratio (~85% expected), timeline coverage, referential integrity
  (0 orphans, 0 duplicate event IDs), derived view sanity, and the hourly
  aggregate.
- Telegraf/Grafana logs surface exec crashes and dropped rows via
  `make infra-logs`.
- Test suite asserts determinism and resumability (see
  [Testing](testing.md)).

## Expected lossy-ness (by design)

Vitals observations are not 100% of ticks. Loss sources:
- 10% loop irregularity (`LOOP_SKIP_PROBABILITY`)
- daily off-monitor windows (handover/transport)
- device dropout probability (0.5% default)
- optional disconnect/flatline fault windows

The design target is ~85% of ticks appearing in `vitals`; the verification
gate accepts 70–95%.

## Known trade-offs (learned live)

1. `verify.py`'s readings invariant is **live-aware**: `readings` are only
   produced by the offline backfill, while the live arm keeps growing
   `vitals`. The check therefore derives the backfill-observed count from
   `readings` and bounds it by the current vitals total, so verification
   passes while streaming.
2. `state/` is `chmod 755` on the host. The Telegraf container runs as root,
   so bind-mount writes just work; world-write (`777`) is unnecessary and was
   removed. The open hardening item is running the exec plugin as an
   unprivileged user (see [Security](security.md)).

## References

- [Infrastructure](infrastructure.md)
- [Data flow](data_flow.md)
- [Testing](testing.md)
- [Security](security.md)