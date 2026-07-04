# src/transformers/combine.py
# Demonstrates merging data from multiple sources — this is where
# the real analytical value of a pipeline emerges. One source alone
# tells you facts; combined sources tell you a STORY.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.config import DATA_DIR
from src.logger import get_logger
from src.date_utils import make_filename

from src.transformers.weather_transformer       import transform_weather_file
from src.transformers.exchange_rate_transformer import transform_exchange_rates

logger = get_logger(__name__)

# Map our monitored cities to their local currencies
CITY_CURRENCY_MAP = {
    "Nairobi" : "KES",
    "London"  : "GBP",
    "Tokyo"   : "JPY",
    "Sydney"  : "AUD",
    # New York uses USD, which is our base — no conversion needed
}


def merge_weather_with_currency(weather_df: pd.DataFrame, rates_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge weather data with exchange rates by mapping each city to its currency.

    This demonstrates pd.merge() — pandas' equivalent of a SQL JOIN.

    Args:
        weather_df: Cleaned weather DataFrame
        rates_df:   Cleaned exchange rate DataFrame (long format)

    Returns:
        Weather data enriched with each city's local currency exchange rate
    """
    # Add a currency column to weather data based on our mapping
    weather_df = weather_df.copy()
    weather_df["currency"] = weather_df["city_name"].map(CITY_CURRENCY_MAP)
    weather_df["currency"] = weather_df["currency"].fillna("USD")    # New York

    # pd.merge() works exactly like SQL JOIN:
    #   left_on / right_on  = the JOIN ON condition
    #   how="left"           = LEFT JOIN (keep all weather rows even if no rate found)
    merged = pd.merge(
        weather_df,
        rates_df[["target_currency", "rate"]],
        left_on="currency",
        right_on="target_currency",
        how="left",
    )

    # USD rows won't match anything in rates_df (USD is the base, not a target)
    # so their rate is NaN — that's correct, fill with 1.0 (USD to USD = 1)
    merged["rate"] = merged["rate"].fillna(1.0)
    merged = merged.drop(columns=["target_currency"])
    merged = merged.rename(columns={"rate": "usd_exchange_rate"})

    logger.info(f"Merged weather + exchange rates: {len(merged)} rows")

    return merged


if __name__ == "__main__":
    weather_path = DATA_DIR / "weather" / make_filename("weather_raw")
    rates_path   = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")

    weather_df = transform_weather_file(weather_path)
    rates_df   = transform_exchange_rates(rates_path)

    merged = merge_weather_with_currency(weather_df, rates_df)

    print("\n=== Weather + Currency (merged) ===")
    print(merged[[
        "city_name", "temperature_c", "description",
        "currency", "usd_exchange_rate"
    ]].to_string(index=False))