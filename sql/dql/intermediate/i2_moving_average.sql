-- lesson: moving average
-- tier: intermediate
-- A spikey reading looks alarming, but the bedroom monitor has known
-- measurement noise. We want to compare the RAW reading against a SMOOTHED
-- reading (a centered 7-reading moving average, i.e. roughly +/- 3 readings
-- either side) to tell transient spikes apart from sustained trends.
--
-- Concepts taught
--   * Moving-average window: AVG() OVER (PARTITION BY ...
--     ORDER BY ... ROWS BETWEEN n PRECEDING AND n FOLLOWING)
--   * The idea that smoothing trades away sharpness for stability -- in the
--     chart you will SEE spikes appear and vanish in the smoothed line
--   * A paired comparison: for each reading, how far it is from its window
--
-- We compare Naomi (the desaturating patient) against Ivy (the stable
-- control) -- same monitor profile, very different physiology.
-- ============================================================================

WITH smoothed AS (
    SELECT
        v.time,
        p.display_name,
        v.spo2_pct,
        ROUND(AVG(v.spo2_pct) OVER (
            PARTITION BY v.patient_id
            ORDER BY v.time
            ROWS BETWEEN 3 PRECEDING AND 3 FOLLOWING
        )::NUMERIC, 2) AS spo2_ma
    FROM vitals v
    JOIN patients p
        ON p.patient_id = v.patient_id
    WHERE v.patient_id IN (
        SELECT patient_id FROM patients WHERE mrn IN ('W10001', 'W10003')
    )
)
SELECT
    time,
    display_name,
    ROUND(spo2_pct::NUMERIC, 1)        AS raw_spo2,
    spo2_ma,
    ROUND((spo2_pct - spo2_ma)::NUMERIC, 2) AS deviation_from_average
FROM smoothed
ORDER BY time, display_name
