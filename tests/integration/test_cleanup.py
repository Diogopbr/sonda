import asyncio
from uuid import uuid4

import pytest

from sonda.access.cleanup import collect_expired
from sonda.access.normal import Credentials, install_normal
from sonda.db import Database
from sonda.migrate import migrate
from tests.integration.test_scope import make_scope


async def test_cleanup_skips_active_workspace_lock_and_preserves_normal(db: Database) -> None:
    scope = await make_scope(db)
    normal = await install_normal(
        db,
        Credentials(
            email="operador@example.com",
            name="Operador",
            password="senha longa de teste",
        ),
    )
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE workspaces SET revoked_at=clock_timestamp() WHERE id=%s",
            (scope.id,),
        )
        extra = str(uuid4())
        await connection.execute(
            "INSERT INTO workspaces(id,kind,visitor_id,expires_at) "
            "VALUES(%s,'demo',%s,clock_timestamp()-interval '1 second')",
            (extra, scope.visitor_id),
        )
    async with db.transaction() as locked:
        await locked.execute("SELECT id FROM workspaces WHERE id=%s FOR SHARE", (scope.id,))
        report = await asyncio.wait_for(collect_expired(db, throttled=False), timeout=2)
        assert report.workspaces == 1
        assert await (
            await locked.execute("SELECT 1 FROM workspaces WHERE id=%s", (scope.id,))
        ).fetchone()
    assert (await collect_expired(db, throttled=False)).workspaces == 1
    async with db.connection() as connection:
        assert await (
            await connection.execute("SELECT 1 FROM workspaces WHERE id=%s", (normal.id,))
        ).fetchone()


async def test_cleanup_batch_and_database_maintenance_throttle(db: Database) -> None:
    scope = await make_scope(db)
    async with db.transaction() as connection:
        for _ in range(5):
            await connection.execute(
                "INSERT INTO workspaces(id,kind,visitor_id,expires_at) "
                "VALUES(%s,'demo',%s,clock_timestamp()-interval '1 second')",
                (uuid4(), scope.visitor_id),
            )
    first = await collect_expired(db, batch=2)
    assert first.workspaces == 2 and not first.skipped
    assert (await collect_expired(db, batch=2)).skipped
    assert (await collect_expired(db, batch=2, throttled=False)).workspaces == 2
    assert (await collect_expired(db, batch=2, throttled=False)).workspaces == 1
    for invalid in [0, 1001]:
        with pytest.raises(ValueError):
            await collect_expired(db, batch=invalid)


async def test_cleanup_removes_only_expired_sessions_and_limits(db: Database) -> None:
    await migrate(db)
    async with db.transaction() as connection:
        for expired in [False, True]:
            expression = (
                "clock_timestamp()-interval '1 second'"
                if expired
                else "clock_timestamp()+interval '1 hour'"
            )
            await connection.execute(
                "INSERT INTO sessions(id,payload,expires_at) VALUES(%s,'{}'," + expression + ")",
                (uuid4().hex * 2,),
            )
            await connection.execute(
                "INSERT INTO rate_limits(key,bucket,hits,expires_at) "
                "VALUES(%s,clock_timestamp(),1," + expression + ")",
                (str(uuid4()),),
            )
    report = await collect_expired(db, throttled=False)
    assert report.sessions == 1 and report.limits == 1
    async with db.connection() as connection:
        assert (await (await connection.execute("SELECT count(*) AS n FROM sessions")).fetchone())[
            "n"
        ] == 1
        assert (
            await (await connection.execute("SELECT count(*) AS n FROM rate_limits")).fetchone()
        )["n"] == 1
