import pytest

from sonda.access.passwords import PasswordService


async def test_salted_scrypt_checks_password_without_reusing_salts() -> None:
    service = PasswordService()
    first = await service.hash("senha-fixture-correta-123")
    second = await service.hash("senha-fixture-correta-123")
    assert first != second
    assert first.startswith("scrypt$32768$8$1$")
    assert await service.verify("senha-fixture-correta-123", first)
    assert not await service.verify("senha-fixture-incorreta-123", first)


@pytest.mark.parametrize("password", ["short", " " * 12, "x" * 129, "valid-pass-with\nnewline"])
async def test_installation_password_policy_is_bounded(password: str) -> None:
    with pytest.raises(ValueError):
        await PasswordService().hash(password)


@pytest.mark.parametrize(
    "encoded",
    ["disabled", "scrypt$999999999$8$1$salt$key", "scrypt$32768$8$1$invalid$invalid"],
)
async def test_malformed_or_unbounded_hashes_never_validate(encoded: str) -> None:
    assert not await PasswordService().verify("senha-fixture-correta-123", encoded)
