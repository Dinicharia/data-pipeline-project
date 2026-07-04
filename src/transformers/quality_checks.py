# src/transformers/quality_checks.py
# Automated data quality validation — runs AFTER cleaning, BEFORE loading.
# This is the pipeline's last line of defense before bad data reaches
# the database.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.logger     import get_logger
from src.exceptions import TransformError

logger = get_logger(__name__)


class QualityCheckResult:
    """Holds the outcome of a data quality validation run."""

    def __init__(self):
        self.passed: list[str]  = []
        self.failed: list[str]  = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        """A DataFrame is valid only if NO checks failed."""
        return len(self.failed) == 0

    def summary(self) -> str:
        lines = [
            f"Quality check: {len(self.passed)} passed, "
            f"{len(self.failed)} failed, {len(self.warnings)} warnings"
        ]
        for f in self.failed:
            lines.append(f"  ❌ FAIL: {f}")
        for w in self.warnings:
            lines.append(f"  ⚠️  WARN: {w}")
        return "\n".join(lines)


def validate_weather_dataframe(df: pd.DataFrame) -> QualityCheckResult:
    """
    Run a battery of quality checks on a cleaned weather DataFrame.

    Checks are categorized:
      - FAILURES block the pipeline (data must not be loaded)
      - WARNINGS are logged but don't block loading

    Args:
        df: Cleaned weather DataFrame

    Returns:
        QualityCheckResult with pass/fail/warning details
    """
    result = QualityCheckResult()

    # ── Check 1: DataFrame is not empty ─────────────────────────────────────
    if len(df) == 0:
        result.failed.append("DataFrame is empty — nothing to load")
    else:
        result.passed.append(f"DataFrame has {len(df)} rows")

    # ── Check 2: No nulls in critical columns ───────────────────────────────
    critical_columns = ["city_id", "temperature_c", "humidity_pct", "recorded_at"]
    for col in critical_columns:
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.failed.append(f"{col} has {null_count} NULL values (critical column)")
        else:
            result.passed.append(f"{col} has no NULL values")

    # ── Check 3: No duplicate natural keys ──────────────────────────────────
    dupes = df.duplicated(subset=["city_id", "recorded_at"]).sum()
    if dupes > 0:
        result.failed.append(f"{dupes} duplicate (city_id, recorded_at) pairs found")
    else:
        result.passed.append("No duplicate natural keys")

    # ── Check 4: Value ranges (mirrors DB CHECK constraints) ───────────────
    if not df["temperature_c"].between(-90, 60).all():
        result.failed.append("temperature_c has values outside [-90, 60]")
    else:
        result.passed.append("temperature_c within valid range")

    if not df["humidity_pct"].between(0, 100).all():
        result.failed.append("humidity_pct has values outside [0, 100]")
    else:
        result.passed.append("humidity_pct within valid range")

    # ── Check 5: Freshness — is this data actually recent? ─────────────────
    # A WARNING, not a failure — old data might still be valid for backfills
    now = pd.Timestamp.now(tz="UTC")
    oldest = df["recorded_at"].min()
    age_hours = (now - oldest).total_seconds() / 3600
    if age_hours > 24:
        result.warnings.append(
            f"Oldest reading is {age_hours:.1f} hours old — "
            f"expected fresh data (<24h)"
        )
    else:
        result.passed.append(f"Data freshness OK ({age_hours:.1f}h old)")

    # ── Check 6: Expected row count ─────────────────────────────────────────
    # We expect exactly 5 readings (one per monitored city)
    # Fewer means some cities failed extraction — worth knowing, not fatal
    expected_cities = 5
    if len(df) < expected_cities:
        result.warnings.append(
            f"Expected {expected_cities} city readings, got {len(df)} — "
            f"some cities may have failed extraction"
        )
    else:
        result.passed.append(f"Got expected {expected_cities} city readings")

    return result


def run_quality_gate(df: pd.DataFrame, validator_fn) -> pd.DataFrame:
    """
    Run a validator function against a DataFrame. Raise an exception if
    validation fails, blocking the data from proceeding to load.

    This is the function the pipeline calls — it turns the validation
    result into a hard stop/go decision.

    Args:
        df:           DataFrame to validate
        validator_fn: A function like validate_weather_dataframe

    Returns:
        The same DataFrame, unchanged, if validation passes

    Raises:
        TransformError: if any check failed
    """
    result = validator_fn(df)
    logger.info(f"\n{result.summary()}")

    if not result.is_valid:
        raise TransformError(
            f"Data quality gate FAILED — {len(result.failed)} check(s) failed. "
            f"Pipeline halted to prevent loading bad data."
        )

    return df


if __name__ == "__main__":
    from src.config import DATA_DIR
    from src.date_utils import make_filename
    from src.transformers.weather_transformer import transform_weather_file

    filepath = DATA_DIR / "weather" / make_filename("weather_raw")
    df = transform_weather_file(filepath)

    validated_df = run_quality_gate(df, validate_weather_dataframe)
    print(f"\n✅ {len(validated_df)} rows passed quality gate and are ready to load")
