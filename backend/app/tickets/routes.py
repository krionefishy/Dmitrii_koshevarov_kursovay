from typing import Annotated

from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get, patch, post
from litestar.params import QueryParameter

from backend.app.api.parameters import Cursor, Limit, PathID
from backend.app.auth.services import AuthContext
from backend.app.tickets.usecases import (
    AddCommentUseCase,
    ChangeStatusUseCase,
    CreateTicketUseCase,
    GetTicketUseCase,
    ListCommentsUseCase,
    ListTicketsUseCase,
    SummaryUseCase,
)
from backend.shared.schemas import (
    MAX_ID,
    AddComment,
    CommentDTO,
    CreateTicket,
    Page,
    SetStatus,
    Status,
    SummaryDTO,
    TicketDetail,
    TicketDTO,
)


class TicketsController(Controller):
    path = ""

    @post("/tickets")
    @inject
    async def create_ticket(
        self, data: CreateTicket, ctx: FromDishka[AuthContext], usecase: FromDishka[CreateTicketUseCase]
    ) -> TicketDTO:
        return await usecase.execute(data, ctx)

    @get("/tickets")
    @inject
    async def list_tickets(
        self,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListTicketsUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
        category_id: Annotated[int | None, QueryParameter(ge=1, le=MAX_ID)] = None,
        status: Annotated[Status | None, QueryParameter()] = None,
    ) -> Page[TicketDTO]:
        return await usecase.execute(ctx, limit, cursor, category_id, status)

    @get("/tickets/{ticket_id:int}")
    @inject
    async def get_ticket(
        self, ticket_id: PathID, ctx: FromDishka[AuthContext], usecase: FromDishka[GetTicketUseCase]
    ) -> TicketDetail:
        return await usecase.execute(ticket_id, ctx)

    @get("/tickets/{ticket_id:int}/comments")
    @inject
    async def list_comments(
        self,
        ticket_id: PathID,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListCommentsUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
        newest_first: Annotated[bool, QueryParameter()] = False,
    ) -> Page[CommentDTO]:
        return await usecase.execute(ticket_id, ctx, limit, cursor, newest_first)

    @post("/tickets/{ticket_id:int}/comments")
    @inject
    async def add_comment(
        self, ticket_id: PathID, data: AddComment, ctx: FromDishka[AuthContext], usecase: FromDishka[AddCommentUseCase]
    ) -> CommentDTO:
        return await usecase.execute(ticket_id, data, ctx)

    @patch("/tickets/{ticket_id:int}/status")
    @inject
    async def change_status(
        self, ticket_id: PathID, data: SetStatus, ctx: FromDishka[AuthContext], usecase: FromDishka[ChangeStatusUseCase]
    ) -> TicketDTO:
        return await usecase.execute(ticket_id, data, ctx)

    @get("/summary")
    @inject
    async def summary(self, ctx: FromDishka[AuthContext], usecase: FromDishka[SummaryUseCase]) -> SummaryDTO:
        return await usecase.execute(ctx)
