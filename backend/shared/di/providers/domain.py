from dishka import Provider, Scope, provide
from litestar import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import AuthContext, PasswordService, TokenService
from backend.app.auth.usecases import LoginUseCase
from backend.app.categories.usecases import (
    CreateCategoryUseCase,
    ListCategoriesUseCase,
    ListNormsUseCase,
    PatchCategoryUseCase,
    SetNormUseCase,
)
from backend.app.tickets.usecases import (
    AddCommentUseCase,
    ChangeStatusUseCase,
    CreateTicketUseCase,
    GetTicketUseCase,
    ListCommentsUseCase,
    ListTicketsUseCase,
    SummaryUseCase,
)
from backend.app.users.db_models import UserModel
from backend.app.users.usecases import CreateUserUseCase, ListUsersUseCase, PatchUserUseCase
from backend.shared.utils import AppError, Clock, Paginator


class DomainProvider(Provider):
    clock = provide(Clock, scope=Scope.APP)
    passwords = provide(PasswordService, scope=Scope.APP)
    tokens = provide(TokenService, scope=Scope.APP)
    paginator = provide(Paginator, scope=Scope.APP)
    login = provide(LoginUseCase, scope=Scope.REQUEST)
    create_ticket = provide(CreateTicketUseCase, scope=Scope.REQUEST)
    list_tickets = provide(ListTicketsUseCase, scope=Scope.REQUEST)
    get_ticket = provide(GetTicketUseCase, scope=Scope.REQUEST)
    list_comments = provide(ListCommentsUseCase, scope=Scope.REQUEST)
    add_comment = provide(AddCommentUseCase, scope=Scope.REQUEST)
    change_status = provide(ChangeStatusUseCase, scope=Scope.REQUEST)
    summary = provide(SummaryUseCase, scope=Scope.REQUEST)
    list_categories = provide(ListCategoriesUseCase, scope=Scope.REQUEST)
    create_category = provide(CreateCategoryUseCase, scope=Scope.REQUEST)
    patch_category = provide(PatchCategoryUseCase, scope=Scope.REQUEST)
    list_norms = provide(ListNormsUseCase, scope=Scope.REQUEST)
    set_norm = provide(SetNormUseCase, scope=Scope.REQUEST)
    list_users = provide(ListUsersUseCase, scope=Scope.REQUEST)
    create_user = provide(CreateUserUseCase, scope=Scope.REQUEST)
    patch_user = provide(PatchUserUseCase, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    async def current_user(self, request: Request, tokens: TokenService, session: AsyncSession) -> UserModel:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AppError("Требуется вход в систему", status_code=401)
        payload = tokens.decode(token)
        user = await session.scalar(select(UserModel).where(UserModel.login == payload["sub"]))
        if user is None or not user.is_active or user.auth_version != payload["ver"]:
            raise AppError("Требуется повторный вход", status_code=401)
        return user

    @provide(scope=Scope.REQUEST)
    def auth_context(self, user: UserModel) -> AuthContext:
        return AuthContext(login=user.login, role=user.role)
