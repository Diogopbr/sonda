from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sonda.config import Settings
from sonda.db import Database
from sonda.http.gateway import GatewayMiddleware
from sonda.http.security import SecurityHeadersMiddleware
from sonda.version import LATEST_MIGRATION


def create_app(settings: Settings, db: Database) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(GatewayMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        try:
            async with db.connection() as connection:
                metadata = await (
                    await connection.execute(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema=current_schema() AND table_name='schema_migrations') "
                        "AS present"
                    )
                ).fetchone()
                if metadata and metadata["present"]:
                    latest = await (
                        await connection.execute(
                            "SELECT 1 FROM schema_migrations WHERE version=%s", (LATEST_MIGRATION,)
                        )
                    ).fetchone()
                    if latest:
                        return JSONResponse({"status": "ready"})
        except Exception:
            pass
        return JSONResponse({"status": "unavailable"}, status_code=503)

    return app
