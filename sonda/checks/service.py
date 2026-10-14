from datetime import datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from sonda.access.limits import consume_limit, lock_key
from sonda.access.scope import Scope, with_workspace
from sonda.checks.models import CheckProjection, Claim, check_projection, claim_projection
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.targets.fetcher import FetchOutcome


def _id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HttpError(404, "NOT_FOUND", "Registro não encontrado.") from None


async def _clock(connection: AsyncConnection[dict[str, Any]]) -> datetime:
    row = await (await connection.execute("SELECT clock_timestamp() AS now")).fetchone()
    assert row is not None
    return cast(datetime, row["now"])


async def _monitor(
    connection: AsyncConnection[dict[str, Any]], scope: Scope, monitor_id: str
) -> dict[str, Any]:
    row = await (
        await connection.execute(
            "SELECT * FROM monitors WHERE workspace_id=%s AND id=%s FOR UPDATE",
            (scope.id, monitor_id),
        )
    ).fetchone()
    if row is None:
        raise HttpError(404, "NOT_FOUND", "Serviço não encontrado.")
    return row


async def _clear_lease(connection: AsyncConnection[dict[str, Any]], monitor_id: str) -> None:
    await connection.execute(
        "UPDATE monitors SET lease_id=NULL,lease_token=NULL,lease_until=NULL WHERE id=%s",
        (monitor_id,),
    )


class CheckService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def claim(
        self,
        scope: Scope,
        monitor_id: str,
        key: str,
        origin: Literal["manual", "runner"] = "manual",
    ) -> Claim:
        monitor_id, key = _id(monitor_id), _id(key)
        if origin == "runner" and scope.kind != "normal":
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado.")
        async with with_workspace(self.db, scope) as connection:
            await lock_key(connection, f"check:key:{scope.id}:{key}")
            monitor = await _monitor(connection, scope, monitor_id)
            now = await _clock(connection)
            if monitor["lease_id"] is not None:
                active = await (
                    await connection.execute(
                        "SELECT monitor_version FROM check_runs WHERE id=%s",
                        (monitor["lease_id"],),
                    )
                ).fetchone()
                changed = (
                    active is None
                    or active["monitor_version"] != monitor["version"]
                    or not monitor["enabled"]
                )
                if changed or monitor["lease_until"] <= now:
                    await connection.execute(
                        "UPDATE check_runs SET state='abandoned',finished_at=%s,abandon_reason=%s "
                        "WHERE id=%s AND state='pending'",
                        (
                            now,
                            "MONITOR_CHANGED" if changed else "LEASE_EXPIRED",
                            monitor["lease_id"],
                        ),
                    )
                    await _clear_lease(connection, monitor_id)
                    monitor["lease_id"] = None
            previous = await (
                await connection.execute(
                    "SELECT * FROM check_runs WHERE workspace_id=%s AND client_key=%s",
                    (scope.id, key),
                )
            ).fetchone()
            if previous is not None:
                if str(previous["monitor_id"]) != monitor_id:
                    raise HttpError(
                        409, "IDEMPOTENCY_CONFLICT", "Este comando pertence a outro serviço."
                    )
                return claim_projection(previous, replayed=True)
            if not monitor["enabled"]:
                raise HttpError(409, "MONITOR_PAUSED", "O serviço está pausado.")
            if monitor["lease_id"] is not None:
                raise HttpError(409, "CHECK_RUNNING", "Uma verificação já está em andamento.")
            if scope.kind == "demo":
                await lock_key(connection, f"check:quota:{scope.id}")
                deadline = await (
                    await connection.execute(
                        "SELECT greatest(1,ceil(extract(epoch FROM "
                        "expires_at-clock_timestamp())))::int "
                        "AS retry_after FROM workspaces WHERE id=%s "
                        "AND expires_at>clock_timestamp() AND revoked_at IS NULL",
                        (scope.id,),
                    )
                ).fetchone()
                if deadline is None:
                    raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
                count = await (
                    await connection.execute(
                        "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                        (scope.id,),
                    )
                ).fetchone()
                assert count is not None
                if count["n"] >= 60:
                    raise HttpError(
                        429,
                        "DEMO_QUOTA",
                        "Esta demonstração atingiu 60 verificações.",
                        retry_after=deadline["retry_after"],
                    )
                await consume_limit(connection, f"check:visitor:{scope.visitor_id}", 60, 6)
            now = await _clock(connection)
            row = await (
                await connection.execute(
                    "INSERT INTO check_runs(id,workspace_id,monitor_id,actor_id,client_key,origin,"
                    "lease_token,monitor_version,started_at,lease_until) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                    (
                        uuid4(),
                        scope.id,
                        monitor_id,
                        scope.user_id,
                        key,
                        origin,
                        uuid4(),
                        monitor["version"],
                        now,
                        now + timedelta(seconds=30),
                    ),
                )
            ).fetchone()
            assert row is not None
            await connection.execute(
                "UPDATE monitors SET lease_id=%s,lease_token=%s,lease_until=%s,"
                "next_due_at=%s WHERE id=%s",
                (
                    row["id"],
                    row["lease_token"],
                    row["lease_until"],
                    now + timedelta(seconds=monitor["interval_seconds"]),
                    monitor_id,
                ),
            )
            return claim_projection(row, replayed=False)

    async def finish(self, scope: Scope, claim: Claim, outcome: FetchOutcome) -> CheckProjection:
        if claim.workspace_id != scope.id:
            raise HttpError(404, "NOT_FOUND", "Verificação não encontrada.")
        async with with_workspace(self.db, scope) as connection:
            monitor = await _monitor(connection, scope, _id(claim.monitor_id))
            now = await _clock(connection)
            row = await (
                await connection.execute(
                    "SELECT * FROM check_runs WHERE workspace_id=%s AND monitor_id=%s AND id=%s",
                    (scope.id, claim.monitor_id, _id(claim.id)),
                )
            ).fetchone()
            if row is None:
                raise HttpError(404, "NOT_FOUND", "Verificação não encontrada.")
            if (
                row["state"] != "pending"
                or str(row["actor_id"]) != scope.user_id
                or str(row["lease_token"]) != claim.lease_token
                or str(monitor["lease_id"]) != claim.id
                or str(monitor["lease_token"]) != claim.lease_token
                or monitor["lease_until"] <= now
                or row["lease_until"] <= now
                or not monitor["enabled"]
                or monitor["version"] != row["monitor_version"]
            ):
                raise HttpError(410, "CHECK_SUPERSEDED", "Esta verificação perdeu a validade.")
            finished = await (
                await connection.execute(
                    "UPDATE check_runs SET state='finished',finished_at=%s,status_code=%s,"
                    "duration_ms=%s,error_code=%s WHERE id=%s RETURNING *",
                    (now, outcome.status_code, outcome.duration_ms, outcome.error_code, claim.id),
                )
            ).fetchone()
            assert finished is not None
            await _clear_lease(connection, claim.monitor_id)
            return check_projection(finished)

    async def get_check(self, scope: Scope, check_id: str) -> CheckProjection:
        async with with_workspace(self.db, scope) as connection:
            row = await (
                await connection.execute(
                    "SELECT * FROM check_runs WHERE workspace_id=%s AND id=%s",
                    (scope.id, _id(check_id)),
                )
            ).fetchone()
            if row is None:
                raise HttpError(404, "NOT_FOUND", "Verificação não encontrada.")
            return check_projection(row)
