import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import AuthContext
from backend.app.categories.usecases import CreateCategoryUseCase
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.tickets.usecases import AddCommentUseCase, ChangeStatusUseCase, CreateTicketUseCase, SummaryUseCase
from backend.app.users.db_models import UserModel
from backend.app.users.usecases import PatchUserUseCase
from backend.shared.schemas import AddComment, CreateCategory, CreateTicket, SetStatus
from backend.shared.utils import AppError, Clock, Paginator
from backend.tests.builder import Builder

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("close_first", [True, False])
async def test_close_and_comment_serialize(committed_sessions, settings, frozen_datetime, close_first):
    first, second = committed_sessions
    builder = Builder(first, frozen_datetime)
    support = await builder.build_user(role="support")
    ticket = await builder.build_ticket(status="in_progress")
    await first.commit()
    ctx = AuthContext(support.login, "support")
    paginator = Paginator(settings)
    close = ChangeStatusUseCase(first if close_first else second, Clock(), paginator)
    comment = AddCommentUseCase(second if close_first else first, Clock(), paginator)
    await first.scalar(select(TicketModel).where(TicketModel.id == ticket.id).with_for_update())
    waiter_pid = await second.scalar(select(func.pg_backend_pid()))
    task = asyncio.create_task(
        comment.execute(ticket.id, AddComment(body="Ответ"), ctx)
        if close_first
        else close.execute(ticket.id, SetStatus(status="closed"), ctx)
    )
    try:
        for _ in range(500):
            waiting = await first.scalar(
                text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": waiter_pid}
            )
            if waiting:
                break
            await asyncio.sleep(0.01)
        assert waiting, "Second operation must wait for the ticket row lock"
        if close_first:
            await close.execute(ticket.id, SetStatus(status="closed"), ctx)
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(task, 5)
            assert error.value.status_code == 409
            expected_comments = 0
        else:
            await comment.execute(ticket.id, AddComment(body="Ответ"), ctx)
            await asyncio.wait_for(task, 5)
            expected_comments = 1
        assert await first.scalar(select(func.count()).select_from(CommentModel)) == expected_comments
        assert await first.scalar(select(TicketModel.status).where(TicketModel.id == ticket.id)) == "closed"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "customer"}])
async def test_admins_cannot_remove_each_other_concurrently(
    committed_sessions, frozen_datetime, session_request, bearer_headers, monkeypatch, change
):
    first, second = committed_sessions
    builder = Builder(first, frozen_datetime)
    alice = await builder.build_user(login="admin_alice", role="admin")
    bob = await builder.build_user(login="admin_bob", role="admin")
    await first.commit()

    gate = asyncio.Event()
    arrived = 0
    original = PatchUserUseCase.execute

    async def synchronized(self, ctx, login, data):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            gate.set()
        await asyncio.wait_for(gate.wait(), 5)
        return await original(self, ctx, login, data)

    monkeypatch.setattr(PatchUserUseCase, "execute", synchronized)
    responses = await asyncio.wait_for(
        asyncio.gather(
            session_request(
                first, "PATCH", f"/api/v1/admin/users/{bob.login}", headers=bearer_headers(alice), json=change
            ),
            session_request(
                second, "PATCH", f"/api/v1/admin/users/{alice.login}", headers=bearer_headers(bob), json=change
            ),
        ),
        10,
    )
    assert sorted(r.status_code for r in responses) == [200, 403]
    remaining = await first.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.role == "admin", UserModel.is_active.is_(True))
    )
    assert remaining == 1


async def test_summary_consistent_when_category_and_ticket_appear_during_read(
    committed_sessions, settings, frozen_datetime, monkeypatch
):
    first, second = committed_sessions
    builder = Builder(first, frozen_datetime)
    admin = await builder.build_user(role="admin")
    customer = await builder.build_user()
    empty = await builder.build_category(name="Пустая")
    await first.commit()
    ctx = AuthContext(admin.login, "admin")
    ready, proceed = asyncio.Event(), asyncio.Event()
    original = AsyncSession.execute

    async def pause_after_first_read(self, statement, *args, **kwargs):
        result = await original(self, statement, *args, **kwargs)
        if self is first and not ready.is_set():
            ready.set()
            await proceed.wait()
        return result

    monkeypatch.setattr(AsyncSession, "execute", pause_after_first_read)
    summary = SummaryUseCase(first, Clock(), Paginator(settings))
    task = asyncio.create_task(summary.execute(ctx))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        category = await CreateCategoryUseCase(second, Paginator(settings)).execute(
            ctx, CreateCategory(name="Новая во время чтения", response_seconds=3600)
        )
        await CreateTicketUseCase(second, Clock(), Paginator(settings)).execute(
            CreateTicket(category_id=category.id, title="Новая заявка", body="Описание"),
            AuthContext(customer.login, "customer"),
        )
        proceed.set()
        result = await asyncio.wait_for(task, 5)
        assert result.open_count == 0
        assert [row.category_id for row in result.items] == [empty.id]
        fresh = await summary.execute(ctx)
        assert fresh.open_count == 1
        assert [row.category_id for row in fresh.items] == [empty.id, category.id]
    finally:
        proceed.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
