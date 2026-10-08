api:
    uv run --frozen uvicorn backend.app.main:app --reload --host 127.0.0.1 --port "${APP_PORT:-8000}"

lint:
    uv run --frozen ruff check .
    uv run --frozen ruff format --check .

fmt:
    uv run --frozen ruff check . --fix
    uv run --frozen ruff format .

typecheck:
    uv run --frozen mypy backend/
