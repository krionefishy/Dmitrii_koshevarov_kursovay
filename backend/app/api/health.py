from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class HealthController(Controller):
    path = ""

    @get("/health", cache=False)
    async def health(self) -> dict[str, str]:
        return {"status": "ok"}

    @get("/ready", cache=False)
    @inject
    async def ready(self, session: FromDishka[AsyncSession]) -> dict[str, str]:
        await session.execute(select(1))
        return {"status": "ok"}
