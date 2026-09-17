-- lesson: local extrema
-- tier: advanced
-- A "peak" in a vital is a reading higher than the one before AND the one
-- after it. Finding those local maxima (and, by symmetry, local minima) is
-- how you turn a noisy trace into a short list of candidate events, and it
-- is the smallest interesting use of a 3-row frame.
--
-- Concepts taught
--   * LAG + LEAD together: looking both backwards and forwards in one pass
--   * A local maximum = current > previous AND current > next
--   * "Prominence": how far the peak stands above its higher neighbour,
--     computed with GREATEST(previous, next)
--   * The equivalent frame form: MAX(hr) OVER (ROWS BETWEEN 1 PRECEDING AND
--     1 FOLLOWING) -- useful when you want the neighbourhood extreme itself
--
-- We scan Cole (W10002, tachycardia) for one day and report every peak with
-- its prominence, biggest first. Swap the comparison operators to find
-- troughs instead.
-- ============================================================================

WITH neighbourhood AS (
    SELECT
        time,
        heart_rate_bpm,
        LAG(heart_rate_bpm)  OVER w AS previous_hr,
        LEAD(heart_rate_bpm) OVER w AS next_hr
    FROM vitals
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10002')
      AND quality_code <> 'LOST'
      AND time >= TIMESTAMPTZ '2026-01-03 00:00:00+00'
      AND time <  TIMESTAMPTZ '2026-01-04 00:00:00+00'
    WINDOW w AS (ORDER BY time)
)
SELECT
    time,
    ROUND(previous_hr::NUMERIC, 1)                                     AS previous_hr,
    ROUND(heart_rate_bpm::NUMERIC, 1)                                  AS peak_hr,
    ROUND(next_hr::NUMERIC, 1)                                         AS next_hr,
    ROUND((heart_rate_bpm - GREATEST(previous_hr, next_hr))::NUMERIC, 1) AS prominence_bpm
FROM neighbourhood
WHERE previous_hr IS NOT NULL
  AND next_hr IS NOT NULL
  AND heart_rate_bpm > previous_hr
  AND heart_rate_bpm > next_hr
ORDER BY prominence_bpm DESC, time
