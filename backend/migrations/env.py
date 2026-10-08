import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateSchema

from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.app.tickets.db_models import CommentModel, TicketModel
from backend.app.users.db_models import UserModel
from backend.shared.config import Settings
from backend.storage.pg.database import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
settings = Settings.load()
models = (CategoryModel, ResponseNormModel, CommentModel, TicketModel, UserModel)
target_metadata = Base.metadata


def configure(connection: Connection | None = None) -> None:
    context.configure(
        connection=connection,
        url=settings.url if connection is None else None,
        target_metadata=target_metadata,
        compare_type=True,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    configure()
    context.execute(CreateSchema(settings.schema_name, if_not_exists=True))
    context.execute(f'SET search_path TO "{settings.schema_name}"')
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:

    connection.execute(CreateSchema(settings.schema_name, if_not_exists=True))
    connection.exec_driver_sql(f'SET search_path TO "{settings.schema_name}"')
    connection.commit()
    connection.dialect.default_schema_name = settings.schema_name
    configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
