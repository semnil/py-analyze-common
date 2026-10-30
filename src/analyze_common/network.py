"""HTTPS fetching whose failed connection names every address it tried.

``connect()`` tries a host's addresses in the order ``getaddrinfo`` returns
them, like ``socket.create_connection``, and when every address fails raises
an ``OSError`` naming each address with its own error
(``could not connect to HOST port PORT (ADDRESS: ERROR; ...)``).
``HTTPSHandler`` and ``urlopen()`` make urllib's HTTPS connections with it.
"""

import http.client
import socket
import urllib.request


def connect(address, timeout, source_address):
    """``socket.create_connection`` whose error, when every address fails, names each address with its error."""
    host, port = address
    errors = []
    for family, kind, protocol, _, peer in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        connection = None
        try:
            connection = socket.socket(family, kind, protocol)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(peer)
            return connection
        except OSError as e:
            if connection is not None:
                connection.close()
            errors.append(f"{peer[0]}: {e}")
    raise OSError(f"could not connect to {host} port {port} ({'; '.join(errors)})")


class HTTPSConnection(http.client.HTTPSConnection):
    """``http.client.HTTPSConnection`` that connects with ``connect()``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = connect


class HTTPSHandler(urllib.request.HTTPSHandler):
    """``urllib.request.HTTPSHandler`` whose connections are ``HTTPSConnection``."""

    def https_open(self, req):
        return self.do_open(HTTPSConnection, req, context=self._context)


def urlopen(url, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
    """``urllib.request.urlopen(url, timeout=timeout)`` whose HTTPS connections are ``HTTPSConnection``."""
    return urllib.request.build_opener(HTTPSHandler).open(url, timeout=timeout)
