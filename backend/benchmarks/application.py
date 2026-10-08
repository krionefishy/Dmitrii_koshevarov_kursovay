from dishka import Provider
from litestar import Litestar
from litestar.middleware import DefineMiddleware

from backend.app.application import ApplicationFactory
from backend.benchmarks.metrics import EngineInstrumentation, TimingMiddleware
from backend.shared.config import Settings
from backend.storage.pg.database import Database


class BenchmarkApplicationFactory:
    @classmethod
    def create(cls, settings: Settings | None = None, *, extra_providers: tuple[Provider, ...] = ()) -> Litestar:
        settings = settings or Settings.load()
        database = Database(settings)
        EngineInstrumentation(database.engine.sync_engine)
        return ApplicationFactory.create(
            settings,
            extra_providers=extra_providers,
            database=database,
            middleware=(DefineMiddleware(TimingMiddleware),),
        )
