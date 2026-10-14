from dataclasses import replace

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from sonda.config import Settings
from sonda.http.gateway import GatewayMiddleware


def settings() -> Settings:
    return Settings.from_env(
        {
            "APP_URL": "http://127.0.0.1:5097",
            "DATABASE_URL": "postgresql://sonda_test:fixture@127.0.0.1/sonda_test",
            "SESSION_SECRET": "session-fixture-only-" + "a" * 32,
            "PROBE_SECRET": "probe-fixture-only-" + "b" * 32,
        }
    )


def app(config: Settings) -> FastAPI:
    result = FastAPI()
    result.add_middleware(GatewayMiddleware, settings=config)

    @result.get("/probe")
    async def probe(request: Request) -> dict[str, object]:
        return {
            "ip": request.client.host if request.client else None,
            "host": request.headers.get("x-forwarded-host"),
            "forwarded": request.headers.get("forwarded"),
        }

    return result


async def test_direct_requests_cannot_choose_proxy_identity_or_forwarded_host() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app(settings())), base_url="http://local"
    ) as c:
        response = await c.get(
            "/probe",
            headers={
                "X-Forwarded-For": "203.0.113.15",
                "X-Forwarded-Host": "attacker.example",
                "Forwarded": "for=203.0.113.15;host=attacker.example",
            },
        )
        assert response.json() == {"ip": "127.0.0.1", "host": None, "forwarded": None}


async def test_verified_platform_ingress_has_one_ip_and_removes_ambiguous_headers() -> None:
    config = replace(settings(), trust_vercel_ingress=True, vercel_runtime=True)
    async with AsyncClient(transport=ASGITransport(app=app(config)), base_url="https://local") as c:
        response = await c.get(
            "/probe",
            headers={
                "X-Vercel-Forwarded-For": "203.0.113.15",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "attacker.example",
                "Forwarded": "for=10.0.0.1",
            },
        )
        assert response.json() == {"ip": "203.0.113.15", "host": None, "forwarded": None}
        bad = await c.get(
            "/probe",
            headers={
                "X-Vercel-Forwarded-For": "203.0.113.15,10.0.0.1",
                "X-Forwarded-Proto": "https",
            },
        )
        assert bad.status_code == 400


async def test_ingress_flag_without_platform_marker_is_unavailable() -> None:
    config = replace(settings(), trust_vercel_ingress=True)
    async with AsyncClient(transport=ASGITransport(app=app(config)), base_url="https://local") as c:
        response = await c.get("/probe")
        assert response.status_code == 503
