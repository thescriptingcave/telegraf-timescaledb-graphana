# SQL Lessons — Ward Vitals Lab

A **read-only** SQL curriculum that runs against the real January 2026 ward
dataset. Each lesson is a single, self-documenting `.sql` file: the comment
block states the business question and the concepts taught, then the query
below it produces the answer. Run them as-is, then edit and re-run to explore.

Everything here is **synthetic** — no real patients. See
[`docs/synthetic_data.md`](../../docs/synthetic_data.md).

## Prerequisites

The lessons query live tables, so bring up the stack and load the ward first
(from the repository root):

```bash
make infra-up        # TimescaleDB (healthy) → Telegraf + Grafana
make init            # apply the schema idempotently
make generate-data   # backfill the 30-day January ward
```

## Running a lesson

Every lesson is a plain `SELECT`, so pipe the file straight into `psql`.
With the default `.env` values (`postgres` / `telemetry`):

```bash
docker compose exec -T timescaledb \
  psql -U postgres -d telemetry \
  < sql/dql/beginner/b1_ward_census.sql
```

If you changed `POSTGRES_USER` / `POSTGRES_DB` in `.env`, use those. You can
also connect any client with the `DATABASE_URL` from `.env`, or paste the
query into Grafana's Explore panel.

## Lesson format

Each file carries a consistent header so the curriculum is machine-checkable:

```sql
-- lesson: <title>
-- tier: beginner | intermediate | advanced
-- <the clinical/business question>
--
-- Concepts taught
--   * <concept>
--   * <concept>
```

The curriculum currently has **23 lessons** across the three tiers.

Guarantees, enforced by [`tests/test_lessons.py`](../../tests/test_lessons.py):

- Every lesson exists with `-- lesson:` and a matching `-- tier:` header.
- Every lesson is **read-only** — no `INSERT`/`UPDATE`/`DELETE`/`CREATE`/…
- Every lesson references at least one lab table.

Some lessons end with **"Try it yourself"** prompts that suggest a variation to
run next.

## Suggested study path

Read top-to-bottom within a tier, then move up:

1. **Beginner** — get fluent with `SELECT`, joins, and `time_bucket`.
2. **Intermediate** — window functions (`LAG`, frames, ranking) and the
   long-format fact table.
3. **Advanced** — gap-and-islands, sessionization, recursive CTEs, gap filling,
   continuous aggregates, and observed-vs-truth fidelity.

A six-session plan:

| Session | Lessons | Theme |
| --- | --- | --- |
| 1 | B1, B2, B3 | Roster, hourly rollups, flagging a patient |
| 2 | I1, I2, I3 | Finding an event, smoothing, ranking |
| 3 | I4, I5, I6 | Window frames, LEAD / first-last, dense rank |
| 4 | D1, A4, A7 | Star-schema reads and the "latest per patient" idioms |
| 5 | A5, A6, A8 | Step-change deltas, percentile outliers, local extrema |
| 6 | A1, A2, A9 | Gap-and-islands, sessionization, and a band-reframed recap |
| 7 | R1, G1 | Recursive CTEs and gap filling |
| 8 | A3, C1, A10 | Measurement fidelity, continuous aggregates, reading a plan |

## Beginner

| # | File | Lesson | Concepts | Tables |
| --- | --- | --- | --- | --- |
| B1 | [`b1_ward_census.sql`](beginner/b1_ward_census.sql) | Ward census | `SELECT`, `INNER JOIN`, `ORDER BY` | `patients`, `encounters` |
| B2 | [`b2_hourly_handoff.sql`](beginner/b2_hourly_handoff.sql) | Hourly handoff | `time_bucket`, `GROUP BY` + `AVG`, `ROUND`, first CTE, join | `vitals`, `patients` |
| B3 | [`b3_flag_attention.sql`](beginner/b3_flag_attention.sql) | Flag attention | Time-window filter, aggregate-then-filter via CTE, `LEFT JOIN` | `vitals`, `patients`, `encounters` |

## Intermediate

| # | File | Lesson | Concepts | Tables |
| --- | --- | --- | --- | --- |
| I1 | [`i1_first_drop.sql`](intermediate/i1_first_drop.sql) | First SpO2 drop | `LAG`, `PARTITION BY` + `ORDER BY` window, state transition | `vitals`, `patients` |
| I2 | [`i2_moving_average.sql`](intermediate/i2_moving_average.sql) | Moving average | Window frames (`ROWS BETWEEN n PRECEDING AND n FOLLOWING`), smoothing, deviation | `vitals`, `patients` |
| I3 | [`i3_worst_ranked.sql`](intermediate/i3_worst_ranked.sql) | Worst ranked | `RANK` vs `ROW_NUMBER`, `NTILE`, filtering window results outside | `vitals`, `patients` |
| I4 | [`i4_window_frames.sql`](intermediate/i4_window_frames.sql) | Window frames | Running vs trailing frames (`ROWS BETWEEN`), `ROWS` vs `RANGE`, running `COUNT` | `vitals`, `patients` |
| I5 | [`i5_lead_first_last.sql`](intermediate/i5_lead_first_last.sql) | Lead and first/last | `LEAD`, `FIRST_VALUE` / `LAST_VALUE`, named `WINDOW`, the default-frame trap | `vitals`, `patients` |
| I6 | [`i6_dense_rank.sql`](intermediate/i6_dense_rank.sql) | Dense rank | `ROW_NUMBER` vs `RANK` vs `DENSE_RANK`, `PERCENT_RANK`, ranking a cagg | `vitals_hourly` |
| D1 | [`d1_dimension_modeling.sql`](intermediate/d1_dimension_modeling.sql) | Dimension modeling | Long-format fact, multi-dimension joins, time-overlap join, derived dimensions | `readings`, `patients`, `encounters` |

## Advanced

| # | File | Lesson | Concepts | Tables |
| --- | --- | --- | --- | --- |
| A1 | [`a1_desaturation_episodes.sql`](advanced/a1_desaturation_episodes.sql) | Desaturation episodes | Gap-and-islands (`LAG` + running `SUM` + `GROUP BY`) | `vitals`, `patients` |
| A2 | [`a2_alarm_sessions.sql`](advanced/a2_alarm_sessions.sql) | Alarm sessions | Sessionization / burst collapsing, `LAG(time)`, running `SUM` | `vitals`, `patients` |
| A3 | [`a3_observed_vs_truth.sql`](advanced/a3_observed_vs_truth.sql) | Observed vs truth | Resampling (`time_bucket` + median `percentile_cont`), join, bias | `vitals`, `vitals_truth`, `patients` |
| A4 | [`a4_lateral_latest.sql`](advanced/a4_lateral_latest.sql) | Lateral latest | `JOIN LATERAL`, correlated latest-row per patient, `ON TRUE` | `patients`, `encounters`, `vitals` |
| A5 | [`a5_delta_alerts.sql`](advanced/a5_delta_alerts.sql) | Delta alerts | `LAG` step-diff, NULL guard, `ABS` threshold, filtering computed deltas | `vitals` |
| A6 | [`a6_percentile_outliers.sql`](advanced/a6_percentile_outliers.sql) | Percentile outliers | `percentile_cont` vs `percentile_disc`, median vs mean, `COUNT(*) FILTER` | `vitals_truth` |
| A7 | [`a7_distinct_on_latest.sql`](advanced/a7_distinct_on_latest.sql) | Distinct on latest | `DISTINCT ON`, the leading-`ORDER BY` contract, idiom comparison | `patients`, `vitals` |
| A8 | [`a8_local_extrema.sql`](advanced/a8_local_extrema.sql) | Local extrema | `LAG` + `LEAD`, local maxima, prominence, 3-row frame | `vitals`, `patients` |
| A9 | [`a9_episode_reframe.sql`](advanced/a9_episode_reframe.sql) | Episode reframe | Gap-and-islands on a two-sided band, nested-window workaround | `vitals_truth`, `patients` |
| A10 | [`a10_explain_selectivity.sql`](advanced/a10_explain_selectivity.sql) | Explain selectivity | `EXPLAIN (ANALYZE, BUFFERS)`, sargable predicates, chunk exclusion | `vitals`, `patients` |
| R1 | [`r1_recursive_cte.sql`](advanced/r1_recursive_cte.sql) | Recursive CTE | `WITH RECURSIVE` + `UNION ALL`, fixpoint join | `vitals_truth`, `patients` |
| G1 | [`g1_gap_fill.sql`](advanced/g1_gap_fill.sql) | Gap fill | `time_bucket_gapfill`, `locf`, sample counts | `vitals`, `patients` |
| C1 | [`c1_continuous_aggregates.sql`](advanced/c1_continuous_aggregates.sql) | Continuous aggregates | Cagg vs manual rollup, full join, re-bucketing | `vitals`, `vitals_hourly` |

## Concept index

| Concept | Lessons |
| --- | --- |
| `INNER JOIN` / `LEFT JOIN` | B1, B3 |
| Multi-dimension & time-overlap joins | D1 |
| `JOIN LATERAL` | A4 |
| `DISTINCT ON` | A7 |
| Common table expressions (CTEs) | B2, B3 (and every advanced lesson) |
| `time_bucket` binning | B2, A3, C1 |
| Window functions — `LAG` | I1, A1, A2, A5, A9 |
| Window functions — `LEAD` | I5, A8 |
| Window functions — frames (`ROWS` / `RANGE`) | I2, I4, A8, A9 |
| Window functions — `RANK` / `ROW_NUMBER` / `NTILE` | I3 |
| Window functions — `DENSE_RANK` / `PERCENT_RANK` | I6 |
| Window functions — `FIRST_VALUE` / `LAST_VALUE` | I5 |
| Running aggregates & totals | I4, A1, A2, A9 |
| Gap-and-islands / sessionization | A1, A2, A9, R1 |
| Recursive CTEs | R1 |
| Gap filling & interpolation | G1 |
| Percentiles / robust medians | A3, A6 |
| Conditional aggregation (`FILTER`) | A6 |
| Step-change / outlier detection | A5, A6, A8 |
| Query plans & sargable predicates | A10 |
| Continuous aggregates | C1 |
| Hypertables & compression | all lessons (`vitals*`), see [data model](../../docs/data_model.md) |

## A note on the data

- `vitals` is written by **both** the backfill and the live Telegraf stream, so
  its row count grows while the stack runs. Lessons over `vitals` naturally
  show more rows over time.
- `vitals_truth`, `readings`, and `vitals_hourly` are produced by the backfill
  only, so they are stable for a given commit.

## Related documentation

- [Data model](../../docs/data_model.md) — tables, hypertables, views, caggs
- [Testing](../../docs/testing.md) — how the lessons are validated
- [Scope](../../docs/scope.md) — personas and what the lab delivers
- [Data flow](../../docs/data_flow.md) — where the queried data comes from
