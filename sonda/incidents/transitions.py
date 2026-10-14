from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection

from sonda.access.scope import Scope
from sonda.incidents.events import record_event


async def apply_result(
    connection: AsyncConnection[dict[str, Any]],
    scope: Scope,
    monitor: dict[str, Any],
    check: dict[str, Any],
    now: datetime,
) -> None:
    active = await (
        await connection.execute(
            "SELECT * FROM incidents WHERE workspace_id=%s AND monitor_id=%s "
            "AND state<>'resolved' FOR UPDATE",
            (scope.id, monitor["id"]),
        )
    ).fetchone()
    healthy = check["error_code"] is None
    failures = 0 if healthy else monitor["failure_streak"] + 1
    successes = monitor["success_streak"] + 1 if healthy else 0
    first_at = (
        None if healthy else (monitor["failure_started_at"] if monitor["failure_streak"] else now)
    )
    first_id = (
        None
        if healthy
        else (monitor["failure_started_check_id"] if monitor["failure_streak"] else check["id"])
    )
    state = monitor["observed_state"]
    if healthy:
        if state != "unavailable" or successes >= 2:
            state = "healthy"
        if active is not None and successes >= 2:
            await connection.execute(
                "UPDATE incidents SET state='resolved',version=version+1,resolved_at=%s,"
                "resolution_check_id=%s WHERE id=%s",
                (now, check["id"], active["id"]),
            )
            await record_event(
                connection,
                scope,
                str(monitor["id"]),
                "INCIDENT_RESOLVED",
                now,
                {"before": active["state"], "after": "resolved"},
                incident_id=str(active["id"]),
                check_id=str(check["id"]),
            )
    elif failures >= 2:
        state = "unavailable"
        if active is None:
            id = str(uuid4())
            await connection.execute(
                "INSERT INTO incidents(id,workspace_id,monitor_id,first_failure_at,confirmed_at,"
                "first_failure_check_id,confirmation_check_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (id, scope.id, monitor["id"], first_at, now, first_id, check["id"]),
            )
            await record_event(
                connection,
                scope,
                str(monitor["id"]),
                "INCIDENT_OPENED",
                now,
                {"before": None, "after": "open"},
                incident_id=id,
                check_id=str(check["id"]),
            )
    await connection.execute(
        "UPDATE monitors SET observed_state=%s,failure_streak=%s,success_streak=%s,"
        "failure_started_at=%s,failure_started_check_id=%s,last_check_id=%s,version=version+1 "
        "WHERE id=%s",
        (state, failures, successes, first_at, first_id, check["id"], monitor["id"]),
    )
