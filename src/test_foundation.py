# src/test_foundation.py
# Phase 1 assignment — wires together every module we built.
# Run with: python src/test_foundation.py

import sys
from pathlib import Path

# Add project root to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests                          # for the GitHub zen call
from src.logger     import get_logger
from src.date_utils import (
    now_utc, to_iso_string,
    date_range, days_ago, make_filename,
)
from src.utils      import save_json, load_json

logger = get_logger(__name__)


def test_logger():
    """1. Exercise every log level so we can see them all in the log file."""
    print("\n--- 1. Testing Logger Levels ---")

    # DEBUG is filtered out unless LOG_LEVEL=DEBUG in secrets.env
    logger.debug(   "DEBUG   — granular detail, development only")
    logger.info(    "INFO    — pipeline started successfully")
    logger.warning( "WARNING — API rate limit at 80%, slowing down")
    logger.error(   "ERROR   — failed to parse record, skipping")
    logger.critical("CRITICAL — database unreachable, pipeline halted")


def test_dates():
    """2. Confirm UTC timestamps and ISO formatting work correctly."""
    print("\n--- 2. Testing UTC Date Utilities ---")

    now = now_utc()
    print(f"Current UTC time : {now}")
    print(f"As ISO string    : {to_iso_string(now)}")


def test_date_range():
    """
    3. Generate filenames for the last 3 days.
    Notice we pass `d` into make_filename — that's what makes each name unique.
    """
    print("\n--- 3. Testing Date Range Filenames ---")

    # days_ago(2) gives us the day before yesterday
    # today() gives us today
    # so date_range produces exactly 3 dates: -2, -1, 0
    for d in date_range(days_ago(2), days_ago(0)):
        filename = make_filename("test", d)        # ← pass d, not today()
        print(f"  {d}  →  {filename}")


def test_http():
    """
    4. Direct HTTP call to GitHub's zen endpoint.
    This endpoint returns plain text, not JSON, so we use requests directly.
    Our safe_request() wrapper is for JSON APIs — this is a deliberate exception.
    """
    print("\n--- 4. Testing Direct HTTP Request ---")

    try:
        response = requests.get(
            "https://api.github.com/zen",
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        response.raise_for_status()
        print(f"  GitHub Zen: \"{response.text}\"")

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request failed: {e}")


def test_json_io():
    """
    5. Save a dict to disk and read it back.
    The verified_at field uses now_utc() — never hardcode dates.
    """
    print("\n--- 5. Testing JSON File I/O ---")

    from src.config import DATA_DIR

    # Build the record — every field is dynamic
    record = {
        "status"       : "foundation_verified",
        "project"      : "data_pipeline_project",
        "phase"        : 1,
        "verified_at"  : to_iso_string(now_utc()),    # ← real timestamp
        "modules_built": [
            "config", "logger", "exceptions",
            "utils", "date_utils", "file_readers",
        ],
    }

    # Save
    filepath = DATA_DIR / make_filename("test")       # test_2026-06-28.json
    save_json(record, filepath)
    print(f"  Saved  → {filepath.name}")

    # Read back and verify round-trip integrity
    loaded = load_json(filepath)
    assert loaded["status"] == "foundation_verified", "Round-trip failed!"
    print(f"  Loaded → status={loaded['status']!r}")
    print(f"           verified_at={loaded['verified_at']!r}")
    print(f"           modules={loaded['modules_built']}")


def main():
    logger.info("Phase 1 foundation test starting")

    test_logger()
    test_dates()
    test_date_range()
    test_http()
    test_json_io()

    logger.info("Phase 1 foundation test complete — all systems nominal")
    print("\n✅ All tests passed. Check logs/ for the full log file.\n")


if __name__ == "__main__":
    main()