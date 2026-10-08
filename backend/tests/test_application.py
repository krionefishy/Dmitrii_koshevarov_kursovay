from httpx import AsyncClient


async def test_litestar_starts_and_disables_http_caching(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


async def test_ui_assets_and_openapi_are_served(client: AsyncClient) -> None:
    for path, kind in [("/", "text/html"), ("/assets/app.js", "text/javascript"), ("/assets/styles.css", "text/css")]:
        response = await client.get(path)
        assert response.status_code == 200
        assert kind in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-store"
    schema = (await client.get("/api/docs/openapi.json")).json()
    assert "/api/v1/tickets/{ticket_id}" in schema["paths"]
