"""Shared fixtures: an Ed25519 test signer."""

import base64
import hashlib

import pytest

from analyze_common import ed25519 as _ed


def _compress(point: tuple) -> bytes:
    zinv = pow(point[2], _ed._P - 2, _ed._P)
    x = point[0] * zinv % _ed._P
    y = point[1] * zinv % _ed._P
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
        self.public_key = _compress(_ed._mul(a, _ed._BASE))
        self.public_key_b64 = base64.b64encode(self.public_key).decode("ascii")

    def sign(self, message: bytes) -> bytes:
        r = int.from_bytes(hashlib.sha512(self._prefix + message).digest(), "little") % _ed._Q
        r_bytes = _compress(_ed._mul(r, _ed._BASE))
        k = int.from_bytes(hashlib.sha512(r_bytes + self.public_key + message).digest(), "little") % _ed._Q
        s = (r + k * self._a) % _ed._Q
        return r_bytes + int.to_bytes(s, 32, "little")


@pytest.fixture
def signer():
    return Signer(b"\x07" * 32)

