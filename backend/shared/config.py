import re
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    personal_prefix: str = Field(default="dmitrii_koshevarov", pattern=r"^[a-z][a-z0-9_]{1,39}$")
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "app"
    db_password: str = "local-dev-only"
    db_name: str | None = None
    db_schema: str | None = None
    database_url: str | None = None
    app_name: str = "Служба поддержки"
    jwt_secret: str = Field(min_length=32)
    token_ttl: int = Field(default=3600, ge=60, le=86400)

    @field_validator("db_schema")
    @classmethod
    def validate_schema(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", value):
            raise ValueError("DB_SCHEMA must be a lowercase SQL identifier")
        return value

    @property
    def schema_name(self) -> str:
        return self.db_schema or self.personal_prefix

    @property
    def url(self) -> str | URL:
        return self.database_url or URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name or f"{self.personal_prefix}_helpdesk",
        )

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Settings":
        options: dict[str, Any] = {"_env_file": env_file}
        return cls(**options)
