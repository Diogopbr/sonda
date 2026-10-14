import base64
import re
from dataclasses import dataclass, field
from uuid import uuid4

from sonda.access.limits import consume_limit, ip_key, lock_key
from sonda.access.passwords import PasswordService, validate_password
from sonda.access.scope import Scope
from sonda.access.sessions import IssuedSession, SessionService
from sonda.db import Database
from sonda.http.errors import HttpError


def canonical_email(email: str) -> str:
    value = email.strip().lower()
    if not 3 <= len(value) <= 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value
    ):
        raise ValueError("Invalid email")
    return value


@dataclass(frozen=True)
class Credentials:
    email: str
    name: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        canonical_email(self.email)
        validate_password(self.password)
        if not 3 <= len(self.name.strip()) <= 80 or any(ord(char) < 32 for char in self.name):
            raise ValueError("Name must contain3..80 characters without controls")


async def install_normal(db: Database, credentials: Credentials) -> Scope:
    password_hash = await PasswordService().hash(credentials.password)
    async with db.transaction() as connection:
        await lock_key(connection, "install:normal")
        workspace = await (
            await connection.execute("SELECT id FROM workspaces WHERE kind='normal' FOR UPDATE")
        ).fetchone()
        workspace_id = str(workspace["id"]) if workspace else str(uuid4())
        if workspace is None:
            await connection.execute(
                "INSERT INTO workspaces(id,kind) VALUES(%s,'normal')",
                (workspace_id,),
            )
        actor = await (
            await connection.execute(
                "INSERT INTO users(id,workspace_id,email,name,password_hash) "
                "VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT(workspace_id,email) DO UPDATE SET name=EXCLUDED.name,"
                "password_hash=EXCLUDED.password_hash RETURNING id",
                (
                    str(uuid4()),
                    workspace_id,
                    canonical_email(credentials.email),
                    credentials.name.strip(),
                    password_hash,
                ),
            )
        ).fetchone()
        assert actor is not None
        await connection.execute("DELETE FROM sessions WHERE actor_id=%s", (actor["id"],))
    return Scope(workspace_id, str(actor["id"]), "normal", None)


class LoginService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.passwords = PasswordService()
        salt = base64.urlsafe_b64encode(bytes(16)).decode().rstrip("=")
        key = base64.urlsafe_b64encode(bytes(64)).decode().rstrip("=")
        self._dummy = f"scrypt$32768$8$1${salt}${key}"

    async def login(
        self, email: str, password: str, ip: str, *, previous: str | None = None
    ) -> IssuedSession:
        async with self.db.transaction() as connection:
            await consume_limit(connection, ip_key("login:ip", ip), 60, 10)
        try:
            email = canonical_email(email)
        except ValueError:
            email = ""
        async with self.db.connection() as connection:
            actor = await (
                await connection.execute(
                    "SELECT u.id,u.workspace_id,u.password_hash FROM users u "
                    "JOIN workspaces w ON w.id=u.workspace_id "
                    "WHERE w.kind='normal' AND w.revoked_at IS NULL AND u.email=%s",
                    (email,),
                )
            ).fetchone()
        verified = await self.passwords.verify(
            password, actor["password_hash"] if actor else self._dummy
        )
        if actor is None or not verified:
            raise HttpError(401, "LOGIN_INVALID", "E-mail ou senha inválidos.")
        scope = Scope(str(actor["workspace_id"]), str(actor["id"]), "normal", None)
        return await SessionService(self.db).issue(
            scope,
            previous=previous,
            expected_password_hash=actor["password_hash"],
        )
