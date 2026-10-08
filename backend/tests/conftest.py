import asyncio
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from dishka import Provider, Scope, provide
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.application import ApplicationFactory
from backend.app.auth.services import TokenService
from backend.app.users.db_models import UserModel
from backend.shared.config import Settings
from backend.shared.utils import Clock
from backend.storage.pg.database import Database
from backend.tests.builder import Builder

_current_db_session: ContextVar[AsyncSession | None] = ContextVar("current_test_db_session", default=None)


class TestSessionProvider(Provider):
    @provide(scope=Scope.REQUEST, override=True)
    def session(self) -> AsyncSession:
        session = _current_db_session.get()
        if session is None:
            raise RuntimeError("Database API tests must request the db_session or builder fixture")
        return session


@pytest.fixture
def settings() -> Settings:
    return Settings.load()


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    url = make_url(settings.url) if isinstance(settings.url, str) else settings.url
    if not url.database or not url.database.endswith("_test"):
        raise ValueError("Test database name must end with _test")
    database = Database(settings)
    try:
        yield database
    finally:
        await database.disconnect()


@pytest.fixture
async def db_session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            ) as session:
                token = _current_db_session.set(session)
                try:
                    yield session
                finally:
                    _current_db_session.reset(token)
        finally:
            await transaction.rollback()


@pytest.fixture
def frozen_datetime() -> datetime:
    return datetime(2026, 9, 1, 12, tzinfo=UTC)


@pytest.fixture
def builder(db_session: AsyncSession, frozen_datetime: datetime) -> Builder:
    return Builder(db_session, frozen_datetime)


@pytest.fixture
async def application(settings: Settings, frozen_datetime: datetime) -> AsyncIterator[Litestar]:
    class FrozenClock(Clock):
        def now(self) -> datetime:
            return frozen_datetime

    class TestClockProvider(Provider):
        @provide(scope=Scope.APP, override=True)
        def clock(self) -> Clock:
            return FrozenClock()

    app = ApplicationFactory.create(settings, extra_providers=(TestSessionProvider(), TestClockProvider()))
    started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    stopped = asyncio.Event()

    async def run_lifespan() -> None:

        try:
            async with app.lifespan():
                started.set_result(None)
                await stopped.wait()
        except BaseException as exc:
            if not started.done():
                started.set_exception(exc)
            raise

    lifespan_task = asyncio.create_task(run_lifespan())
    try:
        await started
        yield app
    finally:
        stopped.set()
        await lifespan_task


@pytest.fixture
async def client(application: Litestar) -> AsyncIterator[AsyncClient]:

    transport = ASGITransport(app=cast(Any, application))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def session_request(client: AsyncClient):

    async def request(session: AsyncSession, method: str, path: str, **kwargs):
        token = _current_db_session.set(session)
        try:
            return await client.request(method, path, **kwargs)
        finally:
            await session.rollback()
            _current_db_session.reset(token)

    return request


@pytest.fixture
def bearer_headers(settings: Settings, frozen_datetime: datetime):
    class FrozenClock(Clock):
        def now(self) -> datetime:
            return frozen_datetime

    def headers(user: UserModel) -> dict[str, str]:
        return {"Authorization": f"Bearer {TokenService(settings, FrozenClock()).issue(user.login, user.auth_version)}"}

    return headers


@pytest.fixture
async def committed_sessions(database: Database):

    from sqlalchemy import text

    async with database.session() as first, database.session() as second:
        try:
            yield first, second
        finally:
            await first.rollback()
            await second.rollback()
            await first.execute(text("TRUNCATE comments, tickets, response_norms, categories, users RESTART IDENTITY"))
            await first.commit()


@pytest.fixture
async def benchmark_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    from backend.benchmarks.application import BenchmarkApplicationFactory

    app = BenchmarkApplicationFactory.create(settings)
    started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    stopped = asyncio.Event()

    async def run_lifespan() -> None:
        try:
            async with app.lifespan():
                started.set_result(None)
                await stopped.wait()
        except BaseException as exc:
            if not started.done():
                started.set_exception(exc)
            raise

    lifespan_task = asyncio.create_task(run_lifespan())
    try:
        await started
        transport = ASGITransport(app=cast(Any, app))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        stopped.set()
        await lifespan_task
