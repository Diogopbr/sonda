import pytest

from sonda.config import Settings


def production_env() -> dict[str, str]:
    return {
        "SONDA_ENV": "production",
        "APP_URL": "https://sonda.example",
        "DATABASE_URL": "postgresql://app:fixture-password@db.example/sonda?sslmode=disable",
        "DB_TLS": "true",
        "SESSION_SECRET": "session-fixture-only-" + "a" * 32,
        "PROBE_SECRET": "probe-fixture-only-" + "b" * 32,
    }


@pytest.mark.parametrize(
    "override",
    [
        {"APP_URL": "http://sonda.example"},
        {"APP_URL": "https://sonda.example/another-path"},
        {"APP_URL": "https://user:password@sonda.example"},
        {"APP_URL": "https://sonda.example?origin=other"},
        {"DB_TLS": "false"},
        {"DB_TLS": "yes"},
        {"SESSION_SECRET": "short"},
        {"PROBE_SECRET": "session-fixture-only-" + "a" * 32},
        {"SONDA_DEMO_ENABLED": "1"},
        {"SONDA_ENV": "staging"},
        {"DATABASE_URL": "https://db.example/sonda"},
    ],
)
def test_production_rejects_insecure_or_ambiguous_configuration(override: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(production_env() | override)


def test_valid_production_has_no_implicit_public_access_or_secret_repr() -> None:
    settings = Settings.from_env(production_env())
    assert settings.production
    assert settings.database_tls
    assert settings.app_url == "https://sonda.example"
    assert not settings.demo_enabled
    assert not settings.login_enabled
    assert not settings.vercel_runtime
    assert "fixture-password" not in repr(settings)
    assert production_env()["SESSION_SECRET"] not in repr(settings)


def test_platform_runtime_cannot_run_with_development_security_defaults() -> None:
    with pytest.raises(ValueError):
        Settings.from_env(production_env() | {"SONDA_ENV": "development", "VERCEL": "1"})
