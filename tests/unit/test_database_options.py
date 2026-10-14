import certifi
import pytest

from sonda.config import Settings
from sonda.db import Database


def settings() -> Settings:
    return Settings.from_env(
        {
            "SONDA_ENV": "production",
            "APP_URL": "https://sonda.example",
            "DATABASE_URL": (
                "postgresql://app:fixture-password@db.example/sonda"
                "?sslmode=disable&sslrootcert=wrong&hostaddr=127.0.0.1"
            ),
            "SESSION_SECRET": "session-fixture-only-" + "a" * 32,
            "PROBE_SECRET": "probe-fixture-only-" + "b" * 32,
        }
    )


def test_url_parameters_cannot_override_verified_tls_or_connection_host() -> None:
    options = Database(settings()).connection_options
    assert options["host"] == "db.example"
    assert options["sslmode"] == "verify-full"
    assert options["sslrootcert"] == certifi.where()
    assert options["prepare_threshold"] is None
    assert "hostaddr" not in options
    assert "conninfo" not in options


@pytest.mark.parametrize("schema", ["other", "public;DROP SCHEMA public", 'st_"', "../public"])
def test_schema_selection_rejects_everything_except_public_or_isolated_test_id(schema: str) -> None:
    with pytest.raises(ValueError):
        Database(settings(), schema)
