"""Tests for analyze_common.network."""

import re
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from analyze_common import network


class TestConnect:
    def test_returns_the_first_address_that_connects(self, fake_network):
        created = fake_network({"192.0.2.1": TimeoutError("timed out"), "fe80::1": None,
                                "192.0.2.2": TimeoutError("timed out")})
        connection = network.connect(("pin.invalid", 443), 60, None)
        assert [(s.peer, s.timeout, s.bound, s.closed) for s in created] == [
            (("192.0.2.1", 443), 60, None, True),
            (("fe80::1", 443, 0, 7), 60, None, False),
        ]
        assert connection is created[1]

    def test_leaves_the_default_timeout_and_binds_the_source_address(self, fake_network):
        created = fake_network({"192.0.2.1": None})
        network.connect(("pin.invalid", 443), socket._GLOBAL_DEFAULT_TIMEOUT, ("192.0.2.9", 0))
        assert [(s.timeout, s.bound) for s in created] == [(None, ("192.0.2.9", 0))]

    def test_names_every_address_with_its_error(self, unreachable_host):
        with pytest.raises(OSError) as raised:
            network.connect(("pin.invalid", 443), 60, None)
        assert str(raised.value) == unreachable_host


class TestUrlopen:
    def test_names_every_address_with_its_error(self, unreachable_host):
        with pytest.raises(urllib.error.URLError) as raised:
            network.urlopen("https://pin.invalid/", 60)
        assert str(raised.value.reason) == unreachable_host

    def test_fetches_a_url_or_a_request_without_a_timeout(self, http_server):
        http_server.add("/page", b"body")
        with network.urlopen(http_server.base + "/page") as response:
            assert response.read() == b"body"
        with network.urlopen(urllib.request.Request(http_server.base + "/page")) as response:
            assert response.read() == b"body"


def test_other_modules_make_https_connections_through_network():
    direct = re.compile(r"urllib\.request\.(urlopen|urlretrieve|HTTPSHandler)\(|http\.client\.HTTPSConnection\(")
    package = Path(network.__file__).parent
    found = [f"{path.name}:{number}" for path in sorted(package.glob("*.py")) if path.name != "network.py"
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if direct.search(line)]
    assert found == []
