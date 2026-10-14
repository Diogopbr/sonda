from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from sonda.access.scope import Scope, with_workspace
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.migrate import migrate


async def make_scope(db: Database) -> Scope:
    await migrate(db)
    scope = Scope(str(uuid4()), str(uuid4()), "demo", str(uuid4()))
    async with db.transaction() as connection:
        await connection.execute(
            "INSERT INTO visitors(id,token_hash) VALUES(%s,%s)", (scope.visitor_id, uuid4().hex * 2)
        )
        await connection.execute(
            "INSERT INTO workspaces(id,kind,visitor_id,expires_at) "
            "VALUES(%s,'demo',%s,clock_timestamp()+interval '24 hours')",
            (scope.id, scope.visitor_id),
        )
        await connection.execute(
            "INSERT INTO users(id,workspace_id,email,name,password_hash) "
            "VALUES(%s,%s,'visitante@demo.invalid','Visitante','disabled')",
            (scope.user_id, scope.id),
        )
    return scope


async def test_scope_is_immutable_and_actor_and_kind_are_verified(db: Database) -> None:
    scope = await make_scope(db)
    with pytest.raises(FrozenInstanceError):
        scope.user_id = str(uuid4())  # type: ignore[misc]
    for forged in [replace(scope, user_id=str(uuid4())), replace(scope, kind="normal")]:
        with pytest.raises(HttpError) as caught:
            async with with_workspace(db, forged):
                pass
        assert caught.value.status_code == 404


async def test_precommit_expiry_reverts_all_work(db: Database) -> None:
    scope = await make_scope(db)
    added = str(uuid4())
    with pytest.raises(HttpError) as caught:
        async with with_workspace(db, scope) as connection:
            await connection.execute(
                "INSERT INTO users(id,workspace_id,email,name,password_hash) "
                "VALUES(%s,%s,'rollback@demo.invalid','Rollback','disabled')",
                (added, scope.id),
            )
            await connection.execute(
                "UPDATE workspaces SET expires_at=clock_timestamp()-interval '1 second' "
                "WHERE id=%s",
                (scope.id,),
            )
    assert caught.value.status_code == 404
    async with db.connection() as connection:
        assert not await (
            await connection.execute("SELECT 1 FROM users WHERE id=%s", (added,))
        ).fetchone()


async def test_failed_callback_reverts_writes(db: Database) -> None:
    scope = await make_scope(db)
    added = str(uuid4())
    with pytest.raises(RuntimeError, match="fixture failure"):
        async with with_workspace(db, scope) as connection:
            await connection.execute(
                "INSERT INTO users(id,workspace_id,email,name,password_hash) "
                "VALUES(%s,%s,'rollback@demo.invalid','Rollback','disabled')",
                (added, scope.id),
            )
            raise RuntimeError("fixture failure")
    async with db.connection() as connection:
        assert not await (
            await connection.execute("SELECT 1 FROM users WHERE id=%s", (added,))
        ).fetchone()
