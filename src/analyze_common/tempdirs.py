"""Which instances of a program run, and the sweep of the temp folders a killed one left behind."""

import errno
import glob
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Collection

ORPHAN_MIN_AGE_SEC = 3600
# A lock file this new counts as a running instance, locked or not: its process may not have locked it yet.
_STARTING_SEC = 5
# On a file system without locks a lock file counts as a running instance until it is this old.
_NO_LOCKS_RUNNING_SEC = 24 * 3600

if sys.platform == "win32":
    import msvcrt

    def _try_lock(descriptor: int) -> bool:
        """False when another process holds the lock. Raises OSError when no lock can be taken."""
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as err:
            if err.errno == errno.EACCES:
                return False
            raise
        return True

    def _unlock(descriptor: int) -> None:
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(descriptor: int) -> bool:
        """False when another process holds the lock. Raises OSError when no lock can be taken."""
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            if err.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return False
            raise
        return True

    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _lock_file_prefix(prefix: str) -> str:
    return f"{prefix}instance_"


class InstanceLock:
    """Marks this process as a running instance of the program with the temp folder prefix ``prefix``.

    The mark is a lock the operating system holds on a file in the temp folder, so it ends with the process, however
    the process ends. Programs the process starts do not hold it. The file stays until ``release()`` or the sweep of
    another instance.
    """

    def __init__(self, prefix: str) -> None:
        self._descriptor, self.path = tempfile.mkstemp(prefix=_lock_file_prefix(prefix), suffix=".lock")
        try:
            if not _try_lock(self._descriptor):
                raise OSError("another process holds it")
        except OSError as err:
            print(f"Could not lock {self.path}: {err}", file=sys.stderr)

    def release(self) -> None:
        """Ends the mark and removes the file. Later calls do nothing."""
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        try:
            _unlock(descriptor)
        except OSError:
            pass
        os.close(descriptor)
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def __enter__(self) -> "InstanceLock":
        return self

    def __exit__(self, *args) -> None:
        self.release()


def _is_running(lock_file: str) -> bool:
    """Whether a process holds ``lock_file``, or may be about to. Removes a file no process holds.

    A file that cannot be read counts as running. A file on which no lock can be taken counts as running until it is
    ``_NO_LOCKS_RUNNING_SEC`` old.
    """
    try:
        age = time.time() - os.path.getmtime(lock_file)
        if age <= _STARTING_SEC:
            return True
        descriptor = os.open(lock_file, os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            if not _try_lock(descriptor):
                return True
        except OSError:
            if age <= _NO_LOCKS_RUNNING_SEC:
                return True
        else:
            _unlock(descriptor)
    except OSError:
        return True
    finally:
        os.close(descriptor)
    try:
        os.unlink(lock_file)
    except OSError:
        pass
    return False


def _other_instance_runs(prefix: str, lock: InstanceLock) -> bool:
    start = glob.escape(os.path.join(tempfile.gettempdir(), _lock_file_prefix(prefix)))
    return any(path != lock.path and _is_running(path) for path in glob.glob(start + "*.lock"))


def sweep_orphan_tempdirs(prefix: str, lock: InstanceLock, keep: Collection[str] = ()) -> None:
    """Remove the temp folders named ``prefix*`` not in ``keep`` that have not changed for ORPHAN_MIN_AGE_SEC.

    ``lock`` is this process's. While another instance runs nothing is removed, so a folder an instance uses stays.
    """
    if _other_instance_runs(prefix, lock):
        return
    now = time.time()
    for path in glob.glob(glob.escape(os.path.join(tempfile.gettempdir(), prefix)) + "*"):
        if path in keep:
            continue
        try:
            if os.path.islink(path) or not os.path.isdir(path):
                continue
            if now - os.path.getmtime(path) <= ORPHAN_MIN_AGE_SEC:
                continue
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
