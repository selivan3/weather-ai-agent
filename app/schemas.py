from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import (
    DEFAULT_CHAT_LANGUAGE,
    DEFAULT_TIMEZONE,
    MAX_FORECAST_DAYS,
    MIN_HISTORY_DATE,
    SUPPORTED_CHAT_LANGUAGES,
    SUPPORTED_CHAT_TIMEZONES,
    get_settings,
)

DateType = date


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SettingsSchema(StrictModel):
    app_name: str
    default_city: str
    app_env: str
    model_label: str
    langfuse_enabled: bool


class ChatPreferences(StrictModel):
    city: str = Field(default_factory=lambda: get_settings().default_city)
    timezone: str = Field(default=DEFAULT_TIMEZONE)
    language: Literal["ru", "en"] = Field(default=DEFAULT_CHAT_LANGUAGE)

    @field_validator("city", mode="before")
    @classmethod
    def default_city(cls, value: str | None) -> str:
        if value is None:
            return get_settings().default_city
        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_CHAT_TIMEZONES.values():
            raise ValueError("Часовой пояс не поддерживается.")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Часовой пояс не найден.") from exc
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value not in SUPPORTED_CHAT_LANGUAGES.values():
            raise ValueError("Язык не поддерживается.")
        return value


class LocationSchema(StrictModel):
    city: str
    region: str | None = None
    country: str | None = None
    localtime: str | None = None


class CurrentWeatherResponse(StrictModel):
    city: str
    temp_c: float
    feelslike_c: float
    condition: str
    humidity: int
    wind_kph: float
    pressure_mb: float
    last_updated: str


class ForecastDayResponse(StrictModel):
    date: date
    condition: str
    mintemp_c: float
    maxtemp_c: float
    avgtemp_c: float
    maxwind_kph: float
    daily_chance_of_rain: int
    sunrise: str | None = None
    sunset: str | None = None
    morning_temp_c: float | None = None
    day_temp_c: float | None = None
    evening_temp_c: float | None = None


class ForecastResponse(StrictModel):
    city: str
    days: int
    forecast: list[ForecastDayResponse]


class HistoryResponse(StrictModel):
    city: str
    date: date
    condition: str
    mintemp_c: float
    maxtemp_c: float
    avgtemp_c: float
    maxwind_kph: float
    totalprecip_mm: float


class ErrorResponse(StrictModel):
    detail: str
    code: str = "weather_provider_error"


class HealthResponse(StrictModel):
    status: str = "ok"


class CurrentWeatherInput(StrictModel):
    city: str | None = Field(default=None)

    @field_validator("city", mode="before")
    @classmethod
    def default_city(cls, value: str | None) -> str:
        if value is None:
            return get_settings().default_city
        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized


class AgentCurrentWeatherInput(StrictModel):
    city: str | None = Field(default=None)

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized


class ForecastInput(StrictModel):
    city: str | None = Field(default=None)
    days: int | None = Field(default=None, ge=1, le=MAX_FORECAST_DAYS)

    @field_validator("city", mode="before")
    @classmethod
    def default_city(cls, value: str | None) -> str:
        if value is None:
            return get_settings().default_city
        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized

    @field_validator("days", mode="before")
    @classmethod
    def default_days(cls, value: int | None) -> int:
        if value is None:
            return get_settings().default_forecast_days
        return value


class AgentForecastInput(StrictModel):
    city: str | None = Field(default=None)
    days: int | None = Field(default=None, ge=1, le=MAX_FORECAST_DAYS)

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized

    @field_validator("days", mode="before")
    @classmethod
    def default_days(cls, value: int | None) -> int:
        if value is None:
            return get_settings().default_forecast_days
        return value


class HistoryInput(StrictModel):
    city: str | None = Field(default=None)
    date: date

    @field_validator("city", mode="before")
    @classmethod
    def default_city(cls, value: str | None) -> str:
        if value is None:
            return get_settings().default_city
        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized

    @field_validator("date")
    @classmethod
    def validate_history_date(cls, value: date) -> date:
        if value < MIN_HISTORY_DATE:
            raise ValueError(
                f"Дата истории должна быть не раньше {MIN_HISTORY_DATE.isoformat()}."
            )
        return value


class AgentHistoryInput(StrictModel):
    city: str | None = Field(default=None)
    date: date

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Город не должен быть пустым.")
        return normalized

    @field_validator("date")
    @classmethod
    def validate_history_date(cls, value: date) -> date:
        if value < MIN_HISTORY_DATE:
            raise ValueError(
                f"Дата истории должна быть не раньше {MIN_HISTORY_DATE.isoformat()}."
            )
        return value


class WeatherWidgetInput(StrictModel):
    source: Literal["current", "forecast", "history"]
    layout: Literal[
        "current_compact",
        "forecast_day",
        "forecast_week",
        "forecast_dense",
        "forecast_month",
        "history_compact",
    ]
    title: str | None = None
    note: str | None = None
    date: DateType | None = None
    day_index: int | None = Field(default=None, ge=0, le=30)
    show_actions: bool | None = None

    @field_validator("title", "note")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None
