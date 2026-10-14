import argparse
import asyncio
import os
import sys

from sonda.config import Settings
from sonda.db import Database
from sonda.runner import run_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Run due Sonda monitors once")
    parser.add_argument("--once", required=True, action="store_true")
    parser.add_argument("--batch", type=int, default=10)
    arguments = parser.parse_args()
    try:
        report = asyncio.run(
            run_due(Database(Settings.from_env(os.environ)), batch=arguments.batch),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except Exception as error:
        print(f"Runner failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        f"Aceitas: {report.claimed}; finalizadas: {report.finished}; "
        f"substituídas: {report.superseded}."
    )


if __name__ == "__main__":
    main()
