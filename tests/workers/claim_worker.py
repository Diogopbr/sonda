import asyncio
import json
import os
import sys
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from sonda.access.limits import lock_key
from sonda.access.scope import Scope, with_workspace
from sonda.checks import service
from sonda.checks.service import CheckService
from sonda.config import Settings
from sonda.db import Database
from sonda.http.errors import HttpError


def emit(event: str, **values) -> None:
    print(json.dumps({"event": event, **values}), flush=True)


async def release() -> None:
    if not await asyncio.to_thread(sys.stdin.readline):
        raise RuntimeError("Parent closed the claim barrier")


async def main() -> None:
    settings = Settings.from_env(os.environ)
    url = urlsplit(settings.database_url)
    if (
        settings.environment != "test"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.path != "/sonda_test"
        or url.username != "sonda_test"
    ):
        raise RuntimeError("Claim worker requires isolated local test database")
    schema, workspace_id, user_id, kind, visitor_id, monitor_id, key, mode = sys.argv[1:]
    db = Database(settings, schema)
    scope = Scope(workspace_id, user_id, kind, None if visitor_id == "none" else visitor_id)
    if mode == "unsafe":
        async with with_workspace(db, scope) as connection:
            monitor = await (
                await connection.execute(
                    "SELECT * FROM monitors WHERE id=%s",
                    (monitor_id,),
                )
            ).fetchone()
            assert monitor is not None and monitor["lease_id"] is None
            emit("snapshot", pid=connection.info.backend_pid)
            await release()
            now = await service._clock(connection)
            id, token = uuid4(), uuid4()
            await connection.execute(
                "INSERT INTO check_runs(id,workspace_id,monitor_id,actor_id,client_key,origin,"
                "lease_token,monitor_version,started_at,lease_until) "
                "VALUES(%s,%s,%s,%s,%s,'manual',%s,%s,%s,%s)",
                (
                    id,
                    workspace_id,
                    monitor_id,
                    user_id,
                    key,
                    token,
                    monitor["version"],
                    now,
                    now + timedelta(seconds=30),
                ),
            )
            await connection.execute(
                "UPDATE monitors SET lease_id=%s,lease_token=%s,lease_until=%s WHERE id=%s",
                (id, token, now + timedelta(seconds=30), monitor_id),
            )
        emit("result", accepted=True, id=str(id))
        return
    original = service._monitor

    async def observed(connection, scope, monitor_id):
        if mode == "wait":
            emit("waiting", pid=connection.info.backend_pid)
        monitor = await original(connection, scope, monitor_id)
        if mode == "quota-wait":
            emit("waiting", pid=connection.info.backend_pid)
        if mode in {"hold", "quota-hold"}:
            if mode == "quota-hold":
                await lock_key(connection, f"check:quota:{scope.id}")
            emit("locked", pid=connection.info.backend_pid)
            await release()
        return monitor

    service._monitor = observed
    if mode == "key-wait":
        original_key = service.lock_key

        async def observed_key(connection, key):
            if key.startswith("check:key:"):
                emit("waiting", pid=connection.info.backend_pid)
            await original_key(connection, key)

        service.lock_key = observed_key
    try:
        claim = await CheckService(db).claim(scope, monitor_id, key)
        emit("result", accepted=True, id=claim.id, started_at=claim.claimed_at.isoformat())
    except HttpError as error:
        emit(
            "result",
            accepted=False,
            status=error.status_code,
            code=error.code,
            retry_after=error.retry_after,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    except Exception as error:
        emit("worker-error", type=type(error).__name__)
        raise SystemExit(1) from None
