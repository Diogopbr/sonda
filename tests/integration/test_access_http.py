from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app
from sonda.migrate import migrate


async def start_demo(client: AsyncClient) -> dict[str, str]:
    csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
    response = await client.post(
        "/api/demo/start",
        headers={"Origin": str(client.base_url).rstrip("/"), "X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


async def test_two_apps_share_sessions_but_visitors_cannot_read_each_others_monitors(
    db: Database,
) -> None:
    await migrate(db)
    async with (
        AsyncClient(
            transport=ASGITransport(app=create_app(db.settings, db)), base_url=db.settings.app_url
        ) as first,
        AsyncClient(
            transport=ASGITransport(app=create_app(db.settings, db)), base_url=db.settings.app_url
        ) as second,
    ):
        a = await start_demo(first)
        b = await start_demo(second)
        assert a["workspace_id"] != b["workspace_id"]
        monitors = await first.get("/api/monitors")
        assert monitors.status_code == 200 and len(monitors.json()["monitors"]) == 4
        monitor_id = monitors.json()["monitors"][0]["id"]
        assert (await second.get(f"/api/monitors/{monitor_id}")).status_code == 404
        second.cookies.update(first.cookies)
        assert (await second.get("/api/auth")).json()["workspace_id"] == a["workspace_id"]
        assert (await second.get(f"/api/monitors/{monitor_id}")).status_code == 200


async def test_origin_csrf_and_old_generation_are_rejected_before_reset(db: Database) -> None:
    await migrate(db)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(db.settings, db)), base_url=db.settings.app_url
    ) as client:
        csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
        for headers in [
            {},
            {"Origin": "https://foreign.invalid", "X-CSRF-Token": csrf},
            {"Origin": db.settings.app_url, "X-CSRF-Token": "wrong"},
        ]:
            assert (await client.post("/api/demo/start", headers=headers)).status_code == 419
        original = await start_demo(client)
        old_cookie = client.cookies.get("sonda_session")
        csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
        reset = await client.post(
            "/api/demo/reset",
            headers={
                "Origin": db.settings.app_url,
                "X-CSRF-Token": csrf,
                "X-Sonda-Workspace": original["workspace_id"],
            },
        )
        assert reset.status_code == 201
        assert reset.json()["workspace_id"] != original["workspace_id"]
        assert client.cookies.get("sonda_session") != old_cookie
        new_csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
        stale = await client.post(
            "/api/demo/reset",
            headers={
                "Origin": db.settings.app_url,
                "X-CSRF-Token": new_csrf,
                "X-Sonda-Workspace": original["workspace_id"],
            },
        )
        assert stale.status_code == 404
        async with AsyncClient(
            transport=ASGITransport(app=create_app(db.settings, db)),
            base_url=db.settings.app_url,
            cookies={"sonda_session": old_cookie},
        ) as old_tab:
            assert (await old_tab.get("/api/monitors")).status_code == 404
        assert reset.headers["cache-control"] == "no-store"


async def test_demo_recovery_keeps_deadline_and_production_cookie_is_secure(db: Database) -> None:
    from dataclasses import replace

    await migrate(db)
    settings = replace(db.settings, environment="production", app_url="https://sonda.invalid")
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings, db)), base_url=settings.app_url
    ) as client:
        first = await start_demo(client)
        csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
        recovered = await client.post(
            "/api/demo/start",
            headers={
                "Origin": settings.app_url,
                "X-CSRF-Token": csrf,
            },
        )
        assert recovered.status_code == 201
        assert recovered.json() == first
        cookie = recovered.headers.get_list("set-cookie")[0].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
        assert (await client.get("/api/auth")).json()["workspace_id"] == first["workspace_id"]


async def test_normal_login_logout_and_disabled_login(db: Database) -> None:
    from dataclasses import replace

    from sonda.access.normal import Credentials, install_normal

    await migrate(db)
    credentials = Credentials(
        email="operador@example.com", name="Operador", password="senha longa de teste"
    )
    scope = await install_normal(db, credentials)
    for enabled in [False, True]:
        settings = replace(db.settings, login_enabled=enabled)
        async with AsyncClient(
            transport=ASGITransport(app=create_app(settings, db)), base_url=settings.app_url
        ) as client:
            csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
            headers = {"Origin": settings.app_url, "X-CSRF-Token": csrf}
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": credentials.email,
                    "password": credentials.password,
                },
                headers=headers,
            )
            assert response.status_code == (200 if enabled else 404)
            if enabled:
                assert response.json()["workspace_id"] == scope.id
                headers["X-CSRF-Token"] = (await client.get("/api/auth/csrf")).json()["csrf"]
                headers["X-Sonda-Workspace"] = scope.id
                assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
                assert (await client.get("/api/monitors")).status_code == 404


async def test_access_rejects_large_body_and_never_echoes_login_input(db: Database) -> None:
    from dataclasses import replace

    await migrate(db)
    settings = replace(db.settings, login_enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings, db)), base_url=settings.app_url
    ) as client:
        csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
        headers = {"Origin": settings.app_url, "X-CSRF-Token": csrf}
        response = await client.post(
            "/api/auth/login",
            json={
                "email": "operador@example.com",
                "password": "private-test-password",
                "unexpected": 1,
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "private-test-password" not in response.text
        response = await client.post("/api/auth/login", content=b"x" * 16385, headers=headers)
        assert response.status_code == 413
        assert response.headers["cache-control"] == "no-store"
