from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sonda.targets.policy import canonical_host


def _boolean(environ: Mapping[str, str], name: str, default: bool) -> bool:
    value = environ.get(name)
    if value is None:
        return default
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class Settings:
    environment: str
    app_url: str
    database_url: str = field(repr=False)
    database_tls: bool
    session_secret: str = field(repr=False)
    probe_secret: str = field(repr=False)
    demo_enabled: bool
    login_enabled: bool
    trust_vercel_ingress: bool
    vercel_runtime: bool
    port: int
    allowed_hosts: frozenset[str] = frozenset()

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        environment = environ.get("SONDA_ENV", "development")
        if environment not in {"development", "test", "production"}:
            raise ValueError("SONDA_ENV must be development, test or production")
        production = environment == "production"
        if environ.get("VERCEL") == "1" and not production:
            raise ValueError("Vercel runtime requires SONDA_ENV=production")
        app_url = environ.get("APP_URL", "")
        try:
            origin = urlsplit(app_url)
            if (
                any(ord(character) < 32 for character in app_url)
                or origin.scheme not in {"http", "https"}
                or not origin.hostname
                or origin.username is not None
                or origin.password is not None
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
                or (origin.port is not None and not 1 <= origin.port <= 65535)
                or (production and origin.scheme != "https")
            ):
                raise ValueError()
        except ValueError as error:
            raise ValueError("APP_URL must be an HTTP origin; production requires HTTPS") from error
        database_url = environ.get("DATABASE_URL", "")
        try:
            database = urlsplit(database_url)
            if (
                any(ord(character) < 32 for character in database_url)
                or database.scheme not in {"postgres", "postgresql"}
                or not database.hostname
                or not database.username
                or len(database.path) < 2
                or database.fragment
                or (database.port is not None and not 1 <= database.port <= 65535)
            ):
                raise ValueError()
        except ValueError as error:
            raise ValueError("DATABASE_URL must identify a PostgreSQL database and role") from error
        tls = _boolean(environ, "DB_TLS", production)
        if production and not tls:
            raise ValueError("Production requires verified database TLS")
        session_secret = environ.get("SESSION_SECRET", "")
        probe_secret = environ.get("PROBE_SECRET", "")
        if min(len(session_secret), len(probe_secret)) < 32 or session_secret == probe_secret:
            raise ValueError(
                "SESSION_SECRET and PROBE_SECRET must be distinct and at least 32 characters"
            )
        try:
            port = int(environ.get("PORT", "5095"))
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError as error:
            raise ValueError("PORT must be an integer between 1 and 65535") from error
        assert origin.hostname is not None
        try:
            host = (
                canonical_host(origin.hostname)
                if production
                else origin.hostname.encode("idna").decode("ascii").lower()
            )
        except (ValueError, UnicodeError):
            raise ValueError("APP_URL must contain a valid hostname") from None
        authority = f"[{host}]" if ":" in host else host
        if origin.port is not None and origin.port != (443 if origin.scheme == "https" else 80):
            authority += f":{origin.port}"
        return cls(
            environment=environment,
            app_url=f"{origin.scheme}://{authority}",
            database_url=database_url,
            database_tls=tls,
            session_secret=session_secret,
            probe_secret=probe_secret,
            demo_enabled=_boolean(environ, "SONDA_DEMO_ENABLED", False),
            login_enabled=_boolean(environ, "SONDA_LOGIN_ENABLED", False),
            trust_vercel_ingress=_boolean(environ, "TRUST_VERCEL_INGRESS", False),
            vercel_runtime=environ.get("VERCEL") == "1",
            port=port,
            allowed_hosts=frozenset(
                canonical_host(host.strip())
                for host in environ.get("SONDA_ALLOWED_HOSTS", "").split(",")
            )
            if environ.get("SONDA_ALLOWED_HOSTS", "")
            else frozenset(),
        )
