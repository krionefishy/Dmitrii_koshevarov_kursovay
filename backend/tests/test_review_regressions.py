import pytest

from backend.shared.schemas import MAX_ID

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("edit_self", [True, False])
async def test_name_edit_with_unchanged_permissions_keeps_token(client, builder, bearer_headers, edit_self):
    admin = await builder.build_user(role="admin")
    target = admin if edit_self else await builder.build_user()
    headers = bearer_headers(target)
    response = await client.patch(
        f"/api/v1/admin/users/{target.login}",
        headers=bearer_headers(admin),
        json={"display_name": "Новое имя", "role": target.role, "is_active": target.is_active},
    )
    assert response.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["display_name"] == "Новое имя"


@pytest.mark.parametrize("change", [{"role": "support"}, {"is_active": False}, {"password": "New-password-123"}])
async def test_actual_security_changes_revoke_token(client, builder, bearer_headers, change):
    admin = await builder.build_user(role="admin")
    target = await builder.build_user()
    headers = bearer_headers(target)
    changed = await client.patch(f"/api/v1/admin/users/{target.login}", headers=bearer_headers(admin), json=change)
    assert changed.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


@pytest.mark.parametrize("role", ["customer", "support"])
async def test_inactive_category_visible_in_history_but_not_creation(client, builder, bearer_headers, role):
    customer = await builder.build_user()
    actor = customer if role == "customer" else await builder.build_user(role=role)
    active = await builder.build_category(name="Активная")
    inactive = await builder.build_category(name="Архивная", is_active=False)
    own = await builder.build_ticket(author_login=customer.login, category_id=inactive.id)
    stranger = await builder.build_user()
    foreign = await builder.build_ticket(author_login=stranger.login, category_id=inactive.id)
    headers = bearer_headers(actor)
    choices = (await client.get("/api/v1/categories", headers=headers)).json()
    assert [c["id"] for c in choices["items"]] == [active.id]
    history = await client.get("/api/v1/categories", params={"include_inactive": True}, headers=headers)
    assert history.status_code == 200
    assert {c["id"] for c in history.json()["items"]} == {active.id, inactive.id}
    queue = await client.get("/api/v1/tickets", params={"category_id": inactive.id}, headers=headers)
    assert {t["id"] for t in queue.json()["items"]} == ({own.id} if role == "customer" else {own.id, foreign.id})
    denied = await client.post(
        "/api/v1/tickets",
        headers=bearer_headers(customer),
        json={"category_id": inactive.id, "title": "Новая заявка", "body": "Описание"},
    )
    assert denied.status_code == 404
    page = (
        await client.get("/api/v1/categories", params={"include_inactive": True, "limit": 1}, headers=headers)
    ).json()
    bad_cursor = await client.get(
        "/api/v1/categories", params={"limit": 1, "cursor": page["next_cursor"]}, headers=headers
    )
    assert bad_cursor.status_code == 400


async def test_newest_comment_page_contains_post_and_preserves_history(client, builder, bearer_headers):
    customer = await builder.build_user()
    stranger = await builder.build_user()
    ticket = await builder.build_ticket(author_login=customer.login)
    comments = [
        await builder.build_comment(ticket_id=ticket.id, author_login=customer.login, is_staff_reply=False)
        for _ in range(41)
    ]
    path = f"/api/v1/tickets/{ticket.id}/comments"
    headers = bearer_headers(customer)
    params = {"limit": 20, "newest_first": True}
    old = (await client.get(path, params=params, headers=headers)).json()
    posted = await client.post(path, json={"body": "Новый ответ"}, headers=headers)
    assert posted.status_code == 201
    fresh = (await client.get(path, params=params, headers=headers)).json()
    assert fresh["items"][0]["id"] == posted.json()["id"]

    seen = [c["id"] for c in old["items"]]
    cursor = old["next_cursor"]
    while cursor:
        page = (await client.get(path, params={**params, "cursor": cursor}, headers=headers)).json()
        seen.extend(c["id"] for c in page["items"])
        cursor = page["next_cursor"]
    assert seen == [c.id for c in reversed(comments)]
    assert (
        await client.get(path, params={"limit": 20, "cursor": old["next_cursor"]}, headers=headers)
    ).status_code == 400
    assert (await client.get(path, params=params, headers=bearer_headers(stranger))).status_code == 404


@pytest.mark.parametrize("value", [-1, 0, MAX_ID, MAX_ID + 1])
@pytest.mark.parametrize(
    ("role", "method", "path", "payload"),
    [
        ("support", "GET", "/tickets/{id}", None),
        ("support", "GET", "/tickets/{id}/comments", None),
        ("support", "POST", "/tickets/{id}/comments", {"body": "Ответ"}),
        ("support", "PATCH", "/tickets/{id}/status", {"status": "in_progress"}),
        ("admin", "PATCH", "/admin/categories/{id}", {"name": "Категория"}),
        ("admin", "PUT", "/admin/norms/{id}", {"response_seconds": 60}),
        ("customer", "POST", "/tickets", {"title": "Тема", "body": "Описание"}),
        ("support", "GET", "/tickets?category_id={id}", None),
    ],
)
async def test_all_numeric_inputs_obey_bigint_range(
    client, builder, bearer_headers, value, role, method, path, payload
):
    actor = await builder.build_user(role=role)
    if path == "/tickets":
        payload = {**payload, "category_id": value}
    response = await client.request(
        method, "/api/v1" + path.format(id=value), headers=bearer_headers(actor), json=payload
    )
    expected = (200 if "?" in path else 404) if value == MAX_ID else 400
    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    ("role", "method", "path", "payload"),
    [
        ("customer", "POST", "/tickets", {"title": "x\x00y", "body": "Описание"}),
        ("customer", "POST", "/tickets", {"title": "Тема", "body": "x\x00y"}),
        ("customer", "POST", "/tickets/{ticket}/comments", {"body": "x\x00y"}),
        ("admin", "POST", "/admin/categories", {"name": "x\x00y", "response_seconds": 60}),
        ("admin", "POST", "/admin/categories", {"name": "Имя", "description": "x\x00y", "response_seconds": 60}),
        ("admin", "PATCH", "/admin/categories/{category}", {"name": "x\x00y"}),
        ("admin", "PATCH", "/admin/categories/{category}", {"description": "x\x00y"}),
        (
            "admin",
            "POST",
            "/admin/users",
            {"login": "new_user", "display_name": "x\x00y", "role": "customer", "password": "Valid-password-123"},
        ),
        ("admin", "PATCH", "/admin/users/{login}", {"display_name": "x\x00y"}),
        ("admin", "PATCH", "/admin/users/bad%00login", {"display_name": "Имя"}),
    ],
)
async def test_null_character_is_client_error(client, builder, bearer_headers, role, method, path, payload):
    actor = await builder.build_user(role=role)
    category = await builder.build_category()
    ticket = await builder.build_ticket(author_login=actor.login, category_id=category.id)
    if path == "/tickets":
        payload = {**payload, "category_id": category.id}
    response = await client.request(
        method,
        "/api/v1" + path.format(ticket=ticket.id, category=category.id, login=actor.login),
        headers=bearer_headers(actor),
        json=payload,
    )
    assert response.status_code == 400, response.text
    assert (await client.get("/api/v1/auth/me", headers=bearer_headers(actor))).status_code == 200


async def test_partial_category_edit_preserves_concurrent_disable(client, builder, bearer_headers):
    actor = await builder.build_user(role="admin")
    category = await builder.build_category()
    path = f"/api/v1/admin/categories/{category.id}"
    headers = bearer_headers(actor)
    assert (await client.patch(path, headers=headers, json={"is_active": False})).status_code == 200
    response = await client.patch(path, headers=headers, json={"description": "Новое описание"})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
