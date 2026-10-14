import asyncio
import os
import re
import sys
from urllib.parse import urlsplit

from sonda.access.scope import Scope
from sonda.checks import service
from sonda.checks.service import CheckService
from sonda.config import Settings
from sonda.db import Database
from tests.workers.claim_worker import emit, release


async def main() -> None:
    settings = Settings.from_env(os.environ)
    schema, workspace_id, user_id, mode = sys.argv[1:]
    url = urlsplit(settings.database_url)
    if (
        settings.environment != "test"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.path != "/sonda_test"
        or url.username != "sonda_test"
        or not re.fullmatch(r"st_[a-f0-9]{32}", schema)
    ):
        raise RuntimeError("Runner worker requires an owned isolated test schema")
    db = Database(settings, schema)
    original = service._claim_locked_monitor
    waiting = mode == "hold"

    async def observed(connection, scope, monitor, key, origin):
        nonlocal waiting
        if waiting:
            waiting = False
            emit("locked", pid=connection.info.backend_pid)
            await release()
        return await original(connection, scope, monitor, key, origin)

    service._claim_locked_monitor = observed
    claims = await CheckService(db).claim_due(Scope(workspace_id, user_id, "normal", None))
    emit("result", ids=[claim.id for claim in claims])


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    except Exception as error:
        emit("worker-error", type=type(error).__name__)
        raise SystemExit(1) from None
