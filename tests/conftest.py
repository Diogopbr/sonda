import asyncio
import os
import re
import sys
from collections.abc import AsyncIterator
from urllib.parse import urlsplit
from uuid import uuid4

import pytest_asyncio
from psycopg import AsyncConnection, sql

from sonda.config import Settings
from sonda.db import Database

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    url = os.environ.get("SONDA_TEST_DATABASE_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path != "/sonda_test"
        or parsed.username != "sonda_test"
    ):
        raise RuntimeError("Tests require the isolated local sonda_test database and role")
    settings = Settings.from_env(dict(os.environ) | {"DATABASE_URL": url, "SONDA_ENV": "test"})
    schema = "st_" + uuid4().hex
    async with await AsyncConnection.connect(url, autocommit=True, sslmode="disable") as connection:
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield Database(settings, schema)
    finally:
        if not re.fullmatch(r"st_[a-f0-9]{32}", schema):
            raise RuntimeError("Refusing to clean an unowned test schema")
        async with await AsyncConnection.connect(
            url, autocommit=True, sslmode="disable"
        ) as connection:
            await connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
