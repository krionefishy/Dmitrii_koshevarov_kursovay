import argparse
import asyncio
import importlib.metadata
import json
import math
import platform
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.engine import make_url

from backend.app.auth.services import PasswordService
from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.users.db_models import UserModel
from backend.cli.seed import DEMO_PASSWORD, PROFILES, TABLES
from backend.shared.config import Settings
from backend.storage.pg.database import Database


class BenchmarkCommand:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()

    async def execute(self, base_url: str, profile: str, warmup: int, repeats: int, output: str) -> None:
        if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
            raise SystemExit("Benchmark supports the local coursework service only")
        settings = self.settings
        url = make_url(settings.url) if isinstance(settings.url, str) else settings.url
        allowed = {f"{settings.personal_prefix}_helpdesk", f"{settings.personal_prefix}_helpdesk_test"}
        if url.database not in allowed or url.host not in {"localhost", "127.0.0.1", "db"}:
            raise SystemExit("Benchmark database must be the local coursework database")
        database = Database(settings)
        password_hash = PasswordService().hash(DEMO_PASSWORD)
        headers = {}
        results = []
        started = datetime.now(UTC).isoformat()
        try:
            async with database.session() as session:
                before = {m.__tablename__: await session.scalar(select(func.count()).select_from(m)) for m in TABLES}
                db_version = await session.scalar(text("SELECT version()"))
                if await session.get(UserModel, "bench_user") is not None:
                    raise SystemExit("bench_user already exists; reset the demo dataset before benchmarking")
            users, categories, tickets = PROFILES[profile]
            expected = {
                "users": users,
                "categories": categories,
                "response_norms": categories,
                "tickets": tickets,
                "comments": tickets * 3,
            }
            if before != expected:
                raise SystemExit(f"Expected {expected} for {profile}, got {before}; seed first")
            async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
                readiness = await client.get("/api/v1/health")
                readiness.raise_for_status()
                if not {"x-server-ms", "x-db-ms", "x-sql-count"}.issubset(readiness.headers):
                    raise SystemExit("Start the measurement server with just serve-benchmark or just benchmark-up")
                for role in ("customer", "support", "admin"):
                    login = await client.post("/api/v1/auth/login", json={"login": role, "password": DEMO_PASSWORD})
                    login.raise_for_status()
                    headers[role] = {"Authorization": "Bearer " + login.json()["access_token"]}
                first = await client.get("/api/v1/tickets?limit=20", headers=headers["support"])
                first.raise_for_status()
                cursor = first.json()["next_cursor"]
                operations = [
                    ("login", "customer", "POST", "/auth/login", {"login": "customer", "password": DEMO_PASSWORD}),
                    ("me", "customer", "GET", "/auth/me", None),
                    ("categories", "customer", "GET", "/categories?limit=20", None),
                    ("own_tickets", "customer", "GET", "/tickets?limit=20", None),
                    ("queue", "support", "GET", "/tickets?limit=20", None),
                    ("queue_filtered", "support", "GET", "/tickets?limit=20&category_id=1&status=new", None),
                    ("queue_page_2", "support", "GET", f"/tickets?limit=20&cursor={cursor}", None),
                    ("ticket_detail", "customer", "GET", "/tickets/10", None),
                    ("comments", "customer", "GET", "/tickets/10/comments?limit=20", None),
                    ("summary", "support", "GET", "/summary", None),
                    ("admin_categories", "admin", "GET", "/admin/categories?limit=20", None),
                    ("admin_norms", "admin", "GET", "/admin/norms?limit=20", None),
                    ("admin_users", "admin", "GET", "/admin/users?limit=20", None),
                    (
                        "create_ticket",
                        "customer",
                        "POST",
                        "/tickets",
                        {"category_id": 1, "title": "Замер", "body": "Замер создания"},
                    ),
                    ("add_comment", "support", "POST", "/tickets/{ticket}/comments", {"body": "Ответ поддержки"}),
                    ("change_status", "support", "PATCH", "/tickets/{ticket}/status", {"status": "in_progress"}),
                    (
                        "create_category",
                        "admin",
                        "POST",
                        "/admin/categories",
                        {"name": "Замер категории", "response_seconds": 3600},
                    ),
                    (
                        "patch_category",
                        "admin",
                        "PATCH",
                        "/admin/categories/{category}",
                        {"name": "Изменённая категория"},
                    ),
                    ("set_norm", "admin", "PUT", "/admin/norms/{category}", {"response_seconds": 7200}),
                    (
                        "create_user",
                        "admin",
                        "POST",
                        "/admin/users",
                        {"login": "bench_user", "display_name": "Замер", "role": "customer", "password": DEMO_PASSWORD},
                    ),
                    ("patch_user", "admin", "PATCH", "/admin/users/bench_user", {"display_name": "Изменённое имя"}),
                ]
                for name, role, method, route, payload in operations:
                    samples = []
                    for iteration in range(warmup + repeats):
                        ids = {}
                        cleanup_user = name in {"create_user", "patch_user"}
                        async with database.session() as session:
                            if "{ticket}" in route:
                                ids["ticket"] = await session.scalar(
                                    insert(TicketModel)
                                    .values(
                                        author_login="customer",
                                        category_id=1,
                                        title="Изолированный замер",
                                        body="Предусловие",
                                        status="new",
                                        response_norm_seconds=3600,
                                        created_at=datetime.now(UTC),
                                    )
                                    .returning(TicketModel.id)
                                )
                            if "{category}" in route:
                                ids["category"] = await session.scalar(
                                    insert(CategoryModel).values(name="Замер").returning(CategoryModel.id)
                                )
                                await session.execute(
                                    insert(ResponseNormModel).values(category_id=ids["category"], response_seconds=3600)
                                )
                            if name == "patch_user":
                                await session.execute(
                                    insert(UserModel).values(
                                        login="bench_user",
                                        display_name="Замер",
                                        role="customer",
                                        password_hash=password_hash,
                                    )
                                )
                            await session.commit()
                        try:
                            request_start = perf_counter()
                            response = await client.request(
                                method, "/api/v1" + route.format(**ids), headers=headers[role], json=payload
                            )
                            client_ms = (perf_counter() - request_start) * 1000
                            response.raise_for_status()
                            if name == "create_ticket":
                                ids["ticket"] = response.json()["id"]
                            if name == "create_category":
                                ids["category"] = response.json()["id"]
                            server_ms = float(response.headers["x-server-ms"])
                            db_ms = float(response.headers["x-db-ms"])
                            if iteration >= warmup:
                                samples.append(
                                    {
                                        "client_ms": client_ms,
                                        "server_ms": server_ms,
                                        "db_ms": db_ms,
                                        "non_sql_ms": max(0, server_ms - db_ms),
                                        "sql_count": int(response.headers["x-sql-count"]),
                                    }
                                )
                        finally:
                            async with database.session() as session:
                                if "ticket" in ids:
                                    await session.execute(
                                        delete(CommentModel).where(CommentModel.ticket_id == ids["ticket"])
                                    )
                                    await session.execute(delete(TicketModel).where(TicketModel.id == ids["ticket"]))
                                if "category" in ids:
                                    await session.execute(
                                        delete(ResponseNormModel).where(
                                            ResponseNormModel.category_id == ids["category"]
                                        )
                                    )
                                    await session.execute(
                                        delete(CategoryModel).where(CategoryModel.id == ids["category"])
                                    )
                                if cleanup_user:
                                    await session.execute(delete(UserModel).where(UserModel.login == "bench_user"))
                                await session.commit()
                    metrics = {}
                    for metric in samples[0]:
                        values = sorted(row[metric] for row in samples)
                        metrics[metric] = {
                            "median": statistics.median(values),
                            "p95": values[math.ceil(0.95 * len(values)) - 1],
                            "max": max(values),
                        }
                    result = {
                        "operation": name,
                        "role": role,
                        "method": method,
                        "route": route.split("cursor=")[0] + ("cursor=<page1>" if "cursor=" in route else ""),
                        "metrics": metrics,
                        "samples": samples,
                    }
                    results.append(result)
                    print(
                        f"{name}: median {metrics['client_ms']['median']:.2f} ms, "
                        f"p95 {metrics['client_ms']['p95']:.2f} ms",
                        flush=True,
                    )
            async with database.session() as session:
                after = {m.__tablename__: await session.scalar(select(func.count()).select_from(m)) for m in TABLES}
            assert before == after, (before, after)
            report = {
                "profile": profile,
                "started_at": started,
                "finished_at": datetime.now(UTC).isoformat(),
                "base_url": base_url,
                "warmup": warmup,
                "repeats": repeats,
                "concurrency": 1,
                "workers": 1,
                "percentile": "nearest rank",
                "platform": platform.platform(),
                "python": platform.python_version(),
                "postgres": db_version,
                "counts_before": before,
                "counts_after": after,
                "versions": {
                    p: importlib.metadata.version(p)
                    for p in ("litestar", "dishka", "sqlalchemy", "asyncpg", "uvicorn", "httpx")
                },
                "results": results,
            }
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        finally:
            await database.disconnect()

    @classmethod
    def main(cls) -> None:
        parser = argparse.ArgumentParser(description="Helpdesk BenchmarkCommand")
        parser.add_argument("--base-url", default="http://127.0.0.1:8000")
        parser.add_argument("--profile", choices=["small", "work"], required=True)
        parser.add_argument("--warmup", type=int, default=5)
        parser.add_argument("--repeats", type=int, default=30)
        parser.add_argument("--output", required=True)
        args = parser.parse_args()
        if args.repeats < 20 or args.warmup < 1:
            parser.error("Use at least 20 repetitions and one warmup")
        asyncio.run(cls().execute(args.base_url, args.profile, args.warmup, args.repeats, args.output))


if __name__ == "__main__":
    BenchmarkCommand.main()
