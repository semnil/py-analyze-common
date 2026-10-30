"""Tests each consumer runs on its own repository.

The consumer's ``tests/conftest.py`` calls ``configure()`` with its repository root and its package, and a test file of
the consumer imports the tests of one module here (``from analyze_common.testing.release_workflow import *``), which
pytest then collects as the consumer's own.
"""

from pathlib import Path

_app = None


def configure(root: Path, package: str) -> None:
    """The consumer's repository root and its Python package (``analyze_loudness``)."""
    global _app
    _app = (Path(root), package)


def app() -> tuple:
    """``(root, package)`` given to ``configure()``."""
    if _app is None:
        raise RuntimeError("analyze_common.testing.configure() was not called by the consumer's tests/conftest.py")
    return _app
