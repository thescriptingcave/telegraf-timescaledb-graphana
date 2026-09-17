-- lesson: percentile outliers
-- tier: advanced
-- A single reading of "88% SpO2" means little on its own. Against the
-- patient's OWN distribution it means everything: is 88 the kind of number
-- this patient produces all the time, or is it in their worst 5%? This
-- lesson builds per-patient percentiles and counts the readings that fall
-- outside the 5th-95th band.
--
-- Concepts taught
--   * percentile_cont(p) WITHIN GROUP (ORDER BY x) -- interpolated percentile
--     (may return a value that never appeared in the data)
--   * percentile_disc(p) -- the DISCRETE percentile: an actual observed value
--   * Why the median (p50) is more robust than mean() when there are spikes:
--     compare the mean - median gap per patient
--   * COUNT(*) FILTER (WHERE condition) -- conditional aggregation
--
-- We read vitals_truth (clean, device-free, backfill only) so the outliers
-- reflect real physiology rather than monitor noise.
-- ============================================================================

WITH bounds AS (
    SELECT
        patient_id,
        mrn,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY spo2_pct) AS p05,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY spo2_pct) AS p50,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY spo2_pct) AS p95,
        avg(spo2_pct)                                          AS mean_spo2
    FROM vitals_truth
    GROUP BY patient_id, mrn
)
SELECT
    b.mrn,
    ROUND(b.p05::NUMERIC, 2)                 AS p05,
    ROUND(b.p50::NUMERIC, 2)                 AS median,
    ROUND(b.mean_spo2::NUMERIC, 2)           AS mean,
    ROUND((b.mean_spo2 - b.p50)::NUMERIC, 2) AS mean_minus_median,
    COUNT(*)                                 AS total_readings,
    COUNT(*) FILTER (WHERE t.spo2_pct < b.p05 OR t.spo2_pct > b.p95)
                                             AS outlier_readings
FROM vitals_truth t
JOIN bounds b
    ON b.patient_id = t.patient_id
GROUP BY b.mrn, b.p05, b.p50, b.mean_spo2, b.p95
ORDER BY b.mrn
