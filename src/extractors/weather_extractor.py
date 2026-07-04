# src/extractors/weather_extractor.py
# Extracts current weather data from OpenWeatherMap API.
# Docs: https://openweathermap.org/current

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config      import WEATHER_API_KEY, DATA_DIR
from src.utils       import safe_request, save_json
from src.date_utils  import now_utc, make_filename
from src.logger      import get_logger
from src.exceptions  import ExtractError, APIAuthError

logger = get_logger(__name__)

# The cities our pipeline monitors
# Each entry: (city name, country code, our database city_id)
MONITORED_CITIES = [
    ("Nairobi",  "KE", 1),
    ("London",   "GB", 2),
    ("New York", "US", 3),
    ("Tokyo",    "JP", 4),
    ("Sydney",   "AU", 5),
]

# Base URL for OpenWeatherMap current weather endpoint
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def extract_city_weather(city_name: str, country_code: str) -> dict:
    """
    Fetch current weather for one city from OpenWeatherMap.

    Args:
        city_name:    e.g. "Nairobi"
        country_code: ISO 3166-1 alpha-2, e.g. "KE"

    Returns:
        Raw API response as a dict

    Raises:
        ExtractError:  if the request fails after retries
        APIAuthError:  if the API key is invalid
    """
    if not WEATHER_API_KEY:
        raise APIAuthError(
            "WEATHER_API_KEY is not set in config/secrets.env. "
            "Get a free key at openweathermap.org"
        )

    logger.info(f"Fetching weather: {city_name}, {country_code}")

    # Query parameters appended to the URL:
    # ?q=Nairobi,KE&appid=abc123&units=metric
    params = {
        "q"     : f"{city_name},{country_code}",
        "appid" : WEATHER_API_KEY,
        "units" : "metric",     # Celsius; use "imperial" for Fahrenheit
    }

    raw = safe_request(BASE_URL, params=params)

    # Add our own metadata to the raw response
    # This lets us track exactly when and how we fetched it
    raw["_extracted_at"] = now_utc().isoformat()
    raw["_city_name"]    = city_name
    raw["_country_code"] = country_code

    logger.debug(
        f"  {city_name}: {raw['main']['temp']}°C, "
        f"{raw['main']['humidity']}% humidity, "
        f"{raw['weather'][0]['description']}"
    )

    return raw


def extract_all_cities() -> list[dict]:
    """
    Fetch weather for all monitored cities and save raw data to disk.

    Returns:
        List of raw API responses, one per city
    """
    logger.info(f"Starting weather extraction for {len(MONITORED_CITIES)} cities")

    results   = []
    failed    = []

    for city_name, country_code, city_id in MONITORED_CITIES:
        try:
            data = extract_city_weather(city_name, country_code)
            data["_city_id"] = city_id     # attach our DB city_id
            results.append(data)

        except APIAuthError:
            # Bad key — no point trying other cities, fail immediately
            raise

        except ExtractError as e:
            # One city failed — log it and continue with the rest
            # A partial result is better than no result
            logger.error(f"Failed to extract {city_name}: {e}")
            failed.append(city_name)
            continue

    # Save all successful results to one file
    if results:
        filepath = DATA_DIR / "weather" / make_filename("weather_raw")
        DATA_DIR.joinpath("weather").mkdir(exist_ok=True)
        save_json(results, filepath)
        logger.info(
            f"Weather extraction complete: "
            f"{len(results)} succeeded, {len(failed)} failed"
        )

    if failed:
        logger.warning(f"Cities with extraction failures: {failed}")

    return results


if __name__ == "__main__":
    data = extract_all_cities()
    print(f"\nExtracted {len(data)} cities")
    for city in data:
        print(
            f"  {city['name']:12s} "
            f"{city['main']['temp']:5.1f}°C  "
            f"{city['main']['humidity']:3d}% humidity  "
            f"{city['weather'][0]['description']}"
        )