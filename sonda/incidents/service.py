from typing import Any

from psycopg import AsyncConnection

from sonda.access.limits import consume_limit
from sonda.access.scope import Scope, with_workspace
from sonda.checks.service import _clock, _id, _monitor
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.incidents.events import record_event
from sonda.incidents.projections import incident_projection
from sonda.monitors.projections import check_payload


async def _incident(
    connection: AsyncConnection[dict[str, Any]], scope: Scope, id: str
) -> dict[str, Any]:
    row = await (
        await connection.execute(
            "SELECT i.*,u.name AS actor_name,to_jsonb(f) AS first_failure_check,"
            "to_jsonb(c) AS confirmation_check,to_jsonb(r) AS resolution_check,"
            "COALESCE((SELECT jsonb_agg(to_jsonb(e)||jsonb_build_object('actor_name',a.name) "
            "ORDER BY e.occurred_at,e.id) FROM events e JOIN users a ON a.id=e.actor_id "
            "WHERE e.workspace_id=i.workspace_id AND e.incident_id=i.id),'[]'::jsonb) AS events "
            "FROM incidents i LEFT JOIN users u "
            "ON u.id=i.acknowledged_by AND u.workspace_id=i.workspace_id "
            "JOIN check_runs f ON f.id=i.first_failure_check_id "
            "JOIN check_runs c ON c.id=i.confirmation_check_id "
            "LEFT JOIN check_runs r ON r.id=i.resolution_check_id "
            "WHERE i.workspace_id=%s AND i.id=%s",
            (scope.id, id),
        )
    ).fetchone()
    if row is None:
        raise HttpError(404, "NOT_FOUND", "Incidente não encontrado.")
    return row


class IncidentService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, scope: Scope, id: str) -> dict[str, Any]:
        async with with_workspace(self.db, scope) as connection:
            row = await _incident(connection, scope, _id(id))
            result = incident_projection(row)
            result["evidence"] = {
                "first_failure": check_payload(row["first_failure_check"]),
                "confirmation": check_payload(row["confirmation_check"]),
                "resolution": check_payload(row["resolution_check"])
                if row["resolution_check"]
                else None,
            }
            result["events"] = [
                {
                    "id": event["id"],
                    "type": event["type"],
                    "occurred_at": event["occurred_at"],
                    "payload": event["payload"],
                    "actor": {"id": event["actor_id"], "name": event["actor_name"]},
                }
                for event in row["events"]
            ]
            return result

    async def acknowledge(
        self, scope: Scope, id: str, reason: str, expected_version: int
    ) -> dict[str, Any]:
        reason = reason.replace("\r\n", "\n").strip()
        if (
            not 3 <= len(reason) <= 500
            or any(ord(char) < 32 and char != "\n" for char in reason)
            or type(expected_version) is not int
            or expected_version < 1
        ):
            raise HttpError(
                422,
                "INPUT_INVALID",
                "Informe um comentário de 3 a 500 caracteres e a versão atual.",
            )
        async with with_workspace(self.db, scope) as connection:
            row = await _incident(connection, scope, _id(id))
            await _monitor(connection, scope, str(row["monitor_id"]))
            await connection.execute("SELECT id FROM incidents WHERE id=%s FOR UPDATE", (id,))
            row = await _incident(connection, scope, id)
            current = incident_projection(row)
            if row["version"] != expected_version:
                raise HttpError(
                    409,
                    "VERSION_CONFLICT",
                    "O incidente mudou. Revise os dados atuais.",
                    current=current,
                )
            if row["state"] != "open":
                raise HttpError(
                    409,
                    "INCIDENT_READONLY",
                    "Este incidente já foi reconhecido ou resolvido.",
                    current=current,
                )
            if scope.kind == "demo":
                await consume_limit(connection, f"mutation:visitor:{scope.visitor_id}", 60, 30)
            now = await _clock(connection)
            await connection.execute(
                "UPDATE incidents SET state='acknowledged',version=version+1,acknowledged_at=%s,"
                "acknowledged_by=%s,acknowledgement=%s WHERE id=%s",
                (now, scope.user_id, reason, id),
            )
            await record_event(
                connection,
                scope,
                str(row["monitor_id"]),
                "INCIDENT_ACKNOWLEDGED",
                now,
                {"before": "open", "after": "acknowledged", "comment": reason},
                incident_id=id,
            )
            return incident_projection(await _incident(connection, scope, id))
