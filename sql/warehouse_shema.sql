-- sql/warehouse_schema.sql
-- Star schema for analytical queries on our pipeline data.
-- This would live in a separate database (or Snowflake/BigQuery
-- in production) — not mixed with our OLTP tables.

-- ── Dimension: Date ───────────────────────────────────────────────────────────
-- Pre-populated with every date — joins are instant
CREATE TABLE dim_date (
    date_id     INTEGER     PRIMARY KEY,   -- format: 20260701 (easy to read)
    full_date   DATE        NOT NULL UNIQUE,
    year        SMALLINT    NOT NULL,
    quarter     SMALLINT    NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month       SMALLINT    NOT NULL CHECK (month   BETWEEN 1 AND 12),
    month_name  VARCHAR(10) NOT NULL,
    week        SMALLINT    NOT NULL,
    day_of_week SMALLINT    NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name    VARCHAR(10) NOT NULL,
    is_weekend  BOOLEAN     NOT NULL
);

-- Populate dim_date for 5 years
INSERT INTO dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER        AS date_id,
    d                                       AS full_date,
    EXTRACT(YEAR    FROM d)::SMALLINT       AS year,
    EXTRACT(QUARTER FROM d)::SMALLINT       AS quarter,
    EXTRACT(MONTH   FROM d)::SMALLINT       AS month,
    TO_CHAR(d, 'Month')                     AS month_name,
    EXTRACT(WEEK    FROM d)::SMALLINT       AS week,
    EXTRACT(ISODOW  FROM d)::SMALLINT       AS day_of_week,
    TO_CHAR(d, 'Day')                       AS day_name,
    EXTRACT(ISODOW  FROM d) IN (6, 7)       AS is_weekend
FROM generate_series(
    '2024-01-01'::DATE,
    '2029-12-31'::DATE,
    '1 day'::INTERVAL
) AS d;


-- ── Dimension: City (SCD Type 2) ───────────────────────────────────────────
CREATE TABLE dim_city (
    city_key    SERIAL      PRIMARY KEY,    -- surrogate key
    city_id     INTEGER     NOT NULL,       -- natural key from OLTP
    name        VARCHAR(100) NOT NULL,
    country     VARCHAR(100) NOT NULL,
    timezone    VARCHAR(50),
    latitude    NUMERIC(8,5),
    longitude   NUMERIC(8,5),
    valid_from  DATE        NOT NULL DEFAULT CURRENT_DATE,
    valid_to    DATE        NOT NULL DEFAULT '9999-12-31',
    is_current  BOOLEAN     NOT NULL DEFAULT TRUE
);

INSERT INTO dim_city (city_id, name, country, timezone, latitude, longitude)
SELECT id, name, country, timezone, latitude, longitude
FROM cities;


-- ── Fact: Weather Readings ─────────────────────────────────────────────────
CREATE TABLE fact_weather_readings (
    reading_id      BIGSERIAL   PRIMARY KEY,
    -- Foreign keys to dimensions
    date_id         INTEGER     NOT NULL REFERENCES dim_date(date_id),
    city_key        INTEGER     NOT NULL REFERENCES dim_city(city_key),
    -- Degenerate dimensions (attributes with low cardinality stored here)
    description     VARCHAR(200),
    temp_category   VARCHAR(20),
    -- Measures (the actual facts)
    temperature_c   NUMERIC(5,2) NOT NULL,
    temperature_f   NUMERIC(5,2) NOT NULL,
    humidity_pct    INTEGER      NOT NULL,
    pressure_hpa    NUMERIC(7,2),
    wind_speed_ms   NUMERIC(5,2),
    -- Audit
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Columnar-style indexes for analytical queries
CREATE INDEX idx_fact_date   ON fact_weather_readings(date_id);
CREATE INDEX idx_fact_city   ON fact_weather_readings(city_key);
CREATE INDEX idx_fact_temp   ON fact_weather_readings(temperature_c);


-- ── Sample analytical queries ──────────────────────────────────────────────

-- Q: What was the average temperature per city per month in 2026?
SELECT
    dc.name                         AS city,
    dd.month_name,
    ROUND(AVG(f.temperature_c), 2)  AS avg_temp,
    COUNT(*)                        AS readings
FROM fact_weather_readings f
JOIN dim_city dc ON f.city_key  = dc.city_key
JOIN dim_date dd ON f.date_id   = dd.date_id
WHERE dd.year = 2026
  AND dc.is_current = TRUE
GROUP BY dc.name, dd.month, dd.month_name
ORDER BY dc.name, dd.month;

-- Q: Which cities were hottest on weekends vs weekdays?
SELECT
    dc.name                                     AS city,
    CASE WHEN dd.is_weekend THEN 'Weekend'
         ELSE 'Weekday' END                     AS day_type,
    ROUND(AVG(f.temperature_c), 2)              AS avg_temp
FROM fact_weather_readings f
JOIN dim_city dc ON f.city_key = dc.city_key
JOIN dim_date dd ON f.date_id  = dd.date_id
WHERE dc.is_current = TRUE
GROUP BY dc.name, dd.is_weekend
ORDER BY dc.name, dd.is_weekend;