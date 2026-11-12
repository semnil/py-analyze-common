# Auto-update decisions

> English version: [auto-update.md](auto-update.md)

analyze-loudness と analyze-spectrum の自動更新について、閉じた判断の記録。更新の流れは [`docs/auto-update.ja.md`](../auto-update.ja.md) にある。この文書には、何を選んだか、却下した案、後から確かめたことを残す。

## The settings dialog keeps the focus while it waits

- **決定** (2026-10-20、semnil/py-analyze-common#8): 設定ダイアログが描き直される間も、ダイアログの部品が無効になっている間も、フォーカスをダイアログの中に残す。フォーカスのあった部品が無効になったときは、ダイアログそのものがフォーカスを受け取る。ダイアログに付くブラウザーのフォーカスリングは、そのまま出す。
- **却下した案**: フォーカスを BODY に置いたまま、文書の側でキーを受ける案。両方を行う案。`outline: none` でダイアログのリングを消す案。
- **実害の記録**: フォーカスが BODY にあると、Escape がページに届き、走っている解析が取り消された。経路は semnil/py-analyze-common#8 にある。

## A press outside the dialog does not move the focus

- **決定** (2026-10-20、semnil/py-analyze-common#9): ダイアログの外の領域を押したときは、どの押下でも既定の動作を止め、フォーカスが動かないようにする。外を押して閉じたときも、フォーカスは、閉じる処理が戻した先 (設定のボタン) に残る。
- **却下した案**: 確認の最中だけ既定の動作を止める案。キーを受ける案。

## Real-device checks

- **結果** (2026-11-12 にメンテナーが述べた内容): 更新の仕組みが入った最初のリリースより後のリリースで行うことにしていた実機の確認は、メンテナーが行い、問題は見つからなかった。対象は、Windows のインストーラー (UAC、mutex の待ち、元の利用者での再起動)、`%APPDATA%` の下に保存したテーマと言語、WebView2 での起動時の色、ボタンの文言。macOS の、`/Applications` にある Developer ID のビルドの入れ替えと、osascript を通る入れ替え。実際の webview での、キャンセルの表示、設定ダイアログの Escape と外側の押下、再起動の後のテーマと言語。
