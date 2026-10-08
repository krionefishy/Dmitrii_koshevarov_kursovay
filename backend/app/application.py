from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import Provider, make_async_container
from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request, Response
from litestar.middleware import DefineMiddleware
from litestar.openapi import OpenAPIConfig

from backend.app.api.router import api_router
from backend.app.ui.routes import ui_router
from backend.shared.config import Settings
from backend.shared.di.providers.provider import ProviderRegistry
from backend.shared.utils import AppError
from backend.storage.pg.database import Database


class ApplicationFactory:
    @staticmethod
    def app_error_handler(request: Request, exc: AppError) -> Response:
        return Response(content={"detail": exc.detail}, status_code=exc.status_code)

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        *,
        extra_providers: tuple[Provider, ...] = (),
        database: Database | None = None,
        middleware: tuple[DefineMiddleware, ...] = (),
    ) -> Litestar:
        settings = settings or Settings.load()
        database = database if database is not None else Database(settings)
        container = make_async_container(
            *ProviderRegistry.build(),
            *extra_providers,
            context={Settings: settings, Database: database},
        )

        @asynccontextmanager
        async def lifespan(app: Litestar) -> AsyncIterator[None]:
            try:
                yield
            finally:
                try:
                    await container.close()
                finally:
                    await database.disconnect()

        app = Litestar(
            route_handlers=[api_router, ui_router],
            lifespan=[lifespan],
            middleware=list(middleware),
            exception_handlers={AppError: cls.app_error_handler},
            response_headers={"Cache-Control": "no-store"},
            openapi_config=OpenAPIConfig(title=settings.app_name, version="0.1.0", path="/api/docs"),
        )
        setup_dishka(container=container, app=app)
        return app
