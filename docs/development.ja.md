# Development procedures

> English version: [development.md](development.md)

analyze-loudness と analyze-spectrum (利用側) が、このライブラリと共有する開発の手順。利用側のテストを git の worktree から走らせる、プルリクエストのコミットごとのテスト結果を取る、macOS で実アプリをマウスやキーボードの入力の合成なしで動かす、の 3 つを書く。最後の 2 つの節には、このライブラリの CI の動きと、利用側の ffmpeg の更新のワークフローがすることを書く。以下、`<package>` は `analyze_loudness` か `analyze_spectrum`、`<product>` は `settings_dir()` に渡すフォルダー名 (`analyze-loudness` か `analyze-spectrum`)。

## Testing a consumer from a worktree

- 利用側の新しい worktree では、`vendor/py-analyze-common` が空になっている。先に `git -C <worktree> submodule update --init` を走らせる。
- 利用側の `.venv` には、主チェックアウトを指す editable install が入っている。テストは worktree から `PYTHONPATH=src <主チェックアウト>/.venv/bin/python -m pytest` で走らせ、`<package>.gui.__file__` を 1 回出して、どのツリーが import されたかを確かめる。
- まだコミットしていない、またはマージしていない py-analyze-common の worktree を当ててテストするときは、その `src` を先に、利用側自身の vendor のパスをその後ろに並べる: `PYTHONPATH=<共有の worktree>/src:<利用側の worktree>/vendor/py-analyze-common/src:src` (絶対パスで書く)。利用側の `src/<package>/__init__.py` は、vendor のパスが `sys.path` にまだ無いときだけ先頭に入れるので、vendor のパスを並べておけば、共有の worktree が前に残る。これが届くのは Python の import だけ。利用側のフロントエンドのテストは、`web/` の下の共有のファイルを、`vendor/py-analyze-common` からファイルのパスで読む (`tests/frontend/test_ui.html`)。そのため、それらのファイルの変更は、次の重ねるやり方でテストする。
- もう 1 つのやり方は、共有の worktree のファイルを submodule に重ねること: 共有の worktree の `src/` を、利用側の worktree の `vendor/py-analyze-common/src/` へ `rsync` する。共有のプルリクエストがマージされたら、`git -C <利用側の worktree>/vendor/py-analyze-common checkout -f --detach <マージコミット>` で置き換える前に、重ねた写しをマージコミットと `cmp` で比べる。利用側のプルリクエストを出す前に、submodule は利用側の `master` が指すコミットに戻しておく ([Changes that span this library and the consumers](../AGENTS.md#changes-that-span-this-library-and-the-consumers))。
- 利用側の `master` に同じやり方で共有のブランチ全体を `vendor/py-analyze-common` として重ねると、利用側の変更が届く前に Dependabot の submodule の更新が作る状態をテストできる。

## Per-commit test runs

プルリクエストの本文に載せるコミットごとのテスト結果は、作業ツリーからではなく、そのコミットから取り出したツリーで取る:

1. `git archive <commit> | tar -x -C <dir>`
2. `git ls-tree <commit> vendor/py-analyze-common` でそのコミットの submodule の固定値を読み、その位置で py-analyze-common の detached な worktree を作り、`<dir>/vendor/py-analyze-common` をその worktree への symlink にする
3. `<dir>` から `PYTHONPATH=src <主チェックアウト>/.venv/bin/python -m pytest` を走らせる。`PYTHONPATH=src` が無いと、`.venv` の editable install が、そのコミットのものではなく主チェックアウトのパッケージを import する。`<package>.__file__` と `analyze_common.__file__` を 1 回表示して、どちらも `<dir>` の下から来ていることを確かめる

analyze-loudness の `pyproject.toml` には `testpaths` が無いので、`<dir>` からの走行は `vendor/py-analyze-common` の下のテストも集め、件数が多くなる。analyze-spectrum の `testpaths` は `["tests"]`。rebase したブランチは走らせ直す。

## Probing the real app on macOS

実際の GUI は、自分のプロセスの中から端から端まで動かせる。ページ自身の fetch と POST の経路が WKWebView の中で走り、マウスやキーボードの入力は合成しない。

### Keeping the user's settings out of a probe

- macOS の `settings_dir()` は、設定のフォルダーを `Path.home()` から決める。`Library/Application Support/<product>/settings.json` を置いた一時フォルダーを `HOME` に指定してアプリを起動すれば、利用者自身の設定ファイルは読まれず、書かれない。
- `<package>.gui` を自分のプロセスに import する probe (`gui.main()` を呼ぶスクリプトや、ハンドラーを同じプロセスで配信する Playwright の probe) は、ページのテーマや言語のボタンが押された時点で本物の設定ファイルを書く (押すと `/settings` へ POST するため)。`gui._settings.path` を一時ファイルへ向けるか、`gui` を import する前に、`analyze_common.settings.settings_dir` と `analyze_common.update.settings_dir` の両方を、一時フォルダーを返す関数に差し替える (利用側の `tests/conftest.py` の `_isolated_settings` と同じ形)。ページを読み込む前に、ストアのパスが一時フォルダーの下にあることを assert する。
- 保存しておく値は、OS の設定 (`defaults read -g AppleInterfaceStyle`、`defaults read -g AppleLanguages`) と逆のものを選ぶ。同じ値だと、撮った画像から、保存した値と、ページが OS から取る既定の値とを区別できない。

### Driving the page

- ソースから起動する場合: `webview.start` を、`drive` という関数を本物の `webview.start` に渡す関数 (`lambda **kw: real_start(drive, **kw)`) に差し替えてから `gui.main()` を呼ぶ。`drive` はウィンドウのスレッドの外で動く。`gui._window.events.loaded.wait()` の後に `evaluate_js` を呼び、たとえば `#url-input` に値を入れて `#analyze-form` の `requestSubmit()` を呼び `#results .title-row` が出るのを待つ、あるいは `#theme-toggle` をクリックする。`window.destroy()` でウィンドウを閉じる。
- ビルドした `.app` は、外からの `evaluate_js` を受け付けない。`Contents/MacOS/<実行ファイル>` を、環境変数を `HOME`・`TMPDIR`・`PATH=/usr/bin:/bin` だけにして直接起動すると、利用者の設定と、バンドルの外の ffmpeg から切り離せる。ページを操作するには、`.app` をコピーし、コピーの `frontend/index.html` に同じオリジンのスクリプトを 1 本足す。スクリプトは、結果をアプリの `/upload` に `.wav` の名前で送れば外へ渡せる (アプリはアップロードを `TMPDIR` の下に書く)。

### Capturing the window

- Quartz の `CGWindowListCopyWindowInfo` でプロセス ID からウィンドウ番号を引き、`screencapture -x -l<番号> <出力先>` で撮る。画像にはウィンドウの影が入り (`-o` を付けると入らない)、倍率 2 の画面ではウィンドウの大きさの 2 倍の画素になる。`screencapture` を走らせるプロセスには、Screen Recording の許可が要る。
- 落ち着いた後のウィンドウを撮るときは、1 秒おきに撮り、2 枚がバイト単位で一致するまで繰り返す。この撮り方では、起動の途中の見た目は分からない。起動の途中の色は、semnil/py-analyze-common#14 のように、最初のフレームから読む。
- 実ポインターの下にウィンドウが開くと、ページの上にツールチップ (`.tip-popup`) が出る。撮る前に CSS で隠す。
- 画面が 2 つ以上あるときは、`webview.create_window(..., screen=webview.screens[i])` で画面を決め、`window.devicePixelRatio` を記録する。キャンバスのフォントの大きさは倍率込みの値になるので、画面に依る値は画面ごとに変わる。

### The README screenshots

利用側それぞれの `docs/screenshot.png` は、この手順で実アプリのウィンドウを撮ったもの: ダークテーマ、日本語、両アプリで同じ音源、既定のウィンドウの大きさ (1200 x 900)。撮る前に、画像に載る UI のプルリクエストがマージ済みか、ツリーが同じ状態かを確かめる。

### Probes whose result depends on the launch

実際の WKWebView のウィンドウでは、URL 欄にフォーカスがあるままウィンドウの幅が変わるとページが先頭へ動く現象 ([Shared frontend scripts](architecture.ja.md#shared-frontend-scripts-web) の `_afterResize()`) が、同じビルドでも、起動によって起きたり起きなかったりする。この probe は、アプリごとに 3 回以上の起動で行う。動かなかった起動が 1 回あるだけでは、「直った」と読めてしまう。

## CI of this library

CI (`.github/workflows/ci.yml`) は、プルリクエストと main への push で走る: その matrix は、Ubuntu 24.04 (`test`) と macOS 26 (`test-macos`) で、`fail-fast: false` で走る。どちらも Python 3.12 に `pip install -e . pytest pytest-cov` を入れ、`python -m pytest -q --cov --cov-report=xml` を走らせ、`coverage.xml` を artifact としてジョブ `coverage` に渡す。チェック `test` と `test-macos` は、main の必須チェックである。ジョブ `test-tempdirs-windows` は、Windows Server 2025 で `tests/test_tempdirs.py` を走らせ、同じやり方でレポートを渡す。これは main の必須チェックではない。3 つのレポートが全部そろうと、`coverage` はそれぞれを `codecov/codecov-action` で Codecov へ送る。`.github/codecov.yml` が `codecov.notify.after_n_builds: 3` を設定しているので、Codecov は、先に届いたものからではなく、3 つのレポートの全部からステータスを出す。Codecov は、同じコミットのアップロードをまとめる。このジョブの `id-token: write` によって、アップロードは GitHub の OIDC のトークンで認証できる (`use_oidc: true`) ので、リポジトリは Codecov のトークンを持たない。プルリクエストでは、アップロードの失敗が `coverage` を失敗にする (`fail_ci_if_error: true`)。main への push では、ステップの `continue-on-error` が走行を緑のままにする (.github/workflows/ci.yml:128)。`codecov/project` は main の必須チェックで、3 つのアップロードが届いてから Codecov が報告する。`codecov/patch` は必須チェックではない。artifact は、1 つの走行の中でレポートを渡すもので、1 日だけ残る。Codecov は、coverage.py が XML に書く `timestamp` より 12 時間を超えて古いレポートを処理しない (`codecov.max_report_age`。既定値のまま)。そのため、失敗した `coverage` ジョブの再実行がレポートを使い回せるのは、テストの走行から 12 時間以内だけである。それを過ぎたら、全部のジョブを再実行して、レポートを作り直す。

## Patch release for an ffmpeg update

利用側の `.github/workflows/ffmpeg-watch.yml` がすることを、ジョブごとに書く。前提と、人がすることは、`AGENTS.md` の同じ見出しの節にある。

1. detect: ジョブが始まった時点の master の先頭を、タグと履歴も含めて checkout し、`build_assets/ffmpeg.json` を osxexperts.net のページと比べる ([Bundled ffmpeg pin](../AGENTS.md#bundled-ffmpeg-pin-ffmpeg_release))。ページに違うビルドがあるときは、BtbN に同じ series があることを確かめ、両方のファイルの SHA256 を照らし、新しい固定値を作る。`__version__` が最新の `vX.Y.Z` のタグと等しく、かつ、今回固定値が変わるか、今の固定値がそのタグでリリースした固定値 (タグの中の固定値のファイル。タグにファイルが無いときは、タグの後でファイルが最初に足されたときの固定値) と違うときに、パッチリリースを作る
2. smoke: detect が記録したコミットそのものを checkout し、macOS と Windows の runner で、そのコミットの固定値 (`pin_update=true` のときは、候補の artifact で置き換える) を使って `build.py --ffmpeg-only` で取得したバイナリーに、`tests/test_ffmpeg_binary.py` を走らせる
3. land: 固定値のプルリクエスト (`ffmpeg-watch/pin-<series>-<run id>-<attempt>`) と、版上げだけのプルリクエスト (`ffmpeg-watch/bump-v<version>-<run id>-<attempt>`、`chore: update the version to vX.Y.Z`) を、この順に開く。push、プルリクエストを開くこと、自動マージを有効にすることは GitHub App のトークン (前提は `AGENTS.md` の同じ見出しの節) で行い、プルリクエストと走行を読むのは GITHUB_TOKEN で行う。それぞれのプルリクエストは、`pull_request` の CI (`Test 🧪`) と `dependabot-auto-merge.yml` (`auto-merge`) の走行、`pull_request_target` の `workflow-checks.yml` (`action-pins`) の走行を起こす。head のコミットでその 3 つの走行が成功すると、land はそのコミットに自動マージを有効にし (`gh pr merge --auto --merge --match-head-commit`)、GitHub がプルリクエストをマージするのを待つ。GitHub は、master のルールセットの必須チェックが全部通ったときにマージする。その 1 つの `codecov/project` は、CI の走行の後に Codecov が報告する。`gh pr checks --required` が並べるのは報告済みのチェックだけなので、このコマンドの答えを見て行うマージは、`codecov/project` が報告される前になることがあり、ルールセットがそれを拒む。版上げのマージの後、master への push の CI の走行が成功すると、`tag-release.yml` がマージコミットにタグを付ける ([Release procedure](../AGENTS.md#release-procedure) の手順 2)。これらのプルリクエストに GITHUB_TOKEN は使わない: GITHUB_TOKEN が開くプルリクエストは `pull_request_target` の走行を起こさず、その `pull_request` の走行は承認を待つ。また、`workflow_dispatch` で起こした走行のチェックは、master のルールセットの必須チェックとして数えられない (そういうプルリクエストのマージは、`3 of 3 required status checks are expected.` で拒まれた)
4. 人が Release を公開する ([Release procedure](../AGENTS.md#release-procedure) の手順 4)

- 前の走行のプルリクエスト (head が `ffmpeg-watch/` の、開いているプルリクエスト) が残っているとき、land は何も変えずに失敗する。そのプルリクエストを閉じるかマージしてから、もう一度走らせる。ブランチ名は走行ごとに違う (run id と attempt) ので、プルリクエストを開く前に失敗した走行が push したブランチは、次の走行の push とぶつからない (そのブランチは、プルリクエストの無いまま残る)。固定値のプルリクエストだけがマージされ、版上げが残っているとき、次の走行の detect は、「今の固定値が、最新のタグがリリースした固定値と違う」として、版上げから再開する。版上げがマージされたのにタグが無いとき (たとえば、その push の CI の走行が失敗したとき)、次の走行の detect は、`__version__` をその値にした master のコミットを報告し (`release_sha`)、land がそのコミットを渡して `tag-release.yml` を起こす。タグがすでにあれば、何もしない
- smoke か、プルリクエストの走行のどれか (CI、auto-merge、action-pins) が失敗したとき、または走行が 3 分以内に始まらないとき、land はそこで止まり、マージしない
- land が、GitHub がプルリクエストをマージするのを待っている間、必須チェックの失敗、マージされないまま閉じられたプルリクエスト、マージの無いままの 10 分は、どれも land を止める。land がプルリクエストの自動マージを有効にした後は、プルリクエストがマージされるか閉じられる前に land のステップを終わらせるもの (上のどれかの停止、失敗したコマンド、取り消されたジョブのステップに runner が送る SIGINT) が何であっても、ステップは出る前に GitHub を呼んで、その自動マージを外す。そのため、後から通ったチェックがプルリクエストをマージすることは無い。その呼び出しが失敗すると、ステップはエラー `could not turn the auto-merge of #<number> off, so it can still merge` で失敗する。取り消されたジョブでは、runner は SIGINT の 7.5 秒後に SIGTERM でステップのシェルを終わらせ (actions/runner `src/Runner.Sdk/ProcessInvoker.cs`)、ステップは、そのときまだ走っている呼び出しを待たない: その呼び出しが終わらなければ、自動マージは有効のまま残り、エラーは報告されない
