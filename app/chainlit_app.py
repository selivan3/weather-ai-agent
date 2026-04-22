from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import chainlit as cl
import httpx
from chainlit.input_widget import Select, TextInput

from app.agent import extract_final_text, get_weather_agent
from app.chat_elements import (
    create_current_weather_element,
    create_weather_elements_from_result,
)
from app.config import (
    SUPPORTED_CHAT_LANGUAGES,
    SUPPORTED_CHAT_TIMEZONES,
    get_language_label,
    get_settings,
)
from app.observability import (
    build_langfuse_metadata,
    get_langfuse_handler,
    langfuse_trace_context,
)
from app.schemas import ChatPreferences, CurrentWeatherResponse
from app.weather_client import WeatherProviderError
from app.weather_service import get_weather_service

CHAT_PREFERENCES_KEY = "chat_preferences"
logger = logging.getLogger(__name__)

CHAT_COPY: dict[str, dict[str, str]] = {
    "ru": {
        "intro": "**Привет! Я агент по погоде.**",
        "default_city": "Город по умолчанию: **{city}**.",
        "timezone": "Часовой пояс: **{timezone}**.",
        "language": "Язык ответов: **{language}**.",
        "weather_loaded": "Ниже показана текущая погода в городе {city}.",
        "weather_error": "Текущую погоду сейчас не удалось загрузить.",
        "reason": "Причина: {reason}",
        "capabilities": (
            "Могу рассказать о текущей погоде, прогнозе, истории за дату "
            "и дать прикладной совет."
        ),
        "stack": "Текущий стек: {stack}.",
        "project": "Проект сделал [{author}]({url})",
        "provider": "Данные о погоде: WeatherAPI.",
        "settings_saved": "Настройки обновлены.",
        "settings_summary": (
            "Город: **{city}** · Часовой пояс: **{timezone}** · Язык: **{language}**."
        ),
        "weather_for_city": "Ниже показана текущая погода для **{city}**.",
        "weather_refresh_error": "Погоду для выбранного города сейчас не удалось загрузить.",
        "llm_missing": (
            "LLM пока не настроен. Заполните `YANDEX_API_KEY`, "
            "`YANDEX_FOLDER_ID` и `YANDEX_MODEL_URI` в `.env`."
        ),
        "agent_error": "Не получилось обработать запрос к погодному агенту. {detail}",
        "settings_invalid": (
            "Не получилось применить настройки. Проверьте город, часовой пояс и язык."
        ),
    },
    "en": {
        "intro": "**Hello! I am a weather agent.**",
        "default_city": "Default city: **{city}**.",
        "timezone": "Time zone: **{timezone}**.",
        "language": "Response language: **{language}**.",
        "weather_loaded": "Current weather for {city} is shown below.",
        "weather_error": "I could not load the current weather right now.",
        "reason": "Reason: {reason}",
        "capabilities": (
            "I can explain the current weather, forecast, history for a date, "
            "and give practical advice."
        ),
        "stack": "Current stack: {stack}.",
        "project": "Project by [{author}]({url})",
        "provider": "Weather data: WeatherAPI.",
        "settings_saved": "Settings updated.",
        "settings_summary": (
            "City: **{city}** · Time zone: **{timezone}** · Language: **{language}**."
        ),
        "weather_for_city": "Current weather for **{city}** is shown below.",
        "weather_refresh_error": "I could not load weather for the selected city right now.",
        "llm_missing": (
            "The LLM is not configured yet. Fill in `YANDEX_API_KEY`, "
            "`YANDEX_FOLDER_ID`, and `YANDEX_MODEL_URI` in `.env`."
        ),
        "agent_error": "I could not process the weather request. {detail}",
        "settings_invalid": (
            "Could not apply the settings. Please check the city, time zone, and language."
        ),
    },
}


def get_copy(language: str) -> dict[str, str]:
    return CHAT_COPY["en"] if language == "en" else CHAT_COPY["ru"]


def _extract_exception_message(exc: BaseException | None) -> str | None:
    if exc is None:
        return None

    seen: set[int] = set()
    queue: list[BaseException] = [exc]

    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)

        message = str(current).strip()
        if message:
            return message

        if isinstance(current, BaseExceptionGroup):
            queue.extend(
                nested for nested in current.exceptions if isinstance(nested, BaseException)
            )

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            queue.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            queue.append(context)

    return None


def describe_agent_error(exc: BaseException, *, language: str) -> str:
    fallback_message = _extract_exception_message(exc)

    if isinstance(exc, WeatherProviderError):
        return exc.detail

    if isinstance(exc, httpx.ConnectError):
        if language == "en":
            return (
                "Could not connect to the external AI service. "
                "Please check internet access, DNS, and Yandex AI Studio settings."
            )
        return (
            "Не удалось подключиться к внешнему AI-сервису. "
            "Проверьте интернет, DNS и настройки Yandex AI Studio."
        )

    if isinstance(exc, httpx.TimeoutException):
        if language == "en":
            return "The external AI service did not respond in time. Please try again."
        return "Внешний AI-сервис не ответил вовремя. Попробуйте ещё раз."

    if fallback_message:
        return fallback_message

    if language == "en":
        return f"Unexpected {type(exc).__name__} without a text description."
    return f"Произошла ошибка {type(exc).__name__} без текстового описания."


def get_default_chat_preferences() -> ChatPreferences:
    settings = get_settings()
    return ChatPreferences(city=settings.default_city)


def set_chat_preferences(preferences: ChatPreferences) -> None:
    cl.user_session.set(CHAT_PREFERENCES_KEY, preferences.model_dump())


def get_chat_preferences() -> ChatPreferences:
    stored = cl.user_session.get(CHAT_PREFERENCES_KEY)
    if isinstance(stored, dict):
        try:
            return ChatPreferences.model_validate(stored)
        except Exception:
            pass

    preferences = get_default_chat_preferences()
    set_chat_preferences(preferences)
    return preferences


def merge_chat_preferences(
    raw_settings: dict[str, Any] | None,
    fallback: ChatPreferences,
) -> ChatPreferences:
    payload = raw_settings or {}
    return ChatPreferences.model_validate(
        {
            "city": payload.get("city", fallback.city),
            "timezone": payload.get("timezone", fallback.timezone),
            "language": payload.get("language", fallback.language),
        }
    )


def build_chat_settings(preferences: ChatPreferences) -> list[TextInput | Select]:
    return [
        TextInput(
            id="city",
            label="Город",
            initial=preferences.city,
            placeholder="Например, Krasnodar",
            description="Город по умолчанию для прогноза и советов агента.",
        ),
        Select(
            id="timezone",
            label="Часовой пояс",
            initial_value=preferences.timezone,
            items=SUPPORTED_CHAT_TIMEZONES,
            description="Используется для интерпретации слов вроде «сегодня» и «завтра».",
        ),
        Select(
            id="language",
            label="Язык ответов",
            initial_value=preferences.language,
            items=SUPPORTED_CHAT_LANGUAGES,
            description="Влияет на язык ответов агента и погодных карточек.",
        ),
    ]


async def send_chat_settings(preferences: ChatPreferences) -> dict[str, Any]:
    return await cl.ChatSettings(build_chat_settings(preferences)).send()


def build_agent_messages(current_message: cl.Message) -> list[dict[str, str]]:
    """Build the full chat history for the agent from Chainlit session context."""

    normalized_history: list[dict[str, str]] = []
    for item in cl.chat_context.to_openai():
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant", "system"}:
            continue
        if not isinstance(content, str):
            continue

        trimmed_content = content.strip()
        if not trimmed_content:
            continue

        normalized_history.append(
            {
                "role": role,
                "content": trimmed_content,
            }
        )

    current_content = (
        current_message.content.strip()
        if isinstance(current_message.content, str)
        else ""
    )
    if current_content:
        current_payload = {"role": "user", "content": current_content}
        if not normalized_history or normalized_history[-1] != current_payload:
            normalized_history.append(current_payload)

    return normalized_history


def build_start_message(
    *,
    preferences: ChatPreferences,
    stack_label: str,
    author_name: str,
    author_url: str,
    weather: CurrentWeatherResponse | None = None,
    weather_error: str | None = None,
) -> str:
    copy = get_copy(preferences.language)
    parts = [copy["intro"]]

    if weather is not None:
        parts.extend(
            [
                "",
                copy["weather_loaded"].format(city=weather.city),
            ]
        )
    elif weather_error:
        parts.extend(
            [
                "",
                copy["weather_error"],
                copy["reason"].format(reason=weather_error),
            ]
        )

    parts.extend(
        [
            "",
            copy["capabilities"],
            copy["project"].format(author=author_name, url=author_url),
            copy["provider"],
        ]
    )
    return "\n".join(parts)


def build_settings_update_message(
    *,
    preferences: ChatPreferences,
    weather: CurrentWeatherResponse | None = None,
    weather_error: str | None = None,
) -> str:
    copy = get_copy(preferences.language)
    parts = [
        copy["settings_saved"],
        copy["settings_summary"].format(
            city=preferences.city,
            timezone=preferences.timezone,
            language=get_language_label(preferences.language),
        ),
    ]

    if weather is not None:
        parts.extend(["", copy["weather_for_city"].format(city=weather.city)])
    elif weather_error:
        parts.extend(
            [
                "",
                copy["weather_refresh_error"],
                copy["reason"].format(reason=weather_error),
            ]
        )

    return "\n".join(parts)


@cl.on_chat_start
async def on_chat_start() -> None:
    settings = get_settings()
    session_id = str(uuid4())
    cl.user_session.set("session_id", session_id)

    preferences = get_default_chat_preferences()
    applied_settings = await send_chat_settings(preferences)
    preferences = merge_chat_preferences(applied_settings, preferences)
    set_chat_preferences(preferences)

    weather = None
    weather_error = None

    try:
        weather = await get_weather_service().get_current_weather(
            preferences.city,
            language=preferences.language,
        )
    except WeatherProviderError as exc:
        weather_error = exc.detail

    elements = None
    if weather is not None:
        elements = [
            create_current_weather_element(weather, language=preferences.language)
        ]

    await cl.Message(
        content=build_start_message(
            preferences=preferences,
            stack_label=settings.stack_label,
            author_name=settings.author_name,
            author_url=settings.author_url,
            weather=weather,
            weather_error=weather_error,
        ),
        elements=elements,
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread: dict[str, Any]) -> None:
    thread_id = thread.get("id")
    session_id = (
        cl.user_session.get("session_id")
        or (str(thread_id) if thread_id else None)
        or str(uuid4())
    )
    cl.user_session.set("session_id", session_id)
    await send_chat_settings(get_chat_preferences())


@cl.on_settings_update
async def on_settings_update(updated_settings: dict[str, Any]) -> None:
    current_preferences = get_chat_preferences()

    try:
        preferences = merge_chat_preferences(updated_settings, current_preferences)
    except Exception:
        copy = get_copy(current_preferences.language)
        await cl.Message(content=copy["settings_invalid"]).send()
        return

    set_chat_preferences(preferences)

    weather = None
    weather_error = None

    try:
        weather = await get_weather_service().get_current_weather(
            preferences.city,
            language=preferences.language,
        )
    except WeatherProviderError as exc:
        weather_error = exc.detail

    elements = None
    if weather is not None:
        elements = [
            create_current_weather_element(weather, language=preferences.language)
        ]

    await cl.Message(
        content=build_settings_update_message(
            preferences=preferences,
            weather=weather,
            weather_error=weather_error,
        ),
        elements=elements,
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    settings = get_settings()
    preferences = get_chat_preferences()
    copy = get_copy(preferences.language)

    if not settings.yandex_enabled:
        await cl.Message(content=copy["llm_missing"]).send()
        return

    session_id = cl.user_session.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        cl.user_session.set("session_id", session_id)

    handler = get_langfuse_handler(settings)
    callbacks = [handler] if handler else []
    agent_messages = build_agent_messages(message)

    try:
        agent = get_weather_agent(
            default_city=preferences.city,
            timezone=preferences.timezone,
            language=preferences.language,
        )
        with langfuse_trace_context(
            settings,
            route="/chat",
            city=preferences.city,
            session_id=session_id,
            language=preferences.language,
            timezone=preferences.timezone,
        ):
            result = await agent.ainvoke(
                {"messages": agent_messages},
                config={
                    "callbacks": callbacks,
                    "metadata": build_langfuse_metadata(
                        settings,
                        route="/chat",
                        city=preferences.city,
                        session_id=session_id,
                        language=preferences.language,
                        timezone=preferences.timezone,
                    ),
                    "configurable": {"thread_id": session_id},
                },
            )
    except Exception as exc:
        detail = describe_agent_error(exc, language=preferences.language)
        logger.exception(
            "Weather agent request failed",
            extra={
                "city": preferences.city,
                "language": preferences.language,
                "timezone": preferences.timezone,
                "session_id": session_id,
            },
        )
        await cl.Message(content=copy["agent_error"].format(detail=detail)).send()
        return

    answer = extract_final_text(result["messages"], language=preferences.language)
    weather_elements = create_weather_elements_from_result(result["messages"])
    elements = weather_elements or None
    await cl.Message(content=answer, elements=elements).send()
