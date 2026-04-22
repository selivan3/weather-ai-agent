from __future__ import annotations

import json
from typing import Any, Sequence

import chainlit as cl
from langchain_core.messages import BaseMessage, ToolMessage

from app.config import DEFAULT_CHAT_LANGUAGE
from app.schemas import CurrentWeatherResponse

WEATHER_ELEMENT_NAME = "WeatherSnippet"
WEATHER_WIDGET_TOOL_NAME = "show_weather_widget"


def create_current_weather_element(
    weather: CurrentWeatherResponse,
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> cl.CustomElement:
    return cl.CustomElement(
        name=WEATHER_ELEMENT_NAME,
        props={
            "kind": "current",
            "layout": "current_compact",
            "language": language,
            "show_actions": True,
            "city": weather.city,
            "condition": weather.condition,
            "temp_c": weather.temp_c,
            "feelslike_c": weather.feelslike_c,
            "humidity": weather.humidity,
            "wind_kph": weather.wind_kph,
            "pressure_mb": weather.pressure_mb,
            "last_updated": weather.last_updated,
        },
        display="inline",
    )


def create_weather_elements_from_result(
    messages: Sequence[BaseMessage | Any],
) -> list[cl.CustomElement]:
    elements: list[cl.CustomElement] = []

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.name != WEATHER_WIDGET_TOOL_NAME:
            continue

        payload = _parse_tool_payload(message.content)
        if not payload or payload.get("error"):
            continue

        widget = payload.get("widget")
        if not isinstance(widget, dict):
            continue

        element = _create_widget_element(widget)
        if element is not None:
            elements.append(element)

    return elements


def _parse_tool_payload(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None

    try:
        loaded = json.loads(content)
    except json.JSONDecodeError:
        return None

    return loaded if isinstance(loaded, dict) else None


def _create_widget_element(widget: dict[str, Any]) -> cl.CustomElement | None:
    if not widget.get("kind") or not widget.get("layout"):
        return None

    return cl.CustomElement(
        name=WEATHER_ELEMENT_NAME,
        props=widget,
        display="inline",
    )
