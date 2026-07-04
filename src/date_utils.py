import sys
from pathlib import Path

# Add project root to path BEFORE importing src.logger
sys.path.insert(0, str(Path(__file__).parent.parent))

# src/date_utils.py
# All date/time utilities for the pipeline.
# Centralizing these means consistent formatting everywhere.

from datetime import datetime, date, timedelta, timezone
from src.logger import get_logger

logger = get_logger(__name__)


# ─── The one true timestamp format we use everywhere ──────────────────────────
# ISO 8601 is the international standard. Databases, APIs, and humans all read it.
# Example: "2026-06-27T14:32:01+00:00"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Simpler format for filenames (no colons — they're illegal in Windows filenames)
# Example: "2026-06-27"
DATE_FORMAT = "%Y-%m-%d"


def now_utc() -> datetime:
    """
    Return the current time in UTC, timezone-aware.
    Always use this instead of datetime.now() which returns a naive local time.
    """
    # timezone.utc is Python's built-in UTC timezone object
    return datetime.now(tz=timezone.utc)


def today() -> date:
    """Return today's date in UTC."""
    return now_utc().date()


def to_iso_string(dt: datetime) -> str:
    """
    Convert a datetime to an ISO 8601 string.
    This is the format we store in the database and log files.

    Example: datetime(2026, 6, 27, 14, 32, 1) → "2026-06-27T14:32:01+00:00"
    """
    # If the datetime has no timezone info, assume it's UTC and add it
    if dt.tzinfo is None:
        logger.warning(
            "Converting naive datetime to UTC — "
            "check your data source provides timezone info"
        )
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.isoformat()


def from_iso_string(s: str) -> datetime:
    """
    Parse an ISO 8601 string back into a datetime object.
    Handles the formats most APIs return.

    Example: "2026-06-27T14:32:01Z" → datetime(2026, 6, 27, 14, 32, 1, tzinfo=UTC)
    """
    # APIs use "Z" to mean UTC, but Python can't parse "Z" directly until 3.11
    # Replace "Z" with "+00:00" for compatibility
    s = s.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(
            f"Cannot parse date string '{s}'. "
            f"Expected ISO 8601 format like '2026-06-27T14:32:01+00:00'"
        ) from e


def date_range(start: date, end: date) -> list[date]:
    """
    Generate a list of every date from start to end, inclusive.

    Used when we need to backfill data — fetch data for each missing day.

    Example:
        date_range(date(2026, 6, 25), date(2026, 6, 27))
        → [date(2026, 6, 25), date(2026, 6, 26), date(2026, 6, 27)]
    """
    if end < start:
        raise ValueError(f"end date {end} is before start date {start}")

    dates = []
    current = start

    # timedelta(days=1) represents exactly one day
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)   # advance by one day

    return dates


def days_ago(n: int) -> date:
    """
    Return the date n days before today.
    Useful for: "give me all data from the last 7 days"

    Example: days_ago(7) → date(2026, 6, 20)  if today is 2026-06-27
    """
    return today() - timedelta(days=n)


def make_filename(prefix: str, dt: date = None, extension: str = "json") -> str:
    """
    Generate a standardized filename with a date stamp.
    This is how we name our raw data files so they sort chronologically.

    Example: make_filename("weather") → "weather_2026-06-27.json"
    Example: make_filename("github", extension="csv") → "github_2026-06-27.csv"
    """
    dt = dt or today()                          # default to today
    date_str = dt.strftime(DATE_FORMAT)         # format as "2026-06-27"
    return f"{prefix}_{date_str}.{extension}"


# ─── Quick demo ───────────────────────────────────────────────────────────────
if __name__ == "__main__":

    print("=== Date Utilities Demo ===\n")

    # Current time
    now = now_utc()
    print(f"Current UTC time : {now}")
    print(f"As ISO string    : {to_iso_string(now)}")
    print(f"Today's date     : {today()}")

    # Date arithmetic
    print(f"\n7 days ago       : {days_ago(7)}")
    print(f"30 days ago      : {days_ago(30)}")

    # Date ranges — we'll use this when backfilling API data
    print("\nLast 5 days:")
    for d in date_range(days_ago(4), today()):
        print(f"  {d}  →  filename: {make_filename('weather', d)}")

    # Parsing API responses — APIs return dates as strings
    print("\nParsing API date strings:")
    api_responses = [
        "2026-06-27T14:32:01Z",          # GitHub format
        "2026-06-27T14:32:01+00:00",     # standard ISO 8601
        "2026-06-27T17:32:01+03:00",     # East Africa Time (Nairobi)
    ]
    for s in api_responses:
        parsed = from_iso_string(s)
        print(f"  {s!r:40s} → {parsed}")
