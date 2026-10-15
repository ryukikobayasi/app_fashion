import unittest
from unittest.mock import Mock, patch

import requests
from urllib3.util.retry import Retry

import weather
from weather import (
    WeatherDataError,
    WeatherRateLimitError,
    get_historical_monthly_average,
    get_weather,
    parse_historical_monthly_average,
    parse_weather,
)


def make_payload():
    return {
        "current": {
            "temperature_2m": 18.2,
            "apparent_temperature": 17.6,
            "relative_humidity_2m": 55,
            "weather_code": 1,
            "time": "2026-10-15T12:00",
        },
        "daily": {
            "temperature_2m_max": [22.0],
            "temperature_2m_min": [15.0],
            "precipitation_probability_max": [10],
            "wind_speed_10m_max": [12.0],
        },
    }


def make_archive_payload(temperatures=None):
    return {
        "daily": {
            "time": ["2025-03-01", "2025-03-02", "2025-03-03"],
            "temperature_2m_mean": temperatures if temperatures is not None else [10.0, None, 20.0],
        }
    }


class WeatherTests(unittest.TestCase):
    def setUp(self):
        get_weather.clear()
        get_historical_monthly_average.clear()
        with weather._rate_limit_lock:
            weather._rate_limit_until.update(forecast=0.0, archive=0.0)
        self.addCleanup(get_weather.clear)
        self.addCleanup(get_historical_monthly_average.clear)

    def test_parse_weather_maps_current_and_daily_forecast(self):
        result = parse_weather("東京", make_payload())

        self.assertEqual(result.city, "東京")
        self.assertEqual(result.current_temperature, 18.2)
        self.assertEqual(result.feels_like, 17.6)
        self.assertEqual(result.high, 22.0)
        self.assertEqual(result.low, 15.0)
        self.assertEqual(result.rain_probability, 10)

    def test_parse_weather_rejects_incomplete_provider_payload(self):
        with self.assertRaises(WeatherDataError):
            parse_weather("東京", {"current": {}, "daily": {}})

    def test_parse_historical_average_ignores_missing_days(self):
        result = parse_historical_monthly_average("東京", 2025, 3, make_archive_payload())

        self.assertEqual(result.city, "東京")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 3)
        self.assertEqual(result.average_temperature, 15.0)
        self.assertEqual(result.sample_days, 2)

    def test_parse_historical_average_rejects_missing_temperature_data(self):
        with self.assertRaises(WeatherDataError):
            parse_historical_monthly_average(
                "東京",
                2025,
                3,
                make_archive_payload([None, None, None]),
            )

    @patch("weather.requests.Session")
    def test_get_weather_uses_retrying_session_and_city_coordinates(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.return_value.json.return_value = make_payload()
        session_factory.return_value = session

        result = get_weather("東京")

        self.assertEqual(result.city, "東京")
        session.mount.assert_called_once()
        adapter = session.mount.call_args.args[1]
        self.assertIsInstance(adapter.max_retries, Retry)
        self.assertGreaterEqual(adapter.max_retries.total, 1)
        request = session.get.call_args
        self.assertEqual(request.args[0], weather._FORECAST_URL)
        self.assertEqual(request.kwargs["params"]["latitude"], weather.CITIES["東京"].latitude)
        self.assertEqual(request.kwargs["params"]["longitude"], weather.CITIES["東京"].longitude)
        self.assertEqual(request.kwargs["timeout"], (5, 20))

    @patch("weather.requests.Session")
    def test_get_historical_average_uses_full_previous_month(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.return_value.json.return_value = make_archive_payload()
        session_factory.return_value = session

        result = get_historical_monthly_average("東京", 2025, 3)

        self.assertEqual(result.average_temperature, 15.0)
        request = session.get.call_args
        self.assertEqual(request.args[0], weather._ARCHIVE_URL)
        self.assertEqual(request.kwargs["params"]["start_date"], "2025-03-01")
        self.assertEqual(request.kwargs["params"]["end_date"], "2025-03-31")
        self.assertEqual(request.kwargs["params"]["daily"], "temperature_2m_mean")
        self.assertEqual(request.kwargs["params"]["timezone"], "Asia/Tokyo")

    @patch("weather.requests.Session")
    def test_get_weather_propagates_provider_http_errors(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        response = session.get.return_value
        response.raise_for_status.side_effect = requests.HTTPError("503 Service Unavailable")
        session_factory.return_value = session

        with self.assertRaises(requests.HTTPError):
            get_weather("東京")

    @patch("weather.requests.Session")
    def test_rate_limit_is_not_retried_and_enters_a_shared_cooldown(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        response = session.get.return_value
        response.status_code = 429
        response.headers = {"Retry-After": "120"}
        session_factory.return_value = session

        with self.assertRaises(WeatherRateLimitError) as first_error:
            get_weather("東京")
        with self.assertRaises(WeatherRateLimitError) as cooldown_error:
            get_weather("大阪")

        self.assertEqual(first_error.exception.retry_after_seconds, 120)
        self.assertGreaterEqual(cooldown_error.exception.retry_after_seconds, 1)
        session.get.assert_called_once()

    @patch("weather.requests.Session")
    def test_archive_rate_limit_has_its_own_cooldown(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        response = session.get.return_value
        response.status_code = 429
        response.headers = {"Retry-After": "45"}
        session_factory.return_value = session

        with self.assertRaises(WeatherRateLimitError) as first_error:
            get_historical_monthly_average("東京", 2025, 3)
        with self.assertRaises(WeatherRateLimitError) as cooldown_error:
            get_historical_monthly_average("大阪", 2025, 3)

        self.assertEqual(first_error.exception.retry_after_seconds, 45)
        self.assertGreaterEqual(cooldown_error.exception.retry_after_seconds, 1)
        session.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
