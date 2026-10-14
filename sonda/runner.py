import asyncio
from dataclasses import dataclass

from sonda.access.scope import Scope
from sonda.checks.execution import ExecutionService, Fetcher
from sonda.checks.models import Claim
from sonda.db import Database
from sonda.http.errors import HttpError


@dataclass(frozen=True)
class RunnerReport:
    claimed: int = 0
    finished: int = 0
    superseded: int = 0


async def run_due(db: Database, *, batch: int = 10, fetcher: Fetcher | None = None) -> RunnerReport:
    if not 1 <= batch <= 10:
        raise ValueError("Runner batch must be between1 and10")
    async with db.connection() as connection:
        row = await (
            await connection.execute(
                "SELECT w.id,u.id AS user_id FROM workspaces w JOIN users u ON u.workspace_id=w.id "
                "WHERE w.kind='normal' AND w.revoked_at IS NULL ORDER BY u.id LIMIT 1"
            )
        ).fetchone()
    if row is None:
        return RunnerReport()
    scope = Scope(str(row["id"]), str(row["user_id"]), "normal", None)
    execution = ExecutionService(db, fetcher=fetcher)
    claims = await execution.checks.claim_due(scope, batch)
    slots = asyncio.Semaphore(4)

    async def execute(claim: Claim) -> bool:
        async with slots:
            try:
                await execution.execute_claimed(scope, claim)
                return True
            except HttpError as error:
                if error.status_code in {404, 410}:
                    return False
                raise

    results = await asyncio.gather(*(execute(claim) for claim in claims))
    return RunnerReport(len(claims), sum(results), len(results) - sum(results))
