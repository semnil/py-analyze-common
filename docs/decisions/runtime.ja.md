# Runtime decisions

> English version: [runtime.md](runtime.md)

アプリが動いている間と終わるときの動きについて、閉じた判断の記録。コードの今の動きは `docs/architecture.ja.md` (「GUI server (server)」「Temp folders a killed process left behind (tempdirs)」「Fetching over HTTPS (network)」) と `AGENTS.md` (「Temp folders a killed process left behind (tempdirs)」) にある。この文書には、何を決めたか、どの事実をもとに決めたか、却下した案、決定を開け直す条件を残す。

## The 5-second watch on Quit stays (macOS)

- **決定** (2026-11-06、semnil/py-analyze-common#50): `run_atexit_on_app_quit()` が `faulthandler.dump_traceback_later` で仕掛ける見張りを残す。Quit から 5 秒たっても終了の処理が終わらないプロセスは、終わらせる。
- **決めた経緯**: 最初にそろえた判断材料に誤りがあったので、材料をそろえ直し、そろえ直した材料で決めた。
- **もとにした事実** (ソースからの起動):
  - 見張りを仕掛けていると、終了の処理が止まったプロセスは約 5 秒で、終了コード 1 で終わる。見張りが無いと、16 秒たっても動いたままで、2 回目の Quit も効かず、強制終了が要った。ビルドしたアプリの標準エラーは `/dev/null` なので、止まった場所は残らない。解析中の Quit 692 回で、見張りが働いた回は無かった。ここまでは semnil/py-analyze-common#50 にある。
  - 見張りは、ウィンドウを閉じる経路には掛からない。Windows では何もしない。
  - 一時フォルダーに 10 万個のファイルがあると、見張りは通常の削除も 5 秒で打ち切る。見張りが無いと、削除は 5.93〜6.53 秒で終わった。ファイルが 10 万個になる経路は、読んだ範囲のコードには見つかっていない。
- **開け直す条件**: 見張りが実際の利用で働いたという報告があったとき。または、一時フォルダーのファイルが 1 万個を超えて増える経路が見つかったとき。
- **頼まれていないこと**: ビルドしたアプリで、止まった場所を残せるようにする変更。

## Temp folders when an old and a new version run together

- **決定** (2026-11-07、semnil/analyze-loudness#182・semnil/analyze-spectrum#181): `InstanceLock` を持たない版と、持つ版を同時に動かしたときの動きは、今のままにする。
- **起きること**: 古い版はロックを作らず、読まない。どちらの版が終わっても、もう一方の、1 時間より古いフォルダーが消え、もう一方の次の解析は `[Errno 2]` で失敗する。ロックができる前と同じ動きで、動いているものがロックを持つ版だけになれば起きない。
- **却下した案**: 新しい版に別の接頭辞 (たとえば `spectrum-v2_`) を使わせる案。試作では、新旧の版を混ぜても解析が成功したが、新しい版が、古い名前で残ったものを消さなくなった。
- **開け直す条件**: 自動更新の経路で、新旧の版が同時に動くと分かったとき。測った結果を添えて挙げ直す。

## One Connection reset from network

- **決定** (2026-10-31): `network` (semnil/py-analyze-common#34) を検証している間に 1 回だけ出た `[Errno 54] Connection reset by peer` は、原因を特定しないまま閉じる。もう一度出たら見直す。
- **見えたこと**: 証明書が別の名前のものになっているテスト用のホストに、`network.urlopen()` で 48 回つなぐと、reset が 1 回、`Hostname mismatch` が 47 回で、接続が受け入れられた回は無かった。標準の `urllib` は 49 回のうち 49 回が `Hostname mismatch` だった。reset の後の 40 回では出なかった。原因は特定していない。reset が出た回までの数は semnil/py-analyze-common#34 にある。
- **開け直す条件**: `network` を通る取得で、reset がもう一度出たとき。新しいコードと標準の `urllib` で、同じ回数つないだときに reset が出る割合を比べる測定から始め、結果を添えて挙げる。1 回目の観測を、偶然として記録したものではない。
