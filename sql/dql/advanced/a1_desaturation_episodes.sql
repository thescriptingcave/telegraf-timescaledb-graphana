-- lesson: desaturation episodes
-- tier: advanced
-- Naomi's SpO2 sat below 94% for the better part of an hour. But "below
-- 94%" is not one single long event -- the trace dips, recovers, dips
-- again. The clinical reviewer wants each DISTINCT episode: when each one
-- started, when it ended, how long it lasted and how low it got.
--
-- Concepts taught
--   * The gap-and-islands pattern -- the single most useful time-series
--     technique in this whole course
--   * Step 1: turn each reading into a flag (low = 1 below threshold)
--   * Step 2: use LAG() to detect where the flag TRANSITIONS 0 -> 1
--   * Step 3: a running SUM() of those transitions gives every contiguous
--     low stretch a shared bucket number (the "island")
--   * Step 4: GROUP BY the island and summarize
--   * Duration in Postgres: EXTRACT(EPOCH FROM interval)
--
-- Try it yourself: replace 94 with 90 (a much deeper desaturation) and
-- watch the underlying episode split out -- and notice why it might still
-- fragment near the edges of the plateau.
-- ============================================================================

WITH flagged AS (
    SELECT
        patient_id,
        time,
        spo2_pct,
        CASE WHEN spo2_pct < 94 THEN 1 ELSE 0 END AS is_low,
        LAG(CASE WHEN spo2_pct < 94 THEN 1 ELSE 0 END, 1) OVER (
            PARTITION BY patient_id
            ORDER BY time
        ) AS previous_is_low
    FROM vitals
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
),
islands AS (
    SELECT
        time,
        spo2_pct,
        is_low,
        SUM(
            CASE WHEN is_low = 1
                  AND (previous_is_low IS NULL OR previous_is_low = 0)
                 THEN 1 ELSE 0 END
        ) OVER (
            PARTITION BY patient_id
            ORDER BY time
            ROWS UNBOUNDED PRECEDING
        ) AS episode_id
    FROM flagged
)
SELECT
    MIN(time)                                            AS episode_start,
    MAX(time)                                            AS episode_end,
    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::INT     AS duration_seconds,
    COUNT(*)                                            AS readings,
    ROUND(MIN(spo2_pct)::NUMERIC, 1)                    AS lowest_spo2,
    ROUND(AVG(spo2_pct)::NUMERIC, 1)                    AS avg_spo2
FROM islands
WHERE is_low = 1
GROUP BY episode_id
ORDER BY episode_start
