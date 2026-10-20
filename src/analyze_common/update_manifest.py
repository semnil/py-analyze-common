"""Build and sign a release's update manifest (``latest.json``) in CI.

    python -m analyze_common.update_manifest sign --config PKG.MODULE:NAME \\
        --tag vX.Y.Z --key KEY.pem --out DIR/latest.json PLATFORM=FILE ...
    python -m analyze_common.update_manifest public-key KEY.pem

``--config`` names the app's ``UpdateConfig``.  Signing goes through
``openssl pkeyutl -rawin`` with an Ed25519 PEM key, and every signature is
checked against the config's public key before the manifest is written; a key
that does not match the app's exits 1 without writing it.
"""

import argparse
import base64
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from analyze_common import ed25519
from analyze_common.update import (
    PLATFORMS, UpdateConfig, UpdateError, parse_version, statement,
)

_ED25519_PUBLIC_KEY_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")


def _openssl(args: list) -> bytes:
    executable = shutil.which("openssl")
    if executable is None:
        raise UpdateError("openssl is not on PATH")
    result = subprocess.run([executable, *args], capture_output=True)
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", "replace").strip()[-300:]
        raise UpdateError(f"openssl {args[0]} failed (exit {result.returncode}): {tail}")
    return result.stdout


def public_key(key_path: Path) -> str:
    """Base64 of the raw Ed25519 public key in a PEM private key."""
    der = _openssl(["pkey", "-in", str(key_path), "-pubout", "-outform", "DER"])
    if len(der) != len(_ED25519_PUBLIC_KEY_DER_PREFIX) + 32 or not der.startswith(_ED25519_PUBLIC_KEY_DER_PREFIX):
        raise UpdateError(f"{key_path} is not an Ed25519 key")
    return base64.b64encode(der[len(_ED25519_PUBLIC_KEY_DER_PREFIX):]).decode("ascii")


def sign(key_path: Path, message: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        message_path = Path(tmp) / "statement"
        signature_path = Path(tmp) / "signature"
        message_path.write_bytes(message)
        _openssl(["pkeyutl", "-sign", "-inkey", str(key_path), "-rawin",
                  "-in", str(message_path), "-out", str(signature_path)])
        return signature_path.read_bytes()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(config: UpdateConfig, tag: str, key_path: Path, assets: dict) -> dict:
    """The manifest for ``tag``: one signed entry per ``{platform: path}``."""
    version = tag[1:] if tag.startswith("v") else ""
    if version != config.current_version:
        raise UpdateError(f"Tag {tag} does not match the app version {config.current_version}")
    parse_version(version)
    key = base64.b64decode(config.public_key, validate=True)
    platforms = {}
    for platform, path in assets.items():
        if platform not in PLATFORMS:
            raise UpdateError(f"Unknown platform {platform!r} (expected one of {', '.join(PLATFORMS)})")
        path = Path(path)
        message = statement(config.product, version, platform, _sha256(path))
        signature = sign(key_path, message)
        if not ed25519.verify(key, message, signature):
            raise UpdateError("The signing key does not match the app's public key")
        url = config.asset_url(tag, path.name)
        platforms[platform] = {"url": url, "signature": base64.b64encode(signature).decode("ascii")}
    if not platforms:
        raise UpdateError("No assets to sign")
    return {"version": version, "platforms": platforms}


def _load_config(spec: str) -> UpdateConfig:
    module, _, name = spec.partition(":")
    config = getattr(importlib.import_module(module), name, None) if name else None
    if not isinstance(config, UpdateConfig):
        raise UpdateError(f"{spec} is not an UpdateConfig")
    return config


def _asset(text: str) -> tuple:
    platform, sep, path = text.partition("=")
    if not sep or not path:
        raise argparse.ArgumentTypeError(f"expected PLATFORM=FILE, got {text!r}")
    return platform, path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analyze_common.update_manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sign_parser = subparsers.add_parser("sign", help="write a signed latest.json")
    sign_parser.add_argument("--config", required=True, help="PKG.MODULE:NAME of the app's UpdateConfig")
    sign_parser.add_argument("--tag", required=True)
    sign_parser.add_argument("--key", required=True, type=Path, help="Ed25519 private key (PEM)")
    sign_parser.add_argument("--out", required=True, type=Path)
    sign_parser.add_argument("assets", nargs="+", type=_asset, metavar="PLATFORM=FILE")
    key_parser = subparsers.add_parser("public-key", help="print the base64 public key of a PEM key")
    key_parser.add_argument("key", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "public-key":
            print(public_key(args.key))
            return 0
        assets = dict(args.assets)
        if len(assets) != len(args.assets):
            raise UpdateError("A platform is listed twice")
        manifest = build_manifest(_load_config(args.config), args.tag, args.key, assets)
        args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except (UpdateError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
