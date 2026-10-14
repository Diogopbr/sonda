import asyncio
import time
from contextlib import AsyncExitStack
from uuid import uuid4

import pytest
from httpx import AsyncClient, ConnectError, ConnectTimeout

from sonda.checks.execution import ExecutionService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.migrate import migrate
from sonda.monitors.service import MonitorService
from sonda.targets.fetcher import FetchOutcome
from tests.integration.test_access_http import start_demo
from tests.integration.test_checks import demo_monitors
from tests.integration.test_http_readiness import _start, _stop
from tests.integration.test_product_http import headers


class HeldFetcher:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self, target):
        self.entered.set()
        await self.release.wait()
        return FetchOutcome(200, 1, None)


async def test_network_wait_holds_no_database_slot_and_pause_refuses_late_result(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    fetcher = HeldFetcher()
    task = asyncio.create_task(
        ExecutionService(db, fetcher=fetcher).execute(scope, monitors[0], str(uuid4()))
    )
    try:
        await asyncio.wait_for(fetcher.entered.wait(), timeout=2)
        async with AsyncExitStack() as connections:
            for _ in range(4):
                await asyncio.wait_for(connections.enter_async_context(db.connection()), timeout=2)
        await MonitorService(db).change(scope, monitors[0], 1, enabled=False)
        fetcher.release.set()
        with pytest.raises(HttpError) as late:
            await task
        assert late.value.status_code == 410
        monitor = await MonitorService(db).get(scope, monitors[0])
        assert monitor["observed_state"] == "unknown" and monitor["failure_streak"] == 0
        assert monitor["checks"][0]["state"] == "abandoned"
    finally:
        fetcher.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_real_http_incident_cycle_replay_acknowledgement_and_recovery(db: Database) -> None:
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
            access = await start_demo(client)
            workspace = access["workspace_id"]
            monitor = (await client.get("/api/monitors")).json()["monitors"][0]
            id = monitor["id"]
            key = str(uuid4())

            async def check(key: str | None = None):
                response = await client.post(
                    f"/api/monitors/{id}/checks",
                    headers=await headers(client, workspace),
                    json={"key": key or str(uuid4())},
                )
                assert response.status_code == 200
                return response.json()

            healthy = await check(key)
            assert healthy["status_code"] == 200 and healthy["duration_ms"] >= 0
            assert (await check(key))["id"] == healthy["id"]
            for mode in ["unavailable", "available"]:
                current = (await client.get(f"/api/monitors/{id}")).json()
                changed = await client.patch(
                    f"/api/monitors/{id}",
                    headers=await headers(client, workspace),
                    json={"expected_version": current["version"], "fixture_mode": mode},
                )
                assert changed.status_code == 200
                assert (await check())["status_code"] == (503 if mode == "unavailable" else 200)
                assert (await check())["status_code"] == (503 if mode == "unavailable" else 200)
                if mode == "unavailable":
                    incident = (await client.get(f"/api/monitors/{id}")).json()["active_incident"]
                    incident_id = incident["id"]
                    acknowledgement = await client.post(
                        f"/api/incidents/{incident_id}/ack",
                        headers=await headers(client, workspace),
                        json={
                            "expected_version": incident["version"],
                            "comment": "Investigando a resposta da API de pedidos.",
                        },
                    )
                    assert (
                        acknowledgement.status_code == 200
                        and acknowledgement.json()["state"] == "acknowledged"
                    )
                    stale = await client.post(
                        f"/api/incidents/{incident_id}/ack",
                        headers=await headers(client, workspace),
                        json={
                            "expected_version": incident["version"],
                            "comment": "Rascunho da outra aba.",
                        },
                    )
                    assert stale.status_code == 409
            resolved = (await client.get(f"/api/incidents/{incident_id}")).json()
            assert resolved["state"] == "resolved"
            assert resolved["acknowledgement"] == "Investigando a resposta da API de pedidos."
            assert len(resolved["events"]) == 3
            assert resolved["evidence"]["first_failure"]["status_code"] == 503
            assert resolved["evidence"]["resolution"]["status_code"] == 200
            service_history = (await client.get(f"/api/monitors/{id}")).json()
            assert service_history["incidents"][0]["id"] == incident_id
            assert service_history["incidents"][0]["state"] == "resolved"
            assert (await client.get(f"/api/checks/{healthy['id']}")).json()["id"] == healthy["id"]
            async with AsyncClient(base_url=origin) as other:
                await start_demo(other)
                assert (await other.get(f"/api/incidents/{incident_id}")).status_code == 404
                assert (await other.get(f"/api/checks/{healthy['id']}")).status_code == 404
            async with db.connection() as connection:
                total = await (
                    await connection.execute(
                        "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s", (workspace,)
                    )
                ).fetchone()
                assert total is not None and total["n"] == 5
    finally:
        await asyncio.to_thread(_stop, process)
