import ipaddress
import socket

from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver

from sonda.targets.policy import Target


class DNSRejected(OSError):
    def __init__(self) -> None:
        super().__init__("DNS destination rejected")


class PublicResolver(AbstractResolver):
    def __init__(self, target: Target, *, source: AbstractResolver | None = None) -> None:
        self.target = target
        self.source = source if source is not None else DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        if host != self.target.host or port != self.target.port:
            raise DNSRejected()
        results = await self.source.resolve(host, port, family)
        if not results or len(results) > 64:
            raise DNSRejected()
        validated: list[ResolveResult] = []
        for result in results:
            try:
                if "%" in result["host"]:
                    raise ValueError
                address = ipaddress.ip_address(result["host"])
            except ValueError:
                raise DNSRejected() from None
            if not self.target.local and (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None)
            ):
                raise DNSRejected()
            if self.target.local and not address.is_loopback:
                raise DNSRejected()
            validated.append(
                ResolveResult(
                    hostname=host,
                    host=str(address),
                    port=port,
                    family=socket.AF_INET6 if address.version == 6 else socket.AF_INET,
                    proto=socket.IPPROTO_TCP,
                    flags=socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                )
            )
        return validated

    async def close(self) -> None:
        await self.source.close()
