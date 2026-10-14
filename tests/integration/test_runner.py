from dataclasses import replace
from uuid import uuid4

import pytest

from sonda.db import Database
from sonda.runner import run_due
from sonda.targets.fetcher import FetchOutcome
from tests.integration.test_checks import demo_monitors
from tests.integration.test_claim_concurrency import normal_monitor, worker
from tests.integration.test_http_readiness import _stop


class HealthyFetcher:
    def __init__(self):
        self.calls = 0

    async def fetch(self, target):
        self.calls += 1
        return FetchOutcome(200, 1, None)


async def test_runner_is_bounded_skips_locked_normal_monitor_and_never_touches_demo(
    db: Database,
) -> None:
    import asyncio

    scope, first_monitor = await normal_monitor(db)
    demo, _ = await demo_monitors(db)
    async with db.transaction() as connection:
        for number in range(11):
            await connection.execute(
                "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url) "
                "VALUES(%s,%s,%s,'normal','https://example.com/')",
                (uuid4(), scope.id, f"Serviço autorizado {number:02d}"),
            )
    held = await worker(db, scope, first_monitor, "hold")
    try:
        assert (await held.next())["event"] == "locked"
        runtime = Database(
            replace(db.settings, allowed_hosts=frozenset({"example.com"})), db.schema
        )
        fetcher = HealthyFetcher()
        report = await asyncio.wait_for(run_due(runtime, fetcher=fetcher), timeout=5)
        assert report.claimed == report.finished == 10 and fetcher.calls == 10
        second = await run_due(runtime, fetcher=fetcher)
        assert second.claimed == second.finished == 1
        assert (await run_due(runtime, fetcher=fetcher)).claimed == 0
        async with db.connection() as connection:
            assert not await (
                await connection.execute(
                    "SELECT 1 FROM check_runs WHERE workspace_id=%s", (demo.id,)
                )
            ).fetchone()
            rows = await (
                await connection.execute(
                    "SELECT c.origin,m.next_due_at-c.started_at AS interval FROM check_runs c "
                    "JOIN monitors m ON m.id=c.monitor_id WHERE c.workspace_id=%s",
                    (scope.id,),
                )
            ).fetchall()
            assert all(
                row["origin"] == "runner" and row["interval"].total_seconds() >= 60 for row in rows
            )
        for batch in [0, 11]:
            with pytest.raises(ValueError):
                await run_due(runtime, batch=batch, fetcher=fetcher)
        held.release()
        assert (await held.next())["accepted"]
    finally:
        await asyncio.to_thread(_stop, held.process)


async def test_two_runner_processes_skip_each_others_locked_batch(db: Database) -> None:
    import asyncio
    import os
    import subprocess
    import sys

    from tests.integration.test_claim_concurrency import Worker

    scope, _ = await normal_monitor(db)
    async with db.transaction() as connection:
        for number in range(11):
            await connection.execute(
                "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url) "
                "VALUES(%s,%s,%s,'normal','https://example.com/')",
                (uuid4(), scope.id, f"Serviço autorizado {number:02d}"),
            )

    async def start(mode):
        process = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "tests.workers.runner_worker",
                db.schema,
                scope.id,
                scope.user_id,
                mode,
            ],
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return Worker(process)

    first = await start("hold")
    second = None
    try:
        assert (await first.next())["event"] == "locked"
        second = await start("plain")
        other = await second.next()
        assert len(other["ids"]) == 2
        first.release()
        original = await first.next()
        assert len(original["ids"]) == 10 and set(original["ids"]).isdisjoint(other["ids"])
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s", (scope.id,)
                )
            ).fetchone()
            assert row is not None and row["n"] == 12
    finally:
        await asyncio.to_thread(_stop, first.process)
        if second:
            await asyncio.to_thread(_stop, second.process)
