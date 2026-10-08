db-migrate:
    uv run --frozen alembic upgrade head

db-rollback:
    uv run --frozen alembic downgrade -1

db-create-migration name:
    uv run --frozen alembic revision --autogenerate -m "{{name}}"

db-status:
    uv run --frozen alembic current

db-history:
    uv run --frozen alembic history --verbose
