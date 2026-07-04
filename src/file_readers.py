import sys
from pathlib import Path

# Add project root to path BEFORE importing src.logger
sys.path.insert(0, str(Path(__file__).parent.parent))


# src/file_readers.py
# Functions for reading raw data files.
# In Phase 5 we'll use pandas for serious transformation,
# but these basic readers are useful for quick inspection and testing.

import csv                    # Python's built-in CSV reader
import json                   # Python's built-in JSON parser
from pathlib import Path
from src.logger import get_logger
from src.exceptions import ExtractError

logger = get_logger(__name__)


def read_json(filepath) -> dict | list:
    """
    Read a JSON file and return parsed Python data.

    JSON (JavaScript Object Notation) is the universal language of APIs.
    Every API in our project returns JSON.

    JSON → Python type mapping:
        {}  → dict
        []  → list
        ""  → str
        1   → int
        1.5 → float
        true/false → True/False
        null → None
    """
    filepath = Path(filepath)
    logger.debug(f"Reading JSON: {filepath}")

    if not filepath.exists():
        raise ExtractError(f"JSON file not found: {filepath}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Log a useful summary depending on the data type
        if isinstance(data, list):
            logger.info(f"Loaded {len(data)} records from {filepath.name}")
        elif isinstance(data, dict):
            logger.info(f"Loaded JSON object with {len(data)} keys from {filepath.name}")

        return data

    except json.JSONDecodeError as e:
        # Line and column numbers help locate the exact corruption
        raise ExtractError(
            f"Malformed JSON in {filepath} at line {e.lineno}, col {e.colno}: {e.msg}"
        )


def read_csv(filepath, delimiter: str = ",") -> list[dict]:
    """
    Read a CSV file and return a list of dictionaries.

    Each row becomes a dict where keys are the column headers.

    Example CSV:
        city,temperature,date
        Nairobi,24.5,2026-06-27
        London,18.2,2026-06-27

    Returns:
        [
            {"city": "Nairobi", "temperature": "24.5", "date": "2026-06-27"},
            {"city": "London",  "temperature": "18.2", "date": "2026-06-27"},
        ]

    Note: CSV values are ALWAYS strings — we convert types in Phase 5 (Pandas).
    """
    filepath = Path(filepath)
    logger.debug(f"Reading CSV: {filepath}")

    if not filepath.exists():
        raise ExtractError(f"CSV file not found: {filepath}")

    try:
        rows = []

        with open(filepath, "r", encoding="utf-8", newline="") as f:
            # DictReader automatically uses the first row as column names
            reader = csv.DictReader(f, delimiter=delimiter)

            for row in reader:
                # Strip whitespace from all values (common issue in real CSVs)
                cleaned = {k: v.strip() for k, v in row.items()}
                rows.append(cleaned)

        logger.info(f"Loaded {len(rows)} rows from {filepath.name}")
        return rows

    except PermissionError:
        raise ExtractError(f"Permission denied reading {filepath}")


def inspect_json(data: dict | list, max_items: int = 3) -> None:
    """
    Print a human-readable preview of JSON data.
    Useful during development to understand what an API returned.
    """
    print(f"\n{'─'*50}")
    print(f"Type: {type(data).__name__}")

    if isinstance(data, list):
        print(f"Records: {len(data)}")
        print(f"First {min(max_items, len(data))} items:")
        for item in data[:max_items]:
            print(f"  {json.dumps(item, indent=2, default=str)}")

    elif isinstance(data, dict):
        print(f"Keys ({len(data)}): {list(data.keys())}")
        print("Preview:")
        # Show first max_items keys
        for key in list(data.keys())[:max_items]:
            print(f"  {key!r}: {data[key]!r}")

    print(f"{'─'*50}\n")