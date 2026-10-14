from dataclasses import replace

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app
from sonda.migrate import migrate


async def test_readiness_requires_current_schema_migrations_and_reports_no_credentials(
    db: Database,
) -> None:
    app = create_app(db.settings, db)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=db.settings.app_url
    ) as client:
        before = await client.get("/health/ready")
        assert before.status_code == 503
        await migrate(db)
        after = await client.get("/health/ready")
        assert after.status_code == 200
        assert after.json() == {"status": "ready"}
        assert db.settings.database_url not in after.text
        assert after.headers["x-content-type-options"] == "nosniff"


async def test_migration_is_idempotent_and_rejects_changed_applied_content(db: Database) -> None:
    await migrate(db)
    await migrate(db)
    async with db.transaction() as connection:
        rows = await (await connection.execute("SELECT version FROM schema_migrations")).fetchall()
        assert len(rows) == 1
        await connection.execute("UPDATE schema_migrations SET hash='tampered'")
    import pytest

    with pytest.raises(ValueError, match="Applied migration changed"):
        await migrate(db)


async def test_database_connection_failure_only_exposes_unavailable(db: Database) -> None:
    broken_settings = replace(
        db.settings, database_url="postgresql://fixture:password@127.0.0.1:1/sonda_test"
    )
    app = create_app(broken_settings, Database(broken_settings))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=db.settings.app_url
    ) as client:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert "password" not in response.text
