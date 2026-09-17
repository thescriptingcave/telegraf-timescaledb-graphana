-- lesson: distinct on latest
-- tier: advanced
-- The same "most recent reading per patient" question as a4, answered with
-- Postgres's DISTINCT ON. It is the tersest idiom for row-per-group, but it
-- has one non-obvious rule: the leading ORDER BY expressions must match the
-- DISTINCT ON expressions, and the rows that survive are the FIRST row per
-- group under that ordering.
--
-- Concepts taught
--   * DISTINCT ON (expr) keeps one row per distinct expr value
--   * The ORDER BY contract: it must START with the DISTINCT ON columns;
--     the remaining keys decide which row wins (v.time DESC = the latest)
--   * How the three idioms relate: LATERAL (a4), row_number() window (i3),
--     DISTINCT ON (here) -- same result, different ergonomics
--   * Why the bound is pinned to the end of the backfill: the live stream
--     keeps appending, so "latest" must be scoped to stay reproducible
-- ============================================================================

SELECT DISTINCT ON (p.mrn)
    p.mrn,
    p.display_name,
    v.time                                 AS last_reading_at,
    ROUND(v.spo2_pct::NUMERIC, 1)          AS spo2_pct,
    ROUND(v.heart_rate_bpm::NUMERIC, 1)    AS heart_rate_bpm,
    v.quality_code
FROM patients p
JOIN vitals v
    ON v.patient_id = p.patient_id
WHERE v.time < TIMESTAMPTZ '2026-01-31 00:00:00+00'
ORDER BY p.mrn, v.time DESC
