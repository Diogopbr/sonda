from typing import Protocol

from sonda.access.scope import Scope, with_workspace
from sonda.checks.models import CheckProjection, Claim
from sonda.checks.service import CheckService
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.targets.fetcher import FetchOutcome, SafeFetcher
from sonda.targets.policy import Target, TargetRejected, validate_target


class Fetcher(Protocol):
    async def fetch(self, target: Target) -> FetchOutcome: ...


class ExecutionService:
    def __init__(self, db: Database, *, fetcher: Fetcher | None = None) -> None:
        self.db = db
        self.checks = CheckService(db)
        self.fetcher = fetcher if fetcher is not None else SafeFetcher(db.settings)

    async def execute(self, scope: Scope, monitor_id: str, key: str) -> CheckProjection:
        claim = await self.checks.claim(scope, monitor_id, key)
        return await self.execute_claimed(scope, claim)

    async def execute_claimed(self, scope: Scope, claim: Claim) -> CheckProjection:
        if claim.replayed:
            return await self.checks.get_check(scope, claim.id)
        async with with_workspace(self.db, scope) as connection:
            monitor = await (
                await connection.execute(
                    "SELECT m.target_url,m.target_kind FROM monitors m "
                    "JOIN check_runs c ON c.id=m.lease_id "
                    "WHERE m.workspace_id=%s AND m.id=%s AND m.lease_id=%s AND m.lease_token=%s "
                    "AND m.enabled=true AND m.version=c.monitor_version AND c.actor_id=%s "
                    "AND m.lease_until>clock_timestamp() AND c.state='pending'",
                    (scope.id, claim.monitor_id, claim.id, claim.lease_token, scope.user_id),
                )
            ).fetchone()
            if monitor is None:
                raise HttpError(410, "CHECK_SUPERSEDED", "Esta verificação perdeu a validade.")
        try:
            target = validate_target(
                monitor["target_url"],
                self.db.settings.allowed_hosts,
                self.db.settings.app_url,
                production=self.db.settings.production,
            )
            if monitor["target_kind"] == "normal" and target.internal:
                raise TargetRejected()
        except TargetRejected:
            outcome = FetchOutcome(None, 0, "TARGET_REJECTED")
        else:
            outcome = await self.fetcher.fetch(target)
        return await self.checks.finish(scope, claim, outcome)
