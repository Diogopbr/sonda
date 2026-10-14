import asyncio
import base64
import hashlib
import hmac
import re
import secrets


def validate_password(password: str) -> None:
    if (
        not 12 <= len(password) <= 128
        or not password.strip()
        or any(ord(character) < 32 for character in password)
    ):
        raise ValueError("Password must contain12..128 characters without control characters")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid hash encoding")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=64
    )


class PasswordService:
    def __init__(self) -> None:
        self._slots = asyncio.Semaphore(2)

    async def hash(self, password: str) -> str:
        validate_password(password)
        salt = secrets.token_bytes(16)
        async with self._slots:
            key = await asyncio.to_thread(_derive, password, salt)
        return f"scrypt$32768$8$1${_encode(salt)}${_encode(key)}"

    async def verify(self, password: str, encoded: str) -> bool:
        if len(password) > 128 or len(encoded) > 200:
            return False
        parts = encoded.split("$")
        if len(parts) != 6 or parts[:4] != ["scrypt", "32768", "8", "1"]:
            return False
        try:
            salt, expected = _decode(parts[4]), _decode(parts[5])
        except ValueError:
            return False
        if len(salt) != 16 or len(expected) != 64:
            return False
        async with self._slots:
            actual = await asyncio.to_thread(_derive, password, salt)
        return hmac.compare_digest(actual, expected)
