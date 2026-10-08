from datetime import datetime

from backend.shared.schemas import ReactionDTO
from backend.shared.utils import AppError


class TicketRules:
    @staticmethod
    def reaction(
        created_at: datetime,
        first_reply: datetime | None,
        norm: int,
        as_of: datetime,
        *,
        closed_at: datetime | None = None,
    ) -> ReactionDTO:
        elapsed = max(0.0, ((first_reply or closed_at or as_of) - created_at).total_seconds())
        return ReactionDTO(
            first_staff_reply_at=first_reply,
            elapsed_seconds=elapsed,
            norm_seconds=norm,
            breached=elapsed > norm,
            as_of=as_of,
        )

    @staticmethod
    def validate_transition(current: str, target: str) -> None:
        if current == target:
            return
        if (current, target) not in {("new", "in_progress"), ("in_progress", "closed")}:
            raise AppError("Недопустимый переход статуса", status_code=409)
