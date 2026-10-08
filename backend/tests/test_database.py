import pytest
from httpx import AsyncClient
from sqlalchemy import Column, Integer, MetaData, Table, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.config import Settings
from backend.storage.pg.database import Database


@pytest.mark.integration
async def test_postgres17_and_dishka_request_session(
    db_session: AsyncSession, client: AsyncClient, settings: Settings
) -> None:
    version = await db_session.scalar(select(func.current_setting("server_version_num")))
    assert version is not None
    assert 170000 <= int(version) < 180000
    assert await db_session.scalar(select(func.current_schema())) == settings.schema_name
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200


@pytest.mark.integration
async def test_usecase_commit_stays_inside_test_transaction(db_session: AsyncSession, database: Database) -> None:
    probe = Table("rollback_probe", MetaData(), Column("id", Integer, primary_key=True))
    connection = await db_session.connection()
    await connection.run_sync(probe.create)
    await db_session.execute(insert(probe).values(id=1))
    await db_session.commit()
    assert connection.in_transaction()
    assert await db_session.scalar(select(func.count()).select_from(probe)) == 1
    async with database.session() as other_session:
        assert await other_session.scalar(select(func.to_regclass("rollback_probe"))) is None
