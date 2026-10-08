import pytest


async def test_regular_server_has_no_measurement_headers(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert not {"x-server-ms", "x-db-ms", "x-sql-count", "server-timing"}.intersection(response.headers)


async def test_measurement_server_adds_timing_headers(benchmark_client):
    response = await benchmark_client.get("/api/v1/health")
    assert response.status_code == 200
    assert float(response.headers["x-server-ms"]) >= 0
    assert float(response.headers["x-db-ms"]) == 0
    assert int(response.headers["x-sql-count"]) == 0


@pytest.mark.integration
async def test_measurement_server_counts_queries_per_request(benchmark_client):
    first = await benchmark_client.get("/api/v1/ready")
    second = await benchmark_client.get("/api/v1/ready")
    health = await benchmark_client.get("/api/v1/health")
    assert first.status_code == second.status_code == health.status_code == 200
    assert int(first.headers["x-sql-count"]) == 1
    assert int(second.headers["x-sql-count"]) == 1
    assert float(first.headers["x-db-ms"]) > 0
    assert int(health.headers["x-sql-count"]) == 0


@pytest.mark.integration
async def test_regular_database_has_no_measurement_listeners(database):
    assert not database.engine.sync_engine.dispatch.before_cursor_execute
    assert not database.engine.sync_engine.dispatch.after_cursor_execute
