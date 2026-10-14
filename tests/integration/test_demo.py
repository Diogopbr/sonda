import secrets

import pytest

from sonda.access.demo import DemoService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.migrate import migrate


async def test_demo_recovery_keeps_generation_and_deadline_with_four_unmeasured_monitors(
    db: Database,
) -> None:
    await migrate(db)
    token = secrets.token_hex(32)
    service = DemoService(db)
    first = await service.start(token, "203.0.113.11")
    again = await service.start(token, "203.0.113.12")
    assert again == first
    async with db.connection() as connection:
        rows = await (
            await connection.execute(
                "SELECT name,observed_state,failure_streak,success_streak FROM monitors "
                "WHERE workspace_id=%s ORDER BY name",
                (first.scope.id,),
            )
        ).fetchall()
        assert len(rows) == 4
        assert all(row["observed_state"] == "unknown" for row in rows)
        assert all(row["failure_streak"] == row["success_streak"] == 0 for row in rows)
        count = await (await connection.execute("SELECT count(*) AS n FROM visitors")).fetchone()
        assert count and count["n"] == 1


async def test_reset_revokes_generation_keeps_visitor_and_limits_second_reset(db: Database) -> None:
    await migrate(db)
    token = secrets.token_hex(32)
    service = DemoService(db)
    first = await service.start(token, "203.0.113.11")
    second = await service.reset(first.scope, token, "203.0.113.11")
    assert second.scope.id != first.scope.id
    assert second.scope.visitor_id == first.scope.visitor_id
    async with db.connection() as connection:
        old = await (
            await connection.execute(
                "SELECT revoked_at FROM workspaces WHERE id=%s", (first.scope.id,)
            )
        ).fetchone()
        assert old and old["revoked_at"] is not None
    key = f"reset:visitor:{second.scope.visitor_id}"
    for _ in range(3):
        async with db.connection() as connection:
            before = await (
                await connection.execute(
                    "SELECT bucket,hits FROM rate_limits WHERE key=%s ORDER BY bucket DESC LIMIT 1",
                    (key,),
                )
            ).fetchone()
        assert before is not None
        try:
            second = await service.reset(second.scope, token, "203.0.113.11")
        except HttpError as error:
            assert error.status_code == 429
            assert error.retry_after is not None and 1 <= error.retry_after <= 60
            break
        async with db.connection() as connection:
            after = await (
                await connection.execute(
                    "SELECT bucket,hits FROM rate_limits WHERE key=%s ORDER BY bucket DESC LIMIT 1",
                    (key,),
                )
            ).fetchone()
        assert after is not None and after["bucket"] > before["bucket"] and after["hits"] == 1
    else:
        raise AssertionError("Reset limit was never observed")


async def test_reset_checks_visitor_ownership_before_consuming_limits(db: Database) -> None:
    await migrate(db)
    service = DemoService(db)
    first = await service.start(secrets.token_hex(32), "203.0.113.11")
    async with db.connection() as connection:
        before = await (
            await connection.execute("SELECT sum(hits) AS n FROM rate_limits")
        ).fetchone()
    with pytest.raises(HttpError) as caught:
        await service.reset(first.scope, secrets.token_hex(32), "203.0.113.11")
    assert caught.value.status_code == 404
    async with db.connection() as connection:
        after = await (
            await connection.execute("SELECT sum(hits) AS n FROM rate_limits")
        ).fetchone()
    assert before == after
