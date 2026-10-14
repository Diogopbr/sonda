import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import unquote, urlsplit

import certifi
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from sonda.config import Settings


class Database:
    def __init__(self, settings: Settings, schema: str = "public") -> None:
        if schema != "public" and not re.fullmatch(r"st_[a-f0-9]{32}", schema):
            raise ValueError("Schema must be public or an isolated st_ test schema")
        self.settings = settings
        self.schema = schema
        self._slots = asyncio.Semaphore(4)

    @property
    def connection_options(self) -> dict[str, Any]:
        url = urlsplit(self.settings.database_url)
        options: dict[str, Any] = {
            "host": url.hostname,
            "port": url.port or 5432,
            "dbname": unquote(url.path[1:]),
            "user": unquote(url.username or ""),
            "password": unquote(url.password or ""),
            "sslmode": "verify-full" if self.settings.database_tls else "disable",
            "connect_timeout": 5,
            "prepare_threshold": None,
        }
        if self.settings.database_tls:
            options["sslrootcert"] = certifi.where()
        return options

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
        async with self._slots:
            connection = await AsyncConnection.connect(
                **self.connection_options, row_factory=dict_row
            )
            try:
                await connection.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
                )
                await connection.execute("SET statement_timeout = '5s'")
                await connection.commit()
                yield connection
            finally:
                await connection.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
        async with self.connection() as connection, connection.transaction():
            yield connection
