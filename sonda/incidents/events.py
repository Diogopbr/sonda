from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from sonda.access.scope import Scope


async def record_event(
    connection: AsyncConnection[dict[str, Any]],
    scope: Scope,
    monitor_id: str,
    type: str,
    now: datetime,
    payload: dict[str, Any],
    *,
    incident_id: str | None = None,
    check_id: str | None = None,
) -> None:
    await connection.execute(
        "INSERT INTO events(id,workspace_id,monitor_id,incident_id,check_id,actor_id,"
        "type,occurred_at,payload) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            scope.id,
            monitor_id,
            incident_id,
            check_id,
            scope.user_id,
            type,
            now,
            Jsonb(payload),
        ),
    )
