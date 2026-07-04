# src/database.py
# Manages all database connections for the pipeline.
# Every other file that needs the database imports from here —
# one place to manage connections, one place to fix connection issues.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2                           # PostgreSQL driver for Python
import psycopg2.extras                    # helpers: execute_values, RealDictCursor
from contextlib import contextmanager     # for clean connection handling

from src.config     import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from src.logger     import get_logger
from src.exceptions import LoadError

logger = get_logger(__name__)


def get_connection() -> psycopg2.extensions.connection:
    """
    Create and return a new PostgreSQL connection.

    WHY not a global connection?
    Global connections silently die after periods of inactivity —
    the server closes them but your code doesn't know. Creating a
    fresh connection per pipeline run avoids this completely.

    Returns:
        An open psycopg2 connection

    Raises:
        LoadError: if the connection cannot be established
    """
    try:
        conn = psycopg2.connect(
            host     = DB_HOST,
            port     = DB_PORT,
            dbname   = DB_NAME,
            user     = DB_USER,
            password = DB_PASSWORD,
            # Wait max 10 seconds for a connection before giving up
            connect_timeout = 10,
        )
        logger.debug(f"Connected to {DB_NAME} at {DB_HOST}:{DB_PORT}")
        return conn

    except psycopg2.OperationalError as e:
        raise LoadError(
            f"Cannot connect to database {DB_NAME} at {DB_HOST}:{DB_PORT}. "
            f"Is PostgreSQL running? Check your config/secrets.env. "
            f"Original error: {e}"
        )


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Context manager that provides a database cursor and handles
    transactions automatically.

    WHY a context manager?
    It guarantees the connection is ALWAYS closed, even if an exception
    occurs mid-pipeline. Without this, failed pipelines leak connections
    until the database runs out and refuses new ones.

    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("INSERT INTO ...")
        # connection automatically committed and closed here

    Args:
        commit: If True, commits on success. If False, always rolls back
                (useful for read-only operations and testing)

    Yields:
        A psycopg2 cursor using RealDictCursor
        (returns rows as dicts instead of tuples — much easier to work with)
    """
    conn   = None
    cursor = None

    try:
        conn   = get_connection()
        # RealDictCursor: rows come back as {"column": value} dicts
        # instead of plain tuples — much easier to work with
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        yield cursor     # ← pipeline code runs here

        if commit:
            conn.commit()
            logger.debug("Transaction committed")

    except Exception as e:
        if conn:
            conn.rollback()     # ← undo EVERYTHING if anything failed
            logger.error(f"Transaction rolled back due to: {e}")
        raise                   # ← re-raise so the pipeline knows it failed

    finally:
        # This block runs regardless of success or failure
        # Guaranteed cleanup — no leaked connections
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            logger.debug("Database connection closed")


def test_connection() -> bool:
    """
    Verify the database is reachable and our schema exists.
    Called at the start of every pipeline run.

    Returns:
        True if connection and schema are healthy
    """
    try:
        with get_db_cursor(commit=False) as cursor:
            # Simple query that confirms connection + our tables exist
            cursor.execute("""
                SELECT
                    COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'cities', 'weather_readings',
                      'exchange_rates', 'pipeline_runs'
                  )
            """)
            row = cursor.fetchone()
            table_count = row["table_count"]

            if table_count < 4:
                logger.warning(
                    f"Only {table_count}/4 expected tables found. "
                    f"Did you run sql/schema.sql?"
                )
                return False

            logger.info(
                f"Database connection healthy — "
                f"{table_count}/4 pipeline tables confirmed"
            )
            return True

    except LoadError as e:
        logger.error(f"Database health check failed: {e}")
        return False


if __name__ == "__main__":
    healthy = test_connection()
    print(f"\nDatabase healthy: {healthy}")