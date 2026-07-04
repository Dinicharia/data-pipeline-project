# src/loader.py
# Loads cleaned DataFrames into PostgreSQL.
#
# The critical design choice here: we use INSERT ... ON CONFLICT DO NOTHING
# everywhere. This means the pipeline is "idempotent" — you can run it
# ten times and the database ends up in exactly the same state as after
# one run. No duplicates, no errors, no manual cleanup needed.
#
# IDEMPOTENCY is a core Data Engineering principle. Pipelines fail and
# get restarted. They must handle that gracefully.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import psycopg2.extras                # for execute_values — bulk insert

from src.database   import get_db_cursor
from src.logger     import get_logger
from src.exceptions import LoadError

logger = get_logger(__name__)


def load_weather_readings(df: pd.DataFrame) -> int:
    """
    Load cleaned weather data into the weather_readings table.

    Uses execute_values() for bulk insert — far faster than inserting
    one row at a time (100 rows at once vs 100 individual round-trips
    to the database).

    Args:
        df: Cleaned weather DataFrame from weather_transformer.py

    Returns:
        Number of rows actually inserted (may be less than len(df)
        if some rows already existed — ON CONFLICT DO NOTHING)
    """
    if df.empty:
        logger.warning("load_weather_readings called with empty DataFrame — skipping")
        return 0

    # Build list of tuples — psycopg2.extras.execute_values needs this format
    rows = [
        (
            int(row.city_id),
            float(row.temperature_c),
            int(row.humidity_pct),
            float(row.pressure_hpa)  if pd.notna(row.pressure_hpa)  else None,
            float(row.wind_speed_ms) if pd.notna(row.wind_speed_ms) else None,
            str(row.description),
            row.recorded_at.isoformat(),    # datetime → ISO string for psycopg2
        )
        for row in df.itertuples()
    ]

    sql = """
        INSERT INTO weather_readings
            (city_id, temperature_c, humidity_pct, pressure_hpa,
             wind_speed_ms, description, recorded_at)
        VALUES %s
        ON CONFLICT (city_id, recorded_at)
        DO NOTHING
    """
    # ON CONFLICT DO NOTHING:
    # If a row with this (city_id, recorded_at) already exists, silently
    # skip it. The pipeline can restart safely without creating duplicates.

    try:
        with get_db_cursor() as cursor:
            # execute_values sends all rows in one database round-trip
            psycopg2.extras.execute_values(cursor, sql, rows)

            # cursor.rowcount tells us how many rows were actually inserted
            # (rows skipped by ON CONFLICT DO NOTHING are not counted)
            inserted = cursor.rowcount
            logger.info(
                f"Weather: {inserted} rows inserted, "
                f"{len(rows) - inserted} duplicates skipped"
            )
            return inserted

    except Exception as e:
        raise LoadError(f"Failed to load weather readings: {e}") from e


def load_exchange_rates(df: pd.DataFrame) -> int:
    """
    Load cleaned exchange rates into the exchange_rates table.

    Args:
        df: Cleaned exchange rate DataFrame (long format)

    Returns:
        Number of rows inserted
    """
    if df.empty:
        logger.warning("load_exchange_rates called with empty DataFrame — skipping")
        return 0

    rows = [
        (
            str(row.base_currency),
            str(row.target_currency),
            float(row.rate),
            row.recorded_at.isoformat(),
        )
        for row in df.itertuples()
    ]

    sql = """
        INSERT INTO exchange_rates
            (base_currency, target_currency, rate, recorded_at)
        VALUES %s
        ON CONFLICT (base_currency, target_currency, recorded_at)
        DO NOTHING
    """

    try:
        with get_db_cursor() as cursor:
            psycopg2.extras.execute_values(cursor, sql, rows)
            inserted = cursor.rowcount
            logger.info(
                f"Exchange rates: {inserted} rows inserted, "
                f"{len(rows) - inserted} duplicates skipped"
            )
            return inserted

    except Exception as e:
        raise LoadError(f"Failed to load exchange rates: {e}") from e


def refresh_materialized_view() -> None:
    """
    Refresh the mv_city_stats materialized view after loading new data.
    Called at the end of each successful pipeline run.
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute("REFRESH MATERIALIZED VIEW mv_city_stats")
            logger.info("Materialized view mv_city_stats refreshed")

    except Exception as e:
        # Non-fatal — log it but don't fail the pipeline over a stale view
        logger.warning(f"Failed to refresh materialized view: {e}")