# src/pipeline_run.py
# Manages pipeline execution lifecycle:
#   - records each run in the pipeline_runs table
#   - ensures status is always updated (success OR failed)
#   - provides a clean decorator so any function can become a tracked stage

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import contextmanager
from src.database import get_db_cursor
from src.logger   import get_logger

logger = get_logger(__name__)


@contextmanager
def tracked_pipeline_run(pipeline_name: str):
    """
    Context manager that records a pipeline run in the audit table.

    Guarantees:
      - A 'running' record is created before any work starts
      - Status is updated to 'success' or 'failed' no matter what
      - Error messages are captured automatically on failure

    Usage:
        with tracked_pipeline_run("weather_etl") as run_id:
            # do pipeline work here
            # run_id is the integer ID of this run in pipeline_runs

    Args:
        pipeline_name: Human-readable name logged to pipeline_runs table
    """
    run_id = None

    try:
        # ── Start: create the 'running' record ──────────────────────────────
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT start_pipeline_run(%s)",
                (pipeline_name,)
            )
            run_id = cursor.fetchone()["start_pipeline_run"]
            logger.info(
                f"Pipeline '{pipeline_name}' started (run_id={run_id})"
            )

        yield run_id    # ← pipeline stages execute here

        # ── Success: update to 'success' ────────────────────────────────────
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT complete_pipeline_run(%s, %s, %s, %s)",
                (run_id, "success", 0, None)
            )
        logger.info(f"Pipeline '{pipeline_name}' completed successfully (run_id={run_id})")

    except Exception as e:
        # ── Failure: update to 'failed', capture the error message ──────────
        error_msg = str(e)[:500]    # truncate very long errors to fit the column
        if run_id:
            try:
                with get_db_cursor() as cursor:
                    cursor.execute(
                        "SELECT complete_pipeline_run(%s, %s, %s, %s)",
                        (run_id, "failed", 0, error_msg)
                    )
            except Exception as db_err:
                # If we can't even write the failure record, log it —
                # don't let this secondary failure hide the original one
                logger.error(f"Could not write failure status to DB: {db_err}")

        logger.error(
            f"Pipeline '{pipeline_name}' FAILED (run_id={run_id}): {error_msg}"
        )
        raise    # re-raise original exception so the caller knows it failed