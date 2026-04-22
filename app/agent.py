from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.messages.utils import convert_to_openai_messages
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict
from yandex_ai_studio_sdk import AIStudio

from app.config import (
    DEFAULT_CHAT_LANGUAGE,
    DEFAULT_CITY,
    DEFAULT_TIMEZONE,
    get_settings,
    get_language_label,
    get_prompt_language_name,
)
from app.tools import build_weather_tools
from app.weather_service import get_weather_service

WEATHER_SYSTEM_PROMPT_TEMPLATE = """Ты агент по погоде.

Контекст:
- Текущая локальная дата: {today_iso}
- Текущие локальные дата и время: {now_local}
- Часовой пояс для интерпретации относительных дат: {timezone}
- Выбранный город по умолчанию: {default_city}
- Выбранный язык ответа: {language_label} ({language_code})
- Ты помогаешь пользователю по вопросам текущей погоды, прогноза, исторической погоды и прикладных погодных советов.

Правила:
- Всегда отвечай на {prompt_language_name} языке.
- Всегда используй метрические единицы.
- Тебе передаётся история текущего диалога. Учитывай предыдущие сообщения пользователя и свои ответы.
- Слова "сегодня", "завтра", "вчера", "утром", "днём", "вечером" интерпретируй относительно даты {today_iso} и часового пояса {timezone}.
- Если пользователь не указал город, используй {default_city}.
- При вызове погодных инструментов всегда передавай город явным параметром `city`. Если пользователь не назвал другой город, передавай `city="{default_city}"`.
- Для любых вопросов о реальной погоде, прогнозе или истории сначала используй инструменты.
- Интерактивные погодные блоки показывай не всегда, а только когда они реально помогают ответу.
- Для визуальных блоков используй инструмент `show_weather_widget` только после соответствующего погодного инструмента.
- Для точечной даты или формулировок вроде "завтра", "послезавтра", "в пятницу" используй `show_weather_widget(source="forecast", layout="forecast_day", ...)`.
- Для запроса на неделю используй `show_weather_widget(source="forecast", layout="forecast_week")`.
- Для запроса на 8-14 дней используй `show_weather_widget(source="forecast", layout="forecast_dense")`.
- Для запроса на месяц или длинный горизонт используй `show_weather_widget(source="forecast", layout="forecast_month")`, но честно сообщай, если провайдер даёт максимум 14 дней.
- Для истории за конкретную дату используй `show_weather_widget(source="history", layout="history_compact")` только если визуальная карточка действительно полезна.
- Если пользователю нужен только короткий текстовый ответ или прикладной совет, не вызывай `show_weather_widget`.
- Не придумывай факты о погоде и не отвечай "с потолка".
- Если данных недостаточно или внешний API вернул ошибку, честно об этом скажи.
- Когда даёшь совет, опирайся на фактические погодные данные из инструментов.
- Отвечай кратко, полезно и по делу.
"""


class YandexAIStudioChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    sdk: AIStudio
    model_uri: str
    timeout: int = 60
    temperature: float = 0.1
    max_tokens: int = 1200

    @property
    def _llm_type(self) -> str:
        return "yandex-ai-studio-sdk"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_uri": self.model_uri,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def bind_tools(
        self,
        tools,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        prepared_tools = [self._to_sdk_tool(tool) for tool in tools]
        return self.bind(
            bound_tools=prepared_tools,
            bound_tool_choice=tool_choice,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager
        sdk_messages = self._convert_messages(messages)
        sdk_tools = kwargs.get("bound_tools", [])
        tool_choice = self._resolve_tool_choice(
            kwargs.get("bound_tool_choice"),
            sdk_tools,
        )

        model = self.sdk.chat.completions(self.model_uri).configure(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=sdk_tools or None,
            tool_choice=tool_choice,
        )
        result = model.run(sdk_messages, timeout=self.timeout)
        first_choice = result.choices[0]

        usage_metadata = None
        if result.usage is not None:
            usage_metadata = UsageMetadata(
                input_tokens=result.usage.prompt_tokens,
                output_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
            )

        tool_calls = []
        for tool_call in first_choice.tool_calls or []:
            if tool_call.function is None:
                continue
            tool_calls.append(
                {
                    "name": tool_call.function.name,
                    "args": tool_call.function.arguments,
                    "id": tool_call.id,
                    "type": "tool_call",
                }
            )

        message = AIMessage(
            content=first_choice.content or "",
            tool_calls=tool_calls,
            usage_metadata=usage_metadata,
            response_metadata={
                "model": result.model,
                "finish_reason": first_choice.finish_reason.value,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _to_sdk_tool(self, tool: dict[str, Any] | type | Any | BaseTool):
        openai_tool = convert_to_openai_tool(tool)
        function_spec = openai_tool["function"]
        return self.sdk.tools.function(
            function_spec["parameters"],
            name=function_spec["name"],
            description=function_spec.get("description"),
            strict=function_spec.get("strict"),
        )

    def _resolve_tool_choice(self, tool_choice: str | None, sdk_tools: list[Any]):
        if tool_choice is None:
            return None

        normalized = tool_choice.lower()
        if normalized in {"auto", "required", "none"}:
            return normalized
        if normalized == "any":
            return "required"

        for tool in sdk_tools:
            if getattr(tool, "name", None) == tool_choice:
                return tool
        return tool_choice

    @staticmethod
    def _convert_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
        openai_messages = convert_to_openai_messages(messages, text_format="string")
        sdk_messages: list[dict[str, Any]] = []

        for message in openai_messages:
            role = message["role"]
            if role == "tool":
                sdk_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message["tool_call_id"],
                        "content": message.get("content", ""),
                    }
                )
                continue

            if role == "assistant" and message.get("tool_calls"):
                sdk_messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": message["tool_calls"],
                    }
                )
                continue

            content = message.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(part for part in text_parts if part)

            sdk_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return sdk_messages


def extract_final_text(
    messages: list[Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            if isinstance(message.content, str) and message.content.strip():
                return message.content
            if isinstance(message.content, list):
                text_parts = [
                    block.get("text", "")
                    for block in message.content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                combined = "\n".join(part for part in text_parts if part).strip()
                if combined:
                    return combined

    fallback = _build_tool_fallback_text(messages, language=language)
    if fallback:
        return fallback

    if language == "en":
        return "I could not form a final answer. Please try rephrasing the request."
    return "Не удалось сформировать ответ. Попробуйте переформулировать запрос."


def _build_tool_fallback_text(
    messages: list[Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str | None:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue

        payload = _parse_tool_payload(message.content)
        if not payload:
            continue

        if message.name == "show_weather_widget":
            widget = payload.get("widget")
            if isinstance(widget, dict):
                return _build_widget_fallback_text(widget, language=language)

        if message.name == "get_current_weather":
            return _build_current_weather_fallback_text(payload, language=language)

        if message.name == "get_forecast":
            return _build_forecast_fallback_text(payload, language=language)

        if message.name == "get_history":
            return _build_history_fallback_text(payload, language=language)

    return None


def _parse_tool_payload(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _build_widget_fallback_text(
    widget: dict[str, Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str | None:
    layout = widget.get("layout")
    title = widget.get("title")
    city = widget.get("city")

    if layout == "forecast_day":
        forecast = widget.get("forecast")
        if isinstance(forecast, list) and forecast:
            day = forecast[0]
            if isinstance(day, dict):
                date = day.get("date")
                condition = day.get("condition")
                mintemp = day.get("mintemp_c")
                maxtemp = day.get("maxtemp_c")
                rain = day.get("daily_chance_of_rain")
                wind = day.get("maxwind_kph")
                if language == "en":
                    return (
                        f"{title or 'Forecast'}: {condition}, {mintemp} to {maxtemp} °C, "
                        f"rain chance {rain}%, wind up to {wind} km/h."
                    )
                return (
                    f"{title or 'Прогноз'}: {condition}, от {mintemp} до {maxtemp} °C, "
                    f"вероятность дождя {rain}%, ветер до {wind} км/ч."
                )

    if layout in {"forecast_week", "forecast_dense", "forecast_month"}:
        days = widget.get("days")
        if language == "en":
            return f"Below is a compact forecast for {city} for {days} day(s)."
        return f"Ниже показан компактный прогноз для {city} на {days} дн."

    if layout == "current_compact":
        condition = widget.get("condition")
        temp_c = widget.get("temp_c")
        feelslike_c = widget.get("feelslike_c")
        if language == "en":
            return (
                f"Current weather in {city}: {condition}, {temp_c} °C, "
                f"feels like {feelslike_c} °C."
            )
        return (
            f"Сейчас в {city}: {condition}, {temp_c} °C, "
            f"ощущается как {feelslike_c} °C."
        )

    if layout == "history_compact":
        date = widget.get("date")
        condition = widget.get("condition")
        avgtemp = widget.get("avgtemp_c")
        if language == "en":
            return f"Historical weather in {city} for {date}: {condition}, average {avgtemp} °C."
        return f"Историческая погода в {city} за {date}: {condition}, средняя температура {avgtemp} °C."

    return None


def _build_current_weather_fallback_text(
    payload: dict[str, Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str | None:
    city = payload.get("city")
    condition = payload.get("condition")
    temp_c = payload.get("temp_c")
    feelslike_c = payload.get("feelslike_c")
    if city is None or condition is None or temp_c is None or feelslike_c is None:
        return None

    if language == "en":
        return (
            f"Current weather in {city}: {condition}, {temp_c} °C, "
            f"feels like {feelslike_c} °C."
        )
    return (
        f"Сейчас в {city}: {condition}, {temp_c} °C, "
        f"ощущается как {feelslike_c} °C."
    )


def _build_forecast_fallback_text(
    payload: dict[str, Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str | None:
    city = payload.get("city")
    forecast = payload.get("forecast")
    days = payload.get("days")
    if city is None or not isinstance(forecast, list) or not forecast:
        return None

    first_day = forecast[0]
    if not isinstance(first_day, dict):
        return None

    condition = first_day.get("condition")
    mintemp = first_day.get("mintemp_c")
    maxtemp = first_day.get("maxtemp_c")
    date = first_day.get("date")
    if language == "en":
        if days == 1:
            return f"Forecast for {city} on {date}: {condition}, {mintemp} to {maxtemp} °C."
        return f"Below is the forecast for {city} for {days} day(s)."

    if days == 1:
        return f"Прогноз для {city} на {date}: {condition}, от {mintemp} до {maxtemp} °C."
    return f"Ниже показан прогноз для {city} на {days} дн."


def _build_history_fallback_text(
    payload: dict[str, Any],
    *,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str | None:
    city = payload.get("city")
    date = payload.get("date")
    condition = payload.get("condition")
    avgtemp = payload.get("avgtemp_c")
    if city is None or date is None or condition is None or avgtemp is None:
        return None

    if language == "en":
        return f"Historical weather in {city} for {date}: {condition}, average {avgtemp} °C."
    return f"Историческая погода в {city} за {date}: {condition}, средняя температура {avgtemp} °C."


def build_weather_system_prompt(
    *,
    default_city: str = DEFAULT_CITY,
    timezone: str = DEFAULT_TIMEZONE,
    language: str = DEFAULT_CHAT_LANGUAGE,
) -> str:
    now = datetime.now(ZoneInfo(timezone))
    return WEATHER_SYSTEM_PROMPT_TEMPLATE.format(
        today_iso=now.date().isoformat(),
        now_local=now.strftime("%Y-%m-%d %H:%M"),
        timezone=timezone,
        default_city=default_city,
        language_label=get_language_label(language),
        language_code=language,
        prompt_language_name=get_prompt_language_name(language),
    )


@lru_cache(maxsize=1)
def get_yandex_sdk() -> AIStudio:
    settings = get_settings()
    if not settings.yandex_enabled:
        raise RuntimeError(
            "Yandex AI Studio не настроен. Заполните YANDEX_API_KEY, "
            "YANDEX_FOLDER_ID и YANDEX_MODEL_URI."
        )
    return AIStudio(
        folder_id=settings.yandex_folder_id,
        auth=settings.yandex_api_key,
    )


@lru_cache(maxsize=1)
def get_chat_model() -> YandexAIStudioChatModel:
    settings = get_settings()
    return YandexAIStudioChatModel(
        sdk=get_yandex_sdk(),
        model_uri=settings.yandex_model_uri or "",
        timeout=settings.model_request_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )


def get_weather_agent(
    *,
    default_city: str = DEFAULT_CITY,
    timezone: str = DEFAULT_TIMEZONE,
    language: str = DEFAULT_CHAT_LANGUAGE,
):
    service = get_weather_service()
    return create_agent(
        model=get_chat_model(),
        tools=build_weather_tools(
            service,
            default_city=default_city,
            language=language,
        ),
        system_prompt=build_weather_system_prompt(
            default_city=default_city,
            timezone=timezone,
            language=language,
        ),
        name="weather-agent",
    )
