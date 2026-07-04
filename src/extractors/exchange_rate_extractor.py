# src/extractors/exchange_rate_extractor.py
# Extracts exchange rates from the free Open Exchange Rates API.
# No API key required for this endpoint.
# Docs: https://www.exchangerate-api.com/docs/free

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config     import DATA_DIR
from src.utils      import safe_request, save_json
from src.date_utils import now_utc, make_filename
from src.logger     import get_logger
from src.exceptions import ExtractError

logger = get_logger(__name__)

BASE_URL       = "https://open.er-api.com/v6/latest"
BASE_CURRENCY  = "USD"

# Only track currencies relevant to our monitored cities
TARGET_CURRENCIES = ["KES", "GBP", "EUR", "JPY", "AUD", "CAD", "CHF"]


def extract_exchange_rates(base: str = BASE_CURRENCY) -> dict:
    """
    Fetch current exchange rates for all target currencies.

    Args:
        base: The base currency code (default: USD)

    Returns:
        Dict containing rates and metadata
    """
    logger.info(f"Fetching exchange rates: {base} → {TARGET_CURRENCIES}")

    url = f"{BASE_URL}/{base}"
    raw = safe_request(url)

    # Validate the response structure
    if raw.get("result") != "success":
        raise ExtractError(
            f"Exchange rate API returned failure: {raw.get('error-type', 'unknown')}"
        )

    # Extract only the currencies we care about
    all_rates     = raw["rates"]
    filtered_rates = {
        currency: rate
        for currency, rate in all_rates.items()
        if currency in TARGET_CURRENCIES
    }

    # Build a clean result object
    result = {
        "base_currency"  : base,
        "rates"          : filtered_rates,
        "api_updated_at" : raw.get("time_last_update_utc"),
        "next_update_at" : raw.get("time_next_update_utc"),
        "_extracted_at"  : now_utc().isoformat(),
    }

    logger.info(
        "Exchange rates fetched: "
        + ", ".join(f"{k}={v:.4f}" for k, v in filtered_rates.items())
    )

    return result


def extract_and_save() -> dict:
    """Extract exchange rates and save raw data to disk."""

    data     = extract_exchange_rates()
    filepath = DATA_DIR / "exchange_rates" / make_filename("exchange_rates_raw")
    DATA_DIR.joinpath("exchange_rates").mkdir(exist_ok=True)
    save_json(data, filepath)

    return data


if __name__ == "__main__":
    data = extract_and_save()
    print(f"\nBase currency: {data['base_currency']}")
    print(f"API updated:   {data['api_updated_at']}")
    print("\nRates:")
    for currency, rate in data["rates"].items():
        print(f"  1 USD = {rate:10.4f} {currency}")