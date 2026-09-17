-- lesson: recursive cte
-- tier: advanced
-- The gap-and-islands lesson (a1) used window functions. A recursive CTE is
-- the other classic way to assign episode IDs: walk the low-SpO2 ticks in
-- order and BRIDGE any tick that is consecutive to the previous one onto the
-- same episode, starting a new episode wherever the tick stream breaks.
--
-- Concepts taught
--   * WITH RECURSIVE + UNION ALL: anchor term (first low tick of each
--     patient) and a recursive term that visits the next tick
--   * A fixpoint-style join: o.rn = e.rn + 1 walks the rows exactly once
--   * "Consecutive" here means sequence_number = previous + 1 (the truth
--     table ticks every 10 seconds); a hole in the sequence starts a new
--     episode
--   * Postgres runs recursion until the working table is empty -- no explicit
--     terminator needed as long as each step moves strictly forward
--
-- We read from vitals_truth so the episodes reflect true physiology, free
-- of device noise. Naomi (W10001) is the progressive-hypoxemia patient.
-- The run is bounded to the first three days so the recursion stays snappy
-- (every day has many low ticks; an unbounded run over the whole month takes
-- roughly fifteen minutes because each recursive step re-scans the seed).
-- Adjust the mrn or widen/remove the time bound to explore other patients.
-- ============================================================================

WITH RECURSIVE low_ticks AS (
    SELECT
        patient_id,
        time,
        sequence_number,
        spo2_pct,
        ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY time) AS rn
    FROM vitals_truth
    WHERE patient_id = (SELECT patient_id FROM patients WHERE mrn = 'W10001')
      AND spo2_pct < 94
      AND time >= TIMESTAMPTZ '2026-01-01'
      AND time <  TIMESTAMPTZ '2026-01-04'
),
episodes AS (
    SELECT
        patient_id,
        time,
        sequence_number,
        spo2_pct,
        rn,
        sequence_number AS episode_seq_start,
        time           AS episode_start
    FROM low_ticks
    WHERE rn = 1
    UNION ALL
    SELECT
        lt.patient_id,
        lt.time,
        lt.sequence_number,
        lt.spo2_pct,
        lt.rn,
        CASE WHEN lt.sequence_number = e.sequence_number + 1
             THEN e.episode_seq_start
             ELSE lt.sequence_number END AS episode_seq_start,
        CASE WHEN lt.sequence_number = e.sequence_number + 1
             THEN e.episode_start
             ELSE lt.time END            AS episode_start
    FROM episodes e
    JOIN low_ticks lt
        ON lt.patient_id = e.patient_id
       AND lt.rn = e.rn + 1
),
summarized AS (
    SELECT
        patient_id,
        episode_seq_start                                  AS episode_id,
        MIN(time)                                          AS episode_start,
        MAX(time)                                          AS episode_end,
        EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::INT   AS duration_seconds,
        COUNT(*)                                           AS ticks,
        ROUND(MIN(spo2_pct)::NUMERIC, 1)                   AS lowest_spo2
    FROM episodes
    GROUP BY patient_id, episode_seq_start
)
SELECT
    p.display_name,
    s.episode_id,
    s.episode_start,
    s.episode_end,
    s.duration_seconds,
    s.ticks,
    s.lowest_spo2
FROM summarized s
JOIN patients p
    ON p.patient_id = s.patient_id
ORDER BY s.episode_start
