# board — 板の server と頁 / the board server and page

## 起こし方

```
python board/server.py
```

127.0.0.1 だけで待ち受け、起動ごとの token を `board/state/run.json` に書き、頁を既定のブラウザで開きます (Python 3.10 以上・標準ライブラリだけ)。止める = Ctrl+C (止めると hook は判断を返さず、Claude Code のいつもの確認に戻ります)。

| 旗 | 既定 | 意味 |
|---|---|---|
| `--port` | 8765 | 使用中なら起動を断る (別の port に黙って移らない)。別の port の 2 枚目は在処 (`run.json`) を奪うので、先の板を止めてから起こす |
| `--wait` | 300 | 札の待ち (秒・表示から・540 まで) |
| `--perm-wait` | = `--wait` | 権限の札だけの待ち |
| `--undo-ms` | 3000 | 押した後の取り消しの猶予 (0〜5000) |
| `--allow-host NAME` | — | Host の照合に足す名 (携帯の転送で別の名を使う時・提出版では確かめていない・足した名は DNS rebinding の守りの外になる) |
| `--no-browser` / `--no-log` | — | 頁を開かない / `board/state/log-*.jsonl` を書かない |

頁が「token がありません」と出たら、server の端末に出た URL (`#t=` つき) を開いてください。

頁がどこにも開かれていない時 (最後に見てから 30 秒・起動の時は「見た」と数える) は、板は新しい札を受けません。hook は判断なしで終わり、端末のいつもの確認が出ます (頁を閉じたまま端末が止まって見えないように)。開いていた札も切れます (決めた札は猶予を終えて渡します)。

### 頁の URL の引数

`http://127.0.0.1:8765/?mode=small&lang=ja#t=<token>`

既定はマウス向けです。見つめて押す機能・視線で文章を送る機能・視線の点・スイッチの走査は、すべて切です。OS の視線の道具からクリックを送る人は、そのまま使えます。見つめるだけで押したい時は、設定か `python blemma.py --set dwell=1` で入れます (扇が既に開いている時に別の端末から起こすと、その `--set` は効きません = 扇の窓を閉じてから起こし直すか、設定で替えます)。

| 引数 | 既定 | 意味 |
|---|---|---|
| `dwell` | `0` | 見つめて押す秒 (0.3〜5)。`0` = 切。扇以外の本文の視線送りも、この値が 0 より大きい時だけ |
| `click` | `double` | 扇は 1 回目で選択、同じ羽根を 1.5 秒以内にもう 1 回押すと確定。ダブルクリックでも同じ。`single` = 1 回で確定 |
| `scan` | `off` | スイッチ 1 鍵の走査 (秒ごとに次のボタンへ・0.5〜10)。`?scan` だけなら 1.5 秒 |
| `key` | Space | 走査で選ぶ鍵。`KeyboardEvent.code` か `key` の名のうち `Space`・`Enter`・`NumpadEnter`・`Tab`・`Escape`・`Backspace`・矢印 (`ArrowLeft` など)・`F1`〜`F24`・英数 1 字・`KeyA`〜`KeyZ`・`Digit0`〜`Digit9`・`Numpad0`〜`Numpad9` |
| `lang` | ブラウザの言葉 | `ja` / `en` |
| `sound` | 切 | `on` = 待ちの合図で短い音 |
| `mode` | `large` | `small` = 扇 (`python blemma.py` の既定)・`large` = 大きなボタンの板 |
| `theme` | `auto` | `light`・`dark`・`contrast` (窓の ☀ ☾ でも切り替え) |
| `scale` | `1` | 全体の倍率 (0.75〜2) |
| `font` | `1` | 文字の大きさ。設定では 5 段階 (0.85・1・1.15・1.3・1.5)、URL では 0.8〜2 |
| `face` | `yuji` | 字体: `yuji` = 佑字 粛・`mincho` = 明朝・`gothic` = ゴシック |
| `pos` | `keep` | 窓の位置: そのまま / `br` = 右下 / `bl` = 左下 / `tr` = 右上 / `tl` = 左上。移動はアプリの小窓向け。起動時は右下 |
| `clear` | `off` | `on` = 扇の外の角を窓から切る (Windows・`scale=1` の時だけ)。待機中は題の帯も隠す。対象の窓が無ければ何も変わらない |
| `desc` | `on` | `off` = 選択肢の解説を出さない |
| `trail` | `off` | `on` = 見ている所に点を重ねる (録画用) |

頁の右上の「設定」でも替えられます (設定の釦はキーとクリックで押します = 注視では押せません。替えた値はブラウザの localStorage に残ります。閉じるのは Esc か「閉じる」で、「閉じる」に焦点が在る時は Enter / Space でも閉じます)。優先の順は URL の引数 > 保存した値 > 既定です。`blemma.py` からは `--set 鍵=値` か環境変数 `BLEMMA_OPTS` で渡せます (扇が既に開いている時に別の端末から起こした分は効かず、開いている扇のままです。変える時は、扇の窓を閉じてから設定を付けて起こし直すか、この設定で替えます)。「携帯で開く」は `#t=` つきの URL を大きな字で出します。携帯へは、利用者が用意した転送で 127.0.0.1 へ届けます (例 USB の Android = `adb reverse tcp:8765 tcp:8765`)。この道は提出版では確かめていません。転送の先へ札の本文と token が渡ります。

### 扇と和紙・小窓

- `python blemma.py` は、既定 640×720 の縦長の小窓を右下に開きます。札がある時は上に扇、下の和紙に問いを表示します。横長では左に問い、右に扇。窓の縁をドラッグすると扇・和紙・字が追従し、扇の背景をドラッグすると窓が動きます (表示倍率が 125%・150% などの画面でも、運んだ窓の大きさは変わりません)。
- 羽根は「一〜六」「止」「戻」(英語は `1`〜`6`・`Esc`・`0`)。「戻」はいつもの確認に戻る入口です。朱の印はありません。ポインタを載せた羽根の全文は、内側の押せない帯に出ます。確定後の猶予の間だけ、その帯が「取り消す (n)」のボタンになります。
- Edit の札は、短い差分の「変更」の行を本文の先頭に出し、本文の変わる所に印を付けます。消す所は打ち消し線、足す所は下線です。配色を変えると和紙も追従し、暗い配色では夜の色になります。
- 長い文章は「▼ 続き」で 1 画面ずつ送ります。ポインタを載せて 0.35 秒後に始まり、その後は 1.5 秒ごと。末尾で止まり、載せ直すと先頭へ戻ります。押す操作や ↓ ↑ PageDown PageUp でも送れます。扇の和紙は本文の上にポインタを置いても動きません。「▼ 続き」は `dwell=0` でも使えます。
- 和紙にポインタを載せるとコピーのボタンが現れ、`C` キーでもコピーできます (キーでボタンに移った時も表示)。問いと本文をコピーし、重複する「変更」の行は含めません。
- 小型表示では、札がある間と札が消えてから 1.5 秒間、通知の帯と縁を出しません。
- 「常に手前」は Windows では `POST /window` → `board/window_win.py` の `ctypes` で今のアプリの小窓を固定します。触るのは、窓の名がこの板の物と一致する 1 枚だけです (既定の 8765 以外のポートの板は、窓の名にポート番号が付きます。同じ名の窓が 2 枚以上ある時は、どちらも切りません)。他の OS、対象の窓が見つからない時、固定に失敗した時は、対応ブラウザの Document Picture-in-Picture で画面に収まる大きさの窓を開きます (「固定を外す」が当たらなかった時は、窓を増やしません)。透過 (`clear=on`) は、頁を拡大・縮小している間は切り抜きをやめて四角の窓へ戻します。
- 待機中の扇は横向きに閉じて控え、ポインタを載せると状態の字が出ます。アプリの小窓だけは 320×120 に縮み、札が来ると元の位置と大きさに戻ります (窓の右下の角は動きません。待機の大きさのまま頁を読み直しても、元の大きさは覚えています。札の途中で読み直した時は、今の窓の大きさのままです)。板との切断が 10 秒続くと、アプリの小窓を閉じます。切断と見るのは、板の見張りが続けて 3 回つながらなかった時だけです (送信が 1 回届かなかっただけでは閉じません)。通常のタブでは大きさを変えず、自動では閉じません。

### 入力

| 入力 | 押す | 取り消す (押した後の猶予のうち) |
|---|---|---|
| マウス | 扇は 1 回目で選び、同じ羽根を 1.5 秒以内にもう 1 回押す。`click=single` または大きな板・一覧のボタンなら 1 回 | 「取り消す」を 1 回押す (扇では内側の帯) |
| 視線 | 設定で `dwell` を入れた時だけ、ボタンの上に留まると 1 回で押す。外れても 150 ms のうちに戻れば数え続ける | 「取り消す」に留まる |
| キー | Tab で移って Space / Enter・数字 1〜6 は 1 回で決まる (「次から訊かない」だけは、同じ数字か、焦点の上の同じキー (Space か Enter) を 1.5 秒以内に 2 回)。0 = いつもの確認に戻る・Esc = 止める側のボタン | Backspace / Esc |
| スイッチ 1 鍵 | 設定で `scan` を入れ、光ったボタンで鍵を 1 回押す | 鍵を一度離してから、もう一度押す |
| 携帯 | 大きな板の縦 1 列は 1 回触る。扇の表示はマウスと同じ 2 回 (携帯への転送は利用者が用意) | 「取り消す」を 1 回触る |

札・設問・並びが替わったら、pointer の下のボタンは一度外へ出て入り直すまで数えず、押したままの鍵は離すまで数えません (見続けて 2 回押さない)。板から札が替わった直後の 0.4 秒は、キー・スイッチ・クリックの押しも数えません (前の表示へ向けた遅れた 1 押しが、新しい札に当たらない)。扇の 2 回押しの 1 回目も同じです。取り消しだけは、猶予を 0.8 秒より短くした時 (`--undo-ms`)、猶予の半分から押せます (走査の光もその時から取り消しに当たります)。焦点の上の Enter / Space・クリック・触る・スイッチで札の中の画面を進めた直後 (拒否 → 理由・前の画面へ・次の設問・確かめの画面) も、0.4 秒は押しを数えません (続けて入った 2 打目やダブルクリックが、進んだ先に当たらない)。数字のキーで進めた時は続けて打てます (Esc と 0 も同じ)。数字や注視で進めた直後の 0.4 秒は、焦点の上の Enter / Space・クリック (扇の 2 回押しの 1 回目も)・触る・スイッチだけを数えません (数字の直後の癖の Enter が、まだ見ていない次の画面の先頭を選ばない。取り消しの押しは、この間に巻き込みません)。スイッチの走査は、札が替わった後の 1 こまぶん (0.4〜1.5 秒) 何も光らせません。窓がキーの焦点を得た直後も同じで、走査は 1 こまぶん光らせず、キーとスイッチの押しは 0.4 秒数えません (別の窓へ向けて打ったキーや、焦点を得た瞬間のスイッチが、扇の「許可」に当たらない。クリックと取り消しは数えます)。数字で「次から訊かない」を押した 1 回目は選ぶだけで、同じ数字を 1.5 秒以内にもう 1 回押すと決まります (間に札や画面が替わると選び直し)。窓の大きさや位置が変わった直後 (待機の小窓が札で開く時など) は、0.6 秒のあいだ注視を数えません。ボタンの並ぶ列や頁が送られた直後 (走査の光が窓の外のボタンを見える所へ送った時・ホイール) も同じです (本文や和紙だけが送られた時は、注視を数え続けます)。設定を閉じた直後も、pointer の下のボタンは入り直すまで数えません。

キーの焦点: 配色や設定のボタンをキーで押しても、焦点はそのボタンに残ります (先頭の羽根へ移りません)。焦点がどこにも無い所へ札が出た時と、自分の押しで札に答えた・札の中を進めた時は、新しい画面の先頭へ置きます (前の画面と同じ位置のボタンへは持ち越しません)。焦点をボタンに置いたまま、自分で答える前に札が替わった・押せなくなった時 (時間切れ・接続の終了・ほかの窓からの答えや取り消し) と、焦点を置いた「取り消す」「▼ 続き」や上のボタン (配色・常に手前) を頁が隠した時は、次の札のどこにも置きません (前の札へ向けた Enter が、次の札の「許可」に当たらない)。その札に自分で答えるか、札の中を進めると (数字・クリック・Tab や矢印で焦点を置いてからの Enter)、次からは元どおり先頭に置きます (焦点の無い Enter・0.4 秒の数えない間の内の押し・間に合わなかった取り消しのキーでは戻りません)。「前の画面へ」で戻った時は「拒否 …」へ、取り消して選ぶ画面へ戻った時はどこにも置きません。「常に手前」で別の窓へ移る・戻る時は、キーで使っている時だけ、焦点の在ったボタンへ焦点を戻します (戻せない時と、マウスで移った時は置きません)。

読み上げの「押す」や音声操作のように pointer の無いクリックは、キーと同じ 1 回の押しとして受けます。スイッチの鍵は、Ctrl・Alt・Meta と一緒に押した時は数えません。Windows のコントラスト テーマ (強制の配色) でも、光っている羽根は系の強調色で見えます。

## 手で確かめる (5 分)

1. `python board/server.py` で頁を開く。
2. 別の端末で、hook の代わりに札を 1 枚出す (repo の根で):
   `python -c "import sys; sys.path.insert(0, 'hooks'); import _client; print(_client.ask_detail({'cwd': '/x/demo', 'session_id': 'abcdef'}, 'permission', {'head': 'Bash', 'blocks': [{'label': 'command', 'text': 'ls', 'mono': True}]}))"`
3. 既定の大きな板で「許可 (今回)」を 1 回クリックする → 上の中央に「取り消す (3)」→ 猶予のうちにそのボタンを 1 回押す → 札が戻る。
4. もう一度「許可 (今回)」を押して 3 秒待つ → 端末に `('answered', {'type': 'allow_once'})`。「端末で答える」なら `('released', None)`。設定で扇に切り替えて試す時は、羽根を 2 回押して確定し、内側の帯を 1 回押して取り消す。
5. server を止めた状態で 2. を打つ → すぐ `('no_board', None)` (= hook は何も書かず、Claude Code のいつもの確認へ)。

頁の純粋な計算 (滞留・走査・ボタンの並び・字) は `board/static/board_core.js` に分けてあり、node で読めます:
`node -e "const c = require('./board/static/board_core.js'); console.log(c.suggestionLabel({type: 'addRules', rules: [{toolName: 'Bash', ruleContent: 'git commit:*'}], behavior: 'allow', destination: 'localSettings'}, 'ja'))"`

自動の試験 = `python -m pytest tests -q` (試験だけ pytest が要ります)。11/7 の記録は **664 passed・0 skipped**。実ブラウザの試験も走ります (Chromium と WebSocket を使える node が必要)。ただし、実ブラウザの試験でも `window.moveTo`・`window.resizeTo`・クリップボードは代用品に差し替えています。板との切断から 10 秒後に app の小窓を閉じる処理 (`window.close()`・`display-mode: standalone` の判定) も、試験は数え方 (3 回続けて失敗) までで、閉じる所は通していません (設計 §10.4)。Windows の実窓の固定・透過や Document Picture-in-Picture の開閉まで、この合格数で確認したとはしません。細目は [`docs/design.md` §7.3](../docs/design.md#73-試験と検収)。

---

## In short (EN)

`python board/server.py` starts the board on 127.0.0.1 only (Python 3.10+, standard library only), writes a per-launch token to `board/state/run.json`, and opens the page in your default browser. Ctrl+C stops it; hooks then return no decision and Claude Code shows its normal prompt. If the page says there is no token, open the URL (with `#t=`) printed in the server's terminal. If no page has been open for 30 s (the server start counts as a view), the board refuses new cards and hooks fall back to the terminal's normal prompt; open cards expire, and a card already decided still finishes its grace period.

Page URL: `http://127.0.0.1:8765/?mode=small&lang=en#t=<token>`. Mouse input is the default: dwell, gaze scrolling, trail and scanning are off. For fan choices, click once to select and again on the same blade within 1.5 s to confirm; a double-click also works. `click=single` restores one-click confirmation. The large board, keys, enabled dwell and switches use one action (on "Don't ask again" a number key takes the same number twice within 1.5 s, and Enter / Space on the key focus takes the same key twice). For 0.4 s after the window gets the key focus, keys and the switch are not counted and scanning stays dark for one step. Undo always takes one click (the inner band in the fan). Enable dwell with `dwell=1` or Settings; OS gaze tools that send clicks can keep `dwell=0`.

The app opens at 640×720, with the fan above the question; wide windows place the question on the left. Resize to fit the fan, paper and text, or drag the fan background to move the window. More pages after a 0.35 s hover and then every 1.5 s, or by click/arrow/PageUp/PageDown keys. Hover to reveal Copy, or press C. Settings include `face` (Yuji Syuku/serif/sans serif), five `font` sizes, paper-aware `theme`, four corners (`pos`) and optional Windows-only `clear=on` at `scale=1`. Windows pins the existing app window; other OSes use supported Document Picture-in-Picture. The idle app shrinks to 320×120 with a closed fan, returns to its saved size for a card, and closes after a detected disconnection lasts 10 s. Phones can reach 127.0.0.1 through forwarding you set up yourself (not tested in this version); the card text and token travel to wherever you forward.

Hand check: start the server, then from the repo root run the `_client.ask_detail(...)` one-liner above, click "Allow (this time)" on the default large board, undo within the grace, click again and wait — the terminal prints `('answered', {'type': 'allow_once'})`. Tests: `python -m pytest tests -q`, 664 passed and 0 skipped in the Nov 7 record, including a real-browser test. Window movement/resizing and clipboard writes are substituted there; the app window's auto-close 10 seconds after losing the board (`window.close()`, the `display-mode` check) is tested only up to the counting of three failed polls, not the close itself (design §10.4); native pinning, clipping and real PiP windows still require separate checks.
