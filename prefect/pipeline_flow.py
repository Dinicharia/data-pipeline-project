# prefect/pipeline_flow.py
# Our ETL pipeline rebuilt in Prefect.
# Compare this file to airflow/dags/pipeline_dag.py —
# same logic, dramatically less boilerplate.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from datetime import timedelta

from src.config     import DATA_DIR
from src.date_utils import make_filename


# ══════════════════════════════════════════════════════════════════
# EXTRACT TASKS
# @task decorator turns any Python function into a Prefect task.
#
# retries=2          → retry twice on failure (like Airflow's retries)
# retry_delay_seconds → wait between retries
# cache_key_fn       → if this task ran successfully with the same
#                      inputs today, skip it and return cached result
#                      This is something Airflow can't do natively.
# ══════════════════════════════════════════════════════════════════

@task(
    name="Extract Weather",
    retries=2,
    retry_delay_seconds=30,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=1),
)
def extract_weather() -> int:
    """Extract weather data for all monitored cities."""
    # get_run_logger() returns a logger that writes to Prefect's
    # UI dashboard — you see logs there just like Airflow's task logs
    logger = get_run_logger()

    from src.extractors.weather_extractor import extract_all_cities
    results = extract_all_cities()

    logger.info(f"Extracted weather for {len(results)} cities")
    return len(results)


@task(
    name="Extract Exchange Rates",
    retries=2,
    retry_delay_seconds=30,
)
def extract_exchange_rates() -> int:
    """Extract USD exchange rates."""
    logger = get_run_logger()

    from src.extractors.exchange_rate_extractor import extract_and_save
    data = extract_and_save()
    count = len(data.get("rates", {}))

    logger.info(f"Extracted {count} exchange rates")
    return count


@task(
    name="Extract GitHub Stats",
    retries=2,
    retry_delay_seconds=30,
)
def extract_github() -> int:
    """Extract GitHub repository statistics."""
    logger = get_run_logger()

    from src.extractors.github_extractor import extract_all_repos
    results = extract_all_repos()

    logger.info(f"Extracted stats for {len(results)} repositories")
    return len(results)


@task(
    name="Extract NASA APOD",
    retries=3,
    retry_delay_seconds=60,   # NASA rate limits need longer wait
)
def extract_nasa() -> int:
    """Extract NASA Astronomy Picture of the Day."""
    logger = get_run_logger()

    from src.extractors.nasa_extractor import extract_and_save
    results = extract_and_save()

    logger.info(f"Extracted {len(results)} NASA APOD records")
    return len(results)


# ══════════════════════════════════════════════════════════════════
# TRANSFORM TASKS
# Notice: tasks receive the OUTPUT of previous tasks directly
# as function arguments — no XCom.push/pull needed.
# Prefect tracks the dependency automatically.
# ══════════════════════════════════════════════════════════════════

@task(name="Transform Weather")
def transform_weather(extracted_count: int):
    """Clean and validate weather data."""
    logger = get_run_logger()

    from src.transformers.weather_transformer import transform_weather_file
    from src.transformers.quality_checks import (
        run_quality_gate, validate_weather_dataframe
    )

    filepath = DATA_DIR / "weather" / make_filename("weather_raw")
    df = transform_weather_file(filepath)
    df = run_quality_gate(df, validate_weather_dataframe)

    logger.info(f"Transformed {len(df)} weather rows (from {extracted_count} extracted)")
    return df    # return the actual DataFrame — Prefect handles serialization


@task(name="Transform Exchange Rates")
def transform_rates(extracted_count: int):
    """Clean and reshape exchange rate data."""
    logger = get_run_logger()

    from src.transformers.exchange_rate_transformer import transform_exchange_rates

    filepath = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")
    df = transform_exchange_rates(filepath)

    logger.info(f"Transformed {len(df)} exchange rate rows")
    return df


# ══════════════════════════════════════════════════════════════════
# LOAD TASKS
# ══════════════════════════════════════════════════════════════════

@task(name="Load Weather to PostgreSQL")
def load_weather(df) -> int:
    """Load cleaned weather data into PostgreSQL."""
    logger = get_run_logger()

    from src.loader import load_weather_readings
    n = load_weather_readings(df)

    logger.info(f"Loaded {n} weather rows to PostgreSQL")
    return n


@task(name="Load Exchange Rates to PostgreSQL")
def load_rates(df) -> int:
    """Load cleaned exchange rates into PostgreSQL."""
    logger = get_run_logger()

    from src.loader import load_exchange_rates
    n = load_exchange_rates(df)

    logger.info(f"Loaded {n} exchange rate rows to PostgreSQL")
    return n


@task(name="Refresh Materialized Views")
def refresh_views(weather_loaded: int, rates_loaded: int):
    """Refresh PostgreSQL materialized views after loading."""
    logger = get_run_logger()

    from src.loader import refresh_materialized_view
    refresh_materialized_view()

    logger.info(
        f"Views refreshed after loading "
        f"{weather_loaded} weather + {rates_loaded} rate rows"
    )


# ══════════════════════════════════════════════════════════════════
# THE FLOW — equivalent of an Airflow DAG
#
# This is just a Python function that calls tasks.
# Prefect builds the dependency graph by watching what calls what.
#
# Notice how much cleaner this is than the DAG file:
#   - No operators
#   - No explicit >> dependency declarations
#   - No XCom push/pull
#   - Results flow directly between functions
#   - Parallel execution declared with a simple list
# ══════════════════════════════════════════════════════════════════

@flow(
    name="Data Pipeline ETL",
    description="Daily ETL: extract APIs → transform → load PostgreSQL",
    log_prints=True,    # print() statements appear in Prefect logs
)
def run_pipeline():
    """
    Complete ETL pipeline as a Prefect flow.

    Prefect automatically:
      - Runs tasks with no dependencies in parallel
      - Tracks state of every task
      - Retries failed tasks
      - Logs everything to the UI
      - Sends alerts on failure (when configured)
    """
    logger = get_run_logger()
    logger.info("Pipeline starting")

    # ── Extract (all four run concurrently) ──────────────────────────────
    # .submit() runs the task in a thread pool — parallel execution
    # Without .submit(), tasks run sequentially
    weather_future  = extract_weather.submit()
    rates_future    = extract_exchange_rates.submit()
    github_future   = extract_github.submit()
    nasa_future     = extract_nasa.submit()

    # ── Transform (each waits for its upstream extract) ──────────────────
    # Passing a future as an argument automatically creates a dependency —
    # transform_weather won't start until extract_weather completes
    weather_df = transform_weather.submit(weather_future)
    rates_df   = transform_rates.submit(rates_future)

    # ── Load (each waits for its upstream transform) ──────────────────────
    weather_loaded = load_weather.submit(weather_df)
    rates_loaded   = load_rates.submit(rates_df)

    # ── Refresh (waits for both loads to complete) ────────────────────────
    refresh_views.submit(weather_loaded, rates_loaded)

    # GitHub and NASA are extracted and tracked but not yet loaded
    # (same as our Airflow DAG — loaders coming in Phase 7 extension)
    logger.info(
        f"Pipeline complete — "
        f"GitHub: {github_future.result()} repos, "
        f"NASA: {nasa_future.result()} records"
    )


# ── Run directly for testing ──────────────────────────────────────────────────
if __name__ == "__main__":
    run_pipeline()