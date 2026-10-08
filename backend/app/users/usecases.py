from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import AuthContext, PasswordService
from backend.app.users.db_models import UserModel
from backend.shared.schemas import (
    CreateUser,
    Page,
    PatchUser,
    UserDTO,
)
from backend.shared.utils import AppError, Clock, Paginator


class UserUseCase:
    def __init__(self, session: AsyncSession, paginator: Paginator, passwords: PasswordService, clock: Clock) -> None:
        self.session = session
        self.paginator = paginator
        self.passwords = passwords
        self.clock = clock


class ListUsersUseCase(UserUseCase):
    async def execute(self, ctx: AuthContext, limit: int, cursor: str | None) -> Page[UserDTO]:
        ctx.require("admin")
        return await self.paginator.page(
            self.session,
            select(UserModel),
            UserModel.login,
            "login",
            UserDTO,
            limit,
            cursor,
            {"resource": "users", "user": ctx.login},
        )


class CreateUserUseCase(UserUseCase):
    async def execute(self, ctx: AuthContext, data: CreateUser) -> UserDTO:
        ctx.require("admin")
        try:
            user = (
                await self.session.execute(
                    insert(UserModel)
                    .values(
                        **data.model_dump(exclude={"password"}),
                        password_hash=self.passwords.hash(data.password),
                        created_at=self.clock.now(),
                    )
                    .returning(UserModel)
                )
            ).scalar_one()
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Логин уже занят", status_code=409) from exc
        return UserDTO.model_validate(user)


class PatchUserUseCase(UserUseCase):
    async def execute(self, ctx: AuthContext, login: str, data: PatchUser) -> UserDTO:
        ctx.require("admin")
        values = data.model_dump(exclude_unset=True)
        if not values or any(value is None for value in values.values()):
            raise AppError("Нужно передать непустые поля изменения", status_code=400)
        if login == ctx.login and (
            values.get("is_active") is False or ("role" in values and values["role"] != "admin")
        ):
            raise AppError("Нельзя отключить собственную учётную запись администратора", status_code=409)

        await self.session.execute(select(func.pg_advisory_xact_lock(0x48444B, 1)))
        actor = await self.session.scalar(
            select(UserModel).where(UserModel.login == ctx.login).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.role != "admin":
            raise AppError("Права администратора изменились", status_code=403)
        current = await self.session.scalar(
            select(UserModel)
            .where(UserModel.login == login)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise AppError("Пользователь не найден", status_code=404)
        if (
            current.is_active
            and current.role == "admin"
            and (values.get("is_active") is False or values.get("role", current.role) != "admin")
        ):
            remaining = await self.session.scalar(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.is_active.is_(True), UserModel.role == "admin")
            )
            if remaining is None or remaining <= 1:
                raise AppError("Должен оставаться хотя бы один активный администратор", status_code=409)
        if "password" in values:
            values["password_hash"] = self.passwords.hash(values.pop("password"))
        if "password_hash" in values or any(
            field in values and values[field] != getattr(current, field) for field in ("role", "is_active")
        ):
            values["auth_version"] = UserModel.auth_version + 1
        user = (
            await self.session.execute(
                update(UserModel).where(UserModel.login == login).values(**values).returning(UserModel)
            )
        ).scalar_one()
        await self.session.commit()
        return UserDTO.model_validate(user)
