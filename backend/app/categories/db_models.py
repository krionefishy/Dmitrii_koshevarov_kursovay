from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Identity, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.pg.database import Base


class CategoryModel(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ResponseNormModel(Base):
    __tablename__ = "response_norms"
    __table_args__ = (CheckConstraint("response_seconds > 0", name="positive_seconds"),)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), primary_key=True)
    response_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
