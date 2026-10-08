from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import PasswordService
from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.users.db_models import UserModel
from backend.storage.pg.database import Base


class Builder:
    def __init__(self, session: AsyncSession, default_datetime: datetime | None = None) -> None:
        self._session = session
        self._default_datetime = default_datetime or datetime(2026, 9, 1, 12, tzinfo=UTC)
        self._counter = 0
        self._customer: UserModel | None = None
        self._category: CategoryModel | None = None

    async def _insert[T: Base](self, model: type[T], **values: Any) -> T:
        result = await self._session.execute(insert(model).values(**values).returning(model))
        return result.scalar_one()

    async def build_user(
        self,
        *,
        login: str | None = None,
        role: str = "customer",
        password: str = "Test-password-123",
        display_name: str = "Тестовый пользователь",
        is_active: bool = True,
    ) -> UserModel:
        self._counter += 1
        return await self._insert(
            UserModel,
            login=login or f"user_{self._counter}",
            role=role,
            password_hash=PasswordService().hash(password),
            display_name=display_name,
            is_active=is_active,
            created_at=self._default_datetime,
        )

    @property
    async def default_customer(self) -> UserModel:
        if self._customer is None:
            self._customer = await self.build_user()
        return self._customer

    async def build_norm(self, *, category_id: int, response_seconds: int = 3600) -> ResponseNormModel:
        return await self._insert(ResponseNormModel, category_id=category_id, response_seconds=response_seconds)

    async def build_category(
        self, *, name: str = "Тестовая категория", response_seconds: int = 3600, is_active: bool = True
    ) -> CategoryModel:
        category = await self._insert(CategoryModel, name=name, description="Описание", is_active=is_active)
        await self.build_norm(category_id=category.id, response_seconds=response_seconds)
        return category

    @property
    async def default_category(self) -> CategoryModel:
        if self._category is None:
            self._category = await self.build_category()
        return self._category

    async def build_ticket(
        self,
        *,
        author_login: str | None = None,
        category_id: int | None = None,
        title: str = "Тестовая заявка",
        status: str = "new",
        response_norm_seconds: int = 3600,
        created_at: datetime | None = None,
    ) -> TicketModel:
        created = created_at or self._default_datetime
        return await self._insert(
            TicketModel,
            author_login=author_login or (await self.default_customer).login,
            category_id=category_id or (await self.default_category).id,
            title=title,
            body="Подробное описание проблемы",
            status=status,
            response_norm_seconds=response_norm_seconds,
            created_at=created,
            closed_at=created + timedelta(hours=1) if status == "closed" else None,
        )

    async def build_comment(
        self,
        *,
        ticket_id: int,
        author_login: str | None = None,
        is_staff_reply: bool = True,
        created_at: datetime | None = None,
        body: str = "Комментарий",
    ) -> CommentModel:
        if author_login is None:
            author_login = (await self.build_user(role="support" if is_staff_reply else "customer")).login
        return await self._insert(
            CommentModel,
            ticket_id=ticket_id,
            author_login=author_login,
            body=body,
            is_staff_reply=is_staff_reply,
            created_at=created_at or self._default_datetime,
        )
