from typing import Annotated

from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get, patch, post
from litestar.params import PathParameter

from backend.app.api.parameters import Cursor, Limit
from backend.app.auth.services import AuthContext
from backend.app.users.usecases import CreateUserUseCase, ListUsersUseCase, PatchUserUseCase
from backend.shared.schemas import (
    CreateUser,
    Page,
    PatchUser,
    UserDTO,
)


class UsersController(Controller):
    path = ""

    @get("/admin/users")
    @inject
    async def list_users(
        self,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListUsersUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
    ) -> Page[UserDTO]:
        return await usecase.execute(ctx, limit, cursor)

    @post("/admin/users")
    @inject
    async def create_user(
        self, data: CreateUser, ctx: FromDishka[AuthContext], usecase: FromDishka[CreateUserUseCase]
    ) -> UserDTO:
        return await usecase.execute(ctx, data)

    @patch("/admin/users/{login:str}")
    @inject
    async def patch_user(
        self,
        login: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9_]{2,63}$")],
        data: PatchUser,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[PatchUserUseCase],
    ) -> UserDTO:
        return await usecase.execute(ctx, login, data)
