import asyncio
import hashlib
import re
from pathlib import Path

from sonda.db import Database


def _sources() -> list[tuple[str, bytes]]:
    directory = Path(__file__).resolve().parent.parent / "database" / "migrations"
    return [
        (file.name, file.read_bytes())
        for file in sorted(directory.iterdir())
        if re.fullmatch(r"\d{3}_[a-z_]+\.sql", file.name)
    ]


async def migrate(db: Database) -> None:
    sources = await asyncio.to_thread(_sources)
    async with db.transaction() as connection:
        await connection.execute(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(current_database() || ':' || current_schema() || ':migrations',0))"
        )
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, hash text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        for version, contents in sources:
            digest = hashlib.sha256(contents).hexdigest()
            existing = await (
                await connection.execute(
                    "SELECT hash FROM schema_migrations WHERE version=%s", (version,)
                )
            ).fetchone()
            if existing is not None:
                if existing["hash"] != digest:
                    raise ValueError(f"Applied migration changed: {version}")
                continue
            await connection.execute(contents.decode("utf-8"), prepare=False)
            await connection.execute(
                "INSERT INTO schema_migrations(version,hash) VALUES(%s,%s)", (version, digest)
            )
