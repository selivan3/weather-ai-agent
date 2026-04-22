from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain.tools import tool

from app.schemas import (
    AgentCurrentWeatherInput,
    AgentForecastInput,
    AgentHistoryInput,
    CurrentWeatherResponse,
    ForecastDayResponse,
    ForecastResponse,
    HistoryResponse,
    WeatherWidgetInput,
)
from app.weather_client import WeatherProviderError
from app.weather_service import WeatherService


def _dump(model: Any) -> str:
    return model.model_dump_json(indent=2, ensure_ascii=False, exclude_none=True)


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _dump_error(exc: WeatherProviderError) -> str:
    return json.dumps(
        {
            "error": {
                "detail": exc.detail,
                "code": exc.code,
            }
        },
        ensure_ascii=False,
        indent=2,
    )


def _dump_widget_error(detail: str, *, code: str = "weather_widget_error") -> str:
    return _dump_payload(
        {
            "error": {
                "detail": detail,
                "code": code,
            }
        }
    )


def _default_widget_title(
    *,
    source: str,
    layout: str,
    language: str,
    resolved_date: str | None = None,
    days_count: int | None = None,
) -> str | None:
    if language == "en":
        titles = {
            "current_compact": "Current weather",
            "forecast_day": f"Forecast for {resolved_date}" if resolved_date else "Daily forecast",
            "forecast_week": "Weekly forecast",
            "forecast_dense": f"{days_count or 14}-day forecast",
            "forecast_month": "Long-range outlook",
            "history_compact": f"Weather on {resolved_date}" if resolved_date else "Historical weather",
        }
    else:
        titles = {
            "current_compact": "Текущая погода",
            "forecast_day": f"Прогноз на {resolved_date}" if resolved_date else "Прогноз на день",
            "forecast_week": "Прогноз на неделю",
            "forecast_dense": f"Прогноз на {days_count or 14} дней",
            "forecast_month": "Долгий прогноз",
            "history_compact": f"Погода на {resolved_date}" if resolved_date else "Историческая погода",
        }

    return titles.get(layout if source != "current" else "current_compact")


def _default_widget_note(layout: str, *, language: str) -> str | None:
    if layout != "forecast_month":
        return None

    if language == "en":
        return "WeatherAPI currently provides forecast data for up to 14 days."
    return "WeatherAPI сейчас отдаёт прогноз максимум на 14 дней."


def _default_show_actions(layout: str) -> bool:
    return layout in {"current_compact", "forecast_day", "history_compact"}


def _select_forecast_day(
    forecast: ForecastResponse,
    *,
    day_index: int | None,
    date_value: date | None,
) -> ForecastDayResponse | None:
    if date_value is not None:
        for item in forecast.forecast:
            if item.date == date_value:
                return item
        return None

    if day_index is not None:
        if 0 <= day_index < len(forecast.forecast):
            return forecast.forecast[day_index]
        return None

    return forecast.forecast[0] if forecast.forecast else None


def _build_current_widget_payload(
    current: CurrentWeatherResponse,
    *,
    language: str,
    title: str | None,
    note: str | None,
    show_actions: bool | None,
) -> dict[str, Any]:
    return {
        "widget": {
            "kind": "current",
            "layout": "current_compact",
            "language": language,
            "title": title
            or _default_widget_title(
                source="current",
                layout="current_compact",
                language=language,
            ),
            "note": note,
            "show_actions": (
                _default_show_actions("current_compact")
                if show_actions is None
                else show_actions
            ),
            "city": current.city,
            "condition": current.condition,
            "temp_c": current.temp_c,
            "feelslike_c": current.feelslike_c,
            "humidity": current.humidity,
            "wind_kph": current.wind_kph,
            "pressure_mb": current.pressure_mb,
            "last_updated": current.last_updated,
        }
    }


def _build_forecast_widget_payload(
    forecast: ForecastResponse,
    *,
    language: str,
    layout: str,
    title: str | None,
    note: str | None,
    day_index: int | None,
    date_value: date | None,
    show_actions: bool | None,
) -> dict[str, Any] | None:
    selected_days: list[ForecastDayResponse]

    if layout == "forecast_day":
        selected_day = _select_forecast_day(
            forecast,
            day_index=day_index,
            date_value=date_value,
        )
        if selected_day is None:
            return None
        selected_days = [selected_day]
    elif layout == "forecast_week":
        selected_days = forecast.forecast[:7]
    elif layout in {"forecast_dense", "forecast_month"}:
        selected_days = forecast.forecast[:14]
    else:
        return None

    resolved_date = selected_days[0].date.isoformat() if len(selected_days) == 1 else None
    resolved_note = note or _default_widget_note(layout, language=language)

    return {
        "widget": {
            "kind": "forecast",
            "layout": layout,
            "language": language,
            "title": title
            or _default_widget_title(
                source="forecast",
                layout=layout,
                language=language,
                resolved_date=resolved_date,
                days_count=len(selected_days),
            ),
            "note": resolved_note,
            "show_actions": (
                _default_show_actions(layout) if show_actions is None else show_actions
            ),
            "city": forecast.city,
            "days": len(selected_days),
            "forecast": [item.model_dump(mode="json") for item in selected_days],
        }
    }


def _build_history_widget_payload(
    history: HistoryResponse,
    *,
    language: str,
    title: str | None,
    note: str | None,
    show_actions: bool | None,
) -> dict[str, Any]:
    return {
        "widget": {
            "kind": "history",
            "layout": "history_compact",
            "language": language,
            "title": title
            or _default_widget_title(
                source="history",
                layout="history_compact",
                language=language,
                resolved_date=history.date.isoformat(),
            ),
            "note": note,
            "show_actions": (
                _default_show_actions("history_compact")
                if show_actions is None
                else show_actions
            ),
            "city": history.city,
            "date": history.date.isoformat(),
            "condition": history.condition,
            "mintemp_c": history.mintemp_c,
            "maxtemp_c": history.maxtemp_c,
            "avgtemp_c": history.avgtemp_c,
            "maxwind_kph": history.maxwind_kph,
            "totalprecip_mm": history.totalprecip_mm,
        }
    }


def build_weather_tools(
    service: WeatherService,
    *,
    default_city: str,
    language: str,
):
    latest_results: dict[str, CurrentWeatherResponse | ForecastResponse | HistoryResponse | None] = {
        "current": None,
        "forecast": None,
        "history": None,
    }

    @tool(args_schema=AgentCurrentWeatherInput)
    async def get_current_weather(city: str | None = None) -> str:
        """Получить текущую погоду по городу."""

        try:
            resolved_city = (
                city.strip()
                if isinstance(city, str) and city.strip()
                else default_city
            )
            result = await service.get_current_weather(
                city=resolved_city,
                language=language,
            )
            latest_results["current"] = result
            return _dump(result)
        except WeatherProviderError as exc:
            return _dump_error(exc)

    @tool(args_schema=AgentForecastInput)
    async def get_forecast(city: str | None = None, days: int | None = None) -> str:
        """Получить прогноз погоды на 1-14 дней."""

        try:
            resolved_city = (
                city.strip()
                if isinstance(city, str) and city.strip()
                else default_city
            )
            result = await service.get_forecast(
                city=resolved_city,
                days=days,
                language=language,
            )
            latest_results["forecast"] = result
            return _dump(result)
        except WeatherProviderError as exc:
            return _dump_error(exc)

    @tool(args_schema=AgentHistoryInput)
    async def get_history(date: str, city: str | None = None) -> str:
        """Получить историческую погоду за конкретную дату YYYY-MM-DD."""

        try:
            resolved_city = (
                city.strip()
                if isinstance(city, str) and city.strip()
                else default_city
            )
            result = await service.get_history(
                city=resolved_city,
                date_value=date,
                language=language,
            )
            latest_results["history"] = result
            return _dump(result)
        except WeatherProviderError as exc:
            return _dump_error(exc)

    @tool(args_schema=WeatherWidgetInput)
    async def show_weather_widget(
        source: str,
        layout: str,
        title: str | None = None,
        note: str | None = None,
        date: date | None = None,
        day_index: int | None = None,
        show_actions: bool | None = None,
    ) -> str:
        """
        Создать интерактивный погодный блок для уже полученных погодных данных.

        Вызывай этот инструмент только когда визуальный блок действительно помогает:
        - для конкретного дня: layout="forecast_day"
        - для недели: layout="forecast_week"
        - для 8-14 дней: layout="forecast_dense"
        - для длинного диапазона или запроса "на месяц": layout="forecast_month"
        - для текущей погоды: layout="current_compact"
        - для истории за дату: layout="history_compact"
        """

        if source == "current":
            if layout != "current_compact":
                return _dump_widget_error(
                    "Для source=current используй layout=current_compact.",
                    code="weather_widget_invalid_current_layout",
                )
            current = latest_results.get("current")
            if not isinstance(current, CurrentWeatherResponse):
                return _dump_widget_error(
                    "Сначала вызови get_current_weather, а потом show_weather_widget.",
                    code="weather_widget_missing_current",
                )
            return _dump_payload(
                _build_current_widget_payload(
                    current,
                    language=language,
                    title=title,
                    note=note,
                    show_actions=show_actions,
                )
            )

        if source == "forecast":
            forecast = latest_results.get("forecast")
            if not isinstance(forecast, ForecastResponse):
                return _dump_widget_error(
                    "Сначала вызови get_forecast, а потом show_weather_widget.",
                    code="weather_widget_missing_forecast",
                )

            payload = _build_forecast_widget_payload(
                forecast,
                language=language,
                layout=layout,
                title=title,
                note=note,
                day_index=day_index,
                date_value=date,
                show_actions=show_actions,
            )
            if payload is None:
                return _dump_widget_error(
                    "Не удалось собрать прогнозный блок с указанными параметрами.",
                    code="weather_widget_invalid_forecast_layout",
                )
            return _dump_payload(payload)

        if layout != "history_compact":
            return _dump_widget_error(
                "Для source=history используй layout=history_compact.",
                code="weather_widget_invalid_history_layout",
            )

        history = latest_results.get("history")
        if not isinstance(history, HistoryResponse):
            return _dump_widget_error(
                "Сначала вызови get_history, а потом show_weather_widget.",
                code="weather_widget_missing_history",
            )
        return _dump_payload(
            _build_history_widget_payload(
                history,
                language=language,
                title=title,
                note=note,
                show_actions=show_actions,
            )
        )

    return [get_current_weather, get_forecast, get_history, show_weather_widget]
