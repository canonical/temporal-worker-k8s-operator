# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for environment-based Temporal proxy configuration."""

import importlib
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.client import HttpConnectProxyConfig
from temporallib.client import Client

from resource_sample.proxy import proxy_options


@pytest.fixture(autouse=True)
def clear_proxy_environment(monkeypatch):
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "TEMPORAL_PROXY_HOST",
        "TEMPORAL_PROXY_USERNAME",
        "TEMPORAL_PROXY_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def config(host="temporal.example.com:7233", tls=False):
    return Client._build_proxy_config(proxy_options(host, tls))


def test_no_proxy_defaults_to_direct(monkeypatch):
    monkeypatch.setenv("TEMPORAL_PROXY_HOST", "ignored:3128")
    assert config() is None


@pytest.mark.parametrize(
    "tls,https,expected",
    [
        (False, "http://secure-proxy:8080", "plain-proxy:3128"),
        (True, "http://secure-proxy:8080", "secure-proxy:8080"),
        (True, "", "plain-proxy:3128"),
    ],
)
def test_proxy_selection(monkeypatch, tls, https, expected):
    monkeypatch.setenv("HTTP_PROXY", "http://plain-proxy:3128")
    monkeypatch.setenv("HTTPS_PROXY", https)
    assert config(tls=tls) == HttpConnectProxyConfig(expected)


def test_https_proxy_not_used_for_plaintext(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://secure-proxy:8080")
    assert config() is None


@pytest.mark.parametrize(
    "url,target,auth",
    [
        ("http://proxy:3128", "proxy:3128", None),
        ("proxy:3128", "proxy:3128", None),
        ("http://proxy", "proxy:80", None),
        ("http://[::1]:3128", "[::1]:3128", None),
        ("http://user:pass@proxy:3128", "proxy:3128", ("user", "pass")),
        ("http://user@proxy", "proxy:80", ("user", "")),
        ("http://user:@proxy", "proxy:80", ("user", "")),
        (
            "http://u%40ser:p%3Aa%2Fss@proxy:3128",
            "proxy:3128",
            ("u@ser", "p:a/ss"),
        ),
    ],
)
def test_proxy_address_and_credentials(monkeypatch, url, target, auth):
    monkeypatch.setenv("HTTP_PROXY", url)
    assert config() == HttpConnectProxyConfig(target, basic_auth=auth)


@pytest.mark.parametrize(
    "host,bypass",
    [
        ("temporal.example.com:7233", "temporal.example.com"),
        ("temporal.example.com:7233", ".example.com"),
        ("example.com:7233", ".example.com"),
        ("temporal.example.com:7233", "other, temporal.example.com:7233"),
        ("[::1]:7233", "[::1]"),
        ("temporal.example.com:7233", "*"),
    ],
)
@pytest.mark.parametrize("tls", [False, True])
def test_no_proxy_bypasses(monkeypatch, host, bypass, tls):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("NO_PROXY", bypass)
    assert config(host, tls) is None


@pytest.mark.parametrize("bypass", ["ample.com", "temporal.example.com:9999", "other"])
def test_no_proxy_does_not_bypass_unmatched_hosts(monkeypatch, bypass):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy:3128")
    monkeypatch.setenv("NO_PROXY", bypass)
    assert config() == HttpConnectProxyConfig("proxy:3128")


def test_lowercase_variables_and_uppercase_precedence(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://lower:3128")
    assert config() == HttpConnectProxyConfig("lower:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://upper:3128")
    assert config() == HttpConnectProxyConfig("upper:3128")
    monkeypatch.setenv("no_proxy", ".example.com")
    assert config() is None
    monkeypatch.setenv("NO_PROXY", "")
    assert config() == HttpConnectProxyConfig("upper:3128")
    monkeypatch.setenv("https_proxy", "http://secure:3128")
    assert config(tls=True) == HttpConnectProxyConfig("secure:3128")


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@proxy:3128",
        "socks5://user:secret@proxy:3128",
        "http://user:secret@",
        "http://user:secret@proxy:invalid",
        "http://user:secret@proxy:65536",
        "http://user:secret@proxy:0",
        "http://user:secret@[::1",
        "http://user:secret@proxy/path",
        "http://user:secret@proxy?query",
        "http://user:secret@proxy#fragment",
        "http://:secret@proxy",
    ],
)
def test_invalid_proxy_fails_without_exposing_credentials(monkeypatch, url):
    monkeypatch.setenv("HTTP_PROXY", url)
    with pytest.raises(ValueError) as exc:
        config()
    assert "secret" not in str(exc.value)


def test_no_proxy_bypasses_even_invalid_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "invalid://proxy")
    monkeypatch.setenv("NO_PROXY", "*")
    assert config() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tls,bypass,expected",
    [
        (False, "", HttpConnectProxyConfig("plain:3128", ("user", "pass"))),
        (True, "", HttpConnectProxyConfig("secure:3128")),
        (False, "*", None),
        (True, ".example.com", None),
        (False, "", None),
    ],
)
async def test_worker_passes_proxy_to_sdk(monkeypatch, tls, bypass, expected):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "resource_sample"))
    worker = importlib.import_module("worker")
    monkeypatch.setenv("TEMPORAL_HOST", "temporal.example.com:7233")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "default")
    monkeypatch.setenv("TEMPORAL_QUEUE", "test-queue")
    monkeypatch.setenv("TEMPORAL_TLS_ROOT_CAS", "test-ca" if tls else "")
    for name in ("DSN", "RELEASE", "ENVIRONMENT"):
        monkeypatch.setenv("TEMPORAL_SENTRY_" + name, "")
    monkeypatch.delenv("TEMPORAL_PROMETHEUS_PORT", raising=False)
    if expected is not None or bypass:
        monkeypatch.setenv("HTTP_PROXY", "http://user:pass@plain:3128")
        monkeypatch.setenv("HTTPS_PROXY", "http://secure:3128")
    monkeypatch.setenv("NO_PROXY", bypass)

    connect = AsyncMock()
    monkeypatch.setattr("temporallib.client.client.TemporalClient.connect", connect)
    run = AsyncMock()
    make_worker = Mock(return_value=Mock(run=run))
    monkeypatch.setattr(worker, "Worker", make_worker)
    try:
        await worker.run_worker()
        connect.assert_awaited_once()
        assert connect.call_args.args == ("temporal.example.com:7233",)
        assert connect.call_args.kwargs["http_connect_proxy_config"] == expected
        assert bool(connect.call_args.kwargs["tls"]) == tls
        assert make_worker.call_args.kwargs["client"] is connect.return_value
        run.assert_awaited_once()
    finally:
        await worker.Client.stop_reconnect()
