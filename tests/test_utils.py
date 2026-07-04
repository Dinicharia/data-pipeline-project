# tests/test_utils.py
# Tests for HTTP utilities using mock objects.
# We never make real HTTP calls in tests — that would make tests
# slow, flaky (depends on internet), and burn API rate limits.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock  import patch, MagicMock
from requests.exceptions import Timeout, ConnectionError


class TestSafeRequest:

    def test_successful_request_returns_json(self):
        """A 200 response returns the parsed JSON body."""
        from src.utils import safe_request

        mock_response          = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"temp": 24.5}

        with patch("src.utils.requests.get", return_value=mock_response):
            result = safe_request("https://fake-api.com/weather")

        assert result == {"temp": 24.5}

    def test_401_raises_api_auth_error(self):
        """A 401 response raises APIAuthError immediately (no retry)."""
        from src.utils      import safe_request
        from src.exceptions import APIAuthError
        from requests.exceptions import HTTPError

        mock_response             = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = HTTPError(
            response=mock_response
        )

        with patch("src.utils.requests.get", return_value=mock_response):
            with pytest.raises(APIAuthError):
                safe_request("https://fake-api.com/weather")

    def test_timeout_retries_and_raises(self):
        """A Timeout retries max_retries times then raises ExtractError."""
        from src.utils      import safe_request
        from src.exceptions import ExtractError

        with patch("src.utils.requests.get", side_effect=Timeout):
            with patch("src.utils.time.sleep"):  # don't actually sleep in tests
                with pytest.raises(ExtractError):
                    safe_request(
                        "https://fake-api.com/weather",
                        max_retries=2
                    )

    def test_429_backs_off_and_retries(self):
        """A 429 triggers exponential backoff and retries."""
        from src.utils import safe_request
        from requests.exceptions import HTTPError

        # First call: 429. Second call: 200 success.
        rate_limited          = MagicMock()
        rate_limited.status_code = 429
        rate_limited.raise_for_status.side_effect = HTTPError(
            response=rate_limited
        )

        success               = MagicMock()
        success.status_code   = 200
        success.json.return_value = {"data": "ok"}

        with patch("src.utils.requests.get",
                   side_effect=[rate_limited, success]):
            with patch("src.utils.time.sleep") as mock_sleep:
                result = safe_request("https://fake-api.com/weather")

        assert result == {"data": "ok"}
        mock_sleep.assert_called_once()    # backoff sleep was called


class TestSaveAndLoadJson:

    def test_round_trip(self, tmp_path):
        """Data saved with save_json can be read back with load_json."""
        from src.utils import save_json, load_json

        filepath = tmp_path / "test.json"
        data     = {"city": "Nairobi", "temp": 24.5, "readings": [1, 2, 3]}

        save_json(data, filepath)
        loaded = load_json(filepath)

        assert loaded == data

    def test_load_missing_file_raises(self, tmp_path):
        """Loading a non-existent file raises ExtractError."""
        from src.utils      import load_json
        from src.exceptions import ExtractError

        with pytest.raises(ExtractError):
            load_json(tmp_path / "does_not_exist.json")