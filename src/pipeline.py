# src/pipeline.py
# The main pipeline entrypoint.
# Run this file to execute the complete ETL:
#   Extract  → raw JSON files
#   Transform → cleaned DataFrames
#   Validate → quality gate
#   Load      → PostgreSQL
#
# Usage:
#   python src/pipeline.py            # run today's pipeline
#   python src/pipeline.py --dry-run  # extract + transform but don't load

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from src.logger      import get_logger
from src.database    import test_connection
from src.pipeline_run import tracked_pipeline_run
from src.date_utils  import make_filename
from src.config      import DATA_DIR

# ── Extractors ────────────────────────────────────────────────────────────────
from src.extractors.weather_extractor       import extract_all_cities
from src.extractors.exchange_rate_extractor import extract_and_save as extract_rates
from src.extractors.github_extractor        import extract_all_repos
from src.extractors.nasa_extractor          import extract_and_save as extract_nasa

# ── Transformers ──────────────────────────────────────────────────────────────
from src.transformers.weather_transformer       import transform_weather_file
from src.transformers.exchange_rate_transformer import transform_exchange_rates
from src.transformers.github_transformer        import transform_github_repos
from src.transformers.nasa_transformer          import transform_nasa_apod
from src.transformers.quality_checks           import (
    run_quality_gate,
    validate_weather_dataframe,
)

# ── Loaders ───────────────────────────────────────────────────────────────────
from src.loader import (
    load_weather_readings,
    load_exchange_rates,
    refresh_materialized_view,
)

logger = get_logger(__name__)


def run_extract_stage() -> dict:
    """
    Stage 1 — Extract: call all APIs and save raw JSON files.

    Returns:
        Dict of {source_name: filepath} for the transform stage
    """
    logger.info("=" * 60)
    logger.info("STAGE 1: EXTRACT")
    logger.info("=" * 60)

    # Run all four extractors — even if one fails, try the rest
    filepaths = {}
    errors    = []

    # Weather
    try:
        extract_all_cities()
        filepaths["weather"] = DATA_DIR / "weather" / make_filename("weather_raw")
        logger.info("✓ Weather extraction complete")
    except Exception as e:
        logger.error(f"✗ Weather extraction failed: {e}")
        errors.append("weather")

    # Exchange rates
    try:
        extract_rates()
        filepaths["exchange_rates"] = (
            DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")
        )
        logger.info("✓ Exchange rates extraction complete")
    except Exception as e:
        logger.error(f"✗ Exchange rate extraction failed: {e}")
        errors.append("exchange_rates")

    # GitHub
    try:
        extract_all_repos()
        filepaths["github"] = DATA_DIR / "github" / make_filename("github_raw")
        logger.info("✓ GitHub extraction complete")
    except Exception as e:
        logger.error(f"✗ GitHub extraction failed: {e}")
        errors.append("github")

    # NASA
    try:
        extract_nasa()
        filepaths["nasa"] = DATA_DIR / "nasa" / make_filename("nasa_apod_raw")
        logger.info("✓ NASA extraction complete")
    except Exception as e:
        logger.error(f"✗ NASA extraction failed: {e}")
        errors.append("nasa")

    if not filepaths:
        raise RuntimeError("All extractions failed — nothing to transform")

    if errors:
        logger.warning(f"Extract stage completed with failures: {errors}")

    return filepaths


def run_transform_stage(filepaths: dict) -> dict:
    """
    Stage 2 — Transform: clean and validate each raw file.

    Args:
        filepaths: Output from run_extract_stage()

    Returns:
        Dict of {source_name: cleaned_dataframe}
    """
    logger.info("=" * 60)
    logger.info("STAGE 2: TRANSFORM")
    logger.info("=" * 60)

    dataframes = {}

    if "weather" in filepaths:
        df = transform_weather_file(filepaths["weather"])
        df = run_quality_gate(df, validate_weather_dataframe)
        dataframes["weather"] = df
        logger.info(f"✓ Weather transform complete: {len(df)} rows")

    if "exchange_rates" in filepaths:
        df = transform_exchange_rates(filepaths["exchange_rates"])
        dataframes["exchange_rates"] = df
        logger.info(f"✓ Exchange rates transform complete: {len(df)} rows")

    if "github" in filepaths:
        df = transform_github_repos(filepaths["github"])
        dataframes["github"] = df
        logger.info(f"✓ GitHub transform complete: {len(df)} rows")

    if "nasa" in filepaths:
        df = transform_nasa_apod(filepaths["nasa"])
        dataframes["nasa"] = df
        logger.info(f"✓ NASA transform complete: {len(df)} rows")

    return dataframes


def run_load_stage(dataframes: dict) -> dict:
    """
    Stage 3 — Load: insert cleaned DataFrames into PostgreSQL.

    Args:
        dataframes: Output from run_transform_stage()

    Returns:
        Dict of {source_name: rows_inserted}
    """
    logger.info("=" * 60)
    logger.info("STAGE 3: LOAD")
    logger.info("=" * 60)

    counts = {}

    if "weather" in dataframes:
        n = load_weather_readings(dataframes["weather"])
        counts["weather"] = n
        logger.info(f"✓ Weather loaded: {n} rows")

    if "exchange_rates" in dataframes:
        n = load_exchange_rates(dataframes["exchange_rates"])
        counts["exchange_rates"] = n
        logger.info(f"✓ Exchange rates loaded: {n} rows")

    # GitHub and NASA transforms are complete but we'll add their
    # loaders when we design their tables — for now log the row counts
    if "github" in dataframes:
        logger.info(
            f"✓ GitHub transformed ({len(dataframes['github'])} rows) "
            f"— loader coming in Phase 7 extension"
        )

    if "nasa" in dataframes:
        logger.info(
            f"✓ NASA transformed ({len(dataframes['nasa'])} rows) "
            f"— loader coming in Phase 7 extension"
        )

    # Refresh the materialized view so dashboards see fresh data
    refresh_materialized_view()

    return counts


def run_pipeline(dry_run: bool = False) -> None:
    """
    Execute the complete ETL pipeline.

    Args:
        dry_run: If True, extract and transform but skip loading.
                 Useful for testing without touching the database.
    """
    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║           DATA PIPELINE STARTING                    ║")
    logger.info("╚══════════════════════════════════════════════════════╝")

    # ── Pre-flight check ────────────────────────────────────────────────────
    if not dry_run:
        if not test_connection():
            raise RuntimeError(
                "Database connection failed — cannot start pipeline. "
                "Check PostgreSQL is running and config/secrets.env is correct."
            )

    # ── Run all three stages under the audit tracker ────────────────────────
    with tracked_pipeline_run("full_etl_pipeline") as run_id:

        # Stage 1: Extract
        filepaths  = run_extract_stage()

        # Stage 2: Transform + validate
        dataframes = run_transform_stage(filepaths)

        # Stage 3: Load (skipped in dry-run mode)
        if dry_run:
            logger.info("DRY RUN — skipping load stage")
            counts = {k: 0 for k in dataframes}
        else:
            counts = run_load_stage(dataframes)

    # ── Final summary ────────────────────────────────────────────────────────
    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║           DATA PIPELINE COMPLETE                    ║")
    logger.info("╠══════════════════════════════════════════════════════╣")
    for source, count in counts.items():
        logger.info(f"║  {source:<20} {count:>4} rows loaded              ║")
    logger.info("╚══════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ETL data pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and transform but do not load to database"
    )
    args = parser.parse_args()


# Add to the top of run_pipeline() in src/pipeline.py:

def run_pipeline(dry_run: bool = False) -> None:
    from src.health_checks import run_all_checks
    from src.alerting      import alerter

    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║           DATA PIPELINE STARTING                    ║")
    logger.info("╚══════════════════════════════════════════════════════╝")

    # ── Pre-flight health checks ─────────────────────────────────────────
    if not dry_run:
        if not test_connection():
            alerter.critical("Pipeline aborted — database unreachable")
            raise RuntimeError("Database connection failed")

        # Run health checks but don't abort on anomalies — just alert
        run_all_checks()

    # ... rest of pipeline unchanged ...

    # ── Post-run ─────────────────────────────────────────────────────────
    alerter.send_daily_digest()


    run_pipeline(dry_run=args.dry_run)