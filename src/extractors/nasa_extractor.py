# src/extractors/nasa_extractor.py
# Extracts Astronomy Picture of the Day (APOD) metadata from NASA API.
# Demonstrates: API key in query params, date-range requests.
# Docs: https://api.nasa.gov

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config     import NASA_API_KEY, DATA_DIR
from src.utils      import safe_request, save_json
from src.date_utils import now_utc, today, days_ago, make_filename
from src.logger     import get_logger
from src.exceptions import ExtractError

logger = get_logger(__name__)

BASE_URL = "https://api.nasa.gov/planetary/apod"


def extract_apod(days: int = 7) -> list[dict]:
    """
    Fetch NASA Astronomy Picture of the Day for the last N days.

    Args:
        days: Number of days of history to fetch (default: 7)

    Returns:
        List of APOD records, one per day
    """
    start_date = days_ago(days - 1)
    end_date   = today()

    logger.info(f"Fetching NASA APOD: {start_date} to {end_date}")

    params = {
        "api_key"    : NASA_API_KEY,
        "start_date" : start_date.isoformat(),    # "2026-06-21"
        "end_date"   : end_date.isoformat(),      # "2026-06-28"
        "thumbs"     : "true",    # include thumbnail URL for videos
    }

    raw = safe_request(BASE_URL, params=params)

    # NASA returns a list when date range is specified
    if not isinstance(raw, list):
        raw = [raw]

    # Add extraction metadata to each record
    for record in raw:
        record["_extracted_at"] = now_utc().isoformat()

    logger.info(f"NASA APOD: fetched {len(raw)} records")

    return raw


def extract_and_save(days: int = 7) -> list[dict]:
    """Extract NASA APOD data and save raw data to disk."""

    data     = extract_apod(days)
    filepath = DATA_DIR / "nasa" / make_filename("nasa_apod_raw")
    DATA_DIR.joinpath("nasa").mkdir(exist_ok=True)
    save_json(data, filepath)

    return data


if __name__ == "__main__":
    data = extract_and_save(days=7)
    print(f"\nNASA APOD — Last {len(data)} days\n")
    for record in data:
        media = "🎥" if record.get("media_type") == "video" else "🔭"
        print(f"  {record['date']}  {media}  {record['title']}")