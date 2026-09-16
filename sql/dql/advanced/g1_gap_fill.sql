-- lesson: gap fill
-- tier: advanced
-- Every day each patient has two off-monitor windows during vitals sign
-- collection: 06:00-06:45 UTC and 18:30-19:15 UTC (bathroom / walk breaks),
-- so an hourly heart-rate series has gaps. time_bucket_gapfill() invents
-- the missing buckets and locf() (last-observation-carried-forward) fills
-- their value from the last known measurement.
--
-- Concepts taught
--   * time_bucket_gapfill(interval, time, start, finish) -- only valid when
--     the WHERE clause bounds time, and nothing else can reference the
--     unfilled bucket
--   * locf(agg) -- a TimescaleDB "interpolator" aggregate that fills gaps by
--     copying the previous non-null value forward
--   * count() of the raw samples per bucket so you can SEE which buckets
--     were synthesized rather than measured
--
-- We look at one day (2026-01-05) for Naomi (W10001), a day without a
-- desaturation, so the HR trace is quiet and gaps stand out in the count.
-- Try swapping locf() for interpolate() to get linear interpolation, or
-- drop the mrn filter to see several patients at once.
-- ============================================================================

SELECT
    time_bucket_gapfill(
        '1 hour',
        v.time,
        TIMESTAMPTZ '2026-01-05 00:00:00+00',
        TIMESTAMPTZ '2026-01-06 00:00:00+00'
    )                    AS bucket,
    locf(avg(v.heart_rate_bpm)) AS heart_rate_bpm_filled,
    count(v.heart_rate_bpm)     AS samples_in_bucket
FROM vitals v
WHERE v.patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
  AND v.time >= TIMESTAMPTZ '2026-01-05 00:00:00+00'
  AND v.time <  TIMESTAMPTZ '2026-01-06 00:00:00+00'
GROUP BY 1
ORDER BY bucket
