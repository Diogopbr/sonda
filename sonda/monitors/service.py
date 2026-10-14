from typing import Any, Literal

from psycopg import AsyncConnection

from sonda.access.limits import consume_limit
from sonda.access.scope import Scope, with_workspace
from sonda.checks.service import _clear_lease, _clock, _id, _monitor
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.incidents.events import record_event
from sonda.incidents.projections import incident_projection
from sonda.monitors.projections import check_payload, monitor_projection


def _query(*, detail: bool) -> str:
    history = (
        ",COALESCE((SELECT jsonb_agg(to_jsonb(h) ORDER BY h.started_at DESC,h.id) FROM "
        "(SELECT * FROM check_runs r WHERE r.workspace_id=m.workspace_id AND r.monitor_id=m.id "
        "ORDER BY r.started_at DESC,r.id LIMIT 60) h),'[]'::jsonb) AS checks,"
        "COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.confirmed_at DESC,a.id) FROM "
        "(SELECT i2.*,u2.name AS actor_name FROM incidents i2 LEFT JOIN users u2 "
        "ON u2.id=i2.acknowledged_by AND u2.workspace_id=i2.workspace_id "
        "WHERE i2.workspace_id=m.workspace_id AND i2.monitor_id=m.id "
        "ORDER BY i2.confirmed_at DESC,i2.id LIMIT 20) a),'[]'::jsonb) AS incidents "
        if detail
        else " "
    )
    return (
        "SELECT m.*,to_jsonb(c) AS last_check,"
        "to_jsonb(i)||jsonb_build_object('actor_name',u.name) AS active_incident"
        + history
        + "FROM monitors m LEFT JOIN check_runs c ON c.id=m.last_check_id "
        "LEFT JOIN incidents i ON i.workspace_id=m.workspace_id "
        "AND i.monitor_id=m.id AND i.state<>'resolved' "
        "LEFT JOIN users u ON u.id=i.acknowledged_by AND u.workspace_id=i.workspace_id "
    )


async def _get(
    connection: AsyncConnection[dict[str, Any]], scope: Scope, id: str, *, detail: bool = False
) -> dict[str, Any]:
    row = await (
        await connection.execute(
            _query(detail=detail) + "WHERE m.workspace_id=%s AND m.id=%s", (scope.id, id)
        )
    ).fetchone()
    if row is None:
        raise HttpError(404, "NOT_FOUND", "Serviço não encontrado.")
    projection = monitor_projection(row)
    if detail:
        projection["checks"] = [check_payload(check) for check in row["checks"]]
        projection["history_limit"] = 60
        projection["incidents"] = [incident_projection(incident) for incident in row["incidents"]]
        projection["incident_history_limit"] = 20
    return projection


class MonitorService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list(self, scope: Scope) -> list[dict[str, Any]]:
        async with with_workspace(self.db, scope) as connection:
            rows = await (
                await connection.execute(
                    _query(detail=False) + "WHERE m.workspace_id=%s ORDER BY m.name", (scope.id,)
                )
            ).fetchall()
            return [monitor_projection(row) for row in rows]

    async def get(self, scope: Scope, id: str) -> dict[str, Any]:
        async with with_workspace(self.db, scope) as connection:
            return await _get(connection, scope, _id(id), detail=True)

    async def change(
        self,
        scope: Scope,
        id: str,
        expected_version: int,
        *,
        enabled: bool | None = None,
        fixture_mode: Literal["available", "unavailable"] | None = None,
    ) -> dict[str, Any]:
        if (
            type(expected_version) is not int
            or expected_version < 1
            or (enabled is not None and type(enabled) is not bool)
            or fixture_mode not in {None, "available", "unavailable"}
            or (enabled is None and fixture_mode is None)
        ):
            raise HttpError(422, "INPUT_INVALID", "Informe a alteração e a versão atual.")
        id = _id(id)
        async with with_workspace(self.db, scope) as connection:
            row = await _monitor(connection, scope, id)
            if row["version"] != expected_version:
                raise HttpError(
                    409,
                    "VERSION_CONFLICT",
                    "O serviço mudou. Revise os dados atuais.",
                    current=await _get(connection, scope, id),
                )
            if fixture_mode is not None and row["target_kind"] != "fixture":
                raise HttpError(
                    422, "INPUT_INVALID", "Somente a demonstração permite mudar o cenário."
                )
            before = {"enabled": row["enabled"], "fixture_mode": row["fixture_mode"]}
            after = {
                "enabled": enabled if enabled is not None else row["enabled"],
                "fixture_mode": fixture_mode if fixture_mode is not None else row["fixture_mode"],
            }
            if before == after:
                return await _get(connection, scope, id)
            if scope.kind == "demo":
                await consume_limit(connection, f"mutation:visitor:{scope.visitor_id}", 60, 30)
            now = await _clock(connection)
            if row["lease_id"] is not None:
                await connection.execute(
                    "UPDATE check_runs SET state='abandoned',finished_at=%s,"
                    "abandon_reason='MONITOR_CHANGED' "
                    "WHERE id=%s AND state='pending'",
                    (now, row["lease_id"]),
                )
                await _clear_lease(connection, id)
            await connection.execute(
                "UPDATE monitors SET enabled=%s,fixture_mode=%s,version=version+1 WHERE id=%s",
                (after["enabled"], after["fixture_mode"], id),
            )
            await record_event(
                connection, scope, id, "MONITOR_CHANGED", now, {"before": before, "after": after}
            )
            return await _get(connection, scope, id)
