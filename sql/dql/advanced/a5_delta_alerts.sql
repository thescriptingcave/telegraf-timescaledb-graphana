-- lesson: delta alerts
-- tier: advanced
-- Sudden-change alarms do not care about the absolute value -- they care how
-- far a reading MOVED since the previous one. A heart rate that drifts from
-- 80 to 110 over an hour is a trend; one that jumps 80 -> 110 between two
-- 10-second ticks is an artifact or an event. This lesson turns the raw
-- stream into per-tick deltas and flags the jumps.
--
-- Concepts taught
--   * LAG(value) to subtract the previous reading from the current one
--   * The first row of a partition has a NULL previous value -- guard it
--     (WHERE previous IS NOT NULL) before doing arithmetic
--   * ABS() for two-sided change detection, plus a GREATEST-of-two threshold
--     idea you can extend to a percentage move
--   * Computing deltas in a CTE, then filtering on the computed column --
--     you cannot reference a window result in the same SELECT's WHERE
--
-- We sweep the whole ward for one day and order the biggest jumps first, so
-- the worst step changes surface immediately.
-- ============================================================================

WITH deltas AS (
    SELECT
        mrn,
        time,
        heart_rate_bpm,
        LAG(heart_rate_bpm) OVER (
            PARTITION BY patient_id
            ORDER BY time
        ) AS previous_hr
    FROM vitals
    WHERE quality_code <> 'LOST'
      AND time >= TIMESTAMPTZ '2026-01-02 00:00:00+00'
      AND time <  TIMESTAMPTZ '2026-01-03 00:00:00+00'
)
SELECT
    mrn,
    time,
    ROUND(previous_hr::NUMERIC, 1)                  AS previous_hr,
    ROUND(heart_rate_bpm::NUMERIC, 1)               AS heart_rate_bpm,
    ROUND((heart_rate_bpm - previous_hr)::NUMERIC, 1) AS delta_bpm
FROM deltas
WHERE previous_hr IS NOT NULL
  AND ABS(heart_rate_bpm - previous_hr) >= 15
ORDER BY ABS(heart_rate_bpm - previous_hr) DESC, time
