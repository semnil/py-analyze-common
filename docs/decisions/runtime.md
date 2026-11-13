# Runtime decisions

> 日本語版は [runtime.ja.md](runtime.ja.md) を参照してください。

Closed decisions about how the apps behave while they run and when they end. How the code works today is in `docs/architecture.md` ("GUI server (server)", "Temp folders a killed process left behind (tempdirs)", "Fetching over HTTPS (network)") and in `AGENTS.md` ("Temp folders a killed process left behind (tempdirs)"); this file keeps what was decided, on which facts, what was rejected and what would reopen a decision.

## The 5-second watch on Quit stays (macOS)

- **Decision** (2026-11-06, semnil/py-analyze-common#50): the limit that `run_atexit_on_app_quit()` arms with `faulthandler.dump_traceback_later` stays. A process whose exit work has not ended 5 seconds after Quit is ended.
- **How it was decided**: the facts were put together a second time, after an error in the first set, and the decision was made on the second set.
- **Facts it rests on** (a run from source):
  - A stalled exit ends at about 5 seconds with exit code 1 when the limit is armed. Without it the process was still running at 16 seconds, a second Quit changed nothing, and it had to be force-terminated. A built app's standard error is `/dev/null`, so where it stalled is not kept. In 692 Quits during an analysis the limit did not fire. These are in semnil/py-analyze-common#50.
  - The limit does not cover closing the window, and it does nothing on Windows.
  - With 100,000 files in the temp folders, the limit cuts an ordinary removal off at 5 seconds; without the limit the removal ended in 5.93 to 6.53 seconds. No path that makes 100,000 files was found in the code that was read.
- **Reopen when**: the limit is reported to have fired in use; or a path is found by which the files in the temp folders grow past 10,000.
- **Not asked for**: a change that lets a built app keep where it stalled.

## Temp folders when an old and a new version run together

- **Decision** (2026-11-07, semnil/analyze-loudness#182, semnil/analyze-spectrum#181): what happens when a version without `InstanceLock` and a version with it run at the same time stays as it is.
- **What happens**: the old version neither makes the lock nor reads it. Whichever of the two ends, the other's folders older than an hour are removed, and its next analysis fails with `[Errno 2]`. This is what happened before the lock existed, and it stops once every running copy is a version with the lock.
- **Rejected alternative**: a prefix of its own for the new version (`spectrum-v2_`, for one). In a trial the analysis then succeeded with the two versions mixed, but the new version no longer removed what was left under the old name.
- **Reopen when**: an old and a new version are found to run together on the auto-update path. Raise it again with what was measured.

## One Connection reset from network

- **Decision** (2026-10-31): one `[Errno 54] Connection reset by peer` seen while `network` (semnil/py-analyze-common#34) was verified is closed without a cause. It is looked at again if it comes back.
- **What was seen**: against a test host whose certificate is for another name, 48 connections through `network.urlopen()` gave one reset and 47 `Hostname mismatch`, and none was accepted. The standard `urllib` gave `Hostname mismatch` 49 times out of 49. In the 40 connections after the reset it did not appear again. The cause was not identified. semnil/py-analyze-common#34 holds the counts up to the reset.
- **Reopen when**: a reset appears again in a fetch through `network`. Start by comparing how often the new code and the standard `urllib` give a reset over the same number of connections, and raise it with the result. The first observation is not recorded as chance.
