from ipaddress import ip_address

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sonda.config import Settings


class GatewayMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_scope = dict(scope)
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        if self.settings.trust_vercel_ingress:
            if not self.settings.vercel_runtime:
                await JSONResponse(
                    {"error": {"code": "UNAVAILABLE", "message": "Serviço indisponível."}},
                    status_code=503,
                )(scope, receive, send)
                return
            ips = [value for name, value in headers if name.lower() == b"x-vercel-forwarded-for"]
            protocols = [value for name, value in headers if name.lower() == b"x-forwarded-proto"]
            try:
                if len(ips) != 1 or protocols != [b"https"]:
                    raise ValueError()
                verified_ip = str(ip_address(ips[0].decode("ascii")))
            except (ValueError, UnicodeError):
                await JSONResponse(
                    {"error": {"code": "INVALID_GATEWAY", "message": "Origem inválida."}},
                    status_code=400,
                )(scope, receive, send)
                return
            request_scope["client"] = (verified_ip, 0)
            request_scope["scheme"] = "https"
            scope["scheme"] = "https"
        ignored = {
            b"forwarded",
            b"x-forwarded-for",
            b"x-forwarded-proto",
            b"x-forwarded-host",
            b"x-forwarded-port",
            b"x-vercel-forwarded-for",
        }
        request_scope["headers"] = [
            (name, value) for name, value in headers if name.lower() not in ignored
        ]
        await self.app(request_scope, receive, send)
