# src/health_checks.py
# Automated health checks that run before and after each pipeline run.
# Think of this as the pipeline's self-diagnostic system.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime       import datetime, timezone, timedelta
from src.database   import get_db_cursor
from src.logger     import get_logger
from src.alerting   import alerter

logger = get_logger(__name__)


def check_database_health() -> bool:
    """Verify database is reachable and tables exist."""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM weather_readings")
            row    = cursor.fetchone()
            count  = row["cnt"]
            logger.info(f"Database healthy — {count:,} weather readings total")
            return True
    except Exception as e:
        alerter.critical("Database health check failed", {"error": str(e)})
        return False


def check_data_freshness() -> bool:
    """
    Verify we have recent data — detect silent extraction failures.
    If no data has loaded in 25 hours, something is broken.
    """
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT
                    MAX(recorded_at)                    AS latest,
                    NOW() - MAX(recorded_at)            AS age,
                    COUNT(*)                            AS readings_last_24h
                FROM weather_readings
                WHERE recorded_at >= NOW() - INTERVAL '24 hours'
            """)
            row = cursor.fetchone()

            if row["readings_last_24h"] == 0:
                alerter.critical(
                    "No weather data loaded in last 24 hours",
                    {"latest_reading": str(row["latest"])}
                )
                return False

            logger.info(
                f"Data freshness OK — "
                f"{row['readings_last_24h']} readings in last 24h, "
                f"latest: {row['latest']}"
            )
            return True

    except Exception as e:
        alerter.critical("Freshness check failed", {"error": str(e)})
        return False


def check_data_anomalies() -> list[str]:
    """
    Statistical anomaly detection on recent data.
    Flags readings that are more than 3 standard deviations
    from the city's historical mean — a classic z-score check.
    """
    anomalies = []

    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                WITH city_stats AS (
                    SELECT
                        city_id,
                        AVG(temperature_c)    AS mean_temp,
                        STDDEV(temperature_c) AS std_temp
                    FROM weather_readings
                    GROUP BY city_id
                ),
                recent AS (
                    SELECT
                        wr.id,
                        c.name          AS city,
                        wr.temperature_c,
                        wr.recorded_at
                    FROM weather_readings wr
                    JOIN cities c ON wr.city_id = c.id
                    WHERE wr.recorded_at >= NOW() - INTERVAL '2 hours'
                )
                SELECT
                    r.city,
                    r.temperature_c,
                    s.mean_temp,
                    s.std_temp,
                    ABS(r.temperature_c - s.mean_temp)
                        / NULLIF(s.std_temp, 0) AS z_score
                FROM recent r
                JOIN city_stats s ON
                    (SELECT id FROM cities WHERE name = r.city) = s.city_id
                WHERE ABS(r.temperature_c - s.mean_temp)
                      / NULLIF(s.std_temp, 0) > 3
            """)

            rows = cursor.fetchall()
            for row in rows:
                msg = (
                    f"Anomaly: {row['city']} temperature {row['temperature_c']}°C "
                    f"is {row['z_score']:.1f} standard deviations from mean "
                    f"({row['mean_temp']:.1f}°C)"
                )
                anomalies.append(msg)
                alerter.warning(msg)

    except Exception as e:
        logger.error(f"Anomaly check failed: {e}")

    return anomalies


def run_all_checks() -> bool:
    """
    Run all health checks. Returns True if pipeline is healthy.
    Called at the start of each pipeline run.
    """
    logger.info("Running pipeline health checks...")

    db_ok        = check_database_health()
    freshness_ok = check_data_freshness()
    anomalies    = check_data_anomalies()

    all_ok = db_ok and freshness_ok

    if all_ok:
        logger.info("All health checks passed ✓")
    else:
        logger.error("Health checks FAILED — review alerts before proceeding")

    return all_ok