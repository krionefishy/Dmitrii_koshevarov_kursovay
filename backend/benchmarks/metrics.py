from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter

from litestar.types import ASGIApp, Message, Receive, Scope, Send
from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class QueryMetrics:
    count: int = 0
    seconds: float = 0.0


_current: ContextVar[QueryMetrics | None] = ContextVar("request_query_metrics", default=None)


class EngineInstrumentation:
    def __init__(self, engine: Engine) -> None:
        event.listen(engine, "before_cursor_execute", self.before)
        event.listen(engine, "after_cursor_execute", self.after)
        event.listen(engine, "handle_error", self.error)

    def before(self, conn, cursor, statement, parameters, context, executemany) -> None:
        conn.info["query_started"] = perf_counter()
        metrics = _current.get()
        if metrics is not None:
            metrics.count += 1

    def finish(self, conn) -> None:
        started = conn.info.pop("query_started", None)
        metrics = _current.get()
        if started is not None and metrics is not None:
            metrics.seconds += perf_counter() - started

    def after(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.finish(conn)

    def error(self, context) -> None:
        if context.connection is not None:
            self.finish(context.connection)


class TimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        metrics = QueryMetrics()
        token = _current.set(metrics)

        async def measured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                server_ms = (perf_counter() - started) * 1000
                db_ms = metrics.seconds * 1000
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-server-ms", f"{server_ms:.3f}".encode()),
                        (b"x-db-ms", f"{db_ms:.3f}".encode()),
                        (b"x-sql-count", str(metrics.count).encode()),
                        (b"server-timing", f"server;dur={server_ms:.3f}, db;dur={db_ms:.3f}".encode()),
                    ]
                )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            _current.reset(token)
