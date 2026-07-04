# src/transformers/exchange_rate_transformer.py
# The raw exchange rate JSON is WIDE: one row, one column per currency.
# Our database table is LONG: one row per currency. This is the most
# common reshaping operation in data engineering — "unpivoting."

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.config     import DATA_DIR
from src.utils      import load_json
from src.logger     import get_logger
from src.exceptions import TransformError

logger = get_logger(__name__)


def transform_exchange_rates(filepath) -> pd.DataFrame:
    """
    Transform raw exchange rate JSON into a long-format DataFrame.

    Raw structure (WIDE — one row's worth of data):
        {
            "base_currency": "USD",
            "rates": {"KES": 129.44, "GBP": 0.7551, "EUR": 0.8760, ...},
            "_extracted_at": "2026-06-30T..."
        }

    Target structure (LONG — one row per currency pair):
        base_currency | target_currency | rate    | extracted_at
        USD           | KES             | 129.44  | 2026-06-30...
        USD           | GBP             | 0.7551  | 2026-06-30...

    WHY long format? Our database table has one row per (base, target,
    time) combination — that's how SQL joins and aggregates work.
    A wide table with one column per currency would need a schema
    change every time a new currency is added. Long format never does.
    """
    raw = load_json(filepath)

    if "rates" not in raw or not raw["rates"]:
        raise TransformError(f"No rates found in {filepath}")

    base       = raw["base_currency"]
    extracted  = raw["_extracted_at"]

    # This is the unpivot: dict of {currency: rate} → list of rows
    rows = [
        {
            "base_currency"  : base,
            "target_currency": currency,
            "rate"           : rate,
            "extracted_at"   : extracted,
        }
        for currency, rate in raw["rates"].items()
    ]

    df = pd.DataFrame(rows)

    # ── Type conversion ──────────────────────────────────────────────────
    df["extracted_at"] = pd.to_datetime(df["extracted_at"], utc=True)
    df["recorded_at"]  = df["extracted_at"]    # rates don't have a separate timestamp

    # ── Validation: rate must be positive (mirrors our CHECK constraint) ──
    before = len(df)
    df = df[df["rate"] > 0]
    if len(df) < before:
        logger.warning(f"Dropped {before - len(df)} rows with non-positive rates")

    # ── Round to consistent precision ──────────────────────────────────────
    df["rate"] = df["rate"].round(8)    # matches NUMERIC(18,8) in our schema

    logger.info(f"Transformed {len(df)} exchange rate rows (base={base})")

    return df.reset_index(drop=True)


if __name__ == "__main__":
    from src.date_utils import make_filename
    filepath = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")

    df = transform_exchange_rates(filepath)
    print("\n=== Transformed Exchange Rates (long format) ===")
    print(df[["base_currency", "target_currency", "rate", "recorded_at"]].to_string(index=False))