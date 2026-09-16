-- lesson: continuous aggregates
-- tier: advanced
-- vitals_hourly is a TimescaleDB continuous aggregate: the same query you
-- would write with a manual time_bucket + GROUP BY, but precomputed
-- incrementally by a refresh policy instead of scanned on every run.
--
-- Concepts taught
--   * What a continuous aggregate IS: a MATERIALIZED VIEW with
--     timescaledb.continuous, keyed on time_bucket, refreshed by policy;
--     querying it is a plain SELECT and needs no GROUP BY of its own
--   * Verifying it: rebuild the same hourly rollup by hand over vitals and
--     full-join them -- every row should match (rows where spo2_delta > 0
--     would be the bug to investigate)
--   * Caveats to expect: a WITH NO DATA aggregate returns nothing until the
--     first refresh, and by design it only covers the materialized < refresh
--     horizon -- recent hours will differ from the raw table until the
--     policy runs
--   * Rolling up higher: re-bucket the aggregate's own buckets with
--     time_bucket('1 month', bucket) to get a fast monthly summary without
--     ever touching the raw hypertable
-- ============================================================================

WITH manual_hourly AS (
    SELECT
        time_bucket('1 hour', time) AS bucket,
        patient_id,
        mrn,
        scenario,
        count(*)                              AS n,
        ROUND(avg(heart_rate_bpm)::NUMERIC, 4) AS heart_rate_bpm,
        ROUND(avg(spo2_pct)::NUMERIC, 4)       AS spo2_pct,
        ROUND(min(spo2_pct)::NUMERIC, 4)       AS spo2_pct_min
    FROM vitals
    GROUP BY 1, 2, 3, 4
)
SELECT
    h.bucket,
    h.patient_id,
    h.n            AS cagg_readings,
    m.n            AS manual_readings,
    h.spo2_pct     AS cagg_spo2,
    m.spo2_pct     AS manual_spo2,
    ROUND(ABS(h.spo2_pct - m.spo2_pct)::NUMERIC, 4) AS spo2_delta
FROM vitals_hourly h
JOIN manual_hourly m
    ON m.bucket = h.bucket
   AND m.patient_id = h.patient_id
   AND m.mrn = h.mrn
WHERE h.mrn = 'W10001'
  AND ROUND(ABS(h.spo2_pct - m.spo2_pct)::NUMERIC, 4) > 0.0001
ORDER BY h.bucket

-- Fast monthly summary straight off the continuous aggregate:
SELECT
    time_bucket('1 month', bucket) AS month,
    patient_id,
    mrn,
    count(DISTINCT bucket)         AS hours_covered,
    ROUND(avg(spo2_pct)::NUMERIC, 1) AS avg_spo2,
    ROUND(min(spo2_pct)::NUMERIC, 1) AS min_spo2
FROM vitals_hourly
GROUP BY 1, 2, 3
ORDER BY month, mrn
