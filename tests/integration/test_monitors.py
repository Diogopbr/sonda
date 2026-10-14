from uuid import uuid4

import pytest

from sonda.checks.service import CheckService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.monitors.service import MonitorService
from sonda.targets.fetcher import FetchOutcome
from tests.integration.test_checks import demo_monitors
from tests.integration.test_claim_concurrency import normal_monitor


async def test_scenario_and_pause_are_versioned_and_abandon_pending_without_failure(
    db: Database,
) -> None:
    scope, monitors = await demo_monitors(db)
    service = MonitorService(db)
    original = await service.get(scope, monitors[0])
    checks = CheckService(db)
    claimed = await checks.claim(scope, monitors[0], str(uuid4()))
    changed = await service.change(
        scope, monitors[0], original["version"], fixture_mode="unavailable"
    )
    assert changed["fixture_mode"] == "unavailable" and changed["observed_state"] == "unknown"
    assert changed["failure_streak"] == 0 and changed["last_check"] is None
    assert (await checks.get_check(scope, claimed.id)).state == "abandoned"
    with pytest.raises(HttpError) as stale:
        await service.change(scope, monitors[0], original["version"], enabled=False)
    assert (
        stale.value.code == "VERSION_CONFLICT"
        and stale.value.current["version"] == changed["version"]
    )
    with pytest.raises(HttpError) as late:
        await checks.finish(scope, claimed, FetchOutcome(503, 1, "HTTP_STATUS"))
    assert late.value.status_code == 410
    paused = await service.change(scope, monitors[0], changed["version"], enabled=False)
    assert not paused["enabled"]
    with pytest.raises(HttpError) as refused:
        await checks.claim(scope, monitors[0], str(uuid4()))
    assert refused.value.code == "MONITOR_PAUSED"
    assert len((await service.get(scope, monitors[0]))["checks"]) == 1


async def test_normal_targets_are_immutable_in_scenario_change_and_last_result_is_real(
    db: Database,
) -> None:
    scope, monitor = await normal_monitor(db)
    service = MonitorService(db)
    with pytest.raises(HttpError) as rejected:
        await service.change(scope, monitor, 1, fixture_mode="available")
    assert rejected.value.status_code == 422
    checks = CheckService(db)
    claimed = await checks.claim(scope, monitor, str(uuid4()))
    await checks.finish(scope, claimed, FetchOutcome(200, 14, None))
    projection = await service.get(scope, monitor)
    assert (
        projection["observed_state"] == "healthy" and projection["last_check"]["duration_ms"] == 14
    )
    assert projection["version"] == 2 and projection["active_incident"] is None
