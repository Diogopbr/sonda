from pathlib import Path

from httpx import ASGITransport, AsyncClient

from sonda.db import Database
from sonda.http.app import create_app


async def test_only_named_app_routes_and_asset_directories_are_served(
    db: Database, tmp_path: Path
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "fonts").mkdir()
    (tmp_path / "index.html").write_text(
        "<html lang='pt-BR'>Sonda fixture</html>", encoding="utf-8"
    )
    (tmp_path / "assets" / "app.js").write_text("export const fixture = true", encoding="utf-8")
    (tmp_path / "fonts" / "source.woff2").write_bytes(b"fixture-font")
    async with AsyncClient(
        transport=ASGITransport(app=create_app(db.settings, db, assets_directory=tmp_path)),
        base_url=db.settings.app_url,
    ) as client:
        for route in [
            "/",
            "/services",
            "/login",
            "/services/00000000-0000-0000-0000-000000000001",
            "/incidents/00000000-0000-0000-0000-000000000001",
        ]:
            response = await client.get(route)
            assert response.status_code == 200 and "Sonda fixture" in response.text
        assert (await client.get("/assets/app.js")).status_code == 200
        assert (await client.get("/fonts/source.woff2")).status_code == 200
        for path in [
            "/README.md",
            "/.env",
            "/frontend/src/App.svelte",
            "/sonda/config.py",
            "/.local/settings.json",
            "/docs/contracts/http.md",
        ]:
            assert (await client.get(path)).status_code == 404
