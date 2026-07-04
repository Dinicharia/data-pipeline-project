# airflow/dags/pipeline_dag.py
# Our ETL pipeline as an Airflow DAG.
#
# KEY CONCEPT: This file does not RUN the pipeline.
# It DESCRIBES the pipeline as a graph.
# Airflow reads this file, builds the graph in memory,
# and executes tasks according to the schedule and dependencies.

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Tell Python where our src/ package lives inside the container
# (mounted at /opt/airflow/src via the volume in docker-compose)
sys.path.insert(0, "/opt/airflow")

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty  import EmptyOperator

# ── Default arguments applied to every task in this DAG ──────────────────────
# These are the production defaults — every real Airflow DAG sets these.
default_args = {
    "owner"           : "data_engineering",
    "depends_on_past" : False,     # don't wait for yesterday's run to succeed
    "email_on_failure": False,     # set to True + add email in production
    "email_on_retry"  : False,
    "retries"         : 2,         # retry failed tasks twice before giving up
    "retry_delay"     : timedelta(minutes=5),   # wait 5 min between retries
}


# ── DAG definition ────────────────────────────────────────────────────────────
# The `with DAG(...)` block registers this DAG with Airflow.
# Everything inside it becomes part of this pipeline.
with DAG(
    dag_id="data_pipeline_etl",          # unique name shown in the UI
    description="Daily ETL: extract APIs → transform → load PostgreSQL",
    default_args=default_args,
    schedule="0 6 * * *",               # cron: run at 06:00 UTC every day
    start_date=datetime(2026, 7, 1),    # Airflow won't schedule before this date
    catchup=False,                      # don't backfill missed runs
    tags=["etl", "weather", "pipeline"],
    max_active_runs=1,                  # only one run at a time
) as dag:

    # ── Helper: import and run safely ─────────────────────────────────────────
    # Each task function is kept minimal — it imports what it needs and
    # calls one function. Heavy imports at module level would slow
    # Airflow's DAG parsing, which runs every 30 seconds.

    # ── Start marker ─────────────────────────────────────────────────────────
    # EmptyOperator is a no-op — just a visual anchor in the graph
    start = EmptyOperator(task_id="start")


    # ── Extract tasks (run in parallel — no dependencies between them) ────────

    def extract_weather_task():
        from src.extractors.weather_extractor import extract_all_cities
        results = extract_all_cities()
        return len(results)   # return value stored in XCom automatically

    def extract_rates_task():
        from src.extractors.exchange_rate_extractor import extract_and_save
        data = extract_and_save()
        return len(data.get("rates", {}))

    def extract_github_task():
        from src.extractors.github_extractor import extract_all_repos
        results = extract_all_repos()
        return len(results)

    def extract_nasa_task():
        from src.extractors.nasa_extractor import extract_and_save
        results = extract_and_save()
        return len(results)

    extract_weather = PythonOperator(
        task_id="extract_weather",
        python_callable=extract_weather_task,
    )

    extract_rates = PythonOperator(
        task_id="extract_exchange_rates",
        python_callable=extract_rates_task,
    )

    extract_github = PythonOperator(
        task_id="extract_github",
        python_callable=extract_github_task,
    )

    extract_nasa = PythonOperator(
        task_id="extract_nasa",
        python_callable=extract_nasa_task,
    )


    # ── Transform tasks ───────────────────────────────────────────────────────

    def transform_weather_task(**context):
        """
        **context gives us access to Airflow's task context,
        including XCom — the way tasks pass data to each other.
        """
        from src.transformers.weather_transformer import transform_weather_file
        from src.transformers.quality_checks import (
            run_quality_gate, validate_weather_dataframe
        )
        from src.config     import DATA_DIR
        from src.date_utils import make_filename

        filepath = DATA_DIR / "weather" / make_filename("weather_raw")
        df = transform_weather_file(filepath)
        df = run_quality_gate(df, validate_weather_dataframe)

        # Push row count to XCom so the load task can log it
        context["ti"].xcom_push(key="weather_rows", value=len(df))
        return len(df)

    def transform_rates_task(**context):
        from src.transformers.exchange_rate_transformer import transform_exchange_rates
        from src.config     import DATA_DIR
        from src.date_utils import make_filename

        filepath = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")
        df = transform_exchange_rates(filepath)
        context["ti"].xcom_push(key="rates_rows", value=len(df))
        return len(df)

    transform_weather = PythonOperator(
        task_id="transform_weather",
        python_callable=transform_weather_task,
    )

    transform_rates = PythonOperator(
        task_id="transform_exchange_rates",
        python_callable=transform_rates_task,
    )


    # ── Load tasks ────────────────────────────────────────────────────────────

    def load_weather_task(**context):
        from src.transformers.weather_transformer import transform_weather_file
        from src.transformers.quality_checks import (
            run_quality_gate, validate_weather_dataframe
        )
        from src.loader     import load_weather_readings
        from src.config     import DATA_DIR
        from src.date_utils import make_filename

        filepath = DATA_DIR / "weather" / make_filename("weather_raw")
        df = transform_weather_file(filepath)
        df = run_quality_gate(df, validate_weather_dataframe)
        n  = load_weather_readings(df)
        return n

    def load_rates_task(**context):
        from src.transformers.exchange_rate_transformer import transform_exchange_rates
        from src.loader     import load_exchange_rates
        from src.config     import DATA_DIR
        from src.date_utils import make_filename

        filepath = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")
        df = transform_exchange_rates(filepath)
        n  = load_exchange_rates(df)
        return n

    load_weather = PythonOperator(
        task_id="load_weather",
        python_callable=load_weather_task,
    )

    load_rates = PythonOperator(
        task_id="load_exchange_rates",
        python_callable=load_rates_task,
    )


    # ── Final tasks ───────────────────────────────────────────────────────────

    def refresh_views_task():
        from src.loader import refresh_materialized_view
        refresh_materialized_view()

    refresh_views = PythonOperator(
        task_id="refresh_materialized_views",
        python_callable=refresh_views_task,
    )

    end = EmptyOperator(task_id="end")


    # ── Define the dependency graph ───────────────────────────────────────────
    # This is the most important part of the DAG file.
    # >> means "must complete before"
    # [a, b, c] means "all of these can run in parallel"
    #
    # Reading it aloud:
    # "start, then extract all four sources in parallel,
    #  then transform weather and rates in parallel,
    #  then load weather and rates in parallel,
    #  then refresh views,
    #  then end"

    start >> [extract_weather, extract_rates, extract_github, extract_nasa]

    extract_weather >> transform_weather >> load_weather
    extract_rates   >> transform_rates   >> load_rates

    # Both loads must complete before refreshing views
    [load_weather, load_rates] >> refresh_views >> end