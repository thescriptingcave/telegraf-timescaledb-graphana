-- lesson: flag attention
-- tier: beginner
-- It is 04:00 on the ward. Which patients spent the previous hour
-- (03:00-04:00) with an average SpO2 below 95%? The progressive-hypoxemia
-- patient is already dipping by day 2 of her stay, so one row should flag.
--
-- Concepts taught
--   * Filtering on a time window (BETWEEN-style range on time)
--   * Aggregating before filtering: AVG() can NOT go in WHERE, so we compute
--     it first (in a CTE) and then apply the threshold on the aggregate
--   * A LEFT JOIN, to keep patients even when they have no telemetry for the
--     window -- see the difference between INNER JOIN (B1) and LEFT JOIN here
--
-- Note: HAVING is how you filter a grouped aggregate directly; we use the
-- CTE + WHERE pattern to keep the logic readable and to make the report
-- columns available to the outer query.
--
-- The LEFT JOIN is the key learning this lesson: patients admitted later in
-- January (Marcus, Fatima, Diego) exist in the patients table but have no
-- telemetry on this day. An INNER JOIN would hide them entirely; a LEFT JOIN
-- keeps their rows with a NULL vitals summary.
-- ============================================================================

WITH previous_hour AS (
    SELECT
        patient_id,
        ROUND(AVG(spo2_pct)::NUMERIC, 1) AS avg_spo2,
        COUNT(*)                         AS readings
    FROM vitals
    WHERE time >= TIMESTAMPTZ '2026-01-02 03:00:00+00'
      AND time <  TIMESTAMPTZ '2026-01-02 04:00:00+00'
    GROUP BY patient_id
)
SELECT
    p.display_name,
    p.mrn,
    e.floor,
    e.room,
    ph.avg_spo2,
    ph.readings,
    CASE
        WHEN ph.avg_spo2 IS NULL THEN 'no telemetry'
        WHEN ph.avg_spo2 < 95     THEN 'needs attention'
        ELSE 'within range'
    END AS status
FROM patients p
LEFT JOIN encounters e
    ON e.patient_id = p.patient_id
LEFT JOIN previous_hour ph
    ON ph.patient_id = p.patient_id
ORDER BY ph.avg_spo2 ASC NULLS LAST
