-- sql/schema.sql
-- Complete database schema for the data pipeline project.
-- Run once to create all tables, indexes, views, and functions.
-- To reset: psql -U pipeline_user -d pipeline_db -f sql/schema.sql

-- ── Clean slate ───────────────────────────────────────────────────────────────
DROP VIEW  IF EXISTS v_weather_enriched    CASCADE;
DROP VIEW  IF EXISTS v_daily_city_summary  CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_city_stats CASCADE;
DROP TABLE IF EXISTS pipeline_runs         CASCADE;
DROP TABLE IF EXISTS exchange_rates        CASCADE;
DROP TABLE IF EXISTS weather_readings      CASCADE;
DROP TABLE IF EXISTS cities                CASCADE;
DROP FUNCTION IF EXISTS start_pipeline_run(VARCHAR);
DROP FUNCTION IF EXISTS complete_pipeline_run(INTEGER, VARCHAR, INTEGER, TEXT);


-- ── Tables ────────────────────────────────────────────────────────────────────

CREATE TABLE cities (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    country     VARCHAR(100) NOT NULL,
    latitude    NUMERIC(8,5) NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude   NUMERIC(8,5) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    timezone    VARCHAR(50),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cities_name_country UNIQUE (name, country)
);

CREATE TABLE weather_readings (
    id             SERIAL        PRIMARY KEY,
    city_id        INTEGER       NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
    temperature_c  NUMERIC(5,2)  NOT NULL CHECK (temperature_c  BETWEEN -90 AND 60),
    humidity_pct   INTEGER       NOT NULL CHECK (humidity_pct   BETWEEN 0 AND 100),
    pressure_hpa   NUMERIC(7,2)           CHECK (pressure_hpa  BETWEEN 800 AND 1100),
    wind_speed_ms  NUMERIC(5,2)           CHECK (wind_speed_ms  >= 0),
    description    VARCHAR(200),
    recorded_at    TIMESTAMPTZ   NOT NULL,
    loaded_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_reading_city_time UNIQUE (city_id, recorded_at)
);

CREATE TABLE exchange_rates (
    id               SERIAL        PRIMARY KEY,
    base_currency    CHAR(3)       NOT NULL,
    target_currency  CHAR(3)       NOT NULL,
    rate             NUMERIC(18,8) NOT NULL CHECK (rate > 0),
    recorded_at      TIMESTAMPTZ   NOT NULL,
    loaded_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rate_currencies_time UNIQUE (base_currency, target_currency, recorded_at)
);

CREATE TABLE pipeline_runs (
    id                 SERIAL       PRIMARY KEY,
    pipeline_name      VARCHAR(100) NOT NULL,
    status             VARCHAR(20)  NOT NULL CHECK (status IN ('running','success','failed','partial')),
    started_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at       TIMESTAMPTZ,
    records_extracted  INTEGER      DEFAULT 0,
    records_loaded     INTEGER      DEFAULT 0,
    error_message      TEXT,
    CONSTRAINT chk_run_times CHECK (completed_at IS NULL OR completed_at >= started_at)
);


-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX idx_weather_city_id     ON weather_readings(city_id);
CREATE INDEX idx_weather_recorded_at ON weather_readings(recorded_at DESC);
CREATE INDEX idx_weather_city_time   ON weather_readings(city_id, recorded_at DESC);
CREATE INDEX idx_rates_currencies    ON exchange_rates(base_currency, target_currency);
CREATE INDEX idx_rates_recorded_at   ON exchange_rates(recorded_at DESC);
CREATE INDEX idx_runs_name_status    ON pipeline_runs(pipeline_name, status);


-- ── Views ─────────────────────────────────────────────────────────────────────

CREATE VIEW v_weather_enriched AS
SELECT
    wr.id,
    c.name                                          AS city,
    c.country,
    c.timezone,
    c.latitude,
    c.longitude,
    wr.temperature_c,
    ROUND(wr.temperature_c * 9.0/5.0 + 32, 2)      AS temperature_f,
    wr.humidity_pct,
    wr.pressure_hpa,
    wr.wind_speed_ms,
    wr.description,
    wr.recorded_at,
    DATE(wr.recorded_at AT TIME ZONE c.timezone)    AS local_date,
    EXTRACT(HOUR FROM wr.recorded_at AT TIME ZONE c.timezone) AS local_hour
FROM weather_readings wr
JOIN cities c ON wr.city_id = c.id;

CREATE VIEW v_daily_city_summary AS
SELECT
    c.name                              AS city,
    c.country,
    DATE(wr.recorded_at)                AS date,
    COUNT(*)                            AS reading_count,
    ROUND(AVG(wr.temperature_c), 2)     AS avg_temp_c,
    MIN(wr.temperature_c)               AS min_temp_c,
    MAX(wr.temperature_c)               AS max_temp_c,
    ROUND(AVG(wr.humidity_pct), 1)      AS avg_humidity
FROM weather_readings wr
JOIN cities c ON wr.city_id = c.id
GROUP BY c.name, c.country, DATE(wr.recorded_at);

CREATE MATERIALIZED VIEW mv_city_stats AS
SELECT
    c.id                                AS city_id,
    c.name                              AS city,
    c.country,
    COUNT(*)                            AS total_readings,
    ROUND(AVG(wr.temperature_c), 2)     AS all_time_avg_temp,
    MIN(wr.temperature_c)               AS all_time_min_temp,
    MAX(wr.temperature_c)               AS all_time_max_temp,
    MIN(wr.recorded_at)                 AS first_reading_at,
    MAX(wr.recorded_at)                 AS latest_reading_at
FROM weather_readings wr
JOIN cities c ON wr.city_id = c.id
GROUP BY c.id, c.name, c.country;


-- ── Functions ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION start_pipeline_run(p_pipeline_name VARCHAR)
RETURNS INTEGER AS $$
DECLARE v_run_id INTEGER;
BEGIN
    INSERT INTO pipeline_runs (pipeline_name, status, started_at)
    VALUES (p_pipeline_name, 'running', NOW())
    RETURNING id INTO v_run_id;
    RETURN v_run_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION complete_pipeline_run(
    p_run_id         INTEGER,
    p_status         VARCHAR,
    p_records_loaded INTEGER,
    p_error_message  TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    UPDATE pipeline_runs
    SET status        = p_status,
        completed_at  = NOW(),
        records_loaded = p_records_loaded,
        error_message = p_error_message
    WHERE id = p_run_id;
END;
$$ LANGUAGE plpgsql;


-- ── Seed data ─────────────────────────────────────────────────────────────────

INSERT INTO cities (name, country, latitude, longitude, timezone) VALUES
    ('Nairobi',  'Kenya',          -1.28333,  36.81667, 'Africa/Nairobi'),
    ('London',   'United Kingdom', 51.50853,  -0.12574, 'Europe/London'),
    ('New York', 'United States',  40.71427, -74.00597, 'America/New_York'),
    ('Tokyo',    'Japan',          35.68950, 139.69171, 'Asia/Tokyo'),
    ('Sydney',   'Australia',     -33.86785, 151.20732, 'Australia/Sydney');