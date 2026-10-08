from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import PasswordService, TokenService
from backend.app.users.db_models import UserModel
from backend.shared.config import Settings
from backend.shared.schemas import LoginRequest, LoginResponse, UserDTO
from backend.shared.utils import AppError


class LoginUseCase:
    def __init__(
        self, session: AsyncSession, passwords: PasswordService, tokens: TokenService, settings: Settings
    ) -> None:
        self.session = session
        self.passwords = passwords
        self.tokens = tokens
        self.settings = settings

    async def execute(self, data: LoginRequest) -> LoginResponse:
        user = await self.session.scalar(select(UserModel).where(UserModel.login == data.login))
        if user is None or not self.passwords.verify(user.password_hash, data.password) or not user.is_active:
            raise AppError("Неверный логин или пароль", status_code=401)
        return LoginResponse(
            access_token=self.tokens.issue(user.login, user.auth_version),
            expires_in=self.settings.token_ttl,
            user=UserDTO.model_validate(user),
        )
