import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection

from sonda.access.limits import consume_limit, ip_key, lock_key
from sonda.access.scope import Scope
from sonda.db import Database
from sonda.http.errors import HttpError


@dataclass(frozen=True)
class DemoWorkspace:
    scope: Scope
    expires_at: datetime


class DemoService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def start(self, token: str, ip: str) -> DemoWorkspace:
        digest = self._digest(token)
        async with self.db.transaction() as connection:
            await consume_limit(connection, ip_key("start:ip", ip), 60, 10)
            visitor = await (
                await connection.execute(
                    "INSERT INTO visitors(id,token_hash) VALUES(%s,%s) "
                    "ON CONFLICT(token_hash) DO UPDATE SET token_hash=EXCLUDED.token_hash "
                    "RETURNING id",
                    (uuid4(), digest),
                )
            ).fetchone()
            assert visitor is not None
            visitor_id = str(visitor["id"])
            await lock_key(connection, f"demo:visitor:{visitor_id}")
            current = await (
                await connection.execute(
                    "SELECT w.id,w.expires_at,u.id AS user_id FROM workspaces w "
                    "JOIN users u ON u.workspace_id=w.id WHERE w.visitor_id=%s "
                    "AND w.revoked_at IS NULL AND w.expires_at>clock_timestamp() "
                    "ORDER BY w.created_at DESC LIMIT 1 FOR SHARE OF w",
                    (visitor_id,),
                )
            ).fetchone()
            if current is not None:
                return DemoWorkspace(
                    Scope(str(current["id"]), str(current["user_id"]), "demo", visitor_id),
                    current["expires_at"],
                )
            return await self._create(connection, visitor_id)

    async def reset(self, scope: Scope, token: str, ip: str) -> DemoWorkspace:
        digest = self._digest(token)
        if scope.kind != "demo" or scope.visitor_id is None:
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
        async with self.db.transaction() as connection:
            await lock_key(connection, ip_key("reset:ip", ip))
            await lock_key(connection, f"demo:visitor:{scope.visitor_id}")
            await self._owned(connection, scope, digest)
            await connection.execute(
                "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (scope.id,)
            )
            await self._owned(connection, scope, digest)
            await consume_limit(connection, ip_key("reset:ip", ip), 3600, 10)
            await consume_limit(connection, f"reset:visitor:{scope.visitor_id}", 60, 1)
            await connection.execute(
                "UPDATE workspaces SET revoked_at=clock_timestamp() WHERE id=%s", (scope.id,)
            )
            await connection.execute("DELETE FROM sessions WHERE workspace_id=%s", (scope.id,))
            fresh = await self._create(connection, scope.visitor_id)
            await self._owned(connection, scope, digest, allow_revoked=True)
            return fresh

    @staticmethod
    def _digest(token: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", token):
            raise HttpError(404, "NOT_FOUND", "Identidade não encontrada.")
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    @staticmethod
    async def _owned(
        connection: AsyncConnection[dict[str, Any]],
        scope: Scope,
        digest: str,
        *,
        allow_revoked: bool = False,
    ) -> None:
        current = await (
            await connection.execute(
                "SELECT 1 FROM workspaces w JOIN visitors v ON v.id=w.visitor_id "
                "JOIN users u ON u.workspace_id=w.id WHERE w.id=%s AND w.kind='demo' "
                "AND w.visitor_id=%s AND u.id=%s AND v.token_hash=%s "
                "AND (w.revoked_at IS NULL OR %s) AND w.expires_at>clock_timestamp()",
                (scope.id, scope.visitor_id, scope.user_id, digest, allow_revoked),
            )
        ).fetchone()
        if current is None:
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")

    async def _create(
        self, connection: AsyncConnection[dict[str, Any]], visitor_id: str
    ) -> DemoWorkspace:
        scope = Scope(str(uuid4()), str(uuid4()), "demo", visitor_id)
        row = await (
            await connection.execute(
                "INSERT INTO workspaces(id,kind,visitor_id,expires_at) "
                "VALUES(%s,'demo',%s,clock_timestamp()+interval '24 hours') RETURNING expires_at",
                (scope.id, visitor_id),
            )
        ).fetchone()
        assert row is not None
        await connection.execute(
            "INSERT INTO users(id,workspace_id,email,name,password_hash) "
            "VALUES(%s,%s,%s,%s,'disabled')",
            (scope.user_id, scope.id, f"{scope.user_id}@demo.invalid", "Visitante"),
        )
        for name in [
            "Portal editorial",
            "API de pedidos",
            "Área de downloads",
            "Página de suporte",
        ]:
            monitor_id = str(uuid4())
            await connection.execute(
                "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url,fixture_mode) "
                "VALUES(%s,%s,%s,'fixture',%s,'available')",
                (monitor_id, scope.id, name, f"{self.db.settings.app_url}/probe/{monitor_id}"),
            )
        return DemoWorkspace(scope, row["expires_at"])
