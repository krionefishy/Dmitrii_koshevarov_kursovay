from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Role = Literal["customer", "support", "admin"]
Status = Literal["new", "in_progress", "closed"]
Login = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
Password = Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]
MAX_ID = 2**63 - 1
EntityID = Annotated[int, Field(ge=1, le=MAX_ID)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def validate_text(cls, value: object) -> object:
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Нулевой символ недопустим")
        return value


class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    has_more: bool


class UserDTO(DTO):
    login: str
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime


class CategoryDTO(DTO):
    id: int
    name: str
    description: str
    is_active: bool


class NormDTO(DTO):
    category_id: int
    response_seconds: int


class TicketDTO(DTO):
    id: int
    author_login: str
    category_id: int
    title: str
    status: Status
    response_norm_seconds: int
    created_at: datetime
    closed_at: datetime | None


class CommentDTO(DTO):
    id: int
    ticket_id: int
    author_login: str
    body: str
    is_staff_reply: bool
    created_at: datetime


class LoginRequest(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    login: Login
    password: Annotated[str, Field(min_length=1, max_length=128)]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserDTO


class CreateUser(Input):
    login: Login
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: Password


class PatchUser(Input):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: Password | None = None


class CreateCategory(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    response_seconds: int = Field(gt=0, le=2_592_000)


class PatchCategory(Input):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class SetNorm(Input):
    response_seconds: int = Field(gt=0, le=2_592_000)


class CreateTicket(Input):
    category_id: EntityID
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class AddComment(Input):
    body: str = Field(min_length=1, max_length=10000)


class SetStatus(Input):
    status: Status


class ReactionDTO(BaseModel):
    first_staff_reply_at: datetime | None
    elapsed_seconds: float
    norm_seconds: int
    breached: bool
    as_of: datetime


class TicketDetail(TicketDTO):
    body: str
    category: CategoryDTO
    author_name: str
    reaction: ReactionDTO


class SummaryRow(BaseModel):
    category_id: int
    category_name: str
    open_count: int = 0
    breached_count: int = 0
    breached_share: float = 0


class SummaryDTO(BaseModel):
    as_of: datetime
    open_count: int
    breached_count: int
    items: list[SummaryRow]
