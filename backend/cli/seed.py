import argparse
import asyncio
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import make_url

from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.users.db_models import UserModel
from backend.shared.config import Settings
from backend.storage.pg.database import Database

PROFILES = {"small": (100, 10, 600), "work": (6000, 20, 100000)}
DEMO_PASSWORD = "Demo-password-2026!"
REFERENCE_DATE = datetime(2026, 9, 1, 12, tzinfo=UTC)
TABLES = (UserModel, CategoryModel, ResponseNormModel, TicketModel, CommentModel)
CATEGORY_NAMES = [
    "Учётная запись",
    "Сеть и интернет",
    "Учебные системы",
    "Программное обеспечение",
    "Оборудование",
    "Электронная почта",
    "Доступ в корпус",
    "Документы",
    "Библиотека",
    "Другое",
    "Печать и сканирование",
    "Видеоконференции",
    "Личный кабинет",
    "Облачные сервисы",
    "Телефония",
    "Информационная безопасность",
    "Мобильные приложения",
    "Аудиторное оборудование",
    "Виртуальные рабочие места",
    "Лицензии программ",
]


class SeedCommand:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()

    @staticmethod
    def demo_comments(ticket: dict[str, Any]) -> list[dict[str, Any]]:

        ticket_id = ticket["id"]
        answered = ticket["status"] == "closed" or (ticket["status"] == "in_progress" and ticket_id % 4 != 0)
        norm = ticket["response_norm_seconds"]
        reply_delay = norm // 2 if ticket_id % 4 in (0, 1) else norm * 2
        if answered:
            messages = (
                "Уточнение: проблема повторяется при каждой попытке.",
                "Проблема устранена. Проверьте, пожалуйста, результат."
                if ticket["status"] == "closed"
                else "Проверяем обращение. Сообщим, когда появится результат.",
                "Спасибо, теперь всё работает." if ticket["status"] == "closed" else "Спасибо, ожидаю решения.",
            )
        else:
            messages = (
                "Уточнение: проблема повторяется при каждой попытке.",
                "Повторил действие — ошибка сохраняется.",
                "Пока не удалось решить проблему самостоятельно.",
            )
        return [
            {
                "id": (ticket_id - 1) * 3 + j + 1,
                "ticket_id": ticket_id,
                "author_login": "support" if answered and j == 1 else ticket["author_login"],
                "body": body,
                "is_staff_reply": answered and j == 1,
                "created_at": ticket["created_at"] + timedelta(seconds=30 if j == 0 else reply_delay + j),
            }
            for j, body in enumerate(messages)
        ]

    async def execute(self, profile: str, reset: bool, output: str | None) -> None:
        settings = self.settings
        url = make_url(settings.url) if isinstance(settings.url, str) else settings.url
        allowed = {f"{settings.personal_prefix}_helpdesk", f"{settings.personal_prefix}_helpdesk_test"}
        if url.database not in allowed or url.host not in {"localhost", "127.0.0.1", "db"}:
            raise SystemExit("Seed разрешён только для локальной учебной БД с личным префиксом")
        if not reset:
            raise SystemExit("Укажите --reset: наполнение заменяет все учебные данные")
        users_count, categories_count, tickets_count = PROFILES[profile]
        rng = random.Random(17)

        password_hash = PasswordHasher().hash(DEMO_PASSWORD, salt=b"helpdesk-demo-17!")
        users = [
            {
                "login": login,
                "display_name": name,
                "role": role,
                "password_hash": password_hash,
                "created_at": REFERENCE_DATE - timedelta(days=180),
            }
            for login, name, role in [
                ("customer", "Демонстрационный пользователь", "customer"),
                ("support", "Сотрудник поддержки", "support"),
                ("admin", "Администратор", "admin"),
            ]
        ]
        users += [
            {
                "login": f"user_{i:05d}",
                "display_name": f"Пользователь {i}",
                "role": "customer",
                "password_hash": password_hash,
                "created_at": REFERENCE_DATE - timedelta(days=180),
            }
            for i in range(3, users_count)
        ]
        categories = [
            {
                "id": i + 1,
                "name": CATEGORY_NAMES[i],
                "description": f"Помощь: {CATEGORY_NAMES[i].lower()}",
                "is_active": True,
            }
            for i in range(categories_count)
        ]
        norms = [{"category_id": i + 1, "response_seconds": (1 + i % 4) * 3600} for i in range(categories_count)]
        tickets, comments = [], []
        for i in range(1, tickets_count + 1):
            category_id = rng.randrange(1, categories_count + 1)
            norm = norms[category_id - 1]["response_seconds"]
            author = "customer" if i % 10 == 0 else users[3 + (i % (users_count - 3))]["login"]
            status = ("new", "in_progress", "closed")[i % 3]
            created = REFERENCE_DATE - timedelta(seconds=rng.randrange(4 * 3600, 90 * 86400))
            tickets.append(
                {
                    "id": i,
                    "author_login": author,
                    "category_id": category_id,
                    "title": f"{CATEGORY_NAMES[category_id - 1]}: обращение {i}",
                    "body": "Не удаётся выполнить действие. Прошу проверить доступ и помочь с решением проблемы.",
                    "status": status,
                    "response_norm_seconds": norm,
                    "created_at": created,
                    "closed_at": created + timedelta(seconds=norm * 4) if status == "closed" else None,
                }
            )
            comments.extend(self.demo_comments(tickets[-1]))
        data: list[list[dict[str, Any]]] = [users, categories, norms, tickets, comments]
        fingerprint = hashlib.sha256(
            json.dumps(data, default=str, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        database = Database(settings)
        try:
            async with database.session() as session:
                await session.execute(
                    text("TRUNCATE comments, tickets, response_norms, categories, users RESTART IDENTITY")
                )
                for model, rows in zip(TABLES, data, strict=True):
                    for start in range(0, len(rows), 1000):
                        await session.execute(insert(model), rows[start : start + 1000])
                for name in ("categories", "tickets", "comments"):
                    await session.execute(
                        text(f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), (SELECT max(id) FROM {name}))")
                    )
                await session.commit()
                counts = {
                    model.__tablename__: await session.scalar(select(func.count()).select_from(model))
                    for model in TABLES
                }
                for model in TABLES:
                    await session.execute(text(f"ANALYZE {model.__tablename__}"))
                await session.commit()
            result = {
                "profile": profile,
                "random_seed": 17,
                "reference_date": REFERENCE_DATE.isoformat(),
                "counts": counts,
                "data_sha256": fingerprint,
                "generated_at": datetime.now(UTC).isoformat(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        finally:
            await database.disconnect()

    @classmethod
    def main(cls) -> None:
        parser = argparse.ArgumentParser(description="Helpdesk SeedCommand")
        parser.add_argument("--profile", choices=PROFILES, default="small")
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--output")
        args = parser.parse_args()
        asyncio.run(cls().execute(args.profile, args.reset, args.output))


if __name__ == "__main__":
    SeedCommand.main()
