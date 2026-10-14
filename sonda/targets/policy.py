import ipaddress
import re
from collections.abc import Collection
from dataclasses import dataclass
from urllib.parse import urlsplit


class TargetRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("Target is not an authorized HTTP destination")


def canonical_host(host: str) -> str:
    try:
        value = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise TargetRejected() from None
    if (
        not value
        or len(value) > 253
        or value.endswith(".")
        or not any(character.isalpha() for character in value)
        or value == "localhost"
        or value.endswith((".localhost", ".local", ".internal"))
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in value.split(".")
        )
    ):
        raise TargetRejected()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise TargetRejected()


@dataclass(frozen=True)
class Target:
    url: str
    host: str
    port: int
    internal: bool
    local: bool


def validate_target(
    url: str, allowed_hosts: Collection[str], internal_origin: str, *, production: bool
) -> Target:
    try:
        if (
            len(url) > 2048
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)
            or any(char in url for char in "\\?#")
        ):
            raise TargetRejected()
        parsed = urlsplit(url)
        origin = urlsplit(internal_origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port == 0
        ):
            raise TargetRejected()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origin_port = origin.port or (443 if origin.scheme == "https" else 80)
        internal = (
            parsed.scheme == origin.scheme
            and parsed.hostname == origin.hostname
            and port == origin_port
            and re.fullmatch(r"/probe/[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", parsed.path)
            is not None
        )
        local = False
        if internal and not production:
            try:
                local = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local = parsed.hostname == "localhost"
        if local:
            host = parsed.hostname
        else:
            host = canonical_host(parsed.hostname)
            if parsed.scheme != "https" or port != 443:
                raise TargetRejected()
            if not internal and host not in {canonical_host(item) for item in allowed_hosts}:
                raise TargetRejected()
        authority = host if port == (443 if parsed.scheme == "https" else 80) else f"{host}:{port}"
        if ":" in host:
            authority = f"[{host}]" + (f":{port}" if port != 80 else "")
        return Target(
            f"{parsed.scheme}://{authority}{parsed.path or '/'}", host, port, internal, local
        )
    except ValueError:
        raise TargetRejected() from None
