from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import AuthContext
from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.tickets.rules import TicketRules
from backend.app.users.db_models import UserModel
from backend.shared.schemas import (
    AddComment,
    CategoryDTO,
    CommentDTO,
    CreateTicket,
    Page,
    SetStatus,
    SummaryDTO,
    SummaryRow,
    TicketDetail,
    TicketDTO,
)
from backend.shared.utils import AppError, Clock, Paginator


class TicketUseCase:
    def __init__(self, session: AsyncSession, clock: Clock, paginator: Paginator) -> None:
        self.session = session
        self.clock = clock
        self.paginator = paginator

    async def ticket(self, ticket_id: int, ctx: AuthContext, *, lock: bool = False) -> TicketModel:
        ctx.require("customer", "support")
        statement = select(TicketModel).where(TicketModel.id == ticket_id)
        if ctx.role == "customer":
            statement = statement.where(TicketModel.author_login == ctx.login)
        if lock:
            statement = statement.with_for_update()
        result = await self.session.scalar(statement)
        if result is None:
            raise AppError("Заявка не найдена", status_code=404)
        return result


class CreateTicketUseCase(TicketUseCase):
    async def execute(self, data: CreateTicket, ctx: AuthContext) -> TicketDTO:
        ctx.require("customer")

        category = await self.session.scalar(
            select(CategoryModel).where(CategoryModel.id == data.category_id).with_for_update()
        )
        if category is None or not category.is_active:
            raise AppError("Категория недоступна", status_code=404)
        norm = await self.session.scalar(select(ResponseNormModel).where(ResponseNormModel.category_id == category.id))
        if norm is None:
            raise AppError("Для категории не задан норматив", status_code=409)
        ticket = (
            await self.session.execute(
                insert(TicketModel)
                .values(
                    **data.model_dump(),
                    author_login=ctx.login,
                    status="new",
                    response_norm_seconds=norm.response_seconds,
                    created_at=self.clock.now(),
                )
                .returning(TicketModel)
            )
        ).scalar_one()
        await self.session.commit()
        return TicketDTO.model_validate(ticket)


class ListTicketsUseCase(TicketUseCase):
    async def execute(
        self, ctx: AuthContext, limit: int, cursor: str | None, category_id: int | None, status: str | None
    ) -> Page[TicketDTO]:
        ctx.require("customer", "support")
        statement = select(TicketModel)
        if ctx.role == "customer":
            statement = statement.where(TicketModel.author_login == ctx.login)
        if category_id is not None:
            statement = statement.where(TicketModel.category_id == category_id)
        if status is not None:
            statement = statement.where(TicketModel.status == status)
        return await self.paginator.page(
            self.session,
            statement,
            TicketModel.id,
            "id",
            TicketDTO,
            limit,
            cursor,
            {"resource": "tickets", "user": ctx.login, "role": ctx.role, "category": category_id, "status": status},
        )


class GetTicketUseCase(TicketUseCase):
    async def execute(self, ticket_id: int, ctx: AuthContext) -> TicketDetail:
        ticket = await self.ticket(ticket_id, ctx)
        category = await self.session.get(CategoryModel, ticket.category_id)
        author = await self.session.get(UserModel, ticket.author_login)
        first_reply = await self.session.scalar(
            select(func.min(CommentModel.created_at)).where(
                CommentModel.ticket_id == ticket_id, CommentModel.is_staff_reply.is_(True)
            )
        )
        assert category is not None and author is not None
        return TicketDetail(
            **TicketDTO.model_validate(ticket).model_dump(),
            body=ticket.body,
            category=CategoryDTO.model_validate(category),
            author_name=author.display_name,
            reaction=TicketRules.reaction(
                ticket.created_at,
                first_reply,
                ticket.response_norm_seconds,
                self.clock.now(),
                closed_at=ticket.closed_at,
            ),
        )


class ListCommentsUseCase(TicketUseCase):
    async def execute(
        self, ticket_id: int, ctx: AuthContext, limit: int, cursor: str | None, newest_first: bool = False
    ) -> Page[CommentDTO]:
        await self.ticket(ticket_id, ctx)
        statement = select(CommentModel).where(CommentModel.ticket_id == ticket_id)
        return await self.paginator.page(
            self.session,
            statement,
            CommentModel.id,
            "id",
            CommentDTO,
            limit,
            cursor,
            {"resource": "comments", "ticket": ticket_id, "user": ctx.login},
            ascending=not newest_first,
        )


class AddCommentUseCase(TicketUseCase):
    async def execute(self, ticket_id: int, data: AddComment, ctx: AuthContext) -> CommentDTO:
        ticket = await self.ticket(ticket_id, ctx, lock=True)
        if ticket.status == "closed":
            raise AppError("Заявка уже закрыта", status_code=409)
        comment = (
            await self.session.execute(
                insert(CommentModel)
                .values(
                    ticket_id=ticket_id,
                    author_login=ctx.login,
                    body=data.body,
                    is_staff_reply=ctx.role == "support",
                    created_at=self.clock.now(),
                )
                .returning(CommentModel)
            )
        ).scalar_one()
        await self.session.commit()
        return CommentDTO.model_validate(comment)


class ChangeStatusUseCase(TicketUseCase):
    async def execute(self, ticket_id: int, data: SetStatus, ctx: AuthContext) -> TicketDTO:
        ctx.require("support")
        ticket = await self.ticket(ticket_id, ctx, lock=True)
        TicketRules.validate_transition(ticket.status, data.status)
        if ticket.status != data.status:
            ticket = (
                await self.session.execute(
                    update(TicketModel)
                    .where(TicketModel.id == ticket_id)
                    .values(
                        status=data.status,
                        closed_at=self.clock.now() if data.status == "closed" else None,
                    )
                    .returning(TicketModel)
                )
            ).scalar_one()
        await self.session.commit()
        return TicketDTO.model_validate(ticket)


class SummaryUseCase(TicketUseCase):
    async def execute(self, ctx: AuthContext) -> SummaryDTO:
        ctx.require("support", "admin")
        as_of = self.clock.now()
        first_replies = (
            select(CommentModel.ticket_id, func.min(CommentModel.created_at).label("first_reply"))
            .where(CommentModel.is_staff_reply.is_(True))
            .group_by(CommentModel.ticket_id)
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(CategoryModel, TicketModel, first_replies.c.first_reply)
                .select_from(CategoryModel)
                .outerjoin(
                    TicketModel, and_(TicketModel.category_id == CategoryModel.id, TicketModel.status != "closed")
                )
                .outerjoin(first_replies, first_replies.c.ticket_id == TicketModel.id)
                .order_by(CategoryModel.id)
            )
        ).all()

        totals: dict[int, SummaryRow] = {}
        for category, ticket, first_reply in rows:
            if category.id not in totals:
                totals[category.id] = SummaryRow(category_id=category.id, category_name=category.name)
            if ticket is None:
                continue
            row = totals[category.id]
            row.open_count += 1
            row.breached_count += int(
                TicketRules.reaction(ticket.created_at, first_reply, ticket.response_norm_seconds, as_of).breached
            )
        for row in totals.values():
            row.breached_share = row.breached_count / row.open_count if row.open_count else 0
        return SummaryDTO(
            as_of=as_of,
            open_count=sum(r.open_count for r in totals.values()),
            breached_count=sum(r.breached_count for r in totals.values()),
            items=list(totals.values()),
        )
