from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get, post

from backend.app.auth.usecases import LoginUseCase
from backend.app.users.db_models import UserModel
from backend.shared.schemas import (
    LoginRequest,
    LoginResponse,
    UserDTO,
)


class AuthController(Controller):
    path = ""

    @post("/auth/login", status_code=200)
    @inject
    async def login(self, data: LoginRequest, usecase: FromDishka[LoginUseCase]) -> LoginResponse:
        return await usecase.execute(data)

    @get("/auth/me")
    @inject
    async def me(self, user: FromDishka[UserModel]) -> UserDTO:
        return UserDTO.model_validate(user)
