from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, UniqueViolation

from sonda.checks.service import CheckService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.incidents.service import IncidentService
from sonda.targets.fetcher import FetchOutcome
from tests.integration.test_claim_concurrency import normal_monitor


async def finish(db, scope, monitor, healthy):
    service = CheckService(db)
    claim = await service.claim(scope, monitor, str(uuid4()))
    return await service.finish(
        scope, claim, FetchOutcome(200 if healthy else 503, 7, None if healthy else "HTTP_STATUS")
    )


async def current(db, monitor):
    async with db.connection() as connection:
        return await (
            await connection.execute("SELECT * FROM monitors WHERE id=%s", (monitor,))
        ).fetchone()


async def test_failures_open_one_incident_and_two_consecutive_successes_resolve(
    db: Database,
) -> None:
    scope, monitor = await normal_monitor(db)
    await finish(db, scope, monitor, True)
    first_failure = await finish(db, scope, monitor, False)
    assert (await current(db, monitor))["observed_state"] == "healthy"
    second_failure = await finish(db, scope, monitor, False)
    assert (await current(db, monitor))["observed_state"] == "unavailable"
    async with db.connection() as connection:
        incident = await (
            await connection.execute("SELECT * FROM incidents WHERE monitor_id=%s", (monitor,))
        ).fetchone()
    assert incident is not None
    assert incident["first_failure_at"] == first_failure.finished_at
    assert incident["confirmed_at"] == second_failure.finished_at
    await finish(db, scope, monitor, False)
    await finish(db, scope, monitor, True)
    await finish(db, scope, monitor, False)
    service = IncidentService(db)
    still_open = await service.get(scope, str(incident["id"]))
    assert still_open["state"] == "open"
    await finish(db, scope, monitor, True)
    recovered = await finish(db, scope, monitor, True)
    resolved = await service.get(scope, str(incident["id"]))
    assert resolved["state"] == "resolved" and resolved["resolution_check_id"] == recovered.id
    assert (await current(db, monitor))["observed_state"] == "healthy"
    async with db.connection() as connection:
        rows = await (
            await connection.execute("SELECT * FROM incidents WHERE monitor_id=%s", (monitor,))
        ).fetchall()
        assert len(rows) == 1
        types = await (
            await connection.execute(
                "SELECT type FROM events WHERE incident_id=%s ORDER BY occurred_at",
                (incident["id"],),
            )
        ).fetchall()
        assert [row["type"] for row in types] == ["INCIDENT_OPENED", "INCIDENT_RESOLVED"]


async def test_acknowledgement_is_versioned_keeps_incident_open_and_resolved_is_readonly(
    db: Database,
) -> None:
    scope, monitor = await normal_monitor(db)
    await finish(db, scope, monitor, False)
    await finish(db, scope, monitor, False)
    async with db.connection() as connection:
        incident = await (
            await connection.execute(
                "SELECT id,version FROM incidents WHERE monitor_id=%s", (monitor,)
            )
        ).fetchone()
    assert incident is not None
    service = IncidentService(db)
    acknowledged = await service.acknowledge(
        scope,
        str(incident["id"]),
        "Investigando a resposta do serviço.\nRevisando o proxy.",
        incident["version"],
    )
    assert (
        acknowledged["state"] == "acknowledged"
        and acknowledged["acknowledged_by"]["id"] == scope.user_id
    )
    assert (await current(db, monitor))["observed_state"] == "unavailable"
    with pytest.raises(HttpError) as stale:
        await service.acknowledge(
            scope, str(incident["id"]), "Rascunho de outra aba.", incident["version"]
        )
    assert stale.value.code == "VERSION_CONFLICT" and stale.value.current == acknowledged
    await finish(db, scope, monitor, True)
    await finish(db, scope, monitor, True)
    resolved = await service.get(scope, str(incident["id"]))
    with pytest.raises(HttpError) as readonly:
        await service.acknowledge(
            scope, str(incident["id"]), "Outro comentário.", resolved["version"]
        )
    assert readonly.value.code == "INCIDENT_READONLY"
    for comment in ["ab", " " * 10, "x" * 501]:
        with pytest.raises(HttpError) as invalid:
            await service.acknowledge(scope, str(incident["id"]), comment, resolved["version"])
        assert invalid.value.status_code == 422


async def test_event_failure_rolls_back_result_monitor_and_incident(db: Database) -> None:
    scope, monitor = await normal_monitor(db)
    await finish(db, scope, monitor, False)
    service = CheckService(db)
    claim = await service.claim(scope, monitor, str(uuid4()))
    before = await current(db, monitor)
    async with db.transaction() as connection:
        await connection.execute("""
            CREATE FUNCTION fail_incident_event() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'controlled event failure' USING ERRCODE='23514'; END; $$;
            CREATE TRIGGER controlled_event_failure BEFORE INSERT ON events
              FOR EACH ROW EXECUTE FUNCTION fail_incident_event();
        """)
    with pytest.raises(CheckViolation):
        await service.finish(scope, claim, FetchOutcome(503, 4, "HTTP_STATUS"))
    assert await current(db, monitor) == before
    assert (await service.get_check(scope, claim.id)).state == "pending"
    async with db.connection() as connection:
        assert not await (
            await connection.execute("SELECT 1 FROM incidents WHERE monitor_id=%s", (monitor,))
        ).fetchone()


async def test_unique_active_incident_and_append_only_events(db: Database) -> None:
    scope, monitor = await normal_monitor(db)
    await finish(db, scope, monitor, False)
    await finish(db, scope, monitor, False)
    async with db.connection() as connection:
        incident = await (
            await connection.execute("SELECT * FROM incidents WHERE monitor_id=%s", (monitor,))
        ).fetchone()
        event = await (
            await connection.execute("SELECT id FROM events WHERE monitor_id=%s", (monitor,))
        ).fetchone()
    assert incident is not None and event is not None
    with pytest.raises(UniqueViolation):
        async with db.transaction() as connection:
            await connection.execute(
                "INSERT INTO incidents(id,workspace_id,monitor_id,first_failure_at,confirmed_at,"
                "first_failure_check_id,confirmation_check_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    scope.id,
                    monitor,
                    incident["first_failure_at"],
                    incident["confirmed_at"],
                    incident["first_failure_check_id"],
                    incident["confirmation_check_id"],
                ),
            )
    for sql in ["UPDATE events SET payload='{}' WHERE id=%s", "DELETE FROM events WHERE id=%s"]:
        with pytest.raises(CheckViolation):
            async with db.transaction() as connection:
                await connection.execute(sql, (event["id"],))
    async with db.transaction() as connection:
        await connection.execute("DELETE FROM workspaces WHERE id=%s", (scope.id,))
