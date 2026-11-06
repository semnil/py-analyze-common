"""Programs that end with this process."""

import atexit
import threading
import weakref

_programs = weakref.WeakSet()
_lock = threading.Lock()
_killing_first = False
_ending = False


def start_program(start):
    """Return ``start()``, a started process that the atexit functions kill while it runs.

    A start and the kill run one at a time, so a program is either killed or not started: once the kill has run, this
    raises RuntimeError without calling ``start``. The kill runs before the atexit functions registered before the
    first start.
    """
    global _killing_first
    with _lock:
        if _ending:
            raise RuntimeError("Not starting a program: this process is ending")
        if not _killing_first:
            atexit.register(_kill_programs)
            _killing_first = True
        process = start()
        _programs.add(process)
    return process


def _kill_programs() -> None:
    global _ending
    with _lock:
        _ending = True
        for program in _programs:
            program.kill()


# A first start while the atexit functions run registers too late to run, so the kill is also registered here.
atexit.register(_kill_programs)
