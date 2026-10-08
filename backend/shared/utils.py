import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from backend.shared.config import Settings
from backend.shared.schemas import Page


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class AppError(Exception):
    def __init__(self, detail: str, *, status_code: int) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class Paginator:
    def __init__(self, settings: Settings) -> None:
        self.secret = settings.jwt_secret.encode()

    def encode(self, payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        sig = hmac.digest(self.secret, raw, hashlib.sha256)
        return base64.urlsafe_b64encode(sig + raw).rstrip(b"=").decode()

    def decode(self, cursor: str, scope: dict, value_type: type) -> dict:
        try:
            if len(cursor) > 2048:
                raise ValueError
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            sig, data = raw[:32], raw[32:]
            if not hmac.compare_digest(sig, hmac.digest(self.secret, data, hashlib.sha256)):
                raise ValueError
            payload = json.loads(data)
            if payload["v"] != 1 or payload["scope"] != scope:
                raise ValueError
            if type(payload["last"]) is not value_type or type(payload["max"]) is not value_type:
                raise ValueError
            return payload
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise AppError("Неверный курсор или изменён фильтр", status_code=400) from exc

    async def page(
        self,
        session: AsyncSession,
        statement: Select,
        key: InstrumentedAttribute,
        key_name: str,
        dto: type[BaseModel],
        limit: int,
        cursor: str | None,
        scope: dict,
        ascending: bool = False,
    ) -> Page:
        if not 1 <= limit <= 100:
            raise AppError("Размер страницы должен быть от 1 до 100", status_code=400)
        value_type = str if key_name == "login" else int
        scope = {**scope, "limit": limit, "ascending": ascending}
        maximum: Any = None
        if cursor:
            payload = self.decode(cursor, scope, value_type)
            maximum = payload["max"]
            statement = statement.where(key <= maximum, key > payload["last"] if ascending else key < payload["last"])
        elif ascending:
            maximum = await session.scalar(statement.with_only_columns(key).order_by(key.desc()).limit(1))
            if maximum is not None:
                statement = statement.where(key <= maximum)
        rows = list(
            (await session.scalars(statement.order_by(key.asc() if ascending else key.desc()).limit(limit + 1))).all()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        if maximum is None and rows:
            maximum = getattr(rows[0], key_name)
        next_cursor = (
            self.encode({"v": 1, "last": getattr(rows[-1], key_name), "max": maximum, "scope": scope}) if more else None
        )
        return Page(items=[dto.model_validate(row) for row in rows], next_cursor=next_cursor, has_more=more)
