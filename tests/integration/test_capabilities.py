from dataclasses import replace

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app


async def test_entry_capabilities_expose_only_enabled_access_modes_without_database_query(
    db: Database,
) -> None:
    settings = replace(db.settings, demo_enabled=False, login_enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings, db)), base_url=settings.app_url
    ) as client:
        response = await client.get("/api/capabilities")
        assert response.status_code == 200
        assert response.json() == {"demo_enabled": False, "login_enabled": True}
        assert response.headers["cache-control"] == "no-store"
