from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from sonda.config import Settings
from sonda.db import Database
from sonda.http.access import Access, access_router
from sonda.http.body import BodyLimitMiddleware
from sonda.http.errors import HttpError, error_response
from sonda.http.gateway import GatewayMiddleware
from sonda.http.probe import probe_router
from sonda.http.product import product_router
from sonda.http.security import SecurityHeadersMiddleware
from sonda.version import LATEST_MIGRATION


def create_app(settings: Settings, db: Database) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(GatewayMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware)
    access = Access(settings, db)
    app.include_router(access_router(access))
    app.include_router(product_router(access))
    app.include_router(probe_router(settings, db))

    @app.exception_handler(HttpError)
    async def domain_error(request: Request, error: HttpError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(HttpError(422, "INPUT_INVALID", "Confira os campos da requisição."))

    @app.middleware("http")
    async def private_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/probe/")):
            response.headers["Cache-Control"] = "no-store"
        return response

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
