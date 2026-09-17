-- lesson: explain selectivity
-- tier: advanced
-- Why does one time filter fly through a hypertable and another crawl?
-- EXPLAIN (ANALYZE) is the ground truth: it runs the query and shows what
-- the planner actually did -- which chunks were pruned, whether an index was
-- used, how many rows were touched.
--
-- Concepts taught
--   * EXPLAIN (ANALYZE, BUFFERS) shows the real plan and its cost, not a guess
--   * Sargable predicates: `time >= X AND time < Y` lets the planner use the
--     index and skip whole chunks; wrapping the column -- `time_bucket('1
--     hour', time) = ...` or `date_trunc('day', time) = ...` -- usually forces
--     a scan because the column is hidden inside a function
--   * Hypertable chunk exclusion: a bounded time range prunes entire one-day
--     chunks before they are read
--   * Why a selective index scan on (patient_id, time DESC) beats a
--     sequential scan on a 10M-row hypertable
--
-- Run this, read the plan, then try the seductive-but-slow variant noted
-- below and compare the "Buffers" and "Actual Rows" numbers.
--
--   -- slower, non-sargable: the column is wrapped in a function
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT time, heart_rate_bpm FROM vitals
--   WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
--     AND date_trunc('day', time) = TIMESTAMPTZ '2026-01-10 00:00:00+00';
-- ============================================================================

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    time,
    heart_rate_bpm,
    spo2_pct
FROM vitals
WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
  AND time >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
  AND time <  TIMESTAMPTZ '2026-01-11 00:00:00+00'
ORDER BY time
