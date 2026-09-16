-- lesson: ward census
-- tier: beginner
-- The charge nurse wants the January ward roster: every admitted patient with
-- demographics, their admission/discharge window, and where they are camped.
--
-- Concepts taught
--   * Reading a table (SELECT from patients)
--   * INNER JOIN across two tables in the same database (patients <-> encounters)
--   * ORDER BY for a stable, readable result
--
-- Why INNER JOIN?
--   We only want rows that exist in BOTH tables. A patient row without a
--   matching encounter row disappears, and an encounter without a patient
--   row disappears too. (Lesson B3 demonstrates LEFT JOIN, which is what you
--   reach for when you want to KEEP the patient row anyway.)
-- ============================================================================

SELECT
    p.display_name,
    p.mrn,
    p.age,
    p.sex,
    p.scenario_label,
    p.admitted_at,
    p.discharged_at,
    e.floor,
    e.room,
    e.started_at,
    e.ended_at
FROM patients p
JOIN encounters e
    ON e.patient_id = p.patient_id
ORDER BY p.admitted_at
