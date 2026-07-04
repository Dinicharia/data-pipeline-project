# src/database_airflow.py
# Database connection that works both locally AND inside Airflow.
# When running in Airflow, uses Airflow's connection store.
# When running locally (python src/pipeline.py), uses config.py as before.
#
# This is the "environment-aware" pattern — same code, different
# connection strategy depending on where it's running.

import os
from contextlib import contextmanager

def is_running_in_airflow() -> bool:
    """
    Detect whether this code is executing inside an Airflow task.
    Airflow sets AIRFLOW_CTX_DAG_ID in the environment for every task.
    """
    return "AIRFLOW_CTX_DAG_ID" in os.environ


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Returns a database cursor, using the right connection method
    depending on whether we're inside Airflow or running locally.
    """
    if is_running_in_airflow():
        # ── Airflow path: use Airflow's connection store ─────────────────
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook   = PostgresHook(postgres_conn_id="postgres_pipeline")
        conn   = hook.get_conn()
        cursor = conn.cursor()

        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    else:
        # ── Local path: use our existing database.py ─────────────────────
        from src.database import get_db_cursor as local_cursor
        with local_cursor(commit=commit) as cursor:
            yield cursor