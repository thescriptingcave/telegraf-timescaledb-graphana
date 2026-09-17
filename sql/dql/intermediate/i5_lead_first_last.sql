-- lesson: lead and first/last value
-- tier: intermediate
-- A handoff report wants a little context around each reading: the value
-- BEFORE it (LAG, from i1), the value AFTER it (LEAD), and the first and
-- last reading of the shift (FIRST_VALUE / LAST_VALUE). The classic trap is
-- LAST_VALUE: with the default frame it returns the CURRENT row, not the
-- last reading of the partition -- you must widen the frame explicitly.
--
-- Concepts taught
--   * LEAD(value, 1) -- the mirror image of LAG
--   * FIRST_VALUE(value) and LAST_VALUE(value) as window functions
--   * Why LAST_VALUE needs ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED
--     FOLLOWING to mean "last of the partition"
--   * A named WINDOW clause reused by several functions
--
-- One quiet day (2026-01-05) for Naomi (W10001) keeps the output readable.
-- ============================================================================

SELECT
    time,
    ROUND(heart_rate_bpm::NUMERIC, 1)                             AS heart_rate_bpm,
    ROUND((LAG(heart_rate_bpm, 1) OVER w)::NUMERIC, 1)            AS previous_hr,
    ROUND((LEAD(heart_rate_bpm, 1) OVER w)::NUMERIC, 1)           AS next_hr,
    ROUND((FIRST_VALUE(heart_rate_bpm) OVER w)::NUMERIC, 1)       AS first_hr_of_day,
    ROUND((LAST_VALUE(heart_rate_bpm) OVER (
        PARTITION BY patient_id
        ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ))::NUMERIC, 1)                                               AS last_hr_of_day
FROM vitals
WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
  AND time >= TIMESTAMPTZ '2026-01-05 00:00:00+00'
  AND time <  TIMESTAMPTZ '2026-01-06 00:00:00+00'
WINDOW w AS (PARTITION BY patient_id ORDER BY time)
ORDER BY time
