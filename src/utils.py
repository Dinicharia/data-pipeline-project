import sys
from pathlib import Path

# Add project root to path BEFORE importing src.logger
sys.path.insert(0, str(Path(__file__).parent.parent))

# src/utils.py
# Utility functions used across the entire pipeline.
# The most important one is safe_request() — every API call
# in this project goes through it.

import time                           # for sleep() when retrying
import requests                       # HTTP library (we installed this)
from requests.exceptions import (
    ConnectionError,                  # no internet / host unreachable
    Timeout,                          # server took too long to respond
    HTTPError,                        # server returned an error status code
)

from src.logger import get_logger
from src.exceptions import (
    ExtractError,
    APIRateLimitError,
    APIAuthError,
)

# Every module gets its own logger — the name shows up in log lines
logger = get_logger(__name__)


def safe_request(
    url: str,
    params: dict = None,
    headers: dict = None,
    max_retries: int = 3,
    timeout: int = 10,
) -> dict:
    """
    Make an HTTP GET request with automatic retries and error handling.

    This is the ONLY function that makes HTTP requests in our project.
    Centralizing it means:
      - Retry logic is written once, not in every extractor
      - All HTTP errors are handled consistently
      - All requests are logged the same way

    Args:
        url:         The API endpoint to call
        params:      Query parameters (e.g. {"city": "Nairobi", "units": "metric"})
        headers:     HTTP headers (e.g. {"Authorization": "Bearer mytoken"})
        max_retries: How many times to retry on temporary failures
        timeout:     Seconds to wait before giving up on a response

    Returns:
        The parsed JSON response as a Python dictionary

    Raises:
        APIAuthError:      On 401/403 — bad credentials, don't retry
        APIRateLimitError: On 429 — slow down, will retry with backoff
        ExtractError:      On any other failure after all retries exhausted
    """

    # We'll try up to max_retries times before giving up
    for attempt in range(1, max_retries + 1):

        try:
            logger.debug(f"Calling URL: {url} | Attempt {attempt}/{max_retries}")

            # Make the actual HTTP GET request
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,       # don't wait forever
            )

            # raise_for_status() converts HTTP error codes into Python exceptions
            # e.g. a 404 response becomes an HTTPError exception
            # Without this, requests considers ANY response a "success"
            response.raise_for_status()

            # If we get here, the request succeeded
            logger.debug(f"Success: {url} | Status {response.status_code}")

            # Parse and return the JSON response body as a Python dict
            return response.json()

        except HTTPError as e:
            status = e.response.status_code

            # ── 401/403: Authentication failed ────────────────────────────
            # Retrying won't help — the key is just wrong
            if status in (401, 403):
                logger.error(f"Authentication failed for {url} | Status {status}")
                raise APIAuthError(
                    f"Invalid API credentials for {url}. "
                    f"Check your API key in config/secrets.env"
                ) from e

            # ── 429: Rate limited ──────────────────────────────────────────
            # The API is telling us to slow down
            elif status == 429:
                wait = 2 ** attempt   # exponential backoff: 2s, 4s, 8s
                logger.warning(
                    f"Rate limited by {url} | Waiting {wait}s before retry..."
                )
                time.sleep(wait)
                continue              # go to next iteration of the for loop

            # ── 5xx: Server error ──────────────────────────────────────────
            # The server is broken — might recover, so we retry
            elif status >= 500:
                logger.warning(
                    f"Server error {status} from {url} | "
                    f"Attempt {attempt}/{max_retries}"
                )
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise ExtractError(
                    f"Server error {status} from {url} after {max_retries} attempts"
                ) from e

            # ── 4xx: Client error (our fault) ─────────────────────────────
            # Bad URL, wrong params — retrying won't help
            else:
                raise ExtractError(
                    f"Client error {status} from {url}: {e}"
                ) from e

        except Timeout:
            # Server didn't respond in time
            logger.warning(
                f"Timeout calling {url} | Attempt {attempt}/{max_retries}"
            )
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise ExtractError(
                f"Request to {url} timed out after {max_retries} attempts"
            )

        except ConnectionError:
            # No internet, DNS failure, etc.
            logger.error(f"Cannot connect to {url} — check your internet connection")
            raise ExtractError(
                f"Connection failed for {url}. "
                f"Is the server reachable?"
            )

    # If the loop finishes without returning, all retries failed
    raise ExtractError(f"All {max_retries} attempts failed for {url}")


def save_json(data: dict | list, filepath) -> None:
    """
    Save data to a JSON file with error handling and logging.

    Args:
        data:     Python dict or list to save
        filepath: Where to save it (string or Path object)
    """
    import json
    from pathlib import Path

    filepath = Path(filepath)

    try:
        # Create parent directories if they don't exist
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write the file with nice formatting (indent=2 makes it human-readable)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(data) if isinstance(data, list) else 1} records → {filepath}")

    except PermissionError:
        # We don't have write access to this location
        raise ExtractError(f"Permission denied writing to {filepath}")

    except OSError as e:
        # Disk full, path too long, etc.
        raise ExtractError(f"Failed to write {filepath}: {e}")


def load_json(filepath) -> dict | list:
    """
    Load a JSON file with error handling.

    Args:
        filepath: Path to the JSON file

    Returns:
        Parsed JSON as dict or list
    """
    import json
    from pathlib import Path

    filepath = Path(filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.debug(f"Loaded {filepath}")
        return data

    except FileNotFoundError:
        raise ExtractError(
            f"File not found: {filepath}. "
            f"Has the extract step run yet?"
        )

    except json.JSONDecodeError as e:
        raise ExtractError(
            f"Invalid JSON in {filepath}: {e}. "
            f"The file may be corrupted or incomplete."
        )