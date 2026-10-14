from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def attach_assets(app: FastAPI, directory: Path) -> None:
    index = directory / "index.html"
    if not index.is_file():
        return
    for name in ("assets", "fonts"):
        target = directory / name
        if target.is_dir():
            app.mount(f"/{name}", StaticFiles(directory=target), name=name)

    def page() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    @app.get("/services", include_in_schema=False)
    @app.get("/login", include_in_schema=False)
    async def entry() -> FileResponse:
        return page()

    @app.get("/services/{id}", include_in_schema=False)
    @app.get("/incidents/{id}", include_in_schema=False)
    async def detail(id: UUID) -> FileResponse:
        return page()
