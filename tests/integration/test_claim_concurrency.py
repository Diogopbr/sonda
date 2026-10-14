import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import pytest

from sonda.access.normal import Credentials, install_normal
from sonda.access.scope import Scope
from sonda.db import Database
from sonda.migrate import migrate
from tests.integration.test_checks import demo_monitors
from tests.integration.test_http_readiness import _stop


@dataclass
class Worker:
    process: subprocess.Popen[bytes]

    async def next(self) -> dict:
        assert self.process.stdout is not None
        line = await asyncio.wait_for(asyncio.to_thread(self.process.stdout.readline), timeout=10)
        if not line:
            raise RuntimeError("Claim worker exited before reporting")
        event = json.loads(line)
        assert event["event"] != "worker-error", event
        return event

    def release(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(b"release\n")
        self.process.stdin.flush()


async def worker(
    db: Database, scope: Scope, monitor: str, mode: str, key: str | None = None
) -> Worker:
    process = await asyncio.to_thread(
        subprocess.Popen,
        [
            sys.executable,
            "-m",
            "tests.workers.claim_worker",
            db.schema,
            scope.id,
            scope.user_id,
            scope.kind,
            scope.visitor_id or "none",
            monitor,
            key or str(uuid4()),
            mode,
        ],
        env=dict(os.environ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return Worker(process)


async def blocked_by(db: Database, waiting: int, holding: int) -> None:
    deadline = time.monotonic() + 5
    async with db.connection() as observer:
        while time.monotonic() < deadline:
            row = await (
                await observer.execute(
                    "SELECT pg_blocking_pids(%s) AS blockers",
                    (waiting,),
                )
            ).fetchone()
            if row is not None and holding in row["blockers"]:
                return
    raise AssertionError("Required PostgreSQL blocking was not observed")


async def normal_monitor(db: Database) -> tuple[Scope, str]:
    await migrate(db)
    scope = await install_normal(
        db,
        Credentials(
            email="operador@example.com",
            name="Operador",
            password="senha longa de teste",
        ),
    )
    id = str(uuid4())
    async with db.transaction() as connection:
        await connection.execute(
            "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url) "
            "VALUES(%s,%s,'API de pedidos','normal','https://example.com/')",
            (id, scope.id),
        )
    return scope, id


async def test_monitor_row_lock_blocks_second_process_and_admits_only_one_claim(
    db: Database,
) -> None:
    scope, monitor = await normal_monitor(db)
    first = await worker(db, scope, monitor, "hold")
    second = None
    try:
        locked = await first.next()
        assert locked["event"] == "locked"
        second = await worker(db, scope, monitor, "wait")
        waiting = await second.next()
        assert waiting["event"] == "waiting"
        await blocked_by(db, waiting["pid"], locked["pid"])
        first.release()
        assert (await first.next())["accepted"]
        refused = await second.next()
        assert not refused["accepted"] and refused["code"] == "CHECK_RUNNING"
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                    (scope.id,),
                )
            ).fetchone()
            assert row is not None and row["n"] == 1
    finally:
        await asyncio.to_thread(_stop, first.process)
        if second:
            await asyncio.to_thread(_stop, second.process)


async def test_negative_control_without_row_lock_admits_two_claims(db: Database) -> None:
    scope, monitor = await normal_monitor(db)
    first, second = (
        await worker(db, scope, monitor, "unsafe"),
        await worker(db, scope, monitor, "unsafe"),
    )
    try:
        assert (await first.next())["event"] == "snapshot"
        assert (await second.next())["event"] == "snapshot"
        first.release()
        second.release()
        assert (await first.next())["accepted"] and (await second.next())["accepted"]
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                    (scope.id,),
                )
            ).fetchone()
            assert row is not None and row["n"] == 2
    finally:
        await asyncio.to_thread(_stop, first.process)
        await asyncio.to_thread(_stop, second.process)


@pytest.mark.parametrize("seed_count", [58, 59])
async def test_demo_quota_is_shared_between_monitors_and_lease_starts_after_wait(
    db: Database,
    seed_count: int,
) -> None:
    scope, monitors = await demo_monitors(db)
    async with db.transaction() as connection:
        for _ in range(seed_count):
            id = uuid4()
            await connection.execute(
                "INSERT INTO check_runs(id,workspace_id,monitor_id,actor_id,client_key,origin,"
                "lease_token,monitor_version,started_at,lease_until) "
                "VALUES(%s,%s,%s,%s,%s,'manual',%s,1,clock_timestamp()-interval '1 hour',"
                "clock_timestamp()-interval '59 minutes')",
                (id, scope.id, monitors[0], scope.user_id, uuid4(), uuid4()),
            )
            await connection.execute(
                "UPDATE check_runs SET state='abandoned',finished_at=clock_timestamp(),"
                "abandon_reason='LEASE_EXPIRED' WHERE id=%s",
                (id,),
            )
    first = await worker(db, scope, monitors[0], "quota-hold")
    second = None
    try:
        locked = await first.next()
        second = await worker(db, scope, monitors[1], "quota-wait")
        waiting = await second.next()
        await blocked_by(db, waiting["pid"], locked["pid"])
        async with db.connection() as connection:
            released = await (
                await connection.execute("SELECT clock_timestamp() AS now")
            ).fetchone()
        assert released is not None
        first.release()
        accepted = await first.next()
        assert (
            accepted["accepted"]
            and datetime.fromisoformat(accepted["started_at"]) >= released["now"]
        )
        refused = await second.next()
        if seed_count == 59:
            assert not refused["accepted"] and refused["code"] == "DEMO_QUOTA"
            assert 1 <= refused["retry_after"] <= 86400
        else:
            assert refused["accepted"]
            assert datetime.fromisoformat(refused["started_at"]) >= released["now"]
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                    (scope.id,),
                )
            ).fetchone()
            assert row is not None and row["n"] == 60
    finally:
        await asyncio.to_thread(_stop, first.process)
        if second:
            await asyncio.to_thread(_stop, second.process)


async def test_same_key_on_two_monitors_waits_and_returns_binding_conflict(db: Database) -> None:
    scope, monitor = await normal_monitor(db)
    second_monitor = str(uuid4())
    async with db.transaction() as connection:
        await connection.execute(
            "INSERT INTO monitors(id,workspace_id,name,target_kind,target_url) "
            "VALUES(%s,%s,'Portal editorial','normal','https://example.com/')",
            (second_monitor, scope.id),
        )
    key = str(uuid4())
    first = await worker(db, scope, monitor, "hold", key)
    second = None
    try:
        locked = await first.next()
        second = await worker(db, scope, second_monitor, "key-wait", key)
        waiting = await second.next()
        await blocked_by(db, waiting["pid"], locked["pid"])
        first.release()
        assert (await first.next())["accepted"]
        refused = await second.next()
        assert not refused["accepted"] and refused["code"] == "IDEMPOTENCY_CONFLICT"
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                    (scope.id,),
                )
            ).fetchone()
            assert row is not None and row["n"] == 1
    finally:
        await asyncio.to_thread(_stop, first.process)
        if second:
            await asyncio.to_thread(_stop, second.process)
