from sonda.access.sessions import SessionService
from sonda.db import Database
from sonda.migrate import migrate
from tests.integration.test_scope import make_scope


async def test_sessions_survive_restart_and_rotation_revokes_old_cookie(db: Database) -> None:
    scope = await make_scope(db)
    service = SessionService(db)
    first = await service.issue(scope)
    restarted = SessionService(db)
    restored = await restarted.resolve(first.cookie)
    assert restored is not None and restored.scope == scope
    second = await restarted.issue(scope, previous=first.cookie)
    assert second.record.csrf != first.record.csrf
    assert await service.resolve(first.cookie) is None
    assert await service.resolve(second.cookie) == second.record
    assert await service.resolve(second.cookie[:-1] + "z") is None


async def test_revoked_workspace_invalidates_session(db: Database) -> None:
    scope = await make_scope(db)
    service = SessionService(db)
    issued = await service.issue(scope)
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE workspaces SET revoked_at=clock_timestamp() WHERE id=%s", (scope.id,)
        )
    assert await service.resolve(issued.cookie) is None


async def test_anonymous_session_expiry_and_logout(db: Database) -> None:
    await migrate(db)
    service = SessionService(db)
    issued = await service.issue()
    assert issued.record.scope is None
    assert await service.resolve(issued.cookie) == issued.record
    await service.destroy(issued.cookie)
    assert await service.resolve(issued.cookie) is None
    expired = await service.issue()
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (expired.record.digest,),
        )
    assert await service.resolve(expired.cookie) is None


async def test_session_deadline_is_bounded_by_workspace_and_never_extended(db: Database) -> None:
    scope = await make_scope(db)
    async with db.transaction() as connection:
        row = await (
            await connection.execute(
                "UPDATE workspaces SET expires_at=clock_timestamp()+interval '10 minutes' "
                "WHERE id=%s RETURNING expires_at",
                (scope.id,),
            )
        ).fetchone()
    assert row is not None
    service = SessionService(db)
    issued = await service.issue(scope)
    assert issued.record.expires_at == row["expires_at"]
    assert await service.resolve(issued.cookie) == issued.record
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE workspaces SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (scope.id,),
        )
    assert await service.resolve(issued.cookie) is None


async def test_payload_cannot_select_another_workspace(db: Database) -> None:
    scope = await make_scope(db)
    service = SessionService(db)
    issued = await service.issue(scope)
    async with db.transaction() as connection:
        await connection.execute(
            'UPDATE sessions SET payload=payload || \'{"kind":"normal",'
            '"workspace_id":"forged","actor_id":"forged"}\'::jsonb WHERE id=%s',
            (issued.record.digest,),
        )
    assert await service.resolve(issued.cookie) == issued.record
