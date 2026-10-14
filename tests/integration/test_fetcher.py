import asyncio
import shutil
import ssl
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from sonda.config import Settings
from sonda.targets.fetcher import SafeFetcher
from sonda.targets.policy import validate_target
from tests.unit.test_config import production_env

PROBE = "/probe/00000000-0000-0000-0000-000000000001"


def settings_for(origin: str) -> Settings:
    return Settings.from_env(
        production_env()
        | {
            "SONDA_ENV": "test",
            "APP_URL": origin,
            "DB_TLS": "false",
        }
    )


@asynccontextmanager
async def target_server(
    status: int,
    *,
    wait_headers: bool = False,
    wait_body: bool = False,
    tls: ssl.SSLContext | None = None,
    names: list[str | None] | None = None,
) -> AsyncIterator[tuple[str, list[bytes]]]:
    release = asyncio.Event()
    requests: list[bytes] = []
    tasks: set[asyncio.Task[None]] = set()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        try:
            requests.append(await reader.readuntil(b"\r\n\r\n"))
            if wait_headers:
                await release.wait()
            location = "Location: /redirect-target\r\n" if status == 302 else ""
            length = 1000000000 if wait_body else 0
            writer.write(
                f"HTTP/1.1 {status} Test\r\n{location}Content-Length: {length}\r\n\r\n".encode()
            )
            await writer.drain()
            if wait_body:
                await release.wait()
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    if tls is not None and names is not None:
        tls.set_servername_callback(lambda socket, name, context: names.append(name))
    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=tls)
    assert server.sockets is not None
    host = "https://localhost" if tls else "http://127.0.0.1"
    origin = f"{host}:{server.sockets[0].getsockname()[1]}"
    try:
        yield origin, requests
    finally:
        release.set()
        for task in tuple(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tuple(tasks), return_exceptions=True)
        server.close()
        await server.wait_closed()


async def test_real_http_statuses_and_internal_secret_header() -> None:
    for status in [200, 503]:
        async with target_server(status) as (origin, requests):
            settings = settings_for(origin)
            target = validate_target(origin + PROBE, set(), origin, production=False)
            outcome = await SafeFetcher(settings).fetch(target)
            assert outcome.status_code == status
            assert outcome.error_code == (None if status == 200 else "HTTP_STATUS")
            assert outcome.duration_ms >= 0
            assert len(requests) == 1
            assert ("X-Sonda-Probe: " + settings.probe_secret).encode() in requests[0]


async def test_real_redirect_is_not_followed() -> None:
    async with target_server(302) as (origin, requests):
        target = validate_target(origin + PROBE, set(), origin, production=False)
        outcome = await SafeFetcher(settings_for(origin)).fetch(target)
        assert outcome.status_code == 302 and outcome.error_code == "REDIRECT_NOT_ALLOWED"
        assert len(requests) == 1 and b"/redirect-target" not in requests[0]


async def test_returns_at_headers_without_waiting_for_large_response_body() -> None:
    async with target_server(200, wait_body=True) as (origin, requests):
        target = validate_target(origin + PROBE, set(), origin, production=False)
        outcome = await asyncio.wait_for(SafeFetcher(settings_for(origin)).fetch(target), timeout=2)
        assert outcome.status_code == 200 and len(requests) == 1


async def test_total_timeout_includes_waiting_for_headers() -> None:
    async with target_server(200, wait_headers=True) as (origin, requests):
        target = validate_target(origin + PROBE, set(), origin, production=False)
        outcome = await SafeFetcher(settings_for(origin)).fetch(target)
        assert outcome.status_code is None and outcome.error_code == "TIMEOUT"
        assert 4900 <= outcome.duration_ms <= 8000 and len(requests) == 1


async def test_real_tls_verifies_trust_hostname_and_preserves_sni(tmp_path: Path) -> None:
    executable = shutil.which("openssl") or "C:/Program Files/Git/usr/bin/openssl.exe"
    cert, key = tmp_path / "certificate.pem", tmp_path / "private-key.pem"
    result = await asyncio.to_thread(
        subprocess.run,
        [
            executable,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    assert result.returncode == 0
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert, key)
    trusted = ssl.create_default_context(cafile=str(cert))
    names: list[str | None] = []
    async with target_server(200, tls=server_context, names=names) as (origin, requests):
        settings = settings_for(origin)
        target = validate_target(origin + PROBE, set(), origin, production=False)
        success = await SafeFetcher(settings, ssl_context=trusted).fetch(target)
        assert success.status_code == 200 and success.error_code is None
        assert names[0] == "localhost" and b"Host: localhost:" in requests[0]
        untrusted = await SafeFetcher(settings).fetch(target)
        assert untrusted.status_code is None and untrusted.error_code == "TLS_ERROR"
        wrong_origin = origin.replace("localhost", "127.0.0.1")
        wrong = validate_target(wrong_origin + PROBE, set(), wrong_origin, production=False)
        mismatch = await SafeFetcher(settings_for(wrong_origin), ssl_context=trusted).fetch(wrong)
        assert mismatch.status_code is None and mismatch.error_code == "TLS_ERROR"
        assert len(requests) == 1
    insecure = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    with pytest.raises(ValueError):
        SafeFetcher(settings, ssl_context=insecure)
