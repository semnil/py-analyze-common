# CI and release decisions

> English version: [ci-and-release.md](ci-and-release.md)

analyze-loudness・analyze-spectrum・このライブラリの、ワークフローと Dependabot とリリースの経路について、閉じた判断の記録。今の動きは `AGENTS.md` (「yt-dlp version pin」「Releasing a consumer」) と、それぞれの `.github/dependabot.yml` のコメントにある。この文書には、何を選んだか、理由、却下した案、決定を開け直す条件を残す。`master` は利用側の既定のブランチ。

## ffmpeg-watch lands with a GitHub App's token

- **決定** (2026-10-21、semnil/analyze-loudness#86・semnil/analyze-spectrum#89): 利用側の `ffmpeg-watch.yml` の land ジョブは、Contents と Pull requests の書き込みだけを持つ GitHub App のトークンで push し、プルリクエストを開き、マージする。プルリクエスト自身の `pull_request` と `pull_request_target` の走行を待つ。
- **理由**: `GITHUB_TOKEN` では、人の手なしに `master` の必須チェックを満たせない。前提は `AGENTS.md` (「Patch release for an ffmpeg update」) にあり、マージが拒まれた記録は上の 2 つのプルリクエストにある。
- **却下した案**:
  - 個人のアクセストークン: プルリクエストとマージが人の名前になり、トークンは期限が来るたびに作り直すことになる。
  - `GITHUB_TOKEN` のまま、人が走行を承認し、`workflow-checks.yml` に `pull_request` を足す案: 無人で出るリリースが無くなり、プルリクエストが検査そのものを書き換えて通せる。
  - `workflow_dispatch` で起こした走行から必須チェックを出す案: ルールセットはそのチェックを数えない。再び提案しない。
- **決定** (2026-11-09、semnil/analyze-loudness#201・semnil/analyze-spectrum#203・semnil/py-analyze-common#63): land は、プルリクエストを自分ではマージしない。プルリクエストの 3 つの走行が成功したら、App のトークンで head のコミットに自動マージを有効にし、GitHub がマージするのを待つ。マージの前にステップが終わるときは、出る前にその自動マージを外す。
- **理由**: 同じ日に `codecov/project` が `master` の必須チェックになり、Codecov はそれを CI の走行の後に報告する。`gh pr checks --required` が並べるのは報告済みのチェックなので、その答えを見て行ったマージはルールセットに拒まれた。
- **限界**: ジョブが取り消されると、ランナーは割り込みの 7.5 秒後にステップのシェルを終わらせ、ステップはそのとき走っている呼び出しを待たない。自動マージが、エラーなしで有効のまま残りうる。今の動きは `AGENTS.md` (「Patch release for an ffmpeg update」) にある。
- **前提**: App が有効にした自動マージで GitHub が行うマージは、App 自身のマージと同じく、`master` への push の CI を起こす。そのため `tag-release.yml` が続く。その走行が来ないときは、次の `ffmpeg-watch.yml` の走行が、版上げのコミット (`release_sha`) に `tag-release.yml` を起こす。

## What Dependabot updates

- **決定** (2026-10-22、semnil/analyze-loudness#92・semnil/analyze-spectrum#95): 利用側それぞれの `.github/dependabot.yml` は、ワークフローの action、submodule、Python の依存 (`uv`) を更新する。`uv` のエントリは yt-dlp だけでなくすべての依存を対象にし、固定値どうしが食い違うプルリクエストは `test_locks_resolve_with_their_own_pins` (`analyze_common.testing.release_workflow`) が落とす。
- **理由**: Dependabot の `uv` の更新は、ロックファイルを作ったときの extra を付けずに間接の依存を上げるので、ほかのテストが通ったまま、ロックが解けなくなったプルリクエストを開くことがある。実例は上のプルリクエストにある。
- **却下した案**: `uv` を yt-dlp だけに絞る案。Python の依存を Dependabot から外す案。
- **スケジュール** (2026-10-25、semnil/analyze-loudness#114・semnil/analyze-spectrum#119・semnil/py-analyze-common#28): どのエントリも、cron のスケジュールで毎日 00:00 JST に走らせる。`interval: daily` は平日だけ走るため。
- **submodule のエントリは cooldown の外に置く** (2026-10-23、semnil/analyze-loudness#105・semnil/analyze-spectrum#110): Dependabot の既定の cooldown は submodule のコミットも待たせるので、`gitsubmodule` のエントリに `cooldown: exclude: ["*"]` を置く。`default-days: 0` は受け付けられない (1 から 90)。
- **yt-dlp-ejs** (2026-10-25、semnil/analyze-loudness#119・semnil/analyze-spectrum#124): analyze-loudness と analyze-spectrum は、yt-dlp が使う解析用のスクリプト `yt-dlp-ejs` に依存する。yt-dlp は、自分が期待する版のときだけこのスクリプトを使う。Dependabot は 2 つを 1 つのプルリクエストで動かし (`uv` のエントリの `yt-dlp` グループ)、食い違うと `tests/test_yt_dlp_ejs.py` が落ちる。却下した案: テストだけ、またはグループだけにする案 (片方だけがマージされうる)。extra の `yt-dlp[default]` を使う案 (パッケージが 6 つ増え、その影響は測っていない)。
- **このライブラリ** (2026-10-25): このライブラリの Dependabot にも `uv` のエントリを置き、`pyproject.toml` の yt-dlp の固定値を上げる。

## pyee is not updated on its own

- **決定** (2026-10-23、semnil/analyze-spectrum#106・semnil/analyze-loudness#102): 利用側それぞれの `uv` のエントリは、`pyee` を無視する。
- **理由**: pyee は playwright の間接の依存で、playwright は `pyee<15` を要求する。pyee だけを上げるプルリクエストは、`requirements/release.txt` が解けなくなり、必須チェックで落ち、毎日出し直される。pyee は固定していないので、playwright の更新でロックを解き直せば動く。pyee は `dev` の extra の playwright と一緒にだけ入り、出荷するアプリには入らないので、pyee のセキュリティ更新を止めても、出荷するアプリは変わらない。
- **却下した案**: `allow` に `dependency-type: direct` を置く案。間接の依存だけを上げるプルリクエストがすべて止まり、出荷する間接の依存 (pywebview と yt-dlp のもの) のセキュリティ更新も止まる。

## What Dependabot merges by itself

- **決定** (2026-10-22、semnil/analyze-loudness#98・semnil/analyze-spectrum#102・semnil/py-analyze-common#23): 3 つのリポジトリで同じファイルの `dependabot-auto-merge.yml` は、パッケージの種類と更新の種類で、自動マージを有効にするかを決める: `uv` は semver のどの水準でも、submodule は常に、GitHub Action は patch と minor の更新のとき。それ以外では自動マージを無効にする。
- **さらに絞った** (2026-10-23、semnil/analyze-loudness#101・semnil/analyze-spectrum#107・semnil/py-analyze-common#26): プルリクエストが 1 コミットで、それがイベントの head であり、Dependabot が書き、GitHub (`web-flow`) がコミットし、署名が検証済みのときだけにした。更新の情報は先頭のコミットだけから読まれ、amend したコミットは author が残って committer が変わるので、author だけでは、ほかの人の手が入っていないことが分からない。
- **置き換わった旧決定**: 2026-10-22 より前は、どの種類でも patch の更新だけをマージしていた。
- **却下した案**: 人がコミットを足したプルリクエストも、誰がコミットを書いたかを見ずにマージする案。

## The submodule pointer is moved by Dependabot

- **決定** (2026-10-31): 利用側の `vendor/py-analyze-common` の固定値は、Dependabot のプルリクエストとその自動マージが動かす。手で動かすプルリクエストは、そのつど頼まれたときだけ開く。規則とプルリクエストの順番は `AGENTS.md` (「Changes that span this library and the consumers」) にある。

## Detect runs again on another runner when it cannot connect

- **決定** (2026-11-09、semnil/py-analyze-common#60・semnil/analyze-spectrum#202・semnil/analyze-loudness#200): `detect` は、ホストのどのアドレスも接続を受け付けなかったときだけ終了コード 3 を返す。利用側の `ffmpeg-watch.yml` はそのとき自分を起こし直し、detect を別の runner で走らせる (3 回まで)。
- **理由**: ホストへつながらない runner は数分のあいだつながらないままで、その間もほかの runner はつながる (`AGENTS.md`「Patch release for an ffmpeg update」)。
- **却下した案**: 警告だけを出して、翌日の定期実行に任せる案。ワークフローを今のままにする案。同じ runner の中でやり直す案 (待ち時間を延ばす、つなぎ直す)。その runner からは通らない。
- **待つと決めたこと** (2026-11-11): ワークフローが自分を起こし直すことと、`detect_attempt` に渡す数値は、GitHub の上でまだ動いていない。試しの走行で確かめることはせず、自然に起きるのを待つ。次に detect が接続に失敗したら、`retry` のジョブが次の走行を作ったことと、その走行の detect が 2 回目として動いたことを確かめる。

## The full-length yt-dlp check runs on a local machine

- **決定**: yt-dlp の固定値を確かめる全長のダウンロードは、利用側の版上げの前に、手元の `.venv` で行う。CI で走らせる案は、再び提案しない。
- **理由**: GitHub のホストする runner からは、このダウンロードが最後まで進まない (`AGENTS.md`「yt-dlp version pin」)。
