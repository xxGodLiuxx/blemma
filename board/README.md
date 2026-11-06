# board — 板の server と頁 / the board server and page

## 起こし方

```
python board/server.py
```

127.0.0.1 だけで待ち受け、起動ごとの token を `board/state/run.json` に書き、頁を既定のブラウザで開きます (Python 3.10 以上・標準ライブラリだけ)。止める = Ctrl+C (止めると hook は判断を返さず、Claude Code のいつもの確認に戻ります)。

| 旗 | 既定 | 意味 |
|---|---|---|
| `--port` | 8765 | 使用中なら起動を断る (別の port に黙って移らない) |
| `--wait` | 300 | 札の待ち (秒・表示から・540 まで) |
| `--perm-wait` | = `--wait` | 権限の札だけの待ち |
| `--undo-ms` | 3000 | 押した後の取り消しの猶予 (0〜5000) |
| `--allow-host NAME` | — | Host の照合に足す名 (携帯の転送で別の名を使う時) |
| `--no-browser` / `--no-log` | — | 頁を開かない / `board/state/log-*.jsonl` を書かない |

頁が「token がありません」と出たら、server の端末に出た URL (`#t=` つき) を開いてください。

頁がどこにも開かれていない時 (最後に見てから 30 秒・起動の時は「見た」と数える) は、板は新しい札を受けません。hook は判断なしで終わり、端末のいつもの確認が出ます (頁を閉じたまま端末が止まって見えないように)。開いていた札も切れます (決めた札は猶予を終えて渡します)。

### 頁の URL の引数

`http://127.0.0.1:8765/?dwell=1.2&scan=1.5&key=Space&lang=ja#t=<token>`

| 引数 | 既定 | 意味 |
|---|---|---|
| `dwell` | 1.0 | 視線の滞留で押す秒 (0.3〜5)。`0` = 頁の滞留を止めて click で押す (OS の視線の道具が click する時) |
| `scan` | なし | スイッチ 1 鍵の走査 (秒ごとに次のボタンへ)。`?scan` だけなら 1.5 |
| `key` | Space | 走査で選ぶ鍵 (`KeyboardEvent.code` か `key`・例 `Enter`・`F13`) |
| `lang` | ブラウザの言葉 | `ja` / `en` |
| `sound` | 切 | `on` = 待ちの合図で短い音 |
| `mode` | `large` | `small` = 扇 (`python blemma.py` の既定)・`large` = 大きなボタンの板 |
| `theme` | `auto` | `light`・`dark`・`contrast` (窓の ☀ ☾ でも切り替え) |
| `scale` / `font` | 1 | 窓の中の倍率 (0.75〜2) / 字の倍率 (0.8〜2) |
| `desc` | `on` | `off` = 選択肢の解説を出さない |
| `trail` | `off` | `on` = 見ている所に点を重ねる (録画用) |

頁の右上の「設定」でも替えられます (キーと click だけ・保存はブラウザの localStorage)。優先の順は URL の引数 > 保存した値 > 既定です。`blemma.py` からは `--set 鍵=値` か環境変数 `BLEMMA_OPTS` で渡せます。「携帯で開く」は `#t=` つきの URL を大きな字で出します。携帯は利用者の転送で 127.0.0.1 へ届けます (例 USB の Android = `adb reverse tcp:8765 tcp:8765`)。転送の先へ札の本文と token が渡ります。

### 入力

| 入力 | 押す | 取り消す (押した後の猶予のうち) |
|---|---|---|
| 視線 | ボタンの上に留まる (縁が満ちる)。外れても 150 ms のうちに戻れば数え続ける | 上の中央の「取り消す」に留まる |
| キー | Tab で移って Space / Enter・数字 1〜6・Esc = 左下の固定の位置のボタン | Backspace / Esc |
| スイッチ 1 鍵 | 光ったボタンで鍵を押す | 鍵を一度離してから、もう一度押す |
| 携帯 | 触る (縦 1 列) | 「取り消す」を触る |
| マウス | click | 「取り消す」を click |

札・設問・並びが替わったら、pointer の下のボタンは一度外へ出て入り直すまで数えず、押したままの鍵は離すまで数えません (見続けて 2 回押さない)。

## 手で確かめる (5 分)

1. `python board/server.py` で頁を開く。
2. 別の端末で、hook の代わりに札を 1 枚出す (repo の根で):
   `python -c "import sys; sys.path.insert(0, 'hooks'); import _client; print(_client.ask_detail({'cwd': '/x/demo', 'session_id': 'abcdef'}, 'permission', {'head': 'Bash', 'blocks': [{'label': 'command', 'text': 'ls', 'mono': True}]}))"`
3. 頁の「許可 (今回)」を見続ける (約 1 秒で押される) → 上の中央に「取り消す (3)」→ 猶予のうちに取り消す → 札が戻る。
4. もう一度押して 3 秒待つ → 端末に `('answered', {'type': 'allow_once'})`。「端末で答える」なら `('released', None)`。
5. server を止めた状態で 2. を打つ → すぐ `('no_board', None)` (= hook は何も書かず、Claude Code のいつもの確認へ)。

頁の純粋な計算 (滞留・走査・ボタンの並び・字) は `board/static/board_core.js` に分けてあり、node で読めます:
`node -e "const c = require('./board/static/board_core.js'); console.log(c.suggestionLabel({type: 'addRules', rules: [{toolName: 'Bash', ruleContent: 'git commit:*'}], behavior: 'allow', destination: 'localSettings'}, 'ja'))"`

自動の試験 = `python -m pytest tests -q` (試験だけ pytest が要ります)。

---

## In short (EN)

`python board/server.py` starts the board on 127.0.0.1 only (Python 3.10+, standard library only), writes a per-launch token to `board/state/run.json`, and opens the page in your default browser. Ctrl+C stops it; hooks then return no decision and Claude Code shows its normal prompt. If the page says there is no token, open the URL (with `#t=`) printed in the server's terminal. If no page has been open for 30 s (the server start counts as a view), the board refuses new cards and hooks fall back to the terminal's normal prompt; open cards expire, and a card already decided still finishes its grace period.

Page URL: `http://127.0.0.1:8765/?dwell=1.2&scan=1.5&key=Space&lang=en#t=<token>` — `dwell` = seconds to press by resting the pointer/gaze on a button (`0` = click only), `scan` = one-key switch scanning interval (`?scan` alone = 1.5 s), `key` = the switch key, `lang` = `ja`/`en`, `sound=on` = a short tone on Claude Code's notifications. Undo during the grace period: gaze/click/touch the top-center Undo button, Backspace/Esc on a keyboard, or release the switch and press it again. Phones reach 127.0.0.1 through your own forwarding (e.g. `adb reverse tcp:8765 tcp:8765`); the card text and the token travel to wherever you forward.

Hand check: start the server, then from the repo root run the `_client.ask_detail(...)` one-liner above, dwell on "Allow (this time)", undo within the grace, press again and wait — the terminal prints `('answered', {'type': 'allow_once'})`. Tests: `python -m pytest tests -q`.
