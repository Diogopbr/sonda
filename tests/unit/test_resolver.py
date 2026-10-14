import socket

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from sonda.targets.policy import validate_target
from sonda.targets.resolver import DNSRejected, PublicResolver


class SourceResolver(AbstractResolver):
    def __init__(self, addresses: list[str]) -> None:
        self.addresses = addresses
        self.calls = 0

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> list[ResolveResult]:
        self.calls += 1
        return [
            ResolveResult(
                hostname=host,
                host=address,
                port=port,
                family=socket.AF_INET6 if ":" in address else socket.AF_INET,
                proto=socket.IPPROTO_TCP,
                flags=0,
            )
            for address in self.addresses
        ]

    async def close(self) -> None:
        pass


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "192.0.2.1",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::ffff:8.8.8.8",
        "::ffff:127.0.0.1",
        "2001:db8::1",
        "8.8.8.8%zone",
    ],
)
async def test_entire_dns_set_rejected_if_any_address_is_not_global(address: str) -> None:
    target = validate_target(
        "https://example.com/", {"example.com"}, "https://sonda.example", production=True
    )
    resolver = PublicResolver(target, source=SourceResolver(["8.8.8.8", address]))
    with pytest.raises(DNSRejected):
        await resolver.resolve(target.host, target.port)


async def test_validated_results_keep_original_host_and_bind_port() -> None:
    target = validate_target(
        "https://example.com/", {"example.com"}, "https://sonda.example", production=True
    )
    source = SourceResolver(["8.8.8.8", "2606:4700:4700::1111"])
    resolver = PublicResolver(target, source=source)
    records = await resolver.resolve(target.host, target.port)
    assert source.calls == 1
    assert {record["host"] for record in records} == set(source.addresses)
    assert all(record["hostname"] == target.host and record["port"] == 443 for record in records)
    with pytest.raises(DNSRejected):
        await resolver.resolve("other.example", 443)


async def test_local_exception_does_not_allow_different_host_or_port() -> None:
    target = validate_target(
        "http://localhost:5095/probe/00000000-0000-0000-0000-000000000001",
        set(),
        "http://localhost:5095",
        production=False,
    )
    resolver = PublicResolver(target, source=SourceResolver(["127.0.0.1"]))
    assert (await resolver.resolve("localhost", 5095))[0]["host"] == "127.0.0.1"
    for host, port in [("localhost", 5096), ("example.com", 5095)]:
        with pytest.raises(DNSRejected):
            await resolver.resolve(host, port)
