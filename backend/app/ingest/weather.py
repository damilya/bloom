"""Open-Meteo weather (free, no API key). Archive for the past, forecast for the next days."""
from datetime import date, timedelta

import httpx

from app.config import get_settings
from app.data import db

WMO = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent showers", 95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code"


def _fetch(url: str, start: date, end: date) -> list[dict]:
    s = get_settings()
    params = {
        "latitude": s.home_lat, "longitude": s.home_lon, "daily": DAILY,
        "timezone": "Europe/Brussels", "start_date": start.isoformat(), "end_date": end.isoformat(),
    }
    resp = httpx.get(url, params=params, timeout=20)
    resp.raise_for_status()
    d = resp.json()["daily"]
    return [
        {
            "date": d["time"][i], "tmax": d["temperature_2m_max"][i], "tmin": d["temperature_2m_min"][i],
            "precip_mm": d["precipitation_sum"][i], "wind_max": d["wind_speed_10m_max"][i],
            "weather_code": d["weather_code"][i],
        }
        for i in range(len(d["time"]))
        if d["temperature_2m_max"][i] is not None
    ]


def sync_weather(start: date, end: date) -> int:
    """Fill the weather table for [start, end]. Archive API lags ~5 days, so recent days use forecast."""
    today = date.today()
    records: list[dict] = []
    archive_end = min(end, today - timedelta(days=6))
    if start <= archive_end:
        records += _fetch("https://archive-api.open-meteo.com/v1/archive", start, archive_end)
    fc_start = max(start, today - timedelta(days=5))
    fc_end = min(end, today + timedelta(days=14))
    if fc_start <= fc_end:
        records += _fetch("https://api.open-meteo.com/v1/forecast", fc_start, fc_end)
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO weather(date, tmax, tmin, precip_mm, wind_max, weather_code) "
            "VALUES(:date, :tmax, :tmin, :precip_mm, :wind_max, :weather_code)",
            records,
        )
    return len(records)


def describe(code: int | None) -> str:
    return WMO.get(code or 0, "unknown")
