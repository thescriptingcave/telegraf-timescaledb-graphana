-- lesson: dimension modeling
-- tier: intermediate
-- readings is a long-format star-schema "fact" table: one row per
-- (patient, time, sequence_number, channel, source). dimensions such as
-- patients and encounters carry the descriptive attributes. A star-schema
-- query JOINs the fact to its dimensions and then slices by any combination
-- of dimensional attributes.
--
-- Business question
--   During daytime hours, how does observed SpO2 compare across age bands
--   and sexes, restricted to patients whose encounters put them on floor 2?
--
-- Concepts taught
--   * Long format: one row per channel, so we filter channel = 'spo2_pct'
--     and source = 'observed' before aggregating
--   * Joining facts to MULTIPLE dimensions (patients for demographics,
--     encounters for floor) -- the "star" hub in the middle of a dimension
--     model
--   * A time-overlap join to encounters: a reading belongs to an encounter
--     while started_at <= reading.time <= ended_at
--   * GROUP BY on dimensions you want the answer broken across (sex,
--     age band); CASE-created bands are derived dimensions
--
-- Note: EXTRACT(HOUR FROM time) uses the current TimeZone setting; the lab
-- timetable is UTC.
-- ============================================================================

WITH spo2_readings AS (
    SELECT
        r.patient_id,
        r.time,
        r.value AS spo2_pct
    FROM readings r
    WHERE r.channel = 'spo2_pct'
      AND r.source  = 'observed'
      AND EXTRACT(HOUR FROM r.time) BETWEEN 8 AND 17
)
SELECT
    CASE
        WHEN p.age < 50 THEN 'under 50'
        WHEN p.age < 65 THEN '50-64'
        ELSE '65+'
    END AS age_band,
    p.sex,
    ROUND(AVG(s.spo2_pct)::NUMERIC, 1) AS avg_spo2,
    ROUND(MIN(s.spo2_pct)::NUMERIC, 1) AS min_spo2,
    COUNT(*)                           AS readings
FROM spo2_readings s
JOIN patients p
    ON p.patient_id = s.patient_id
LEFT JOIN encounters e
    ON e.patient_id = s.patient_id
   AND e.started_at <= s.time
   AND (e.ended_at IS NULL OR e.ended_at >= s.time)
WHERE e.floor = '2'
GROUP BY 1, 2
ORDER BY avg_spo2 ASC NULLS LAST
