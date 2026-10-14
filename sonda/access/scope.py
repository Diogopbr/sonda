from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from psycopg import AsyncConnection

from sonda.db import Database
from sonda.http.errors import HttpError


@dataclass(frozen=True)
class Scope:
    id: str
    user_id: str
    kind: Literal["demo", "normal"]
    visitor_id: str | None


@asynccontextmanager
async def with_workspace(
    db: Database, scope: Scope
) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
    async with db.transaction() as connection:

        async def validate() -> None:
            current = await (
                await connection.execute(
                    "SELECT 1 FROM workspaces w JOIN users u ON u.workspace_id=w.id "
                    "WHERE w.id=%s AND u.id=%s AND w.kind=%s "
                    "AND w.visitor_id IS NOT DISTINCT FROM %s::uuid AND w.revoked_at IS NULL "
                    "AND (w.expires_at IS NULL OR w.expires_at>clock_timestamp())",
                    (scope.id, scope.user_id, scope.kind, scope.visitor_id),
                )
            ).fetchone()
            if current is None:
                raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")

        await validate()
        await connection.execute("SELECT id FROM workspaces WHERE id=%s FOR SHARE", (scope.id,))
        await validate()
        yield connection
        await validate()
