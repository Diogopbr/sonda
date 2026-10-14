import asyncio
import os
import socket
import subprocess
import sys
import time

from httpx import AsyncClient, ConnectError, ConnectTimeout, Timeout

from sonda.db import Database
from sonda.migrate import migrate


def _start(db: Database, app_url: str | None = None) -> tuple[subprocess.Popen[bytes], str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.workers.http_app", db.schema, str(port)],
        env=dict(os.environ) | {"APP_URL": app_url or origin, "PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process, origin


def _stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def test_separate_http_process_observes_database_migration_without_restart(
    db: Database,
) -> None:
    process, origin = await asyncio.to_thread(_start, db)
    try:
        async with AsyncClient(base_url=origin, timeout=Timeout(10, connect=0.5)) as client:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("HTTP worker exited before accepting requests")
                try:
                    before = await client.get("/health/ready")
                    break
                except (ConnectError, ConnectTimeout):
                    if time.monotonic() >= deadline:
                        raise
                    await asyncio.sleep(0.03)
            assert before.status_code == 503
            await migrate(db)
            after = await client.get("/health/ready")
            assert after.status_code == 200
            assert after.json() == {"status": "ready"}
            assert after.headers["x-content-type-options"] == "nosniff"
    finally:
        await asyncio.to_thread(_stop, process)


async def test_two_http_processes_share_persistent_access_without_cross_visitor_reads(
    db: Database,
) -> None:
    await migrate(db)
    first_process, first_origin = await asyncio.to_thread(_start, db)
    second_process, second_origin = await asyncio.to_thread(_start, db, first_origin)
    try:
        async with (
            AsyncClient(base_url=first_origin, timeout=Timeout(10, connect=0.5)) as first,
            AsyncClient(base_url=second_origin, timeout=Timeout(10, connect=0.5)) as second,
        ):
            for process, client in [(first_process, first), (second_process, second)]:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("HTTP worker exited before accepting requests")
                    try:
                        assert (await client.get("/health/ready")).status_code == 200
                        break
                    except (ConnectError, ConnectTimeout):
                        if time.monotonic() >= deadline:
                            raise
                        await asyncio.sleep(0.03)
            workspaces = []
            for client in [first, second]:
                csrf = (await client.get("/api/auth/csrf")).json()["csrf"]
                started = await client.post(
                    "/api/demo/start",
                    headers={
                        "Origin": first_origin,
                        "X-CSRF-Token": csrf,
                    },
                )
                assert started.status_code == 201
                workspaces.append(started.json()["workspace_id"])
            assert workspaces[0] != workspaces[1]
            monitor = (await first.get("/api/monitors")).json()["monitors"][0]["id"]
            assert (await second.get(f"/api/monitors/{monitor}")).status_code == 404
            second.cookies.update(first.cookies)
            assert (await second.get("/api/auth")).json()["workspace_id"] == workspaces[0]
            assert (await second.get(f"/api/monitors/{monitor}")).status_code == 200
    finally:
        await asyncio.to_thread(_stop, first_process)
        await asyncio.to_thread(_stop, second_process)
