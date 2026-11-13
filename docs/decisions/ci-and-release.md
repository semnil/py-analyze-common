# CI and release decisions

> 日本語版は [ci-and-release.ja.md](ci-and-release.ja.md) を参照してください。

Closed decisions about the workflows, Dependabot and the release path of analyze-loudness, analyze-spectrum and this library. How they work today is in `AGENTS.md` ("yt-dlp version pin", "Releasing a consumer") and in the comments of each `.github/dependabot.yml`; this file keeps what was chosen, why, what was rejected and what would reopen a decision. `master` is a consumer's default branch.

## ffmpeg-watch lands with a GitHub App's token

- **Decision** (2026-10-21, semnil/analyze-loudness#86, semnil/analyze-spectrum#89): the land job of a consumer's `ffmpeg-watch.yml` pushes, opens its pull requests and merges them with the token of a GitHub App that has write access to Contents and Pull requests only, and waits for the pull requests' own `pull_request` and `pull_request_target` runs.
- **Reason**: with `GITHUB_TOKEN` the required checks of `master` cannot be met without a person. The premises are in `AGENTS.md` ("Patch release for an ffmpeg update"), and the refused merge is in the two pull requests above.
- **Rejected alternatives**:
  - A personal access token: the pull requests and merges would carry a person's name, and the token expires and has to be made again.
  - Keeping `GITHUB_TOKEN`, with a person approving the runs and `pull_request` added to `workflow-checks.yml`: no release would go out unattended, and a pull request could rewrite the check and pass it.
  - Reporting the required checks from runs started with `workflow_dispatch`: the ruleset does not count them. Not to be proposed again.
- **Decision** (2026-11-09, semnil/analyze-loudness#201, semnil/analyze-spectrum#203, semnil/py-analyze-common#63): land does not merge a pull request itself. Once the pull request's three runs succeed, it enables auto-merge on the head commit with the App's token and waits for GitHub to merge; whatever ends the step before the merge turns that auto-merge off on the way out.
- **Reason**: `codecov/project` became a required check of `master` on the same day, and Codecov reports it after the CI run. `gh pr checks --required` lists the checks already reported, so a merge made on its answer was refused by the ruleset.
- **Limit**: on a cancelled job the runner ends the step's shell 7.5 seconds after the interrupt, and the step does not wait for a call still running then, so the auto-merge can stay on with no error. How it works today is in `AGENTS.md` ("Patch release for an ffmpeg update").
- **Premise**: the merge GitHub makes through an auto-merge the App enabled starts the CI run of the push to `master`, as the App's own merge did, so `tag-release.yml` follows it. If that run does not come, the next run of `ffmpeg-watch.yml` starts `tag-release.yml` for the bump's commit (`release_sha`).

## What Dependabot updates

- **Decision** (2026-10-22, semnil/analyze-loudness#92, semnil/analyze-spectrum#95): each consumer's `.github/dependabot.yml` updates the workflow actions, the submodule and the Python dependencies (`uv`). The `uv` entry covers every dependency, not yt-dlp alone, and `test_locks_resolve_with_their_own_pins` (`analyze_common.testing.release_workflow`) fails a pull request whose pins contradict each other.
- **Reason**: Dependabot's `uv` update raises a transitive dependency without the extras the lock file was compiled with, so it can open a pull request whose lock no longer resolves while the other tests pass. The cases are in the pull requests above.
- **Rejected alternatives**: limiting `uv` to yt-dlp; leaving the Python dependencies out of Dependabot.
- **Schedule** (2026-10-25, semnil/analyze-loudness#114, semnil/analyze-spectrum#119, semnil/py-analyze-common#28): every entry runs on a cron schedule at 00:00 JST, because `interval: daily` runs on weekdays only.
- **The submodule entry is outside the cooldown** (2026-10-23, semnil/analyze-loudness#105, semnil/analyze-spectrum#110): Dependabot's default cooldown also holds back a submodule commit, so the `gitsubmodule` entry has `cooldown: exclude: ["*"]`. `default-days: 0` is not accepted (1 to 90).
- **yt-dlp-ejs** (2026-10-25, semnil/analyze-loudness#119, semnil/analyze-spectrum#124): analyze-loudness and analyze-spectrum depend on `yt-dlp-ejs`, the solver scripts yt-dlp uses, and yt-dlp takes them only when they are the version it expects. Dependabot moves the two in one pull request (the `yt-dlp` group of the `uv` entry), and `tests/test_yt_dlp_ejs.py` fails when they disagree. Rejected: the test alone or the group alone (one of the two can still be merged by itself); the extra `yt-dlp[default]` (six more packages, whose effect was not measured).
- **This library** (2026-10-25): its Dependabot also has a `uv` entry, which raises the yt-dlp pin in `pyproject.toml`.

## pyee is not updated on its own

- **Decision** (2026-10-23, semnil/analyze-spectrum#106, semnil/analyze-loudness#102): the `uv` entry of each consumer ignores `pyee`.
- **Reason**: pyee is a transitive dependency of playwright, which requires `pyee<15`. A pull request that raises pyee alone leaves `requirements/release.txt` without a resolution, fails a required check and is offered again every day. pyee is not pinned, so it still moves when a playwright update resolves the lock again. It comes only with playwright in the `dev` extra and is not in the shipped app, so stopping its security updates leaves the shipped app as it was.
- **Rejected alternative**: `allow` with `dependency-type: direct`, which stops every pull request for a transitive dependency alone, the security updates of the transitive dependencies that are shipped (those of pywebview and yt-dlp) included.

## What Dependabot merges by itself

- **Decision** (2026-10-22, semnil/analyze-loudness#98, semnil/analyze-spectrum#102, semnil/py-analyze-common#23): `dependabot-auto-merge.yml`, the same file in the three repositories, turns auto-merge on by package ecosystem and update type: `uv` at any semver level, a submodule always, a GitHub Action for a patch or minor update. For anything else it turns auto-merge off.
- **Narrowed** (2026-10-23, semnil/analyze-loudness#101, semnil/analyze-spectrum#107, semnil/py-analyze-common#26): only when the pull request is one commit that is the head of the event, written by Dependabot, committed by GitHub (`web-flow`) and with a verified signature. The update's metadata is read from the first commit only, and an amended commit keeps its author while its committer changes, so the author alone does not show that nobody else touched the pull request.
- **Superseded**: before 2026-10-22 only patch updates were merged, in every ecosystem.
- **Rejected alternative**: merging a pull request that a person added commits to, without looking at who wrote the commits.

## The submodule pointer is moved by Dependabot

- **Decision** (2026-10-31): the pointer of `vendor/py-analyze-common` in a consumer is moved by Dependabot's pull request and its auto-merge. A pull request that moves it by hand is opened only when it is asked for at that time. The rule and the order of the pull requests are in `AGENTS.md` ("Changes that span this library and the consumers").

## Detect runs again on another runner when it cannot connect

- **Decision** (2026-11-09, semnil/py-analyze-common#60, semnil/analyze-spectrum#202, semnil/analyze-loudness#200): `detect` exits 3 only when no address of a host accepted the connection, and the consumer's `ffmpeg-watch.yml` then dispatches itself, so that detect runs on another runner, up to three attempts.
- **Reason**: a runner that cannot connect to the host stays unable to for minutes, while other runners connect (`AGENTS.md`, "Patch release for an ffmpeg update").
- **Rejected alternatives**: a warning only, leaving the work to the next day's scheduled run; leaving the workflow as it was; trying again inside the same runner (a longer wait, or connecting again), which does not get through from that runner.
- **Waiting** (2026-11-11): the workflow dispatching itself, and the number passed in `detect_attempt`, have not run on GitHub yet. This was left to happen by itself rather than forced with a test run. The next time detect fails to connect, confirm that the `retry` job made the next run and that its detect ran as attempt 2.

## The full-length yt-dlp check runs on a local machine

- **Decision**: the full-length download that checks the yt-dlp pin is done in a local `.venv` before a consumer's version bump. Running it in CI is not to be proposed again.
- **Reason**: the download does not complete from GitHub's hosted runners (`AGENTS.md`, "yt-dlp version pin").
