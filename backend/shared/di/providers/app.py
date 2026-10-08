from collections.abc import AsyncIterator

from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.config import Settings
from backend.storage.pg.database import Database


class AppProvider(Provider):
    scope = Scope.APP
    settings = from_context(Settings)
    database = from_context(Database)


class SessionProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def session(self, database: Database) -> AsyncIterator[AsyncSession]:
        async with database.session() as session:
            yield session
