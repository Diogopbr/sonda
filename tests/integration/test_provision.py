from dataclasses import replace

import pytest

from sonda.db import Database
from sonda.monitors.provision import MonitorSpec, install_monitor
from tests.integration.test_claim_concurrency import normal_monitor


async def test_authorized_normal_monitor_is_unknown_idempotent_and_target_immutable(
    db: Database,
) -> None:
    await normal_monitor(db)
    runtime = Database(replace(db.settings, allowed_hosts=frozenset({"example.com"})), db.schema)
    spec = MonitorSpec("Portal editorial", "https://EXAMPLE.com:443/", 60)
    first = await install_monitor(runtime, spec)
    assert (await install_monitor(runtime, spec)) == first
    for spec in [
        MonitorSpec("Portal editorial", "https://example.com/changed", 60),
        MonitorSpec("Outro serviço", "https://127.0.0.1/", 60),
        MonitorSpec("Outro serviço", "http://example.com/", 60),
        MonitorSpec("Outro serviço", "https://unapproved.example/", 60),
    ]:
        with pytest.raises(ValueError):
            await install_monitor(runtime, spec)
    async with db.connection() as connection:
        row = await (
            await connection.execute("SELECT * FROM monitors WHERE id=%s", (first["id"],))
        ).fetchone()
        assert (
            row is not None and row["observed_state"] == "unknown" and row["last_check_id"] is None
        )
        assert row["target_url"] == "https://example.com/"


@pytest.mark.parametrize(
    "values",
    [
        ("ab", "https://example.com/", 60),
        ("Nome válido", "https://example.com/", 59),
        ("Nome válido", "https://example.com/", True),
    ],
)
def test_monitor_provision_input_is_bounded_and_typed(values) -> None:
    with pytest.raises(ValueError):
        MonitorSpec(*values)
