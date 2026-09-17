-- lesson: lateral latest
-- tier: advanced
-- The "current board" the charge nurse glances at: one row per patient with
-- their most recent good reading and where they are. The natural way to ask
-- "the latest row per patient" is a correlated subquery, but SQL makes the
-- row-per-group join awkward -- LATERAL (Postgres's implicit-LATERAL JOIN)
-- lets the inner query see the outer patient row directly.
--
-- Concepts taught
--   * JOIN LATERAL: like a correlated subquery in the FROM clause; the
--     right-hand side is re-evaluated for EVERY left-hand row
--   * ORDER BY ... LIMIT 1 inside the lateral block = the single latest row
--   * ON TRUE, because the lateral subquery already did the filtering
--   * How this compares to a row_number() window (i3) or DISTINCT ON (a7)
--     -- same answer, three idioms
--
-- The time bound is fixed at the end of the backfill so the "latest" row is
-- stable even while the live Telegraf stream keeps writing to vitals.
-- ============================================================================

SELECT
    p.display_name,
    p.mrn,
    e.floor,
    e.room,
    latest.time                     AS last_reading_at,
    ROUND(latest.heart_rate_bpm::NUMERIC, 1) AS heart_rate_bpm,
    ROUND(latest.spo2_pct::NUMERIC, 1)       AS spo2_pct,
    latest.quality_code
FROM patients p
JOIN encounters e
    ON e.patient_id = p.patient_id
JOIN LATERAL (
    SELECT v.time, v.heart_rate_bpm, v.spo2_pct, v.quality_code
    FROM vitals v
    WHERE v.patient_id = p.patient_id
      AND v.quality_code = 'GOOD'
      AND v.time < TIMESTAMPTZ '2026-01-31 00:00:00+00'
    ORDER BY v.time DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY p.mrn
