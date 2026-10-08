from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.pg.database import Base


class TicketModel(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('new', 'in_progress', 'closed')", name="ticket_status"),
        CheckConstraint("response_norm_seconds > 0", name="positive_norm"),
        CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name="closed_at_status"),
        CheckConstraint("closed_at IS NULL OR closed_at >= created_at", name="closed_at_order"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    author_login: Mapped[str] = mapped_column(ForeignKey("users.login", ondelete="RESTRICT"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    response_norm_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommentModel(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False)
    author_login: Mapped[str] = mapped_column(ForeignKey("users.login", ondelete="RESTRICT"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_staff_reply: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
