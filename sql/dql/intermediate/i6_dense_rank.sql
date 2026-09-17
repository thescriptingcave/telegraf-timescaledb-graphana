-- lesson: dense rank
-- tier: intermediate
-- For each patient, rank the hours by average heart rate from highest to
-- lowest. i3 showed RANK and NTILE; this lesson puts the three ranking
-- families side by side so the tie behaviour is obvious:
--
--   ROW_NUMBER -> always unique (1, 2, 3, 4)
--   RANK       -> ties share a rank, then it SKIPS (1, 1, 3)
--   DENSE_RANK -> ties share a rank, then is CONTIGUOUS (1, 1, 2)
--
-- Concepts taught
--   * ROW_NUMBER vs RANK vs DENSE_RANK, and when the difference matters
--   * PERCENT_RANK(): this row's relative standing in [0, 1]
--   * Ranking a pre-aggregated continuous aggregate (vitals_hourly) instead
--     of the raw hypertable -- same window logic, far fewer rows
--   * Filtering the ranked rows OUTSIDE the window via a CTE
--
-- We keep the top 3 hours per patient so the whole ward fits on one page.
-- ============================================================================

WITH ranked AS (
    SELECT
        mrn,
        scenario,
        bucket,
        ROUND(heart_rate_bpm::NUMERIC, 1)                          AS avg_hr,
        ROW_NUMBER() OVER w                                        AS row_num,
        RANK()       OVER w                                        AS rank_with_gaps,
        DENSE_RANK() OVER w                                        AS dense_rank_no_gaps,
        ROUND((PERCENT_RANK() OVER w)::NUMERIC, 3)                 AS pct_rank
    FROM vitals_hourly
    WHERE n > 0
    WINDOW w AS (PARTITION BY patient_id ORDER BY heart_rate_bpm DESC)
)
SELECT
    mrn,
    scenario,
    bucket,
    avg_hr,
    rank_with_gaps,
    dense_rank_no_gaps,
    pct_rank
FROM ranked
WHERE row_num <= 3
ORDER BY mrn, row_num
