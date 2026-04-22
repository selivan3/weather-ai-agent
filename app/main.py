from __future__ import annotations

from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path

from chainlit.utils import mount_chainlit
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import APP_TITLE, get_settings
from app.logging_config import configure_logging
from app.observability import flush_langfuse
from app.schemas import (
    CurrentWeatherInput,
    CurrentWeatherResponse,
    ErrorResponse,
    ForecastInput,
    ForecastResponse,
    HealthResponse,
    HistoryInput,
    HistoryResponse,
)
from app.weather_client import WeatherProviderError
from app.weather_service import close_weather_service, get_weather_service

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    yield
    await close_weather_service()
    flush_langfuse(get_settings())


app = FastAPI(
    title=APP_TITLE,
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/public", StaticFiles(directory=".chainlit/public"), name="chainlit-public")


@app.exception_handler(WeatherProviderError)
async def weather_provider_exception_handler(
    request: Request,
    exc: WeatherProviderError,
) -> JSONResponse:
    del request
    payload = ErrorResponse(detail=exc.detail, code=exc.code)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.exception_handler(ValidationError)
async def validation_exception_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    del request
    detail = "; ".join(error["msg"] for error in exc.errors())
    payload = ErrorResponse(detail=detail, code="validation_error")
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/chat/", status_code=307)


@app.get(
    "/api/weather/current",
    response_model=CurrentWeatherResponse,
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.BAD_REQUEST: {"model": ErrorResponse},
        HTTPStatus.BAD_GATEWAY: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def api_current_weather(
    city: str | None = Query(default=None),
) -> CurrentWeatherResponse:
    payload = CurrentWeatherInput(city=city)
    return await get_weather_service().get_current_weather(payload.city)


@app.get(
    "/api/weather/forecast",
    response_model=ForecastResponse,
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.BAD_REQUEST: {"model": ErrorResponse},
        HTTPStatus.BAD_GATEWAY: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def api_forecast(
    city: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=14),
) -> ForecastResponse:
    payload = ForecastInput(city=city, days=days)
    return await get_weather_service().get_forecast(payload.city, payload.days)


@app.get(
    "/api/weather/history",
    response_model=HistoryResponse,
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.BAD_REQUEST: {"model": ErrorResponse},
        HTTPStatus.BAD_GATEWAY: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def api_history(
    city: str | None = Query(default=None),
    date: str = Query(...),
) -> HistoryResponse:
    payload = HistoryInput(city=city, date=date)
    return await get_weather_service().get_history(payload.city, payload.date)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


mount_chainlit(
    app=app,
    target=str(Path(__file__).with_name("chainlit_app.py").resolve()),
    path="/chat",
)
