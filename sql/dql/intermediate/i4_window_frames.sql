-- lesson: window frames
-- tier: intermediate
-- The worsening patient's chart needs two derived lines the raw monitor does
-- not draw: a RUNNING average of heart rate since admission, and a TRAILING
-- 6-reading average that only looks backwards. i2 used a centered frame
-- (3 PRECEDING AND 3 FOLLOWING); this lesson pins the frame down explicitly
-- and shows the running-total shape that real-time monitoring relies on.
--
-- Concepts taught
--   * OVER (...) with no frame defaults to RANGE UNBOUNDED PRECEDING AND
--     CURRENT ROW -- i.e. a running aggregate over the partition so far
--   * ROWS BETWEEN ... PRECEDING AND CURRENT ROW -- a trailing window that
--     never looks into the future, safe to render in real time
--   * ROWS counts physical rows; RANGE groups "peers" that tie on ORDER BY
--     (with a unique time key the two coincide)
--   * COUNT(*) OVER (...) as a running row counter
--
-- We show the first day (2026-01-01) of Naomi (W10001) so the frame effects
-- are visible without scrolling through a whole month.
-- ============================================================================

SELECT
    time,
    ROUND(heart_rate_bpm::NUMERIC, 1) AS heart_rate_bpm,
    COUNT(*) OVER (
        PARTITION BY patient_id
        ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS readings_so_far,
    ROUND((AVG(heart_rate_bpm) OVER (
        PARTITION BY patient_id
        ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ))::NUMERIC, 2) AS running_avg_hr,
    ROUND((AVG(heart_rate_bpm) OVER (
        PARTITION BY patient_id
        ORDER BY time
        ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ))::NUMERIC, 2) AS trailing_6_avg_hr
FROM vitals
WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
  AND time >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND time <  TIMESTAMPTZ '2026-01-02 00:00:00+00'
ORDER BY time
