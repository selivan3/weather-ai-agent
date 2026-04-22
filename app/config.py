from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "weather-agent"
APP_TITLE = "Агент Погоды"
AUTHOR_NAME = "Иван Селиванов"
AUTHOR_URL = "https://ivan-selivanov.ru/"
STACK_LABEL = (
    "FastAPI · Chainlit · LangChain · Langfuse · "
    "Pydantic · Yandex AI Studio · WeatherAPI"
)
DEFAULT_CITY = "Krasnodar"
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_CHAT_LANGUAGE = "ru"
DEFAULT_FORECAST_DAYS = 3
MAX_FORECAST_DAYS = 14
MIN_HISTORY_DATE = date(2010, 1, 1)
CURRENT_WEATHER_CACHE_TTL_SECONDS = 300
SUPPORTED_CHAT_LANGUAGES = {
    "Русский": "ru",
    "English": "en",
}
SUPPORTED_CHAT_TIMEZONES = {
    "Москва (Europe/Moscow)": "Europe/Moscow",
    "Калининград (Europe/Kaliningrad)": "Europe/Kaliningrad",
    "Екатеринбург (Asia/Yekaterinburg)": "Asia/Yekaterinburg",
    "Новосибирск (Asia/Novosibirsk)": "Asia/Novosibirsk",
    "Иркутск (Asia/Irkutsk)": "Asia/Irkutsk",
    "Владивосток (Asia/Vladivostok)": "Asia/Vladivostok",
    "UTC": "UTC",
}
PROMPT_LANGUAGE_NAMES = {
    "ru": "русском",
    "en": "английском",
}
CITY_LOCALIZATION_RU = {
    "krasnodar": "Краснодар",
    "moscow": "Москва",
    "saint petersburg": "Санкт-Петербург",
    "st petersburg": "Санкт-Петербург",
    "sochi": "Сочи",
    "kazan": "Казань",
    "yekaterinburg": "Екатеринбург",
    "novosibirsk": "Новосибирск",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    yandex_api_key: str | None = Field(default=None, alias="YANDEX_API_KEY", repr=False)
    yandex_folder_id: str | None = Field(default=None, alias="YANDEX_FOLDER_ID")
    yandex_model_uri: str | None = Field(default=None, alias="YANDEX_MODEL_URI")

    weatherapi_key: str | None = Field(default=None, alias="WEATHERAPI_KEY", repr=False)

    langfuse_public_key: str | None = Field(
        default=None,
        alias="LANGFUSE_PUBLIC_KEY",
        repr=False,
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        alias="LANGFUSE_SECRET_KEY",
        repr=False,
    )
    langfuse_host: str | None = Field(
        default=None,
        alias="LANGFUSE_HOST",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )

    app_name: str = APP_NAME
    default_city: str = Field(default=DEFAULT_CITY, alias="DEFAULT_CITY")
    app_env: Literal["local", "heroku"] = Field(default="local", alias="APP_ENV")

    weather_timeout_seconds: int = Field(default=10, ge=1, le=30)
    weather_retry_attempts: int = Field(default=1, ge=0, le=3)
    current_weather_cache_ttl_seconds: int = Field(
        default=CURRENT_WEATHER_CACHE_TTL_SECONDS,
        ge=30,
        le=3600,
    )
    current_weather_cache_maxsize: int = Field(default=128, ge=1, le=1024)
    default_forecast_days: int = Field(
        default=DEFAULT_FORECAST_DAYS,
        ge=1,
        le=MAX_FORECAST_DAYS,
    )
    model_request_timeout_seconds: int = Field(default=60, ge=1, le=300)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1200, ge=128, le=8192)

    @field_validator(
        "yandex_api_key",
        "yandex_folder_id",
        "yandex_model_uri",
        "weatherapi_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_host",
        mode="before",
    )
    @classmethod
    def blank_strings_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("default_city", mode="before")
    @classmethod
    def validate_default_city(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("DEFAULT_CITY must be a string.")

        stripped = value.strip()
        if not stripped:
            raise ValueError("DEFAULT_CITY must not be empty.")
        return stripped

    @property
    def stack_label(self) -> str:
        return STACK_LABEL

    @property
    def author_name(self) -> str:
        return AUTHOR_NAME

    @property
    def author_url(self) -> str:
        return AUTHOR_URL

    @property
    def default_city_label(self) -> str:
        return localize_city_name(self.default_city)

    @property
    def langfuse_enabled(self) -> bool:
        return all(
            [self.langfuse_public_key, self.langfuse_secret_key, self.langfuse_host]
        )

    @property
    def yandex_enabled(self) -> bool:
        return all([self.yandex_api_key, self.yandex_folder_id, self.yandex_model_uri])

    @property
    def weatherapi_enabled(self) -> bool:
        return bool(self.weatherapi_key)

    @property
    def is_weatherapi_configured(self) -> bool:
        return self.weatherapi_enabled

    @property
    def is_yandex_configured(self) -> bool:
        return self.yandex_enabled

    @property
    def is_langfuse_configured(self) -> bool:
        return self.langfuse_enabled

    @property
    def model_label(self) -> str:
        if not self.yandex_model_uri:
            return "unconfigured"

        parts = [part for part in self.yandex_model_uri.split("/") if part]
        if len(parts) >= 2:
            return parts[-2]
        return parts[-1]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def localize_city_name(city: str) -> str:
    return localize_city_name_for_language(city)


def localize_city_name_for_language(
    city: str,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str:
    normalized = city.strip().lower()
    if language == "ru":
        localized = CITY_LOCALIZATION_RU.get(normalized)
        if localized:
            return localized
    return city.strip()


def get_language_label(language: str) -> str:
    for label, value in SUPPORTED_CHAT_LANGUAGES.items():
        if value == language:
            return label
    return language


def get_prompt_language_name(language: str) -> str:
    return PROMPT_LANGUAGE_NAMES.get(
        language,
        PROMPT_LANGUAGE_NAMES[DEFAULT_CHAT_LANGUAGE],
    )
