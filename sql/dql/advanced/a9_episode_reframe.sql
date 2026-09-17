-- lesson: episode reframe (out-of-band HR)
-- tier: advanced
-- a1 found desaturation episodes with a one-sided threshold on SpO2. Here we
-- block the SAME gap-and-islands pattern around a two-sided band: Cole
-- (W10002) has tachycardia, so we flag every tick whose heart rate is
-- outside a resting 60-100 bpm band, then collapse the flagged ticks into
-- distinct episodes.
--
-- Concepts taught
--   * Reusing gap-and-islands on a new question: flag -> detect the 0->1
--     transition with LAG -> running SUM for the island id -> GROUP BY
--   * A band condition: x NOT BETWEEN low AND high (equivalent to below OR
--     above), versus a1's single-sided `x < threshold`
--   * Window functions cannot be nested: compute LAG in one CTE, then the
--     running SUM in the next -- the same two-step split a1 uses
--   * COALESCE(LAG(...), 0): the first tick of the partition has no previous
--     flag, and treating it as 0 starts an episode correctly
--   * ROWS-based frames for the running SUM; note how RANGE would behave the
--     same here because time is unique
--
-- We read vitals_truth so the episodes reflect the true rhythm, not monitor
-- noise, and report the range each episode actually spanned.
-- ============================================================================

WITH flagged AS (
    SELECT
        time,
        heart_rate_bpm,
        CASE WHEN heart_rate_bpm NOT BETWEEN 60 AND 100 THEN 1 ELSE 0 END AS out_of_band
    FROM vitals_truth
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10002')
),
transitions AS (
    SELECT
        time,
        heart_rate_bpm,
        out_of_band,
        COALESCE(LAG(out_of_band) OVER (ORDER BY time), 0) AS previous_out_of_band
    FROM flagged
),
islands AS (
    SELECT
        time,
        heart_rate_bpm,
        out_of_band,
        SUM(
            CASE
                WHEN out_of_band = 1 AND previous_out_of_band = 0
                THEN 1 ELSE 0
            END
        ) OVER (
            ORDER BY time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS episode_id
    FROM transitions
)
SELECT
    episode_id,
    MIN(time)                                            AS episode_start,
    MAX(time)                                            AS episode_end,
    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::INT     AS duration_seconds,
    COUNT(*)                                             AS readings,
    ROUND(MIN(heart_rate_bpm)::NUMERIC, 1)               AS lowest_hr,
    ROUND(MAX(heart_rate_bpm)::NUMERIC, 1)               AS highest_hr
FROM islands
WHERE out_of_band = 1
GROUP BY episode_id
ORDER BY episode_start
