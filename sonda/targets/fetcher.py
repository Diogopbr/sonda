import asyncio
import ssl
import time
from dataclasses import dataclass

import aiohttp
import certifi
from aiohttp.abc import AbstractResolver

from sonda.config import Settings
from sonda.targets.policy import Target, TargetRejected, validate_target
from sonda.targets.resolver import DNSRejected, PublicResolver


@dataclass(frozen=True)
class FetchOutcome:
    status_code: int | None
    duration_ms: int
    error_code: str | None


class SafeFetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        resolver_source: AbstractResolver | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.settings = settings
        self.source = resolver_source
        self.ssl = ssl_context or ssl.create_default_context(cafile=certifi.where())
        if self.ssl.verify_mode != ssl.CERT_REQUIRED or not self.ssl.check_hostname:
            raise ValueError("HTTP transport requires certificate and hostname verification")
        self._slots = asyncio.Semaphore(4)

    async def fetch(self, target: Target) -> FetchOutcome:
        started = time.perf_counter()

        def outcome(code: str | None, status: int | None = None) -> FetchOutcome:
            return FetchOutcome(status, max(0, round((time.perf_counter() - started) * 1000)), code)

        try:
            target = validate_target(
                target.url,
                self.settings.allowed_hosts,
                self.settings.app_url,
                production=self.settings.production,
            )
            async with asyncio.timeout(5), self._slots:
                resolver = PublicResolver(target, source=self.source)
                try:
                    connector = aiohttp.TCPConnector(
                        resolver=resolver,
                        use_dns_cache=False,
                        ssl=self.ssl,
                        limit=4,
                        force_close=True,
                        timeout_ceil_threshold=float("inf"),
                    )
                    async with aiohttp.ClientSession(
                        connector=connector,
                        trust_env=False,
                        cookie_jar=aiohttp.DummyCookieJar(),
                        timeout=aiohttp.ClientTimeout(
                            total=5, connect=2, sock_connect=2, ceil_threshold=float("inf")
                        ),
                        auto_decompress=False,
                        read_bufsize=4096,
                        max_headers=64,
                    ) as client:
                        headers = (
                            {"X-Sonda-Probe": self.settings.probe_secret} if target.internal else {}
                        )
                        async with client.get(
                            target.url, headers=headers, allow_redirects=False, read_until_eof=False
                        ) as response:
                            status = response.status
                            response.close()
                            if 200 <= status < 300:
                                return outcome(None, status)
                            return outcome(
                                "REDIRECT_NOT_ALLOWED" if 300 <= status < 400 else "HTTP_STATUS",
                                status,
                            )
                finally:
                    await resolver.close()
        except TargetRejected:
            return outcome("TARGET_REJECTED")
        except (TimeoutError, aiohttp.ServerTimeoutError):
            return outcome("TIMEOUT")
        except (aiohttp.ClientSSLError, ssl.SSLError):
            return outcome("TLS_ERROR")
        except aiohttp.ClientConnectorDNSError as error:
            return outcome(
                "DNS_REJECTED" if isinstance(error.os_error, DNSRejected) else "DNS_ERROR"
            )
        except DNSRejected:
            return outcome("DNS_REJECTED")
        except (aiohttp.ClientError, OSError):
            return outcome("CONNECT_ERROR")
