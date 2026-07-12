from __future__ import annotations

import socket

import pytest

import harness.browser as browser
from harness.tools import web


def _addr(address: str):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET,
             socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("url", [
    "http://localhost/admin",
    "http://127.0.0.1/private",
    "http://169.254.169.254/latest/meta-data",
    "http://user:password@example.com/",
])
def test_web_tool_rejects_local_and_credentialed_urls(url: str):
    with pytest.raises(ValueError):
        web._validate_public_url(url)
    assert web.fetch_url(url).startswith("Error fetching")


def test_web_tool_rejects_dns_names_resolving_to_private_addresses(
        monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *a, **k: _addr("10.0.0.2"))
    with pytest.raises(ValueError, match="private network"):
        web._validate_public_url("https://apparently-public.example/path")


def test_browser_route_host_filter_blocks_private_and_allows_public(
        monkeypatch: pytest.MonkeyPatch):
    browser._PUBLIC_HOST_CACHE.clear()
    monkeypatch.setattr(browser.socket, "getaddrinfo",
                        lambda *a, **k: _addr("93.184.216.34"))
    assert browser._host_is_public("example.com") is True

    browser._PUBLIC_HOST_CACHE.clear()
    monkeypatch.setattr(browser.socket, "getaddrinfo",
                        lambda *a, **k: _addr("192.168.1.1"))
    assert browser._host_is_public("router.example") is False


def test_empty_and_oversized_web_inputs_are_rejected_without_network():
    assert web.web_search("   ").startswith("Error")
    assert web.web_search("x" * 501).startswith("Error")
    assert web.fetch_url("").startswith("Error")
    assert web.fetch_url(
        "https://example.com/" + "x" * 5000).startswith("Error")
