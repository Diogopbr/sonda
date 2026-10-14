from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation

from sonda.access.demo import DemoService
from sonda.checks.service import CheckService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.migrate import migrate
from sonda.targets.fetcher import FetchOutcome


async def demo_monitors(db: Database):
    await migrate(db)
    scope = (await DemoService(db).start("c" * 64, "127.0.0.1")).scope
    async with db.connection() as connection:
        monitors = await (
            await connection.execute(
                "SELECT id FROM monitors WHERE workspace_id=%s ORDER BY name",
                (scope.id,),
            )
        ).fetchall()
    return scope, [str(row["id"]) for row in monitors]


async def test_claim_replay_is_bound_to_monitor_and_never_consumes_second_attempt(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    key = str(uuid4())
    claimed = await service.claim(scope, monitors[0], key)
    assert claimed.state == "pending" and not claimed.replayed
    replay = await service.claim(scope, monitors[0], key)
    assert replay.id == claimed.id and replay.replayed and replay.state == "pending"
    with pytest.raises(HttpError) as mismatch:
        await service.claim(scope, monitors[1], key)
    assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(HttpError) as running:
        await service.claim(scope, monitors[0], str(uuid4()))
    assert running.value.code == "CHECK_RUNNING"
    finished = await service.finish(scope, claimed, FetchOutcome(200, 14, None))
    assert finished.state == "finished" and finished.status_code == 200
    replay = await service.claim(scope, monitors[0], key)
    assert replay.replayed and replay.id == claimed.id and replay.state == "finished"
    assert await service.get_check(scope, replay.id) == finished
    async with db.connection() as connection:
        assert (
            await (
                await connection.execute(
                    "SELECT count(*) AS n FROM check_runs WHERE workspace_id=%s",
                    (scope.id,),
                )
            ).fetchone()
        )["n"] == 1
        assert (
            await (
                await connection.execute(
                    "SELECT sum(hits) AS n FROM rate_limits WHERE key=%s",
                    (f"check:visitor:{scope.visitor_id}",),
                )
            ).fetchone()
        )["n"] == 1


async def test_expired_lease_is_abandoned_and_late_finish_cannot_replace_result(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    first = await service.claim(scope, monitors[0], str(uuid4()))
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE monitors SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (monitors[0],),
        )
    with pytest.raises(HttpError) as expired:
        await service.finish(scope, first, FetchOutcome(503, 17, "HTTP_STATUS"))
    assert expired.value.status_code == 410
    second = await service.claim(scope, monitors[0], str(uuid4()))
    assert second.id != first.id
    abandoned = await service.get_check(scope, first.id)
    assert abandoned.state == "abandoned" and abandoned.status_code is None
    with pytest.raises(HttpError) as replaced:
        await service.finish(scope, first, FetchOutcome(200, 9, None))
    assert replaced.value.status_code == 410
    await service.finish(scope, second, FetchOutcome(200, 11, None))


async def test_changed_paused_and_revoked_environment_refuse_finish(db: Database) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    for change in ["version=version+1", "enabled=false"]:
        claimed = await service.claim(scope, monitors[0], str(uuid4()))
        async with db.transaction() as connection:
            await connection.execute(
                "UPDATE monitors SET " + change + " WHERE id=%s", (monitors[0],)
            )
        with pytest.raises(HttpError) as stale:
            await service.finish(scope, claimed, FetchOutcome(200, 3, None))
        assert stale.value.status_code == 410
        async with db.transaction() as connection:
            await connection.execute(
                "UPDATE monitors SET enabled=true,"
                "lease_until=clock_timestamp()-interval '1 second' "
                "WHERE id=%s",
                (monitors[0],),
            )
    claimed = await service.claim(scope, monitors[1], str(uuid4()))
    await DemoService(db).reset(scope, "c" * 64, "127.0.0.1")
    with pytest.raises(HttpError) as reset:
        await service.finish(scope, claimed, FetchOutcome(200, 3, None))
    assert reset.value.status_code == 404


async def test_finished_attempts_are_immutable_but_generation_collection_cascades(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    claimed = await service.claim(scope, monitors[0], str(uuid4()))
    await service.finish(scope, claimed, FetchOutcome(200, 3, None))
    for operation in [
        "UPDATE check_runs SET duration_ms=99 WHERE id=%s",
        "DELETE FROM check_runs WHERE id=%s",
    ]:
        with pytest.raises(CheckViolation):
            async with db.transaction() as connection:
                await connection.execute(operation, (claimed.id,))
    async with db.transaction() as connection:
        await connection.execute("DELETE FROM workspaces WHERE id=%s", (scope.id,))
    async with db.connection() as connection:
        assert not await (
            await connection.execute("SELECT 1 FROM check_runs WHERE id=%s", (claimed.id,))
        ).fetchone()


@pytest.mark.parametrize(
    "outcome",
    [FetchOutcome(None, 1, None), FetchOutcome(503, 1, None), FetchOutcome(200, 1, "HTTP_STATUS")],
)
async def test_incomplete_result_is_rejected_and_keeps_pending_attempt(
    db: Database, outcome: FetchOutcome
) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    claim = await service.claim(scope, monitors[0], str(uuid4()))
    with pytest.raises(CheckViolation):
        await service.finish(scope, claim, outcome)
    assert (await service.get_check(scope, claim.id)).state == "pending"


async def test_failed_monitor_update_rolls_back_the_result(db: Database) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    claim = await service.claim(scope, monitors[0], str(uuid4()))
    async with db.transaction() as connection:
        await connection.execute("""
            CREATE FUNCTION reject_lease_release() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.lease_id IS NULL THEN
                RAISE EXCEPTION 'controlled monitor failure' USING ERRCODE='23514';
              END IF;
              RETURN NEW;
            END; $$;
            CREATE TRIGGER controlled_monitor_failure BEFORE UPDATE ON monitors
              FOR EACH ROW EXECUTE FUNCTION reject_lease_release();
        """)
    with pytest.raises(CheckViolation):
        await service.finish(scope, claim, FetchOutcome(200, 1, None))
    assert (await service.get_check(scope, claim.id)).state == "pending"
    async with db.connection() as connection:
        monitor = await (
            await connection.execute("SELECT lease_id FROM monitors WHERE id=%s", (monitors[0],))
        ).fetchone()
        assert monitor is not None and str(monitor["lease_id"]) == claim.id


async def test_check_ownership_is_verified_and_cross_environment_fk_is_rejected(
    db: Database,
) -> None:
    from psycopg.errors import ForeignKeyViolation

    scope, monitors = await demo_monitors(db)
    other = (await DemoService(db).start("d" * 64, "127.0.0.1")).scope
    service = CheckService(db)
    claim = await service.claim(scope, monitors[0], str(uuid4()))
    for operation in [
        service.claim(other, monitors[0], str(uuid4())),
        service.get_check(other, claim.id),
    ]:
        with pytest.raises(HttpError) as caught:
            await operation
        assert caught.value.status_code == 404
    with pytest.raises(ForeignKeyViolation):
        async with db.transaction() as connection:
            await connection.execute(
                "INSERT INTO check_runs(id,workspace_id,monitor_id,actor_id,client_key,origin,"
                "lease_token,monitor_version,started_at,lease_until) "
                "VALUES(%s,%s,%s,%s,%s,'manual',%s,1,clock_timestamp(),"
                "clock_timestamp()+interval '30 seconds')",
                (uuid4(), other.id, monitors[0], other.user_id, uuid4(), uuid4()),
            )


async def test_check_limit_counts_accepted_attempts_in_current_database_window(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    service = CheckService(db)
    limited = False
    for _ in range(13):
        try:
            claim = await service.claim(scope, monitors[0], str(uuid4()))
        except HttpError as error:
            assert error.code == "RATE_LIMITED" and error.retry_after is not None
            assert 1 <= error.retry_after <= 60
            limited = True
            break
        await service.finish(scope, claim, FetchOutcome(200, 1, None))
    assert limited
    async with db.connection() as connection:
        row = await (
            await connection.execute(
                "SELECT max(hits) AS hits FROM rate_limits WHERE key=%s",
                (f"check:visitor:{scope.visitor_id}",),
            )
        ).fetchone()
        assert row is not None and row["hits"] == 6
