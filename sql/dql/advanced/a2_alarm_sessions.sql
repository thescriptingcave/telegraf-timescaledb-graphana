-- lesson: alarm sessions
-- tier: advanced
-- A device alarm that fires below 90% SpO2 would ring on nearly every 10
-- second tick while Naomi is desaturating -- useless for a tired clinician.
-- The alarm system should collapse a continuous burst into ONE event, and
-- start a NEW event only after 2 minutes of quiet. How many real alarms
-- actually fired, and what did each one cover?
--
-- Concepts taught
--   * Sessionization / event burst collapsing -- window functions at their
--     most business-valuable
--   * Filtering down to only the "alarm" readings first
--   * LAG(time) on the filtered stream to measure the gap to the previous
--     alarm, converted to seconds with EXTRACT(EPOCH FROM interval)
--   * A running SUM() that seeds a new session whenever the gap resets
--     (>= 120 seconds of quiet), otherwise continues the current one
--
-- Read the WITH chain top to bottom: hits (alarm ticks) -> gaps (time since
-- the last alarm) -> sessions (a bucket id per contiguous burst).
-- ============================================================================

WITH hits AS (
    SELECT
        time,
        spo2_pct
    FROM vitals
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
      AND spo2_pct < 90
),
gapped AS (
    SELECT
        time,
        spo2_pct,
        EXTRACT(EPOCH FROM (time - LAG(time, 1) OVER (ORDER BY time)))::INT
            AS seconds_since_last_alarm
    FROM hits
),
sessions AS (
    SELECT
        time,
        spo2_pct,
        SUM(
            CASE WHEN seconds_since_last_alarm IS NULL
                  OR seconds_since_last_alarm >= 120
                 THEN 1 ELSE 0 END
        ) OVER (
            ORDER BY time
            ROWS UNBOUNDED PRECEDING
        ) AS alarm_session
    FROM gapped
)
SELECT
    MIN(time)                          AS alarm_started,
    MAX(time)                          AS alarm_ended,
    ROUND(MIN(spo2_pct)::NUMERIC, 1)   AS lowest_spo2,
    ROUND(AVG(spo2_pct)::NUMERIC, 1)   AS avg_spo2,
    COUNT(*)                          AS alert_readings
FROM sessions
GROUP BY alarm_session
ORDER BY alarm_started
