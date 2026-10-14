import pytest

from sonda.access.normal import Credentials, LoginService, install_normal
from sonda.access.sessions import SessionService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.migrate import migrate


async def test_install_and_login_rotate_sessions_and_password_change_revokes_access(
    db: Database,
) -> None:
    await migrate(db)
    credentials = Credentials(
        email="operador@example.com", name="Operador", password="senha longa de teste"
    )
    scope = await install_normal(db, credentials)
    login = LoginService(db)
    issued = await login.login(credentials.email, credentials.password, "127.0.0.1")
    assert issued.record.scope == scope
    assert await SessionService(db).resolve(issued.cookie) is not None
    changed = await install_normal(
        db,
        Credentials(
            email=credentials.email,
            name=credentials.name,
            password="outra senha longa de teste",
        ),
    )
    assert changed == scope
    assert await SessionService(db).resolve(issued.cookie) is None
    for email, password in [
        (credentials.email, credentials.password),
        ("ausente@example.com", credentials.password),
    ]:
        with pytest.raises(HttpError) as caught:
            await login.login(email, password, "127.0.0.1")
        assert caught.value.status_code == 401 and caught.value.code == "LOGIN_INVALID"
    assert (
        await login.login(credentials.email, "outra senha longa de teste", "127.0.0.1")
    ).record.scope == scope


async def test_old_password_verification_cannot_issue_session_after_password_change(
    db: Database,
) -> None:
    await migrate(db)
    credentials = Credentials(
        email="operador@example.com", name="Operador", password="senha longa de teste"
    )
    scope = await install_normal(db, credentials)
    async with db.connection() as connection:
        row = await (
            await connection.execute(
                "SELECT password_hash FROM users WHERE id=%s", (scope.user_id,)
            )
        ).fetchone()
    assert row is not None
    await install_normal(
        db,
        Credentials(email=credentials.email, name="Operador", password="nova senha longa de teste"),
    )
    with pytest.raises(HttpError) as caught:
        await SessionService(db).issue(scope, expected_password_hash=row["password_hash"])
    assert caught.value.status_code == 401


async def test_login_limit_uses_database_counter(db: Database) -> None:
    await migrate(db)
    login = LoginService(db)
    for _ in range(10):
        with pytest.raises(HttpError) as caught:
            await login.login("ausente@example.com", "senha longa de teste", "127.0.0.1")
        assert caught.value.status_code == 401
    with pytest.raises(HttpError) as caught:
        await login.login("ausente@example.com", "senha longa de teste", "127.0.0.1")
    assert caught.value.status_code == 429
    assert caught.value.retry_after is not None and 1 <= caught.value.retry_after <= 60
