# Development procedures

> English version: [development.md](development.md)

analyze-loudness と analyze-spectrum (利用側) が、このライブラリと共有する開発の手順。利用側のテストを git の worktree から走らせる、プルリクエストのコミットごとのテスト結果を取る、macOS で実アプリをマウスやキーボードの入力の合成なしで動かす、の 3 つを書く。以下、`<package>` は `analyze_loudness` か `analyze_spectrum`、`<product>` は `settings_dir()` に渡すフォルダー名 (`analyze-loudness` か `analyze-spectrum`)。

## Testing a consumer from a worktree

- 利用側の新しい worktree では、`vendor/py-analyze-common` が空になっている。先に `git -C <worktree> submodule update --init` を走らせる。
- 利用側の `.venv` には、主チェックアウトを指す editable install が入っている。テストは worktree から `PYTHONPATH=src <主チェックアウト>/.venv/bin/python -m pytest` で走らせ、`<package>.gui.__file__` を 1 回出して、どのツリーが import されたかを確かめる。
- まだコミットしていない、またはマージしていない py-analyze-common の worktree を当ててテストするときは、その `src` を先に、利用側自身の vendor のパスをその後ろに並べる: `PYTHONPATH=<共有の worktree>/src:<利用側の worktree>/vendor/py-analyze-common/src:src` (絶対パスで書く)。利用側の `src/<package>/__init__.py` は、vendor のパスが `sys.path` にまだ無いときだけ先頭に入れるので、vendor のパスを並べておけば、共有の worktree が前に残る。
- もう 1 つのやり方は、共有の worktree のファイルを submodule に重ねること: 共有の worktree の `src/` を、利用側の worktree の `vendor/py-analyze-common/src/` へ `rsync` する。共有のプルリクエストがマージされたら、`git -C <利用側の worktree>/vendor/py-analyze-common checkout -f --detach <マージコミット>` で置き換える前に、重ねた写しをマージコミットと `cmp` で比べる。利用側のプルリクエストを出す前に、submodule は利用側の `master` が指すコミットに戻しておく ([Changes that span this library and the consumers](../CLAUDE.md#changes-that-span-this-library-and-the-consumers))。
- 利用側の `master` に同じやり方で共有のブランチ全体を `vendor/py-analyze-common` として重ねると、利用側の変更が届く前に Dependabot の submodule の更新が作る状態をテストできる。

## Per-commit test runs

プルリクエストの本文に載せるコミットごとのテスト結果は、作業ツリーからではなく、そのコミットから取り出したツリーで取る:

1. `git archive <commit> | tar -x -C <dir>`
2. `git ls-tree <commit> vendor/py-analyze-common` でそのコミットの submodule の固定値を読み、その位置で py-analyze-common の detached な worktree を作り、`<dir>/vendor/py-analyze-common` をその worktree への symlink にする
3. `<dir>` から pytest を走らせる

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

実際の WKWebView のウィンドウでは、URL 欄にフォーカスがあるままウィンドウの幅が変わるとページが先頭へ動く現象 ([Shared frontend scripts](../CLAUDE.md#shared-frontend-scripts-web) の `_afterResize()`) が、同じビルドでも、起動によって起きたり起きなかったりする。この probe は、アプリごとに 3 回以上の起動で行う。動かなかった起動が 1 回あるだけでは、「直った」と読めてしまう。
