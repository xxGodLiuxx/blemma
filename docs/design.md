# BLEMMA 設計 v1.2 (gaze-board・視線の板) — 2026-11-01

> **この文書はハッカソン (Built with Claude: Japan 2026・2026-11-02 12:00 JST 開始) の前に書いた設計のメモです** (v0 = 2026-10-14 → v1 = 10-31 → v1.2 = 11-01)。開始前に書いたのは文書だけで、実装・試験・設定の file は 11/2 12:00 以後に新しく作る (この repo の最初の commit = 文書だけ = tag `pre-event-docs`・以後の履歴に実装が入り、文書の直しも含む)。文書の中の JSON (§2.5・§7.2) は契約の形の例で、動く file ではない。開始後に変えた所はこの file の git の履歴に残る。

> **11/4 の同期** = 本文を 11/4 の実装 (板の server・共通の client・板の頁・hook 4 本・MCP server・起こし方の 1 行) と 11/4 の転換 (§1) に合わせた。食い違いは code を正とし、code の方が良い所は「実装の判断」、code がまだ設計に届かない所は「未対応 (今後)」と書いた。その日の記録 = §15。

> **11/6 の同期** = 扇 (OhGi)・状態を送る 2 本を含む hooks 6 本・設定・実機の検収で直した所を、`c7cf6c9..409703d` の実装差分に合わせた。その後の同日の変更も、現在の `board/static/board.js`・`board_core.js`・`board.css`・`board/window_win.py`・`blemma.py` に合わせて反映した。既定はマウス・扇は 2 回押し・640×720 の縦長で扇の下に和紙。§9 にも視線と走査を使う時の設定を明記した。検収と扇の形の記録 = §16。

> **v1.2 = 2026-11-01** = 規約 (参加者ガイド・10/31 に読んだ) と主催の回答 (11/1) を反映した版。変えた所 = **提出の締切は 11/8 (日) 20:00 JST** → 工程を前倒し (§8・11/7 録り・11/8 15:00 提出)・デモは字幕も日本語・尺 2:50 前後・冒頭 30 秒に 3 点とテーマ (§9)・名乗るテーマ = テーマ 2「本来、誰にでも届くべきものを。」(§1・§6.2)・§11.4 の 6 件を確定に (期間前の設計の文書は主催の回答で repo に入れてよい・公開の形は新しい repo と新しい履歴)。技術の契約 (§2〜§5・§7・§10・§12) は v1.1 のまま。
> **v1.1 = 2026-10-31** (v1 = 同日)。外部のレビュー (別の LLM による反証) 1 巡目 (2026-10-31・MAJOR_REVISION・BLOCKER 0・HIGH 5・MEDIUM 4・LOW 2) の **11 件に対応した = 10 件を本書で閉じ、#11 (公開前の資料の門) は本書の側だけを閉じた** (他の file の直しは公開の門で・対応表 = §14)。
> - v1 = 設計 v0 (2026-10-14・非公開の作業メモ) + v0 → v1 の差分 (2026-10-30・同) + 公式の裏取り (2026-10-30・`docs/research_official_docs.md`) を 1 枚にした物。**code は 2026-11-02 12:00 (JST) から** = この file は文書だけ (code・試験・設定の file はまだ 1 行も無い)。
> - 前提の版 = Claude Code **v2.1.314** (2026-10-30 の最新・裏取り §1.1)。要る版の下限 = **v2.1.287** (§2.5)。hooks の欄名は変わりうる = 書く前に裏取りと https://code.claude.com/docs/en/hooks.md で確かめる。
> - 以後の設計の正本はこの版。初日 (11/2) の確かめの結果は §10 に書き足し、変わった所は本文も直す。

**札の凡例** (裏取りの札に 2 つを足す): 【raw】公式頁の生の文 / 【断片】要約器が返した逐語の断片 / 【報告】GitHub issue などの利用者の報告 / **憶測** = 出典の無い読み (一覧 = §12) / **v1 の判断**・**v1.1 の判断** = 材料に無く、その版で書き手が決めた事 (実装で覆してよい・覆したらこの file を直す)。「裏取り §1.5」は裏取りの file (`docs/research_official_docs.md`) の節、「§2.1」はこの file の節。

### v0 からの変更点 (v1.1 の時点・10)
1. 口を 4 本に: Claude 自身の質問 (`AskUserQuestion`) を `PreToolUse` の `allow` + `updatedInput` で答える (`hooks/ask.py`)。v0 の「外から答える公式の口は無い」は誤り (裏取り §1.6)。
2. 4 つの口の入力・板・出力・時限を契約の表に (§2)。答えが無い時は無出力・exit 0 = 判断を返さず、Claude Code の通常の判断の流れに委ねる。
3. 権限の釦を整理: 許可 (今回)・次から訊かない (対象と保存期間つき)・拒否・作業を止める・端末で答える。板が答えるのは**選択式の問い**だけ (自由記述と入力の直しは端末へ)。
4. 全部の札の同じ位置に 1 つの釦。字と意味は口ごと (作業を止める / この質問に答えない / この問い合わせを閉じる)。取り消し 3 秒は hook へ返す前に server が持ち、1 鍵のスイッチでも取り消せる。
5. 札ごとに一意の ID と終わりの確定 (答えた・端末へ・期限・接続の終了・照合の終了を排他で 1 つ)。期限は表示から数え、作成からの上限で抑える。板から返るのは番号だけで、公式の JSON は hook が組む (§3)。
6. 携帯は 127.0.0.1 を広げず、利用者の転送で届ける。BLEMMA が保証する通信の範囲を限って書いた (§3.8・§4.4)。
7. 同梱の MCP server の名を `blemma` に (道具 = `mcp__blemma__ask_board`)・版は 2025-11-25 で話す・選択肢は enum の `oneOf` + `title`・雛形の許可に 1 行 (§2.5・§7.2)。
8. 板に出さない物: 計画の承認 (`ExitPlanMode`)・plan mode の権限・URL mode の問い・描けない schema・利用者が挙げた端末専用の道具。
9. 提出版は command 型に固定。http 型の比べ・ExitPlanMode の調べ・余りの機能は提出版の外へ (§5.6)。初日は最小の 3 経路と退化を確かめて、不成立の時に削る物を決める (§10)。11/5 に完成版の異常の経路を実機で検収する。
10. デモ: AskUserQuestion の場面 10 秒・スイッチと携帯の実の操作を入れた。名乗りは JaH だけ・画面は板と端末だけ・冒頭の 1 行は起動の引数・退化は別の撮り (§9)。

---

## 1. なぜ作るか — 一言と線 3 本

**一言**: Claude Code が人に訊く瞬間 (権限の確認・MCP の問い・Claude 自身の質問) と、エージェントが先回りで用意した「次の一手」を、**扇か大きな釦の板**に出す OSS。既定はマウス向けで、扇の羽根を 1 回押して選び、同じ羽根を 1.5 秒以内にもう 1 回押すと決まる (ダブルクリックも同じ)。`click=single` なら 1 回に戻せる。キー・有効にした視線・スイッチは 1 回で決まる。

作り手は視線で PC を使い、OS の視線の道具からクリックを送る。見つめて押す・視線で本文を送る・視線の点・走査はすべて既定で切。見つめるだけで押したい人は設定か `--set dwell=1` で入れられる (§4.2)。

**なぜ**: Claude Code は仕事の途中で何度も人に訊く。どれも端末の小さな dialog に出て、矢印キーと Enter で答える形 = 視線・スイッチ・片手では狙いにくく、結局は打鍵が要る。公式の accessibility は screen reader・拡大鏡・動きの低減・色覚の theme・ベルまでで、視線とスイッチに触れる文は無い (裏取り §3.5【raw】 https://code.claude.com/docs/en/accessibility.md)。BLEMMA は訊く瞬間だけを横取りして別の頁 (板) に出し、答えを公式の仕組みで Claude Code に戻す。

**線 3 本** (動かさない):
1. **公式の口だけに乗る** = settings の hooks (`PermissionRequest`・`PreToolUse`・`Elicitation`・`Notification`・状態だけを送る `UserPromptSubmit`・`Stop`) と MCP の elicitation。Claude Code 本体の fork・patch・端末への打鍵の注入はしない。
2. **板が無ければ退化** = 板が居ない・時限を過ぎた・壊れた時、BLEMMA は判断を返さず (無出力・exit 0)、Claude Code の通常の判断の流れに委ねる。対話の環境で他の決定 (規則・他の hook・mode) が無ければ、いつもの確認が出る (§5.1・§5.3)。
3. **勝手に許可しない** = 人が板で選んだ時だけ allow を返す。時限・不明・誤り = 判断なし (allow でも deny でもない)。

**範囲**: 板が答えるのは**選択式の問い** (選ぶだけで答えが決まる物)。自由記述と入力の直しは端末へ戻す = 視線の利用者にとっては機能の縮小 (打鍵が要る)。縮小を小さくする道は §4.3。

**名乗るテーマ** (v1.2・作り手の決め 10/31): 公募のテーマ 2「本来、誰にでも届くべきものを。」= 壁を取り払って、届いていない人の手に。BLEMMA が取り払う壁 = **操作の壁** (端末の小さな dialog と打鍵。公募の例に挙がる専門知識・費用・言語・手続きには無い壁 = 自分の言葉で名指しする)。壁の外側の具体的なひとり = 視線だけで打つ作り手本人。同じ板が携帯・片手・スイッチの人にも届く。概要・README・動画の冒頭でこの順に言う (§9)。

**11/4 の転換** (作り手の決め・外部のレビュー (別の LLM による反証) を受けた): 板の既定の前面を、同じ板の頁の**小型**の見え方にする。
- 位置・大きさ・字・配色は設定で替え、釦を大きくする切り替えも同じ頁の中 (別の画面は作らない)。起こし方は 1 コマンド (`python blemma.py`・§3.2) = Chrome / Edge の app モードの小窓で開く。現在の「常に手前」は Windows では今の小窓をそのまま固定し、他の OS では対応ブラウザの Document Picture-in-Picture を使う (§4.4)。
- 携帯の場面と転送は提出版の外 (§4.4)。携帯から答えたい人には、公式の Remote Control が使える環境ならそちらを案内する。
- 語りの順は変えない = 視線で使う作り手の壁 → 端末から目を離して働く机の全員へ。
- 理由 = 外部のレビュー (別の LLM による反証) の所見: 「誰でも使う小窓」への全面の転換は、実在するひとりの壁を、規模の分からない一般の不便に置き換えて危うい (同じ板を小窓でも使う形には条件つきで賛成)。OS 固有の「常に手前・焦点を奪わない」窓は、標準ライブラリだけでは 3 つの OS で保証できない = 専用の窓は作らず、ブラウザの頁を共用する。焦点を奪わない窓にはキーが届かない = スイッチのキーで選ぶには板に焦点が要る (見えていれば走査と滞留は進む・§4.2)。
- **11/6 の現在の実装** = 小型の見え方は **扇 (OhGi)** (`?mode=small`)。app モードの既定は **640×720 の縦長** (上に扇・下に問いの和紙)・画面の右下。待機中は小さくなり、扇は横向きに閉じて控える。札が来たら元の大きさに戻る (待機の大きさの窓の時 = 待機中に 40px より広げた窓はその寸法で開く・§5.7)。横長の窓では左に問い・右に扇。折り扇と一覧の使い分け (§4.1)・頁の設定 (§4.2)・最前面と透過 (§4.4) が同じ頁で動く。

---

## 2. 4 つの口と先回りの 1 本 — 契約

**登録する hooks は 6 本** (11/6): 下の 4 つの口に、`UserPromptSubmit` と `Stop` を足す。後の 2 本は同じ `hooks/state.py` を使い、session の頭 6 字と状態だけを `POST /state` へ 1 回送る (`UserPromptSubmit` = `working`・`Stop` = `done`)。通信の総期限は 250 ms・settings の `timeout` は 5 秒。札も判断も作らず、無出力・exit 0 (共通の失敗時の扱いは §2.0)。この 2 本に matcher と `statusMessage` は付けない (§7.2)。

### 2.0 4 本に共通の決まり

- 形: settings の `hooks` = イベント → matcher の組 → hook の定義 (`type: "command"`・exec 形 = `command` + `args`・`timeout`・`statusMessage`)。exec 形は "No shell tokenization happens on any platform." (裏取り §1.3【断片】 https://code.claude.com/docs/en/hooks.md)。
- matcher: 英字・数字・`_`・`-`・空白・`,`・`|` だけの matcher は完全一致の一覧、それ以外の字を含む matcher は "JavaScript regular expression, unanchored" (裏取り §1.3【断片】) = **全部に当てる時は `.*` と明示する** (省略に頼らない)。
- 共通の入力欄 (stdin の JSON): `session_id`・`prompt_id`・`transcript_path`・`cwd`・`scratchpad_dir`・`permission_mode`・`effort`・`hook_event_name`、subagent の中だけ `agent_id`・`agent_type` (裏取り §1.4【断片】)。板は `cwd` の末尾の名・`session_id` の頭 6 字・`agent_type` で札の「出どころ」を見せる (v1 の判断)。
  - 実機で確かめた形 (§10.3 の発見 5・v2.1.318): `effort` は object (`{"level": …}`)・`scratchpad_dir` は対話でだけ来る・`prompt_id` は turn の id。**Elicitation の stdin には subagent の中からでも `agent_id`・`agent_type` が来ない** = 札の「出どころ」に `agent_type` が出るのは権限の口だけ (質問の口は subagent の中では起きない・§2.2)。
- 公式の出力の決まり: "Exit 0 means success, and is the intended exit code when you print JSON for structured control." / "Print nothing but the JSON object to stdout." (裏取り §1.4【断片】)。
- **BLEMMA の hook の約束** (v1.1 の判断):
  - 判断を返す時は stdout に JSON 1 個だけ・exit 0。返さない時 (板が居ない・時限・端末で答える・板で描けない形・例外) は何も書かず exit 0 = Claude Code の通常の判断の流れへ。stderr も既定は空 (`BLEMMA_DEBUG=1` の時だけ 1 行ずつ書く・UTF-8 の bytes と LF = 日本語の Windows でも、Claude Code の debug の記録で化けない)。
  - 板との通信の失敗 (`board/state/run.json` が無い・接続を断られた・時間切れ・壊れた返り) を「無出力・exit 0」に変えるのは**共通の client (`hooks/_client.py`) の責務**。stdin が UTF-8 で解けない・JSON でない時も無出力。
  - Claude Code が settings の `timeout` で hook を止めた時は **exit 0 の保証の外** (公式 = 出力を捨てて判断なし・裏取り §1.9)。
  - exit 2 は使わない。exit 2 の意味は口ごとに違う = PermissionRequest は無効 ("Exit code 2 isn't honored for this event")・Elicitation は「断る + dialog も出ない」・PreToolUse は「道具を止める」(裏取り §1.4 の表)。
  - JSON は `json.dumps(…, ensure_ascii=True)` で書く (Windows の stdout が cp932 でも壊れない)。stdin は bytes で読んで UTF-8 で解く。
  - 雛形に `onFailure` を書かない (既定 `"continue"`。`"block"` にすると板の不調と時限で道具が止まる・v2.1.295 以降の欄・裏取り §1.3)。
  - 公式の JSON を組むのは hook だけ。板の頁と server は「口の種」と「選んだ番号」しか知らない (§3.3)。
  - 待つ秒・期限・取り消しの猶予の数は §3.4 の 1 か所で決める。
- **待っている間の端末の見え方** (口で違う・確かめ = §10.1・**11/4 に実機で確定** = §10.3 の 1〜3・v2.1.318):

| 口 | hook が待つ間の端末 | 出典 |
|---|---|---|
| PermissionRequest (Edit・Bash・PermissionRequest に来た AskUserQuestion) | 端末の dialog も同時に出る (答えの種で結末が分かれる・§3.7)。`statusMessage` は画面に出ない (dialog が前に出る・80×24 の端末で) | 実機 (§10.3 の 1)。【報告】#103115 (AskUserQuestion についての報告・裏取り §1.7) と同じ |
| PermissionRequest (MCP の道具) | 測っていない (上と同じ見込み = 推測) | — |
| PreToolUse (AskUserQuestion) | 質問の dialog は出ない。spinner の行に `statusMessage` が出る | 実機 (§10.3 の 2)。v1.2 までの憶測を確定した |
| Elicitation | form は出ない (hook が終わってから描く)。「Calling blemma…」と spinner の行の `statusMessage` だけ | 実機 (§10.3 の 3)。【報告】#103115 "Claude Code awaits every Elicitation hook before it draws the form" |

  = ask.py と elicitation.py が待つ間は**板が唯一の窓**で、端末は spinner の行のほかは固まって見える。対処 = ①hook の定義の `statusMessage` (共通欄・裏取り §1.3) に「BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board」を入れて spinner の行に出す (§7.2) ②板の全部の札に「端末で答える」(§4.3) を置く ③頁がどこにも開いていない時は板が札を受けない (見る人の判定・§3.4 = hook は判断なしで端末へ = 頁を閉じたまま端末が止まって見えない・11/4 の実装)。

### 2.1 権限の確認 = `PermissionRequest` (`hooks/permission.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "When a tool call needs a permission decision" / "Runs when Claude Code is about to ask you for permission to use a tool." (裏取り §1.2・§1.5【断片】)。hook が `allow` を返すと "Claude Code answers the request on your behalf" (hooks-guide【raw】) |
| matcher | `.*` (= 全部の道具)。人が押した時だけ allow を返すので全部でも安全。公式の注意 "Matching on `.*` or leaving the matcher empty would auto-approve every tool permission prompt" (【raw】・裏取り §1.5) は無条件に allow を返す hook の話。除く物は script の側 (下の「板に出さない物」) |
| 公式の入力 (stdin の鍵) | 共通欄 + `tool_name`・`tool_input` (PreToolUse と同じ形・`tool_use_id` は無い)・MCP の道具なら `mcp_server`・任意で `permission_suggestions` (許可の更新の配列) |
| 板に出す物 | 頭 = 道具の種と出どころ。本文 = 何をしようとしているか (下)。釦 = **許可 (今回)**・**次から訊かない** (`permission_suggestions` が在る時だけ・対象と保存期間つき)・**拒否** (理由を定型 3 つから)・**作業を止める** (固定の位置・§4.3)・**端末で答える** (見え方と寸法は §4.1) |
| 返す出力 (stdout) | 下の JSON。exit は全部 0。端末で答える・時限・板なし・板に出さない物 = 無出力 |
| 時限と退化 | 板の期限 (§3.4)・板へ繋がらない (client が無出力に変える) → 無出力。"A hook that exits 2 without a `decision` object leaves the permission flow unchanged" (裏取り §1.5【断片】)・Claude Code の timeout = 出力を捨てる (裏取り §1.9)。どれも Claude Code の通常の流れへ (対話で他の決定が無ければ端末の dialog) |
| 出典 | https://code.claude.com/docs/en/hooks.md (PermissionRequest 節)・https://code.claude.com/docs/en/hooks-guide.md・裏取り §1.5 |

本文の出し方 (v1 の判断):
- Bash = `command` を**省かず全部** (尾に危ない物を隠させない・長ければ札の中で巻物にする) + `description`。
- Edit = `file_path` と `old_string` → `new_string` (長ければ折りたたむ)。Write = `file_path` と頭の 40 行。
- MCP の道具 = `mcp__<server>__<tool>` と入力の JSON (2,000 字まで・超えたら「続きは端末で」)。他の道具 = 入力の JSON (2,000 字まで・超えたら「続きは端末で」)。
- 実装で決めた事 (11/4): `command` を持つ道具 (Bash・PowerShell など) は Bash と同じ扱い (組み込みの道具だけ・MCP の道具は §2.1 の MCP の規則が先に当たる = 要約なしで 2,000 字に切る・§5.7)・`command` の外の入力 (timeout・sandbox の旗など) も隠さず JSON で添える (2,000 字まで)。1 行の要約 (file 名・url・Bash の description) は 300 字まで (切ったら「…」)。Edit の old / new と Write の頭は 6,000 字まで (切ったら見出しに「先頭 n 字・全 m 字・続きは端末で」)。見えない字 (制御・書字方向など) は `⟨U+XXXX⟩` にして見せる (表示だけ・返す JSON は変えない)。札の payload が 256 KiB を超えたら、command を切らずに札を出さない (無出力 = 端末へ)。

返す JSON:
```json
{ "hookSpecificOutput": { "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" } } }
```
- **欄の契約は裏取りの定義で確定** = `decision` の中に `behavior` (`allow` / `deny`)。allow だけ `updatedInput` と `updatedPermissions` (配列)、deny だけ任意の `message` ("tells Claude why the permission was denied") と `interrupt` ("if `true`, stops Claude") (裏取り §1.5【断片】)。公式頁に無いのは deny の**完成した例**だけで、契約は分かっている。`updatedPermissions` の 1 件の例 = `{"type":"setMode","mode":"acceptEdits","destination":"session"}` (hooks-guide【raw】・裏取り §1.5)。
- 許可 (今回) = 上の通り。
- 次から訊かない = 同じ allow に `"updatedPermissions": [ <選んだ suggestion を入力から逐語で写す> ]`。
- 拒否 = `"decision": { "behavior": "deny", "message": "<定型の理由>", "interrupt": false }` (Claude は理由を見て別の道を探す)。定型 3 つ = 「別のやり方でお願いします」「いまは要りません」「先に説明してください」(v1 の判断・頁の言葉に合わせて英語も)。実装の `message` = `BLEMMA: the user denied this on the board: <日本語> / <英語>` (hook の定型の表から組む・板の文字は使わない)。
- 作業を止める = `"decision": { "behavior": "deny", "message": "BLEMMA: the user stopped the work", "interrupt": true }` (Claude を止める = 作業全体を止められるのはこの口だけ・§5.4)。実機では Claude に渡るのは `message` でなく定型の「STOP …」の文 (§10.3)。

「次から訊かない」の字 (v1.1 の判断・保存先の種 = 裏取り §1.5【断片】):
- 規則を足す suggestion (`addRules`) = 「次から訊かない: Bash(git commit …) — <保存期間>」。保存期間の字 = `session`「このセッションの間」/ `localSettings`「この project・この機械で恒久」/ `projectSettings`「この project の共有の設定で恒久 (commit されうる)」/ `userSettings`「全部の project で恒久」。
- モードを替える suggestion (`setMode`) = 別の字「モードを替える: 編集を訊かない (acceptEdits) — このセッションの間」(規則を 1 つ足す釦と同じ字にしない)。**`bypassPermissions`・`auto` へ移す物は釦にしない** (一押しで以後の確認が全部消える物・分類器に任される物は板で出さない)。
- `replaceRules`・`removeRules`・`addDirectories`・`removeDirectories` = 中身を逐語で出す (例「このフォルダも許す: <路>」)。複数あれば 2 件まで (3 件目からは端末で)。
- #91216【報告】= suggestion が端末の行と一致しない事がある → 板は suggestion の中身そのものを見せ、それをそのまま写す。
- 板に出す列は hook が絞る (11/4) = 公式の 6 種だけ・`bypassPermissions`・`auto` へ移す物を除き・先頭から 2 件。板の答えの番号はこの列で引き、その要素を `updatedPermissions` へ逐語で写す。

**板に出さない物** (script が無出力で返す・v1.1 の判断):
- `tool_name` が `ExitPlanMode` = allow が効かない回帰が open で 3 件 (§5.5)。計画の承認は端末で。
- `tool_name` が `AskUserQuestion` = 質問の口を PreToolUse で答える間 (§2.2 の排他)。PreToolUse が決めない (無出力の) 時は PermissionRequest も `AskUserQuestion` で呼ばれる = この除外は要る (§10.3 で確定)。
- `permission_mode` が `plan` = plan mode では ExitPlanMode 以外の編集に hook の allow が効かない (permissions.md "Hook approvals in plan mode"【raw】・裏取り §1.6)。
- 除外の表 = 上の定数 + 環境変数 `BLEMMA_TERMINAL_ONLY` (カンマ区切りの道具の名)。利用者が端末で答えたい道具 (下の `requiresUserInteraction` の道具など) をここに書く。

限界 (README に書く): `_meta["anthropic/requiresUserInteraction"]` を付けた MCP の道具は、hook の allow で確認を飛ばせない ("a hook can't skip its approval prompt with "allow", with or without `updatedInput`"・裏取り §1.6 = 確定)。板が入力からそれを見分ける方法は引用に無い = 板は allow を渡した後も「許可されました」と書かず、「板の答えを Claude Code へ渡しました (端末の確認が続くことがあります)」と書く (§3.5)。分かっている道具は除外の表へ。
- 「入力を直して許可」(`updatedInput`) は提出版の外。拡張先として残す = 元の入力と直した差分を見て、定型の候補から選ぶ形 (§5.6)。
- 非対話の `claude -p` では「どの hook も決めない呼び出しは拒否」(hooks-guide【raw】) = BLEMMA は対話の `claude` 向け。

### 2.2 Claude 自身の質問 = `PreToolUse` (matcher `AskUserQuestion`) (`hooks/ask.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "Before a tool call executes. Can block it" (裏取り §1.2)。`AskUserQuestion` と `ExitPlanMode` は "require user interaction"。hook の手順 = 入力を stdin から読む → "Collects the answer through your own UI" → `allow` と答えを入れた `updatedInput` を返す。**"Returning "allow" alone is not sufficient for these tools."** (裏取り §1.6【断片】) |
| matcher | `AskUserQuestion` (英字だけ = 完全一致・裏取り §1.3) |
| 公式の入力 (stdin の鍵) | 共通欄 + `tool_name` (= `AskUserQuestion`)・`tool_use_id`・`tool_input.questions` = 1〜4 問、各問 = `question`・`header` (12 字まで)・`options` (2〜4 個・各 `label` と `description`)・`multiSelect` (数の上限 = Agent SDK の user-input 頁【raw】) |
| 板に出す物 | 1 問 = 1 画面。頭 = `header`、本文 = `question`、釦 = 各 `label` と補いの `description` (見え方と寸法は §4.1)。**押す数** = 1 問の単一選択は確定操作の後に送る (扇のクリックは既定 2 回・キーなどは 1 回・§4.2。取り消しの猶予が見直しの代わり)・複数の問いと `multiSelect` は最後に「送る」の 1 押しを足す (確かめの 1 画面)。固定の位置 = **この質問に答えない**。端末の Other に当たる「ほかの答え」は板では書かず端末で答える。端末で答える釦も置く 見えない字 (書字方向・幅ゼロなど) は頁が `⟨U+XXXX⟩` にして見せる (表示だけ・返す answers / content は逐語・11/7 夜の 1 巡目 #23)。 |
| 返す出力 (stdout) | 下の JSON。この質問に答えない = deny。端末で答える・時限・板なし = 無出力。exit は全部 0 |
| 時限と退化 | PreToolUse の hook の timeout = "doesn't block the tool call" / "The call continues through the normal permission flow" (裏取り §1.9【断片】) = 端末に AskUserQuestion の dialog が出る。無出力 (板の期限・板へ繋がらない・端末で答える) も同じ |
| 出典 | https://code.claude.com/docs/en/hooks.md (PreToolUse 節)・https://code.claude.com/docs/en/agent-sdk/user-input.md・https://code.claude.com/docs/en/permissions.md・裏取り §1.6 |

返す JSON (公式の答えの形・裏取り §1.6):
```json
{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "allow",
    "updatedInput": {
      "questions": [ { "question": "Which framework?", "header": "Framework",
        "options": [ {"label":"React","description":"Component library"}, {"label":"Vue","description":"Progressive framework"} ],
        "multiSelect": false } ],
      "answers": { "Which framework?": "React" } } } }
```
- `updatedInput` = 元の `tool_input` を丸ごと写して `answers` を足す (v1 の判断)。`answers` は "Maps question text to the selected option label." = 鍵は `question` の文そのまま (hook が自分の stdin の写しから組む・板からは番号だけ・§3.3)。
- `multiSelect` = label を ", " でつないだ 1 本の文 (SDK の頁は「label の配列か ", " 区切り」【raw】)。実機では配列も通ったが、Claude にはどちらも ", " で繋いだ文に見える = label にカンマがあると区切りが曖昧 (§10.3)。実装は文の形。
- この質問に答えない = `"permissionDecision": "deny"` + `"permissionDecisionReason": "BLEMMA: the user did not answer this question"` (欄名は実機で効いた = Claude に「PreToolUse:AskUserQuestion hook error: <理由>」で届き、作業は続く・§10.3)。deny の意味は「この道具の呼び出しを断る」= **作業全体の停止ではない** (Claude は続けうる・§5.4)。
- 板で描けない形 (11/4) = 問いの文が重なる (`answers` の鍵がぶつかる)・問いの数 1〜4 / 選択肢の数 2〜4 の外・`label` が空か文でない → 無出力で端末へ。
- `permissionDecision` の 4 値 = `allow`・`deny`・`ask`・`defer` (`defer` は `-p` だけ)。複数の hook が食い違えば deny > defer > ask > allow (裏取り §1.6・SDK【raw】)。hook の `allow` は deny / ask の規則を超えない (permissions.md【raw】)。

**経路の排他** (v1.1 の判断): 提出版の主 = PreToolUse。その間 permission.py は `AskUserQuestion` を除く。初日に PreToolUse で答えられず、PermissionRequest の allow + `updatedInput` で答えられた時は、PreToolUse の登録を外すのと同時に permission.py の除外も外し、PermissionRequest の側で答える (両方に同時に登録しない = 札が二重にならない)。両方とも答えられなければ ask.py を外す (§10.2)。

板に出ない場面: subagent の中では `AskUserQuestion` 自体が使えない ("`AskUserQuestion` is not currently available in subagents spawned via the Agent tool"【raw】・裏取り §1.6) = subagent からの問いは ask_board (§2.5)。`ExitPlanMode` も PreToolUse の allow + `updatedInput` で答える形だが、提出版は matcher に入れない (§5.5)。

### 2.3 MCP の問い = `Elicitation` (`hooks/elicitation.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "Runs when an MCP server requests user input mid-task. By default, Claude Code shows an interactive dialog for the user to respond. Hooks can intercept this request and respond programmatically, skipping the dialog entirely." (裏取り §1.7【raw】) |
| matcher | `.*` (= 全部の MCP server)。matcher の対象は MCP server の名 (裏取り §1.3)・`.*` は正規表現の規則で全部に当たる (§2.0) |
| 公式の入力 (stdin の鍵) | 共通欄 + `mcp_server_name`・`message`・任意で `mode` (`form` / `url`)・`url`・`elicitation_id`・`requested_schema` |
| 板に出す物 | 頭 = **問うている server の名** (MCP の MUST "Provide UI that makes it clear which server is requesting information"・裏取り §2.2【raw】)、本文 = `message`、欄 = 下の表。**押す数** = 1 欄の単一選択 (enum・`oneOf`・boolean) は確定操作の後に送る (扇のクリックは既定 2 回・キーなどは 1 回・§4.2。取り消しの猶予が MCP の MUST "allow users to review and modify their responses before sending" の見直しの代わり・v1.1 の判断)・2 欄以上と複数選択は確かめの 1 画面と「送る」の 1 押し。釦 = **断る** (decline)・**この問い合わせを閉じる** (cancel・固定の位置)・端末で答える (見え方と寸法は §4.1) 見えない字 (書字方向・幅ゼロなど) は頁が `⟨U+XXXX⟩` にして見せる (表示だけ・返す answers / content は逐語・11/7 夜の 1 巡目 #23)。 |
| 返す出力 (stdout) | 送る = 下の JSON・断る = `"action": "decline"`・この問い合わせを閉じる = `"action": "cancel"`・端末で答える・時限・板なし・板で描けない形・url mode = 無出力。exit は全部 0 |
| 時限と退化 | 「利用者に任せる = 出力なしで exit 0 → dialog での利用者の答え」(裏取り §1.7【raw】の表)。板の期限・板へ繋がらない → 無出力 → 端末に form が出る |
| 出典 | https://code.claude.com/docs/en/hooks.md (Elicitation 節)・https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation.md・裏取り §1.7・§2 |

返す JSON (`content` の鍵は `requested_schema.properties` の名・裏取り §1.7【raw】):
```json
{ "hookSpecificOutput": { "hookEventName": "Elicitation",
    "action": "accept", "content": { "choice": "2" } } }
```
- `hookEventName` は**必須** (省くと検証で出力ごと捨てられ、`-p` では cancel になる・§10.3)。

欄 (`requested_schema.properties`) の描き方 (MCP の form は "flat objects with primitive properties only"・裏取り §2.2【raw】・v1 の判断):

欄の題は `title`、無ければ `description`、どちらも無ければ欄の名。**`title` と `description` の両方がある欄は、説明も札に載せる** (選ぶ画面では問いの上に、2 欄以上の時は送る前の確かめにも出す)。題が「Confirm」だけの問いで、何を確かめるのか (消す対象・元に戻せるか) が説明にしか無い事があるため。

| 欄の形 | 板 |
|---|---|
| `enum`、または `oneOf` の [{`const`,`title`}] (単一選択) | 選択肢ごとに釦 (字は `title`、無ければ値)。実装 (11/4) は `anyOf` の [{`const`,`title`}] と、旧い `enumNames` (在れば釦の字) も読む |
| `type: array` + `items` の `enum` / `oneOf` / `anyOf` (複数選択) | 印の付く釦 + 「送る」(`minItems` が 2 以上・`maxItems` が選択肢の数より少ない欄は板で守れない = 描けない欄) |
| `boolean` | 2 釦 (はい / いいえ・欄の `title` を問いに) |
| `integer` / `number` で `minimum`〜`maximum` が 10 個以内 | 数の釦 (**提出版の外** = 描けない欄の扱い・11/4 の実装も作っていない) |
| `string` (enum なし)・幅の広い数 | `default` が在れば「既定の値で: <値>」の釦 1 つ (候補の釦)、無ければ「端末で答える」だけ (板で文字は書かない) (**提出版の外** = 描けない欄の扱い・既定の値の釦も 11/4 の実装は作っていない) |
| ask_board の「ほかの答え」(const `"other"` + 任意の書く欄 `other_text`・§2.5) | 「ほかの答え」は端末で答える釦 (押すと無出力)・`other_text` は板に出さない |
| 上のどれでもない・欄が 7 つ以上 | 札を出さず無出力 (端末へ) |

- 描けない欄 (11/4 の実装): 必須 (`required`) なら札ごと無出力で端末へ・任意でも既定の値 (`default`) が在る欄は、札ごと端末へ (端末の form ならその値ごと送られるのに、板で答えると欄が抜けて結果が変わる・11/6)。既定の値の無い任意の欄は、板では空のまま (`content` に入れない・書きたい時は「端末で答える」)。空のままにした任意の欄の題は、札の `omitted` (文字列の列・8 個まで・各 80 字まで) に載せ、頁は和紙に「ここに出せない任意の欄が n 個あります (題)。書く時は「端末で答える」」と出す (11/6 = 前は欄があること自体が人に見えないまま、accept がその欄なしで返っていた)。ask_board の書く欄 `other_text` は「ほかの答え」の釦と対なので載せない。1 欄の選択肢が 13 個以上も描けない欄。欄の数は `properties` の数で数える。
- **欄の必須と、送れる最小の選択の数は別** (11/4 の実装・外部のレビュー (別の LLM による反証) の MEDIUM を受けて分けた): 必須の単一選択と `boolean` = 1 つ選ぶまで先へ進めない・必須の複数選択 = `minItems` が 0 なら印 0 個でも送れて値は `[]`、`minItems` が無いか 1 なら 1 個以上・任意の欄 = 頁に「空のまま」の釦が出て、空のまま送った欄は `content` に入れない (任意の欄はどの形でも空なら入れない = 上の描けない欄と同じ扱い)。
- **描けない形の一覧** (11/4 の実装・どれも無出力 = Claude Code の既定の form へ):

| 形 | 扱い |
|---|---|
| 欄が 7 つ以上 (`properties` の数)・描ける欄が 0・`requested_schema` の `type` が `object` でない | 札ごと端末へ |
| `mode` が `form` でない (無ければ form と見る)・stdin に `url` がある (URL mode・下) | 札ごと端末へ |
| `mcp_server_name` が無い (誰が訊いているか出せない = MCP の MUST を守れない) | 札ごと端末へ |
| 札の payload が 256 KiB を超える | 札ごと端末へ |
| 複数選択の `minItems` が 2 以上・`maxItems` が選択肢の数より少ない (板で数の縛りを守れない) | 描けない欄 (必須なら札ごと・任意なら空のまま) |
| 1 欄の選択肢が 13 個以上 (釦は 1 欄 12 個まで) | 描けない欄 |
| enum の無い `string`・`integer` / `number` (文字と数の入力・上の表の提出版の外) | 描けない欄 |

- `default` は釦に印を付けるだけで、押すまで送らない。`required` の欄が埋まるまで「送る」を出さない。
- `mode` が `url` = 板では答えない (`accept` を返すと dialog が出ず URL は開かない・裏取り §1.7【raw】) → 無出力で端末へ。Notification の `elicitation_url_dialog` で板は光るだけ (§2.4)。
- この問い合わせを閉じる (`cancel`) は、問うた server に「閉じた」を返すだけ = server と Claude は続けうる。Elicitation の hook からは作業を止められない ("Claude Code discards `reason`, `systemMessage`, and `continue` from an Elicitation hook's JSON output, whichever `action` you return."【raw】・§5.4)。

公式の細目 (裏取り §1.7【raw】):
- 端末の dialog では Decline の選択 = `decline`、`Esc` = `cancel`。
- "When an Elicitation hook answers a request, Claude Code sends that answer to the server without running ElicitationResult hooks."
- 版の下限: v2.1.105〜v2.1.284 の間は Elicitation のトップの `decision` が無視された (v2.1.284 で修正)。BLEMMA は `decision` を使わないが、下限は §2.5 の v2.1.287 に揃える。
- 動きの確かめ: `claude --debug` のログに `Elicitation resolved by hook: {"action":"accept","content":{...}}`。
- 機密: MCP の仕様は form で機密 (パスワード・API key・決済) を求めてはならない (裏取り §2.2)。板はどの値も記録しない (§3.8)。

### 2.4 待ちの合図 = `Notification` (`hooks/notify.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "When Claude Code sends a notification" (裏取り §1.2)。"Notification hooks can't block or modify notifications." (裏取り §1.8【断片】) |
| matcher | 型の名の完全一致の一覧 (下) |
| 公式の入力 (stdin の鍵) | 共通欄 + `message`・任意で `title`・`notification_type` |
| 板に出す物 | 板の縁を光らせ、上の帯に `message` を 10 秒 (音は設定で入 / 切)。札が出ていれば札を点滅。扇の窓 (`mode=small`) では札そのものが知らせなので、札がある間と消えてから 1.5 秒間は縁も帯も点滅も出さない (`permission_prompt` は札の約 6 秒後に来る = 帯が割り込むと見つめている羽根がずれる)。札が無い時だけ通知の帯と縁を表示の対象にする (閉じた扇の待機表示では帯は隠す)。`idle_prompt` = 「Claude が次の指示を待っています (端末へ)」。`elicitation_url_dialog` = 「端末でリンクを開くか決めてください」。決める釦は出さない (観察だけ) |
| 返す出力 (stdout) | 何も書かない・exit 0 ("Exit code and stderr are ignored"・裏取り §1.4) |
| 時限と退化 | settings の `timeout` 10 秒・板へは 1 回 POST して待たない (v1 の判断)。通信の全体の期限 = **2 秒** (11/4 の実装・繋ぐ所から受け終えるまでの総期限・数は `hooks/notify.py` の 1 か所 = 共通の client の既定の 1 秒をここで上書き)・転送 (3xx) は追わない。`python -I` で起こされても自分の dir を `sys.path` の頭に足して `_client` を読む。板が居ない・通信の失敗・壊れた入力・例外・それでも `_client` を読めない置き方でも、何も返さず exit 0 (他の 3 本と同じ守り) |
| 出典 | https://code.claude.com/docs/en/hooks.md (Notification 節)・https://code.claude.com/docs/en/hooks-guide.md・裏取り §1.8 |

- matcher = `permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input` (英字・`_`・`|` だけ = `|` 区切りの完全一致の一覧・裏取り §1.3)。型の全部 = 裏取り §1.8。notify.py も `notification_type` を見て、この 5 つの外は送らない (11/4 の実装)。
- 主経路にしない理由: `permission_prompt` は "Expect `permission_prompt` once you haven't typed for about six seconds." (約 6 秒)、`idle_prompt` は応答の後 約 60 秒 (裏取り §1.8) = 板の札は PermissionRequest / PreToolUse / Elicitation で先に出ている。Notification は光と音の役。

### 2.5 先回りの 1 本 = 同梱の MCP server `blemma` の道具 `ask_board` (`mcp/blemma_mcp.py`)

役: エージェントが文脈から用意した 2〜6 個の選択肢を、MCP の elicitation (form・enum) で人に出す。Elicitation の hook (§2.3) が板に出し、選ばれた物が道具の戻りになる。独自の注入の口は要らない。

**道具の schema** (`tools/list` で返す。11/4 に `minLength`・`uniqueItems` と説明文の「ここで止める」の 2 文、11/6 に任意の `descriptions` を足した):
```json
{
  "name": "ask_board",
  "description": "Ask the human to pick one of 2-6 short choices (big buttons on the BLEMMA board, or the normal form without it). Use at a decision point or to offer next steps. The server adds 'ここで止める' if absent; reserve one of the six slots for it. A stop or cancel answer instructs you to stop and wait; it cannot enforce a stop.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "title": { "type": "string", "minLength": 1, "maxLength": 80,
                 "description": "One-sentence question, up to 80 characters" },
      "choices": { "type": "array", "items": { "type": "string", "minLength": 1, "maxLength": 40 },
                   "minItems": 2, "maxItems": 6, "uniqueItems": true,
                   "description": "Short, distinct labels; at most five if the stop choice is absent" },
      "allow_free_text": { "type": "boolean", "default": false,
                           "description": "Also accept an answer in the human's own words" },
      "descriptions": { "type": "array", "items": { "type": "string" },
                        "minItems": 2, "maxItems": 6,
                        "description": "Optional short explanations, in the same order and length as choices" }
    },
    "required": ["title", "choices"]
  }
}
```
- 道具の説明文は英語 (Claude が読む物・README と揃える)。字の上限・重複・数を道具の側で確かめ、外れたら `isError: true` で理由を返す。
- **「ここで止める」は server が足す** (11/4 の実装): 選択肢に「ここで止める」が無ければ末尾に足す = 自分の選択肢は 5 つまで・6 つ渡す時は必ず「ここで止める」を含む (含まない 6 つは `isError`)。
- **任意の `descriptions`** (11/6) = 渡す `choices` と同じ順・同じ数の文字列の配列。数や型が違えば `isError`。各文は `oneOf` の各要素の `description` (補助の欄) に載せ、`hooks/elicitation.py` が板の選択肢の `description` へ写す。自動で足した「ここで止める」と「ほかの答え」に説明は足さない。補助の欄が途中で落ちても番号・字・値と答えの意味は変わらない。頁の解説は `desc` で入 / 切 (§4.2)。

**出す elicitation** (2025-11-25 の版の `elicitation/create` の params):
```json
{
  "mode": "form",
  "message": "次の一手を選んでください",
  "requestedSchema": {
    "type": "object",
    "properties": {
      "choice": {
        "type": "string",
        "title": "次の一手を選んでください",
        "oneOf": [
          { "const": "1", "title": "PR の本文を書く", "description": "変更と確かめた事をまとめます" },
          { "const": "2", "title": "試験を回す", "description": "変更に関わる試験を実行します" },
          { "const": "3", "title": "ここで止める" }
        ]
      }
    },
    "required": ["choice"]
  }
}
```
- `message` と `title` = 道具の `title`。`const` = "1"〜"6" (字の違いに強い・v1 の判断)。enum の `oneOf` + `title` がそのまま大きな釦に写る (裏取り §2.4 の含意)。1 欄の単一選択 = 板では 1 押しで送る (§2.3)。
- `allow_free_text` が true = `oneOf` の末尾に `{"const":"other","title":"ほかの答え (書いて伝える)"}`、欄 `"other_text": {"type":"string","title":"ほかの答え","maxLength":200}` (必須でない) を足す。板では「ほかの答え」= 端末で答える (板で文字を書かない)。
- `default` は付けない (押すまで決まらない)。

**応答 → 道具の戻り** (`tools/call` の result の `content` の text・v1 の判断):

| elicitation の応答 | 道具の戻り (text) | `isError` |
|---|---|---|
| `accept` + `choice` = "1"〜"6" | `{"answer": "<選ばれた choices の文>", "index": <1 から>}` | false |
| `accept` + `choice` = "other" + 空白でない `other_text` | `{"answer": "<other_text>", "free_text": true}` | false |
| `accept` + `choice` = "other" + `other_text` が空・空白だけ・無い | `decline` と同じ戻り (`{"answer": null, "declined": true}` + 「人はどれも選びませんでした…」) = 空の文を答えにしない (2 巡目 i25) | false |
| `accept` + `choice` = "1"〜"6" + 空でない `other_text` (端末の form) | `{"answer": "<選ばれた choices の文>", "index": <1 から>, "note": "<other_text (前後の空白を除く)>"}` = 番号に添えた文は条件として守る | false |
| `decline` | `{"answer": null, "declined": true}` + 「人はどれも選びませんでした。別の案を出すか、文で訊いてください」 | false |
| `cancel` | `{"answer": null, "cancelled": true}` + 「人はこの問い合わせを閉じました。作業を止めて次の指示を待ってください」 | false |
| client が elicitation を宣言していない | 「この環境では MCP の問いが出せません。AskUserQuestion か文で訊いてください」 | true |
| 応答が期限までに来ない (11/4 の実装) | 「回答の待ち時間を過ぎました。作業を止めて次の指示を待ってください」+ 出した問いに `notifications/cancelled` を送る | true |
| client が `tools/call` を取り消した (`notifications/cancelled`・11/6 の直し) | 待ちを解き、出した問いにも取り消しを送る。取り消された `tools/call` には応答しない | — |
| 応答の形が合わない (`choice` が出した選択肢に無い・`other_text` が 200 字を超える など) | 理由の 1 文 (英語) | true |

- `cancel` の戻りの「止めて待ってください」は Claude への**指示で、止まる保証ではない** (§5.4)。時間切れの戻りも同じ (止めて待つ指示・同じ問いを繰り返させない = 同梱の skill の読み方の表)。
- **待つ秒** (11/4 の実装) = 板の server の `Limits` の hook の自前の期限と同じ数 (555 秒・§3.4) を読む (数は 1 か所)。板が無く端末の form で答える時も、同じ 555 秒で諦める。遅れて来た応答は捨てる。

**板が無い環境での退化**: 板が居ない・期限 = Elicitation の hook が無出力 → 端末に Claude Code の既定の form (同じ `oneOf` の選択肢) が出る (Esc = cancel)。hooks を入れていない人が使っても同じ form が出る。elicitation を話さない client では上の表の最後の行。

**MCP の話し方** (標準ライブラリだけ = JSON-RPC 2.0 を自前で・v1 の判断):
1. stdio = 1 行に 1 つの JSON-RPC の文・stdout には MCP の文の外を書かない・記録は stderr (MCP の transports 頁 https://modelcontextprotocol.io/specification/2025-11-25/basic/transports — この裏取りの外 = 書き手の知識)。**初日の MCP の確かめの前提**なので 11/3 へ送らず、初日に最小の種で確かめる (§10.1)。
2. `initialize` に `protocolVersion: "2025-11-25"` で答え、client の `capabilities.elicitation` を控える。**Claude Code の側は確定** = `{form: {}, url: {}}` を、2025-11-25 までの利用者が設定した stdio の server にも宣言する (v2.1.287 以降・裏取り §2.4【raw】)。自作の server との版の取り決めと、subagent の中からの問いは別の未確認 = 両方に分岐 (§12.3)。
3. `tools/list` で上の schema。`tools/call` の中で server → client の要求 `elicitation/create` (自分の id) を送り、client の応答 (`action`・`content`) を待つ = stdin を読む thread が id で応答を振り分ける (待つ間に来る `ping` にも答える)。
4. 2026-07-28 の版 (`InputRequiredResult` に入れて返し、client が `inputResponses` を付けて呼び直す = MRTR・裏取り §2.3【raw】) は作らない。2025-11-25 が通らなかった時も**MRTR へ自動で全面変更せず、ask_board を外して範囲を縮める** (§10.2)。

**使い方の届け方** (11/6): `initialize` の返りの `instructions` に、ask_board の使い方の芯 (いつ使うか・選択肢の決まり・戻りの読み方・使わない時) を英語の短い文で載せる = Claude Code が MCP server の案内として読むので、何も入れなくても先回りの作法が載る (650 字 (11/7 夜に note の 1 文を足して 646 字)ほど・道具を後から探す設定でも、起動の時に載るのは道具の名とこの文)。同梱の skill `skills/board/SKILL.md` は、repo の根に置いただけでは Claude Code のどの置き場にも当たらず読まれない (公式の置き場 = `~/.claude/skills/`・project の `.claude/skills/` など)。細かな作法まで載せたい人は `~/.claude/skills/board/` へ写す (README)。

**同梱の skill** `skills/board/SKILL.md` (作法・v1 の判断): ①答えが 2〜6 個の選択肢に絞れる問いは `ask_board` で出す ②作業の区切り (commit の後・試験の後) で「次の一手」を 3 つ前後 ③選択肢は 40 字以内・互いに違う・必ず「ここで止める / 待つ」を 1 つ ④答えを推測で進めない (cancel なら止まる) ⑤Claude 自身の確かめ (2〜4 択) は `AskUserQuestion` でもよい・subagent の中からは `ask_board` (AskUserQuestion が無い) ⑥自由記述が要りそうな問いは、ありそうな答えを先に選択肢に入れてから `allow_free_text` (候補の釦を増やす = 端末へ戻る回を減らす)。CLAUDE.md へ誘導する 1 行の例 =「迷う所は ask_board か AskUserQuestion で 2〜6 択にして訊く」。
- 11/4 の実装 (日本語 + 英語の要約): ③は「無ければ server が「ここで止める」を足す = 6 つの枠の 1 つを空けておく (自分の選択肢は 5 つまで)」。戻りの読み方の表を足した = `index` (n 番目を選んだ → その文のとおりに進む)・`note` (番号に添えた文 = 条件として守る・11/7 夜の 2 巡目 i25)・`free_text` (文を指示として読む)・`declined` (別の案か文で訊く)・`cancelled` (止めて待つ)・**時間切れの `isError` = 止めて次の指示を待つ (同じ問いを繰り返さない)**・それ以外の `isError` = 引数を直すか、AskUserQuestion か文で訊く。時間切れを「引数を直す」の行に入れない (外部のレビュー (別の LLM による反証) の所見)。

**要る版**: Claude Code **v2.1.287 以降** (利用者が設定した stdio の MCP server に elicitation を宣言する版・裏取り §2.4【raw】)。v2.1.314 で確かめる → v2.1.318 で確かめた (§10.3 の 3)。

**Stop の別の使い方 (提出版の外)**: `Stop` の hook が `"decision": "block"` + `reason` を返すと、Claude は止まらず `reason` を指示として続ける (連続 8 回の上限・裏取り §1.8【raw】) = 「Claude が止まった時に板で次の一手を選ぶ」をエージェントの協力なしで作れる。ただ応答のたびに待ちが入り、キーで使う人の端末を塞ぐ (§5.6)。実装済みの `Stop` は状態だけを送り、判断を返さない (§2 の冒頭)。

---

## 3. 答えが戻るまでの流れ = 板の server (`board/server.py`)

### 3.1 流れ
Claude Code (hook を起こす・stdin に問いの JSON) → hook (python・`POST /ask` → `GET /wait` の long-poll で待つ) → 板の server (127.0.0.1・待ち行列) → 板の頁 (`GET /pending` の long-poll で札を受ける → 人が選ぶ → `POST /answer`) → server が取り消しの猶予を持つ → hook の `GET /wait` に答え → hook が自分の stdin の写しから公式の JSON を組んで stdout へ → Claude Code。札の終わりは §3.5 の 4 つ (11/4 = `resolved` は作らない) のどれか 1 つに排他で決まる。

### 3.2 起動と在処 (v1 の判断)
- **起こし方の 1 行** (11/6 の実装・`blemma.py`): `python blemma.py [--demo] [--small|--large] [--set KEY=VALUE] [--port PORT] [--keep-board] [--print-only] [--stop] [--window-size W,H] [--window-position X,Y] [-- claude の引数]`。頭で Python の版を確かめ、3.10 未満なら板も窓も開かずに止まる。
  1. 板を用意する = `board/state/run.json` が読め、token つきの照会に板が答えれば、その板を使い回す (照会は札を作らず、見る人にも数えない)。記録の古さでは捨てない (11/6 = 前は 24 時間を過ぎた記録を捨てていたので、1 日を超えて動いている板・時計が戻った時に、生きている板と同じ port へ新しい板を起こそうとして起動ごと失敗した)。居なければ `board/server.py --no-browser --port PORT` を裏で起こす (最長 10 秒待つ)。 起動の確認は既存の板の照会から共通の絶対期限 (最長 10 秒) で測り、照会の各送受信と成功を返す直前にも見直す (11/4 の実装・外部のレビュー (別の LLM による反証) 2 巡目の MEDIUM)。
  2. 頁を開く = `--small` (既定) は Chrome / Edge の app モードの小窓 (`--window-size` 既定 **640,720**・`--window-position` 既定 = 画面の作業領域の右下・環境変数 `BLEMMA_WINDOW_SIZE` / `BLEMMA_WINDOW_POSITION` でも)。普段のブラウザの窓の大きさの記憶に左右されないよう、`board/state/browser` の専用の profile で開く。`--large` か、app モードが使えない環境 (Chrome / Edge が無い・画面の寸法が取れない) は既定のブラウザ。URL の `?mode=small|large` で扇 / 大きな板を選ぶ。待機中の小窓は 320×120 に縮み、札が来たら元の大きさへ戻る (§4.1)。**`--print-only` では頁を開かない**。**使い回した板に見る頁がもう在る時も、新しい窓を開かない** (11/6 = 同じ板の窓が 2 枚になると固定と透過が効かなくなる・どの端末の札も同じ扇に出る)。
  3. 設定を生成する = hooks **6 本**と同梱の MCP の設定を `board/state/settings.generated.json`・`mcp.generated.json` に書く (§7.2 の形・路はこの repo の絶対路)。
  4. claude を起こす = `claude --settings <生成> --mcp-config <生成> --permission-mode default` (`--demo` なら `--setting-sources project,local --strict-mcp-config` を足す = 個人の設定と MCP を混ぜない・§10.3 の 5) + `--` の後の引数 (`--settings` は断る = 後に出た物だけが効く旗で、BLEMMA の設定と置き換わる)。`--print-only` は起動の行を表示するだけ (Windows は PowerShell に貼れる形・頁は開かない = 見る頁が要る時は `python board/server.py` で板を起こす)。**claude が見つからない時は、板も窓も開かずに止まる** (案内を出して戻り値 1・11/6 = 前は起動の行だけを出して自分の板を止めていたので、案内どおりに打っても扇が出なかった)。
  5. 終わる時 = **同じ置き場の板を使う起こし方の、最後の 1 つが終わる時に板を止める** (11/6 = 前は、板を起こした回が終わると、使い回していた別の回の板ごと止まった)。名簿は `board/state/clients/` = Claude を起こす回ごとの登録 (`client-<pid>-<乱数>.json`) と、起こし方が起こした板の印 (`board-<pid>.json`)。止めるのは印のある板だけ (手で起こした板と `--keep-board` で残した板は止めない)。使い回した板を pid で止める前に、印・run.json の pid と token・token つきの応答の 3 つを照らす (板が答えない時は、同じ番号の別の process を止めない)。最後の 1 つは、自分が使っていた板のほかに、今の run.json が指す板も同じ照合で止める (11/6 = 回が走っている間に `--stop` で板を止め、別の回が新しい板を起こして先に終わると、その板が誰も使わないまま残った)。名簿が読み書きできない時と、名簿の錠を作れない置き場 (`clients` に書けない dir・読み取り専用の checkout) の時は、待たずに、自分が起こした板だけを止める前の動きに戻る (名乗らない・理由を日英 1 行・UltraReview (PR #1) の件 1 = 前は錠の使用中と見て 15 秒待ち、毎回止まった。錠の名が無いのに作成を断られる事が 3 回続いた時に、作れない置き場と見る = Windows で別の回が錠を消す一瞬の断りでは退化しない)。名簿の錠 (`clients/.lock` = 名乗りと「数える → 止める」を互いに割り込ませない) が取れない時は、起こす側は名乗らずに止まり (板も窓も Claude Code も起こさない・理由を日英 1 行ずつ・戻り値 1)、終わる側は数えも止めもせずに板を残す (理由を 1 行・次の起こし方の後始末か `--stop` が止める。`--keep-board` の時はいつもどおり残すだけ)。待つのは 15 秒で、見ている錠を回収できる時刻までは伸ばす (上限 65 秒・件 2)。錠には持ち主の pid と時刻を書き、回収するのは、pid が死んだ錠・記録の無いまま 5 秒を過ぎた錠 (持ち主は作った直後に pid を書く)・Windows で 60 秒を過ぎた錠 (持ち主が開いたままの錠は OS が消させない) だけ (POSIX では、生きている pid の錠は古くても奪わない・外の目の 9 巡目 = 前は 15 秒で錠なしに進み、数え終えて止める直前の回の板を使い回せた)。回収は見てから消す = 判定で読んだ錠と同じ錠 (st_ino・更新の時刻・中身) の時だけ、一意の名へ移してから消す (判定の後に別の回が作り直した錠は消さない・件 3)。`python blemma.py --stop` = この置き場の板を、同じ照合の上で止める口。誤りの時も引数と例外の文は出さない (prompt や token つきの URL を含みうる)。設定の鍵の打ち間違い (`--set dwel=1`) と、読めない環境変数 (`BLEMMA_WINDOW_SIZE` など) は、名だけを出して止める (値は出さない)。`dwell`・`scan`・`key` の値が頁の範囲の外の時も止める (`--set` でも `BLEMMA_OPTS` でも・頁は黙って既定へ戻すので・値は短い英数の形の時だけ出す)。
- 頁の設定 = `BLEMMA_OPTS` に URL の query と同じ形 (例 `scale=1.25&theme=dark`) で書くか、`--set scale=1.25 --set theme=dark` と指定する。`--set` は繰り返せ、同じ鍵は後の指定が勝ち、環境変数より優先する。`mode` は明示した `--small` / `--large` が最優先。渡せる鍵と頁の保存値との関係 = §4.2。
- 子の process (板の server・hook・MCP server) は**本体の python** を `-I` (環境変数と利用者の site-packages を見ない) で起こす (venv の中なら `sys._base_executable`)。`-I` は 11/6 = 利用者の `PYTHONPATH` に標準と同じ名の module があると、hook が exit 1 と traceback で終わっていた (判断は返らないが、毎回 hook の誤りが出る)。`board/` と `hooks/` は空の `__init__.py` を持つ通常の package = 別の所に `board` という名の module が在っても、MCP server の `from board.server import …` が取り違えない。理由 = Windows の venv の `python.exe` は本体を孫として起こす転送役 = run.json の pid が子と合わず、hook の起動も 1 段遅い (実装の判断)。
- 板だけを起こす時 (`blemma.py` も裏でこれを起こす) = `python board/server.py [--port 8765] [--wait 300] [--perm-wait SEC] [--undo-ms 3000] [--allow-host NAME] [--no-browser] [--no-log]` で利用者が起こす (hook から自動では起こさない = 隠れた常駐を作らない)。数の意味と上限 = §3.4。起きたら頁を既定のブラウザで開く (`webbrowser`)。URL は `localhost` でなく `127.0.0.1` で出す (localhost は ::1 に引かれうる)。
- 起動ごとに token = `secrets.token_urlsafe(32)`。在処の file = `board/state/run.json` (`{"port":…, "token":…, "pid":…, "started":…}`・`board/state/` は .gitignore 済み)。**置き場は今のユーザーだけが読める**: POSIX は folder 0700・file 0600。Windows の file は親の folder の許可を継ぐので、板を起こすたびに、鍵を書く前に `board/state` の許可 (ACL) を今のユーザーだけに絞る (先に自分の許可を足し、通った時だけ親からの継ぎを外す。できなければ警告を出して続ける)。鍵を読めた人は代わりに答えを送れるので、同じ PC の他のユーザーに読ませない。ただし、ブラウザの起動行に鍵つきの URL が載るため、他のユーザーの process の起動行を読める OS (多くの Linux) で、複数の人が同時に使う機械は想定の外とする。hook は自分の路から `../board/state/run.json` を読む (利用者の project の cwd に依らない)。file が無い・読めない = 板なし = 無出力。止まる時に消す (落ちて残っても、ふつうは接続が断られて無出力になるだけ。ただし、その port を同じ PC の別の利用者の process が先に取ると、hook はそれを板と見なし、札の本文を渡し、偽の「許可」も受ける = 複数の人が同時に使う機械は想定の外・§5.7・11/7 の公開の点検 BL-PY-01・作り手の裁定 #220 B)。
- port は既定 8765・使用中なら起動を断る (黙って別の port に移らない)。
- 待ち受けは **127.0.0.1 だけ** (0.0.0.0・LAN の IP には bind しない)。`http.server.ThreadingHTTPServer` (`daemon_threads = True`)。札の状態は 1 つの錠の下で変える。

### 3.3 口 (全部 JSON・v1.1 の判断)

| 口 | 呼び手 | 送る物 | 返り |
|---|---|---|---|
| `POST /ask` | hook | `kind` (permission / question / elicitation)・`from` (cwd の末尾の名・session の頭 6 字・agent_type)・`payload` (表示に要る物だけ) | `200` + `id` (札の一意の ID)・`hard_deadline` (時刻)・`hard_deadline_in` (秒 = 555・§3.4)・`wait_giveup` (20)・`wait_hold` (15) / `400` (形が違う) / `401` (token 違い) / `503` + `no_viewer` (見る人なし・§3.4) か `queue_full` (待ちが上限を超えた) → hook は無出力 |
| `GET /wait?id=…` | hook | long-poll (server は最長 15 秒抱える・hook はすぐ呼び直す) | `state` = waiting (+ `card` = 札の状態・`remaining`) / answered (+ `answer`) / released / expired / disconnected。答えを渡し終えた札と終わった札への再照会は closed・知らない id は `404` |
| `POST /notify` | notify.py | `type`・`from`・`title`・`message` | `204` (待たない) |
| `POST /state` | state.py (`UserPromptSubmit` / `Stop`) | `session` (頭 6 字・英数字と `_`・`-` の 1〜6 字)・`state` (`working` / `done`) の 2 欄だけ | `204` / `400` + `bad_state` (余分な欄・型・値の違い)。札は作らない |
| `GET /pending?seq=N` | 頁 | long-poll (最長 25 秒・seq が進んだら返す) | `seq`・`card` (無ければ null・`id`・`kind`・`from`・`payload`・`state`・`view_seq`・`remaining`、deciding の時は `choice` と `undo_remaining`)・`queue` (待ちの数)・`last` (直前に終わった札の `id`・種・終わり。答えが渡って終わった時は `answered_by` = 渡った答えの名札も・11/7)・`light`・`states` (下)・`stats`・`undo_ms` |
| `POST /answer` | 頁 | `id`・`seq` (= 札の `view_seq`)・`choice` (下)・`by` (dwell / key / switch / touch / click)・`presses` (まだ送っていない押しの数・§4.5)・`press_batches` (束の ID つきの押しの数・任意・同じ ID は二度数えない・§4.5)・`tag` (答えの名札 = 頁ごとの乱数 + 送信の番号・任意・英数字と `-` `_` `:` の 80 字まで・形が違えば名札なしで受ける。札の写し・hook への返り・記録には載せない・11/7) | `200` + `undo_ms`・`undo_remaining` / `409` + `ended` (終わった札・終わりの種つき)・`not_current`・`expired`・`not_shown`・`stale` / `400` (`bad_choice`・`bad_press_batches` = 束が list でない・束の id が `[A-Za-z0-9:_-]{1,128}` でない・束の presses が object でない)。頁が「画面が古くなっていました。もう一度選んでください」と出すのは `stale`・`400`・分からない返りの時だけ = `expired`・`ended`・`not_current`・`not_shown` では言わず、取り直した表示と終わりの文に任せる (11/7 夜の 2 巡目 i21) |
| `POST /undo` | 頁 | `id`・`by`・`presses`・`press_batches` (猶予のうちだけ) | `200` + `state` (shown・期限の後なら expired) / `409` (`not_undoable`。判定の前に接続の終了と期限を確かめる。同じ札がまだ頭に居る時は今の `state` を添える = `shown` ならほかの頁が先に取り消した・`deciding` なら答えを渡す途中。もう終わった札には `/answer` と同じく終わりの種 `end` を添える。頁が「取り消しは間に合いませんでした」と出すのは 2 つの時だけ = `end` が answered か released の時 (「答えは渡りました」) と、`state` が deciding の時 (「答えを渡している所です」)。それ以外は取り直した表示と終わりの文に任せる・11/7) / `400` (`bad_press_batches`・猶予のうちの deciding の札だけ = 先に 409 の判定が効く) |
| `POST /stats/reset` | 頁 | 空の object (11/4 の実装) | `204` (計を 0 に・§4.5) |
| `GET /page` | 起こし方 | なし | `200` + `open` (真偽値) = いま板を見ている頁が在るか (頁の見張りが開いている・または直前 2 秒のうちに在った)。札を作らず、見る人にも数えない。見る人の判定と違い、起動の猶予は数えない (11/6・§3.2 の 2) |
| `POST /window` | 頁 | `pin` (真偽値・任意) / `shape` (窓に残す形、または null・任意) | `200` + `found`・対象が見つかれば `ok` (頼んだ操作が窓に当たったか) と `pin` (今の固定の状態)。Windows の小窓の固定と透過 (`board/window_win.py`・ctypes)。触るのは窓の名がこの板の物と一致する 1 枚だけ。他の OS・対象なし・同じ名の窓が 2 枚以上では `found: false` (§4.4) |
| `POST /resolve` | 観察の hook (`PostToolUse`・`PermissionDenied`・**提出版では登録しない**) | `session`・`event` (post_tool_use / permission_denied)・`key` (要求と 1 対 1 に結べる照合の鍵) | **提出版では作らない** (11/4・§10.3 = 1 対 1 の鍵が無い) = 他の知らない口と同じ `404`。作るなら `200` + `closed` (id か null)・`reason` (none / ambiguous / no_key) |
| `GET /`・`/static/…` | 頁 | 板の頁 (data を持たない) | token なしで返す (自分の file だけを許す CSP・`X-Frame-Options: DENY`)。開くのは、起動の時に `board/static/` に在った file の名だけ (11/6 = Windows の装置名 `CON.js` などを file として開きに行かない) |

- **`states`** = session ごとの `session`・`state` (`working` / `waiting on you` / `done`)・`reason`・`stale`・`ago` (更新からの秒)。札の受付と対象の Notification は `waiting on you`、答えを渡し終えると `working`、released / expired / disconnected はその理由つきの `waiting on you`。生きた札がある session は `reason: "card"` の待ちを優先する。状態の記憶は最大 128 件・24 時間、10 分更新のない `working` は `stale`。本文・入力・cwd は持たない。小型の頁の印は「◐ 作業中」「◆ あなたの番」「✓ 完了」(状態なしは「○ 待機中」、理由が disconnected なら「■ 止まった・端末を見てください」)。待ちを最優先し、作業中と完了は古くなっていない物、次に新しい物を選ぶ = 別の会話の古い完了で今の作業を隠さない。
- **choice = 種と番号だけ** (hook が自分の stdin の写しから文と公式の JSON を組む = 板が文を作り変えられない・`answers` の鍵が 1 字もずれない)。形は object = `{"type": …}` + 添字 (0 から・11/4 の実装):
  - permission = `allow_once` / `allow_always` + `suggestion` (何番目) / `deny` + `reason` (定型の何番目) / `stop` / `terminal`
  - question = `answer` + `picks` (問いごとの選んだ番号の列) / `skip` (この質問に答えない) / `terminal`
  - elicitation = `accept` + `picks` (欄ごとの選んだ番号の列・空のままの欄は `[]`) / `decline` / `cancel` / `terminal`。**値 (`values` = 欄の名 → const・真偽・数) は板でなく共通の client が自分の payload の写しから組む** (実装の判断 = v1.1 の「板が values を返す」より、板が値を 1 つも作らない形の方が安全)
  - hook は受け取った値を自分の入力 (選択肢の数・schema) と照らし、外れていれば無出力。
- **`/answer` を受ける条件**: `id` が今出している札・札が shown・`seq` が札の `view_seq` と同じ・server の時計で期限の前。どれかが外れれば `409` (古い画面への押しは効かない・§4.2 の世代)。`view_seq` は札を出した時と取り消しで戻した時にだけ進む = 帯や待ちの数で進む全体の `seq` とは別 (実装の判断)。
- **終わりは 4 つ** (answered・released・expired・disconnected・§3.5)。終わった札への `/answer` は `409` (+ `ended`)・`410` は返さない (11/4)。
- **`/resolve` の採用の条件** (作るなら): `key` が要求と 1 対 1 に結べる時だけ (初日に見つかった時・§3.7)。1 件だけ一致すれば閉じ、0 件・2 件以上・鍵なしは何もしない。11/4 = 鍵が無いので作らない (§10.3)。
- **token**: hook と頁は見出し `X-Blemma-Token` で送る。頁は URL の `#t=<token>` を読む (fragment は server へ送られない = 記録と referer に残りにくい)。`/` と `/static/…` の外は token が合わなければ `401`。
- **Host の照合**: `Host` の名の部分 (port は問わない) が `127.0.0.1`・`localhost`・`--allow-host` で足した名でなければ `403` (DNS rebinding で外の頁から叩かれない)。CORS の見出しは出さない (外の頁の `fetch` は token の見出しで preflight に落ちる)。
- **読む待ちと接続の数**: 要求の行・ヘッダー・本文を読む待ちは 10 秒 (`READ_TIMEOUT`) = 鍵を確かめる前の読み取りで、本文を送り切らない相手を待ち続けない (long-poll は返事を抱えるだけで読まないので、この待ちには掛からない)。同時に抱える接続は 64 本まで (`MAX_CONNECTIONS`) で、超えた分は受けずに閉じる。
- **返す JSON は ASCII だけ** (日本語は `\uXXXX`): 札の文に対のないサロゲートなど UTF-8 に直せない字が混じっても、その札が出ている間じゅう板の取得が落ち続ける、という形にしない。
- 本文 (`payload`・`message`) は札が生きている間だけ記憶に持ち、閉じたら捨てる。server の記録 (`log_message`) は口の名と状態だけ。

### 3.4 待ち行列・期限と数 (数はこの 1 か所で決める)
- 札は **1 件ずつ** 出す (先に来た物から)。頁に「待ち N 件」。並列の道具・subagent・複数のセッションで溜まる時は、札の頭の「出どころ」で見分ける。
- **期限 = min(表示した時 + 待ち, 作った時 + 作成からの上限)**。表示から数えるので、2 件目の札も表示から待ちの秒を持つ (作成からの上限で抑える)。
- 表示する時に、作成からの上限まで 30 秒を切っていれば、表示せずに expired (表示の直後の期限切れを作らない)。

| 数 | 値 | 決まり |
|---|---|---|
| 待ち (`--wait`) | 既定 300 秒 (表示から) | 作成からの上限以下 |
| 権限の札の待ち (`--perm-wait`) | 既定 = `--wait` (指定が無ければ `--wait` と同じ) | 縮小の時 (§10.2) に縮める (例 120 秒) |
| 作成からの上限 | 540 秒 (定数) | = settings の hook の `timeout` 600 − 60 |
| 表示の最小の残り | 30 秒 | 切っていれば表示しない |
| 取り消しの猶予 (`--undo-ms`) | 既定 3,000 ms | 0〜5,000 ms・5,000 を超える値は起動を断る |
| hook の自前の期限 (`hard_deadline`) | 作った時 + 540 + 5 + 10 = 555 秒 | settings の `timeout` 600 より 45 秒短い |
| `POST /ask` / `GET /wait` の諦め | 2 秒 / 20 秒 | server は `/wait` を最長 15 秒抱える。`/ask` の 2 秒は繋ぐ所から受け終えるまでの総期限 = Windows では閉じた 127.0.0.1 の port への接続がすぐには断られず、この 2 秒まで掛かる (§10.3 の 4)。2 秒は client の側の数 (`hooks/_client.py`・server の `Limits` の値は写しで、試験が両方を照らす) |
| `POST /notify` の諦め | 2 秒 | `hooks/notify.py` の 1 か所 (§2.4) |
| `POST /state` の諦め | 0.25 秒 | `hooks/_client.py` の `state()`・1 回だけ送る (§2 の冒頭) |
| 接続の終了の判定 | 最後の `/wait` が返ってから 5 秒 | 次の `/wait` が来なければ disconnected |
| 待ちの上限 | 20 件 | 超えたら `503` (`queue_full`) → hook は無出力 |
| 見る人の判定 (11/4 の実装) | 30 秒 | 開いている `GET /pending` が無く、最後の返りから 30 秒を過ぎたら「見る人なし」(板の起動も「見た」と数える)。見る人なしの間は `/ask` に `503` (`no_viewer`) = hook は無出力で端末へ・待ちと表示の札は expired (決めた札は猶予を完走・§3.5)。`None` にすると判定しない (試験だけ・旗は無い) |

- **閉じた頁の long-poll** (11/6 の直し): `GET /pending` は相手の接続の生死を 1 秒以下の間隔で見て、切断を見つけたらすぐ返し、見る人の数から外す。実機では閉じた頁を最長 25 秒抱え、その後の 30 秒と合わせて最大 55 秒掛かっていた。余計な long-poll の待ちを解消したもので、見る人なしと判るまでの 30 秒は残る (§16)。
- **settings の `timeout` を変える時は 3 つを一緒に直す**: 作成からの上限 (= `timeout` − 60)・hook の自前の期限 (= 上限 + 猶予の上限 5 秒 + 10 秒)・`--wait` の上限 (= 作成からの上限)。不等式 = `--wait` ≤ 上限 < 上限 + 15 < `timeout`。
- hook の自前の期限 (と `/ask`・`/wait` の諦めの秒) は**受信の完了まで効く総期限** (単調時計) = 通信の無応答の時間 (読み書き 1 回の待ち) とは別。少しずつ返されても延びず、受け終えた後にも見直し、過ぎていれば答えでも判断なし (無出力)。

### 3.5 札の状態と終わりの確定 (v1.1 の判断)

| 状態 | 入る条件 | 頁の文 | hook の動き |
|---|---|---|---|
| queued | `/ask` を受けた (先の札が在る) | 「待ち N 件」に数える | `/wait` = waiting |
| shown | 先頭になり、残りが 30 秒以上 (§3.4) | 札を描く | waiting |
| deciding | 期限の前に `/answer` を受けた (§3.3 の条件) | 「決まりました・取り消す (n)」 | waiting |
| **answered** (終わり) | 猶予が過ぎ、hook の `/wait` へ答えを返し終えた (渡す直前に hook がもう閉じていれば、渡さずに「切断」で終える。返りを書く所が例外で落ちても、渡しの途中の札は必ず閉じる = 先頭に残って次の札を塞がない・11/6) | 「板の答えを Claude Code へ渡しました (端末の確認が続くことがあります)」 | 公式の JSON を組んで stdout・exit 0 |
| **released** (終わり) | 「端末で答える」の猶予が過ぎ、hook へ返し終えた | 「端末で答えてください」 | 無出力・exit 0 |
| **expired** (終わり) | 期限 (表示の前の失効を含む)・**見る人なし** (§3.4 = 待ちと表示の札だけ・決めた札 (deciding) は猶予を完走して渡す・11/4 の実装) | 「時間切れ。端末で答えてください」 | 無出力・exit 0 |
| **disconnected** (終わり) | どの途中の状態でも、最後の `/wait` から 5 秒、次の `/wait` が来ない | 「接続が終了しました。端末を確認してください」(deciding からなら「板の答えは届いていません」を足す) | (hook は居ない) |
| resolved (**作らない**・11/4) | `/resolve` の 1 対 1 の一致 (採用した時だけ) = 1 対 1 の鍵が無いので作らない (§10.3) = この終わりは来ない | (「端末の側で終わりました」= 頁の字だけ残る) | — |

- **終わりは 4 つ** (11/4 の実装 = answered・released・expired・disconnected)。
- **終わりは排他**: server の錠の下で最初に決まった 1 つだけが効き、後から来た出来事 (遅れた `/answer`・`/undo`・`/resolve`) は捨てて、状態の数だけ記録する。
- answered は「hook へ渡した」までで、Claude Code が使ったかは分からない (端末の答えが先なら捨てられる) = 「許可されました」とは書かない。hook への書き込みが失敗したら (例外の種を問わない) disconnected。答えを渡す直前に hook の接続が閉じていた時も、渡さずに disconnected (頁に「渡しました」と出さない・11/6)。
- disconnected は「端末で答えが出た」と書かない (通信の失敗・hook の異常な終わりと見分けられない)。

### 3.6 取り消しの猶予と優先の順
- 頁が `POST /answer` → 札は deciding (猶予 = `--undo-ms`) → 全部の頁に「決まりました・取り消す (3)」 → 猶予のうちに `POST /undo` が来れば shown へ戻す → 来なければ猶予の後に hook の `/wait` へ返して answered (「端末で答える」なら released)。
- = **1 答あたり猶予の分だけ遅れる** (既定 3 秒・0 にもできる)。server の側で持つ理由 = 2 枚の頁 (大きな頁と小窓・PC と携帯など) が開いていても、決まった事が両方に同時に出る (2 枚で別々に押されて答えが 2 つにならない)。
- 優先の順 (上が勝つ):
  1. 期限の前に受けた答えは猶予を完走する (猶予の分だけ期限を越えてよい・最大 5 秒 = §3.4 の hook の自前の期限の内)。
  2. 猶予のうちの取り消し: 期限の前なら shown へ戻る (残りの時間はそのまま)・期限を過ぎていれば expired。
  3. 猶予のうちに接続が終わった (§3.4 の 5 秒) = disconnected (答えは届いていない)。
  4. 期限と `/answer` が同じ時 (server の時計で期限以後に届いた) = expired が勝ち、`/answer` は `409`。
  5. 2 枚の頁からの `/answer` = 先に錠を取った 1 つだけが deciding に、後は `409`。`/resolve` と `/answer` が重なった時も先に錠を取った方。

### 3.7 端末の側で先に答えが出た時 (両方の挙動に分岐)
- 端末で先に答えた時に Claude Code が hook の process を止めるかは**公式の文が無い** (【報告】#103115 が「早い方が勝つ」と書くのは AskUserQuestion の場合だけ・初日の確かめ 1)。
- (a) **止められる**: hook の呼び直しが途絶え、5 秒で disconnected (「接続が終了しました。端末を確認してください」)。hook の process が殺されても (Windows の止め方では後始末が走らない) 呼び直しが途絶えるだけで閉じる。
- (b) **止められない**: hook は待ち続け、札は期限まで残って次の札を塞ぐ。縮小 (§10.2) = 古い札は人が「端末で答えた・閉じる」(= 端末で答える と同じ動き = released・§4.3) で閉じる + 権限の札の待ちを縮める (`--perm-wait`)。
- **11/4 の確定** (§10.3 の §12.3 の 1・実機): **答えの種で分かれる**。権限の dialog で許可の側 (Yes) を選ぶと、hook は止められず最後まで走る = 板の遅れた答えは効かない (= (b))。No (turn を止める) では hook が殺される (= (a))。質問と MCP の口は待つ間に端末の dialog が無く、端末でできるのは Esc (中断) だけ = 殺される (a)。→ (a) と (b) を両方作った:
  - (a) = 呼び直しの途絶えで 5 秒の後に disconnected。
  - (b) = 端末で許可した権限の札は板に残る = 人が「端末で答える」で閉じる (補いの文「端末で答えた時も、これで閉じる」の見え方は §4.3)。端末で答えることが多い人には `--perm-wait` を縮める助言 (例 120 秒・README)。
- `/resolve` (§3.3) は、要求と 1 対 1 に結べる鍵が初日に見つかった時だけ作る (11/4 = 見つからなかったので作らない)。**指紋 (session_id + tool_name + tool_input) は 1 対 1 にならない** (同じ入力の要求が同じセッションで並ぶ・規則で自動で許された同じ呼び出しの PostToolUse も来る) = 指紋では閉じない。PermissionRequest の入力に `tool_use_id` は無い (裏取り §1.5)。

### 3.8 記録と通信の範囲
- `board/state/log-YYYY-MM-DD.jsonl` に 1 札 1 行 = `{"t":"<時刻>","kind":"permission","end":"answered","choice":"allow_once","sec":2.4,"by":"dwell","presses":1,"undo":0}`。道具の名・入力・問いの文・答えの文字は**書かない**。`--no-log` なら書かない。
- **通信の範囲** (BLEMMA が保証する物を限る): BLEMMA は外のサービスへ自動では何も送らない (server は 127.0.0.1 だけで待ち受け、外へ繋がない・頁は外の font と script を読まない)。携帯で使う時は、**利用者が自分で設けた転送の先へ札の本文と token が渡る** (その先は BLEMMA の保証の外)。MCP の問いへの答えは Claude Code を通って問うた server へ返る (BLEMMA の外の通り道)。機外へ一切出さない使い方では携帯を使わない。README の「外へ出さない」の文もこの範囲に合わせる (公開の門・§8)。

---

## 4. 板の頁 (`board/static/`)

### 4.1 見た目
- 札 1 枚 = 頭 (口の種・出どころ・残りの秒) / 本文 (何をしようとしているか・問い) / 釦。**大きな板** (`mode=large`) は釦の列・左下に固定の「作業を止める」など・右下に「端末で答える」・右上に計。
- 大きな板の通常の釦は高さ・幅 **96px 以上** (倍率 1 の CSS px)、間は 24px・端の余白 48px。幅 720px 以下では余白と間を 16px にして縦 1 列・計を隠す。**高さ 760px 以下では**釦の最小を 72px、余白 16px・間 12px にし、本文の枠を最低 140px 保つ。残りの秒は 60 秒を切ったら色を変える。
- **字の決まり** (基準は `scale=font=1`): 大きな板は釦と本文 28px・頭 36px・問い 32px・釦の説明 22px・本文の巻物と状態の行と帯 24px・計と小さな釦 20px (番号と既定の印は 18px)。扇の和紙は本文 18px・頭 20px・「変更」の行 22px が基準。小型表示の字は `face` の字体を使い、太字を使わず大きさで区別する。`font` と窓に合わせる倍率で字も追従する。設定などの小さな釦はキーとクリックで押す。
- **扇 (OhGi)** (`mode=small`) = 要を下に、骨が 168 度開く折り扇。左の親骨は固定の位置の釦 (止める側・口ごとの意味は §4.3)、右の親骨はいつもの確認に戻る入口。羽根の字は日本語で「一・二・三・四・五・六」と「止・戻」の一文字 (英語は `1`〜`6`・`Esc`・`0`)。朱の印は無い。羽根の字の基準は 30px、形を計算する時の字の位置の幅は 84 CSS px 以上・押せる帯の厚みは 100px。選択肢の数に合わせて形を作り、表示する時に窓へ収める (`fitFan`)。
- **地紙は内外 2 段** = 外の帯は押す羽根・内の帯は押せない書の帯。見つめた羽根の全文を内の帯に弧に沿って出し、読むために羽根を離れても消さない (別の羽根への注目や画面の更新で替わる)。読む所を押す所から分けた理由 = **全文を読む視線が他の羽根を押さないため**。キーの焦点と走査でも同じ文を出す。
- 書の帯 (`fanScript`) は短ければ 28px の 1 行、次に 22px の 1 行、それでも長ければ 20px の 2 行。帯に入らない時だけ末尾を「…」にし、別の欄に全文を出す。説明は `desc=on` の時に同じ欄へ出す。書の帯の字はこの計算で決め、扇とともに拡大縮小する。他の字は `font` と窓に合わせる倍率、頁全体は `scale` の影響を受ける (§4.2)。小型の ask_board の見出しは「次の一手 (Claude の先回り)」。
- 扇にするのは補助を除く選択肢が 2〜6 個で、権限の札、または 1 問・単一選択の札 (`fanEligible`)。複数の問い・複数選択・確かめの画面などは縦 1 列に戻す。「断る」「前の画面へ」などの補助の釦は羽根の外に残す (最小幅 96px・高さ 44px)。ask_board も「断る」と「この問い合わせを閉じる」を両方持つ。
- **窓は 640×720 の縦長が既定** = 上に扇・下の和紙に問い。横長 (縦横比 3:2 以上) では左に問い・右に扇。横長で扇に載らない札は左に問い・右に 2 列の釦。窓の縁をドラッグすると扇・和紙・字も追従する。`fitFan` は扇を 0.45〜1.8 倍、字への補正を 0.85〜1.4 倍の範囲で調整する。扇の背景や閉じた扇をドラッグすると app の窓を動かせる (羽根と取り消しは移動に使わない)。運ぶ位置は、物理の画素で割り切れる所へ寄せる (`gridStep` = 表示倍率 150% は 2 画素・125% と 175% は 4 画素の刻み・整数倍は 1 画素)。割り切れない位置へ窓を動かすたびに、ブラウザが窓の矩形を外側へ丸めて 1 画素ずつ大きくするため (150% の画面の実の窓で、50 回動かすと 640×720 が 690×770 になった)。それでも大きさが変わった時 (頁を拡大している時など) は、掴んだ時の大きさへ戻す。運んでいる最中に札が来て窓の大きさが替わった時は、掴み直しになる。
- 上の釦 (明暗・設定・常に手前) は、上の帯に pointer が来た時か焦点がある時だけ見せる。札が来ると扇が要から開く (0.45 秒・`prefers-reduced-motion` では動かない)。
- 小型では本文を独立した和紙の枠にする。**Edit の変わる所**は `old_string` と `new_string` を比べ、共通の前後を除いた範囲が長い方の本文の 60% 以下の時に印を付ける。消す所は打ち消し線・足す所は下線。抜き出した前後の短文がそれぞれ 40 字以内で改行を含まない時は、「変更」の行を本文の先頭に足す (`diffRange`・`markChange`)。大きな差分では印や先頭の行が出ない場合がある。
- **長い文章は「▼ 続き」で送る** = ポインタを載せて 0.35 秒後に 1 画面分、その後は 1.5 秒ごと。末尾では止まり、載せ直すと先頭へ戻る。釦を押すか ↓ ↑ PageDown PageUp でも送れる。扇の和紙は読む間に動かない。「▼ 続き」は `dwell=0` でも有効で、本文上の位置で連続して送る機能とは別。滞留を入れても、載せている間の送りはこの 1 本だけ (滞留が満ちても送らない・最終デバッグ 1 巡目 #22)。札が替わった時と、札の中で次の設問へ進んだ時は、和紙 (大きな板は札の枠・幅の狭い大きな板では頁) を先頭へ戻す。答えた (猶予)・取り消して同じ画面へ戻った・印を付けただけ・配色や設定の描き直しは、読んでいた位置を保つ (11/7 夜の 2 巡目 i5)。
- **視線での連続した本文送り** (`scrollDirection`) は既定で切。`dwell>0` かつ扇以外の表示に限り、本文などの枠の上端から 32% 未満を見ると上へ・68% より下を見ると下へ、真ん中は止まる (毎秒 90px)。触る入力・設定の表示中・頁が非表示の間は送らず、ポインタが窓の外へ出たら止める。
- **コピー** = 和紙にポインタを載せた時に釦が現れる (キーでその釦へ移った時も表示)。1 回押すか `C` キーで問いと本文をコピーする。重複する「変更」の行は含めない。
- 明暗と高コントラストの配色は和紙にも追従する (暗い配色では和紙も夜の色)。`theme=auto` は `prefers-color-scheme` に従い、`prefers-reduced-motion` では点滅と動きを抑える。
- 字体 (`face`) は **佑字 粛 (Yuji Syuku)・明朝・ゴシック**の 3 種。佑字 粛は `board/static/` に WOFF2 と SIL OFL 1.1 の文を同梱し、板自身から配る (`font/woff2`)。明朝とゴシックは機械の字体を使う。外の字体や CDN は読まない。言葉は日本語と英語 (`navigator.language` で選ぶ・`?lang=` で上書き)。
- **待機中** = 扇は横向きに閉じて控え、ポインタを載せると状態の字が出る。app の小窓だけは 320×120 に縮み、札が来るか設定を開くと元の大きさに戻る (`fitWindow`)。窓は右下の角を保つ = 縮める時は「小さくする → 動かす」、広げる時は「動かす → 大きくする」の順で頼む (逆の順だと、大きい窓が画面の端で押し戻されて角がずれ、待機の扇が隅に行かない)。読み込みの頭で窓の寸法がまだ 0 の間は動かさず、次のこまで見直す (読み直しで窓が画面の左上へ飛ばない)。元の大きさは `sessionStorage` にも覚え、待機の大きさのまま読み直した窓を「元の大きさ」と取り違えない。札つきで始まった時 (起動の直後・札の途中で頁を読み直した時) は、今の窓の大きさのままにする = 利用者が広げた窓を、前に覚えた大きさへ縮めない。覚えた大きさ (無ければ既定) へ開くのは、待機の大きさの窓に札が来た時だけ。板との切断や停止を検知して 10 秒続くと app の小窓を閉じる。切断と見るのは、板の見張り (`GET /pending`) が続けて 3 回落ちた時 (最初に落ちた時から 10 秒) と、鍵が違って見張りをやめた時だけで、答えの送信が 1 回届かなかっただけでは閉じない (「つながらない」と出して見張りを取り直す)。通常のタブは縮めず、自動では閉じない。
- **札を読む間の通知** = 小型表示では札がある間と、札が消えてから 1.5 秒間、通知の帯と縁を出さない。前の札の終了の文も、次の札がある間は出さない (§2.4)。

### 4.2 入力の 5 通り (選択式の問いなら、どれでも同じ仕事)

| 入力 | 動き |
|---|---|
| 視線 (滞留) | 既定は切 (`dwell=0`)。設定か `--set dwell=1` で入れると、釦の上にポインタが留まり縁が満ちた時に 1 回で押す (`dwell` = 0.3〜5 秒・10 を超える値は ms と読む)。OS の視線の道具がクリックを送る時は切のまま使う。揺れの許しは 150 ms。**外れて 150 ms を超えて戻った時と、描画の間が 150 ms を超えて空いた時は頭から数え直す**。`inputActive()` は頁が見えていれば **焦点が無い窓でも滞留を数える** |
| キー | Tab / Shift+Tab で移る・Space / Enter で押す・数字キー 1〜6 で n 番目の釦 (どちらも 1 回で確定。ただし「次から訊かない」だけは、(1 回目の案内は、決まった時・選び直した時・描き直した時に消す・11/7 夜の 2 巡目 i20) 1 回目は選ぶだけで、同じ数字か、焦点の上の同じキー (Space か Enter) を 1.5 秒の内にもう 1 回押して確定 (2 回目は同じ入り方の時だけ = click・数字・焦点の上のキーを混ぜて決めず、焦点の上の Enter と Space も混ぜない・外の目の 9 巡目) = 扇に鍵の焦点が在るまま端末を見て打った数字や、端末の癖で打った ↓↓Enter (端末では「No」・扇では「次から訊かない」に当たる) が、扇で恒久の規則を書かない・端末の選択肢の番号と扇の番号は揃わない・11/7 の公開の点検 F2 と作り手の裁定・§16・焦点の上のキーは最終デバッグ 1 巡目 #19)・0 = いつもの確認に戻る・Esc = 固定の位置の釦。扇の矢印キーは見た目の順に移るが、「▼ 続き」がある時の ↓ ↑ は本文送りを優先する。PageDown / PageUp も本文送り、C はコピー。猶予のうちは Backspace・Esc = 取り消す |
| スイッチ 1 鍵 | `scan` を有効にすると指定の秒で次を光らせる (値なしの `?scan` は 1.5 秒・設定の既定は切)。列では釦の列 → 固定の位置の釦 → 端末、扇では選択肢の羽根 → 止 → 戻 → 補助の釦 → 頭へ。1 鍵 (既定 Space・`key`) で選ぶ。**猶予のうちは走査を止め、鍵を一度離してからの次の押下 = 取り消す**。選択中は窓内の pointer の最後の動きから 1.5 秒間、走査の光を止め、その後は頭から再開する (`409703d`・見つめて読む動きを邪魔しない)。焦点が無くても見えていれば走査できるが、キーで選ぶには板に焦点が要る。走査なしの Space はキーの行のまま。描き直す時は、走査の光と滞留の縁の満ちを常設の釦 (「▼ 続き」・取り消す) からも外す = 動かない偽の光が本物の光と 2 つ点かない (11/7 夜の 2 巡目 i4)。印の付け外し (複数選択の「次へ」が押せる・押せないに替わる) と「▼ 続き」の出入りで列の長さだけが変わる時は、光の位相を保って置き直す = 光は同じこまの中で別の釦へ跳ばない (`keepLight`・光っていた釦が列から消えた時は、静かな 1 こまの後に頭から・最終デバッグ 1 巡目 #21) 走査が回っている間 (光っている時と、光の前の静かな 1 こま) は、pointer の載った羽根を光らせず、羽根の鍵の焦点は外の縁の弧にする = 光って見えるのは次の 1 押しで押される羽根だけ。強制の配色でも、系の強調色の地は走査の光だけ (11/7 夜・1 巡目 #3)。 |
| 携帯 | 大きな板の縦 1 列は 1 回触ると押す (滞留なし)。扇の表示ではマウスと同じ 2 回で確定。猶予のうちは「取り消す」を 1 回触る (携帯の場面は提出版の外・§4.4) |
| マウス | 扇の羽根と補助の釦は、1 回目で選び、同じ物を 1.5 秒以内にもう 1 回押すと確定 (ダブルクリックも同じ・`ARM_MS=1500`)。`click=single` なら 1 回。大きな板と一覧の釦も 1 回。取り消しは常に 1 回 |

- **表示の世代** (v1.1 の判断): 札の id・設問の番号・札の状態・釦の並びのどれかが変わったら、頁は世代を 1 つ進める。進んだら ①滞留の時計を全部止め、選択 (複数選択の印を含む) を消す ②pointer が一度釦の外へ出て入り直すまで滞留を数えない ③変わった時に押されていた鍵 (キー・スイッチ) は、離すまで数えない ④走査は頭から数え直す。期限切れ・別の画面からの答えで札が替わっても、同じ位置への注視が次の札の釦に移らない (外へ出たと見るのは、釦の無い所に 150 ms より長く居た時か、別の釦に入った時 = 縁の揺れ 1 こまでは解かない・11/7 夜の 2 巡目 i19)。
- 押した直後も同じ (全部の釦の滞留を止め、pointer の入り直しまで数えない = 見続けて 2 回押さない)。扇の背景を掴んで窓を運び、羽根の上で離した時も同じ (運ぶ間は pointer の下を数えていないので、離した所の位置から下の釦を引き直し、離した後に最初に届いた pointer の下の釦も入り直すまで数えない・最終デバッグ 1 巡目の追加)。
- マウスなどの釦を押している間 (文字の選択・ドラッグ・窓の移動) は滞留を数えない。離した後も、pointer が一度外へ出て入り直すまで数えない = 押したまま羽根の上で止まっただけでは答えが出ない。押している事は `pointerdown` / `pointerup` と、動きの知らせに載る釦の状態 (`buttons`) から拾う (窓の外で押し始めたドラッグも分かる)。押した・離したその場でも滞留を解く (1 こまの内に押して離す速い click の後も、入り直すまで数えない)。
- **板から表示が替わった直後の 0.4 秒は、鍵・スイッチ・click の押しを数えない** (`SETTLE_MS`・11/6)。板から替わった = 新しい札・札の状態の変化・取り消しで戻った時。前の表示へ向けた遅れた 1 押しや、スイッチ・鍵のばたつきが、新しい札の先頭 (許可) や出たばかりの「取り消す」に当たらないため (人が新しい表示を見て押すには、これより長く掛かる)。扇の 2 回押しの 1 回目 (選ぶだけの click) も、この間は数えない (数えると、前の札へ向けた 2 回押しの 2 回目が新しい札の羽根を選び、見てから押す click は 1 回で決まってしまう)。取り消しだけは、猶予の短い板 (`--undo-ms` が 0.8 秒より短い) では、数えない間を板の猶予の半分までにする (猶予 0.4 秒以下の板でも押せる。数えない間は板の猶予から、猶予の終わりは写しを受けた時の残りから測る = 猶予の半分を過ぎてから写しが届いた時は、押せる間が残らない事がある)。走査の光も、取り消しには押せるようになった時から当てる (11/7・光っていない物は押せない)。札の中で人が画面を進めた時 (拒否 → 理由・前の画面へ・次の設問・確かめの画面) も、位置や焦点で行き先が決まる押し (焦点の上の Enter / Space・click・触る・支援技術の押し・スイッチ) なら同じ間を置く = ばたつき・押し直し・ダブルクリックの 2 打目が、進んだ先 (戻った画面の許可・見ていない次の設問・確かめの画面の「送る」) に当たらない (11/7)。行き先を名指しする鍵 (数字・Esc・0) と、滞留で進めた時は、この間を置かない = 名指しの鍵は続けて打てる。ただしその直後の 0.4 秒は、位置や焦点で行き先が決まる押しだけを数えない (`S.stepAt`・11/7) = 数字の直後の癖の Enter が、見ていない次の設問の先頭を選んで確かめの画面へ進まない (扇の 2 回押しの 1 回目も、この間は数えない)。取り消しの押しは、この間に入れない (猶予の短い板で、押せる間を削らない)。走査は、間を置いた後の 1 こまぶん (0.4〜1.5 秒) 何も光らせない (光っていない物は押せない = 押すのが遅い人の 1 押しが、先頭の許可に当たらない)。窓が鍵の焦点を得た時 (別の窓を閉じた時に OS が扇へ焦点を移す・人が扇を click する) も同じ守りを置く = 走査は焦点から 1 こまぶん光らせずに頭から回し直し、鍵とスイッチの押し (名指しの数字も) は 0.4 秒数えない (別の窓へ向けて打った鍵や、焦点を得た瞬間のスイッチが、跳んだ先の許可に当たらない・`S.focusAt`・11/7 の公開の点検 F3)。click と触る押しは数える (焦点の無い窓を click した最初の押しを捨てない)・取り消しも数える (安全の側)。これらの間 (名指しや滞留で進めた直後の間も)、頁は `body` に `settling` の印を付ける (見た目は変えない・試験と外の道具が「もう押せる」を読める)。滞留は②が別に守る。0.4 秒より短い滞留 (URL や `--set` で入れた時) は、替わった直後の数え始めを遅らせ、滞留の押しも替わって 0.4 秒より後にする (押しを捨てる形にはしない = 見続けていれば押せる)。
- **窓の大きさや位置が変わった直後は、0.6 秒のあいだ滞留を数えない** (`windowMoved`・`WINDOW_SETTLE_MS`・11/6)。札を出している間に、上の帯 (待ち N 件) や状態の行 (繋がりません・知らせ・数字の案内) の出入りで押せる的 (扇の枠・釦の列・「▼ 続き」) が縦にずれた時も同じ扱い (比べるのは縦の位置だけ。扇の和紙だけが下がった時は守らない・最終デバッグ 1 巡目 #4)。待機の小窓が札で開く時や窓の縁を引いた時は、画面の同じ所に居る pointer の下の物が入れ替わる (置いたままの pointer の下に羽根が来る)。前の窓での pointer の位置と、その下に居た釦は捨てる。落ち着いた後に最初に届いた pointer の下の釦は、入り直すまで数えない。押せる的 (滞留の釦) を含む列や頁そのものが送られた時 (走査の光が窓の外の釦を見える所へ実際に送った時・ホイール) と、設定で窓を隅へ動かした時も同じ扱い = 送られて pointer の下に来た釦を、滞留で押さない (送りでは pointer の位置は捨てない = 見つめて送る動きが続く)。押せる的を含まない枠 (本文・和紙) だけが送られた時と、走査の光が進んでも何も送らなかった時は守らない = 本文から釦へ視線を移す途中で本文が少し送られても、次に見た釦は入り直さずに押せる (11/7)。設定の板を閉じた時も、板の裏で置いたままの pointer の下に居た釦と、閉じた後に最初に届いた pointer の下の釦は、入り直すまで数えない (11/7・板を開いている間に札が替わっていても同じ)。
- **頁が鍵の焦点を先頭の釦へ置くのは、焦点がどこにも無い所へ札 (画面) が出た時と、人が自分の押しで札に答えた・札の中を進めた時だけ** (鍵で使う人が Tab を押し直さずに済むための物・走査が切の時)。人が自分で置いた焦点 (配色・設定・コピー・常に手前の釦) は奪わない = 配色の釦を鍵で 2 回押した 2 回目が、焦点の移った先頭の羽根 (許可) に当たらない (11/6)。同じ釦へ焦点を付け直すのは、同じ画面の描き直し (印を付けただけ・配色や設定・言葉の変更・窓の移り) だけ = 札が替わった時と、札の中で次の画面へ進んだ時は、前の画面と同じ位置の釦 (次の札の「次から訊かない」・次の設問の同じ番号) へ持ち越さない (11/7)。入れ物を隠した釦と押せなくした釦は、ブラウザが焦点を外すまで焦点を持ったまま残るので、焦点が在るとは数えない (設定の板を「閉じる」の Enter で閉じた同じこまに札が来た時は、先頭へ置く)。例外は 3 つ (11/7): 「前の画面へ」で戻った時は来た元の「拒否 …」へ置く (押し直しが許可に当たらない) / 取り消して選ぶ画面へ戻った時はどこにも置かない (ほかの頁が取り消して、途中の写しを受けなかった時も同じ) / 「常に手前」で別の窓 (PiP) へ移る・戻る時は、鍵で使っていれば、付け替える前と後に焦点の在った釦へ戻す (戻せない時と、マウスで押した時は置かない)。
- **来た焦点が、人の押しで使われないまま消えた後は、次の札のどこにも焦点を置かない** (11/7)。前の札の釦へ向けた遅れた Enter が、次の札の先頭 (権限の許可・質問の 1 番目の答え・MCP の受け入れ) に当たらないため = 焦点の行き先を、頁が許可へ変えない (線 3)。
  - **覚える** (`S.focusSeen`): 鍵の焦点がどこかに来た事を、ブラウザの `focusin` の知らせで覚える (人が Tab・矢印・click で置いた時)。頁が自分で置いた焦点 (先頭へ・「拒否 …」へ・設定の「閉じる」へ・窓を移った後) は、置いたその場で覚える (`focusOn()`・窓が背面に居る間は、ブラウザが焦点の知らせを送らない)。焦点の数 (`S.focusGen`) は、焦点の行き先の釦が替わった時だけ進める = 同じ釦への付け直し (描き直しで作り直した同じ鍵の釦・PiP の窓への移し・窓へ戻った時のブラウザの再通知) では進めない。
  - **使われる**: ①この頁の人の答えが渡って、札が終わった時。使われたと数えるのは、押した時に在った焦点 (札の釦の上か、どこにも無い時) だけ = 押した後に来た焦点 (置き直した焦点・取り消しへ置いた焦点) と、「▼ 続き」や上の釦に在る生きた焦点は、その答えでは使われていない。猶予に入っただけでは数えない = 取り消された答えと、ほかの頁が答え直した札は、最初から数に入らない。②人が自分の押しで札の中を進めた時 (拒否 → 理由・次の設問・確かめの画面・`focusUsed()`)。印を付けただけの押し (複数選択の印) は、札の中を進めていないので数えない。③設定の板を閉じた時は、板の中に在る焦点だけ (板の外で消えた焦点の事は、閉じる操作で済ませない)。
  - **置かない**: 先頭へ焦点を置こうとした時に、焦点がどこにも無く、来た焦点が使われないまま残っていれば、置かない。こうなる場面 = 焦点の在る釦の札が、答え無しで替わる・消える・押せなくなる (時間切れ・接続の終了・ほかの頁の答え・ほかの頁の取り消し) / 焦点の在る「取り消す」が消える (猶予が切れる・札が替わる・扇の描き直しが枠を付け替える) / 焦点の在る「▼ 続き」や上の釦 (配色・常に手前) を頁が隠す (待機の小窓は CSS で隠す) / 焦点の在る「次へ」を、印の変化で頁が押せなくする。場面ごとに印を立てる作りではない = 頁のどこが焦点を消しても、同じに効く。
  - **どの答えが渡ったか**: 頁の側で推し量らず、板の名札で読む。頁は答えに名札 (`tag` = 頁ごとの乱数 + 送信の番号) を添え、送信ごとに「押した時の焦点」を控える。板は、渡った答えの名札を「直前に終わった札」(`last.answered_by`) に添える (§3.3)。送っただけの答え (板が断った・届いたか分からない・時間切れと同時に押した)・ほかの頁の答え・板の返りと写しの順は、どれも関わらない。返りを失った 1 回目が板に通っていて、焦点を置き直して送り直した時も、渡った 1 回目の控えで照合する (2 回目の控えと取り違えない)。`last` がほかの札を指している時 (札が続けて終わった) は、読めないので数えない。
  - **戻るきっかけ**: 人が自分でその札に答えるか、札の中を進める (数字・click・触る・Tab や扇の矢印で焦点を置いてからの Enter・読み上げソフトの「押す」)。何も起こさない鍵 (焦点の無い Enter・大きな板の矢印・釦の無い番号・押せない釦の番号)・数えない間の内の押し・間に合わなかった取り消しの鍵では戻らない。期限は無い (札が時間切れになった後、長く離れて戻った人の Enter も、次の札の許可にしない)。
- **pointer の無い click** (読み上げの「押す」・音声操作 = `detail` が 0) は、直前 0.5 秒に鍵が動いていない時だけ、鍵と同じ 1 回の押しとして受ける (扇でも 1 回で決まり、猶予の取り消しは残る)。鍵が自分で起こした click は `keydown` で扱ったので数えない。スイッチの鍵は、Ctrl・Alt・Meta と一緒に押した時は数えない (Ctrl+Space の IME の切り替えで、光っている釦を押さない)。
- 頁の表示 / 非表示 (`visibilitychange`) と焦点の出入り (`blur` / `focus`) の瞬間には `releaseDwell()` で時計を解き、pointer の下の釦は一度外へ出て入り直すまで数えない。焦点が無い間ずっと止める意味ではない。押したままの鍵は離すまで数えず (窓が焦点を取り戻した時は、押したままの印を捨てる = 焦点の無い間に離した知らせは別の窓へ行く。⌘・Ctrl・Alt と組んだ鍵には印を立てない = mac は ⌘ を押している間、ほかの鍵の離した知らせを送らない・最終デバッグ 1 巡目 #10・#33)、`focus` では走査も頭から数え直す (11/6 の実装)。
- ①で消すのは、いまの画面の選択 (複数選択の印) だけ。**同じ札の中で答えた前の問いの選択は持つ** (確かめの画面に並ぶ・待ちの数や帯で板が更新されても消さない)。札が替われば全部捨てる (11/4 の実装)。配色 (☀ / ☾・歯車)・設定の変更 (言葉の切り替えを含む)・「常に手前」の窓 (PiP) への出入りの描き直しは同じ画面 = いまの画面の印も消さない (世代は進める = 押しを数えない間と走査の頭出しは残す・印は選択肢の番号なので言葉が替わっても指す物は同じ・最終デバッグ 1 巡目 #27)。
- 頁は描いた時の `seq` を `/answer` に付ける (§3.3 = 古い画面への押しは `409`)。
- 設定は URL の引数と頁の歯車 (キー・click だけ)。歯車の変更は URL と `localStorage` の `blemma.options` に保つ。端末の側の設定 file は作らない。設定の板は Esc か「閉じる」で閉じる (「閉じる」に焦点が在る時は Enter / Space でも・板の中の選択や入力の Enter / Space には触らない・11/7)。

**設定の鍵** (11/6・`board_core.js` の `parseOptions`):

| 鍵 | 既定 | 値と役 |
|---|---|---|
| `mode` | 頁は `large`・`blemma.py` は `small` | `small` = 「扇 (OhGi)」/ `large` = 「大きな板」 |
| `dwell` | `0` | 滞留の秒 (0.3〜5)・`0` で止める。扇以外の本文の視線送りも有効化する |
| `click` | `double` | 扇のクリック / タッチは 2 回で確定。`single` = 1 回。キー・視線・スイッチ・取り消しには適用しない |
| `scan` | `off` | 走査の秒 (0.5〜10)・`0` / `off` で止める・値なしの `?scan` は 1.5 秒 |
| `key` | `Space` | スイッチのキー (`Enter`・英数字・`KeyA` など、実装の許すキー名) |
| `lang` | `auto` | `auto` (`navigator.language` に従う) / `ja` / `en` |
| `sound` | `off` | `on` / `off` (合図の音) |
| `scale` | `1` | 頁全体の倍率 (0.75〜2) |
| `font` | `1` | 設定では 5 段階 (0.85・1・1.15・1.3・1.5)。URL では 0.8〜2・書の帯は §4.1 の計算 |
| `face` | `yuji` | `yuji` = 佑字 粛 / `mincho` = 明朝 / `gothic` = ゴシック |
| `pos` | `keep` | そのまま / `br` = 右下 / `bl` = 左下 / `tr` = 右上 / `tl` = 左上。app の窓を 4 隅へ動かす (起動時は右下) |
| `clear` | `off` | `on` = 扇の外の角を窓から切る (Windows・`scale=1`・§4.4) |
| `theme` | `auto` | `auto` / `light` / `dark` / `contrast` |
| `desc` | `on` | `on` / `off` (選択肢の解説) |
| `trail` | `off` | `on` / `off` (pointer の所に点を重ねる・録画用・押下を遮らない) |

- 優先の順 = **URL > 頁の保存値 > 既定**。不正な値はその鍵の既定に戻す。起こす時は **`--set` (同じ鍵は最後) > `BLEMMA_OPTS`** を URL に載せる。`mode` だけは **`--small` / `--large` > `--set mode=…` > `BLEMMA_OPTS` の mode > `small`**。URL に渡さない鍵には頁の保存値が効く。
- 窓の **☀ / ☾** は「明るい配色へ」/「暗い配色へ」の釦 (キー・click だけ)。歯車の「配色」と同じ `theme` を替え、URL と頁の保存値に保つ。

### 4.3 固定の位置の釦・取り消す・端末で答える
- **固定の位置の釦** = 全部の札の**同じ位置** (列では左下・扇では左の親骨・Esc でも押せる)。下の字は扇では「止」の羽根の全文として見せる。意味は口ごと (v1.1 の判断):

| 口 | 釦の字 | 返す値 | 効き |
|---|---|---|---|
| 権限 | 作業を止める | deny + `interrupt: true` | Claude を止める ("if `true`, stops Claude"・裏取り §1.5) |
| Claude の質問 | この質問に答えない | deny (PreToolUse) | この道具の呼び出しを断る。Claude は続けうる |
| MCP の問い・ask_board | この問い合わせを閉じる | `cancel` | 問うた server に「閉じた」を返す。server と Claude は続けうる |

  作業全体を止められる範囲 = §5.4。
- **取り消す** = 押した後の猶予のうちだけ、上の中央に大きく出る (押した釦の上には出さない = 見続けていても誤って取り消さない)。扇では内の書の帯そのものが取り消しの的になる (四角の枠を出さない・帯に「取り消す (残り)」と決めた答えを出す・羽根には重ならない)。マウス・有効にした視線・キー・スイッチ・携帯のどれでも取り消せる (クリックは 1 回・§4.2)。`/answer` の返りを待たずに取り消せる。取り消すと札は shown へ戻り、確かめの画面がある札 (複数の問い・複数選択) は**確かめの画面に戻る** (答えた選択を持ったまま・頭からではない・頭からは「やり直す」の釦) (11/4 の実装)。
- **拒否は 2 段** (11/4 の実装) = 権限の札の「拒否 …」を押すと、理由 3 つ (別のやり方でお願いします・いまは要りません・先に説明してください) と「前の画面へ」の画面に替わり、理由を押して送る (11/6 = 補助の釦の字を「戻る」から替えた。羽根の「戻」= いつもの確認に戻る、と取り違えないため)。
- **端末で答える** = 列では右下・扇では右の親骨「戻」(英語は `0`・寸法は §4.1)。押すと (猶予の後に) hook は無出力で終わり、端末の dialog / form が出る (自由記述・板で描けない物・キーで答えたい時の道)。板からはどの札が端末で答え済みか分からないので、字は替えない。補いの文「端末で答えた時も、これで閉じる」は列では釦の下、扇では `desc=on` で注目した時の説明欄に出す。
- **自由記述と入力の直しは端末へ** = 視線の利用者には機能の縮小 (打鍵が要る)。縮小を小さくする道:
  - 候補の釦 = Elicitation の string の `default` を釦に (§2.3・**提出版の外** = 11/4 の実装は作っていない)・ask_board はありそうな答えを先に選択肢に入れる (§2.5 の skill の作法)。
  - 端末の打鍵を最小にする公式の道 = screen reader mode (`--ax-screen-reader` など)。"menus you'd normally navigate with the arrow keys, including permission prompts, become numbered lists ... Type the number of the option you want and press Enter." (裏取り §3.5【raw】) = 番号と Enter の 2 打鍵。質問の dialog と form で同じに効くかは確かめていない = README の助言の 1 行に留める。

### 4.4 小窓を常に手前に・携帯で見る
- **常に手前** = 利用者が小型表示の「常に手前」をキーかクリックで押す。Windows は `POST /window` → `board/window_win.py` の `ctypes` で今の Chrome / Edge の app の窓を固定する (`SetWindowPos`・位置と大きさを変えず、焦点を奪わない)。「固定を外す」で解除する。**触るのはこの板の窓 1 枚だけ** = 窓の名 (既定の port 8765 は「BLEMMA · 扇 (OhGi)」・ほかの port の板は末尾に「 · port」) と窓の種類が一致する窓を探し、ちょうど 1 枚の時だけ当てる。0 枚か 2 枚以上なら何もしない (別の port で起こした板の窓や、同じ板の 2 枚目の窓を、こちらの形で切らない)。戻す向きの頼み (固定を外す・四角へ戻す) だけは、同じ名の窓の全部に当てる (前に固定した窓が、外せないまま手前に残らない・11/6)。API の戻り値を見て、失敗は `ok: false` で頁へ返す。Windows 以外、対象の窓が見つからない時、固定に失敗した時は、対応ブラウザの Document Picture-in-Picture で同じ頁の表示と入力を移す (固定する側だけ。「固定を外す」が窓に当たらなかった時は、手前の窓を増やさない)。大きさは幅 `min(640, 作業領域の幅−40)`・高さ `min(720, 作業領域の高さ−60)` で画面に収める。「元の窓へ」か窓を閉じる操作で戻す。app モードだけで常に手前になるわけではない。
- **窓の位置** = 設定の `pos` で 4 隅を選ぶ (`keep` はそのまま)。app の窓向けで、通常のタブを移動できるとはしない。待機と札の表示で大きさが替わる時も、選んだ隅に合わせる。
- **透過** = `clear=on` は既定で切の Windows 専用の設定。小型表示・`scale=1`・設定を閉じている時だけ、`POST /window` の `shape` と `SetWindowRgn` で扇の外の角を窓から切る。和紙は四角のまま残し、待機中は閉じた扇だけを残して題の帯も隠す。全体を半透明にはしない。対象の窓が無い・他の OS では何も変わらない。切に戻す時は `shape: null` で四角の窓へ戻す。読めない形と、面積が 0 の形 (当てると窓が丸ごと見えず押せなくなる) は当てず、四角へ戻して `ok: false` を返す (11/6)。同じ名の窓が 2 枚以上ある時と、切る途中で API が失敗した時も、古い形を残さず四角の窓へ戻す (作った region は、Windows に渡せた時だけ Windows の持ち物になり、渡せなかった時は解放する)。頁は当たらなかった形を最大 20 回送り直す。形は、窓の外と内の寸法が揃ってから 1 つずつ送る (大きさを変えた直後は外の寸法だけが先に新しくなる = 枠の幅や題の帯の高さがあり得ない値の間は送らず、前の頼みの返事を待ってから次を送る。続けて送ると板に届く順が入れ替わり、古い形が後から当たって切り抜きが外れる)。あり得ない値が 0.8 秒続く時は、頁を拡大・縮小していると見て、切り抜きをやめて四角の窓へ戻す (内の寸法だけが倍率で変わり、形が扇からずれて羽根が切れるため)。板の側も、窓への操作を 1 つずつ順に当てる。扇の字の大きさ (`--font`) は「設定の倍率 × 窓に合わせた補正」で、書く所は 1 か所 (`setFont`) = 窓の操作の応答では固定のボタンの字だけを直す。
- **11/4 の転換で、携帯の場面と転送は提出版の外** (デモにも入れない・§1・§9)。残る物 = server の `--allow-host` (Host の照合に名を足す)・頁の縦 1 列の見え方 (小窓でも使う)・頁の「携帯で開く」の釦 (`#t=` つきの URL を大きく出す)。携帯から Claude Code に答えたい人には、README で公式の Remote Control を案内する (BLEMMA の頁を携帯へ届ける仕組みではない = 板の札を携帯で答えられるとは約束しない)。下は利用者が自分で転送する時の線 (変えない)。
- 板の server は LAN にも外にも開かない。携帯で見る時は利用者が自分の転送で 127.0.0.1 へ届ける = Android の USB なら `adb reverse tcp:8765 tcp:8765` (携帯の `http://127.0.0.1:8765/#t=…` がそのまま通る)・`ssh -L`・自分の VPN の転送 (名が `127.0.0.1` / `localhost` でなければ `--allow-host <名>` で照合に足す)。
- その時は、利用者が設けた転送の先へ札の本文と token が渡る (BLEMMA の保証の外・§3.8)。機外へ一切出さない使い方では携帯を使わない。
- 頁の右上の「携帯で開く」で `#t=` つきの URL を大きな字で出す。token は起動ごとに替わる。
- 理由 (v1 の判断): LAN へ bind する旗は作らない (平文の HTTP では token が同じ網に見える・待ち受けを広げるのは利用者の転送の側に置く)。

### 4.5 計 (操作の数と時間)
- **数える物 = この頁が受け付けた確定や選択の操作** (滞留が満ちた・キーで釦を押した・スイッチで選んだ・触った・クリックした。取り消しも 1 と数える)。扇の 2 回押しの最初は `armChoice` で選ぶだけなので計に入らず、確定する 2 回目を 1 と数える。計はマウスを押した実回数ではない。**送った答えの数** (answered と released) とは別に出す。
- 表示 = 「押し N (視線 a・キー b・スイッチ c・触る d)・送った答え M・経過 mm:ss」。札ごとに「出てから決まるまでの秒」。実装 (11/4): 手段は click を含む 5 つ (クリックは 1 回以上の時だけ出す)・札ごとの秒は直近の 5 枚。
- 頁は札ごとの押した数と手段を `/answer` と `/undo` の `presses`・`by` で server へ渡し、記録は数だけ (§3.8)。
- **計に入るのは `/answer` と `/undo` と一緒に送った押しだけ** (11/4 の実装・外部のレビュー (別の LLM による反証) の MEDIUM を再現して直した): 押しの数は要求ごとに切り離し (送る分を取り出し、次は 0 から)、返りが 200 でなければ同じ札の間だけ未送へ戻す = `/answer` の返りより先に取り消しても、同じ押しを 2 回送らない。送らずに終わった札 (期限・見る人なし・端末で先に終わった) の押し (拒否の理由の画面への行き来など) は入らない = 計は少なめに出る。 押しは ID つきの束 (`press_batches`) で送り、server は札の間だけ受けた ID を覚えて同じ束を二度数えない = 応答が失われて頁が再送しても計は増えない (外部のレビュー (別の LLM による反証) 2 巡目の MEDIUM を再現して直した)。
- 板の外の打鍵 (端末) は数えない (未計測)。OS の側の起動の 1 回は板の計に入れず、別に書く。
- 計を 0 に戻す = 頁の [計を 0 に] (キー・click だけ = 視線で誤って消さない・`POST /stats/reset`)。

---

## 5. 安全と退化

### 5.1 公式の仕様で決まっている物

| 場面 | 結果 | 出典 |
|---|---|---|
| command の hook が timeout | Claude Code が hook を止め、出力を捨てる = "on most events a timed-out hook renders no decision" (exit 0 の保証の外) | 裏取り §1.9【断片】 |
| PreToolUse の hook が timeout | 道具を止めず通常の許可の流れへ ("don't count on a stalled hook to act as a gate")。`onFailure: "block"` の時を除く | 裏取り §1.9 |
| PermissionRequest が exit 2・decision なし | 流れは変わらない | 裏取り §1.5【断片】 |
| Elicitation が無出力 exit 0 | dialog での利用者の答えに任せる | 裏取り §1.7【raw】 |
| hook の allow と規則 | allow は deny / ask の規則を超えない・複数の hook では deny が勝つ | 裏取り §1.6・裏取り §3.2 |
| plan mode | ExitPlanMode 以外の編集に hook の allow は効かない | 裏取り §1.6 |
| `requiresUserInteraction` の MCP の道具 | hook の allow で確認を飛ばせない | 裏取り §1.6 |
| `onFailure` | 既定 `"continue"`・`"block"` だと失敗と時限で道具を止める (v2.1.295 以降) = 雛形に書かない | 裏取り §1.3 |

- 「無出力 = 必ず端末の確認」ではない: BLEMMA は判断を返さず、Claude Code の通常の判断の流れに委ねるだけ。他の規則・他の hook・mode が決めれば、そちらが効く。対話の環境で他の決定が無ければ、いつもの確認が出る。
- http 型の hook の公式の決まり (非 2xx・接続失敗 = 非ブロッキングのエラー・裏取り §1.3) は、command の hook の python が板へ送る HTTP には当たらない。その失敗を無出力に変えるのは `_client.py` (§2.0)。

### 5.2 板の側で足す物 (BLEMMA の約束)
- 人が押した時だけ allow。時限・板なし・壊れた = 無出力 (判断を返さない)。allow を既定にする設定は作らない。
- hook は stdout に JSON 1 個か空・exit 0・例外と通信の失敗は無出力・公式の JSON は hook が自分の入力から組む (§2.0・§3.3)。
- 127.0.0.1 だけ・起動ごとの token (見出しで)・Host の照合・CORS なし (§3.3)。
- 札ごとの一意の ID と、終わり 4 つ (11/4 = `resolved` は作らない) の排他の確定・期限は表示から数え作成からの上限で抑える・「渡しました」と「許可されました」を分ける (§3.4〜§3.6)。
- 頁がどこにも開いていない時は札を受けない (見る人の判定・§3.4 = hook は無出力で端末へ・待ちと表示の札は expired・決めた札は猶予を完走)。
- 「常に手前」は利用者が開く Document Picture-in-Picture (§4.4)。非対応なら釦を隠し、開けなければ「常に手前を開けませんでした」と出す。OS 固有の最前面の保証は足さない。
- 端末で先に許可の側を答えた権限の札は、hook が止められず遅れた板の答えは効かない = 人が「端末で答える」で閉じる・`--perm-wait` を縮める助言 (§3.7 (b))。
- 札は 1 件ずつ・出どころを頭に・Bash の command は省かない・「次から訊かない」は対象と保存期間を見せ、モードの切り替えは別の字・`bypassPermissions`・`auto` へ移す suggestion は出さない (§2.1)。
- 取り消しは hook へ返す前・4 つの入力とも・表示の世代が変わったら滞留と選択を解く (§3.6・§4.2)。
- 記録は選択と時刻と数だけ・BLEMMA は外のサービスへ自動では送らない (§3.8)。
- 計画の承認 (ExitPlanMode)・plan mode の権限・URL mode の問い・描けない schema・除外の表の道具は板に出さない (§2.1・§2.3)。

### 5.3 退化の道
板の server が居ない (run.json 無し・接続を断られた) / 期限 / 「端末で答える」/ 板で描けない形 / hook の例外 → 全部「無出力・exit 0」→ Claude Code の通常の判断の流れ (対話で他の決定が無ければ既定の確認)。settings の timeout で止められた時は Claude Code が出力を捨てる (§5.1)。hooks を入れていない人が ask_board を呼んだ時も、既定の form が出る。

### 5.4 作業全体を止められる範囲
- 保証があるのは**権限の口の「作業を止める」だけ** (deny + `interrupt: true` = "if `true`, stops Claude"・裏取り §1.5【断片】)。
- 質問の口の deny は「この道具の呼び出しを断る」で、Claude は続けうる (裏取り §1.6)。共通欄の `continue: false` (処理全体を止める・裏取り §1.4【断片】) は PreToolUse で効くかを確かめていない = 提出版では使わない。
- MCP の口からは止められない (Elicitation の hook の `continue` は捨てられる【raw】)。`cancel` は問うた server に返るだけ。
- ask_board の戻りの「止めて待ってください」は Claude への指示で、止まる保証ではない (§2.5)。
- 確実に全部を止めたい時の道 = 次の権限の札で「作業を止める」、または端末の Esc (人の手)。README に書く。

### 5.5 ExitPlanMode の扱い
- open の回帰 3 件 = #74256 (v2.1.199 以降 allow が無視され chooser が出る)・#97656 (v2.1.283 で再発・`updatedPermissions` つきも dialog が出た)・#90498 (`updatedInput` を付けないと黙って無視・2.1.246)【報告】(裏取り §1.10)。
- 提出版 = 板に出さない (permission.py が無出力・ask.py の matcher に入れない)。期間の中では調べない (初日の確かめからも外した)。README に「計画の承認は板で出さない (公式の不具合が直るまで)」。

### 5.6 提出版の外に置く物 (外部のレビュー (別の LLM による反証) 1 巡目を受けて外した)

| 物 | 外す理由 | 戻す時 |
|---|---|---|
| http 型の handler (板の server へ直に POST) | 本文の形・接続の切り方・timeout の上限・`allowedHttpHookUrls` の既定が未確認。採るなら別の契約と検収が要る | 提出の後に比べる。比べる所 = Windows の `.exe` の縛り・端末先着の時の切り方・token の渡し方 (env の展開は板を起こし直すと古くなる)・入力の形 |
| ExitPlanMode の調べ | 板に出さないので期間の中では要らない | 公式の不具合が直った後 |
| 板の text 欄 (自由記述)・視線の文字盤 | 期間の中では作らない (§4.3 の縮小を小さくする道で補う) | 提出の後 |
| 入力を直して許可 (`updatedInput`) | 直した文の確かめの画面が要る | 元の入力と差分を見て定型の候補から選ぶ形で |
| Stop の hook で次の一手を問い、続行を指示する | 応答のたびに待ちが入り、キーで使う人の端末を塞ぐ。状態だけを送る Stop は実装済み (§2) | 提出の後 |
| 携帯の QR・plugin として配る形 | 余りの機能 | 提出の後 (plugin は公式の plugins の頁で確かめてから) |

### 5.7 知っていて残した制限

11/6 の反証 (4 つの持ち場の読むだけの反証役 + 別の LLM による外部のレビュー) で分かり、提出版では直さずに残した物。どれも線 3 本 (公式の口だけ・板が無ければ退化・勝手に許可しない) には触れない。

| 制限 | 分かっている事 | 当面の使い方 |
|---|---|---|
| 滞留を入れた扇で、猶予の間に決めた答えの字を読むと「取り消す」が押される | 内側の帯の全部が取り消しの的で、決めた答えの字もその上に出る (取り消される向き = 許可が出る向きではない) | 猶予の間は帯の外を見る。読み直したい時は、取り消してから読む |
| 扇に載らない札 (複数選択・2 問以上・7 択以上) は、既定の窓では縦の列が窓より長くなる事がある | 走査の光は見える所へ送るが、視線だけでは頁を送れない | 窓を縦に伸ばすか、「端末で答える」 |
| 触る入力 (touch) では、上の釦 (設定・配色・コピー・常に手前) が見えず押せない | pointer を載せた時と焦点がある時にだけ出る | マウスかキーで押す |
| 隠れた頁・最小化した頁も「見る人」に数える | 質問と MCP の札は、期限 (既定 5 分) まで扇で待つ (§3.4 の決め) | 端末の行「BLEMMA: 板 (ブラウザ) で答えを待っています」で気づける。小窓を手前に出す |
| 言葉を切り替えた直後は、状態の行と開いている設定が前の言葉のまま | 次の札・設定の開き直しで直る | 見た目だけ |
| 透過 (`clear=on`) で待機の小窓を縦に伸ばすと、切り抜きが閉じた扇の絵からずれる | 次の札で戻る | 待機の小窓は伸ばさない |
| 大きな板の滞留の満ちは、地との色の対比が低い | 明るい配色で約 1.4:1・暗い配色で約 2.4:1 | 扇の表示か、高コントラストの配色を使う |
| 小型の表示では、札の到着を読み上げない・設定を閉じた後の焦点が頁の頭へ行く | 読み上げの「押す」は受ける (§4.2)・扇の取り消しには読み上げ用の名がある | 読み上げを使う人の通り道は、提出の後に実機で確かめる |
| 同じ板の窓が 2 枚ある間は、固定と透過が効かない | どの窓が頼んだ頁か決められない (戻す向きの頼みだけは全部に当てる・§4.4) | 窓は 1 枚で使う (起こし方は、見る頁が在る板に 2 枚目を開かない・§3.2) |
| 端末の窓・タブを ✕ で閉じた・SSH が切れた・kill された時は、起こし方の後始末が走らない (Ctrl+C と `/exit` だけが後始末を通る) | 板・`run.json`・板の印・扇の小窓が残り、次に `blemma.py` を起こした回が終わる時か `--stop` まで止まらない (板が生きているので小窓の 10 秒の自動終了も効かない)。Windows は登録 (名簿) だけ消えて板が残る (ConPTY で実測 5 回中 5 回)・POSIX は登録も残る = その番号を別の process が使い回すと「まだ使っている」と数える (安全側)。許可には届かない (hooks は起こした claude にしか載らない) (1 巡目 #32) | `python blemma.py --stop` で止める |
| `--print-only` が表示する 1 行は、Windows では PowerShell 用 | cmd.exe と Git Bash ではそのまま打てない。Git Bash では日本語の文が化ける事がある。書けない字 (é など) を含む出力先へ向けた時は、理由を出して止まる (2 巡目 i29)。**npm で入れた `claude.cmd` に解決する時は、空白の無い引数の中の `& \| < > ^` が cmd.exe の記号として効く (PowerShell 7 の既定でも 5.1 でも守れない・フォルダー名に `&` を含む置き場 (`R&D` など) や `--` の後の引数) = claude には `--settings` の値が `&` の手前までしか渡らず、残りは命令として走る (写しで再現)。Windows PowerShell 5.1 では引数の中の `"` と空の語も崩れる (最終デバッグ 1 巡目 #9+#13)** | PowerShell で打つ。**`&` などを含む路に置かない・記号を含む引数は `--print-only` を使わず直に起こす・npm 版なら claude.exe を PATH に** |
| mac / Linux・WSL・SSH の先・画面の無い環境 | 手元で試した OS は Windows だけ。mac / Linux は、画面の寸法が取れない時 (tkinter が無い時・tkinter が在っても DISPLAY / WAYLAND_DISPLAY が無い時) に `webbrowser` に落ちる = 画面があれば既定のブラウザのタブで開く。**画面の無い Linux (SSH の先) に文字のブラウザ (www-browser・w3m・lynx・links・elinks) が在ると、タブではなく端末でそれが開き、閉じる (q) まで Claude Code が起きない (頁は JS が無いので空)。`python board/server.py` を手で起こした時も同じ (閉じるまで process が残る) (1 巡目 #14・Linux の実機では未確認 = 代役で再現)** | 提出の後に実機で確かめる。**画面の無い環境では `--print-only` と、手で起こす板 (`--no-browser`) を使う** |
| 板が後始末なしに消えた後、同じ PC の別の利用者の process が同じ port を先に取ると、hook はそれを板と見なす (11/7 の公開の点検 BL-PY-01・作り手の裁定 #220 B) | 起動の記録 (`run.json`) が残ったまま。hook は札の本文をその相手へ渡し、相手が「許可」と返せば、人が押さないまま許可を返す (写しで再現)。同じユーザーの process は元から鍵を読めるので、害が増えるのは別の利用者だけ | 複数の人が同時に使う機械では使わない。板が強制終了した後は `board/state/run.json` を消してから起こす |
| 同じユーザーで動く他のプログラムは、`board/state/run.json` の token を読める (11/7 の公開の点検 BL-PY-07) | 置き場の許可 (§3.2) は他のユーザーへの守り。同じユーザーの process は、Claude Code 自身を含め、token を読んで `/answer` を送れる | 板が見張る相手と同じユーザーの process は信じる前提で使う (README に明記) |
| 板への 1 byte ずつ滴らせる接続は、読みの 1 回ごとの待ち (10 秒) では切れず、接続の枠 (64) を埋められる (BL-PY-04) | 同じ PC の process だけが打てる (頁からは打てない)。枠が埋まっても、hook は判断を返さず端末のいつもの確認に戻る (安全側) | 起こし直す |
| `--stop` と最後の使い手の後始末は、`run.json` の pid を、照会に答えた相手の言うまま止める (BL-PY-05) | 古い `run.json` の pid を OS が別の process に使い回し、その port に別の相手が答えた時だけ (起きる見込みは低い) | 板が強制終了した後は `board/state/run.json` を消してから起こす |
| `--allow-host` で足した名は、Host の照合 (DNS rebinding の守り) の外になる (BL-PY-08) | 携帯の転送の名を足すための旗で、提出版では使い道が無い (携帯の場面は提出版の外・§4.4) | 使わない |
| 大きな板 (`--large`・手で起こした板) では、token が頁の住所の `#t=` に残る (頁の点検 F4) | 普段のブラウザの profile の住所の欄・履歴・前回の tab の復元に残りうる。扇の小窓 (専用の profile・住所の欄なし) はほぼ当たらない。token は起動ごとに替わり、127.0.0.1 と Host の照合の外では使えない | 画面を録る・共有する時は大きな板の「携帯で開く」を開かない |
| 「常に手前」の窓探しは、題 (と窓の型) だけで照合し、process を見ない (F6) | 同じ題の別の窓が 1 枚だけ在ると、固定や透かしがその窓に当たりうる (2 枚以上なら当てない)。頼みは token の要る頁からしか来ない = 許可には届かない | 同じ題の窓を開かない |
| 板で 2 分を超えて答える `ask_board` が裏の task へ移らないのは、公式の文に無い振る舞いに頼っている (11/7 夜の実機の確かめ r14) | 公式の文は「開いている elicitation の dialog を待つ間は移さない」だけ。v2.1.319 では Elicitation の hook が問いを握る間も移さず、133 秒後の板の答えを同じ turn で受けて続けた (同じ版と起こし方で、問いを出さない遅い MCP の道具は 120 秒で裏へ移った = 移さない理由は hook が握っている事) | 版を上げたら確かめ直す。移る版では、答えは task の知らせで後から届き、その前に Claude が先へ進みうる |
| 待機の小窓を縁で 40px より広げると、次の札はその窓のまま開き、札の終わりにその寸法を「元の大きさ」として覚える (2 巡目 i6・実測) | 以後の札は全部その寸法で開き、640×720 には戻らない。利用者が決めた寸法を尊重する作り (§4.1) の帰結。札の間に窓を広げ直せば、その寸法を覚え直す | 待機の小窓は広げない。扇が小さいままなら、札の間に窓を広げ直す |
| 頁を読み込む前に板が止まると (起こしてすぐ Claude Code が終わった時 = `--` の後の旗の打ち間違いなど)、繋がらない頁の窓が残る (2 巡目 i13) | 10 秒で閉じるのは、頁が一度でも板に繋がった窓だけ (頁の JS が切断を数える)。許可には届かない | 手で閉じる |
| 板の在処 (`board/state/run.json`) は置き場に 1 枠 = 手で別の port の 2 枚目の板 (`python board/server.py --port 9000`) を起こすと在処を奪い、それを止めると先の板の在処も消える (2 巡目 i22) | 先の板と扇は動いたまま、hook は板なしとして端末へ戻り (安全側)、`--stop` も板を見つけない。起こし方 (`blemma.py`) は生きた板を使い回すので、手で server.py を 2 枚目に起こした時だけ起きる | 板は置き場に 1 枚。先の板を止めてから起こす。在処が消えたら、先の板を止めて起こし直す |
| `--port` にブラウザが拒む番号 (fetch の bad port のうち 1024 以上 = 1719・1720・1723・2049・3659・4045・4190・5060・5061・6000・6566・6665〜6669・6679・6697・10080) を渡すと、板と Claude Code は起きるが扇の窓は ERR_UNSAFE_PORT の頁になる (2 巡目 i28) | 板の bind も起こし方の照会も通るので止まらない。見る人が居ないので hook は端末へ戻る (安全側) | 小窓に ERR_UNSAFE_PORT が出たら、別の番号 (8766 など) で起こし直す |
| `claude` が shell の alias や関数だけで打てる時 (古い版の local の入れ方 `~/.claude/local`) は「claude が見つかりません」で止まる (2 巡目 i30) | 探すのは PATH の絶対の dir だけ (cwd の claude.cmd を拾わない守り・§7)。alias は子 process から見えない。板も窓も開かずに止まる (安全側) | `which claude` が空なら、案内の第 2 の道 (板を手で起こし、`--print-only` の 1 行を alias の効く端末で打つ) を使う。または公式の手順で `claude` を PATH の実体にする |
| mac では、画面の寸法を測る tkinter が起こし方の process (claude が終わるまで生きる) を Dock に出る型のアプリに変え、回の間ずっと Dock と Cmd+Tab に中身の無い「Python」が残りうる (2 巡目 i32・実機では未確認 = python.org の Python と Tk の振る舞いからの読み) | work_area() が blemma.py 自身の process で Tk() を作り、destroy しても process が終わるまで戻らない。見た目と焦点だけ | 気になる時は `--window-position X,Y` を渡す (tkinter を呼ばない) |
| `blemma.py` が起こした板は、`board/state` の許可を今のユーザーだけに絞れなかった時の警告 (板の stderr) を捨てる | exFAT / FAT32 の USB や ACL を変えられない共有に置くと、token の入る `run.json` が同じ PC の他のユーザーにも読める (継いだ許可のまま) 状態で、何も知らせずに動く。手で起こした板 (`python board/server.py`) は警告を出す。ほぼ同時 (約 100 ms 以内) に 2 つの `blemma.py` を起こすと、負けた側は相手の板を使わずに「板を起動できません」で止まる (もう 1 回打てば通る・許可には届かない) (1 巡目 #8+#31) | 他のユーザーが読めない NTFS / 0700 の置き場に置く。script で 2 つ起こす時は 200 ms 空ける |
| 名簿の錠が取れない時は、起こす側が止まり (戻り値 1)、終わる側が板を残す (待つのは 15 秒・見ている錠を回収できる時刻までは伸ばす・上限 65 秒)。錠を持ったまま消えた回 (名乗りや「数える → 止める」の途中で kill された回) の pid を別の process が使い回すと、POSIX ではその錠が外れず、`blemma.py` が「名簿の錠が取れません」で止まり続ける (外の目の 9 巡目の直しで生まれた型)。Windows は 60 秒を過ぎた錠を回収しに行き、待つ側もその時まで待つので、起こし直さずに 1 分の内に進む。名簿の置き場 (`board/state/clients`) に書けない時は、名簿を使わない前の動きに戻る = 板を使い回した別の回が残っていても、板を起こした回が終わると板が止まる | 錠の回収は pid の生死で決める (生きている pid の錠は古くても奪わない・§3.2)。Windows だけは、持ち主が開いたままの錠を OS が消させない (共有の決まり・3.13 と 3.10 で実測) ので、生きている pid でも 60 秒を過ぎれば回収を試みる = 生きている持ち主からは奪えず、使い回された pid の錠だけが外れる。記録の無い錠は 5 秒で回収し、回収は見てから消す (判定で読んだ錠と同じ錠の時だけ・UltraReview (PR #1) の件 2・3)。止まる向きなので、勝手に許可する道は無い。使っている板を奪うのは、書けない置き場の前の動きだけ (残った回の hook は端末の確認に戻る・件 1) | 起こす時は少し待って起こし直す。ほかに `blemma.py` が動いていないのに、起こし直しても続く時は、`board/state/clients/.lock` を消す。終わる時に出て残った板は `python blemma.py --stop` で止める。「名簿 (board/state/clients) に書けないため」と出たら、その dir を今の利用者が書けるようにする (前に sudo で起こして作られたなら、持ち主を戻す) |
| `ask_board` が足す選択肢「ここで止める」と「ほかの答え (書いて伝える)」は、英語の頁 (`lang=en`) でも、板が無い時の端末の form でも日本語のまま | 選択肢の title は 1 本の文字列で、頁の {ja,en} の切り替えが効かない。意味は index と本文で Claude に届く (`{"answer":"ここで止める","index":4}`)。英語の Claude が "Stop here" を 3 択に入れると「ここで止める」がもう 1 本足され、止める選択肢が 2 つ並ぶ (6 択に入れると isError) (1 巡目 #29) | 英語の人は固定の羽根「Esc Close this request」で止める。2 言語の 1 本 (「ここで止める / Stop here」) にする直しは提出の後 |
| MCP の道具の権限の札は要約の行 (file・url の名) が無く、入力の JSON を Claude が出した鍵の順のまま 2,000 字で切る (§2.1 の選択・§16 ⑦) | 長い欄 (content・stdin) が先に来る入力では、書き込む先の path や command が見える範囲に 1 字も入らないまま「許可 (今回)」「次から訊かない」が出る (写しで再現・鍵の順を Claude Code が保つかは未実測)。見出しの「先頭 2000 字・全 N 字・続きは端末で」と、同時に出る端末の dialog が守り。`command` を持つ MCP の道具も Bash と違って切られる (hook の MCP の規則が先に当たる = §2.1 の「command を持つ道具は Bash と同じ」は組み込みの道具だけ) (1 巡目 #30) | 見出しに「続きは端末で」が出た MCP の札は端末で読んでから答える。提出の後に MCP の枝にも要約 (path・url・command を先頭へ並べ替えて表示) を足す |
| URL に手で書いた `dwell` / `scan` / `key` が範囲 (0.3〜5・0.5〜10・許す鍵の名) の外だと、丸めずにその鍵の既定 (滞留と走査は切・鍵は Space) に戻る (`parseOptions`・設計の「不正な値は既定に戻す」) | 走査が黙って切になると、1 鍵で届くのは焦点の置かれた先頭の羽根 (許可 今回) だけで、Space では取り消せない (Esc / Backspace で)。JS で丸めると ms の割り算が先に効いて dwell=12 が 0.3 秒・scan=25 が 0.5 秒の最速値に落ちる (視線の人に誤押しの値) ので丸めない。`--set`・`BLEMMA_OPTS` の分は起こし方が値を確かめて止める (1 巡目 #6・#24・§3.2) | 歯車の設定で入れる (範囲の外は欄が既定に戻るので気づける) |

---

## 6. 先行の道具と BLEMMA の 3 点

### 6.1 先行の道具 (URL と細目 = 裏取り §6)
- claude-remote-approver (GitHub・MIT) = 携帯から権限の承認・拒否 (PermissionRequest の hook + AskUserQuestion・通知の中継・時限で CLI の確認へ戻る)。
- claude-board (PyPI) = 携帯・物の釦から承認 (頁の中でライセンスが MIT と AGPL で食い違う)。
- = 「手元の外から権限を押す」は既に在る。
- 11/4 に足した 3 つ (転換の検討で読んだ):
  - herdr-ask-inbox (https://github.com/speardragon/herdr-ask-inbox) = herdr の plugin。Claude の `AskUserQuestion` の待ちを 1 つの popup に集め (先に来た順)、その場で答える。権限 (`PermissionRequest`) は対象外 (README "Permission approval is left to the native UI to eliminate any risk of misdelivery.")。
  - OpenAI Supply Co. × Work Louder の小さな鍵盤 (https://worklouder.cc/) = OpenAI のコーディングエージェント専用。光る鍵で作業ごとの状態 (idle・thinking・complete・needs input・error) を見せ、鍵で承認と却下。数量限定で売り切れ。手で押す前提。
  - VibeSignal (https://pypi.org/project/vibesignal/・BSD-2-Clause) = 市販の busy light を Claude Code の hook で光らせるソフト + 最前面の小窓。README に "There is no purpose-built "AI agent light" product." = 知らせるだけで、答える口は無い。
- = 「端末の外で知らせる・答える」(popup・光・鍵盤・携帯) も既に在る。作り手が 11/4 に調べた範囲では、視線とスイッチの走査に触れた物は見つからなかった。

### 6.2 BLEMMA の 3 点 (README と動画の頭に・3 つとも動画で実の操作を見せる = §9)
1. **先回り** = 問いが出る前にエージェントが `ask_board` で選択肢を作る。人は選ぶだけ。
2. **選択式の問いは同じ板で全部** = 権限・Claude 自身の質問・MCP の問い (elicitation) を 1 枚の板で。
3. **マウス・視線・スイッチで使う小窓** (11/4 の転換で「携帯」→「小窓」) = 既定はマウスの 2 回押し。設定で視線の滞留や 1 鍵の走査を入れられる。固定の位置の釦・取り消し 3 秒 (1 鍵でも)・同じ頁を大きな板と扇で使う。
- 3 点の前に置く 1 行 = テーマ 2 の名指し (§1「名乗るテーマ」= 操作の壁を取り払う)。

### 6.3 代替の道 (BLEMMA が hooks を選ぶ理由)

| 道 | 答えられる物 | BLEMMA の主にしない理由 |
|---|---|---|
| Agent SDK `canUseTool` | 権限・AskUserQuestion (同じ callback・"The callback can stay pending indefinitely."【raw】裏取り §4) | 対話の `claude` の画面ではない・自作の app が要る |
| TS SDK `onElicitation` | MCP の問い | 同上・Python の SDK には elicitation の口が確認できない |
| Channels の permission relay | Bash・Write・Edit などの許可 | research preview・起動の旗が要る・AskUserQuestion は対象外 (記載なし)・裏取り §3.4 |
| Remote Control | 携帯から one-tap の承認 | 端末でしか描けない要求は外れる・板の形にできない |

- = 主の道は hooks (いつもの `claude` をそのまま使う)。README に「SDK で使う時は `canUseTool` に板を繋ぐ」の 1 節 (任意・11/6)。

---

## 7. 作り

### 7.1 file の木 (repo の根 = `blemma/`・11/6 の時点)
```
blemma/
  blemma.py                     起こし方の 1 行 = 板を用意 (居れば使い回す)・頁を小窓で開く・設定を生成・claude を起こす (§3.2)
  board/__init__.py             空 (board を通常の package にする = 別の所の同じ名の module と取り違えない)
  board/server.py               127.0.0.1 の小さな HTTP・待ち行列・状態の確定・期限・token・Host・取り消し・見る人の判定・記録
  board/window_win.py           Windows の app の窓の固定と透過 (ctypes・対象なしなら何もしない)
  board/README.md               板だけの起こし方・旗・URL の引数・入力・手の確かめ 5 分 (日本語 + 英語の要約)
  board/static/index.html       板の頁 (1 枚)
  board/static/board_core.js    頁の純粋な計算 (滞留・走査・扇の形と字・設定・状態の優先・計) = DOM と通信なし・node で読める
  board/static/board.js         long-poll・入力・世代・取り消し・扇・本文送り・常に手前・計の送り (DOM と通信)
  board/static/board.css        大きな板・折り扇・明暗と高コントラスト・低い窓の本文
  board/static/YujiSyuku-Regular.woff2  扇の書体 (佑字 粛・板自身から配る)
  board/static/YujiSyuku-OFL.txt        書体の SIL OFL 1.1
  board/state/                  (git の外) run.json・log-*.jsonl・settings.generated.json・mcp.generated.json・browser/ (小窓専用のブラウザの profile)・clients/ (起こし方の名簿)
  hooks/__init__.py             空 (hooks を通常の package にする)
  hooks/_client.py              hooks 6 本の共通 = run.json を読む・POST /ask・GET /wait・通知と状態・総期限・転送を追わない
  hooks/permission.py           PermissionRequest → 板 → decision
  hooks/ask.py                  PreToolUse (AskUserQuestion) → 板 → updatedInput
  hooks/elicitation.py          Elicitation → 板 → action / content
  hooks/notify.py               Notification → 板 (光・音)
  hooks/state.py                UserPromptSubmit / Stop → 状態だけを 1 回送る・無出力・exit 0
  mcp/blemma_mcp.py             MCP server (stdio・JSON-RPC 2.0 を自前で)・道具 ask_board・initialize で使い方の芯を返す
  skills/board/SKILL.md         作法 (§2.5・日本語 + 英語の要約)
  examples/settings.blemma.json hooks 6 本 + 許可の 1 行の雛形
  examples/mcp.blemma.json      同梱の MCP server の雛形
  examples/README.md            雛形を手で使う 3 手順 (普段は blemma.py で足りる)
  tests/                        conftest.py + 試験の Python file 12 本 (§7.3・試験だけ pytest・成果物は標準ライブラリだけ)
    test_state.py               状態の 2 本・実の板との通信・状態の優先と古さ
    browser_ohgi.cjs             実の Chromium で扇の描画・入力・縦 1 列・設定を確かめる
    page_dom.cjs                 頁を init() ごと node で走らせる DOM の代用品 (index.html から木を作り、板の写し・鍵・click・pointer の入口から入れる)
    test_browser_ohgi.py         実ブラウザの試験を隔離して起こす (描画ができなければ skip)
    test_window_win.py           窓の形の検証と座標の計算・対象なしと失敗時の扱い (実の窓の操作は通さない)
  docs/                         設計・裏取り
    img/ohgi.png                 扇の画面
  README.md (JA + EN) / LICENSE (MIT)
```
- Python 3.10 以上・標準ライブラリだけ (`json`・`sys`・`os`・`pathlib`・`urllib.request`・`http.server`・`threading`・`secrets`・`time`・`webbrowser`)。Windows / mac / Linux。提出版の handler は command 型だけ。実装 (11/4) で使った物 = 上に加えて `http.client`・`socket`・`select`・`hmac`・`argparse`・`subprocess`・`shutil`・`tempfile`、画面の寸法に `ctypes` (Windows)・`tkinter` (mac / Linux・無い環境では既定のブラウザ)。client の通信は `urllib.request` でなく `http.client` (proxy を通さない・転送を追わない)。
- hook は `_client.py` を同じ dir から import する (script の dir は `sys.path` の頭)。実装 (11/4): `python -I` / `-P` でも読めるよう、hook は自分の dir を `sys.path` の頭に足す・それでも読めなければ exit 0。

### 7.2 設定の雛形 (11/4 に `examples/` に作り、11/6 に hooks 6 本へ・`blemma.py` は同じ形を `board/state/` に生成する)
`examples/settings.blemma.json` (`<BLEMMA>` = clone した場所の絶対パス・`<PY>` = `python -c "import sys; print(sys.executable)"` の出力 = python の絶対パス。mac / Linux は `python3 -c …`、Windows は `py -3 -c …` でも引ける):
```json
{
  "permissions": { "allow": ["mcp__blemma__ask_board"] },
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/state.py"],
                     "timeout": 5 } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/state.py"],
                     "timeout": 5 } ] }
    ],
    "PermissionRequest": [
      { "matcher": ".*",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/permission.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/ask.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board" } ] }
    ],
    "Elicitation": [
      { "matcher": ".*",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/elicitation.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board" } ] }
    ],
    "Notification": [
      { "matcher": "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["-I", "<BLEMMA>/hooks/notify.py"],
                     "timeout": 10 } ] }
    ]
  }
}
```
- `statusMessage` の文は日本語 + 英語 (spinner の行に出る・§2.0)・付けるのは答えを待つ 3 本 (PermissionRequest・PreToolUse・Elicitation) だけ (11/6 = Notification の hook は 1 回送るだけで待たないので、「待っています」と出すと札が無いのに嘘になる)。`args` の頭の `-I` は消さない (利用者の `PYTHONPATH` に標準と同じ名の module があっても、hook が落ちない・§3.2)。追加の `UserPromptSubmit` と `Stop` は `hooks/state.py` = 状態だけを 1 回送り、無出力・exit 0。matcher と `statusMessage` は付けない。
`examples/mcp.blemma.json`:
```json
{ "mcpServers": { "blemma": { "command": "<PY>", "args": ["-I", "<BLEMMA>/mcp/blemma_mcp.py"] } } }
```
- `permissions.allow` の `mcp__blemma__ask_board` = 無いと ask_board を呼ぶたびに権限の札が先に出る (札が 2 重)。MCP の道具の名 = `mcp__<server>__<tool>` (裏取り §1.3)。
- `onFailure` は書かない (§5.1)。`timeout` 600 を変える時は §3.4 の 3 つを一緒に直す。
- 使い方は 2 通り: ①**どの settings.json も書き換えずに** `claude --settings examples/settings.blemma.json --mcp-config examples/mcp.blemma.json` で起こす (試し・デモの既定。旗の名と形はこの裏取りの外 = 初日の確かめ 5・効かなければ隔離したデモ用の project の設定で) ②利用者が自分の `.claude/settings.json` と `.mcp.json` に写す (README の手順)。
- → 11/4 の実装で 3 通り:
  1. **`python blemma.py`** (既定・§3.2) = 上の形を `board/state/settings.generated.json`・`mcp.generated.json` に生成し (`<PY>` = 本体の python・`<BLEMMA>` = repo の絶対路)、`claude --settings <生成> --mcp-config <生成> --permission-mode default` で起こす。デモと録り = `--demo` で `--setting-sources project,local --strict-mcp-config` を足す。
  2. 雛形を写して `<PY>`・`<BLEMMA>` を置き換え、板を `python board/server.py` で起こしてから `claude --settings settings.blemma.json --mcp-config mcp.blemma.json --permission-mode default` (`examples/README.md`)。
  3. 利用者が自分の `.claude/settings.json` と `.mcp.json` に写す (README の手順)。
- 旗の理由 (§10.3 の発見 1〜3・5): `--permission-mode default` = v2.1.318 の対話の既定の mode は auto で、auto のままだと Edit が PermissionRequest を呼ばずに通る = 板の権限の札が出ない。`--setting-sources project,local` = 「次から訊かない」の `addRules` (`localSettings`) をその回に効かせる (源に `local` が無いと file に書かれるだけ)・個人 (user) の設定の hooks を混ぜない。`--strict-mcp-config` = `--mcp-config` の MCP だけにする。`--settings` で渡した `permissions.allow` は信頼の確認の前でも効く。
- hook は起動時に読まれる (第三者の README・裏取り §3.4) = 設定を変えたら `claude` を起こし直す。初回は Claude Code の信頼の確かめが出る (人が 1 回押す)。
- Windows: `python.exe` の路は `py -3 -c "import sys; print(sys.executable)"` で引いて `<PY>` に書く (exec 形は `.exe` 必須 = "On Windows, exec form requires `command` to resolve to a real executable such as a `.exe`."・裏取り §1.3【断片】)。
- 形の出典: 3 段の形・`args`・`timeout`・`statusMessage`・matcher の規則 = hooks.md【断片】(裏取り §1.3)。`.mcp.json` の `mcpServers` の形は公式の mcp 頁 (この裏取りは elicitation の節だけ読んだ = 書き手の知識・初日の確かめ 3 の前提)。

### 7.3 試験と検収
- **自動の試験**: hook の入出力の契約 (判断を返す 3 本・Notification・状態の 2 本)・server の状態と期限・token と Host・ask_board の JSON-RPC と任意の説明・頁の入力と設定・扇の形。Claude Code の代わりに stdin / JSON-RPC を送り、頁の代わりに HTTP で answer を打つ試験を含む。実ブラウザの描画は別の試験で通す (下)。
- **11/7 の実行記録 = 656 passed・0 skipped** (Python 3.13.17 と 3.10.6 の両方・`python -m pytest tests -q`・全 656 件・試験の Python file 12 本 + `conftest.py`・同日の朝は 588 件 = 午後の公開の点検の直しとその外の目で 9 本を足した)。実ブラウザの試験も走る。Chromium の描画・node と組み込みの WebSocket が必要で、使えない環境ではその試験を skip する (skip を合格には数えない)。管理者権限の端末から起こした Chrome は、権限を下げた別の process として自分を起こし直す。メモリ上限つきの job の中ではその起こし直しが実らず、この試験が黙って skip になった (11/6 夜) = 試験の起動に `--do-not-de-elevate` を付けて、起こした process をそのまま browser にする。

| file | 本 | 見る物 |
|---|---|---|
| `test_board_core.py` | 61 | 板の server の状態の確定 (§3.4〜§3.6・時計を差し替えて直に・HTTP なし)・閉じた頁の long-poll・起こし方が訊く「見る頁が在るか」の判定・断った取り消しに添える札の状態と、終わった札の終わり方 (判定の前に接続の終了を確かめる)・頁の計算 (board_core.js) の一部を node で = 質問と MCP の札の見えない字・頁と hook の網の対称 (17 本)・「次から訊かない」から bypassPermissions と auto を外す事・記録の日付の変わり目 (11/7 夜・1 巡目) |
| `test_server_http.py` | 43 | 板の server の HTTP の口 (token・Host・CORS なし・静的の頁・long-poll・run.json・port の使用中 (0.0.0.0・:: の二重で待つ相手を含む = この試験と `test_launcher.py` の同じ試験は 0.0.0.0 で待つので、python に受信の規則が無い Windows では firewall の確認が出うる)・壊れた要求の行・`/window` と、窓の操作へ自分の port を渡す事)・答えの渡しの後始末・静的の口は実在の file だけ・頁の照会 `GET /page`・遅い相手と接続の上限・置き場の許可・深い入れ子の本文 (鍵の前に解かず、鍵があれば 400 で断る)・本文を解くのは鍵が通った後だけ (解いた回数を数える) |
| `test_client.py` | 48 | 共通の client (板なし・接続断・時間切れ・壊れた返り・総期限・転送を追わない・答えと payload の照合) |
| `test_board_js.py` | 139 | 頁の JS を node で走らせる (純粋な計算・DOM の無い vm・滞留・扇・設定・状態の優先・Edit の印・2 回押しの反例・字の倍率の書き手・板の見張りの数え方・窓の名・node が無ければ skip)・運ぶ位置の刻み・窓が替わった直後の滞留・押しを数えない間と走査の静かな 1 こま・支援技術の押し・修飾キーつきのスイッチ・頁の拡大と切り抜き・替わった直後の click を 2 回押しの 1 回目に数えない事・猶予の短い板の取り消し・取り消しの知らせの出し分け・送られた列と滞留・人が置いた焦点・1 こまの内の click・短い滞留の数え始め・窓を隅へ動かした時・見張りを 1 本に保つ事・鍵が起こした click (聞き手から)・写しを当てる所からの送信の印・落ち着いた後の最初の pointer・走査の静かな間の持ち越し。11/7 = 頁を init() ごと DOM の代用品 (`page_dom.cjs`) の中で回し、板の写し・鍵・click・pointer の入口から入れる筋 (札の中の進みの 2 打目・数字の鍵は続けて打てる事・焦点の持ち越しと置き場・PiP の出入りの焦点・取り消しの枠の出入り・設定の板を閉じた後・本文だけの送り・走査の光の送り・取り消しの光・「閉じる」の鍵・押したまま来て同じこまで離す押し・PiP の間の印の後始末・形の送信の例外・答え無しで替わった札の後の焦点 (権限・質問・MCP の問いの各釦から)・自分で答えた札とほかの頁が答えた札の見分け・頁が焦点を消した印を解く押しと解かない押し・押しそびれた取り消しと「▼ 続き」の焦点・数字の直後の Enter と、その間の頁の印・取り消しを巻き込まない事)。11/7 午後 = 窓が鍵の焦点を得た直後の走査と鍵 (札の来る前の印の外れ方を含む)・数字で押す「次から訊かない」の 2 回押し (click と数字を混ぜない)・止まっていた走査が戻る時の焦点の後の静かな間 |
| `test_browser_ohgi.py` | 1 | `browser_ohgi.cjs` で実の DOM・描画・当たり判定・入力・HTTP・一覧・設定・本文送り・2 回押し (描き直しをまたぐ反例を含む)・待機の窓の大きさの覚え方・`clear=on` の字の倍率。窓の移動やクリップボードなどの差し替えは下記・ドラッグで窓の大きさが変わらない事・札の途中の読み直し・替わった直後の押し・長い規則の全文・強制の配色・配色の釦を鍵で 2 回・スイッチで札の中を進んだ直後の 2 打目・走査が送る列と置いたままの pointer。11/7 = 「前の画面へ」の上の Enter×2・広い窓の 2 列の一覧 (自分で送られる要素) をホイールで送った時の置いたままの pointer・Enter で札を次々に答える流れ・ほかの頁が答えた札の後の焦点・押しそびれた取り消しの焦点・走査中の光・pointer・鍵の焦点の見分け (計算後の地と 1 画素の撮影・強制の配色も) (11/7 夜・1 巡目 #3) |
| `test_hooks.py` | 120 | hook 3 本 (permission・ask・elicitation) を別 process で・偽の板・stdin は v2.1.318 の実の形 (値はダミー)・板で描けない任意の欄の題 (`omitted`)・記録の符号 |
| `test_notify.py` | 29 | notify と共通の client を別 process で・偽の板と実の板 (`python -I` でも届いて exit 0) |
| `test_mcp.py` | 71 | MCP server を別 process の UTF-8 の入出力で (JSON-RPC・説明を実の hook と板へ運ぶ往復・取り消し・時間切れ)・`initialize` で返す使い方・深い入れ子と長い行 |
| `test_launcher.py` | 94 | 起こし方・設定の優先 (板は実の子 process・claude とブラウザは起こさない)・名簿 (最後の使い手が板を止める)・同時の起動・止める口 `--stop`・版の確かめ・設定の誤りの名指し・`-I`・見る頁が在る板に窓を増やさない・`--stop` の後に起きた板の後始末 (手で起こした板は止めない)・claude とブラウザを PATH の絶対の dir だけで探す事 (cwd と相対の dir に置いた物を拾わない)・`--print-only` の PowerShell の 1 行の全角の二重引用符 (Windows で PowerShell に実際に渡して確かめる)・-I・-P・PYTHONSAFEPATH=1 での --help・0.0.0.0 で待つ相手の port で止まる事・--set / BLEMMA_OPTS の dwell・scan・key の値の範囲 (11/7 夜・1 巡目) |
| `test_state.py` | 15 | UserPromptSubmit / Stop の無出力・状態だけの送信・総期限・実の板の認証と状態の古さ |
| `test_window_win.py` | 32 | 窓の形の検証 (float に収まらない整数を含む)・実画素への換算・待機中の題の帯を除く計算・この板の 1 枚だけに当てる決まり (0 枚・2 枚以上・port つきの窓の名)・API の失敗の返し方と region の解放の順・別 OS と例外の扱い (Windows の実 API は通さない)・読めない形と面積 0 の形・窓が 2 枚の時の「固定を外す」 |
| `test_packages.py` | 3 | `board/`・`hooks/` が通常の package である事 (別の所の同じ名の module に負けない)・直の起動 (`python board/server.py`・`python hooks/permission.py`・`-I` つきも) が今までどおり動く事 |

- **headless のブラウザでの確かめ** (自動の試験の外・11/4): 隔離した設定の Chrome / Edge で実の頁を動かす確かめ 23 件 + 13 件 (全部通った)。
- **実機の検収** (11/6): 出荷の code と実の Claude Code v2.1.318 で 15 経路中 14 が PASS・残る 1 件は複数行の commit の suggestion の形の問題。異常の経路で勝手に続行した例は 0。検収で直した 4 件・扇を実物で見て直した所 = §16。
- **自動の試験だけでは通らない経路**: `test_board_js.py` は `init()` と通信を差し替え、`test_pip_uses_visible_window_focus_and_retains_held_keys` も代用品の窓でイベントを渡すだけで、実の `requestWindow()` と描画は通らない。`browser_ohgi.cjs` にも PiP を開く操作は無く、ドラッグは `window.moveTo`、コピーは `navigator.clipboard.writeText`、待機の縮小は `window.matchMedia`・`window.resizeTo`・`window.moveTo` を代用品へ差し替える。したがって OS の実窓の移動・縮小・実クリップボードは未検証。`test_window_win.py` は窓と Win32 の呼び出しをすべて代用品へ替え (1 枚だけに当てる決まり・失敗の返し方・region の解放の順を見る)、実の `SetWindowPos`・`SetWindowRgn` による固定・透過は通さない。`test_pending_returns_at_once_when_the_viewer_closed` は `alive` を偽の切断判定に差し替え、実の接続の切断検知までは通さない。`test_launcher.py` は `monkeypatch` で Claude Code とブラウザの起動を差し替える。`page_dom.cjs` (頁を init() ごと回す代用品) は配置 (CSS) を持たず、当たり判定は試験が決める。焦点の外れ方・送りの知らせ・Enter と Space の既定の click の順は、実の Chromium 156 で測った物を前提として置く。656 件の合格だけで、これらの実機の検収まで済んだとはしない (残りは §10.4)。
- **皿ごとの検収** (11/3・11/4) は実の `claude` で、完成版の hook の出力を Claude Code に解釈させる (偽の答えで済ませない)。
- **完成版の異常の経路の検収項目** (当初 11/5 の予定・11/6 の記録は §16): ①端末先着 (§3.7 の (a) か (b) の通りに閉じる) ②板先着 ③待機中の server 停止 ④2 件同時 (待ち行列と 2 件目の期限) ⑤2 画面からの競合 (大きな頁と小窓で同時に押す) ⑥スイッチの取り消し (1 鍵で猶予のうちに)。§3.5 の表の状態と頁の文に照らす。
- **初日の確かめの成功を完成版の検収に代用しない** (初日は使い捨ての試し・§10.1)。

---

## 8. 7 日の工程 (11/2 (月) 12:00 〜 **提出の締切 11/8 (日) 20:00 JST**・1 日 1 皿・毎日 push)

v1.2 = 締切が 11/8 20:00 (参加者ガイド・10/31) なので v1.1 の 8 日から 2 日前倒し (作り手の決め・10/31)。11/10 14:00 はイベント全体の期間の終わり (11/9 一次審査・11/10 13:00〜14:00 最終) = 提出の締切ではない。締切の後の編集は不可 (主催の回答・11/1)。

| 日 | 皿 | 検収 | 主催の予定 |
|---|---|---|---|
| 11/2 (月) 12:00〜 | 12:00〜13:00 キックオフを聞く (審査の詳細・提出フォーム。手元の門の作業 (staging の確かめ・.gitignore・改名) は並行可・`gh repo create` は 13:00 以後) → **公開の門** (公開する資料を決める・該当の箇所を公開用に・新しい repo と新しい履歴で出す・README を公開時点の仕様 (この版) に合わせる・§11.4 の 6) → public 化 (作り手の go)。**初日の確かめ 5 つ** (§10.1・使い捨ての試しの hook と最小の MCP の種) → 分岐を決める (§10.2)。画面は作らない | 5 つの結果と選んだ分岐を §10 に書いた | キックオフ |
| 11/3 (火・祝) | `board/server.py` (状態の確定・期限・token・Host) + 板の頁 (釦・滞留・世代・取り消し・キー・計) + `hooks/_client.py` + `hooks/permission.py` (次から訊かない を含む) | 実の `claude` で Edit と Bash の権限が板に出て、許可 (今回)・次から訊かない・拒否・作業を止める・端末で答える が効く | セッション①② |
| 11/4 (水) | `hooks/ask.py` + `hooks/elicitation.py` + `ask_board` + skill `board` + `hooks/notify.py` (分岐で外した物は作らない) | 実の `claude` で質問・MCP の問い・ask_board (skill の作法で Claude が呼ぶ)・光 | ライブ③ |
| 11/5 (木) | スイッチの走査 (取り消しを含む)・携帯 (転送)・自動の試験・**完成版の異常の経路の実機の検収** (§7.3 の 6 つ) + 夜に台本 (§9) の通し 1 回 (**以後は新しい機能を足さない**) | 6 つが全部 §3.5 の表どおり・tests 緑・台本どおりに通し 1 回 | セッション④ |
| 11/6 (金) | README (日本語が本体 + 英語の要約・差別化 3 点・テーマ・SDK の 1 節・計画の承認は板で出さない・選択式の範囲・通信の範囲・止められる範囲)・雛形・外部のレビュー (別の LLM による反証) 1 巡 (読むだけ・並行) → 直す + 録りの稽古 (尺 2:50・日本語の字幕) + 提出フォームの欄の下書き (概要の文) | 外の目の HIGH 0・稽古 1 回 | セッション⑤ |
| 11/7 (土) | **録り本番** (退化は別の撮り)・日本語の字幕・動画 v1 → 頭から終わりまで再生して確かめる (音と絵の同期) | 3 分 (2:50 前後) の動画 v1 | ライブ⑥ (録画で後から) |
| 11/8 (日) | 直し・動画 v2 (要れば)・**提出は 15:00 目標** (締切 20:00 の 5 時間前) → View Submission・別の口座でリンクの再生・repo の公開を確かめる。**提出の後は repo を動かさない** | 提出の受付・確かめ 3 つ | **締切 20:00** |
| 11/9 (月)〜11/10 (火) | 何もしない (11/10 13:00〜14:00 = 最終・クロージング) | — | 一次審査・最終 |

- 11/3 は文化の日 (祝日)。11/2 は 12:00 からの半日 = キックオフと門と確かめと分岐だけ。
- 失った余白 = v1.1 の「11/6 台本の通しと直しの 1 日」と「11/9〜10 の直しの 1.5 日」。代わりに通しを 11/5 の夜へ、稽古を 11/6 へ寄せた。
- 皿が延びたら、分岐 (§10.2) の縮小の側を先に選ぶ。**11/7 の録りと 11/8 15:00 の提出は動かさない**。11/6 の README が延びたら外部のレビュー (別の LLM による反証) は録りの後 (11/8 午前) へ。
- 11/4 の実際 = 11/3〜11/4 の皿 (server・頁・hook 4 本・`ask_board`・skill) と自動の試験は 11/4 に作った (§15)。11/4 の転換で、11/5 の「携帯 (転送)」は外す (§1・§4.4)。

---

## 9. 3 分のデモの台本 (11/6 版・すべて日本語・総尺 2:45)

- **語り手** = (語り手)。作り手の合成の声が代弁する (三人称)。期間前からある物で、BLEMMA の機能ではない = 札と末尾に「ナレーション = 既存・提出物の外」。主語は常に BLEMMA か JaH。
- **絵** = シンプルな字 + 本物の操作。地は夜藍、字は佑字 粛の白、差し色は真鍮 1 色。字は語りの骨 (冒頭・3 つの区切り・締め) だけ = 8 枚・32 秒。**実画面が 80%** (規約 = 実際に動いている所が中心・スライドの発表は不可)。箇条書きと図は置かない。
- 規約 (参加者ガイド・主催の PDF・11/6 の案内): 3 分以内・日本語・期間中に作った機能だけを紹介・1080p 以上・全画面・タスクバーを隠す・通知を止める。**画面の隅の札** = 場面ごとに「BLEMMA (期間中に作った物)」「OS の視線入力 (既存)」「Claude Code 本体 (既存)」。
- 仕事 = ダミーの repo (日本語の README の誤字と表記の揺れ)。頼みの文 =「README.md の誤字と表記の揺れを直して commit して」= 質問 → Edit → commit → `ask_board` の順に出る (実測)。録りの repo は設計の文書の外に置く (祖先の CLAUDE.md が読まれるため)。
- 物語の輪 = 冒頭「代わりに話します」→ 締め「代わりに、話しました」。受賞の組の型 = 人が先・実物がそのまま入力になる・締めは冒頭の人へ戻る (決勝の動画 14 本の分析)。顔は出さず、視線の点を作り手の印にする。

| 秒 | 種 | 画面 | 声 |
|---|---|---|---|
| 0:00〜0:08 | 字 | (語り手) → 「JaH は視線で PC を使います」・字幕に冒頭の 1 文 | わたしは (語り手)。作り手 JaH の代わりに話します。JaH は、視線で PC を使います。 |
| 0:08〜0:17 | 実 | 端末の確認にズーム。視線の点が細い行の上で揺れ、何も起きない (板なしの撮り) | この点が、JaH の目です。確認は端末の細い一行。矢印キーと Enter が要ります。 |
| 0:17〜0:24 | 実 | 視線を有効にした扇の押しを先出し = 羽根を見つめる → 内の帯に全文 → 弧 → 押される → 端末の確認が消える | BLEMMA は、同じ確認を扇に出します。視線を設定で入れると、見つめて一秒で押せます。 |
| 0:24〜0:27 | 字 | 一 Claude の質問 | (なし) |
| 0:27〜0:36 | 実 | OS の視線の道具のクリックで起動 → 閉じた扇が控える → 頼みの 1 行 → README を読む | 起動は、視線クリック一回。Claude Code に、README の誤字を直す仕事を頼みます。 |
| 0:36〜0:46 | 実 | 扇に 2 択 → 見つめて押す → 猶予 → 端末が進む (hook PreToolUse) | Claude 自身の質問も、同じ扇に出ます。設定した一秒の注視で決まり、三秒の猶予の後に答えが返ります。 |
| 0:46〜0:49 | 字 | 二 権限の確認 | (なし) |
| 0:49〜1:08 | 実 | Edit の札の「変更」と本文の印 → 見つめて押す → 猶予の間に取り消す → 押し直す → 端末の確認が消える (hook PermissionRequest) | 権限の確認は、視線一回。押した後の三秒は、取り消せます。/ 今、取り消して、押し直しました。/ 端末の確認も、消えました。 |
| 1:08〜1:30 | 実 | `git commit` の札 → 設定で走査を入れる → 走査の光 → OS の視線入力で Space を 1 回 → 「次から訊かない」→ commit が通る | スイッチ一つでも、同じ扇です。光が目当てに来たら、一回押すだけ。この Space も、JaH の視線が送っています。/ 次から訊かない、も選べます。commit が通りました。 |
| 1:30〜1:33 | 字 | 三 次の一手 | (なし) |
| 1:33〜1:52 | 実 | `ask_board` の行 → 扇に 3〜4 択 → 羽根に触れて帯で全文を読む → 「ここで止める」を押す | 区切りで、Claude が次の一手を差し出します。選択肢は、今この場で Claude が考えた物。読むのは帯、押すのは羽根。今日は、ここで止めます。 |
| 1:52〜2:05 | 実 | 最後の画面・hooks 6 本 + MCP + skill の字幕 | 公式の hooks と MCP に乗るだけ。本体は、改造していません。設計には、外部のレビュー (別の LLM による反証) も入れました。 |
| 2:05〜2:18 | 実 | 板なしの撮り = 端末のいつもの確認 | 扇が無ければ、いつもの Claude Code です。勝手に許可はしません。人が扇で選んだ時だけ、答えを返します。 |
| 2:18〜2:30 | 実 | 扇のズームから画面全体へ引く | 端末から目を離して働く人にも、片手の人にも、スイッチの人にも、同じ扇が届きます。 |
| 2:30〜2:34 | 字 | 本来、誰にでも届くべきものを | (なし) |
| 2:34〜2:45 | 字 | JaH は明日も、この扇で → BLEMMA — JaH | JaH は、明日もこの扇で仕事をします。JaH の代わりに、(語り手) が話しました。 |

- **撮影の設定** = 通常はマウス向けで視線の機能は切。視線の場面だけ `dwell=1` と録画用の `trail=on` を入れ、走査の場面では `scan` も入れる。OS の視線の道具からクリックを送る場面は `dwell=0`。設定を入れた場面だと字幕で示し、既定で見つめて押せるとは説明しない。
- 計の数は台本に決め打ちしない (録りの実測を出す)。選択肢の文は Claude がその場で作るので台本に書かない。
- 撮りは 2 本 = ① 板なし (約 40 秒) → ② 本撮り (約 2 分・最大 3 回)。動画の字幕の「5 打鍵」は実測が変われば外す。

---

## 10. 初日 (11/2) の確かめと分岐 (Claude Code v2.1.314 時点)

### 10.1 確かめる 5 つ (最小の 3 経路と退化を先に)

| # | 確かめる事 | どうやって |
|---|---|---|
| 1 | **権限の口**: allow・deny + message・deny + interrupt・updatedPermissions (addRules と setMode) が Edit と Bash で効くか。端末の dialog が同時に出るか (Edit・Bash・AskUserQuestion の各々)・端末で先に答えた時に hook の process が止められるか・日本語を含む command で stdin が解けるか | 固定の答えを返す使い捨ての試しの hook |
| 2 | **質問の口**: PreToolUse の allow + `updatedInput` で 2 択・4 択・multiSelect (カンマを含む label も)・2 問。待つ間の端末 (`statusMessage`・質問の dialog)。deny (+ `permissionDecisionReason`) の効き。通らなければ PermissionRequest の allow + `updatedInput` で | 同上 |
| 3 | **MCP の口**: 最小の MCP の種 (stdio・改行区切り・2025-11-25 で initialize に答え、道具 1 つが elicitation/create を 1 回出す = ask_board の種) を繋ぎ、Elicitation の hook (matcher `.*`) で accept / decline / cancel・`hookEventName` の要否・待つ間の端末・subagent の中から呼んだ時 | 種は 11/4 の ask_board の頭になる |
| 4 | **退化**: 板の server を止めて (run.json あり・接続断 / run.json なし)・期限を短く (20 秒) して、3 つの口とも hook が無出力で終わり、Claude Code の通常の流れ (端末の確認) へ戻るか | 同上 |
| 5 | **起動**: `--settings` / `--mcp-config` で hooks と MCP を足して起こせるか (どの settings.json も書き換えない)。+ 作り手の個人の settings の hooks (読み上げ・statusline 等) が録りの端末に混ざらないか = 隔離した設定の dir (環境変数 `CLAUDE_CONFIG_DIR`・名は公式 doc で確かめる・推測) で起こし、`claude --debug` で hooks が BLEMMA の 4 本だけかを見る (混ざると隅の札に無い「既存の物」が画面に映る) | 実の `claude` |

- 外した物: ExitPlanMode の調べ (板に出さない・§5.5)・http 型 (提出版の外・§5.6)。
- 初日の確かめは使い捨ての試し = 成功しても完成版の検収 (11/3〜11/5・§7.3) の代わりにしない。

### 10.2 不成立の時に削る物 (11/2 に決めて §10 に書く)

| 不成立 | 削る物 | 見せ場の寄せ先 |
|---|---|---|
| 質問の口が PreToolUse でも PermissionRequest でも答えられない | ask.py (質問は端末で・README に書く) | 先回りは ask_board へ |
| 自作の 2025-11-25 の server で elicitation が通らない | ask_board (MRTR へ自動で全面変更しない) | 先回りは AskUserQuestion (Claude が 2〜4 択を作る) へ |
| Elicitation の hook が答えられない | elicitation.py と ask_board | 先回りは AskUserQuestion へ |
| 質問の口と MCP の口が両方だめ | 板は権限の口だけ | 差別化 1・2 が消える = 作り手に 1 行で範囲を決め直してもらう |
| 端末で先に答えても hook が止まらず、1 対 1 の照合の鍵も無い | `/resolve` を作らない | 古い札は「端末で答えた・閉じる」で人が閉じる・`--perm-wait` を縮める (例 120 秒) |
| multiSelect の答えの形が通らない | 複数選択の問いは板に出さない (端末へ) | — |
| `--settings` / `--mcp-config` が効かない | 旗で足す道 | 隔離したデモ用の project の設定で成立させる (利用者の全体の設定は触らない) |

### 10.3 初日の確かめの結果 (2026-11-04・実機 = Claude Code v2.1.318)

> 使い捨ての試し (repo の外) = 固定の答えを返す試しの hook 1 本 (4 つの口)・最小の MCP の種 (`ask_board` の頭・2025-11-25)・hooks を §7.2 の形で配線した試しの project。`claude -p` (stream-json と debug の log) と、実の対話の `claude` (端末の画面を文字で読んだ) で測った。Windows 11・Python 3.13。§10 の見出しの v2.1.314 から版が進んでいる。判定は測った分だけ。

| # | 判定 | 根拠 |
|---|---|---|
| 1 権限の口 | 成立 | `allow` で Edit・Bash が通る / `deny` + `message` = Claude は理由の文を受けて続ける / `deny` + `interrupt: true` = Claude が止まる (`-p` で測った・Claude に渡るのは `message` でなく定型の「STOP …」の文・result は `error_during_execution`) / `setMode acceptEdits (session)` = 2 回目から hook が呼ばれない / `addRules` (`Bash(git commit *)`) = `destination: session` なら 2 回目から呼ばれない・`localSettings` は file に書かれるが、設定の源に `local` が無い起こし方ではその回に効かない (下の発見 2)。日本語を含む Edit・Bash の入力は UTF-8 で解けた。hook が待つ間も端末の dialog は同時に出る (Edit・Bash・PermissionRequest に来た AskUserQuestion)。端末で先に答えた時は §12.3 の 1 |
| 2 質問の口 | 成立 | PreToolUse の `allow` + `updatedInput` で、2 問 (4 択と multiSelect) を 1 回の呼び出しで、2 択を別の回で答えられた (2 問の回に Claude が受けた文 = `"どの果物にしますか?"="みかん", "どの色を使いますか? (複数可)"="青, 濃い, 緑"`)。待つ間は質問の dialog が出ず、spinner の行に `statusMessage` (「BLEMMA: waiting on the board…」) が出る。`deny` + `permissionDecisionReason` = Claude に「PreToolUse:AskUserQuestion hook error: <理由>」で届き、作業は続く。PermissionRequest の道は要らない |
| 3 MCP の口 | 成立 | 種が 2025-11-25 で initialize に答え、Claude Code は `elicitation: {form: {}, url: {}}` を宣言した。`accept` + `content` / `decline` / `cancel` が `ask_board` の戻り (§2.5 の表) になった。**`hookEventName` は必須** (省くと検証で出力ごと捨てられ、`-p` では cancel になる)。待つ間は form が出ず、「Calling blemma…」と spinner の `statusMessage` だけ。subagent の中からの `ask_board` も hook に来た (ただし Elicitation の stdin に `agent_id`・`agent_type` は無い) |
| 4 退化 | 成立 (対話) | 閉じた port への POST・run.json なし・期限 20 秒の無出力で、3 つの口とも端末のいつもの dialog・質問・form に戻り、端末の答えが通った。Windows では閉じた 127.0.0.1 の port への接続がすぐには断られず、hook の諦め (2 秒) まで掛かった (run.json が無い時は即時)。`-p` の無出力は拒否 (権限)・cancel (MCP) になる = 退化は対話でだけ確かめられる |
| 5 起動 | 成立 | `--setting-sources project` (か空の `""`) + `--settings <file>` + `--strict-mcp-config --mcp-config <file>` で、走った hook は BLEMMA の分だけ・MCP は `blemma` だけ (debug の log)。作り手の個人の plugin は入らず (入るのは Claude Code 同梱の plugin だけ)、対話の端末の帯も Claude Code 本体の表示だけだった。`--settings` だけ (user の設定も読む既定) は走らせていない = 公式 doc の "Hook entries merge across settings levels rather than replacing each other" で混ざる。`CLAUDE_CONFIG_DIR` は名を公式 doc で確かめた (その dir での login が要るので走らせていない) |

**§12.2 の 7 件**: 1 成立 (4 つの口とも UTF-8) / 2 上の表の 1〜3 (権限 = dialog が同時に出る・`statusMessage` は画面に出ない (80×24 の端末で) / 質問と MCP = dialog も form も出ず、`statusMessage` が spinner の行に出る) / 3 成立 (", " で繋いだ文字列も配列も通る。Claude に見えるのはどちらも ", " で繋いだ文字列 = label にカンマがあると区切りが曖昧) / 4 成立 / 5 要る / 6 成立 (改行区切り・`mcpServers` の `command` + `args` + `env` を `--mcp-config` で渡した) / 7 成立。

**§12.3 の 5 件**:
1. 端末の先着は**答えの種で分かれる** = 権限の dialog で許可の側 (Yes) を選ぶと hook は止められず最後まで走る (遅れた答えは効かない = (b))。No (turn を止める) では hook が `cancelled` で殺される (= (a))。質問と MCP の口は待つ間に端末の dialog が無く、端末でできるのは Esc (中断) だけ = 殺される (a・質問の口で測った・MCP の口も同じ見込み)。→ §3.7 の (a) と (b) を両方作る。
2. 質問の道 = PreToolUse (主のまま)。PreToolUse が決めないと PermissionRequest も `AskUserQuestion` で呼ばれる = §2.1 の除外は要る。
3. 自作の server = 2025-11-25 で通った・subagent の中からの問いも通った。
4. 未確定 (その印の道具では試していない)。PermissionRequest の `mcp_server` は `{"name", "source"}` だけで、道具の `_meta` は来ない = stdin から見分ける道は無い見込み → 除外の表と「渡しました」の文 (§2.1・§3.5) のまま。
5. 無い = PermissionRequest の stdin に `tool_use_id` が来ない (`prompt_id` は turn の id)。

**§10.2 で削る物 = `/resolve` (作らない)**。理由 = 許可の側の端末の答えでは hook が止まらず、1 対 1 の照合の鍵も無い。古い権限の札は「端末で答えた・閉じる」で人が閉じ、`--perm-wait` を縮める (§3.7 (b))。他の行 (ask.py・ask_board・elicitation.py・multiSelect・旗で足す道) は成立したので削らない。

**初日に出た、本文に響く発見** (§2・§3.2・§7.2・§9 の本文は以後の皿で直す):
1. **v2.1.318 の対話の既定の mode は auto** (起動の画面に "Auto mode is now Claude Code's default permission mode.")。auto のままだと Edit は PermissionRequest を呼ばずに通った = 板の権限の札が出ない。→ 雛形・README・デモの起動の行に `--permission-mode default` を足す (端末の帯は「manual mode on」)。
2. 「次から訊かない」の `addRules` (`destination: localSettings`) は、起こし方の設定の源に `local` が無いと、その回に効かない (file には書かれる)。→ 隔離して起こす形は `--setting-sources project,local`。
3. project の `.claude/settings.json` の `permissions.allow` (`mcp__blemma__ask_board`) は、信頼の確認を通るまで無視される (`-p` の警告・対話の信頼の確認に "This folder pre-approves 1 tool permission")。`--settings` で渡した `permissions.allow` は信頼の前でも効いた。
4. 待つ間の端末: 権限の口では `statusMessage` は画面に出ない (dialog が前に出る・80×24 の端末で)・質問と MCP の口では spinner の行に出る。端末の form で `ask_board` に答えるのは、この試しの操作で 5 打鍵 (→ ↓ Space ↓ Enter)。
5. stdin の欄: `effort` は object (`{"level": …}`)・`scratchpad_dir` は対話でだけ来る・Elicitation には subagent の中からでも `agent_id`・`agent_type` が来ない (札の「出どころ」に `agent_type` を出せるのは権限の口だけ)。

→ 11/4 の同期で、発見 1〜3 は §7.2 (旗)、4 は §2.0 (待つ間の端末)、5 は §2.0 (stdin の欄) の本文へ移した。台本 (§9) の直しは 11/6 の皿。

### 10.4 測った物と、まだ検収していない物 (11/6 の時点)
- **初日の確かめで測った物** (§10.3・使い捨ての試しの hook と最小の MCP の種・実の `claude`): 4 つの口の公式の出力の効き (allow・deny + message・deny + interrupt・updatedPermissions・updatedInput・accept / decline / cancel・`hookEventName` の要否)・待つ間の端末の見え方・端末の先着の分かれ方・退化 (対話)・起こし方の旗 (`--setting-sources`・`--strict-mcp-config`・`--permission-mode default`)・stdin の欄。= §12 の 12 件のうち 11 件が決まった ((iii) の 4 は試していない・§12)。
- **完成版で検収した物** (11/6・§16): 実の Claude Code v2.1.318 との 15 経路 (14 PASS・1 件は複数行の commit の suggestion の形の問題)、板なし・時限・見る頁なし・端末先着などで勝手に続行した例は 0。扇の実物で、焦点が無い窓の滞留・本文の領域・字の重なりを見つけて直した。小型の見え方と Document Picture-in-Picture は実装済み。
- **合格まで確認できていない物**: 実ブラウザの自動試験は現在の 656 passed・0 skipped に含む (§7.3)。ただし、実の Document Picture-in-Picture の開閉と描画、Windows の実窓の固定・透過・移動・縮小、実クリップボード、板との切断後の app の自動終了、同時の HTTP の競合、mac / Linux の検収結果はこの記録に無い。非表示 / 再表示の滞留の守りも、代用品の窓の試験を実ブラウザの合格には数えない。実装済みと検収済みを分ける。

---

## 11. 決め

### 11.1 決まっている事
- 名 = BLEMMA (gaze-board・視線の板)・MIT・Python 3.10 以上の標準ライブラリだけ (試験だけ pytest)・Windows / mac / Linux。
- この repo (11/2 に作った新しい repo・§11.4 の 6) に個人情報・鍵・作り手の環境の路は 1 バイトも入れない・デモの repo と本文はダミー。
- code は 11/2 12:00 から (それまでは設計と台本だけ)。public 化は作り手の go (11/2 以後)。
- 線 3 本 (§1)・127.0.0.1・起動ごとの token・記録は選択と時刻と数だけ。
- 提出版の handler は command 型に固定 (外部のレビュー (別の LLM による反証) 1 巡目を受けた)。
- デモの仕事 = README の誤字を直して commit。名乗りは JaH だけ。
- 作り手の手元の環境 (音声・手元の画面) との繋ぎは期間の外・この repo に入れない。

### 11.2 v1 と v1.1 で書き手が決めた事 (実装で覆してよい・覆したらこの file を直す)
- 釦 = 許可 (今回)・次から訊かない (対象と保存期間・モードの切り替えは別の字)・拒否 (定型 3)・固定の位置の釦 (口ごとの字と意味・§4.3)・端末で答える (96px 以上)。
- 板は選択式の問いだけ・自由記述と入力の直しは端末へ (候補の釦と最小の打鍵の道で補う・§4.3)。
- 板に出さない物 = ExitPlanMode・plan mode の権限・URL mode・描けない schema・`bypassPermissions`・`auto` へ移す suggestion・除外の表の道具。
- server の口・choice は番号だけ・`seq` で古い画面を断る・token の見出し・Host の照合・待ち 20 件 (§3.3)。→ 11/4 = choice は種と番号の object・MCP の問いの値は client が組む・`seq` は札の `view_seq` (§3.3)。
- 期限と数 (§3.4)・札の状態と終わり 5 つの排他 (§3.5)・優先の順 (§3.6)・`/resolve` は 1 対 1 の鍵がある時だけ (§3.7)。→ 11/4 = 鍵が無く `/resolve` は作らない = 終わりは 4 つ (§10.3)。
- 表示の世代で滞留と選択を解く・1 鍵の取り消し (§4.2)。
- 携帯は利用者の転送 (LAN に bind しない・§4.4)・計は押下と送った答えを分ける (§4.5)。→ 11/4 = 携帯の場面は提出版の外 (§1 の転換)。
- MCP の名 `blemma`・版 2025-11-25・const は "1"〜"6"・default なし (§2.5)。
- デモの冒頭は起動の引数・画面は板と端末だけ・退化は別の撮り (§9)。

### 11.3 決めない事
- 不成立の時の分岐 (§10.2) = 11/2 に確かめの結果で決める。
- 提出版の外に置いた物 (§5.6) = 提出の後。
- 視線の文字盤・作り手の手元の画面との繋ぎ = 期間の外。

### 11.4 規約で確定した物 (v1.2・10/31 に参加者ガイドを読み、11/1 に主催の回答を受けた)
1. **着手の時期** = code・成果物は期間中 (11/2 12:00 以後) に新たに作った物に限る。既存のプロジェクトの再利用・既存のコードは不可。期間中の自分の貢献が区別できないと失格。期間前の設計の文書 (code を含まない) は、主催の回答 (11/1・要旨) = repo は開始後に新規作成し、事前に準備した設計メモを追加して問題ない = 公開用に直して入れ、README と git の記録で期間前の物と明記する (6)。
2. **既存の物の持ち込み** = 開発の環境として以前からの自作の道具 (Claude Code の設定・skill・hooks) は使ってよい・成果物には含めない (主催の回答 11/1)。成果物は標準ライブラリだけ (§11.1) = 第三者の code の持ち込みはそもそも無い。
3. **提出物・提出先・締切** = プロジェクト概要 + 3 分のデモ動画のリンク (Google Drive・作り手の決め) + 公開 GitHub repo・**すべて日本語** (README の英語の要約の併記は作り手の方針で、主催の回答で確かめた事項ではない = 日本語が本体なら「すべて日本語」の文に反しないと読む・推測)。提出先 = CV プラットフォームのイベント頁「Submit Project」(フォームはキックオフ後に公開)。**締切 11/8 (日) 20:00 JST・期限以降の編集は認められない** (主催の回答 11/1) = 提出の後は repo を動かさない。
4. **OSS の条件** = repo は公開設定が必須。ライセンスの指定は無い = MIT のまま。
5. **チーム** = 1 人で出る (最大 2 名)。
6. **公開の形** (作り手の決め 10/31 + 主催の回答 11/1) = 11/2 に**新しい repo を新しい履歴で**作って出す (今の文書だけの private repo は公開に切り替えず別名で残す)。期間前の設計の文書は公開用に直して最初の commit に入れ、tag と README の節で「期間前の物 (日付つき)・code は 11/2 以後」と明記する。公開用に整える段取りと README の文 = 内部の作業メモ (11/1)。public 化は作り手の go (§8 の 11/2 の門)。

名乗るテーマ = テーマ 2 (作り手の決め 10/31・§1)。

---

## 12. 未確定の一覧 (外部のレビュー (別の LLM による反証) の振り分けを受けて 3 段に)

### 12.1 (i) 引用で確定 = 本文に移して未確定から外した物 (4 件)
- v1 の #1 = PermissionRequest の deny と `updatedPermissions` の契約 (欄の定義で確定・公式に無いのは完成した例だけ・§2.1)。
- v1 の #8 の matcher = `.*` で全部に当たる (正規表現の規則・§2.0・§2.3・§7.2)。
- v1 の #9 の Claude Code の側 = 2025-11-25 までの stdio の server に elicitation を宣言する (v2.1.287 以降・§2.5)。
- v1 の #13 の事実 = `requiresUserInteraction` の道具は allow で確認を飛ばせない (§2.1)。
- 別に、v1 の #11 (http 型・外部のレビュー (別の LLM による反証) の分類は (iii)) は未確定のまま提出版の外へ移した (§5.6)。

### 12.2 (ii) 実機で確かめる物 (初日・§10.1)

| # | 物 | 載せた所 | 確かめ |
|---|---|---|---|
| 1 | stdin の文字 (日本語・非 ASCII)。解けなければ無出力 | §2.0 | 1 |
| 2 | 待つ間の端末の見え方を口ごとに (#103115 は AskUserQuestion の報告・Edit・Bash・MCP への一般化と PreToolUse の質問の dialog は憶測)・`statusMessage` の見え方 | §2.0 | 1・2・3 |
| 3 | multiSelect の答えの形 (カンマを含む label も)。通らなければ複数選択は端末へ | §2.2 | 2 |
| 4 | `permissionDecisionReason` の欄名 (使えなくても deny の意味は同じ) | §2.2 | 2 |
| 5 | Elicitation の出力の `hookEventName` の要否 | §2.3 | 3 |
| 6 | MCP の stdio の枠 (改行区切り)・`.mcp.json` の形 (この裏取りの外・11/3 へ送らない) | §2.5・§7.2 | 3 |
| 7 | `--settings`・`--mcp-config` の旗 (この裏取りの外)。効かなければ隔離したデモ用の project の設定で | §7.2 | 5 |

### 12.3 (iii) 両方の挙動に分岐を用意した物

| # | 物 | 分岐 |
|---|---|---|
| 1 | 端末で先に答えた時に hook の process が止められるか | §3.7 の (a) / (b)・§10.2 |
| 2 | AskUserQuestion の道 (PreToolUse か PermissionRequest か) | §2.2 の経路の排他・§10.2 |
| 3 | 自作の server との版の取り決め・subagent の中からの問い | §2.5・§10.2 (ask_board を外す) |
| 4 | `requiresUserInteraction` の道具を板が見分けられるか | 除外の表 (§2.1) と「渡しました」の文 (§3.5) |
| 5 | 要求と 1 対 1 に結べる照合の鍵が在るか | §3.7・§10.2 (`/resolve` を作らない) |

- 残った未確定 = (ii) 7 件 + (iii) 5 件 = 12 件。README の助言に留めた物 (screen reader mode が質問の dialog と form に効くか・§4.3) は本文の札だけ。
- → 11/4: 11 件は初日の確かめで決まった (§10.3)。(iii) の 4 (`requiresUserInteraction` の道具を板が見分けられるか) は、その印の道具で試していない = 用意した分岐 (除外の表と「渡しました」の文) のまま。ほかに残る未確定は、完成版の検収の側 (§10.4)。

---

## 13. 出典
- Claude Code: https://code.claude.com/docs/en/hooks.md ・ https://code.claude.com/docs/en/hooks-guide.md ・ https://code.claude.com/docs/en/permissions.md ・ https://code.claude.com/docs/en/mcp.md ・ https://code.claude.com/docs/en/accessibility.md ・ https://code.claude.com/docs/en/cli-reference.md ・ https://code.claude.com/docs/en/channels-reference.md ・ https://code.claude.com/docs/en/remote-control.md
- Agent SDK: https://code.claude.com/docs/en/agent-sdk/user-input.md ・ https://code.claude.com/docs/en/agent-sdk/hooks.md ・ https://code.claude.com/docs/en/agent-sdk/permissions.md
- MCP: https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation.md ・ https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md ・ https://modelcontextprotocol.io/specification/2025-11-25/basic/transports (この裏取りの外)
- GitHub: https://github.com/anthropics/claude-code/releases.atom ・ issues #74256・#90498・#91216・#97656・#103115 (https://github.com/anthropics/claude-code/issues)
- 読んだ日と札の細目 = `docs/research_official_docs.md` §8。

---

## 14. 外部のレビュー (別の LLM による反証) 1 巡目 (2026-10-31) の対応表

| # | 所見 | 判定 | 本書の所 |
|---|---|---|---|
| 1 | HIGH = 「やめる」が作業の停止を意味しない口がある | 閉じた | §4.3 (口ごとの字と意味)・§5.4 (止められる範囲)・§2.1〜§2.3・§2.5 |
| 2 | HIGH = 通信の終了と回答の完了の混同・`/resolve` の契約・2 件目の 300 秒・期限と猶予の優先の順 | 閉じた | §3.3 (`/resolve`)・§3.4 (期限と数)・§3.5 (状態と終わり)・§3.6 (優先の順)・§3.7 (両方の挙動)・§10.2 |
| 3 | HIGH = 1 鍵のスイッチの取り消し・世代の解除・`--undo-ms` の上限 | 閉じた | §4.2・§4.3・§3.4 (0〜5,000 ms) |
| 4 | HIGH = 偽物の試験と完成版の実機の検収が繋がっていない | 閉じた | §7.3・§8 (11/3〜11/5 の検収) |
| 5 | HIGH = 初日の依存と不成立の時に削る範囲 | 閉じた | §8・§10 (確かめ 5 つ・削る表)・§5.6 (提出版の外)・§11.1 (command 型に固定) |
| 6 | MEDIUM = 「無出力 = 必ず既定の確認」の言い過ぎ | 閉じた | §1 の線 2・§2.0・§5.1・§5.3 |
| 7 | MEDIUM = 携帯と「外へ出さない」の境界 | 閉じた (本書) | §3.8・§4.4。README の 1 文は #11 の公開の門で直す |
| 8 | MEDIUM = 自由記述を端末へ戻すのは視線の利用者の縮小 | 閉じた | §1 (範囲)・§2.1 (次から訊かない の字・入力の直しは拡張先)・§4.3 (96px・候補の釦・最小の打鍵の道)・§6.2 |
| 9 | MEDIUM = 操作数の出どころとデモの手順が一致しない | 閉じた | §4.5・§2.2・§2.3 (押す数)・§9 (実測・退化は別の撮り・スイッチと携帯の実の操作) |
| 10 | LOW = `elicitation_url_dialog` の漏れ | 閉じた | §2.4・§7.2 |
| 11 | LOW = 公開前の資料の門 | 一部 (本書の側だけ) | §8 の 11/2 の門・§11.4 の 6。README と他の作業メモの直しは本書の外 = 公開の門で |
| — | §12 の 14 件の振り分け | 反映した | §12 ((i) 4 件を本文へ・#11 を提出版の外へ・残りは (ii) 7 件と (iii) 5 件) |

---

## 15. 11/4 の実装と転換の記録 (2026-11-04)

事実だけを書く (時刻は JST・commit の時刻と試験の本数は git の記録から数えた)。作り手は Claude Code で作り (一部は別のコーディングエージェントと並列)、外部のレビュー (別の LLM による反証) を 2 系統で受けた。

**その日の流れ** (おおよその順):
1. 午前 = 主催の資料 (録画 2 本・Discord・メール) を読み、審査の小項目と提出の欄を把握した。
2. 公開の門 = 新しい repo (この日は private) と新しい履歴。最初の commit は期間前の文書だけ (tag `pre-event-docs`)・続けて README の日付を repo を作った日に合わせた。
3. 初日の確かめ 5 つ = 5 つとも成立 (§10.3)。削る物は `/resolve` だけ (§10.2)。
4. 実装 (commit は 12:39〜14:27) = server + client + 頁 / hook 3 本 / MCP + notify / 起こし方の 1 行を、Claude Code の働き手 3 体と別のコーディングエージェントで並列に書いた。
5. 実装への外部のレビュー (別の LLM による反証) (読むだけ) 2 本:
   - 板の server と client の反証 = 判定 WARNING (MEDIUM 4) → 採否を決めて直した (期限・終わりの 1 回・記録を錠の外へ・既定の待ち)。一部の部品は所見が返らず、差分レビューへ回した。
   - 差分レビュー (repo を作った後から skill までの 21 file) = 判定 BLOCKED (BLOCKER 3・HIGH 1・MEDIUM 3)。7 件とも直した (code の 6 件は実物で再現してから直し、skill の 1 件は文を直した) = 自前の期限を過ぎた答えを受理していた (→ 総期限)・`python -I` で起こすと notify だけ exit 1・長く外れて戻った瞬間に滞留が押す・転送 (3xx) で token の見出しを別の宛先へ渡しうる・`/answer` の返りより先に取り消すと押しを二重に送る・`minItems` 0 の必須の配列に `[]` を返せない・skill が時間切れを「引数を直す」の行に入れていた。直しの後に、総期限の直しで標準の接続の処理を置き換えた時に落ちていた TCP_NODELAY を戻した。
6. 転換の決め = 既定の前面は同じ板の頁の小型の見え方 (§1)。転換の案への外部の反証 (判定 NEEDS_REVISION = 全面の転換には反対・同じ板を小窓でも使う形には条件つきで賛成) を受けた。起こし方の小窓は作った・頁の側の小型の見え方と Picture-in-Picture は未対応 (今後)。

**試験の本数** (commit ごとに数えた): server 95 → 頁 96 → 権限の口 142 → 質問の口 170 → server の直し 174 → MCP + notify 254 → MCP の問いの口 285 → 見る人の判定 292 → 差分レビューの直し (6 本の commit で再現の試験 +21)・起こし方 (+33) → **346**。

**commit の題** (公開の repo・古い順・この同期の前の 26 本):
- docs: ハッカソン開始前 (2026-10-14〜11-01) に書いた設計の文書と README (code はまだ無い)
- docs: README の日付と工程を、repo を作った日 (2026-11-04) に合わせる
- feat: hook 共通の client (hooks/_client.py) = 板との口と payload の契約
- feat: 板の server (board/server.py) と自動の試験 (tests/)
- docs: 設計 §10.3 = 初日の確かめ 5 つの結果 (2026-11-04・Claude Code v2.1.318)
- docs: 設計 §10.3 = statusMessage の観察を測った端末の大きさ (80×24) で限定する
- feat: 板の頁 (board/static/) = 大きな釦・入力の 5 通り・取り消し・計
- docs: 板の起こし方と手の確かめ (board/README.md・日本語 + 英語の要約)
- feat: 権限の口 (hooks/permission.py) と hook の自動の試験 (tests/test_hooks.py)
- feat: 質問の口 (hooks/ask.py) = AskUserQuestion を板の 1 枚で答える
- fix: 板の server に外の反証を当てる (期限・終わりの 1 回・記録を錠の外へ・既定の待ち)
- feat: 同梱の MCP server (mcp/blemma_mcp.py = 道具 ask_board) と待ちの合図の hook (hooks/notify.py) + 試験 80 本
- feat: MCP の問いの口 (hooks/elicitation.py) = MCP の form を板の釦で答える
- docs: 設計 §2.1〜§2.3 = hook 3 本の実装で確定した所を本文へ
- feat: 同梱の skill (skills/board/SKILL.md) = ask_board で 2〜6 択にして訊く作法 (日本語 + 英語の要約)
- feat: 見る人の判定 = 頁を閉じている時は札を受けない (端末が最長 5 分止まって見えない)
- docs: skill board = 時間切れの戻りは「止めて次の指示を待つ」(再質問を誘導しない・外のレビューの所見)
- fix: 共通の通信に総期限 = 自前の期限を過ぎた答えを受理しない (外のレビュー BLOCKER・線②)
- fix: notify.py を他の 3 本と同じ守りに = python -I でも無出力・exit 0 (外のレビュー BLOCKER・線②)
- feat: 起こし方の 1 行 (blemma.py) と設定の雛形 (examples/) + 試験 33 本
- fix: 共通の通信は転送 (3xx) を追わない = token の見出しを別の宛先へ渡さない (外のレビュー HIGH)
- fix: 滞留は長く外れて戻った瞬間に押さない = 入り直しの離脱と途切れたこまを見る (外のレビュー BLOCKER・線③)
- fix: 押しの数を要求ごとに切り離す = /answer の返りより先に取り消しても二重に送らない (外のレビュー MEDIUM)
- fix: MCP の問いの必須の配列で minItems 0 の空の答え [] を返せる = 欄の必須と最小の選択の数を分ける (外のレビュー MEDIUM)
- docs: 設計 §3.4 = 自前の期限は受信の完了まで効く総期限 (通信の無応答の時間とは別)
- fix: 共通の通信の接続に TCP_NODELAY を戻す (総期限の commit で標準の connect を置き換えた時に落ちていた)

この後に、この設計の同期の commit (節ごと) が続く。

---

## 16. 11/6 の検収と扇の記録 (2026-11-06)

実装の根拠は `git log c7cf6c9..409703d` と同じ範囲の code の差分。検収の集計と外部のレビュー (別の LLM による反証) の重要度は、作り手から共有された 11/6 の記録による。

以下の commit ごとの形は当時の記録。現在の動きは §4 と、本節末尾の同日の追記を参照する。

**実機の検収** = 出荷の code を実の **Claude Code v2.1.318** に挟み、**15 経路中 14 が PASS**。残る 1 件は、複数行の commit で「次から訊かない」が効かない件 = Claude Code の suggestion の形の問題。板は受けた suggestion を逐語で返す (§2.1)。**どの異常の経路でも勝手に続行した例は 0** (板なし・時限・見る頁なし・端末先着を含む)。

**検収で直した 4 件** (`c25857e`):

| # | 見つかった事 | 直した所 |
|---|---|---|
| 1 | 頁を閉じても long-poll が残り、見る頁なしと判るまで最大 55 秒 | `board/server.py` の `pending()` に相手の切断判定を渡し、検知したらすぐ返して見る人の数から外す。30 秒の判定は残す (§3.4) |
| 2 | 日本語の板に英語の合図が出る | `board_core.js` の `lightText()` で、日本語の既知の合図は定型の日本語を使い、英語だけの通知本文を添えない |
| 3 | 取り消された MCP の呼び出しに応答し、debug に `unknown message ID` が出る | `mcp/blemma_mcp.py` で取り消された `tools/call` への応答を止める (§2.5) |
| 4 | `--print-only` でも頁を開く | `blemma.py` で頁を開く処理を通さない (§3.2) |

**外部のレビュー (別の LLM による反証) 3 巡目** = HIGH 1・MEDIUM 3。4 件を次の通り直した (`a9a2463`)。

| # | 指摘 | 直し |
|---|---|---|
| 1 | ask_board の「断る」が無く、MCP の断る / 閉じるの両方を選べない | 「断る」を戻し、扇では羽根の外の補助の釦に置く。左の親骨の「この問い合わせを閉じる」と両立する |
| 2 | pointer が窓の外へ出ても本文送りが続く | `pointerleave` で位置と送りの端数を解き、`gazeScroll()` を止める |
| 3 | 古い別の会話の「完了」が新しい「作業中」を隠す | `priorityState()` で待ちを最優先し、作業中と完了は古さと更新の新しさで選ぶ |
| 4 | 実ブラウザの試験の画面の大きさが今の扇に合わない | `tests/browser_ohgi.cjs` の描画領域を 660×700 に揃える。描画ができず skip した結果は合格に数えない (§7.3) |

**扇の形の変化** (作り手の指摘を受けた順):

1. **円環** (`6126bec`) = 同じ板の小型の見え方として放射状の釦を作り、状態・設定・解説・常に手前を足した。
2. **折り扇** (`c25857e`) = 要・竹の骨・和紙の折り目・骨に沿う縦書き・朱の印へ。左の親骨は止める側、右の親骨は端末で答える側に固定した。既定の窓は 660×700。
3. **羽根は一文字** (`a9a2463`) = 羽根に全文を詰めず「一〜六」「止」「端」にした。
4. **内外 2 段** (同 commit) = 外の帯を押し、内の押せない帯で全文を読む。読む視線が他の羽根を押さないため、全文は羽根を離れても残す (§4.1)。画面の記録 = `docs/img/ohgi.png`。

**実物で見つけた入力の誤り** (`597fff2`): 最初は `hasFocus` を見ており、端末で作業したまま隅の窓を見ても滞留が進まなかった。`inputActive()` を「頁が見えていれば受ける」に直した。焦点の出入りの瞬間の数え直しは `blur` / `focus` の `releaseDwell()` が担う。本文の領域・字の重なり・配色も実物で直し、`scrollDirection` による本文送りを足した。実装の判断で入った制限を実物で見つけて直した記録であり、代用品だけの試験で見え方まで確かめたとはしない。

**同日の追記 = 現在の扇** (前掲の記録の後に変わった所・code が正本):

1. 既定はマウス。`dwell=0`・`scan=off`・`trail=off`。扇は 1 回目で選び、同じ羽根を 1.5 秒以内にもう 1 回押して決める。`click=single` で 1 回に戻せ、取り消しは常に 1 回 (§4.2)。
2. 窓は 640×720、扇が上・問いの和紙が下。横長では左に問い・右に扇。大きさの変更で扇・和紙・字が追従し、扇の背景のドラッグで窓が動く。字体は 3 種・文字の大きさは 5 段階・和紙も配色に追従する。右の親骨は「戻」、朱の印は無い (§4.1)。
3. Edit の短い変更を先頭の「変更」の行と本文の印で示す。長い本文は「▼ 続き」で 1 画面ずつ送り、読む間は動かさない。コピーの釦と C キーを足した。札がある間は通知の帯と縁を出さない (§4.1)。
4. Windows は今の窓を最前面に固定。他の OS は対応ブラウザの Document Picture-in-Picture を画面内に開く。位置は 4 隅、透過は Windows・`scale=1` の任意設定。待機中は扇が横向きに閉じて控え、app の窓だけ縮む。札が来れば元の大きさへ戻り、板との切断が 10 秒続けば閉じる (§4.4)。
5. 自動の試験は 414 passed・0 skipped (この追記の時点)。実ブラウザも走るが、窓の移動・縮小・コピーの試験には代用品がある。実の Windows API や PiP の開閉まで通したとはしない (§7.3)。

**同日の夜の直し** (外部のレビュー (別の LLM による反証) 2 系統の最終の所見を受けて・BLOCKER は無し):

1. **窓の名指し** (HIGH): 窓の名と種類が同じ窓を全部拾って同じ形で切っていた。別の port で起こした板や、同じ板の 2 枚目の窓を取り違える。窓の名に port の印を足し (既定の 8765 は名だけ)、ちょうど 1 枚の時だけ当てる形にした (§4.4)。
2. **字の倍率**: 窓の操作の応答が、窓に合わせて大きくした字を設定の倍率だけへ戻していた (1.82 → 1.3)。書き手を 1 か所にした (§4.4)。
3. **API の失敗と巨大な数**: `SetWindowPos`・`SetWindowRgn` などの戻り値を見て、失敗は頁へ返し、渡せなかった region は解放する。float に収まらない整数は壊れた形として断る (§4.4)。
4. **窓の大きさ**: 待機の大きさのまま読み直した窓を「元の大きさ」と覚えない。元の大きさを知らないまま札つきで始まった時は、今の窓のままにする (§4.1)。
5. **窓が勝手に閉じる条件**: 送信が 1 回届かなかっただけで「板が止まった」と見て、動いている板の窓を 10 秒後に閉じうる形だった。板の見張りが続けて 3 回落ちた時だけ閉じる (§4.1)。
6. **後始末**: 表示の世代が進んだら和紙の自動送りを手放す。釦を離した知らせを取りこぼしても、窓がポインタに貼り付かない (§4.1)。
7. **試験**: 2 回押しの反例を node と実ブラウザの両方に足した (1 回では決まらない・時間切れ・描き直しの後・別の羽根)。直しを 1 件ずつ外した 15 通りの木で、見張りの試験が落ちる事を確かめた。自動の試験は **438 passed・0 skipped** (§7.3)。

**同日の夜の直し・2 巡目** (実の窓の稽古・別の LLM による外部のレビューの全体の虫取り・4 つの持ち場 (頁・板・hook と MCP・起こし方と文書) の読むだけの反証役と検証役)。線 3 本に関わる物 = 2・3・4。

1. **実の窓でしか出ない 3 件** (自動の試験は通っていた): 待機の扇が右下の隅へ行かない (大きい窓のまま動かすと、画面の端で押し戻される → 縮める時は「小さくする → 動かす」)・切り抜きが外れたままになる (大きさを変えた直後の崩れた形と、届く順の入れ替わり → 寸法が揃ってから 1 つずつ送る)・頁を読み直すと窓が左上へ飛ぶ (読み込みの頭は窓の寸法が 0) (§4.1・§4.4)。
2. **押したままの滞留で答えが出る** (BLOCKER・外部のレビュー): 釦を押している間 (文字の選択・ドラッグ) は滞留を数えない (§4.2)。
3. **待機の小窓が札で開くと、置いたままの pointer の下に来た羽根が押される** (BLOCKER・反証役 → 検証役が確定): 守りが、開く前の窓の座標に掛かっていた。窓の大きさや位置が変わった直後 0.6 秒は滞留を数えず、前の窓での位置を捨てる (§4.2)。既定の構成 (滞留は切・窓は右下) では起きない。
4. **札が替わった直後の 1 押しが、新しい札の先頭 (許可) に当たる** (HIGH・スイッチと鍵): 板から替わった直後 0.4 秒は押しを数えず、走査は 1 こまぶん何も光らせない (§4.2)。
5. **掴んで運ぶたびに窓が大きくなる** (実の窓の稽古・表示倍率 125%・150%・175%): 位置を物理の画素で割り切れる所へ寄せる。札の途中で頁を読み直しても、広げた窓を縮めない (§4.1)。
6. **頁**: MCP の欄の説明が消える・返らない送信で固まる・読み上げや音声操作の押し (pointer の無い click) を捨てる・修飾キーつきのスイッチで押される・固定を外せない時に窓が増える・頁の拡大中に切り抜きがずれる・長い「次から訊かない」の保存期間が切れる・強制の配色で光が見えない・取り消せなかった時に黙る (§4.1・§4.2・§4.4)。
7. **板**: 対の無い surrogate で板全体が見えなくなる・遅い相手と接続の上限・鍵の置き場を今のユーザーだけに・答えの渡しの後始末 (閉じた hook へ渡さない・例外でも札を閉じる)・読めない形と面積 0 の形・静的の口は実在の file だけ・窓が 2 枚でも固定は外せる (§3.2・§3.3・§3.5・§4.4)。
8. **hook と MCP**: 板で描けない任意の欄を黙って落とさない (札に知らせる)・別の所の同じ名の module と取り違えない (`board/`・`hooks/` を通常の package に)・記録の符号・MCP の深い入れ子と長い行で落ちない・`initialize` で使い方を返す (同梱の skill は、置いただけでは読まれなかった) (§2.3・§2.5・§7.1)。
9. **起こし方**: claude が無い時は板も窓も開かずに止まる・板は最後の使い手が終わる時に止まる (名簿)・同時に起こしても板が残らない・1 日を超えて動いている板も使い回す・止める口 `--stop`・版の確かめ・設定の誤りの名指し・子の process は `-I`・見る頁が在る板に窓を増やさない (§3.2)。
10. **退けた所見**: 「Windows で板を止めた直後に起こし直すと失敗する (排他の bind と TIME_WAIT)」は、反証役が HIGH とし、検証役も記録と公式の文書から「確定」とした。実測では、接続を閉じた後・待ちの接続を張ったまま・実のブラウザの頁と hook 役が繋がったまま (port に TIME_WAIT が 9〜13 本残る) の 3 通りとも、直後の起こし直しが通った。排他の旗は、ほかのアプリの重ね取りから板の port を守るので残した。
11. **試験の側の穴**: 実ブラウザの試験の「開き直し」が、同じ住所へ移るだけで読み直しになっていなかった (「読み直しても…」と名乗る試験 2 つが、頁の中の状態を持ち越したまま通っていた)。本当の読み直しにし、読み直した事を印で確かめる行を足した。
12. **確かめ方**: 所見は実測で採否を決め、直しは 1 件ずつ外した写しの木で見張りの試験が落ちる事を確かめた (この巡で計 97 通り)。実の窓の稽古は全項目が通った。自動の試験は **522 passed・0 skipped** (§7.3)。知っていて残した制限 = §5.7。

**同日の夜の直し・3 巡目** (2 巡目の差分だけを対象にした、別の LLM による外部のレビュー = HIGH 1・MEDIUM 3。4 件とも採った)。所見の手元の確かめは node と代用品による物で、実ブラウザ・実の process ではない。線 3 本に関わる物 = 1。

1. **替わった直後の click が、2 回押しの 1 回目として残る** (HIGH): 2 巡目の「板から替わった直後 0.4 秒は押しを数えない」守りが、扇の 2 回押しの「選ぶ」処理より後ろに居た。替わって 0.1 秒後と 0.5 秒後の click で許可が送られる = 前の札へ向けた 2 回押しの 2 回目が新しい札の羽根を選び、見てから押す click は 1 回で決まる。選ぶ処理の前で同じ線を引いた (§4.2)。2 巡目の試験は `press()` を直に呼んでいて、click の道を通っていなかった。
2. **短い取り消しの猶予が、押しを数えない間に埋まる** (MEDIUM): `--undo-ms 300` の板では、取り消しの画面にも 0.4 秒の「数えない間」が掛かり、猶予が終わるまで 1 度も取り消せなかった。取り消しだけは、猶予の半分まで (0.8 秒より短い猶予の時) にした (§4.2)。click の取り消しが 2 回押しに巻き込まれない事も試験で押さえた。
3. **`--stop` を挟むと、誰も使わない板が残る** (MEDIUM): 回 A が走っている間に `--stop` → 別の回 B が新しい板を起こして先に終わる (A が居るので残す) → A は自分が最初に使った板しか見ないので、新しい板が残った。最後の使い手は、今の run.json の板も同じ照合 (印・pid と token・token つきの応答) で止める。手で起こした板 (印なし) は止めない (§3.2)。
4. **取り消せた時にも「答えは渡りました」と出る** (MEDIUM): 2 枚の頁から続けて取り消すと、後の頁は 409 を受けて「間に合いませんでした (答えは渡りました)」と出したが、答えは渡っていない (先の頁が取り消して、札は選ぶ所へ戻っている)。板が、同じ札がまだ頭に居る時の 409 に今の状態を添え、頁は `shown` の時には何も言わず取り直した表示に任せる (§3.3)。
5. **確かめ方**: 直しを 1 件ずつ外した写しの木 11 通りで、足した試験が落ちる事を確かめた (2 巡目からの累計 108 通り)。自動の試験は **528 passed・0 skipped** (§7.3)。

**同日の夜の直し・4 巡目** (2 巡目の差分の、頁の入力と窓の守りだけを深く読む反証役 = 読むだけ。所見の確かめは node の模型で、実ブラウザは起こしていない → 重い 3 件は、こちらで本物の Chrome (headless) に同じ筋書きを流して、直す前の木で再現してから採った)。線 3 本に関わる物 = 1・2・3。

1. **走査の光が列を送ると、置いたままの pointer の下に来た釦が滞留で押される** (BLOCKER 相当・2 巡目の「光を見える所へ送る」が持ち込んだ・滞留と走査を両方入れた時だけ): 12 択の問いで、誰も押していないのに 6 番目の選択肢が送られた。頁や列が送られた時は、窓が動いた時と同じ守りを掛ける (落ち着くまで滞留を数えず、その後に pointer の下に居た釦は入り直すまで数えない)。ホイールと「見つめて本文を送る」も同じ守りに入る (§4.2)。
2. **鍵で配色の釦を 2 回押すと、2 回目が「許可」に当たる** (HIGH・前から在った): 表示が替わると先頭の釦へ焦点を移す作りが、人が置いた焦点まで奪っていた。焦点を置くのは、焦点がどこにも無い時と、描き直しで消えた釦に在った時だけにした (§4.2)。
3. **スイッチの 2 打目が、札の中で進んだ先の先頭に当たる** (MEDIUM・前から在った): 「拒否 …」→「前の画面へ」の 0.05 秒後の 2 打目が、戻った画面の許可に当たった。スイッチの時だけ、札の中の進みにも 0.4 秒と走査の静かな 1 こまを置く。鍵で続けて打つ 2 打目は捨てない (§4.2)。
4. **小さい物**: 押した・離したその場で滞留を解く (1 こまの内の速い click)・設定で窓を隅へ動かした時も「窓が動いた」と扱う・板が落ちている間に見張りが 2 本並ばない・0.4 秒より短い滞留は替わった直後の数え始めを遅らせる (最初は押しを捨てる形にして、既存の実ブラウザの試験が止まった = 捨てた釦は入り直すまで数えなくなる。数え始めを遅らせる形に直した)・形の送信が例外で終わっても次を送れる・PiP へ移った時の印の後始末・§2.0 の古い括弧。
5. **試験の穴** (直しを外しても試験が通った所): 鍵が起こした click を数えない守り (試験が時刻を手で置いていた → `keydown` / `keyup` の聞き手から入れる)・窓が落ち着いた後の最初の pointer・走査の静かな間の持ち越し 2 か所・札が替わった時の送信の印 (板の写しを当てる所から入れる)。**守りを足した時は、入力の入口ごとに、その入口から入る試験を書く**。
6. **視線入力のソフトと同じ形の入力での確かめ** (自動の試験の外・新しく足した): OS のカーソルが視線に付いて 0.01 秒ごとに動き続け (ゆっくり漂う + 細かい揺れ)、クリックは物理スイッチの普通の左クリック、という入力の形を、本物の Chrome (headless) の扇に流した。見続けると約 1.08 秒で押される・札が替わっても見たままの羽根は入り直すまで押されない・荒い揺れ・羽根の間を走り続ける視線・境目・スイッチ 1 回では決まらない・押した後に取り消しが押されない・1 回押しの設定、の 8 通りと、上の 1〜3 の再現 3 通り = 直した木で 11 通りとも通った。実の視線入力の機器は通していない。 11/7 夜 (焦点の直後の守りを入れた後・02ab139): 「スイッチの 2 打目」の通りだけ、窓に焦点を渡さずに開いてすぐ打つ形だと、焦点の直後 0.4 秒は鍵とスイッチを数えない守り (§4.2) が最初の押しを捨てて落ちた (main では通り、落ち始めた commit を二分で特定)。人は焦点の無い窓にスイッチを打てないので守りは設計のままとし、稽古に「先に窓へ焦点を渡してから光を待つ」前提を足して 11 通りとも通った。
7. **確かめ方**: 直しを 1 件ずつ外した写しの木 19 通りで、足した試験が落ちる事を確かめた (2 巡目からの累計 127 通り)。自動の試験は **539 passed・0 skipped** (§7.3)。

**翌日 (11/7) の直し・5 巡目** (3 巡目と 4 巡目の直しの差分 `7e688dc..4df559b` を、読むだけの 3 つの視点 (頁の入力・板と起こし方・試験と文書) が調べ、重い 6 件は所見ごとの独立の反証役 (Claude Code の subagent) が自前の模型で確かめた = 全部で 9 体・21 件。重さは出した役の見立てで HIGH 3・MEDIUM 6・LOW 12。同じ件を頁と板の側から見た物・光と押しの側から見た物の 2 組が重なる)。所見の確かめは node の模型による物で、実ブラウザ・実の process ではない (頁の入力の所見は全部、7 の代用品の試験が直す前の木で落ちる = 再現する事を確かめた)。線 3 本に関わる物 = 1〜3。

1. **札の中の進みの 2 打目が許可に当たる** (HIGH・前から在った): 「前の画面へ」の上で Enter / Space が 2 回入ると、2 打目が、戻った画面の先頭へ移った焦点で「許可」を送った。2 問の札の最後の選択肢の Enter×2 は、確かめの画面を見ないまま「送る」を押した。大きな板の「前の画面へ」のダブルクリックも同じ筋。位置や焦点で行き先が決まる押しで札の中を進めた時も 0.4 秒は数えず (数字の鍵と滞留は除く = 続けて打てる)、戻った後の鍵の焦点は来た元の「拒否 …」へ置く (§4.2)。
2. **頁が動かす鍵の焦点が許可へ移る** (HIGH・前から在った / MEDIUM と LOW・4 巡目が持ち込んだ): 取り消して選ぶ画面へ戻った時と、「常に手前」で PiP の窓へ移る・戻る時に、焦点が先頭の「許可」へ移り、次の Enter が許可を送った (拒否を送って取り消した人の答えが許可に変わる筋を含む)。札が答えずに直に替わると、4 巡目の焦点の付け直しが、次の札の同じ位置の「次から訊かない」へ焦点を持ち越した (遅れた Enter が恒久の許可を送る)。同じ釦への付け直しは同じ画面の描き直しだけにし、取り消した後はどこにも置かず、窓を移る時は、鍵で使っていれば元の釦へ戻す。この後に消える釦 (「▼ 続き」・取り消しの釦) に在った焦点は「在る」と数えない (§4.2)。付け直さなかった焦点と、消える釦に在った焦点の行き先 (先頭へ置く) は、9 の①②で改めた。
3. **入り直さずに滞留で押される** (HIGH・MEDIUM・前から在った): 設定の板を閉じた直後、置いたままの pointer の下に居た釦が約 1 秒で押された (板を開いている間に替わった、見ていない札の許可を含む)。取り消しの枠が釦に重なる配置では、枠が消えた下に出た次の札の釦と、枠が出た所の取り消しが、入り直さずに押された。閉じた時に守る釦と pointer の下の釦を揃え、閉じた後の最初の pointer も守る。描く → 取り消しの枠と「▼ 続き」の出し入れ → 世代を進める、の順にした (§4.2)。
4. **守りの効きすぎ** (MEDIUM・LOW・4 巡目が持ち込んだ): 本文の枠や和紙を送っただけで、次に見た釦が入り直すまで押せなかった。走査の光が進むたびに送りの守りが掛かり、滞留と走査を両方入れた列で最初の滞留が捨てられた。押せる的を含む送りと、光が実際に列を送った時だけ守る (§4.2)。4 巡目の 1 の「ホイールと見つめて本文を送るも同じ守りに入る」は、この形に狭めた。
5. **取り消し** (MEDIUM・LOW): 期限切れ・切断で終わった札への取り消しの 409 に終わり方が付かず、頁は答えが渡っていない時も「答えは渡りました」と出した。板は判定の前に接続の終了と期限を確かめ、終わった札には終わり方を添える。頁は、答えが渡った時 (answered・released) に「間に合いませんでした (答えは渡りました)」、同じ札がまだ頭に居て渡している途中 (deciding) の時に「間に合いませんでした (答えを渡している所です)」と言い分け、それ以外では言わない (3 巡目の形は、渡っていない時も「渡りました」と出していた) (§3.3)。猶予の短い板で、取り消しは猶予の半分から押せるのに、走査の光は 0.4 秒まで当たらなかった = 光らせる条件を押しと同じ間に揃えた (§4.2)。
6. **小さい物**: 設定の板の「閉じる」が Enter / Space で閉じなかった (焦点が「閉じる」に在る時だけ閉じる)。bumpGen の注釈が古かった・README の「0.4 秒は数えない」に短い猶予の取り消しの例外が無かった・設計の「押せる時間が必ず残る」は言い過ぎだった (§4.2 を今の作りに合う言い方へ)。
7. **試験の穴と確かめ方**: 4 巡目の直しの行のうち、外しても試験が通った 8 行は、5 行に見張りの試験を足し (離した時と、押しが取り消された時に滞留を解く行・scroll の聞き手の capture・PiP へ移った時の印の後始末・形の送信の例外の枝)、3 行を下の 8 に分けた。送信の印の試験は、描画の途中で止まっていた代用品を直し、最後まで描けた事も確かめる。焦点の試験は関数を直に呼んでいて、描き直しでの付け直しを通っていなかった = 頁を init() ごと回す DOM の代用品 (`tests/page_dom.cjs`) を足し、板の写し・鍵・click・pointer の入口から入れる。代用品が置いたブラウザの順 (焦点の在る釦を外す・付け替える・その釦自身を隠すと、その場で焦点が外れる / 入れ物を隠す・押せなくすると次のこままで残る / 要素の送りの知らせは capture の聞き手にだけ届く) は、実の Chromium 156 で測った。実ブラウザの筋書きに 2 本 (「前の画面へ」の Enter×2・広い窓の 2 列の一覧をホイールで送る筋) を足した。反例の 19 本 (新しく足した 15 本と、書き換えた既存の 4 本) は、直す前の木 (`4df559b`) で落ちる事を確かめた (足した残りの 5 本は、前から在る行の見張りと逆向きの試験 = 直す前の木でも通る)。直しを 1 件ずつ外した写しの木 41 通りで、名指しした試験が落ちる事を確かめた (2 巡目からの累計 168 通り)。うち 1 通り (設定の板を閉じた時に滞留を解く行) は、最初の試験では外しても通った = 閉じた 0.5 秒後に入れた pointer の知らせが、別の守り (閉じた後の最初の pointer) を動かして同じ結果にしていた。閉じた後に pointer が一度も動かない筋を足し、外すと落ちる事を確かめた。この時点の自動の試験は 559 passed・0 skipped (9 の直しの後の数は 9 の末尾と §7.3)。
8. **念のための守り (試験なし)** = ほかの守りと重なる行。外しても今の試験は通る (外して確かめた)。消さずに残す。送られたその場で滞留を解く (`scrolled()` の `releaseDwell()` = 次のこまの、落ち着くまでの枝が同じ事をする) / 押したその場で滞留を解く (`pointerdown` の `releaseDwell()` = 押している間のこまの枝と、離した時の行が同じ事をする) / 文書の根 (`documentElement`) を「人が置いた焦点」の外にする (`body` の在る文書では根に焦点が来ない) / 設定の板を閉じた時に `S.over` を pointer の下の釦へ揃える (閉じた後の最初の pointer の守りが同じ筋を塞ぐ) / 札の中の進みでも、取り消しの枠の出し入れを世代より先にする (札の中の進みでは取り消しの枠が動かない)。9 の組み替えの後に念のための行へ移した物 = PiP へ移る・戻る時に `leaveFocus` で「置かない」と伝える 2 か所 (消えた焦点の決まりが同じ結果を出す)。取り消して戻った時の `leaveFocus` は、数字 1 つで答えた人 (焦点が一度も来ていない) の組の試験が見張る。
9. **実装の後の見直しと、外の目で直した物** (11/7 未明〜朝)。
   - **自分の見直しで 2 点**: 最初の直しは、取り消しが猶予の終わり際に断られて答えを渡している途中 (deciding) だった時に黙る形だった = 3 巡目の「取り消せなかった時に黙らない」を、いちばん多い間に合わない場面で外していた (待ちの札が続く時は、終わりの文も出ない)。その時も「取り消しは間に合いませんでした (答えを渡している所です)」と知らせる形にした。もう 1 つは、「常に手前」で窓を移る時に焦点を元の釦へ戻すのを、鍵で使っている時だけにした (マウスで押した時も戻すと、焦点の在る間、上の釦の帯が出たままになる)。
   - **外部のレビュー (別の LLM による反証) に 5 巡目の差分を渡して 2 件** (どちらも前から在った): ほかの頁が取り消して、この頁が途中 (deciding) の写しを受けないまま選ぶ画面へ戻った時は、取り消しと見分けられず、焦点が前に置いていた「次から訊かない」へ付け直された (「止」を送って取り消された人の次の Enter が、恒久の許可を送る) = 表示の `seq` だけが進んだ同じ札も、取り消しとして扱う。PiP の窓から戻った時は、扇の取り消しの枠が描き直しで付け替えられ、取り消しに置いた焦点が外れた = 描き直しの後にも焦点を戻す。
   - **読むだけの反証役 (Claude Code の subagent・この作業の文脈を持たない) に同じ差分を渡して 5 件**:
     - ① **札が答え無しで替わると、鍵の焦点が次の札の許可へ移る** (HIGH・**5 巡目が持ち込んだ後戻り**): 2 の直し (同じ釦への付け直しを、同じ画面の描き直しだけにする) は、付け直さなかった焦点を「先頭へ置く」既定の決まりに任せた。その結果、焦点を前の札の釦 (拒否 …・止・戻・断る) に置いたまま札が替わると、焦点が次の札の先頭へ移り、前の札へ向けた 0.6 秒遅れの Enter が、権限の許可・質問の 1 番目の答え・MCP の受け入れを送った (反証役が実の headless の Chrome で測って、12 通り中 12 通り)。4 巡目の形 (同じ位置の「次から訊かない」へ持ち越す) を塞いで、別の許可の筋を開けていた。
     - ② **押しそびれた「取り消す」の焦点が、次の札の許可へ移る** (MEDIUM・2 の直しの裏側): 2 は「この後に消える釦に在った焦点は、在ると数えない (= 先頭へ置く)」としていた。取り消しに焦点を置いたまま猶予が切れると、取り消しのつもりの遅れた Enter が、次の札の許可を送った。
     - ③④ **文書** (LOW): README の「Enter・クリック・スイッチで進めた直後」は Space と触る入力が抜け、「遅れた 1 押しが当たらない」は 0.4 秒の内だけの話だった。板の README の「常に手前」の焦点は、鍵で使っている時だけ戻す事を書いていなかった。
     - ⑤ **数字の直後の癖の Enter が、見ていない次の設問を選ぶ** (LOW・1 の残り): 数字の鍵 (名指し) で次の設問へ進めた直後の Enter が、焦点の移った先頭の選択肢を選んで、確かめの画面へ進んだ。名指しや滞留で進めた直後の 0.4 秒は、位置や焦点で行き先が決まる押しだけを数えない (名指しの鍵は続けて打てる・§4.2)。
   - **①②の最初の直し = 頁が焦点を消す場面ごとに印を立てる形**。これを外部のレビューにもう 1 度渡して 8 件 (読みによる所見・HIGH 4・MEDIUM 3・LOW 1): ❶ 同じ札の表示の `seq` だけが進んだ時 (ほかの頁の取り消しを途中の写し無しで受けた・取り消しと答え直しをまとめて受けた) に、印が立たない。❷ 答えを送った時点で「自分で答えた」と数えていた = 時間切れと同時に押した答えが 409 で断られても、その返りより先に来た次の札の先頭へ焦点を置いた。❸ 印を立てない所でも焦点が消える (複数選択の「次へ」が印の変化で押せなくなる・待機の小窓が上の釦を CSS で隠す)。❹ 数えなかった押し (押せない釦の番号) でも印が解ける。❺ 扇の 1 回目の click と読み上げソフトの「押す」では印が解けず、進んだ先で Enter が効かない。❻ 数えない間に PiP の窓へ移ると、移った先の文書に `settling` の印が無い (前から在った)。❼ 足した試験の 1 本が、名乗る枝を通っていなかった (2 問の札は扇にならない)。❽ README の「数字の直後に数えない押し」の言い方が狭い。
   - **❶❸❹❺は、場面を並べる作りそのものの数え漏れ** = 「焦点が来た事をブラウザの知らせ (`focusin`) で覚え、人の自分の押し (答える・札の中を進める・設定を閉じる) で使われないまま消えていたら、先頭へ置かない」作りへ組み替えた (§4.2)。頁のどこが焦点を消しても同じに効き、戻るきっかけも「自分で答えた・札の中を進めた」の 1 つになる。❷は、次の巡で作りを替えた (下)。❻は、印を今の文書へいつも揃える。❼は試験を権限の札 (拒否 … → 理由) で書き直し、❽は文を直した。
   - **組み替えた形を、外部のレビューにもう 1 度渡して 5 件** (読みによる所見・HIGH 3・MEDIUM 2): 【A】板が添える終わり方だけでは、通ったのが自分の答えかどうか分からない (同じ瞬間にほかの頁の答えが先に通ると、断りの返りが届く前に、次の札の許可へ置いた焦点で Enter が打てる)。【B】窓が背面に居る間は、頁が焦点を置いても、ブラウザが焦点の知らせを送らない (公開の実装からの推測)。【C】設定の板を閉じると、板の外で消えた焦点の事まで済んだ事になる。【D】遅れて届いた断りの返りが、人が置き直した焦点まで外す。【E】古い試験の 1 本が、焦点の知らせの聞き手を通らないまま、前の決まりを期待して通っていた。
   - **【A】【D】= 頁の側の推し量りをやめた**。頁は答えに名札 (頁ごとの乱数) を添え、板は渡った答えの名札を写しに添える (§3.3)。頁は、名札が自分の物の時だけ「この頁の人の答え」と読む = 板の返りと写しの順に左右されず、後から焦点を外す処理も要らない。【B】= 頁が置いた焦点は、知らせを待たずに覚える。【C】= 閉じる操作が使うのは、板の中に在る焦点だけ。【E】= その試験を今の決まりに書き直した。
   - **名札の形を、外部のレビューにもう 1 度渡して 3 件** (読みによる所見・HIGH 2・MEDIUM 1): 【F】自分の答えで猶予に入った時に「使われた」と数えると、その答えをほかの頁が取り消して答え直し、途中の写しを受け損ねた時に、数えたまま残る。【G】板の写しが届くのが遅れた間に、人が置き直した焦点まで、送った答えで使われた事になる。【H】試験の代用品が、猶予の写しの名札を補えていなかった (自分の答えの筋が、ほかの頁の答えとして走る見込み)。
   - **【F】【G】= 数える所を 1 か所にした**。「この頁の人の答えが渡って、札が終わった」時だけ数え、数えるのは押した時に在った焦点だけにする (答えを送る時に、その時までに来た焦点の数を控える)。猶予に入っただけでは数えないので、取り消された答えを戻す仕掛けが要らない。板が添える名札も「直前に終わった札」の 1 か所だけになった。【H】= 代用品の自動の補いをやめ、筋書きが「どの答えが渡ったか」を自分で書く。
   - **その形を外部のレビューにもう 1 度渡して 3 件** (読みによる所見・HIGH 1・MEDIUM 1・LOW 1): 【I】返りを失った 1 回目の答えが板に通っていて、人が焦点を置き直して同じ札へ送り直した時、頁の控えが 1 つだと、渡った 1 回目を 2 回目の控えと照合する (置き直した焦点が使われた事になる)。【J】窓へ戻った時の焦点の再通知で、押した時の焦点の数が進む (公開の実装からの推測・この機械では未確認・起きても置かない側に倒れる)。【K】代用品と試験の説明に前の形が残っていた。
   - **【I】= 名札を送信ごとにした** (頁ごとの乱数 + 送信の番号・送信ごとに押した時の焦点を控える)。板は渡った答えの名札を添えるので、頁は渡った方の控えで照合する。【K】は文を直した。
   - **その形を外部のレビューにもう 1 度渡して、判定 WARNING** (許可が送られる穴は、読みでは見つからない・4 件): 【L】答えを送った後に PiP の窓へ移ると、同じ釦への付け直しでも焦点の数が進み、置き直していない人の Enter の流れが切れる (【J】と同じ型・安全な側)。【M】Enter・click で札の中を進めた直後に間を置く行は、念のための行ではない (直後の数字を捨てるのはこの行だけ = 外すと、戻った画面の許可を数字が送る。試験が見張っていなかった)。【N】取り消しの試験の数字の組は、焦点が一度も来ない筋を通っていなかった。【O】文の参照先が無かった。
   - **【J】【L】= 焦点の数は、行き先の釦が替わった時だけ進める**。【M】= 試験を足し、念のための行から外した。【N】= 数字 1 つで答える組を足し、焦点が一度も来ていない事を先に確かめる。【O】= 文を直した。
   - **直しの中で、自分で見つけた 4 点**: (a) 守りを「札が替わる時に焦点が在る」だけで掛けると、猶予が 0 の板や、猶予の写しを受け損ねた頁で、自分で答えた札から次の札へ直に替わった時にも掛かり、Enter で札を次々に答えるふだんの流れが切れる = 自分の押しで答えた時に、焦点は使われた事にする。(b) ⑤の間に頁の `settling` の印が付かず、印だけを見て押す実ブラウザの筋書きの Enter が黙って捨てられた = その間も印を付ける。(c) 取り消しの押しは、⑤の間に入れない (猶予の短い板で、取り消しの押せる間が削られる)。(d) ⑤の間の click は、扇の 2 回押しの 1 回目にも数えない (数えると、0.4 秒をまたぐ 2 回の click が、見ていない画面の羽根を決める = 3 巡目の 1 と同じ筋)。
   - **確かめ**: 頁の試験は 28 本を足し、2 本は期待を逆にして書き直した (`test_board_js.py` は 117 件)。板の芯の試験に名札の 1 本 (付け方・取り消しと答え直し・「端末で答える」・形の違う名札・渡らずに終わった札・hook への返りと記録に載らない事)・HTTP の口の試験に名札の確かめ。実ブラウザの筋書きに 5 本 (Enter で札を次々に答える流れ・ほかの頁が答えた札の後・押しそびれた取り消し・取り消しの枠の付け替え・待機で隠れる上の釦)。直しを 1 件ずつ外した写しの木 78 通りで、名指しした試験が落ちる (2 巡目からの累計 205 通り)。うち実ブラウザの筋書きを名指しした 5 通りは、実ブラウザの試験だけを回しても落ちる (頁の代用品とは別に、実の DOM と HTTP で見張っている)。名札を見ない形と、送り直しの取り違えは、頁と板の試験が見張る (実ブラウザで同じ順を作るには、板の返りを失わせる仕掛けが要る)。念のための行は 7 行 (8)。直す前の木で、今の頁と板の芯の試験を回すと、`f3346a1` (外の目の前) では 24 本・`4df559b` (5 巡目の前) では 46 本が落ちる。自動の試験は **588 passed・0 skipped** (§7.3・Python 3.13 と 3.10)。

**同日 (11/7) の午後・公開の点検** (主催の資料「Claude Code で作ったアプリを安全に公開する」の確かめの表 CHECK 0〜5 = README・公開の file の秘密・git の履歴・GitHub の設定・code の弱点・動かして確かめる、を 6 つの持ち場の読むだけの役で当て、重い所見は独立の検証役が実物で確かめた。秘密の形は全履歴で 0 件・作者と commit の文は JaH と GitHub の noreply だけ・Claude-Session の行も 0)。

10. **公開の点検で直した物と残した物**。
   - ① **「次から訊かない」と「このフォルダも許す」の文が、見えない字 (書字方向・幅ゼロ) を素のまま描く** (頁・検証 LOW): 本文は ⟨U+XXXX⟩ に直してあるのに、恒久の許可を書く釦の文 (道具の入力から来る規則の文と路) だけ守りが無かった = 釦の文も同じ形で見せる (`visibleText`)。hook の側では直さない (Claude Code へ逐語で返す物に、表示用の鍵を足さない)。 質問と MCP の札の字 (head・text・question・選択肢・omitted・出どころ) も同じ形で見せる (11/7 夜・1 巡目 #23)。
   - ② **数字の鍵が、恒久の許可を 1 回で送る** (頁・検証 LOW・実の端末と並べての再現はまだ): 扇に鍵の焦点が在るまま端末を見て数字を打つと、扇の番号で決まり、選択肢の並びしだいで「3」が 2 つ目の「次から訊かない」になった (模型で確かめた)。作り手の裁定で、数字で「次から訊かない」を押す時だけ、同じ数字を 1.5 秒の内にもう 1 回押して決める (§4.2)。1 回目は選ぶだけ (選んだ印・上の帯の案内)。今回の許可・拒否・止める・端末で答えるは 1 回のまま。押しを数えない間の数字は、選ぶ 1 回目にも数えない。
   - ③ **窓が鍵の焦点を得た瞬間に、走査の光が「止」から「許可」へ跳ぶ** (頁・LOW): その瞬間のスイッチの 1 押しや、別の窓へ向けて打った数字が許可に当たった (模型で再現)。表示が替わった時と同じ守り = 走査は焦点から 1 こまぶん光らせない・鍵とスイッチは 0.4 秒数えない・その間は頁の印 (§4.2)。直しの後の実ブラウザの試験で、札の来る前に焦点が来ると印が外れない (表示の世代の時刻が未定義で、外す条件が成り立たない) 自分の後戻りを見つけて直した。実ブラウザの筋書きの 1 本は、0.25 秒ごとの窓の大きさの見直しと click の競りに乗っていた = 見直しを待ってから押す順に直した。
   - ④ **信頼していないフォルダーで起こすと、そこに置かれた `claude.cmd`・`chrome.cmd` が Claude Code の信頼の確認より前に走る** (起こし方・検証 MEDIUM): Windows の `shutil.which` は cwd を先に探す (Python 3.12 以降も、環境変数 `NoDefaultCurrentDirectoryInExePath` が無ければ) = PATH の絶対の dir だけを探す形にした (Windows は PATHEXT の拡張子だけ・拡張子の無い file は拾わない)。3.10.6・3.12.11・3.13.17 で、置いた物を拾わず実の claude と Chrome を見つける事を確かめた。
   - ⑤ **板が鍵の確かめの前に本文の JSON を解く** (板・LOW): 鍵の無い相手の深い入れ子で `RecursionError` が捕まらず、handler の thread が落ちた (Python 3.10.6 までは、巨大な数 1 本で板が数秒止まった) = 本文は鍵の前に読み切り (読み残すと Windows は RST を返す)、解くのは鍵の後・深い入れ子も 400 で断る。
   - ⑥ **`--print-only` の PowerShell の 1 行が、全角の二重引用符を逃がさない** (起こし方・LOW): 引数の中の U+201C・U+201D・U+201E で文字列が終わり、続きが命令になった = その 3 字の前にもバッククォートを置く。試験は Windows で、PowerShell に実際に 1 行を渡して、引数が子へそのまま届き、続きが走らない事を見る。
   - ⑦ **残した物** = §5.7 の表に足した (同じユーザーのプログラムは token を読める・滴らせる接続・`--stop` の pid・`--allow-host`・大きな板の住所の token・「常に手前」の窓探し)。ほかに、本文を切った札にも「許可 (今回)」が出るのは §2.1 の選択のまま (見出しに「先頭 n 字・続きは端末で」と出る)。
   - ⑧ **板が落ちて起動の記録が残った後に、別の利用者の process が同じ port を取ると、hook はそれを板と見なす** (起こし方と client・検証 LOW): 札の本文をその相手へ渡し、相手が「許可」と返せば、人が押さないまま許可を返す (写しで再現)。前提は、板が後始末なしに消えた事と、同じ PC の別の利用者 (か鍵の file を読めない process) がその port を先に取る事 (同じユーザーの process は元から鍵を読める)。§3.2 の「落ちて残っても、接続が断られて無出力になるだけ」は、この前提の時には成り立たない。作り手の裁定 (#220 = B) で直さず、§3.2 と §5.7 と README に限界として書いた (直すなら、板の返りごとに鍵から作る証明を付け、hook と起こし方が確かめる形)。
   - ⑨ **repo と公開の外の物** (code の外): `.gitignore` に `.env.*`・`*.pem`・`*.key`・`tests/.tmp-*/` を足した。README の動画の行を日本語と英語の両方に置いた (提出の時に URL へ替える)。GitHub の repo に、作り手の裁定で、秘密の走査と push の押し返し・main の規則 (削除と force push を止める・早送りの push は通る)・tag `pre-event-docs` の規則 (削除と付け替えを止める)・内々の脆弱性の報告を入れ、About の説明と topics を README に揃えた。公開済みの履歴に残る作り手の屋号は直さない (作り手の裁定・消すには公開済みの履歴を書き換え、tag の証拠が壊れる) = 門の語の網に屋号の語を足して、今後の版に入らないよう見張る。
   - **外の目** (別の LLM による外部のレビュー・差分 `ac26a29..4f5a16e`) = 判定 BLOCKED・4 件 (読みによる所見): 【P】扇の 2 回押しの 1 回目と 2 回目が、click と数字で同じ「選んだ」の控えを使う = click で選んだ「次から訊かない」を、迷い込んだ数字 1 つで決めた (HIGH・②の直しの穴)。【Q】pointer の止まりで走査が戻る枝が、焦点の後の静かな間を短くした (HIGH・③の直しの穴)。【R】返りの形だけを見る試験は、解く順を鍵の前へ戻す後戻りを見張れない (MEDIUM)。【S】PATH の欄の前後の空白を外す処理が POSIX の名を変える (LOW)。→ 【P】= 2 回目は同じ入り方 (click 同士・同じ数字同士) の時だけ決める・【Q】= 戻る時刻も焦点の後の静かな間の後にする・【R】= 解いた回数を数える試験を足した・【S】= 空白と引用符を外すのは Windows だけ。直した後の 7 巡目 (差分 `03d975a..d498aac`) = 判定 APPROVED (4 件とも閉じた・新しい所見なし・読みによる確かめ)。
   - **確かめ**: 試験を 9 本足し、1 本の期待を直した (`test_board_js.py` は 121 件・`test_launcher.py` は 71 件・`test_server_http.py` は 40 件)。直しを 1 件ずつ外した写しの木 19 通りで、名指しした試験が落ちる (2 巡目からの累計 224 通り)。念のための行は 1 行 (数字の 1 回目の札と釦の確かめ = 押す時の確かめと重なる)。自動の試験は **597 passed・0 skipped** (§7.3)。

**同日 (11/7) の夜〜11/8 未明・最終デバッグ** (撮りと動画の後・合流の前に、4 つのレンズ = バグ・見落とし・セキュリティ・汎用性で探す回):

11. **最終デバッグで直した物と残した物**。
   - **探し方**: Claude Code の dynamic workflow を 2 巡 (1 巡目 = 見つける役 7・再現役 36・反証役 36・束ね役 1 = 80 体、2 巡目 = 見つける役 6・再現役 6・反証役 27・束ね役 1 = 40 体)。見つけた 54 + 34 件を、再現役が写しの木で実物に当て、反証役が読みで崩し、束ね役 (Fable) が「直す / 文書へ / 落とす」に振った (1 巡目 = 直す 19・文書へ 8・落とす 5 / 2 巡目 = 直す 16・文書へ 6・落とす 5)。別に、外の目 (別の LLM の読むだけの反証) の 8 巡目 (判定 BLOCKED・3 件 = 設定を閉じる Space の 2 打目・名簿の錠・日本語を書けない console で板が落ちる = 全部直した) と、公式の Claude Security の走査 (5 件 = 4 件は §5.7 に文書済みの限界・1 件直した)。
   - **直した物** = 36 件 + 追加 2 件 (1 件 1 commit・各件に再現の試験 + 直しを外すと落ちる確かめ)。線 3 に関わる主な物: 焦点の上の Enter / Space で「次から訊かない」が 1 押しで決まる (#19)・帯と状態の行の出入りで滞留が見ていない釦を押す (#4)・走査の列の長さだけが変わると光が跳ぶ (#21・keepLight)・押したままの印が焦点の無い窓に残る (#10+#33)・0.0.0.0 で待つ相手の port に板が起きて客を奪う (#16)・`blemma.py` が -I / -P / PYTHONSAFEPATH で落ちる (#2)・質問と MCP の札の見えない字 (#23+#25)・setMode auto の除外 (#26)・描き直しで残る走査の光 (i4)・滞留の守りの 1 こまの揺れ (i19)・設定を閉じる 2 打目・名簿の錠・日本語を書けない console。
   - **外の目の 9 巡目** (差分 `697994b..4dc43ad`・判定 WARNING): MEDIUM 2 件 = 焦点の上の Enter → Space (別のキーを 1 回ずつ) でも「次から訊かない」が決まる (同じキーの 2 回に限る)・名簿の錠が 15 秒で取れない時に錠なしで進む (取れなければ登録は止め、終わる側は板を残す・生きている pid の錠は奪わない) = どちらも直した (a41d673・65af1e4・8406d42 = Windows は 60 秒を過ぎた錠を回収しに行く・POSIX は pid の生死だけ)。LOW 1 件 (試験の数の混在) は読まれる前に直していた。
   - **UltraReview (Anthropic の雲で多数の役が再現まで確かめるレビュー) の 1 回目** (PR #1・11/8 1:1x・無料の 1 回目): 所見 4 件 (normal 1・nit 3・全部 `blemma.py` の名簿の錠と `--print-only`) = 書けない置き場の PermissionError を「錠が使用中」と誤認して 15 秒待って止まる (main からの後戻り)・待ち 15 秒 < 回収 60 秒で記録の無い錠を誰も回収できない窓・回収が「見てから消す」で 2 つの待ち手が新しい錠を消しうる・`--print-only` の厳密な encode が surrogateescape で通っていた bytes を拒む (後戻り)。4 件とも直した (1 件 1 commit・直しを外すと落ちる確かめ付き)。直しの途中で見つけた 5 件目 (Windows で別の回が錠を消す一瞬の PermissionError を書けない置き場と誤認 = 負荷の試しで 3.13 は 17 回・3.10 は 4 回退化 → 続けて 3 回断られた時だけ退化) と、残しの 1 件 (錠は作れたが pid を書けない時は錠を外して退化) も閉じた。線 3 を破る所見は無し (全部「止まりすぎる・退化が厳しすぎる」向き)。
   - **確かめ**: 自動の試験 656 passed・0 skipped (3.13 と 3.10)。視線の形の確かめ 11 通り = 全部通る (1 通りは「先に窓へ焦点を渡す」前提を道具に足した = §5.7)。実の窓の検品 15 枚 = main と画素で同じ (差は滞留の満ちの縁だけ)。公開の門 (語の網・履歴・check_pii) = 0 行。
   - **残した物** = §5.7 に 14 行 (claude.cmd の記号・画面の無い Linux の文字のブラウザ・端末を ✕ で閉じた時の後始末・board/state の許可の警告と同時起動・ask_board の日本語の選択肢・MCP の札の要約なし・URL の手書きの範囲外・2 分越えの ask_board は裏へ移らない、ほか)。
