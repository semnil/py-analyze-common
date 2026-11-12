# Security model of the analyze apps

> English version: [security-model.md](security-model.md)

analyze-loudness と analyze-spectrum に共通する入口、両アプリが取っている対策とその実装の場所、理由を付けて受け入れているリスクを書く。以下の `gui.py` と `cli.py` は、それぞれのアプリの `src/<package>/gui.py` と `src/<package>/cli.py`。`analyze_common/...` はこのライブラリ。アプリの作りは [architecture.ja.md](architecture.ja.md) にある。

## Entry points

| 入口 | 届く経路 | 検査するもの |
|---|---|---|
| コマンドラインの引数 | ローカルのシェル | argparse と、引数の型ごとの検証 |
| GUI の HTTP サーバー | `127.0.0.1` だけ | Host ヘッダー、Content-Type、URL かパス、パラメーター、JSON の本文 |
| フロントエンド | pywebview | 静的なファイルだけ。サーバーの側では何も描画しない |
| ファイルのダイアログ | OS 自身のダイアログ | 利用者がファイルを選ぶ (pywebview の `SAVE_DIALOG` / `OPEN_DIALOG`) |
| 更新の確認とダウンロード | github.com への HTTPS (外向き) | 製品名・版・OS・SHA-256 に対する Ed25519 の署名。リポジトリの releases の下の URL だけ。https のまま進むリダイレクトだけ。大きさと時間の上限 ([auto-update.ja.md](auto-update.ja.md) の「What is verified」) |

## Measures

| ID | 分野 | 対策 | 場所 |
|---|---|---|---|
| CM-01 | ネットワーク | サーバーは `127.0.0.1` の、OS が選ぶポートで待ち受ける | `gui.py` (`_HTTPServer(("127.0.0.1", 0), AnalyzeHandler)`) |
| CM-02 | ネットワーク | Host ヘッダーが `127.0.0.1` でも `localhost` でもない要求を断る (`_check_host()`)。別の名前を loopback のアドレスに解決させるページを止める | `analyze_common/server.py` (`do_GET`)、`gui.py` の `do_POST` の冒頭 |
| CM-03 | インジェクション | subprocess の引数はリストで渡し、シェルを通さない | `analyze_common/ffmpeg.py`、analyze-loudness の `analysis.py`、analyze-spectrum の `pcm.py` |
| CM-04 | クロスサイトスクリプティング | テキストは `textContent` でページに入れる。利用者の文字列を `innerHTML` に入れない | それぞれの `main.js`、`analyze_common/web/` |
| CM-05 | 入力の検証 | URL は `http://` か `https://` で始まるものだけ (`is_url()`) | `analyze_common/download.py`、`gui.py` |
| CM-06 | 入力の検証 | 数値は、先に `isinstance(..., bool)`、その後に `math.isfinite()` で検査する | `gui.py` |
| CM-07 | 入力の検証 | JSON として読めない本文は `None` になり、呼び出し側が 400 で答える | `analyze_common/server.py` (`_read_json_body()`) |
| CM-08 | ファイル | 保存と JSON の読み込みは、ネイティブのダイアログだけを通る | `gui.py` の `/save` と `/load`、`analyze_common/server.py` の `/save-image` |
| CM-09 | ファイル | `sanitize_filename()` が `[\\/:*?"<>|\x00-\x1f]` を置き換え、Windows の予約名を避ける | `analyze_common/download.py` |
| CM-10 | 一時ファイル | 作業フォルダーは `with` ブロックの `TemporaryDirectory`。キャッシュとアップロードのフォルダーは `mkdtemp()` で作り、`atexit` の関数で消す | `gui.py`、`cli.py` |
| CM-11 | 一時ファイル | 終了のとき、強制終了されたプロセスが残した一時フォルダーを消す。消すのは、1 時間のあいだ変わっておらず、ほかのインスタンスが動いていないときだけ。自分のキャッシュとアップロードのフォルダーは除く | `analyze_common/tempdirs.py` (`sweep_orphan_tempdirs()`)、`gui.py` |
| CM-12 | JSON | `json.dumps(allow_nan=False)` と、NaN と Infinity を置き換える `json_safe()` | `analyze_common/server.py` (`_json_response()`・`_send_event()`)、`analyze_common/json_util.py` |
| CM-13 | JSON | 読み込んだ JSON に NaN や Infinity があっても、同じ `_json_response()` を通して答える。`_json_response()` は `json_safe()` に切り替えて返す | `analyze_common/server.py` |
| CM-14 | HTTP | JSON の応答は `Content-Length` を持つ。NDJSON のストリームは `Connection: close` で閉じる | `analyze_common/server.py`、`gui.py` |
| CM-15 | HTTP | `do_POST` は、ハンドラーが上げた例外を受け、JSON の本文の 500 で答え、トレースバックを stderr に書く | `gui.py` |
| CM-16 | バイナリ | SHA256 の照合: uPlot は `build_assets/checksums.json`、macOS の ffmpeg / ffprobe は `build_assets/ffmpeg.json` と比べる | `analyze_common/build.py`、`analyze_common/ffmpeg_release.py` |
| CM-17 | subprocess | frozen の Windows のビルドは、`STARTF_USESHOWWINDOW` でプログラムを起動し、コンソールのウィンドウを出さない | `analyze_common/platform.py` (`subprocess_kwargs()`) |
| CM-18 | subprocess | ffmpeg と ffprobe は `LC_ALL=C` と `LANG=C` で走らせ、出力を 1 つの言語で解析する | `analyze_common/ffmpeg.py` (`ffmpeg_kwargs()`) |
| CM-19 | subprocess | 失敗した道具の stderr は、末尾の 200 文字だけを見せる | `gui.py`、`analyze_common/ffmpeg.py` |
| CM-20 | スレッド | `ThreadingHTTPServer` を使い、共有する状態は `threading.Lock` の下に置く | `analyze_common/server.py` (`GuiServer`)、`gui.py` |
| CM-21 | ファイルの大きさ | `/load` は、読む前にファイルの大きさで断る (`_MAX_LOAD_BYTES`。値はアプリごと) | `gui.py` |
| CM-22 | 自動更新 | ダウンロードしたインストーラーは、アプリに組み込んだ公開鍵で Ed25519 の署名を検証できたときだけ適用する | `analyze_common/update.py`、それぞれのアプリの `update.py` と `release.yaml` |

## Accepted risks

| ID | リスク | 受け入れている理由 |
|---|---|---|
| CA-01 | 同じホストのほかのプロセス | ローカルのサーバーは認証を持たない。ランダムなポートと、Host と Content-Type の検査 (CM-01、CM-02、`_check_content_type()`。別のオリジンのページは、サーバーが答えない preflight を通らないと、この検査を通れない) が、Web のページを締め出す。同じホストのプロセスは、ポートを見つければ、ページが呼ぶものを呼べる (解析を走らせる、「Check at launch」の設定を変える、など) |
| CA-02 | エラーメッセージの中の内部の情報 | メッセージには、ローカルのパスや、道具の出力の末尾 (CM-19) が入ることがある。送る先は `127.0.0.1` のページだけ |
| CA-03 | Cancel の後も続く処理 | Cancel は、ページの側で要求を終える。サーバーは次のイベントを送るときに気付き、起動していたプログラムはそれまで走る。作業フォルダーは `TemporaryDirectory` なので消える。強制終了されたプロセスが残したものは、後の終了のときに、CM-11 の条件で消える |
| CA-04 | `/save` と `/load` のファイル操作 | ローカルのマシンのネイティブのダイアログを通るので、利用者の操作が要る |

## Data and network

- テーマ、言語、「Check at launch」は、利用者の設定ファイル (`settings.json`) に置く。利用者が保存した結果の JSON と画像は、保存した場所に残る (CM-08)。一時ファイルが消える条件は CM-10 と CM-11 にある
- 認証のトークンも Cookie も無い。ローカルのエンドポイントは認証を持たず、Host と Content-Type の検査だけを行う
- 外部のネットワークのインターフェースで待ち受けるものは無い
- アプリが自分から行う外向きの接続は、起動時の更新の確認 (github.com の `latest.json`) だけで、設定で止められる
- 同梱するソフトウェアのライセンスは `THIRD_PARTY_LICENSES.txt` にあり、インストーラーに入る

## Using the list in an audit

新しい監査は、上の表の対策が、表の場所に今も実装されていることを確かめるところから始める。
