test:
    uv run --frozen pytest -m "not integration"

test-db-up:
    docker compose -f deploy/docker-compose.ci.yml up -d --wait

test-db-down:
    docker compose -f deploy/docker-compose.ci.yml down

test-db-migrate:
    DATABASE_URL="postgresql+asyncpg://app:test-only@localhost:${TEST_DB_PORT:-55432}/dmitrii_koshevarov_helpdesk_test" uv run --frozen alembic upgrade head

test-integration:
    DATABASE_URL="postgresql+asyncpg://app:test-only@localhost:${TEST_DB_PORT:-55432}/dmitrii_koshevarov_helpdesk_test" uv run --frozen pytest -m integration

test-all: test test-db-up test-db-migrate test-integration

ci-migrate:
    uv run --frozen alembic upgrade head

ci-test:
    uv run --frozen pytest --cov=backend --cov-report=term-missing

test-ui:
    npm ci
    npm test
