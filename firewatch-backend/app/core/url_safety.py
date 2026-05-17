"""SSRF defense for outbound webhook deliveries.

`validate_outbound_url` enforces that a user-supplied target URL is safe to
POST to from inside the application network. In production (DEBUG=False) it
rejects non-HTTPS schemes and any hostname whose DNS resolution touches a
non-globally-routable IP (loopback, link-local incl. 169.254.169.254 cloud
metadata, RFC 1918 private, multicast, reserved, unspecified). In DEBUG it
only validates the scheme so devs can target localhost / docker-compose / LAN.

In production it also pins the resolved IP and returns it so callers can
connect to the IP literal (closing the DNS-rebinding window between validate
and connect).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

from app.core.config import settings


@dataclass(frozen=True)
class ResolvedTarget:
    parsed: ParseResult
    pinned_ip: str | None
    pinned_port: int


def validate_outbound_url(url: str) -> ResolvedTarget:
    """Raise ValueError if `url` is unsafe; otherwise return a ResolvedTarget.

    In production, `pinned_ip` is the first globally-routable IP from DNS
    resolution and callers should connect to it directly. In DEBUG mode
    `pinned_ip` is None and callers should connect to the hostname as-is.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    default_port = 443 if parsed.scheme == "https" else 80
    pinned_port = parsed.port if parsed.port is not None else default_port

    if settings.DEBUG:
        return ResolvedTarget(parsed=parsed, pinned_ip=None, pinned_port=pinned_port)

    if parsed.scheme != "https":
        raise ValueError("non-HTTPS scheme not allowed in production")

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc

    seen: set[str] = set()
    first_global: str | None = None
    for info in infos:
        addr = info[4][0]
        # IPv6 sockaddr entries can carry a zone id ("fe80::1%eth0"); strip it.
        addr = addr.split("%", 1)[0]
        if addr in seen:
            continue
        seen.add(addr)
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            raise ValueError(f"hostname resolves to private/internal IP: {addr}")
        if first_global is None:
            first_global = addr

    if first_global is None:
        raise ValueError("DNS resolution returned no addresses")

    return ResolvedTarget(parsed=parsed, pinned_ip=first_global, pinned_port=pinned_port)
