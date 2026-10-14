import asyncio
import json
import os
import sys
from typing import TextIO

from sonda.config import Settings
from sonda.db import Database
from sonda.monitors.provision import MonitorSpec, install_monitor


def read_monitor(stream: TextIO) -> MonitorSpec:
    raw = stream.read(16385)
    try:
        if len(raw) > 16384:
            raise ValueError
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"name", "target_url", "interval_seconds"}
            or not isinstance(payload["name"], str)
            or not isinstance(payload["target_url"], str)
            or type(payload["interval_seconds"]) is not int
        ):
            raise ValueError
        return MonitorSpec(**payload)
    except (ValueError, TypeError):
        raise ValueError(
            "Expected bounded JSON with name, target_url and interval_seconds"
        ) from None


def main() -> None:
    try:
        spec = read_monitor(sys.stdin)
        monitor = asyncio.run(
            install_monitor(Database(Settings.from_env(os.environ)), spec),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except Exception as error:
        print(f"Monitor installation failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Monitor configurado: {monitor['id']}.")


if __name__ == "__main__":
    main()
