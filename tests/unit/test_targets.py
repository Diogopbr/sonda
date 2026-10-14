import pytest

from sonda.targets.policy import TargetRejected, validate_target


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://example.com:444/",
        "https://user:pass@example.com/",
        "https://example.com/?token=secret",
        "https://example.com/#x",
        "https://example.com/?",
        "https://example.com/#",
        "https://example.com/\n",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://localhost/",
        "https://metadata.google.internal/",
        "https://unapproved.example/",
        "https://example.com./",
        "https://2130706433/",
        "https://0177.0.0.1/",
        "https://example.com\\@other.example/",
    ],
)
def test_normal_targets_reject_unsafe_or_unauthorized_urls(url: str) -> None:
    with pytest.raises(TargetRejected):
        validate_target(
            url,
            {"example.com", "localhost", "metadata.google.internal"},
            "https://sonda.example",
            production=True,
        )


def test_canonical_https_host_and_exact_internal_fixture() -> None:
    target = validate_target(
        "https://EXAMPLE.com:443/path", {"example.com"}, "https://sonda.example", production=True
    )
    assert target.url == "https://example.com/path" and target.port == 443 and not target.internal
    unicode = validate_target(
        "https://exemplo.рф/path", {"exemplo.xn--p1ai"}, "https://sonda.example", production=True
    )
    assert unicode.host == "exemplo.xn--p1ai"
    fixture = "https://sonda.example/probe/00000000-0000-0000-0000-000000000001"
    assert validate_target(fixture, set(), "https://sonda.example", production=True).internal
    with pytest.raises(TargetRejected):
        validate_target(
            "https://sonda.example/api/auth", set(), "https://sonda.example", production=True
        )


def test_local_exception_is_only_exact_fixture_origin_outside_production() -> None:
    fixture = "http://127.0.0.1:5095/probe/00000000-0000-0000-0000-000000000001"
    assert validate_target(fixture, set(), "http://127.0.0.1:5095", production=False).local
    for url in [fixture.replace("5095", "5096"), fixture.replace("/probe/", "/api/")]:
        with pytest.raises(TargetRejected):
            validate_target(url, set(), "http://127.0.0.1:5095", production=False)
    with pytest.raises(TargetRejected):
        validate_target(fixture, set(), "http://127.0.0.1:5095", production=True)
