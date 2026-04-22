#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import fastapi, chainlit, langchain, langfuse, httpx, jinja2, pydantic, pydantic_settings, cachetools, dotenv, yandex_ai_studio_sdk, gunicorn" >/dev/null 2>&1; then
  python -m pip install -r requirements.txt
fi

if [[ ! -f ".env" ]]; then
  echo "Внимание: файл .env не найден. Приложение запустится, но интеграции погоды и LLM могут быть недоступны."
fi

PORT_VALUE="${PORT:-8000}"
if [[ -z "${PORT:-}" ]]; then
  while lsof -nP -iTCP:"${PORT_VALUE}" -sTCP:LISTEN >/dev/null 2>&1; do
    PORT_VALUE="$((PORT_VALUE + 1))"
  done
fi

echo "Запускаю приложение на http://127.0.0.1:${PORT_VALUE}"
exec python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT_VALUE}"
