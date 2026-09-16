-- ============================================================================
-- Ward vitals schema — TimescaleDB (Telemetry database)
--
-- Owned by the lab infrastructure: this file is mounted into
-- /docker-entrypoint-initdb.d for first-boot init AND applied idempotently by
-- `scripts/init_db.py`. Telegraf's outputs.postgresql plugin is configured
-- never to mutate this schema (create_templates = [], add_column_templates = []).
--
-- Tables:
--   patients   dimension — one row per synthetic patient
--   encounters dimension — one row per admission (patient x device x window)
--   vitals     hypertable — observed telemetry (written by backfill AND live)
--   vitals_truth hypertable — pre-device true physiology (offline backfill only)
--   readings   hypertable — long-format channel rows (offline backfill only)
--
-- Views/aggregates:
--   vitals_derived  — live SQL view: MAP, pulse pressure, shock index
--   vitals_hourly   — continuous aggregate for stable hourly queries
-- ============================================================================

-- TimescaleDB must exist before hypertables are created.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- Dimension tables
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS patients (
    patient_id     UUID        PRIMARY KEY,
    mrn            TEXT        NOT NULL UNIQUE,
    display_name   TEXT        NOT NULL,
    age            INTEGER     NOT NULL,
    sex            TEXT        NOT NULL,
    simulation_id  UUID        NOT NULL,
    scenario_label TEXT        NOT NULL,
    admitted_at    TIMESTAMPTZ NOT NULL,
    discharged_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS encounters (
    encounter_id BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   UUID        NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    device_id    UUID        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    ended_at     TIMESTAMPTZ,
    floor        TEXT        NOT NULL,
    room         TEXT        NOT NULL,
    UNIQUE (patient_id, started_at)
);

-- ----------------------------------------------------------------------------
-- Vitals hypertable (observed telemetry)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vitals (
    event_id             UUID           NOT NULL,
    time                 TIMESTAMPTZ    NOT NULL,
    patient_id           UUID           NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    mrn                  TEXT           NOT NULL,
    device_id            UUID           NOT NULL,
    sequence_number      BIGINT         NOT NULL,
    scenario             TEXT           NOT NULL,
    quality_code         TEXT           NOT NULL,
    device_status        TEXT           NOT NULL,
    heart_rate_bpm       DOUBLE PRECISION,
    spo2_pct             DOUBLE PRECISION,
    respiration_rate_bpm DOUBLE PRECISION,
    temperature_c        DOUBLE PRECISION,
    systolic_bp_mmhg     DOUBLE PRECISION,
    diastolic_bp_mmhg    DOUBLE PRECISION,
    -- TimescaleDB requires the partitioning column to be part of every
    -- unique index: the composite PK (time, event_id) doubles as the
    -- idempotency key for the ON CONFLICT inserts.
    PRIMARY KEY (time, event_id)
);

SELECT create_hypertable(
    'vitals',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS vitals_patient_time_idx
    ON vitals (patient_id, time DESC);
CREATE INDEX IF NOT EXISTS vitals_time_idx
    ON vitals (time DESC);

-- ----------------------------------------------------------------------------
-- Vitals truth hypertable (pre-device true physiology, offline only)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vitals_truth (
    event_id             UUID           NOT NULL,
    time                 TIMESTAMPTZ    NOT NULL,
    patient_id           UUID           NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    mrn                  TEXT           NOT NULL,
    sequence_number      BIGINT         NOT NULL,
    scenario             TEXT           NOT NULL,
    heart_rate_bpm       DOUBLE PRECISION,
    spo2_pct             DOUBLE PRECISION,
    respiration_rate_bpm DOUBLE PRECISION,
    temperature_c        DOUBLE PRECISION,
    systolic_bp_mmhg     DOUBLE PRECISION,
    diastolic_bp_mmhg    DOUBLE PRECISION,
    PRIMARY KEY (time, event_id)
);

SELECT create_hypertable(
    'vitals_truth',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS vitals_truth_patient_time_idx
    ON vitals_truth (patient_id, time DESC);

-- ----------------------------------------------------------------------------
-- Readings hypertable (long format: one row per channel per event)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS readings (
    reading_id  BIGINT         GENERATED ALWAYS AS IDENTITY,
    time        TIMESTAMPTZ    NOT NULL,
    patient_id  UUID           NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    mrn         TEXT           NOT NULL,
    sequence_number BIGINT     NOT NULL,
    channel     TEXT           NOT NULL,
    unit        TEXT           NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    source      TEXT           NOT NULL,
    quality_code TEXT          NOT NULL,
    PRIMARY KEY (time, reading_id),
    UNIQUE (time, patient_id, channel, sequence_number)
);

SELECT create_hypertable(
    'readings',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS readings_patient_channel_time_idx
    ON readings (patient_id, channel, time DESC);

-- ----------------------------------------------------------------------------
-- Derived vitals view (real-time compute layer, no storage)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW vitals_derived AS
SELECT
    time,
    patient_id,
    mrn,
    scenario,
    quality_code,
    device_status,
    heart_rate_bpm,
    spo2_pct,
    respiration_rate_bpm,
    temperature_c,
    systolic_bp_mmhg,
    diastolic_bp_mmhg,
    ROUND(CAST((2.0 * systolic_bp_mmhg + diastolic_bp_mmhg) / 3.0 AS NUMERIC), 1) AS map_mmhg,
    ROUND(CAST(systolic_bp_mmhg - diastolic_bp_mmhg AS NUMERIC), 1)             AS pulse_pressure_mmhg,
    ROUND(CAST(heart_rate_bpm / NULLIF(systolic_bp_mmhg, 0) AS NUMERIC), 3)     AS shock_index
FROM vitals;

-- ----------------------------------------------------------------------------
-- Continuous aggregate: hourly vitals
-- ----------------------------------------------------------------------------

-- Continuous aggregate: hourly vitals.
-- TimescaleDB does not support CREATE OR REPLACE on continuous aggregates,
-- so creation is guarded so the DDL stays idempotent across re-runs.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.continuous_aggregates
        WHERE view_name = 'vitals_hourly'
    ) THEN
        CREATE MATERIALIZED VIEW vitals_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', time) AS bucket,
            patient_id,
            mrn,
            scenario,
            count(*)                                                       AS n,
            avg(heart_rate_bpm)                                            AS heart_rate_bpm,
            min(heart_rate_bpm)                                            AS heart_rate_bpm_min,
            max(heart_rate_bpm)                                            AS heart_rate_bpm_max,
            avg(spo2_pct)                                                  AS spo2_pct,
            min(spo2_pct)                                                  AS spo2_pct_min,
            avg(respiration_rate_bpm)                                      AS respiration_rate_bpm,
            avg(temperature_c)                                             AS temperature_c,
            avg(systolic_bp_mmhg)                                          AS systolic_bp_mmhg,
            avg(diastolic_bp_mmhg)                                         AS diastolic_bp_mmhg
        FROM vitals
        GROUP BY bucket, patient_id, mrn, scenario
        WITH NO DATA;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_refresh_continuous_aggregate'
          AND hypertable_name = 'vitals_hourly'
    ) THEN
        PERFORM add_continuous_aggregate_policy(
            'vitals_hourly',
            start_offset => INTERVAL '3 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        );
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- Compression: compress chunks older than 3 days
-- ----------------------------------------------------------------------------

ALTER TABLE vitals SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'patient_id, scenario'
);

ALTER TABLE readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'patient_id, channel'
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'vitals'
    ) THEN
        PERFORM add_compression_policy(
            'vitals',
            INTERVAL '3 days'
        );
    END IF;
END
$$;