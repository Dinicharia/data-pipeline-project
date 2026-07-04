# tests/test_transformers.py
# Unit tests for our transformer functions.
# Each test is completely isolated — no database, no API calls,
# no file system. We test the logic using invented test data.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy  as np
from datetime import timezone


class TestFlattenWeatherRecords:
    """Tests for the flatten_weather_records() function."""

    def _make_record(self, **overrides) -> dict:
        """Helper: build a minimal valid API response record."""
        record = {
            "_city_id"      : 1,
            "name"          : "Nairobi",
            "main"          : {
                "temp"      : 24.5,
                "feels_like": 23.0,
                "humidity"  : 65,
                "pressure"  : 1013,
            },
            "weather"       : [{"description": "clear sky", "main": "Clear"}],
            "wind"          : {"speed": 3.6},
            "dt"            : 1719561600,
            "_extracted_at" : "2026-07-01T08:00:00+00:00",
        }
        record.update(overrides)
        return record

    def test_flattens_basic_record(self):
        """A valid record produces exactly one row with correct values."""
        from src.transformers.weather_transformer import flatten_weather_records

        records = [self._make_record()]
        df      = flatten_weather_records(records)

        assert len(df) == 1
        assert df.iloc[0]["city_id"]       == 1
        assert df.iloc[0]["city_name"]     == "Nairobi"
        assert df.iloc[0]["temperature_c"] == 24.5
        assert df.iloc[0]["humidity_pct"]  == 65

    def test_skips_record_with_missing_main(self):
        """A record missing the 'main' key is skipped, not crashed."""
        from src.transformers.weather_transformer import flatten_weather_records

        good_record = self._make_record()
        bad_record  = self._make_record()
        del bad_record["main"]              # simulate malformed API response

        df = flatten_weather_records([good_record, bad_record])
        assert len(df) == 1                 # only the good record survives

    def test_handles_missing_wind(self):
        """Records without wind data produce None for wind_speed."""
        from src.transformers.weather_transformer import flatten_weather_records

        record = self._make_record()
        del record["wind"]                  # calm weather — no wind key

        df = flatten_weather_records([record])
        assert df.iloc[0]["wind_speed_ms"] is None

    def test_empty_input_raises(self):
        """Empty input after filtering raises TransformError."""
        from src.transformers.weather_transformer import flatten_weather_records
        from src.exceptions import TransformError

        bad_record = self._make_record()
        del bad_record["main"]

        with pytest.raises(TransformError):
            flatten_weather_records([bad_record])


class TestCleanWeatherDataframe:
    """Tests for clean_weather_dataframe()."""

    def _make_df(self, **overrides) -> pd.DataFrame:
        """Build a minimal valid flat DataFrame."""
        data = {
            "city_id"         : [1],
            "city_name"       : ["Nairobi"],
            "temperature_c"   : [24.5],
            "feels_like_c"    : [23.0],
            "humidity_pct"    : [65],
            "pressure_hpa"    : [1013.0],
            "wind_speed_ms"   : [3.6],
            "description"     : ["clear sky"],
            "weather_main"    : ["Clear"],
            "recorded_at_unix": [1719561600],
            "extracted_at"    : ["2026-07-01T08:00:00+00:00"],
        }
        data.update(overrides)
        return pd.DataFrame(data)

    def test_converts_unix_timestamp(self):
        """recorded_at_unix becomes a timezone-aware datetime."""
        from src.transformers.weather_transformer import clean_weather_dataframe

        df      = self._make_df()
        cleaned = clean_weather_dataframe(df)

        assert "recorded_at" in cleaned.columns
        assert "recorded_at_unix" not in cleaned.columns
        assert cleaned["recorded_at"].dt.tz == timezone.utc

    def test_fills_missing_wind_with_zero(self):
        """Missing wind speed is filled with 0.0 (calm conditions)."""
        from src.transformers.weather_transformer import clean_weather_dataframe

        df             = self._make_df()
        df["wind_speed_ms"] = None

        cleaned = clean_weather_dataframe(df)
        assert cleaned["wind_speed_ms"].iloc[0] == 0.0

    def test_drops_invalid_temperature(self):
        """Temperatures outside [-90, 60] are dropped."""
        from src.transformers.weather_transformer import clean_weather_dataframe

        df = self._make_df(temperature_c=[999.9])
        cleaned = clean_weather_dataframe(df)
        assert len(cleaned) == 0

    def test_drops_invalid_humidity(self):
        """Humidity outside [0, 100] is dropped."""
        from src.transformers.weather_transformer import clean_weather_dataframe

        df      = self._make_df(humidity_pct=[150])
        cleaned = clean_weather_dataframe(df)
        assert len(cleaned) == 0

    def test_removes_duplicates(self):
        """Duplicate (city_id, recorded_at) rows are deduplicated."""
        from src.transformers.weather_transformer import clean_weather_dataframe

        # Two identical records
        df = pd.concat([self._make_df(), self._make_df()], ignore_index=True)
        cleaned = clean_weather_dataframe(df)
        assert len(cleaned) == 1