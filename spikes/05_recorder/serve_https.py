"""Serve the recorder spike over HTTPS on the LAN so a phone can open it.

Usage (after creating a cert with mkcert, see spikes/05_recorder/README.md):
  uv run python spikes/05_recorder/serve_https.py --cert 192.168.1.20.pem --key 192.168.1.20-key.pem
"""

from __future__ import annotations

import argparse
import functools
import http.server
import ssl
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8443)
    # Binding to all interfaces is the point: the phone connects over the LAN.
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    args = parser.parse_args()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.cert, keyfile=args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"Serving {HERE} on https://{args.host}:{args.port}/ (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
