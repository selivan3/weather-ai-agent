from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import DEFAULT_CHAT_LANGUAGE, Settings

logger = logging.getLogger(__name__)


class WeatherProviderError(RuntimeError):
    def __init__(
        self,
        detail: str,
        *,
        code: str = "weather_provider_error",
        status_code: int = 502,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code


class WeatherAPIClient:
    BASE_URL = "https://api.weatherapi.com/v1"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_current(
        self,
        city: str,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> dict[str, Any]:
        return await self._request(
            "/current.json",
            {"q": city, "aqi": "no", "lang": language},
        )

    async def get_forecast(
        self,
        city: str,
        days: int,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> dict[str, Any]:
        return await self._request(
            "/forecast.json",
            {
                "q": city,
                "days": days,
                "aqi": "no",
                "alerts": "no",
                "lang": language,
            },
        )

    async def get_history(
        self,
        city: str,
        date_value: str,
        *,
        language: str = DEFAULT_CHAT_LANGUAGE,
    ) -> dict[str, Any]:
        return await self._request(
            "/history.json",
            {"q": city, "dt": date_value, "aqi": "no", "lang": language},
        )

    async def aclose(self) -> None:
        return None

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.weatherapi_key:
            raise WeatherProviderError(
                "Переменная WEATHERAPI_KEY не настроена.",
                code="weather_provider_not_configured",
                status_code=503,
            )

        merged_params = {"key": self._settings.weatherapi_key, **params}
        attempt_count = self._settings.weather_retry_attempts + 1
        last_error: Exception | None = None

        for attempt in range(1, attempt_count + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.BASE_URL,
                    timeout=self._settings.weather_timeout_seconds,
                    headers={"Accept": "application/json"},
                ) as client:
                    response = await client.get(path, params=merged_params)

                if response.is_error:
                    self._raise_weather_error(response)

                return response.json()
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "Transient WeatherAPI network error",
                    extra={
                        "path": path,
                        "attempt": attempt,
                        "city": params.get("q"),
                    },
                )
                if attempt == attempt_count:
                    break

        raise WeatherProviderError(
            "Погодный провайдер временно недоступен. Попробуйте позже.",
            code="weather_provider_unavailable",
        ) from last_error

    def _raise_weather_error(self, response: httpx.Response) -> None:
        provider_message = None
        try:
            payload = response.json()
            provider_message = payload.get("error", {}).get("message")
        except ValueError:
            provider_message = None

        if response.status_code == 400 and provider_message:
            detail = "Погодный провайдер отклонил запрос."
            code = "weather_provider_bad_request"
            status_code = 400
        elif response.status_code in {401, 403}:
            detail = "Погодный провайдер отклонил запрос. Проверьте WEATHERAPI_KEY."
            code = "weather_provider_auth_error"
            status_code = 502
        elif response.status_code == 404:
            detail = "Локация не найдена."
            code = "weather_provider_not_found"
            status_code = 404
        elif provider_message:
            detail = "Погодный провайдер вернул ошибку."
            code = "weather_provider_error"
            status_code = 502
        else:
            detail = "Погодный провайдер вернул непредвиденную ошибку."
            code = "weather_provider_error"
            status_code = 502

        logger.error(
            "WeatherAPI responded with an error",
            extra={
                "status_code": response.status_code,
                "detail": detail,
            },
        )
        raise WeatherProviderError(detail, code=code, status_code=status_code)
