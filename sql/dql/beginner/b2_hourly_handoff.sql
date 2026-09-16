-- lesson: hourly handoff
-- tier: beginner
-- At shift change the oncoming nurse asks: "for every monitored patient,
-- what did each vital look like on average every hour?" The summary is the
-- handoff sheet: one row per patient per clock-hour.
--
-- Concepts taught
--   * Binning time with time_bucket('1 hour', time) -- the TimescaleDB bread
--     and butter of every time-series analysis
--   * GROUP BY patient + hour, with AVG() per vital
--   * ROUND() to keep the report readable (Postgres rounds NUMERIC, so we
--     cast the AVG() result before rounding)
--   * A Common Table Expression (WITH hourly AS (...)) so the final SELECT is
--     a clean reading of an already-shaped table
--   * A simple JOIN back to patients to resolve display names
--
-- Read it top-down: WITH builds the "hourly" table, the main SELECT joins
-- it back to patient names and sorts it.
--
-- We filter to the first three ward admissions so the report stays on one
-- page; remove the WHERE to summarize the whole ward.
-- ============================================================================

WITH hourly AS (
    SELECT
        patient_id,
        time_bucket('1 hour', time) AS bucket,
        ROUND(AVG(heart_rate_bpm)::NUMERIC, 1)       AS avg_heart_rate,
        ROUND(AVG(spo2_pct)::NUMERIC, 1)             AS avg_spo2,
        ROUND(AVG(respiration_rate_bpm)::NUMERIC, 1) AS avg_respiration,
        ROUND(AVG(temperature_c)::NUMERIC, 2)        AS avg_temperature,
        COUNT(*)                                     AS readings
    FROM vitals
    WHERE mrn IN ('W10001', 'W10002', 'W10003')
    GROUP BY patient_id, bucket
)
SELECT
    h.bucket    AS shift_hour,
    p.display_name,
    h.avg_heart_rate,
    h.avg_spo2,
    h.avg_respiration,
    h.avg_temperature,
    h.readings
FROM hourly h
JOIN patients p
    ON p.patient_id = h.patient_id
ORDER BY h.bucket, p.display_name
