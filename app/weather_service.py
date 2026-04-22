from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from cachetools import TTLCache

from app.config import (
    DEFAULT_CHAT_LANGUAGE,
    Settings,
    localize_city_name_for_language,
)
from app.schemas import (
    CurrentWeatherInput,
    CurrentWeatherResponse,
    ForecastDayResponse,
    ForecastInput,
    ForecastResponse,
    HistoryInput,
    HistoryResponse,
)
from app.weather_client import WeatherAPIClient


class WeatherService:
    def __init__(
        self,
        settings: Settings,
        client: WeatherAPIClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or WeatherAPIClient(settings)
        self._current_cache: TTLCache[str, CurrentWeatherResponse] = TTLCache(
            maxsize=settings.current_weather_cache_maxsize,
            ttl=settings.current_weather_cache_ttl_seconds,
        )
        self._cache_lock = asyncio.Lock()

    async def get_current_weather(
        self,
        city: str | None = None,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> CurrentWeatherResponse:
        payload = CurrentWeatherInput(city=city)
        resolved_city = payload.city
        assert resolved_city is not None
        cache_key = f"{resolved_city.casefold()}:{language}"

        cached = self._current_cache.get(cache_key)
        if cached is not None:
            return cached

        async with self._cache_lock:
            cached = self._current_cache.get(cache_key)
            if cached is not None:
                return cached

            raw = await self._client.get_current(resolved_city, language=language)
            result = CurrentWeatherResponse(
                city=localize_city_name_for_language(raw["location"]["name"], language),
                temp_c=raw["current"]["temp_c"],
                feelslike_c=raw["current"]["feelslike_c"],
                condition=raw["current"]["condition"]["text"],
                humidity=raw["current"]["humidity"],
                wind_kph=raw["current"]["wind_kph"],
                pressure_mb=raw["current"]["pressure_mb"],
                last_updated=raw["current"]["last_updated"],
            )
            self._current_cache[cache_key] = result
            return result

    async def get_forecast(
        self,
        city: str | None = None,
        days: int | None = None,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> ForecastResponse:
        payload = ForecastInput(city=city, days=days)
        resolved_city = payload.city
        resolved_days = payload.days
        assert resolved_city is not None
        assert resolved_days is not None

        raw = await self._client.get_forecast(
            resolved_city,
            resolved_days,
            language=language,
        )
        forecast = [
            ForecastDayResponse(
                date=day["date"],
                condition=day["day"]["condition"]["text"],
                mintemp_c=day["day"]["mintemp_c"],
                maxtemp_c=day["day"]["maxtemp_c"],
                avgtemp_c=day["day"]["avgtemp_c"],
                maxwind_kph=day["day"]["maxwind_kph"],
                daily_chance_of_rain=int(day["day"].get("daily_chance_of_rain", 0)),
                sunrise=day["astro"].get("sunrise"),
                sunset=day["astro"].get("sunset"),
                morning_temp_c=self._extract_hour_temp(day["hour"], 8),
                day_temp_c=self._extract_hour_temp(day["hour"], 14),
                evening_temp_c=self._extract_hour_temp(day["hour"], 20),
            )
            for day in raw["forecast"]["forecastday"]
        ]

        return ForecastResponse(
            city=localize_city_name_for_language(raw["location"]["name"], language),
            days=len(forecast),
            forecast=forecast,
        )

    async def get_history(
        self,
        city: str | None = None,
        date_value: date | str | None = None,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> HistoryResponse:
        payload = HistoryInput(city=city, date=date_value)
        resolved_city = payload.city
        assert resolved_city is not None

        raw = await self._client.get_history(
            resolved_city,
            payload.date.isoformat(),
            language=language,
        )
        day = raw["forecast"]["forecastday"][0]["day"]
        return HistoryResponse(
            city=localize_city_name_for_language(raw["location"]["name"], language),
            date=payload.date,
            condition=day["condition"]["text"],
            mintemp_c=day["mintemp_c"],
            maxtemp_c=day["maxtemp_c"],
            avgtemp_c=day["avgtemp_c"],
            maxwind_kph=day["maxwind_kph"],
            totalprecip_mm=day["totalprecip_mm"],
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _extract_hour_temp(hours: list[dict[str, Any]], target_hour: int) -> float | None:
        if not hours:
            return None

        def hour_distance(item: dict[str, Any]) -> int:
            timestamp = str(item.get("time", ""))
            try:
                hour = int(timestamp.split(" ")[-1].split(":")[0])
            except (IndexError, ValueError):
                return 24
            return abs(hour - target_hour)

        closest = min(hours, key=hour_distance)
        return closest.get("temp_c")


_weather_service: WeatherService | None = None


def get_weather_service() -> WeatherService:
    global _weather_service
    if _weather_service is None:
        from app.config import get_settings

        _weather_service = WeatherService(settings=get_settings())
    return _weather_service


async def close_weather_service() -> None:
    global _weather_service
    if _weather_service is not None:
        await _weather_service.aclose()
        _weather_service = None
