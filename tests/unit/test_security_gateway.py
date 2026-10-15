from dataclasses import replace

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app
from tests.unit.test_gateway import settings


async def test_hsts_uses_verified_ingress_without_trusting_direct_headers() -> None:
    config = replace(settings(), trust_vercel_ingress=True, vercel_runtime=True)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(config, Database(config))), base_url="http://local"
    ) as client:
        response = await client.get(
            "/api/capabilities",
            headers={"X-Vercel-Forwarded-For": "203.0.113.15", "X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 200
        assert response.headers["strict-transport-security"] == "max-age=31536000"

    direct = settings()
    async with AsyncClient(
        transport=ASGITransport(app=create_app(direct, Database(direct))), base_url="http://local"
    ) as client:
        response = await client.get("/api/capabilities", headers={"X-Forwarded-Proto": "https"})
        assert "strict-transport-security" not in response.headers
