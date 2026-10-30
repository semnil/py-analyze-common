"""Shared fixtures: an Ed25519 test signer, a scripted local HTTP server,
executable files for find_executable() and faked name resolution and connecting."""

import base64
import errno
import hashlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from analyze_common import ed25519


def _compress(point: tuple) -> bytes:
    zinv = pow(point[2], ed25519._P - 2, ed25519._P)
    x = point[0] * zinv % ed25519._P
    y = point[1] * zinv % ed25519._P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


class Signer:
    """RFC 8032 section 5.1.6 signing, for tests only (no side-channel care)."""

    def __init__(self, seed: bytes):
        h = hashlib.sha512(seed).digest()
        a = int.from_bytes(h[:32], "little")
        a &= (1 << 254) - 8
        a |= 1 << 254
        self._a = a
        self._prefix = h[32:]
        self.public_key = _compress(ed25519._mul(a, ed25519._BASE))
        self.public_key_b64 = base64.b64encode(self.public_key).decode("ascii")

    def sign(self, message: bytes) -> bytes:
        r = int.from_bytes(hashlib.sha512(self._prefix + message).digest(), "little") % ed25519._Q
        r_bytes = _compress(ed25519._mul(r, ed25519._BASE))
        k = int.from_bytes(hashlib.sha512(r_bytes + self.public_key + message).digest(), "little") % ed25519._Q
        s = (r + k * self._a) % ed25519._Q
        return r_bytes + int.to_bytes(s, 32, "little")


@pytest.fixture
def signer():
    return Signer(b"\x07" * 32)


class Routes:
    """path -> (status, headers, body); ``hits`` counts requests per path."""

    def __init__(self):
        self.table = {}
        self.hits = {}

    def add(self, path, body=b"", status=200, headers=None):
        self.table[path] = (status, dict(headers or {}), body)


@pytest.fixture
def http_server():
    routes = Routes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes.hits[self.path] = routes.hits.get(self.path, 0) + 1
            status, headers, body = routes.table.get(self.path, (404, {}, b"not found"))
            if callable(body):
                body = body(self)
                if body is None:
                    return
            self.send_response(status)
            headers.setdefault("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    routes.base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield routes
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def make_program():
    """``make(directory, name)`` creates an empty executable file that
    find_executable(name) matches in ``directory`` and returns its path."""

    def make(directory, name):
        path = directory / (name + ".exe" if sys.platform == "win32" else name)
        path.write_text("")
        path.chmod(0o755)
        return path

    return make


class FakeSocket:
    """A socket whose ``connect()`` raises the exception ``outcomes`` holds for the address, or returns
    when it holds None; it keeps the address, the timeout, the bound address and whether it was closed."""

    def __init__(self, outcomes, created):
        self.outcomes = outcomes
        self.peer = self.timeout = self.bound = None
        self.closed = False
        created.append(self)

    def settimeout(self, timeout):
        self.timeout = timeout

    def bind(self, address):
        self.bound = address

    def connect(self, peer):
        self.peer = peer
        if self.outcomes[peer[0]] is not None:
            raise self.outcomes[peer[0]]

    def close(self):
        self.closed = True


@pytest.fixture
def fake_network(monkeypatch):
    """``resolve(outcomes)`` makes pin.invalid resolve to the addresses of ``outcomes`` (address -> the
    exception connecting to it raises, or None when it connects; an ``fe80:`` address has the scope id 7)
    and returns the list of the ``FakeSocket`` objects created."""
    monkeypatch.setenv("no_proxy", "*")
    created = []
    table = {}

    def getaddrinfo(host, port, *args):
        assert host == "pin.invalid"
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port, 0, 7 if ip.startswith("fe80:") else 0))
                if ":" in ip else (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in table]

    def resolve(outcomes):
        table.update(outcomes)
        return created

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "socket", lambda family, kind, protocol: FakeSocket(table, created))
    return resolve


@pytest.fixture
def unreachable_host(fake_network):
    """pin.invalid resolves to two addresses that both fail to connect; returns the error network.connect() gives."""
    unreachable = OSError(errno.ENETUNREACH, "Network is unreachable")
    fake_network({"192.0.2.1": TimeoutError("timed out"), "2001:db8::1": unreachable})
    return f"could not connect to pin.invalid port 443 (192.0.2.1: timed out; 2001:db8::1: {unreachable})"
