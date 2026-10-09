"""Opt-in HTTPS server with direct TLS termination (no insecure proxy trust)."""
from __future__ import annotations

import argparse
import ipaddress
import os
import ssl
from pathlib import Path


def prepare_direct_tls(*, host: str, bind: str, port: int,
                       certfile: str, keyfile: str) -> None:
    """Fail before starting if configuration/certificate is unusable."""
    if os.getenv("AJAN_HALI_AUTH_MODE") != "workspace":
        raise ValueError("Direct TLS requires AJAN_HALI_AUTH_MODE=workspace.")
    try:
        ipaddress.ip_address(bind)
    except ValueError as error:
        raise ValueError("--bind must be a literal local interface IP address.") from error
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port.")
    if not Path(certfile).is_file() or not Path(keyfile).is_file():
        raise ValueError("TLS certificate and private-key files are required.")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    except (OSError, ssl.SSLError) as error:
        raise ValueError("TLS certificate and private key cannot be loaded.") from error
    # Both values must agree with the request policy.
    os.environ["AJAN_HALI_DEPLOYMENT_MODE"] = "direct-tls"
    os.environ["AJAN_HALI_TLS_HOST"] = host
    os.environ["AJAN_HALI_TLS_PORT"] = str(port)
    from core.tls_policy import tls_config
    tls_config()


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit direct HTTPS server (workspace mode only)")
    parser.add_argument("--host", required=True, help="DNS name in the trusted TLS certificate")
    parser.add_argument("--bind", required=True, help="Literal IP on this machine")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    args = parser.parse_args()
    try:
        prepare_direct_tls(host=args.host, bind=args.bind, port=args.port,
                           certfile=args.certfile, keyfile=args.keyfile)
    except ValueError as error:
        parser.error(str(error))
    # Import only after the guard has been configured. Never honor forwarded
    # headers supplied by an untrusted HTTP client.
    import uvicorn
    uvicorn.run("api.server:app", host=args.bind, port=args.port,
                ssl_certfile=args.certfile, ssl_keyfile=args.keyfile,
                ssl_version=ssl.PROTOCOL_TLS_SERVER, proxy_headers=False,
                forwarded_allow_ips="", server_header=False)


if __name__ == "__main__":
    main()
