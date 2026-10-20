"""Tests for analyze_common.ed25519 (RFC 8032 test vectors, section 7.1)."""

import pytest

from analyze_common import ed25519
from conftest import Signer

# (secret key, public key, message, signature) — RFC 8032 TEST 1, 2, 3.
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize("secret,public,message,signature", VECTORS)
def test_rfc8032_vectors_verify(secret, public, message, signature):
    assert ed25519.verify(bytes.fromhex(public), bytes.fromhex(message), bytes.fromhex(signature))


@pytest.mark.parametrize("secret,public,message,signature", VECTORS)
def test_test_signer_reproduces_rfc8032(secret, public, message, signature):
    # The fixture signer the update tests rely on must match the RFC.
    s = Signer(bytes.fromhex(secret))
    assert s.public_key.hex() == public
    assert s.sign(bytes.fromhex(message)).hex() == signature


def test_rejects_changed_message():
    _, public, message, signature = VECTORS[2]
    assert not ed25519.verify(bytes.fromhex(public), bytes.fromhex("af83"), bytes.fromhex(signature))


def test_rejects_changed_signature():
    _, public, message, signature = VECTORS[2]
    tampered = bytearray(bytes.fromhex(signature))
    tampered[10] ^= 0x01
    assert not ed25519.verify(bytes.fromhex(public), bytes.fromhex(message), bytes(tampered))


def test_rejects_other_key():
    _, _, message, signature = VECTORS[2]
    other = VECTORS[1][1]
    assert not ed25519.verify(bytes.fromhex(other), bytes.fromhex(message), bytes.fromhex(signature))


def test_rejects_non_canonical_s():
    _, public, message, signature = VECTORS[0]
    original = bytes.fromhex(signature)
    s = int.from_bytes(original[32:], "little") + ed25519._Q
    forged = original[:32] + s.to_bytes(32, "little")
    assert not ed25519.verify(bytes.fromhex(public), bytes.fromhex(message), forged)


@pytest.mark.parametrize("key_len,signature_len", [(31, 64), (33, 64), (32, 63), (32, 65)])
def test_rejects_wrong_lengths(key_len, signature_len):
    assert not ed25519.verify(b"\x01" * key_len, b"", b"\x00" * signature_len)


def test_rejects_key_off_the_curve():
    # y = 2 has no x on the curve (x^2 is not a square mod p).
    key = (2).to_bytes(32, "little")
    _, _, message, signature = VECTORS[0]
    assert ed25519._decompress(key) is None
    assert not ed25519.verify(key, bytes.fromhex(message), bytes.fromhex(signature))


def test_rejects_non_canonical_y():
    key = (2 ** 255 - 1).to_bytes(32, "little")  # y >= p once the sign bit is dropped
    assert ed25519._decompress(key) is None
