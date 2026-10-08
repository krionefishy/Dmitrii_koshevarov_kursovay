from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.tickets.rules import TicketRules
from backend.shared.utils import AppError
from backend.tests.builder import Builder


@pytest.mark.parametrize(
    ("reply_seconds", "wait_seconds", "breached"),
    [(3600, 7200, False), (3601, 7200, True), (None, 3600, False), (None, 3601, True), (10, 7200, False)],
)
def test_sla_boundary(frozen_datetime, reply_seconds, wait_seconds, breached):
    reply = frozen_datetime + timedelta(seconds=reply_seconds) if reply_seconds is not None else None
    result = TicketRules.reaction(frozen_datetime, reply, 3600, frozen_datetime + timedelta(seconds=wait_seconds))
    assert result.breached is breached


@pytest.mark.parametrize(("closed_seconds", "breached"), [(3599, False), (3600, False), (3601, True)])
def test_unanswered_closed_ticket_stops_waiting(frozen_datetime, closed_seconds, breached):
    closed_at = frozen_datetime + timedelta(seconds=closed_seconds)
    result = TicketRules.reaction(
        frozen_datetime, None, 3600, frozen_datetime + timedelta(days=30), closed_at=closed_at
    )
    assert result.first_staff_reply_at is None
    assert result.elapsed_seconds == closed_seconds
    assert result.breached is breached


def test_closed_ticket_keeps_actual_first_response_time(frozen_datetime):
    first_reply = frozen_datetime + timedelta(minutes=30)
    result = TicketRules.reaction(
        frozen_datetime,
        first_reply,
        3600,
        frozen_datetime + timedelta(days=30),
        closed_at=frozen_datetime + timedelta(hours=4),
    )
    assert result.first_staff_reply_at == first_reply
    assert result.elapsed_seconds == 1800
    assert result.breached is False


@pytest.mark.parametrize(("before", "after"), [("new", "closed"), ("in_progress", "new"), ("closed", "in_progress")])
def test_invalid_transitions(before, after):
    with pytest.raises(AppError) as error:
        TicketRules.validate_transition(before, after)
    assert error.value.status_code == 409


@pytest.mark.integration
async def test_ownership_and_role_guards(client: AsyncClient, builder: Builder, bearer_headers):
    owner = await builder.build_user()
    stranger = await builder.build_user()
    admin = await builder.build_user(role="admin")
    ticket = await builder.build_ticket(author_login=owner.login)
    path = f"/api/v1/tickets/{ticket.id}"
    assert (await client.get(path)).status_code == 401
    for suffix in ("", "/comments"):
        assert (await client.get(path + suffix, headers=bearer_headers(stranger))).status_code == 404
    assert (
        await client.post(path + "/comments", headers=bearer_headers(stranger), json={"body": "чужой"})
    ).status_code == 404
    assert (await client.get(path, headers=bearer_headers(admin))).status_code == 403
    assert (await client.get("/api/v1/admin/users", headers=bearer_headers(owner))).status_code == 403
    assert (await client.get("/api/v1/summary", headers=bearer_headers(owner))).status_code == 403
    result = await client.get("/api/v1/tickets", headers=bearer_headers(stranger))
    assert result.json()["items"] == []
    foreign = await builder.build_ticket(author_login=stranger.login)
    own = await client.get("/api/v1/tickets", headers=bearer_headers(owner))
    assert [row["id"] for row in own.json()["items"]] == [ticket.id]
    support = await builder.build_user(role="support")
    queue = await client.get("/api/v1/tickets", headers=bearer_headers(support))
    assert {row["id"] for row in queue.json()["items"]} == {ticket.id, foreign.id}


@pytest.mark.integration
async def test_login_and_token_revocation(client: AsyncClient, builder: Builder, bearer_headers):
    user = await builder.build_user(password="  secret-password  ")
    admin = await builder.build_user(role="admin")
    wrong = await client.post("/api/v1/auth/login", json={"login": user.login, "password": "secret-password"})
    assert wrong.status_code == 401
    login = await client.post("/api/v1/auth/login", json={"login": user.login, "password": "  secret-password  "})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert "password_hash" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    changed = await client.patch(
        f"/api/v1/admin/users/{user.login}", headers=bearer_headers(admin), json={"role": "support"}
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    blocked = await client.patch(
        f"/api/v1/admin/users/{user.login}", headers=bearer_headers(admin), json={"is_active": False}
    )
    assert blocked.status_code == 200
    assert (
        await client.post("/api/v1/auth/login", json={"login": user.login, "password": "  secret-password  "})
    ).status_code == 401


@pytest.mark.integration
async def test_expired_and_tampered_tokens(client, builder, settings, frozen_datetime):
    import jwt

    user = await builder.build_user()
    claims = {
        "sub": user.login,
        "ver": 0,
        "iat": int(frozen_datetime.timestamp()) - 7200,
        "exp": int(frozen_datetime.timestamp()) - 1,
        "iss": "coursework-helpdesk",
        "aud": "helpdesk-ui",
    }
    for token in (jwt.encode(claims, settings.jwt_secret, algorithm="HS256"), "garbage"):
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


@pytest.mark.integration
async def test_norm_snapshot_and_category_disable(client, builder, bearer_headers):
    customer = await builder.build_user()
    admin = await builder.build_user(role="admin")
    category = await builder.build_category(response_seconds=120)
    payload = {"category_id": category.id, "title": "Помогите", "body": "Нет доступа"}
    first = await client.post("/api/v1/tickets", headers=bearer_headers(customer), json=payload)
    assert first.status_code == 201
    assert first.json()["response_norm_seconds"] == 120
    update = await client.put(
        f"/api/v1/admin/norms/{category.id}", headers=bearer_headers(admin), json={"response_seconds": 240}
    )
    assert update.status_code == 200
    assert update.json()["response_seconds"] == 240
    second = await client.post("/api/v1/tickets", headers=bearer_headers(customer), json=payload)
    assert second.json()["response_norm_seconds"] == 240
    old = await client.get(f"/api/v1/tickets/{first.json()['id']}", headers=bearer_headers(customer))
    assert old.json()["reaction"]["norm_seconds"] == 120
    await client.patch(
        f"/api/v1/admin/categories/{category.id}", headers=bearer_headers(admin), json={"is_active": False}
    )
    assert (await client.post("/api/v1/tickets", headers=bearer_headers(customer), json=payload)).status_code == 404


@pytest.mark.integration
async def test_status_and_comments(client, builder, bearer_headers):
    customer = await builder.build_user()
    support = await builder.build_user(role="support")
    ticket = await builder.build_ticket(author_login=customer.login)
    path = f"/api/v1/tickets/{ticket.id}"
    assert (
        await client.patch(path + "/status", headers=bearer_headers(customer), json={"status": "in_progress"})
    ).status_code == 403
    assert (
        await client.patch(path + "/status", headers=bearer_headers(support), json={"status": "closed"})
    ).status_code == 409
    for status in ("in_progress", "in_progress", "closed"):
        result = await client.patch(path + "/status", headers=bearer_headers(support), json={"status": status})
        assert result.status_code == 200
        assert result.json()["status"] == status
    assert result.json()["closed_at"] is not None
    assert (
        await client.post(path + "/comments", headers=bearer_headers(customer), json={"body": "ещё"})
    ).status_code == 409
    assert (
        await client.patch(path + "/status", headers=bearer_headers(support), json={"status": "new"})
    ).status_code == 409


@pytest.mark.integration
async def test_first_reply_summary_and_empty_category(client, builder, bearer_headers, frozen_datetime):
    support = await builder.build_user(role="support")
    category = await builder.build_category()
    empty = await builder.build_category(name="Пустая")
    created = frozen_datetime - timedelta(hours=2)
    on_time = await builder.build_ticket(category_id=category.id, created_at=created)
    late = await builder.build_ticket(category_id=category.id, created_at=created)
    await builder.build_ticket(category_id=category.id, created_at=created, status="closed")
    await builder.build_comment(ticket_id=on_time.id, created_at=created + timedelta(seconds=3600))
    await builder.build_comment(ticket_id=on_time.id, created_at=frozen_datetime)
    await builder.build_comment(ticket_id=late.id, is_staff_reply=False, created_at=created + timedelta(seconds=1))
    result = await client.get("/api/v1/summary", headers=bearer_headers(support))
    assert result.status_code == 200
    assert result.json()["open_count"] == 2
    rows = {r["category_id"]: r for r in result.json()["items"]}
    assert rows[category.id]["breached_share"] == 0.5
    assert rows[empty.id]["open_count"] == rows[empty.id]["breached_share"] == 0
    detail = await client.get(f"/api/v1/tickets/{on_time.id}", headers=bearer_headers(support))
    assert detail.json()["reaction"]["elapsed_seconds"] == 3600
    assert detail.json()["reaction"]["breached"] is False


@pytest.mark.integration
async def test_closed_without_support_reply_uses_closing_time(client, builder, bearer_headers, frozen_datetime):
    owner = await builder.build_user(login="customer", display_name="Демонстрационный пользователь")
    created = frozen_datetime - timedelta(days=30)
    ticket = await builder.build_ticket(author_login=owner.login, created_at=created, status="closed")
    await builder.build_comment(
        ticket_id=ticket.id,
        author_login=owner.login,
        is_staff_reply=False,
        created_at=created + timedelta(minutes=10),
    )
    response = await client.get(f"/api/v1/tickets/{ticket.id}", headers=bearer_headers(owner))
    assert response.status_code == 200
    data = response.json()
    assert data["author_login"] == "customer"
    assert data["author_name"] == owner.display_name
    assert data["reaction"]["first_staff_reply_at"] is None
    assert data["reaction"]["elapsed_seconds"] == 3600
    assert data["reaction"]["breached"] is False


@pytest.mark.integration
async def test_cursor_filters_and_insert_snapshot(client, builder, bearer_headers):
    support = await builder.build_user(role="support")
    category = await builder.build_category()
    tickets = [await builder.build_ticket(category_id=category.id) for _ in range(5)]
    await builder.build_ticket(category_id=category.id, status="closed")
    params = {"limit": 2, "status": "new", "category_id": category.id}
    headers = bearer_headers(support)
    first = (await client.get("/api/v1/tickets", headers=headers, params=params)).json()
    assert [t["id"] for t in first["items"]] == [tickets[4].id, tickets[3].id]
    await builder.build_ticket(category_id=category.id)
    cursor = first["next_cursor"]
    bad = await client.get("/api/v1/tickets", headers=headers, params={**params, "status": "closed", "cursor": cursor})
    assert bad.status_code == 400
    seen = [t["id"] for t in first["items"]]
    while cursor:
        page = (await client.get("/api/v1/tickets", headers=headers, params={**params, "cursor": cursor})).json()
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
    assert seen == [t.id for t in reversed(tickets)]
    for query in ({"cursor": "broken"}, {"limit": 0}, {"limit": 101}, {"status": "invalid"}):
        assert (await client.get("/api/v1/tickets", headers=headers, params=query)).status_code == 400


@pytest.mark.integration
async def test_comment_cursor_snapshot_and_staff_flag(client, builder, bearer_headers):
    customer = await builder.build_user()
    support = await builder.build_user(role="support")
    ticket = await builder.build_ticket(author_login=customer.login)
    path = f"/api/v1/tickets/{ticket.id}/comments"
    comments = [await builder.build_comment(ticket_id=ticket.id) for _ in range(3)]
    first = (await client.get(path, headers=bearer_headers(customer), params={"limit": 2})).json()
    posted = await client.post(path, headers=bearer_headers(customer), json={"body": "Спасибо"})
    assert posted.status_code == 201
    assert posted.json()["is_staff_reply"] is False
    reply = await client.post(path, headers=bearer_headers(support), json={"body": "Ответ"})
    assert reply.json()["is_staff_reply"] is True
    second = (
        await client.get(path, headers=bearer_headers(customer), params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()
    assert [c["id"] for c in second["items"]] == [comments[-1].id]
    assert second["has_more"] is False
    assert (
        await client.post(path, headers=bearer_headers(customer), json={"body": "x", "is_staff_reply": True})
    ).status_code == 400


@pytest.mark.integration
async def test_admin_crud_and_self_lock_protection(client, builder, bearer_headers):
    admin = await builder.build_user(role="admin")
    headers = bearer_headers(admin)
    new = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"login": "created_user", "display_name": "Новый", "role": "support", "password": "  new-password  "},
    )
    assert new.status_code == 201
    assert (
        await client.post("/api/v1/auth/login", json={"login": "created_user", "password": "  new-password  "})
    ).status_code == 200
    for data in ({"is_active": False}, {"role": "customer"}, {}, {"display_name": None}):
        assert (await client.patch(f"/api/v1/admin/users/{admin.login}", headers=headers, json=data)).status_code in (
            400,
            409,
        )
    category = await client.post(
        "/api/v1/admin/categories", headers=headers, json={"name": "Новая", "response_seconds": 60}
    )
    assert category.status_code == 201
    norm = (await client.get("/api/v1/admin/norms", headers=headers)).json()["items"][0]
    assert norm == {"category_id": category.json()["id"], "response_seconds": 60}
    assert (
        await client.put(f"/api/v1/admin/norms/{category.json()['id']}", headers=headers, json={"response_seconds": 0})
    ).status_code == 400


@pytest.mark.integration
@pytest.mark.parametrize("assignment", ["status = 'invalid'", "response_norm_seconds = 0", "category_id = -1"])
async def test_database_rejects_invalid_data(builder: Builder, db_session: AsyncSession, assignment):
    ticket = await builder.build_ticket()
    with pytest.raises(IntegrityError):
        await db_session.execute(text(f"UPDATE tickets SET {assignment} WHERE id = :id"), {"id": ticket.id})
    await db_session.rollback()
