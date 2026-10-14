import json
import subprocess
import sys
from io import StringIO

import pytest

from scripts.install_monitor import read_monitor


def test_monitor_stdin_accepts_only_the_documented_typed_fields() -> None:
    fields = {
        "name": "Portal editorial",
        "target_url": "https://example.com/",
        "interval_seconds": 60,
    }
    assert read_monitor(StringIO(json.dumps(fields))).interval_seconds == 60
    for invalid in [fields | {"extra": True}, fields | {"interval_seconds": True}, {}, []]:
        with pytest.raises(ValueError):
            read_monitor(StringIO(json.dumps(invalid)))


def test_actual_install_cli_rejects_credentials_in_url_without_logging_them() -> None:
    password = "fixture-secret-not-a-real-credential"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.install_monitor"],
        input=json.dumps(
            {
                "name": "Portal editorial",
                "target_url": f"https://user:{password}@example.com/",
                "interval_seconds": 60,
            }
        ),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert password not in result.stdout + result.stderr
    assert "TargetRejected" in result.stderr
