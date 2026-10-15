import unittest
from unittest.mock import Mock, patch

import requests
from urllib3.util.retry import Retry

import weather
from weather import WeatherDataError, get_weather, parse_weather


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


class WeatherTests(unittest.TestCase):
    def setUp(self):
        get_weather.clear()
        self.addCleanup(get_weather.clear)

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
    def test_get_weather_propagates_provider_http_errors(self, session_factory):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        response = session.get.return_value
        response.raise_for_status.side_effect = requests.HTTPError("503 Service Unavailable")
        session_factory.return_value = session

        with self.assertRaises(requests.HTTPError):
            get_weather("東京")


if __name__ == "__main__":
    unittest.main()
