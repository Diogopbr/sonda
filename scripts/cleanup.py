import argparse
import asyncio
import os
import sys

from sonda.access.cleanup import collect_expired
from sonda.config import Settings
from sonda.db import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect expired Sonda demo environments once")
    parser.add_argument("--batch", type=int, default=10)
    arguments = parser.parse_args()
    try:
        report = asyncio.run(
            collect_expired(
                Database(Settings.from_env(os.environ)), batch=arguments.batch, throttled=False
            ),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except Exception as error:
        print(f"Cleanup failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        f"Ambientes: {report.workspaces}; sessões: {report.sessions}; "
        f"contadores: {report.limits}; coleta concorrente: {report.skipped}."
    )


if __name__ == "__main__":
    main()
