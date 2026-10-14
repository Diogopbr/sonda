import hmac
import re
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from sonda.access.cleanup import collect_expired
from sonda.access.demo import DemoService
from sonda.access.normal import LoginService
from sonda.access.scope import Scope
from sonda.access.sessions import IssuedSession, SessionRecord, SessionService
from sonda.config import Settings
from sonda.db import Database
from sonda.http.errors import HttpError
from sonda.monitors.service import MonitorService

SESSION_COOKIE = "sonda_session"
VISITOR_COOKIE = "sonda_visitor"


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)


class Access:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.sessions = SessionService(db)
        self.demo = DemoService(db)
        self.login = LoginService(db)
        self.monitors = MonitorService(db)

    async def current(self, request: Request) -> SessionRecord | None:
        if not hasattr(request.state, "session"):
            request.state.session = await self.sessions.resolve(request.cookies.get(SESSION_COOKIE))
        session: SessionRecord | None = request.state.session
        return session

    async def scope(self, request: Request) -> Scope:
        session = await self.current(request)
        if session is None or session.scope is None:
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
        expected = request.headers.get("x-sonda-workspace")
        if expected is not None and expected != session.scope.id:
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
        return session.scope

    async def authorize(self, request: Request, *, generation: bool = True) -> SessionRecord:
        session = await self.current(request)
        if generation:
            scope = await self.scope(request)
            if request.headers.get("x-sonda-workspace") != scope.id:
                raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
        if (
            session is None
            or request.headers.get("origin") != self.settings.app_url
            or not hmac.compare_digest(
                request.headers.get("x-csrf-token", "").encode(), session.csrf.encode()
            )
        ):
            raise HttpError(419, "CSRF_INVALID", "Atualize o acesso e tente novamente.")
        return session

    def set_session(self, response: JSONResponse, issued: IssuedSession) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            issued.cookie,
            httponly=True,
            secure=self.settings.environment == "production",
            samesite="lax",
            path="/",
        )

    @staticmethod
    def projection(session: SessionRecord) -> dict[str, Any]:
        return {
            "workspace_id": session.scope.id if session.scope else None,
            "kind": session.scope.kind if session.scope else None,
            "expires_at": session.expires_at.isoformat(),
        }


def access_router(access: Access) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/capabilities")
    async def capabilities() -> dict[str, bool]:
        return {
            "demo_enabled": access.settings.demo_enabled,
            "login_enabled": access.settings.login_enabled,
        }

    @router.get("/auth/csrf")
    async def csrf(request: Request) -> JSONResponse:
        session = await access.current(request)
        issued = None
        if session is None:
            issued = await access.sessions.issue(previous=request.cookies.get(SESSION_COOKIE))
            session = issued.record
        response = JSONResponse({"csrf": session.csrf})
        if issued:
            access.set_session(response, issued)
        return response

    @router.get("/auth")
    async def auth(request: Request) -> JSONResponse:
        session = await access.current(request)
        if session is None or session.scope is None:
            raise HttpError(404, "NOT_FOUND", "Ambiente não encontrado ou encerrado.")
        return JSONResponse(access.projection(session))

    @router.post("/demo/start")
    async def start(request: Request) -> JSONResponse:
        if not access.settings.demo_enabled:
            raise HttpError(404, "NOT_FOUND", "Recurso não encontrado.")
        await access.authorize(request, generation=False)
        await collect_expired(access.db)
        token = request.cookies.get(VISITOR_COOKIE, "")
        if not re.fullmatch(r"[a-f0-9]{64}", token):
            token = secrets.token_hex(32)
        workspace = await access.demo.start(
            token, request.client.host if request.client else "unknown"
        )
        issued = await access.sessions.issue(
            workspace.scope, previous=request.cookies.get(SESSION_COOKIE)
        )
        response = JSONResponse(access.projection(issued.record), status_code=201)
        access.set_session(response, issued)
        response.set_cookie(
            VISITOR_COOKIE,
            token,
            httponly=True,
            secure=access.settings.environment == "production",
            samesite="lax",
            path="/",
            max_age=365 * 24 * 3600,
        )
        return response

    @router.post("/demo/reset")
    async def reset(request: Request) -> JSONResponse:
        if not access.settings.demo_enabled:
            raise HttpError(404, "NOT_FOUND", "Recurso não encontrado.")
        await access.authorize(request)
        scope = await access.scope(request)
        workspace = await access.demo.reset(
            scope,
            request.cookies.get(VISITOR_COOKIE, ""),
            request.client.host if request.client else "unknown",
        )
        issued = await access.sessions.issue(
            workspace.scope, previous=request.cookies.get(SESSION_COOKIE)
        )
        response = JSONResponse(access.projection(issued.record), status_code=201)
        access.set_session(response, issued)
        return response

    @router.post("/auth/logout")
    async def logout(request: Request) -> JSONResponse:
        await access.authorize(request)
        await access.sessions.destroy(request.cookies.get(SESSION_COOKIE))
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(
            SESSION_COOKIE,
            httponly=True,
            secure=access.settings.environment == "production",
            samesite="lax",
        )
        return response

    @router.post("/auth/login")
    async def login(request: Request) -> JSONResponse:
        if not access.settings.login_enabled:
            raise HttpError(404, "NOT_FOUND", "Recurso não encontrado.")
        await access.authorize(request, generation=False)
        try:
            body = LoginInput.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HttpError(422, "INPUT_INVALID", "Confira os campos de acesso.") from None
        issued = await access.login.login(
            body.email,
            body.password.get_secret_value(),
            request.client.host if request.client else "unknown",
            previous=request.cookies.get(SESSION_COOKIE),
        )
        response = JSONResponse(access.projection(issued.record))
        access.set_session(response, issued)
        return response

    @router.get("/monitors")
    async def monitors(request: Request) -> dict[str, Any]:
        scope = await access.scope(request)
        return {"monitors": await access.monitors.list(scope)}

    @router.get("/monitors/{monitor_id}")
    async def monitor(request: Request, monitor_id: UUID) -> dict[str, Any]:
        scope = await access.scope(request)
        return await access.monitors.get(scope, str(monitor_id))

    return router
