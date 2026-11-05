# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""HTTP CONNECT proxy settings for Temporal connections."""

import os
from typing import Optional
from urllib.parse import unquote, urlsplit
from urllib.request import proxy_bypass_environment  # type: ignore[attr-defined]

from temporallib.client import ProxyOptions


def _environment(name: str) -> str:
    return os.environ.get(name, os.environ.get(name.lower(), "")).strip()


def proxy_options(host: Optional[str], tls: bool = False) -> ProxyOptions:
    """Select a proxy from the environment, respecting destination bypasses."""
    direct = ProxyOptions(host=None, username=None, password=None)
    no_proxy = _environment("NO_PROXY")
    if host and proxy_bypass_environment(host, {"no": no_proxy}):
        return direct

    proxy = _environment("HTTPS_PROXY") if tls else _environment("HTTP_PROXY")
    if tls and not proxy:
        proxy = _environment("HTTP_PROXY")
    if not proxy:
        return direct

    try:
        parsed = urlsplit(proxy if "://" in proxy else "http://" + proxy)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid HTTP CONNECT proxy address") from None

    if (
        parsed.scheme != "http"
        or not hostname
        or port == 0
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (parsed.username is not None and not parsed.username)
    ):
        raise ValueError(
            "HTTP CONNECT proxy must be an http://[user:pass@]host[:port] URL"
        )

    target = f"[{hostname}]" if ":" in hostname else hostname
    username = unquote(parsed.username) if parsed.username is not None else None
    password = unquote(parsed.password or "") if username is not None else None
    return ProxyOptions(
        host=f"{target}:{port or 80}", username=username, password=password
    )
