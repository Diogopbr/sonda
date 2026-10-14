import hmac
from uuid import UUID

from fastapi import APIRouter, Request
from starlette.responses import Response

from sonda.config import Settings
from sonda.db import Database
from sonda.http.errors import HttpError


def probe_router(settings: Settings, db: Database) -> APIRouter:
    router = APIRouter()

    @router.get("/probe/{monitor_id}")
    async def probe(request: Request, monitor_id: str) -> Response:
        if not settings.demo_enabled or not hmac.compare_digest(
            request.headers.get("x-sonda-probe", "").encode(), settings.probe_secret.encode()
        ):
            raise HttpError(404, "NOT_FOUND", "Alvo não encontrado.")
        try:
            id = UUID(monitor_id)
        except ValueError:
            raise HttpError(404, "NOT_FOUND", "Alvo não encontrado.") from None
        async with db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT m.fixture_mode FROM monitors m "
                    "JOIN workspaces w ON w.id=m.workspace_id "
                    "WHERE m.id=%s AND m.target_kind='fixture' AND w.kind='demo' "
                    "AND w.revoked_at IS NULL AND w.expires_at>clock_timestamp()",
                    (id,),
                )
            ).fetchone()
        if row is None:
            raise HttpError(404, "NOT_FOUND", "Alvo não encontrado.")
        return Response(
            status_code=200 if row["fixture_mode"] == "available" else 503,
            headers={"Cache-Control": "no-store"},
        )

    return router
