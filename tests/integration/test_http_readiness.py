import asyncio
import os
import socket
import subprocess
import sys
import time

from httpx import AsyncClient, ConnectError, ConnectTimeout, Timeout

from sonda.db import Database
from sonda.migrate import migrate


def _start(db: Database) -> tuple[subprocess.Popen[bytes], str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.workers.http_app", db.schema, str(port)],
        env=dict(os.environ) | {"APP_URL": origin, "PORT": str(port)},
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
