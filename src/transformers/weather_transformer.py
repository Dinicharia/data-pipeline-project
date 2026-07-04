# src/transformers/weather_transformer.py
# Transforms raw OpenWeatherMap JSON into a clean, typed DataFrame
# ready for loading into PostgreSQL.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.config     import DATA_DIR
from src.utils      import load_json
from src.logger     import get_logger
from src.exceptions import TransformError

logger = get_logger(__name__)


def load_raw_weather(filepath) -> list[dict]:
    """
    Load a raw weather JSON file from disk.

    Args:
        filepath: Path to the JSON file saved by weather_extractor.py

    Returns:
        List of raw API response dicts (one per city)
    """
    data = load_json(filepath)

    if not isinstance(data, list):
        raise TransformError(
            f"Expected a list of weather records, got {type(data).__name__}"
        )

    logger.info(f"Loaded {len(data)} raw weather records from {filepath.name}")
    return data


def flatten_weather_records(raw_records: list[dict]) -> pd.DataFrame:
    """
    Flatten nested OpenWeatherMap JSON into a flat DataFrame.

    Raw structure we're unpacking:
        {
            "name": "Nairobi",
            "main": {"temp": 24.5, "humidity": 65, "pressure": 1013},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.6},
            "dt": 1719561600,                    ← Unix timestamp
            "_city_id": 1,
            "_extracted_at": "2026-06-28T08:00:00+00:00"
        }

    Args:
        raw_records: List of raw API response dicts

    Returns:
        Flat DataFrame, one row per city, all nested fields extracted
    """
    flattened = []

    for record in raw_records:
        try:
            # pd.json_normalize() could flatten this automatically, but for
            # API responses with inconsistent nesting (weather is a LIST
            # containing a dict — json_normalize handles dicts, not lists
            # inside dicts well) manual extraction is more reliable and
            # makes it obvious exactly which fields we're keeping.
            flat_row = {
                "city_id"        : record["_city_id"],
                "city_name"      : record["name"],
                "temperature_c"  : record["main"]["temp"],
                "feels_like_c"   : record["main"]["feels_like"],
                "humidity_pct"   : record["main"]["humidity"],
                "pressure_hpa"   : record["main"]["pressure"],
                # weather is a list with one dict inside — take the first
                "description"    : record["weather"][0]["description"],
                "weather_main"   : record["weather"][0]["main"],
                # wind is sometimes missing entirely (calm conditions)
                "wind_speed_ms"  : record.get("wind", {}).get("speed"),
                # dt is a Unix timestamp (seconds since 1970) — raw integer
                "recorded_at_unix": record["dt"],
                "extracted_at"   : record["_extracted_at"],
            }
            flattened.append(flat_row)

        except KeyError as e:
            # A field we expected is missing — log it and skip this record
            # rather than crashing the entire transformation
            logger.error(
                f"Missing expected field {e} in record for "
                f"{record.get('name', 'unknown city')} — skipping"
            )
            continue

    if not flattened:
        raise TransformError("No records could be flattened — all had missing fields")

    df = pd.DataFrame(flattened)
    logger.info(f"Flattened {len(df)} of {len(raw_records)} records successfully")

    return df

# Add this to src/transformers/weather_transformer.py
# (append below flatten_weather_records, before the if __name__ block)

def clean_weather_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and validate a flattened weather DataFrame.

    Steps:
      1. Convert Unix timestamp → proper UTC datetime
      2. Handle missing wind_speed (calm weather often omits it)
      3. Validate value ranges
      4. Remove duplicate readings
      5. Round numeric columns to consistent precision

    Args:
        df: Output of flatten_weather_records()

    Returns:
        Cleaned DataFrame ready for database loading
    """
    df = df.copy()    # never mutate the input — work on a copy

    # ── Step 1: Convert Unix timestamp to datetime ─────────────────────────
    # unit="s" tells pandas the integer is seconds since epoch
    # utc=True ensures the result is timezone-aware (our golden rule from Phase 1)
    df["recorded_at"] = pd.to_datetime(df["recorded_at_unix"], unit="s", utc=True)
    df["extracted_at"] = pd.to_datetime(df["extracted_at"], utc=True)
    df = df.drop(columns=["recorded_at_unix"])    # no longer needed

    # ── Step 2: Handle missing wind speed ───────────────────────────────────
    # Missing wind data usually means genuinely calm conditions (0 m/s),
    # not a data quality problem. This is a DELIBERATE business decision —
    # always document WHY you filled a value, not just that you did.
    missing_wind = df["wind_speed_ms"].isna().sum()
    if missing_wind > 0:
        logger.info(f"Filling {missing_wind} missing wind_speed values with 0.0 (calm)")
    df["wind_speed_ms"] = df["wind_speed_ms"].fillna(0.0)

    # ── Step 3: Validate value ranges ───────────────────────────────────────
    # These mirror the CHECK constraints in our database schema —
    # catching bad data HERE, before it reaches the database, is better
    # than letting PostgreSQL reject it and crash the pipeline
    before = len(df)

    valid_temp     = df["temperature_c"].between(-90, 60)
    valid_humidity = df["humidity_pct"].between(0, 100)
    valid_pressure = df["pressure_hpa"].between(800, 1100)

    invalid_mask = ~(valid_temp & valid_humidity & valid_pressure)
    if invalid_mask.any():
        invalid_cities = df.loc[invalid_mask, "city_name"].tolist()
        logger.warning(
            f"Dropping {invalid_mask.sum()} records with out-of-range values: "
            f"{invalid_cities}"
        )
        df = df[~invalid_mask]

    # ── Step 4: Remove duplicates ───────────────────────────────────────────
    # Same city + same recorded_at = duplicate reading (matches our
    # UNIQUE (city_id, recorded_at) constraint in the database)
    duplicates = df.duplicated(subset=["city_id", "recorded_at"]).sum()
    if duplicates > 0:
        logger.warning(f"Removing {duplicates} duplicate readings")
        df = df.drop_duplicates(subset=["city_id", "recorded_at"], keep="first")

    # ── Step 5: Round numeric columns to consistent precision ──────────────
    # Matches our database column precision: NUMERIC(5,2) etc.
    df["temperature_c"]  = df["temperature_c"].round(2)
    df["feels_like_c"]   = df["feels_like_c"].round(2)
    df["wind_speed_ms"]  = df["wind_speed_ms"].round(2)

    after = len(df)
    logger.info(f"Cleaning complete: {before} → {after} rows ({before - after} removed)")

    return df.reset_index(drop=True)    # clean index after dropping rows


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Feature engineering — create new columns derived from existing data.
    These add analytical value beyond the raw measurements.

    Args:
        df: Output of clean_weather_dataframe()

    Returns:
        DataFrame with additional derived columns
    """
    df = df.copy()

    # Fahrenheit — many downstream consumers expect this
    df["temperature_f"] = (df["temperature_c"] * 9 / 5 + 32).round(2)

    # Temperature category — useful for grouping/filtering in dashboards
    df["temp_category"] = pd.cut(
        df["temperature_c"],
        bins=[-100, 0, 15, 25, 35, 100],
        labels=["freezing", "cold", "mild", "warm", "hot"],
    )

    # Heat index flag — simple business rule: humid AND hot is uncomfortable
    df["feels_uncomfortable"] = (
        (df["temperature_c"] > 28) & (df["humidity_pct"] > 70)
    )

    # Day of week — useful for later time-series analysis
    df["day_of_week"] = df["recorded_at"].dt.day_name()

    logger.info("Added 4 derived features: temperature_f, temp_category, "
                "feels_uncomfortable, day_of_week")

    return df


def transform_weather_file(filepath) -> pd.DataFrame:
    """
    Full transformation pipeline for one weather file: load → flatten → clean → enrich.
    This is the single function the rest of our pipeline will call.

    Args:
        filepath: Path to a raw weather JSON file

    Returns:
        Fully cleaned, enriched DataFrame ready for database loading
    """
    raw     = load_raw_weather(filepath)
    flat    = flatten_weather_records(raw)
    cleaned = clean_weather_dataframe(flat)
    enriched = add_derived_features(cleaned)

    return enriched

if __name__ == "__main__":
    from src.date_utils import make_filename
    filepath = DATA_DIR / "weather" / make_filename("weather_raw")

    df = transform_weather_file(filepath)

    print("\n=== Final Transformed DataFrame ===")
    print(df[[
        "city_name", "temperature_c", "temperature_f", "temp_category",
        "humidity_pct", "feels_uncomfortable", "description", "day_of_week"
    ]].to_string(index=False))

    print(f"\nShape: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"\nFull column list: {list(df.columns)}")
    print(f"\nData types:\n{df.dtypes}")