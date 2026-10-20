"""Ed25519 signature verification (RFC 8032, section 5.1.7), pure Python.

Verification only.  Every input it handles is public: the release key, the
downloaded bytes and their signature.
"""

import hashlib

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _add(a: tuple, b: tuple) -> tuple:
    """Add two points in extended coordinates (X, Y, Z, T)."""
    e1 = (a[1] - a[0]) * (b[1] - b[0]) % _P
    e2 = (a[1] + a[0]) * (b[1] + b[0]) % _P
    c = 2 * a[3] * b[3] * _D % _P
    d = 2 * a[2] * b[2] % _P
    e, f, g, h = e2 - e1, d - c, d + c, e2 + e1
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(scalar: int, point: tuple) -> tuple:
    result = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a: tuple, b: tuple) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _decompress(data: bytes) -> tuple | None:
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


_BASE_Y = 4 * pow(5, _P - 2, _P) % _P
_BASE_X = _recover_x(_BASE_Y, 0)
_BASE = (_BASE_X, _BASE_Y, 1, _BASE_X * _BASE_Y % _P)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True when ``signature`` is a valid Ed25519 signature of ``message``.

    Malformed keys and signatures (wrong length, a point off the curve, a
    non-canonical S) verify as False rather than raising.
    """
    if len(public_key) != 32 or len(signature) != 64:
        return False
    a = _decompress(public_key)
    if a is None:
        return False
    r_bytes = signature[:32]
    r = _decompress(r_bytes)
    if r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(r_bytes + public_key + message).digest(), "little") % _Q
    return _equal(_mul(s, _BASE), _add(r, _mul(h, a)))
