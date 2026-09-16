-- lesson: first spo2 drop
-- tier: intermediate
-- The quality team wants the exact reading where Naomi (W10001) started to
-- deteriorate: the first tick where SpO2 crossed BELOW 94% after being at or
-- above it. Report the reading before and the reading after.
--
-- Concepts taught
--   * LAG(value, 1) OVER (...) -- look at the PREVIOUS row in a window
--   * PARTITION BY patient_id + ORDER BY time -- the window definition
--   * A "state transition" read: previous >= threshold AND current <
--     threshold. This is how you find the START of an event in data without
--     an event table -- you will meet the same idea again in the advanced
--     lessons and turn it into episode boundaries.
--
-- Try: raise the threshold to 90 and watch the crossing move later, closer
-- to the deep plateau of Naomi's hypoxemia.
-- ============================================================================

WITH tagged AS (
    SELECT
        v.time,
        v.spo2_pct,
        LAG(v.spo2_pct, 1) OVER (
            PARTITION BY v.patient_id
            ORDER BY v.time
        ) AS previous_spo2
    FROM vitals v
    WHERE v.patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
)
SELECT
    time,
    ROUND(previous_spo2::NUMERIC, 1) AS spo2_before,
    ROUND(spo2_pct::NUMERIC, 1)      AS spo2_after
FROM tagged
WHERE previous_spo2 >= 94 AND spo2_pct < 94
ORDER BY time
