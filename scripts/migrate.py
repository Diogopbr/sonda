import asyncio
import os
import sys

from sonda.config import Settings
from sonda.db import Database
from sonda.migrate import migrate


def main() -> None:
    try:
        asyncio.run(
            migrate(Database(Settings.from_env(os.environ))),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except Exception as error:
        print(f"Migration failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print("Migrations aplicadas.")


if __name__ == "__main__":
    main()
