import asyncio
from dataclasses import replace

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app
from sonda.migrate import migrate
from sonda.targets.fetcher import SafeFetcher
from sonda.targets.policy import validate_target
from tests.integration.test_access_http import start_demo
from tests.integration.test_http_readiness import _start, _stop
from tests.integration.test_scope import make_scope


async def test_probe_authentication_precedes_lookup_and_exposes_no_workspace_data(
    db: Database,
) -> None:
    scope = await make_scope(db)
    from sonda.access.demo import DemoService

    workspace = await DemoService(db).start("a" * 64, "127.0.0.1")
    async with db.connection() as connection:
        row = await (
            await connection.execute(
                "SELECT id FROM monitors WHERE workspace_id=%s LIMIT 1",
                (workspace.scope.id,),
            )
        ).fetchone()
    assert row is not None
    async with AsyncClient(
        transport=ASGITransport(app=create_app(db.settings, db)), base_url=db.settings.app_url
    ) as client:
        for id in [str(row["id"]), "bad-id", scope.id]:
            missing = await client.get(f"/probe/{id}")
            wrong = await client.get(f"/probe/{id}", headers={"X-Sonda-Probe": "wrong"})
            assert missing.status_code == wrong.status_code == 404
            assert missing.json() == wrong.json()
        available = await client.get(
            f"/probe/{row['id']}", headers={"X-Sonda-Probe": db.settings.probe_secret}
        )
        assert available.status_code == 200 and available.content == b""
        assert available.headers["cache-control"] == "no-store"
        async with db.transaction() as connection:
            await connection.execute(
                "UPDATE workspaces SET revoked_at=clock_timestamp() WHERE id=%s",
                (workspace.scope.id,),
            )
        assert (
            await client.get(
                f"/probe/{row['id']}", headers={"X-Sonda-Probe": db.settings.probe_secret}
            )
        ).status_code == 404


async def test_fetcher_calls_real_sonda_probe_and_observes_database_scenario(db: Database) -> None:
    import time

    from httpx import ConnectError, ConnectTimeout

    await migrate(db)
    process, origin = await asyncio.to_thread(_start, db)
    try:
        async with AsyncClient(base_url=origin, timeout=10) as client:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("HTTP worker exited")
                try:
                    assert (await client.get("/health/ready")).status_code == 200
                    break
                except (ConnectError, ConnectTimeout):
                    if time.monotonic() >= deadline:
                        raise
                    await asyncio.sleep(0.03)
            await start_demo(client)
            monitor = (await client.get("/api/monitors")).json()["monitors"][0]["id"]
            target = validate_target(origin + "/probe/" + monitor, set(), origin, production=False)
            fetcher = SafeFetcher(replace(db.settings, app_url=origin))
            assert (await fetcher.fetch(target)).status_code == 200
            async with db.transaction() as connection:
                await connection.execute(
                    "UPDATE monitors SET fixture_mode='unavailable' WHERE id=%s", (monitor,)
                )
            failed = await fetcher.fetch(target)
            assert failed.status_code == 503 and failed.error_code == "HTTP_STATUS"
    finally:
        await asyncio.to_thread(_stop, process)
