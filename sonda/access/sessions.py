import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime

from psycopg.types.json import Jsonb

from sonda.access.scope import Scope, with_workspace
from sonda.db import Database
from sonda.http.errors import HttpError


@dataclass(frozen=True)
class SessionRecord:
    digest: str = field(repr=False)
    csrf: str = field(repr=False)
    scope: Scope | None
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    cookie: str = field(repr=False)
    record: SessionRecord


class SessionService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _signature(self, token: str) -> str:
        return hmac.new(
            self.db.settings.session_secret.encode(), token.encode(), hashlib.sha256
        ).hexdigest()

    def _digest(self, cookie: str | None) -> str | None:
        if cookie is None or not re.fullmatch(r"[a-f0-9]{64}\.[a-f0-9]{64}", cookie):
            return None
        token, signature = cookie.split(".")
        if not hmac.compare_digest(signature, self._signature(token)):
            return None
        return hashlib.sha256(token.encode()).hexdigest()

    async def issue(
        self,
        scope: Scope | None = None,
        *,
        previous: str | None = None,
        expected_password_hash: str | None = None,
    ) -> IssuedSession:
        token, csrf = secrets.token_hex(32), secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        context = with_workspace(self.db, scope) if scope else self.db.transaction()
        async with context as connection:
            if expected_password_hash is not None:
                actor = await (
                    await connection.execute(
                        "SELECT password_hash FROM users WHERE id=%s AND workspace_id=%s FOR SHARE",
                        (scope.user_id if scope else None, scope.id if scope else None),
                    )
                ).fetchone()
                if actor is None or not hmac.compare_digest(
                    actor["password_hash"], expected_password_hash
                ):
                    raise HttpError(401, "LOGIN_INVALID", "E-mail ou senha inválidos.")
            row = await (
                await connection.execute(
                    "INSERT INTO sessions(id,workspace_id,actor_id,payload,expires_at) "
                    "VALUES(%s,%s,%s,%s,LEAST(clock_timestamp()+interval '24 hours',"
                    "(SELECT expires_at FROM workspaces WHERE id=%s))) RETURNING expires_at",
                    (
                        digest,
                        scope.id if scope else None,
                        scope.user_id if scope else None,
                        Jsonb({"csrf": csrf}),
                        scope.id if scope else None,
                    ),
                )
            ).fetchone()
            assert row is not None
            old_digest = self._digest(previous)
            if old_digest:
                await connection.execute("DELETE FROM sessions WHERE id=%s", (old_digest,))
        return IssuedSession(
            token + "." + self._signature(token),
            SessionRecord(digest, csrf, scope, row["expires_at"]),
        )

    async def resolve(self, cookie: str | None) -> SessionRecord | None:
        digest = self._digest(cookie)
        if digest is None:
            return None
        async with self.db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT s.payload,s.expires_at,s.workspace_id,s.actor_id,w.kind,w.visitor_id "
                    "FROM sessions s LEFT JOIN workspaces w ON w.id=s.workspace_id "
                    "LEFT JOIN users u ON u.id=s.actor_id AND u.workspace_id=w.id "
                    "WHERE s.id=%s AND s.expires_at>clock_timestamp() "
                    "AND (s.workspace_id IS NULL OR (u.id IS NOT NULL AND w.revoked_at IS NULL "
                    "AND (w.expires_at IS NULL OR w.expires_at>clock_timestamp())))",
                    (digest,),
                )
            ).fetchone()
        if row is None:
            return None
        csrf = row["payload"].get("csrf")
        if not isinstance(csrf, str) or not re.fullmatch(r"[a-f0-9]{64}", csrf):
            return None
        scope = None
        if row["workspace_id"] is not None:
            scope = Scope(
                str(row["workspace_id"]),
                str(row["actor_id"]),
                row["kind"],
                str(row["visitor_id"]) if row["visitor_id"] else None,
            )
        return SessionRecord(digest, csrf, scope, row["expires_at"])

    async def destroy(self, cookie: str | None) -> None:
        digest = self._digest(cookie)
        if digest:
            async with self.db.transaction() as connection:
                await connection.execute("DELETE FROM sessions WHERE id=%s", (digest,))
