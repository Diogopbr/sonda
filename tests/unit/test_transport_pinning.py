from dataclasses import replace
from typing import Any

import aiohappyeyeballs
import aiohttp
import pytest

from sonda.config import Settings
from sonda.targets.fetcher import SafeFetcher
from sonda.targets.policy import validate_target
from sonda.targets.resolver import PublicResolver
from tests.unit.test_config import production_env
from tests.unit.test_resolver import SourceResolver


@pytest.mark.parametrize("private,remove_guard", [(False, False), (True, False), (True, True)])
async def test_connector_uses_validated_addresses_and_rejection_has_negative_control(
    monkeypatch: pytest.MonkeyPatch,
    private: bool,
    remove_guard: bool,
) -> None:
    settings = Settings.from_env(production_env() | {"SONDA_ALLOWED_HOSTS": "example.com"})
    source = SourceResolver(["8.8.8.8", "127.0.0.1"] if private else ["8.8.8.8"])
    original = source.resolve

    async def changing_dns(*args: Any, **kwargs: Any):
        records = await original(*args, **kwargs)
        source.addresses = ["127.0.0.1"]
        return records

    monkeypatch.setattr(source, "resolve", changing_dns)
    connected: list[Any] = []

    async def observe_connection(*args: Any, **kwargs: Any):
        connected.extend(kwargs["addr_infos"])
        raise OSError("controlled connection stop")

    monkeypatch.setattr(aiohappyeyeballs, "start_connection", observe_connection)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    original_get = aiohttp.ClientSession.get
    outgoing_headers: list[Any] = []

    def capture_get(self: aiohttp.ClientSession, *args: Any, **kwargs: Any):
        outgoing_headers.append(kwargs.get("headers"))
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(aiohttp.ClientSession, "get", capture_get)
    if remove_guard:

        async def unguarded(self: PublicResolver, *args: Any, **kwargs: Any):
            return await self.source.resolve(*args, **kwargs)

        monkeypatch.setattr(PublicResolver, "resolve", unguarded)
    target = validate_target(
        "https://example.com/", settings.allowed_hosts, settings.app_url, production=True
    )
    outcome = await SafeFetcher(settings, resolver_source=source).fetch(
        replace(target, internal=True, local=True)
    )
    assert source.calls == 1
    assert outgoing_headers == [{}]
    if private and not remove_guard:
        assert outcome.error_code == "DNS_REJECTED" and not connected
    else:
        assert outcome.error_code == "CONNECT_ERROR" and connected
        addresses = {record[4][0] for record in connected}
        assert addresses == ({"8.8.8.8", "127.0.0.1"} if remove_guard else {"8.8.8.8"})
        assert all(record[4][1] == 443 for record in connected)
