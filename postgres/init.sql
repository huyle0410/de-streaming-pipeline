CREATE DATABASE airflow;

\connect iot

CREATE TABLE IF NOT EXISTS sensor_readings (
    id BIGSERIAL PRIMARY KEY,
    sensor_id VARCHAR(32) NOT NULL,
    location VARCHAR(64) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    temperature_c DOUBLE PRECISION NOT NULL,
    humidity_pct DOUBLE PRECISION NOT NULL,
    ingested_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sensor_window_stats (
    id BIGSERIAL PRIMARY KEY,
    location VARCHAR(64) NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    avg_temperature_c DOUBLE PRECISION NOT NULL,
    max_temperature_c DOUBLE PRECISION NOT NULL,
    avg_humidity_pct DOUBLE PRECISION NOT NULL,
    reading_count INTEGER NOT NULL,
    UNIQUE (location, window_start)
);

CREATE TABLE IF NOT EXISTS daily_rollup (
    id BIGSERIAL PRIMARY KEY,
    rollup_date DATE NOT NULL,
    location VARCHAR(64) NOT NULL,
    avg_temperature_c DOUBLE PRECISION NOT NULL,
    max_temperature_c DOUBLE PRECISION NOT NULL,
    avg_humidity_pct DOUBLE PRECISION NOT NULL,
    reading_count INTEGER NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (rollup_date, location)
);
