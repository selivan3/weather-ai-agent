from __future__ import annotations

import os
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.config import Settings


def build_trace_tags(
    settings: Settings,
    *,
    route: str,
    city: str | None = None,
    language: str | None = None,
    timezone: str | None = None,
) -> list[str]:
    tags = [
        f"app={settings.app_name}",
        f"env={settings.app_env}",
        "provider=weatherapi",
        f"model={settings.model_label}",
        f"route={route}",
    ]
    if city:
        tags.append(f"city={city}")
    if language:
        tags.append(f"language={language}")
    if timezone:
        tags.append(f"timezone={timezone}")
    return tags


def build_langfuse_metadata(
    settings: Settings,
    *,
    route: str,
    city: str | None = None,
    session_id: str | None = None,
    language: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "app": settings.app_name,
        "env": settings.app_env,
        "provider": "weatherapi",
        "model": settings.model_label,
        "route": route,
    }
    if city:
        metadata["city"] = city
    if language:
        metadata["language"] = language
    if timezone:
        metadata["timezone"] = timezone
    if session_id:
        metadata["langfuse_session_id"] = session_id
    metadata["langfuse_tags"] = build_trace_tags(
        settings,
        route=route,
        city=city,
        language=language,
        timezone=timezone,
    )
    return metadata


def configure_langfuse_environment(settings: Settings) -> None:
    if settings.langfuse_public_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    if settings.langfuse_secret_key:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    if settings.langfuse_host:
        os.environ["LANGFUSE_HOST"] = settings.langfuse_host


@lru_cache(maxsize=1)
def _build_langfuse_client(
    public_key: str,
    secret_key: str,
    host: str,
    environment: str,
) -> Langfuse:
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        environment=environment,
    )


def get_langfuse_client(settings: Settings) -> Langfuse | None:
    if not settings.langfuse_enabled:
        return None

    configure_langfuse_environment(settings)
    return _build_langfuse_client(
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_host,
        settings.app_env,
    )


def get_langfuse_handler(settings: Settings) -> CallbackHandler | None:
    client = get_langfuse_client(settings)
    if client is None:
        return None

    del client
    return CallbackHandler(public_key=settings.langfuse_public_key)


def langfuse_trace_context(
    settings: Settings,
    *,
    route: str,
    city: str | None = None,
    session_id: str | None = None,
    language: str | None = None,
    timezone: str | None = None,
):
    client = get_langfuse_client(settings)
    if client is None:
        return nullcontext()

    del client
    return propagate_attributes(
        session_id=session_id,
        tags=build_trace_tags(
            settings,
            route=route,
            city=city,
            language=language,
            timezone=timezone,
        ),
        metadata={
            "app": settings.app_name,
            "env": settings.app_env,
            "provider": "weatherapi",
            "model": settings.model_label,
            "route": route,
            "city": city,
            "language": language,
            "timezone": timezone,
        },
    )


def flush_langfuse(settings: Settings) -> None:
    client = get_langfuse_client(settings)
    if client is not None:
        client.flush()
