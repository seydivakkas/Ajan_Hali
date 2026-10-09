"""Explicit direct-TLS deployment contract (no reverse proxy header trust).

Launch with `python -m core.secure_server`; this module only controls
request policy and does not turn a plain HTTP server into a TLS server.
"""
from __future__ import annotations

import ipaddress
import os
import re


def deployment_mode() -> str:
    value = os.environ.get("AJAN_HALI_DEPLOYMENT_MODE", "local").strip().lower()
    if value not in {"local", "direct-tls"}:
        raise RuntimeError("Invalid AJAN_HALI_DEPLOYMENT_MODE.")
    return value


def tls_config() -> tuple[str, int]:
    """Return one explicitly trusted host and port; prohibit wildcard hosts."""
    host = os.environ.get("AJAN_HALI_TLS_HOST", "").strip().lower()
    raw_port = os.environ.get("AJAN_HALI_TLS_PORT", "8443")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise RuntimeError("Invalid TLS port.") from error
    if not 1 <= port <= 65535:
        raise RuntimeError("Invalid TLS port.")
    try:
        parsed_ip = ipaddress.ip_address(host)
        if parsed_ip.is_unspecified or parsed_ip.is_multicast or parsed_ip.is_loopback:
            raise RuntimeError("TLS host must be the concrete non-loopback server address.")
    except ValueError:
        if (len(host) > 253 or not re.fullmatch(
            r"(?=.{4,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
        )):
            raise RuntimeError("TLS host must be a concrete DNS name or non-loopback IP.")
    if not host:
        raise RuntimeError("AJAN_HALI_TLS_HOST is required.")
    return host, port


def public_origin() -> str:
    host, port = tls_config()
    hostpart = f"[{host}]" if ":" in host else host
    return f"https://{hostpart}" + (f":{port}" if port != 443 else "")


def host_allowed(host_header: str) -> bool:
    origin = public_origin()
    expected_authority = origin[len("https://"):]
    # No alternative Host, comma, X-Forwarded-Host or trailing dot.
    return host_header.lower() == expected_authority.lower()


def origin_allowed(origin: str | None) -> bool:
    return origin is None or origin == public_origin()
