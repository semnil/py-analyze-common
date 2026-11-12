# GUI decisions

> English version: [gui.md](gui.md)

analyze-loudness と analyze-spectrum が共有する GUI について、閉じた判断の記録。GUI の今の動きは `CLAUDE.md` (「Shared frontend scripts (web)」「Theme and language settings」) にある。この文書には、何を選んだか、理由、却下した案、途中で起きたことを残す。

## Rules both apps share live in common.css

- **決定** (2026-10-17): 両アプリで本文が同じ規則と、両テーマで値が同じ変数は、`src/analyze_common/web/common.css` に置く。それぞれの GUI が `/common/common.css` として配信し、自分の `style.css` より前に読み込む。変数の名前は analyze-spectrum が使っていたもの (`--text`・`--bg-card`・`--text-secondary`・`--text-muted`) にそろえた。
- **規則を移すと変わること**:
  - `common.css` へ移した規則は `style.css` より前に来るので、もとは自分より前にあった、同じ詳細度の `style.css` の規則に負ける。止まっている画面の画素の比較では出ず、hover と focus で出る。規則を移すときは、順序が逆になる組をすべて調べ、利用側の `tests/test_frontend.py` が hover と focus の計算後のスタイルを測る。
  - 逆の向き: Dependabot の submodule の更新は、利用側の移行より先に利用側の `master` へ届くので、`master` はしばらく「新しい `common.css` と古い `style.css`」の組み合わせになる。`common.css` に足した規則が、同じ状態を扱う古い `style.css` の規則より詳細度が高いと、足した規則が勝ち、古い `style.css` が定義していない変数を読む。古い規則がまだ扱っている状態を上書きする共有の規則は、`:where()` で詳細度を下げる。新しい `common.css` を古い利用側のフロントエンドに当てて、hover まで測る。
  - `@media (max-width: 480px)` の中の `h1` は、`style.css` の `h1` より後に来る必要があるので、それぞれの `style.css` に残す。
  - 移した後にマージされた機能が、移す前の変数の名前 (`--fg-muted`) を使っていたことがある。rebase のたびに古い名前を検索する。
- **実害の記録**: Cancel の hover の色が通常の hover の青になった (semnil/analyze-spectrum#67)。analyze-loudness の URL 欄のフォーカスリングが消えた (semnil/analyze-loudness#61)。古い `style.css` の上で Analyze の hover の面が透明になった (semnil/py-analyze-common#43)。

## Icons of the input bar buttons are drawn by JS

- **決定** (2026-11-04): 入力欄のボタンのアイコンは、`web/ui.js` の `_applyButtonIcons()` が描く。テーマの切り替えボタンや警告・エラーの印と同じ、`_createIcon()` の SVG を使う。
- **一緒に受け入れたこと**: Chromium は、スクリプトがアイコンを差し込むより前にページを描くことがあるので、Windows では最初のフレームにアイコンの無いボタンが出ることがある。この決定は、その時間差を測った上で行った (semnil/py-analyze-common#43)。
- **却下した案**: 同じ SVG をそれぞれの `index.html` に直接書く案。`common.css` の疑似要素に CSS のマスクを当てる案。

## Focus after a queue row moves

- **決定** (2026-11-04、semnil/py-analyze-common#44): テーマや言語の切り替えの後と、削除の後は、フォーカスを待ち行列の同じ位置に残す。並べ替えの後は、フォーカスがそのトラックについていく。先頭と末尾では、行そのものがフォーカスを受け取る。
- **却下した案**: 並べ替えの後もフォーカスを同じ位置に残す案。続けて押すと、別のトラックが動くことになる。

## The input bar wraps at 900 px

- **決定** (2026-11-04、semnil/py-analyze-common#45): 入力欄は、幅 900 CSS px 以下で折り返す。規則は `common.css` に置き、利用側は折り返しの規則を持たない。
- **理由**: 1 行に要る幅はフォントで変わる。semnil/py-analyze-common#44 の 800 px は 1 つのフォントで決めた値で、幅の広いフォントでは、収まらない幅でも 1 行のままになった。幅の値は semnil/py-analyze-common#45 にある。
- **却下した案**: ボタンをまとめ、規則に幅を持たせずにブラウザに折り返させる案。
- **Windows**: Windows のフォントで、実際の WebView2 のウィンドウの入力欄から部品がはみ出さないことを確かめた記録は、semnil/py-analyze-common#49 (「On Windows after the merge」) にある。

## The result area looks the same in both apps

- **決定** (2026-11-04、semnil/py-analyze-common#46): 結果欄のタイトルの行、保存のボタン、Copy のボタン、日付と音源の行を共有にした。選んだ向きは次のとおり。
  - タイトルの行は analyze-loudness に合わせ、タイトルを左、ボタンを右に置く。長いタイトルは省略記号で切らず、折り返す。
  - 保存のボタンは、analyze-spectrum と同じ primary の面にする。
  - エラーの行の背景は、analyze-loudness の不透明な色にする。
- **実害の記録**: 片方のテーマで変数が抜けていた件、ダークテーマで音源のリンクが 1.82:1 だった件、ツールバーが最初の Tab を取っていた件は、semnil/py-analyze-common#46 と semnil/analyze-spectrum#170 にある。

## The remaining differences between the apps (2026-11-05)

- **決定** (2026-11-05): 2 つのアプリに残っていた差を 1 つずつ決めた。
  - uPlot のダークテーマの規則の `!important` を消す (単体と比較の結果を Chromium と WebKit で描き比べて、画素の差は無かった)。
  - 既定のウィンドウは、両アプリとも 1200 x 900 にする。
  - Analyze を押すと、入力欄の音源が待ち行列へ移る。1 行なら単体の解析、2 行以上なら比較になる。analyze-loudness が analyze-spectrum の動きに合わせた。
  - 追加、削除、待ち行列に入る JSON は、表示中の結果を消す。Clear All は結果とステータスも消す。並べ替えは、表示中の比較の順番を入れ替える。
  - analyze-spectrum の要約の表は全幅にする。
  - `#status` は `common.css` で `min-height: 20px` にする。
  - 切れ目の無い凡例のラベルがページを横に広げたのは analyze-spectrum だけ (analyze-loudness の凡例はトラックの名前を載せない) なので、analyze-spectrum の `style.css` に `.u-legend .u-label { overflow-wrap: anywhere; }` を置く。
- **置き換わった旧決定**: `#status` は以前 `min-height: 40px` だった (スピナーと 2 行のカウントダウンが出てもレイアウトが動かないようにするため)。上の 20 px がこれを置き換えた。
- **実害の記録**: 全幅の表は、最初 `display: table` の形で示した。長いラベルがあると、表がウィンドウより広がった (1100 px のウィンドウで 1539 px)。行を `tbody` に入れ、`tbody` を `display: table; width: 100%` にして、表の枠の中で横にスクロールする形にした。画素は、示した案と同じ。

## The app name and chart titles stay in English

- **決定**: アプリの名前 (`app.title`) とグラフのタイトル (`chart.*`) は、`ja` の辞書でも英語の文字列のままにする。指標の名前 (Duration・Track・RMS・True Peak など) は、専門用語を中途半端に訳さないために、両方の言語で英語にする。ツールチップの説明文は日本語にする。

## The theme and language are kept in the settings file

- **決定** (2026-10-20、semnil/py-analyze-common#10・semnil/analyze-spectrum#74・semnil/analyze-loudness#71): 選んだテーマと言語は、アプリの設定ファイルに置く。ページへは、要求のたびに組み立てるスクリプト (`/common/settings.js`、`no-store`) で渡す。このライブラリの共有の部分を先に作り、アプリが後に続いた。
- **却下した案**:
  - ウィンドウの URL のクエリで値を渡す案: 再読み込みの後は古い値になり、ページが 2 つ目の写しを持つことになる。
  - pywebview を `private_mode=False` と固定のポートで起動し、localStorage が次の起動に残るようにする案: webview 自身の保存領域が正本のままになる。

## One writer for each label the page rewrites

- **決定** (semnil/analyze-spectrum#75・semnil/analyze-loudness#73): ページが状態によって書き換える文言 (テーマのボタン、処理中の送信ボタン) の書き手は 1 つにする。その要素の `data-i18n*` 属性は外す。
- **却下した案**: `applyStatic()` の後に文言を書き直す案。`DOMContentLoaded` のハンドラーの順序に依ることが変わらない。
