from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app
from sonda.migrate import migrate
from tests.integration.test_access_http import start_demo


async def headers(client: AsyncClient, workspace: str) -> dict[str, str]:
    return {
        "Origin": str(client.base_url).rstrip("/"),
        "X-Sonda-Workspace": workspace,
        "X-CSRF-Token": (await client.get("/api/auth/csrf")).json()["csrf"],
    }


async def test_product_commands_validate_generation_and_body_before_mutating(db: Database) -> None:
    await migrate(db)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(db.settings, db)), base_url=db.settings.app_url
    ) as client:
        access = await start_demo(client)
        monitor = (await client.get("/api/monitors")).json()["monitors"][0]
        id = monitor["id"]
        command_headers = await headers(client, access["workspace_id"])
        forbidden = await client.patch(
            f"/api/monitors/{id}",
            headers=command_headers,
            json={"expected_version": 1, "target_url": "https://private.invalid/"},
        )
        assert forbidden.status_code == 422
        changed = await client.patch(
            f"/api/monitors/{id}",
            headers=command_headers,
            json={"expected_version": 1, "fixture_mode": "unavailable"},
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2
        stale = await client.patch(
            f"/api/monitors/{id}",
            headers=command_headers,
            json={"expected_version": 1, "enabled": False},
        )
        assert stale.status_code == 409 and stale.json()["error"]["current"]["version"] == 2
        invalid_key = await client.post(
            f"/api/monitors/{id}/checks", headers=command_headers, json={"key": "z" * 36}
        )
        assert invalid_key.status_code == 422
        wrong_read = await client.get("/api/monitors", headers={"X-Sonda-Workspace": str(uuid4())})
        assert wrong_read.status_code == 404
        malformed = await client.get("/api/monitors/not-a-uuid")
        assert malformed.status_code == 422 and malformed.json()["error"]["code"] == "INPUT_INVALID"
        command_headers["X-Sonda-Workspace"] = str(uuid4())
        generation = await client.patch(
            f"/api/monitors/{id}", headers=command_headers, content=b"invalid json"
        )
        assert generation.status_code == 404
        assert (await client.get(f"/api/monitors/{id}")).json()["enabled"]
