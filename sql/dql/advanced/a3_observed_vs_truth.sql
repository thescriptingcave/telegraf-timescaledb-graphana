-- lesson: observed vs truth
-- tier: advanced
-- The bedside monitor is a measurement instrument: it adds noise, rounds
-- values, occasionally drops a reading. How big is the observed-vs-truth
-- error in practice, minute by minute? vitals_truth holds the pre-device
-- simulated physiology, so fidelity can be MEASURED.
--
-- Concepts taught
--   * WHY we also loaded a truth table: it holds the exact simulated
--     physiology for every tick, so fidelity can be measured against it
--   * RESAMPLING to a coarser grain with time_bucket + a robust median
--     (percentile_cont(0.5)); the median is robust to the occasional spike
--     that a mean would drag around
--   * A join between observed (vitals) and truth (vitals_truth) on shared
--     (patient, minute) buckets -- note that the schema also lets you align
--     tick-by-tick on (patient_id, sequence_number), since event_id differs
--   * A final comparison computing per-minute bias and absolute error
--
-- We focus on Naomi -- the patient whose trace mattered most that night.
-- ============================================================================

WITH observed AS (
    SELECT
        time_bucket('1 minute', time) AS minute_bucket,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY spo2_pct) AS observed_spo2
    FROM vitals
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
    GROUP BY 1
),
truth AS (
    SELECT
        time_bucket('1 minute', time) AS minute_bucket,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY spo2_pct) AS true_spo2
    FROM vitals_truth
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
    GROUP BY 1
)
SELECT
    o.minute_bucket,
    ROUND(o.observed_spo2::NUMERIC, 3)                    AS observed_spo2,
    ROUND(t.true_spo2::NUMERIC, 3)                        AS true_spo2,
    ROUND((o.observed_spo2 - t.true_spo2)::NUMERIC, 3)    AS bias,
    ROUND(ABS(o.observed_spo2 - t.true_spo2)::NUMERIC, 3) AS abs_error
FROM observed o
JOIN truth t
    ON t.minute_bucket = o.minute_bucket
ORDER BY o.minute_bucket
