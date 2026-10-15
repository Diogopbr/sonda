import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import uvicorn
from psycopg import AsyncConnection, sql

from sonda.config import Settings
from sonda.db import Database
from sonda.http.app import create_app
from sonda.migrate import migrate

ROOT = Path(__file__).resolve().parents[1]


def settings_for(port: int) -> Settings:
    environment = dict(os.environ)
    url = environment.get("SONDA_TEST_DATABASE_URL", "")
    if not url:
        private = json.loads((ROOT / ".local" / "settings.json").read_text(encoding="utf-8-sig"))
        url = (
            f"postgresql://{quote(private['testUsername'], safe='')}:"
            f"{quote(private['testPassword'], safe='')}@{private['host']}:"
            f"{private['port']}/{private['testDatabase']}"
        )
        environment["SESSION_SECRET"] = private["sessionSecret"]
        environment["PROBE_SECRET"] = private["probeSecret"]
    parsed = urlsplit(url)
    if (
        parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path != "/sonda_test"
        or parsed.username != "sonda_test"
    ):
        raise RuntimeError("Browser tests require isolated local sonda_test")
    return Settings.from_env(
        environment
        | {
            "SONDA_ENV": "test",
            "DATABASE_URL": url,
            "DB_TLS": "false",
            "APP_URL": f"http://127.0.0.1:{port}",
            "PORT": str(port),
            "SONDA_DEMO_ENABLED": "true",
            "SONDA_LOGIN_ENABLED": "false",
            "TRUST_VERCEL_INGRESS": "false",
        }
    )


def metadata(schema: str) -> Path:
    if not re.fullmatch(r"st_[a-f0-9]{32}", schema):
        raise ValueError("Refusing an unowned browser schema")
    return ROOT / ".local" / "e2e-owned" / f"{schema}.json"


async def setup(settings: Settings, schema: str) -> None:
    record = metadata(schema)
    async with await AsyncConnection.connect(
        **Database(settings).connection_options, autocommit=True
    ) as connection:
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"schema": schema, "pid": os.getpid()}), encoding="utf-8")
    await migrate(Database(settings, schema))


async def cleanup(settings: Settings, schema: str) -> None:
    record = metadata(schema)
    if not record.is_file():
        return
    owner = json.loads(record.read_text(encoding="utf-8"))
    if owner.get("schema") != schema:
        raise RuntimeError("Browser schema ownership mismatch")
    async with await AsyncConnection.connect(
        **Database(settings).connection_options, autocommit=True
    ) as connection:
        await connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )
    record.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated Sonda browser-test server")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--port", type=int, default=5117)
    parser.add_argument("--cleanup", action="store_true")
    arguments = parser.parse_args()
    settings = settings_for(arguments.port)
    metadata(arguments.schema)
    if arguments.cleanup:
        asyncio.run(cleanup(settings, arguments.schema), loop_factory=asyncio.SelectorEventLoop)
        return
    try:
        asyncio.run(setup(settings, arguments.schema), loop_factory=asyncio.SelectorEventLoop)
        app = create_app(
            settings, Database(settings, arguments.schema), assets_directory=ROOT / "web_dist"
        )
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=arguments.port,
            loop="sonda.runtime:selector_loop",
            proxy_headers=False,
        )
    finally:
        asyncio.run(cleanup(settings, arguments.schema), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Browser server failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
