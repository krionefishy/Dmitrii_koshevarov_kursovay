set dotenv-load := true

measurements_dir := env_var_or_default("MEASUREMENTS_DIR", "../helpdesk-measurements")

import 'just/api.just'
import 'just/db.just'
import 'just/tests.just'

default:
    @just --list

install:
    uv sync --frozen

infra-up:
    docker compose --env-file .env -f deploy/docker-compose.local.yml up -d --wait

infra-down:
    docker compose --env-file .env -f deploy/docker-compose.local.yml down

infra-status:
    docker compose --env-file .env -f deploy/docker-compose.local.yml ps

dev: infra-up db-migrate api

ci: lint typecheck test-all test-ui

docker-build image_tag="local":
    docker build -f deploy/Dockerfile -t coursework-helpdesk:{{image_tag}} .

deploy-up:
    docker compose --env-file .env -f deploy/compose.yaml up -d --build --wait

deploy-down:
    docker compose --env-file .env -f deploy/compose.yaml down

seed profile="small":
    uv run --frozen python -m backend.cli.seed --profile {{profile}} --reset --output "{{measurements_dir}}/seed-{{profile}}.json"

benchmark profile="small":
    uv run --frozen python -m backend.benchmarks.runner --profile {{profile}} --base-url "http://127.0.0.1:${APP_PORT:-8000}" --output "{{measurements_dir}}/{{profile}}.json"

serve:
    uv run --frozen uvicorn backend.app.main:app --host 127.0.0.1 --port "${APP_PORT:-8000}" --workers 1 --no-access-log

benchmark-up:
    docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.benchmark.yaml up -d --build --wait

benchmark-seed profile="small":
    mkdir -p "{{measurements_dir}}"
    docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.benchmark.yaml exec -T backend python -m backend.cli.seed --profile {{profile}} --reset > "{{measurements_dir}}/seed-{{profile}}.json"

benchmark-docker profile="small":
    DATABASE_URL="" DB_HOST=127.0.0.1 DB_PORT="${BENCH_DB_PORT:-55435}" uv run --frozen python -m backend.benchmarks.runner --profile {{profile}} --base-url "http://127.0.0.1:${APP_PORT:-8000}" --output "{{measurements_dir}}/{{profile}}.json"

benchmark-down:
    docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.benchmark.yaml down

load-step scenario="mixed" rate="1" output_dir="../helpdesk-load-results":
    uv run --frozen python load/run_step.py {{scenario}} {{rate}} --output-dir "{{output_dir}}"

serve-benchmark:
    uv run --frozen uvicorn backend.benchmarks.main:app --host 127.0.0.1 --port "${APP_PORT:-8000}" --workers 1 --no-access-log
