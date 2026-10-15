from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import math
import threading
import time

import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class WeatherDataError(Exception):
    """Raised when the weather provider returns an unusable response."""


class WeatherRateLimitError(WeatherDataError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"天気サービスのアクセス上限に達しました。約{retry_after_seconds}秒後に再取得できます。"
        )


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Weather:
    city: str
    current_temperature: float
    feels_like: float
    humidity: int
    high: float
    low: float
    rain_probability: int
    wind_speed: float
    code: int
    updated_at: str


@dataclass(frozen=True)
class HistoricalMonthlyAverage:
    city: str
    year: int
    month: int
    average_temperature: float
    sample_days: int


CITIES = {
    "東京": City("東京", 35.6762, 139.6503),
    "札幌": City("札幌", 43.0618, 141.3545),
    "仙台": City("仙台", 38.2682, 140.8694),
    "名古屋": City("名古屋", 35.1815, 136.9066),
    "京都": City("京都", 35.0116, 135.7681),
    "大阪": City("大阪", 34.6937, 135.5023),
    "広島": City("広島", 34.3853, 132.4553),
    "福岡": City("福岡", 33.5902, 130.4017),
    "那覇": City("那覇", 26.2124, 127.6809),
}

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_RATE_LIMIT_DEFAULT_SECONDS = 60
_RATE_LIMIT_MAX_SECONDS = 3600
_rate_limit_until = {"forecast": 0.0, "archive": 0.0}
_rate_limit_lock = threading.Lock()


def _retry_after_seconds(value: str | None) -> int:
    if value:
        try:
            seconds = int(value)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                seconds = math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                seconds = _RATE_LIMIT_DEFAULT_SECONDS
        return min(max(seconds, 1), _RATE_LIMIT_MAX_SECONDS)
    return _RATE_LIMIT_DEFAULT_SECONDS


def parse_weather(city_name: str, payload: dict) -> Weather:
    try:
        current = payload["current"]
        daily = payload["daily"]
        return Weather(
            city=city_name,
            current_temperature=float(current["temperature_2m"]),
            feels_like=float(current["apparent_temperature"]),
            humidity=int(current["relative_humidity_2m"]),
            high=float(daily["temperature_2m_max"][0]),
            low=float(daily["temperature_2m_min"][0]),
            rain_probability=int(daily["precipitation_probability_max"][0]),
            wind_speed=float(daily["wind_speed_10m_max"][0]),
            code=int(current["weather_code"]),
            updated_at=str(current["time"]),
        )
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise WeatherDataError("天気サービスから不完全なデータが返されました。") from error


def parse_historical_monthly_average(
    city_name: str,
    year: int,
    month: int,
    payload: dict,
) -> HistoricalMonthlyAverage:
    try:
        raw_values = payload["daily"]["temperature_2m_mean"]
        if not isinstance(raw_values, list):
            raise TypeError("temperature_2m_mean must be a list")
        values = [float(value) for value in raw_values if value is not None]
        values = [value for value in values if math.isfinite(value)]
        if not values:
            raise ValueError("No daily mean temperatures")
        return HistoricalMonthlyAverage(
            city=city_name,
            year=year,
            month=month,
            average_temperature=math.fsum(values) / len(values),
            sample_days=len(values),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherDataError("前年の平均気温データを読み取れませんでした。") from error


def _request_json(endpoint: str, params: dict, rate_limit_scope: str) -> dict:
    with _rate_limit_lock:
        remaining = math.ceil(
            _rate_limit_until[rate_limit_scope] - time.monotonic()
        )
    if remaining > 0:
        raise WeatherRateLimitError(remaining)

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=1,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(
            endpoint,
            params=params,
            timeout=(5, 20),
        )
    if response.status_code == 429:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        with _rate_limit_lock:
            _rate_limit_until[rate_limit_scope] = max(
                _rate_limit_until[rate_limit_scope],
                time.monotonic() + retry_after,
            )
        raise WeatherRateLimitError(retry_after)
    response.raise_for_status()
    try:
        payload = response.json()
    except requests.JSONDecodeError as error:
        raise WeatherDataError("天気サービスの応答を読み取れませんでした。") from error
    if not isinstance(payload, dict):
        raise WeatherDataError("天気サービスから不正なデータが返されました。")
    return payload


@st.cache_data(ttl="1h", max_entries=16)
def get_weather(city_name: str) -> Weather:
    city = CITIES.get(city_name)
    if city is None:
        raise ValueError(f"対応していない地域です: {city_name}")

    payload = _request_json(
        _FORECAST_URL,
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,wind_speed_10m_max"
            ),
            "forecast_days": 1,
            "timezone": "Asia/Tokyo",
        },
        "forecast",
    )
    return parse_weather(city_name, payload)


@st.cache_data(ttl="30d", max_entries=128)
def get_historical_monthly_average(
    city_name: str,
    year: int,
    month: int,
) -> HistoricalMonthlyAverage:
    city = CITIES.get(city_name)
    if city is None:
        raise ValueError(f"対応していない地域です: {city_name}")
    if month < 1 or month > 12:
        raise ValueError(f"対応していない月です: {month}")

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    payload = _request_json(
        _ARCHIVE_URL,
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "temperature_2m_mean",
            "timezone": "Asia/Tokyo",
        },
        "archive",
    )
    return parse_historical_monthly_average(city_name, year, month, payload)


def describe_weather_code(code: int) -> str:
    if code == 0:
        return "快晴"
    if code in (1, 2):
        return "晴れ時々くもり"
    if code == 3:
        return "くもり"
    if code in (45, 48):
        return "霧"
    if code in (51, 53, 55, 56, 57):
        return "霧雨"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if code in (95, 96, 99):
        return "雷雨"
    return "天気情報"
