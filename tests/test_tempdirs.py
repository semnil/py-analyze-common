"""The lock of a running instance, across real processes, and the sweep that reads it."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from analyze_common import tempdirs
from analyze_common.tempdirs import ORPHAN_MIN_AGE_SEC, InstanceLock, sweep_orphan_tempdirs

SRC = str(Path(tempdirs.__file__).resolve().parent.parent)
# Prints the lock file, starts the program given as an argument if there is one, prints its pid and waits on stdin.
_INSTANCE = """
import subprocess, sys
from analyze_common.tempdirs import InstanceLock
lock = InstanceLock("app_")
print(lock.path, flush=True)
if len(sys.argv) > 1:
    print(subprocess.Popen([sys.executable, "-c", sys.argv[1]]).pid, flush=True)
sys.stdin.readline()
"""
_SLEEPER = "import time; time.sleep(120)"
_LOCK_RELEASE_WAIT_SEC = 15


@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


@pytest.fixture
def lock(temp_dir):
    held = InstanceLock("app_")
    yield held
    held.release()


def _age(path, seconds) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


def _old_folder(temp_dir, name="app_old") -> Path:
    folder = temp_dir / name
    folder.mkdir()
    (folder / "inside").write_text("x", encoding="utf-8")
    _age(folder, ORPHAN_MIN_AGE_SEC + 1)
    return folder


def _instance(temp_dir, *args):
    env = {**os.environ, "PYTHONPATH": SRC, "TMPDIR": str(temp_dir), "TEMP": str(temp_dir), "TMP": str(temp_dir)}
    process = subprocess.Popen(
        [sys.executable, "-c", _INSTANCE, *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    return process, process.stdout.readline().strip()


def _end(process) -> None:
    process.kill()
    process.wait()
    process.stdin.close()
    process.stdout.close()


def _sweep_until_removed(folder, lock) -> None:
    """The operating system may free the lock of an ended process a moment after the process ended."""
    deadline = time.monotonic() + _LOCK_RELEASE_WAIT_SEC
    while folder.exists() and time.monotonic() < deadline:
        sweep_orphan_tempdirs("app_", lock)
        time.sleep(0.1)


def test_sweep_removes_old_folders_only_when_no_other_instance_runs(temp_dir, lock):
    old = _old_folder(temp_dir)
    new = temp_dir / "app_new"
    new.mkdir()
    _age(new, ORPHAN_MIN_AGE_SEC - 60)
    kept = _old_folder(temp_dir, "app_kept")
    other_program = _old_folder(temp_dir, "other_old")
    plain_file = temp_dir / "app_file"
    plain_file.write_text("x", encoding="utf-8")
    _age(plain_file, ORPHAN_MIN_AGE_SEC + 1)

    sweep_orphan_tempdirs("app_", lock, keep={str(kept)})

    assert not old.exists()
    assert new.is_dir()
    assert kept.is_dir()
    assert other_program.is_dir()
    assert plain_file.exists()
    assert Path(lock.path).exists()


def test_sweep_leaves_a_symlink_and_what_it_points_at(temp_dir, lock):
    target = _old_folder(temp_dir, "target")
    link = temp_dir / "app_link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as e:
        pytest.skip(f"no symlink here: {e}")
    sweep_orphan_tempdirs("app_", lock)
    assert link.is_symlink()
    assert target.is_dir()


def test_sweep_removes_nothing_while_another_process_holds_its_lock(temp_dir, lock):
    folder = _old_folder(temp_dir)
    process, other_lock = _instance(temp_dir)
    try:
        _age(other_lock, ORPHAN_MIN_AGE_SEC)
        sweep_orphan_tempdirs("app_", lock)
        assert folder.is_dir()
        assert Path(other_lock).exists()
    finally:
        _end(process)
    _sweep_until_removed(folder, lock)
    assert not folder.exists()
    assert not Path(other_lock).exists()


def test_sweep_goes_on_after_the_other_instance_released_its_lock(temp_dir, lock):
    folder = _old_folder(temp_dir)
    other = InstanceLock("app_")
    _age(other.path, ORPHAN_MIN_AGE_SEC)
    sweep_orphan_tempdirs("app_", lock)
    assert folder.is_dir()
    other.release()
    other.release()
    assert not Path(other.path).exists()
    sweep_orphan_tempdirs("app_", lock)
    assert not folder.exists()


def test_with_block_holds_the_lock_and_releases_it(temp_dir, lock):
    folder = _old_folder(temp_dir)
    with InstanceLock("app_") as other:
        _age(other.path, ORPHAN_MIN_AGE_SEC)
        sweep_orphan_tempdirs("app_", lock)
        assert folder.is_dir()
    assert not Path(other.path).exists()
    sweep_orphan_tempdirs("app_", lock)
    assert not folder.exists()


def test_a_program_the_instance_started_does_not_keep_its_lock(temp_dir, lock):
    folder = _old_folder(temp_dir)
    process, other_lock = _instance(temp_dir, _SLEEPER)
    started_pid = int(process.stdout.readline())
    try:
        _age(other_lock, ORPHAN_MIN_AGE_SEC)
        _end(process)
        _sweep_until_removed(folder, lock)
        assert not folder.exists()
    finally:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(started_pid)] if sys.platform == "win32" else ["kill", "-9", str(started_pid)],
            capture_output=True)


def test_a_new_lock_file_counts_as_running_until_it_is_old_and_not_held(temp_dir, lock):
    folder = _old_folder(temp_dir)
    starting = temp_dir / "app_instance_starting.lock"
    starting.write_text("", encoding="utf-8")
    sweep_orphan_tempdirs("app_", lock)
    assert folder.is_dir()
    assert starting.exists()
    _age(starting, tempdirs._STARTING_SEC + 1)
    sweep_orphan_tempdirs("app_", lock)
    assert not folder.exists()
    assert not starting.exists()


def test_the_lock_of_another_program_does_not_stop_the_sweep(temp_dir, lock):
    folder = _old_folder(temp_dir)
    with InstanceLock("other_") as other:
        _age(other.path, ORPHAN_MIN_AGE_SEC)
        sweep_orphan_tempdirs("app_", lock)
        assert not folder.exists()
        assert Path(other.path).exists()


@pytest.mark.parametrize("error, running", [
    (PermissionError("denied"), True),
    (OSError("broken"), True),
    (FileNotFoundError("removed during the check"), False),
])
def test_a_lock_file_that_cannot_be_opened_counts_as_running_unless_it_is_gone(temp_dir, monkeypatch, error, running):
    other = temp_dir / "app_instance_other.lock"
    other.write_text("", encoding="utf-8")
    _age(other, tempdirs._STARTING_SEC + 1)

    def refuse(path, *args, **kwargs):
        raise error

    with monkeypatch.context() as patched:
        patched.setattr(tempdirs.os, "open", refuse)
        assert tempdirs._is_running(str(other)) is running
    assert other.exists()


def test_release_goes_on_when_the_lock_or_the_file_will_not_go(temp_dir, monkeypatch):
    held = InstanceLock("app_")

    def refuse(*args):
        raise OSError("broken")

    with monkeypatch.context() as patched:
        patched.setattr(tempdirs, "_unlock", refuse)
        patched.setattr(tempdirs.os, "unlink", refuse)
        held.release()
    assert Path(held.path).exists()
    os.unlink(held.path)


def test_a_lock_file_that_will_not_go_does_not_count_as_running(temp_dir, monkeypatch):
    stale = temp_dir / "app_instance_stale.lock"
    stale.write_text("", encoding="utf-8")
    _age(stale, tempdirs._STARTING_SEC + 1)

    def refuse(path):
        raise PermissionError("in use")

    with monkeypatch.context() as patched:
        patched.setattr(tempdirs.os, "unlink", refuse)
        assert tempdirs._is_running(str(stale)) is False
    assert stale.exists()


def test_sweep_goes_on_past_a_folder_it_cannot_read(temp_dir, lock, monkeypatch):
    unreadable = _old_folder(temp_dir, "app_unreadable")
    old = _old_folder(temp_dir)
    getmtime = tempdirs.os.path.getmtime

    def refuse_one(path):
        if path == str(unreadable):
            raise OSError("gone")
        return getmtime(path)

    monkeypatch.setattr(tempdirs.os.path, "getmtime", refuse_one)
    sweep_orphan_tempdirs("app_", lock)
    assert unreadable.is_dir()
    assert not old.exists()


def test_a_lock_that_cannot_be_given_back_counts_as_running(temp_dir, monkeypatch):
    other = temp_dir / "app_instance_other.lock"
    other.write_text("", encoding="utf-8")
    _age(other, tempdirs._STARTING_SEC + 1)

    def refuse(descriptor):
        raise OSError("broken")

    monkeypatch.setattr(tempdirs, "_unlock", refuse)
    assert tempdirs._is_running(str(other)) is True
    assert other.exists()


def test_a_lock_that_cannot_be_taken_counts_as_running(temp_dir, lock, monkeypatch):
    folder = _old_folder(temp_dir)
    other = temp_dir / "app_instance_other.lock"
    other.write_text("", encoding="utf-8")
    _age(other, tempdirs._STARTING_SEC + 1)
    monkeypatch.setattr(tempdirs, "_try_lock", lambda descriptor: False)
    sweep_orphan_tempdirs("app_", lock)
    assert folder.is_dir()
    assert other.exists()
