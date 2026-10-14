from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sonda.access.limits import lock_key
from sonda.access.scope import Scope, with_workspace
from sonda.checks.service import _clock
from sonda.db import Database
from sonda.incidents.events import record_event
from sonda.targets.policy import TargetRejected, validate_target


@dataclass(frozen=True)
class MonitorSpec:
    name: str
    target_url: str
    interval_seconds: int

    def __post_init__(self) -> None:
        if (
            not 3 <= len(self.name.strip()) <= 80
            or any(ord(char) < 32 for char in self.name)
            or type(self.interval_seconds) is not int
            or not 60 <= self.interval_seconds <= 2147483647
            or not 1 <= len(self.target_url) <= 2048
        ):
            raise ValueError("Invalid monitor name, target or interval")


async def install_monitor(db: Database, spec: MonitorSpec) -> dict[str, Any]:
    target = validate_target(
        spec.target_url,
        db.settings.allowed_hosts,
        db.settings.app_url,
        production=db.settings.production,
    )
    if target.internal:
        raise TargetRejected()
    async with db.connection() as connection:
        operator = await (
            await connection.execute(
                "SELECT w.id,u.id AS user_id FROM workspaces w JOIN users u ON u.workspace_id=w.id "
                "WHERE w.kind='normal' AND w.revoked_at IS NULL ORDER BY u.id LIMIT 1"
            )
        ).fetchone()
    if operator is None:
        raise ValueError("Install a normal operator before provisioning monitors")
    scope = Scope(str(operator["id"]), str(operator["user_id"]), "normal", None)
    name = spec.name.strip()
    async with with_workspace(db, scope) as connection:
        await lock_key(connection, f"provision:monitor:{scope.id}:{name}")
        previous = await (
            await connection.execute(
                "SELECT id,target_url,interval_seconds,version FROM monitors "
                "WHERE workspace_id=%s AND name=%s FOR UPDATE",
                (scope.id, name),
            )
        ).fetchone()
        if previous is not None:
            if (
                previous["target_url"] != target.url
                or previous["interval_seconds"] != spec.interval_seconds
            ):
                raise ValueError(
                    "Existing monitor target and interval are immutable; use a new record"
                )
            return {"id": str(previous["id"]), "version": previous["version"]}
        id = str(uuid4())
        await connection.execute(
            "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url,interval_seconds) "
            "VALUES(%s,%s,%s,'normal',%s,%s)",
            (id, scope.id, name, target.url, spec.interval_seconds),
        )
        await record_event(
            connection,
            scope,
            id,
            "MONITOR_CHANGED",
            await _clock(connection),
            {
                "before": None,
                "after": {
                    "target_url": target.url,
                    "interval_seconds": spec.interval_seconds,
                    "enabled": True,
                },
            },
        )
        return {"id": id, "version": 1}
