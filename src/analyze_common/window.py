"""Setup of the consumer's process for one OS; each function does nothing on the other OSes."""

import atexit
import faulthandler
import sys

_QUIT_LIMIT_SEC = 5


def set_app_user_model_id(app_id: str) -> None:
    """Set the process's AppUserModelID, by which the Windows taskbar groups windows and takes the icon embedded in
    the EXE (without it, the Python runtime's default ID is used and the taskbar shows no app icon)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def run_atexit_on_app_quit() -> None:
    """Run the atexit functions when the app quits on macOS, as they run when the last window closes.

    Quit (the app menu's item, Cmd+Q, logging out) goes through NSApplication's terminate:, which ends the process
    with C's exit() and leaves the interpreter unfinished, so without this nothing registered with atexit runs, and
    neither do the finalizers of a TemporaryDirectory still in use. The functions run on the main thread just before
    exit(). A process still running ``_QUIT_LIMIT_SEC`` seconds after that starts writes every thread's stack to file
    descriptor 2 and ends with exit code 1, also when a thread holds the GIL. On a failure to watch for Quit, the cause
    is reported on stderr and Quit works as it did without this.
    """
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        import Foundation

        Foundation.NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            AppKit.NSApplicationWillTerminateNotification, None, None, _finish_quit)
    except Exception as err:
        print(f"Could not watch for the app quitting: {err!r}", file=sys.stderr)


def _finish_quit(_notification) -> None:
    faulthandler.dump_traceback_later(_QUIT_LIMIT_SEC, file=2, exit=True)
    atexit._run_exitfuncs()
