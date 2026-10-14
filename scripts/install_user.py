import asyncio
import json
import os
import sys
from typing import TextIO

from sonda.access.normal import Credentials, install_normal
from sonda.config import Settings
from sonda.db import Database


def read_credentials(stream: TextIO) -> Credentials:
    raw = stream.read(16385)
    try:
        if len(raw) > 16384:
            raise ValueError
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"email", "name", "password"}
            or not all(isinstance(value, str) for value in payload.values())
        ):
            raise ValueError
        return Credentials(**payload)
    except (ValueError, TypeError):
        raise ValueError("Expected bounded JSON with email, name and password") from None


def main() -> None:
    try:
        credentials = read_credentials(sys.stdin)
        scope = asyncio.run(
            install_normal(Database(Settings.from_env(os.environ)), credentials),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except Exception as error:
        print(f"Installation failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Operador configurado no ambiente {scope.id}. Sessões anteriores revogadas.")


if __name__ == "__main__":
    main()
