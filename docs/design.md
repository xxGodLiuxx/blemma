# BLEMMA 設計 v1.2 (gaze-board・視線の板) — 2026-11-01

> **この文書はハッカソン (Built with Claude: Japan 2026・2026-11-02 12:00 JST 開始) の前に書いた設計のメモです** (v0 = 2026-10-14 → v1 = 10-31 → v1.2 = 11-01)。開始前に書いたのは文書だけで、実装・試験・設定の file は 11/2 12:00 以後に新しく作る (この repo の最初の commit = 文書だけ = tag `pre-event-docs`・以後の履歴に実装が入り、文書の直しも含む)。文書の中の JSON (§2.5・§7.2) は契約の形の例で、動く file ではない。開始後に変えた所はこの file の git の履歴に残る。

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
10. デモ: AskUserQuestion の場面 10 秒・スイッチと携帯の実の操作を入れた。名乗りは屋号だけ・画面は板と端末だけ・冒頭の 1 行は起動の引数・退化は別の撮り (§9)。

---

## 1. なぜ作るか — 一言と線 3 本

**一言**: Claude Code が人に訊く瞬間 (権限の確認・MCP の問い・Claude 自身の質問・待ちの合図) と、エージェントが先回りで用意した「次の一手」を、**大きな釦の板**に出して、**視線 1 回** (スイッチ 1 回・片手 1 押し・携帯 1 タップ) で答えて進める OSS。

**なぜ**: Claude Code は仕事の途中で何度も人に訊く。どれも端末の小さな dialog に出て、矢印キーと Enter で答える形 = 視線・スイッチ・片手では狙いにくく、結局は打鍵が要る。公式の accessibility は screen reader・拡大鏡・動きの低減・色覚の theme・ベルまでで、視線とスイッチに触れる文は無い (裏取り §3.5【raw】 https://code.claude.com/docs/en/accessibility.md)。BLEMMA は訊く瞬間だけを横取りして別の頁 (板) に出し、答えを公式の仕組みで Claude Code に戻す。

**線 3 本** (動かさない):
1. **公式の口だけに乗る** = settings の hooks (`PermissionRequest`・`PreToolUse`・`Elicitation`・`Notification`) と MCP の elicitation。Claude Code 本体の fork・patch・端末への打鍵の注入はしない。
2. **板が無ければ退化** = 板が居ない・時限を過ぎた・壊れた時、BLEMMA は判断を返さず (無出力・exit 0)、Claude Code の通常の判断の流れに委ねる。対話の環境で他の決定 (規則・他の hook・mode) が無ければ、いつもの確認が出る (§5.1・§5.3)。
3. **勝手に許可しない** = 人が板で選んだ時だけ allow を返す。時限・不明・誤り = 判断なし (allow でも deny でもない)。

**範囲**: 板が答えるのは**選択式の問い** (選ぶだけで答えが決まる物)。自由記述と入力の直しは端末へ戻す = 視線の利用者にとっては機能の縮小 (打鍵が要る)。縮小を小さくする道は §4.3。

**名乗るテーマ** (v1.2・作り手の決め 10/31): 公募のテーマ 2「本来、誰にでも届くべきものを。」= 壁を取り払って、届いていない人の手に。BLEMMA が取り払う壁 = **操作の壁** (端末の小さな dialog と打鍵。公募の例に挙がる専門知識・費用・言語・手続きには無い壁 = 自分の言葉で名指しする)。壁の外側の具体的なひとり = 視線だけで打つ作り手本人。同じ板が携帯・片手・スイッチの人にも届く。概要・README・動画の冒頭でこの順に言う (§9)。

---

## 2. 4 つの口と先回りの 1 本 — 契約

### 2.0 4 本に共通の決まり

- 形: settings の `hooks` = イベント → matcher の組 → hook の定義 (`type: "command"`・exec 形 = `command` + `args`・`timeout`・`statusMessage`)。exec 形は "No shell tokenization happens on any platform." (裏取り §1.3【断片】 https://code.claude.com/docs/en/hooks.md)。
- matcher: 英字・数字・`_`・`-`・空白・`,`・`|` だけの matcher は完全一致の一覧、それ以外の字を含む matcher は "JavaScript regular expression, unanchored" (裏取り §1.3【断片】) = **全部に当てる時は `.*` と明示する** (省略に頼らない)。
- 共通の入力欄 (stdin の JSON): `session_id`・`prompt_id`・`transcript_path`・`cwd`・`scratchpad_dir`・`permission_mode`・`effort`・`hook_event_name`、subagent の中だけ `agent_id`・`agent_type` (裏取り §1.4【断片】)。板は `cwd` の末尾の名・`session_id` の頭 6 字・`agent_type` で札の「出どころ」を見せる (v1 の判断)。
- 公式の出力の決まり: "Exit 0 means success, and is the intended exit code when you print JSON for structured control." / "Print nothing but the JSON object to stdout." (裏取り §1.4【断片】)。
- **BLEMMA の hook の約束** (v1.1 の判断):
  - 判断を返す時は stdout に JSON 1 個だけ・exit 0。返さない時 (板が居ない・時限・端末で答える・板で描けない形・例外) は何も書かず exit 0 = Claude Code の通常の判断の流れへ。stderr も既定は空 (`BLEMMA_DEBUG=1` の時だけ 1 行)。
  - 板との通信の失敗 (`board/state/run.json` が無い・接続を断られた・時間切れ・壊れた返り) を「無出力・exit 0」に変えるのは**共通の client (`hooks/_client.py`) の責務**。stdin が UTF-8 で解けない・JSON でない時も無出力。
  - Claude Code が settings の `timeout` で hook を止めた時は **exit 0 の保証の外** (公式 = 出力を捨てて判断なし・裏取り §1.9)。
  - exit 2 は使わない。exit 2 の意味は口ごとに違う = PermissionRequest は無効 ("Exit code 2 isn't honored for this event")・Elicitation は「断る + dialog も出ない」・PreToolUse は「道具を止める」(裏取り §1.4 の表)。
  - JSON は `json.dumps(…, ensure_ascii=True)` で書く (Windows の stdout が cp932 でも壊れない)。stdin は bytes で読んで UTF-8 で解く。
  - 雛形に `onFailure` を書かない (既定 `"continue"`。`"block"` にすると板の不調と時限で道具が止まる・v2.1.295 以降の欄・裏取り §1.3)。
  - 公式の JSON を組むのは hook だけ。板の頁と server は「口の種」と「選んだ番号」しか知らない (§3.3)。
  - 待つ秒・期限・取り消しの猶予の数は §3.4 の 1 か所で決める。
- **待っている間の端末の見え方** (口で違う・確かめ = §10.1):

| 口 | hook が待つ間の端末 | 出典 |
|---|---|---|
| PermissionRequest (AskUserQuestion の確認) | 端末の dialog も同時に出て、早い方の答えが勝つ | 【報告】#103115 = AskUserQuestion についての報告 (裏取り §1.7) |
| PermissionRequest (Edit・Bash・MCP の道具) | 同じかは分からない | 上の報告の一般化は憶測 |
| PreToolUse (AskUserQuestion) | 質問の dialog は出ない (憶測) | 【raw】"PreToolUse hooks run before the permission prompt" (裏取り §1.6)。質問の dialog まで出ないのは、この文からの憶測 |
| Elicitation | form は出ない (hook が終わってから描く) | 【報告】#103115 "Claude Code awaits every Elicitation hook before it draws the form" |

  = ask.py と elicitation.py が待つ間は**板が唯一の窓**で、端末は固まって見える。対処 = hook の定義の `statusMessage` (共通欄・裏取り §1.3) に「BLEMMA: waiting on the board」を入れて端末に出す (端末での見え方は憶測) + 板の全部の札に「端末で答える」(§4.3) を置く。

### 2.1 権限の確認 = `PermissionRequest` (`hooks/permission.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "When a tool call needs a permission decision" / "Runs when Claude Code is about to ask you for permission to use a tool." (裏取り §1.2・§1.5【断片】)。hook が `allow` を返すと "Claude Code answers the request on your behalf" (hooks-guide【raw】) |
| matcher | `.*` (= 全部の道具)。人が押した時だけ allow を返すので全部でも安全。公式の注意 "Matching on `.*` or leaving the matcher empty would auto-approve every tool permission prompt" (【raw】・裏取り §1.5) は無条件に allow を返す hook の話。除く物は script の側 (下の「板に出さない物」) |
| 公式の入力 (stdin の鍵) | 共通欄 + `tool_name`・`tool_input` (PreToolUse と同じ形・`tool_use_id` は無い)・MCP の道具なら `mcp_server`・任意で `permission_suggestions` (許可の更新の配列) |
| 板に出す物 | 頭 = 道具の種と出どころ。本文 = 何をしようとしているか (下)。釦 = **許可 (今回)**・**次から訊かない** (`permission_suggestions` が在る時だけ・対象と保存期間つき)・**拒否** (理由を定型 3 つから)・**作業を止める** (固定の位置・§4.3)・**端末で答える** (96px 以上) |
| 返す出力 (stdout) | 下の JSON。exit は全部 0。端末で答える・時限・板なし・板に出さない物 = 無出力 |
| 時限と退化 | 板の期限 (§3.4)・板へ繋がらない (client が無出力に変える) → 無出力。"A hook that exits 2 without a `decision` object leaves the permission flow unchanged" (裏取り §1.5【断片】)・Claude Code の timeout = 出力を捨てる (裏取り §1.9)。どれも Claude Code の通常の流れへ (対話で他の決定が無ければ端末の dialog) |
| 出典 | https://code.claude.com/docs/en/hooks.md (PermissionRequest 節)・https://code.claude.com/docs/en/hooks-guide.md・裏取り §1.5 |

本文の出し方 (v1 の判断):
- Bash = `command` を**省かず全部** (尾に危ない物を隠させない・長ければ札の中で巻物にする) + `description`。
- Edit = `file_path` と `old_string` → `new_string` (長ければ折りたたむ)。Write = `file_path` と頭の 40 行。
- MCP の道具 = `mcp__<server>__<tool>` と入力の JSON (2,000 字まで・超えたら「続きは端末で」)。他の道具 = 入力の JSON。

返す JSON:
```json
{ "hookSpecificOutput": { "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" } } }
```
- **欄の契約は裏取りの定義で確定** = `decision` の中に `behavior` (`allow` / `deny`)。allow だけ `updatedInput` と `updatedPermissions` (配列)、deny だけ任意の `message` ("tells Claude why the permission was denied") と `interrupt` ("if `true`, stops Claude") (裏取り §1.5【断片】)。公式頁に無いのは deny の**完成した例**だけで、契約は分かっている。`updatedPermissions` の 1 件の例 = `{"type":"setMode","mode":"acceptEdits","destination":"session"}` (hooks-guide【raw】・裏取り §1.5)。
- 許可 (今回) = 上の通り。
- 次から訊かない = 同じ allow に `"updatedPermissions": [ <選んだ suggestion を入力から逐語で写す> ]`。
- 拒否 = `"decision": { "behavior": "deny", "message": "<定型の理由>", "interrupt": false }` (Claude は理由を見て別の道を探す)。定型 3 つ = 「別のやり方でお願いします」「いまは要りません」「先に説明してください」(v1 の判断・頁の言葉に合わせて英語も)。
- 作業を止める = `"decision": { "behavior": "deny", "message": "BLEMMA: the user stopped the work", "interrupt": true }` (Claude を止める = 作業全体を止められるのはこの口だけ・§5.4)。

「次から訊かない」の字 (v1.1 の判断・保存先の種 = 裏取り §1.5【断片】):
- 規則を足す suggestion (`addRules`) = 「次から訊かない: Bash(git commit …) — <保存期間>」。保存期間の字 = `session`「このセッションの間」/ `localSettings`「この project・この機械で恒久」/ `projectSettings`「この project の共有の設定で恒久 (commit されうる)」/ `userSettings`「全部の project で恒久」。
- モードを替える suggestion (`setMode`) = 別の字「モードを替える: 編集を訊かない (acceptEdits) — このセッションの間」(規則を 1 つ足す釦と同じ字にしない)。**`bypassPermissions` へ移す物は釦にしない** (一押しで確認が全部消える物は板で出さない)。
- `replaceRules`・`removeRules`・`addDirectories`・`removeDirectories` = 中身を逐語で出す (例「このフォルダも許す: <路>」)。複数あれば 2 件まで (3 件目からは端末で)。
- #91216【報告】= suggestion が端末の行と一致しない事がある → 板は suggestion の中身そのものを見せ、それをそのまま写す。

**板に出さない物** (script が無出力で返す・v1.1 の判断):
- `tool_name` が `ExitPlanMode` = allow が効かない回帰が open で 3 件 (§5.5)。計画の承認は端末で。
- `tool_name` が `AskUserQuestion` = 質問の口を PreToolUse で答える間 (§2.2 の排他)。
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
| 板に出す物 | 1 問 = 1 画面。頭 = `header`、本文 = `question`、釦 = 各 `label` (下に小さく `description`)。**押す数** = 1 問の単一選択は選んだ 1 押しで送る (取り消しの猶予が見直しの代わり)・複数の問いと `multiSelect` は最後に「送る」の 1 押しを足す (確かめの 1 画面)。固定の位置 = **この質問に答えない**。端末の Other に当たる「ほかの答え」は板では書かず端末で答える。端末で答える (96px 以上) |
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
- `multiSelect` = label を ", " でつないだ 1 本の文 (SDK の頁は「label の配列か ", " 区切り」【raw】・CLI の hook で通る形は未確認 = 初日に、カンマを含む label も確かめる)。通らなければ複数選択の問いは板に出さない (§10.2)。
- この質問に答えない = `"permissionDecision": "deny"` + `"permissionDecisionReason": "BLEMMA: the user did not answer this question"` (欄名 `permissionDecisionReason` はこの裏取りに無い = 初日に確かめる)。理由の欄が使えなくても deny の意味 (この道具の呼び出しを断る) は変わらない = **作業全体の停止ではない** (Claude は続けうる・§5.4)。
- `permissionDecision` の 4 値 = `allow`・`deny`・`ask`・`defer` (`defer` は `-p` だけ)。複数の hook が食い違えば deny > defer > ask > allow (裏取り §1.6・SDK【raw】)。hook の `allow` は deny / ask の規則を超えない (permissions.md【raw】)。

**経路の排他** (v1.1 の判断): 提出版の主 = PreToolUse。その間 permission.py は `AskUserQuestion` を除く。初日に PreToolUse で答えられず、PermissionRequest の allow + `updatedInput` で答えられた時は、PreToolUse の登録を外すのと同時に permission.py の除外も外し、PermissionRequest の側で答える (両方に同時に登録しない = 札が二重にならない)。両方とも答えられなければ ask.py を外す (§10.2)。

板に出ない場面: subagent の中では `AskUserQuestion` 自体が使えない ("`AskUserQuestion` is not currently available in subagents spawned via the Agent tool"【raw】・裏取り §1.6) = subagent からの問いは ask_board (§2.5)。`ExitPlanMode` も PreToolUse の allow + `updatedInput` で答える形だが、提出版は matcher に入れない (§5.5)。

### 2.3 MCP の問い = `Elicitation` (`hooks/elicitation.py`)

| 項目 | 中身 |
|---|---|
| 発火 | "Runs when an MCP server requests user input mid-task. By default, Claude Code shows an interactive dialog for the user to respond. Hooks can intercept this request and respond programmatically, skipping the dialog entirely." (裏取り §1.7【raw】) |
| matcher | `.*` (= 全部の MCP server)。matcher の対象は MCP server の名 (裏取り §1.3)・`.*` は正規表現の規則で全部に当たる (§2.0) |
| 公式の入力 (stdin の鍵) | 共通欄 + `mcp_server_name`・`message`・任意で `mode` (`form` / `url`)・`url`・`elicitation_id`・`requested_schema` |
| 板に出す物 | 頭 = **問うている server の名** (MCP の MUST "Provide UI that makes it clear which server is requesting information"・裏取り §2.2【raw】)、本文 = `message`、欄 = 下の表。**押す数** = 1 欄の単一選択 (enum・`oneOf`・boolean) は選んだ 1 押しで送る (取り消しの猶予が MCP の MUST "allow users to review and modify their responses before sending" の見直しの代わり・v1.1 の判断)・2 欄以上と複数選択は確かめの 1 画面と「送る」の 1 押し。釦 = **断る** (decline)・**この問い合わせを閉じる** (cancel・固定の位置)・端末で答える (96px 以上) |
| 返す出力 (stdout) | 送る = 下の JSON・断る = `"action": "decline"`・この問い合わせを閉じる = `"action": "cancel"`・端末で答える・時限・板なし・板で描けない形・url mode = 無出力。exit は全部 0 |
| 時限と退化 | 「利用者に任せる = 出力なしで exit 0 → dialog での利用者の答え」(裏取り §1.7【raw】の表)。板の期限・板へ繋がらない → 無出力 → 端末に form が出る |
| 出典 | https://code.claude.com/docs/en/hooks.md (Elicitation 節)・https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation.md・裏取り §1.7・§2 |

返す JSON (`content` の鍵は `requested_schema.properties` の名・裏取り §1.7【raw】):
```json
{ "hookSpecificOutput": { "hookEventName": "Elicitation",
    "action": "accept", "content": { "choice": "2" } } }
```
- `hookEventName` を入れるのは他の口と揃えた形 = 要るかは初日に確かめる。

欄 (`requested_schema.properties`) の描き方 (MCP の form は "flat objects with primitive properties only"・裏取り §2.2【raw】・v1 の判断):

| 欄の形 | 板 |
|---|---|
| `enum`、または `oneOf` の [{`const`,`title`}] (単一選択) | 選択肢ごとに釦 (字は `title`、無ければ値) |
| `type: array` + `items` の `enum` / `anyOf` (複数選択) | 印の付く釦 + 「送る」 |
| `boolean` | 2 釦 (はい / いいえ・欄の `title` を問いに) |
| `integer` / `number` で `minimum`〜`maximum` が 10 個以内 | 数の釦 |
| `string` (enum なし)・幅の広い数 | `default` が在れば「既定の値で: <値>」の釦 1 つ (候補の釦)、無ければ「端末で答える」だけ (板で文字は書かない) |
| 上のどれでもない・欄が 7 つ以上 | 札を出さず無出力 (端末へ) |

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
| 板に出す物 | 板の縁を光らせ、上の帯に `message` を 10 秒 (音は設定で入 / 切)。札が出ていれば札を点滅。`idle_prompt` = 「Claude が次の指示を待っています (端末へ)」。`elicitation_url_dialog` = 「端末でリンクを開くか決めてください」。決める釦は出さない (観察だけ) |
| 返す出力 (stdout) | 何も書かない・exit 0 ("Exit code and stderr are ignored"・裏取り §1.4) |
| 時限と退化 | settings の `timeout` 10 秒・板へは 1 回 POST して待たない (1 秒で諦める・v1 の判断)。板が居なければ何もしない |
| 出典 | https://code.claude.com/docs/en/hooks.md (Notification 節)・https://code.claude.com/docs/en/hooks-guide.md・裏取り §1.8 |

- matcher = `permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input` (英字・`_`・`|` だけ = `|` 区切りの完全一致の一覧・裏取り §1.3)。型の全部 = 裏取り §1.8。
- 主経路にしない理由: `permission_prompt` は "Expect `permission_prompt` once you haven't typed for about six seconds." (約 6 秒)、`idle_prompt` は応答の後 約 60 秒 (裏取り §1.8) = 板の札は PermissionRequest / PreToolUse / Elicitation で先に出ている。Notification は光と音の役。

### 2.5 先回りの 1 本 = 同梱の MCP server `blemma` の道具 `ask_board` (`mcp/blemma_mcp.py`)

役: エージェントが文脈から用意した 2〜6 個の選択肢を、MCP の elicitation (form・enum) で人に出す。Elicitation の hook (§2.3) が板に出し、選ばれた物が道具の戻りになる。独自の注入の口は要らない。

**道具の schema** (`tools/list` で返す・v1 の判断):
```json
{
  "name": "ask_board",
  "description": "Ask the human to pick one of 2-6 short choices (big buttons on the BLEMMA board, or the normal form without it). Use at a decision point or to offer next steps. Always include one choice that stops or waits.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "title": { "type": "string", "description": "One-sentence question, up to 80 characters" },
      "choices": { "type": "array", "items": { "type": "string", "maxLength": 40 },
                   "minItems": 2, "maxItems": 6, "description": "Short, distinct labels" },
      "allow_free_text": { "type": "boolean", "default": false,
                           "description": "Also accept an answer in the human's own words" }
    },
    "required": ["title", "choices"]
  }
}
```
- 道具の説明文は英語 (Claude が読む物・README と揃える)。字の上限・重複・数を道具の側で確かめ、外れたら `isError: true` で理由を返す。

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
          { "const": "1", "title": "PR の本文を書く" },
          { "const": "2", "title": "試験を回す" },
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
| `accept` + `choice` = "other" | `{"answer": "<other_text>", "free_text": true}` | false |
| `decline` | `{"answer": null, "declined": true}` + 「人はどれも選びませんでした。別の案を出すか、文で訊いてください」 | false |
| `cancel` | `{"answer": null, "cancelled": true}` + 「人はこの問い合わせを閉じました。作業を止めて次の指示を待ってください」 | false |
| client が elicitation を宣言していない | 「この環境では MCP の問いが出せません。AskUserQuestion か文で訊いてください」 | true |

- `cancel` の戻りの「止めて待ってください」は Claude への**指示で、止まる保証ではない** (§5.4)。

**板が無い環境での退化**: 板が居ない・期限 = Elicitation の hook が無出力 → 端末に Claude Code の既定の form (同じ `oneOf` の選択肢) が出る (Esc = cancel)。hooks を入れていない人が使っても同じ form が出る。elicitation を話さない client では上の表の最後の行。

**MCP の話し方** (標準ライブラリだけ = JSON-RPC 2.0 を自前で・v1 の判断):
1. stdio = 1 行に 1 つの JSON-RPC の文・stdout には MCP の文の外を書かない・記録は stderr (MCP の transports 頁 https://modelcontextprotocol.io/specification/2025-11-25/basic/transports — この裏取りの外 = 書き手の知識)。**初日の MCP の確かめの前提**なので 11/3 へ送らず、初日に最小の種で確かめる (§10.1)。
2. `initialize` に `protocolVersion: "2025-11-25"` で答え、client の `capabilities.elicitation` を控える。**Claude Code の側は確定** = `{form: {}, url: {}}` を、2025-11-25 までの利用者が設定した stdio の server にも宣言する (v2.1.287 以降・裏取り §2.4【raw】)。自作の server との版の取り決めと、subagent の中からの問いは別の未確認 = 両方に分岐 (§12.3)。
3. `tools/list` で上の schema。`tools/call` の中で server → client の要求 `elicitation/create` (自分の id) を送り、client の応答 (`action`・`content`) を待つ = stdin を読む thread が id で応答を振り分ける (待つ間に来る `ping` にも答える)。
4. 2026-07-28 の版 (`InputRequiredResult` に入れて返し、client が `inputResponses` を付けて呼び直す = MRTR・裏取り §2.3【raw】) は作らない。2025-11-25 が通らなかった時も**MRTR へ自動で全面変更せず、ask_board を外して範囲を縮める** (§10.2)。

**同梱の skill** `skills/board/SKILL.md` (作法・v1 の判断): ①答えが 2〜6 個の選択肢に絞れる問いは `ask_board` で出す ②作業の区切り (commit の後・試験の後) で「次の一手」を 3 つ前後 ③選択肢は 40 字以内・互いに違う・必ず「ここで止める / 待つ」を 1 つ ④答えを推測で進めない (cancel なら止まる) ⑤Claude 自身の確かめ (2〜4 択) は `AskUserQuestion` でもよい・subagent の中からは `ask_board` (AskUserQuestion が無い) ⑥自由記述が要りそうな問いは、ありそうな答えを先に選択肢に入れてから `allow_free_text` (候補の釦を増やす = 端末へ戻る回を減らす)。CLAUDE.md へ誘導する 1 行の例 =「迷う所は ask_board か AskUserQuestion で 2〜6 択にして訊く」。

**要る版**: Claude Code **v2.1.287 以降** (利用者が設定した stdio の MCP server に elicitation を宣言する版・裏取り §2.4【raw】)。v2.1.314 で確かめる。

**別の公式の口 (提出版の外)**: `Stop` の hook が `"decision": "block"` + `reason` を返すと、Claude は止まらず `reason` を指示として続ける (連続 8 回の上限・裏取り §1.8【raw】) = 「Claude が止まった時に板で次の一手を選ぶ」をエージェントの協力なしで作れる。ただ応答のたびに待ちが入り、キーで使う人の端末を塞ぐ (§5.6)。

---

## 3. 答えが戻るまでの流れ = 板の server (`board/server.py`)

### 3.1 流れ
Claude Code (hook を起こす・stdin に問いの JSON) → hook (python・`POST /ask` → `GET /wait` の long-poll で待つ) → 板の server (127.0.0.1・待ち行列) → 板の頁 (`GET /pending` の long-poll で札を受ける → 人が選ぶ → `POST /answer`) → server が取り消しの猶予を持つ → hook の `GET /wait` に答え → hook が自分の stdin の写しから公式の JSON を組んで stdout へ → Claude Code。札の終わりは §3.5 の 5 つのどれか 1 つに排他で決まる。

### 3.2 起動と在処 (v1 の判断)
- `python board/server.py [--port 8765] [--wait 300] [--perm-wait SEC] [--undo-ms 3000] [--allow-host NAME] [--no-browser] [--no-log]` で利用者が起こす (hook から自動では起こさない = 隠れた常駐を作らない)。数の意味と上限 = §3.4。起きたら頁を既定のブラウザで開く (`webbrowser`)。URL は `localhost` でなく `127.0.0.1` で出す (localhost は ::1 に引かれうる)。
- 起動ごとに token = `secrets.token_urlsafe(32)`。在処の file = `board/state/run.json` (`{"port":…, "token":…, "pid":…, "started":…}`・`board/state/` は .gitignore 済み・POSIX は 0600)。hook は自分の路から `../board/state/run.json` を読む (利用者の project の cwd に依らない)。file が無い・読めない = 板なし = 無出力。止まる時に消す (落ちて残っても、接続が断られて無出力になるだけ)。
- port は既定 8765・使用中なら起動を断る (黙って別の port に移らない)。
- 待ち受けは **127.0.0.1 だけ** (0.0.0.0・LAN の IP には bind しない)。`http.server.ThreadingHTTPServer` (`daemon_threads = True`)。札の状態は 1 つの錠の下で変える。

### 3.3 口 (全部 JSON・v1.1 の判断)

| 口 | 呼び手 | 送る物 | 返り |
|---|---|---|---|
| `POST /ask` | hook | `kind` (permission / question / elicitation)・`from` (cwd の末尾の名・session の頭 6 字・agent_type)・`payload` (表示に要る物だけ) | `200` + `id` (札の一意の ID)・`hard_deadline` (§3.4) / `401` (token 違い) / `503` (待ちが上限を超えた → hook は無出力) |
| `GET /wait?id=…` | hook | long-poll (server は最長 15 秒抱える・hook はすぐ呼び直す) | `state` = waiting / answered (+ `answer`) / released / expired / closed |
| `POST /notify` | notify.py | `type`・`from`・`title`・`message` | `204` (待たない) |
| `GET /pending?seq=N` | 頁 | long-poll (最長 25 秒・seq が進んだら返す) | `seq`・`card` (無ければ null・`id` と `state` と期限を含む)・`queue` (待ちの数)・`light`・`stats` |
| `POST /answer` | 頁 | `id`・`seq` (描いた時の seq)・`choice` (下)・`by` (dwell / key / switch / touch / click)・`presses` (その札で押した数) | `200` + `undo_until` / `409` (札が shown でない・seq が古い・期限を過ぎた・先に決まった) |
| `POST /undo` | 頁 | `id`・`by`・`presses` (猶予のうちだけ) | `200` / `409` |
| `POST /resolve` | 観察の hook (`PostToolUse`・`PermissionDenied`・**提出版では登録しない**) | `session`・`event` (post_tool_use / permission_denied)・`key` (要求と 1 対 1 に結べる照合の鍵) | `200` + `closed` (id か null)・`reason` (none / ambiguous / no_key) |
| `GET /`・`/static/…` | 頁 | 板の頁 (data を持たない) | token なしで返す |

- **choice = 番号だけ** (hook が自分の stdin の写しから文と公式の JSON を組む = 板が文を作り変えられない・`answers` の鍵が 1 字もずれない):
  - permission = `allow_once` / `allow_always` + `suggestion` (何番目) / `deny` + `reason` (定型の何番目) / `stop` / `terminal`
  - question = `answer` + `picks` (問いごとの選んだ番号の列) / `skip` (この質問に答えない) / `terminal`
  - elicitation = `accept` + `values` (欄の名 → const・真偽・数) / `decline` / `cancel` / `terminal`
  - hook は受け取った値を自分の入力 (選択肢の数・schema) と照らし、外れていれば無出力。
- **`/answer` を受ける条件**: `id` が今出している札・札が shown・`seq` が札の今の表示と同じ・server の時計で期限の前。どれかが外れれば `409` (古い画面への押しは効かない・§4.2 の世代)。
- **`/resolve` の採用の条件**: `key` が要求と 1 対 1 に結べる時だけ (初日に見つかった時・§3.7)。1 件だけ一致すれば閉じ、0 件・2 件以上・鍵なしは何もしない。
- **token**: hook と頁は見出し `X-Blemma-Token` で送る。頁は URL の `#t=<token>` を読む (fragment は server へ送られない = 記録と referer に残りにくい)。`/` と `/static/…` の外は token が合わなければ `401`。
- **Host の照合**: `Host` の名の部分 (port は問わない) が `127.0.0.1`・`localhost`・`--allow-host` で足した名でなければ `403` (DNS rebinding で外の頁から叩かれない)。CORS の見出しは出さない (外の頁の `fetch` は token の見出しで preflight に落ちる)。
- 本文 (`payload`・`message`) は札が生きている間だけ記憶に持ち、閉じたら捨てる。server の記録 (`log_message`) は口の名と状態だけ。

### 3.4 待ち行列・期限と数 (数はこの 1 か所で決める)
- 札は **1 件ずつ** 出す (先に来た物から)。頁に「待ち N 件」。並列の道具・subagent・複数のセッションで溜まる時は、札の頭の「出どころ」で見分ける。
- **期限 = min(表示した時 + 待ち, 作った時 + 作成からの上限)**。表示から数えるので、2 件目の札も表示から待ちの秒を持つ (作成からの上限で抑える)。
- 表示する時に、作成からの上限まで 30 秒を切っていれば、表示せずに expired (表示の直後の期限切れを作らない)。

| 数 | 値 | 決まり |
|---|---|---|
| 待ち (`--wait`) | 既定 300 秒 (表示から) | 作成からの上限以下 |
| 権限の札の待ち (`--perm-wait`) | 既定 = `--wait` | 縮小の時 (§10.2) に縮める (例 120 秒) |
| 作成からの上限 | 540 秒 (定数) | = settings の hook の `timeout` 600 − 60 |
| 表示の最小の残り | 30 秒 | 切っていれば表示しない |
| 取り消しの猶予 (`--undo-ms`) | 既定 3,000 ms | 0〜5,000 ms・5,000 を超える値は起動を断る |
| hook の自前の期限 (`hard_deadline`) | 作った時 + 540 + 5 + 10 = 555 秒 | settings の `timeout` 600 より 45 秒短い |
| `POST /ask` / `GET /wait` の諦め | 2 秒 / 20 秒 | server は `/wait` を最長 15 秒抱える |
| 接続の終了の判定 | 最後の `/wait` が返ってから 5 秒 | 次の `/wait` が来なければ disconnected |
| 待ちの上限 | 20 件 | 超えたら `503` → hook は無出力 |

- **settings の `timeout` を変える時は 3 つを一緒に直す**: 作成からの上限 (= `timeout` − 60)・hook の自前の期限 (= 上限 + 猶予の上限 5 秒 + 10 秒)・`--wait` の上限 (= 作成からの上限)。不等式 = `--wait` ≤ 上限 < 上限 + 15 < `timeout`。

### 3.5 札の状態と終わりの確定 (v1.1 の判断)

| 状態 | 入る条件 | 頁の文 | hook の動き |
|---|---|---|---|
| queued | `/ask` を受けた (先の札が在る) | 「待ち N 件」に数える | `/wait` = waiting |
| shown | 先頭になり、残りが 30 秒以上 (§3.4) | 札を描く | waiting |
| deciding | 期限の前に `/answer` を受けた (§3.3 の条件) | 「決まりました・取り消す (n)」 | waiting |
| **answered** (終わり) | 猶予が過ぎ、hook の `/wait` へ答えを返し終えた | 「板の答えを Claude Code へ渡しました (端末の確認が続くことがあります)」 | 公式の JSON を組んで stdout・exit 0 |
| **released** (終わり) | 「端末で答える」の猶予が過ぎ、hook へ返し終えた | 「端末で答えてください」 | 無出力・exit 0 |
| **expired** (終わり) | 期限 (表示の前の失効を含む) | 「時間切れ。端末で答えてください」 | 無出力・exit 0 |
| **disconnected** (終わり) | どの途中の状態でも、最後の `/wait` から 5 秒、次の `/wait` が来ない | 「接続が終了しました。端末を確認してください」(deciding からなら「板の答えは届いていません」を足す) | (hook は居ない) |
| **resolved** (終わり) | `/resolve` の 1 対 1 の一致 (採用した時だけ) | 「端末の側で終わりました」 | 残っていれば次の `/wait` で closed → 無出力 |

- **終わりは排他**: server の錠の下で最初に決まった 1 つだけが効き、後から来た出来事 (遅れた `/answer`・`/undo`・`/resolve`) は捨てて、状態の数だけ記録する。
- answered は「hook へ渡した」までで、Claude Code が使ったかは分からない (端末の答えが先なら捨てられる) = 「許可されました」とは書かない。hook への書き込みが失敗したら disconnected。
- disconnected は「端末で答えが出た」と書かない (通信の失敗・hook の異常な終わりと見分けられない)。

### 3.6 取り消しの猶予と優先の順
- 頁が `POST /answer` → 札は deciding (猶予 = `--undo-ms`) → 全部の頁に「決まりました・取り消す (3)」 → 猶予のうちに `POST /undo` が来れば shown へ戻す → 来なければ猶予の後に hook の `/wait` へ返して answered (「端末で答える」なら released)。
- = **1 答あたり猶予の分だけ遅れる** (既定 3 秒・0 にもできる)。server の側で持つ理由 = PC と携帯の 2 枚の頁が開いていても、決まった事が両方に同時に出る (2 枚で別々に押されて答えが 2 つにならない)。
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
- `/resolve` (§3.3) は、要求と 1 対 1 に結べる鍵が初日に見つかった時だけ作る。**指紋 (session_id + tool_name + tool_input) は 1 対 1 にならない** (同じ入力の要求が同じセッションで並ぶ・規則で自動で許された同じ呼び出しの PostToolUse も来る) = 指紋では閉じない。PermissionRequest の入力に `tool_use_id` は無い (裏取り §1.5)。

### 3.8 記録と通信の範囲
- `board/state/log-YYYY-MM-DD.jsonl` に 1 札 1 行 = `{"t":"<時刻>","kind":"permission","end":"answered","choice":"allow_once","sec":2.4,"by":"dwell","presses":1,"undo":0}`。道具の名・入力・問いの文・答えの文字は**書かない**。`--no-log` なら書かない。
- **通信の範囲** (BLEMMA が保証する物を限る): BLEMMA は外のサービスへ自動では何も送らない (server は 127.0.0.1 だけで待ち受け、外へ繋がない・頁は外の font と script を読まない)。携帯で使う時は、**利用者が自分で設けた転送の先へ札の本文と token が渡る** (その先は BLEMMA の保証の外)。MCP の問いへの答えは Claude Code を通って問うた server へ返る (BLEMMA の外の通り道)。機外へ一切出さない使い方では携帯を使わない。README の「外へ出さない」の文もこの範囲に合わせる (公開の門・§8)。

---

## 4. 板の頁 (`board/static/`)

### 4.1 見た目
- 札 1 枚 = 頭 (口の種・出どころ・残りの秒) / 本文 (何をしようとしているか・問い) / 釦の列。例 (権限):「EDIT · README.md — 誤字 2 か所を直す」の下に [許可 (今回)] [次から訊かない] [拒否] の大きな釦、左下に固定の [作業を止める]、右下に [端末で答える]、右上に計。
- 釦は **96px 以上** (高さと幅・倍率 1 の CSS px・「端末で答える」も同じ大きさで色を控えめに)、釦どうしの間は 24px 以上、画面の端から 48px 以上離す (視線は端ほど揺れる・v1 の判断)。字は 28px 以上。残りの秒は 60 秒を切ったら色を変える。
- 無地・高コントラスト (文字と背景の比 7:1 を狙う・最低 4.5:1)・`prefers-color-scheme` の明暗・`prefers-reduced-motion` で動きを止める。作り手の手元のデザインは持ち込まない (公開の OSS = 誰の家の物でもない見た目)。
- 外の font・CDN を読まない (offline で動く)。言葉は日本語と英語 (`navigator.language` で選ぶ・`?lang=` で上書き)。

### 4.2 入力の 5 通り (選択式の問いなら、どれでも同じ仕事)

| 入力 | 動き |
|---|---|
| 視線 (滞留) | 釦の上に pointer が留まると縁が満ちていき、**0.8〜1.2 秒** (既定 1.0・`?dwell=`) で押す。揺れの許し 150 ms (外れても 150 ms のうちに戻れば数え続ける)。OS の側の視線の道具が click するなら `?dwell=0` で頁の滞留を止め、click で押す |
| キー | Tab / Shift+Tab で移る・Space / Enter で押す・数字キー 1〜6 で n 番目の釦・Esc = 固定の位置の釦。猶予のうちは Backspace・Esc = 取り消す |
| スイッチ 1 鍵 | 走査 = 光る釦が既定 1.5 秒ごと (`?scan=`) に次へ (釦の列 → 固定の位置の釦 → 端末で答える → 頭へ)・1 鍵 (既定 Space・`?key=`) で選ぶ。**猶予のうちは走査を止め、鍵を一度離してからの次の押下 = 取り消す** |
| 携帯 | 同じ頁 (縦 1 列に並べ替え)・触れたら押す (滞留なし)・猶予のうちは「取り消す」を触る |
| マウス | click で押す |

- **表示の世代** (v1.1 の判断): 札の id・設問の番号・札の状態・釦の並びのどれかが変わったら、頁は世代を 1 つ進める。進んだら ①滞留の時計を全部止め、選択 (複数選択の印を含む) を消す ②pointer が一度釦の外へ出て入り直すまで滞留を数えない ③変わった時に押されていた鍵 (キー・スイッチ) は、離すまで数えない ④走査は頭から数え直す。期限切れ・別の画面からの答えで札が替わっても、同じ位置への注視が次の札の釦に移らない。
- 押した直後も同じ (全部の釦の滞留を止め、pointer の入り直しまで数えない = 見続けて 2 回押さない)。
- 頁は描いた時の `seq` を `/answer` に付ける (§3.3 = 古い画面への押しは `409`)。
- 設定は URL の引数と頁の歯車 (キー・click だけ)。端末の側の設定 file は作らない。

### 4.3 固定の位置の釦・取り消す・端末で答える
- **固定の位置の釦** = 全部の札の**同じ位置** (左下・Esc でも押せる)。位置は同じで、字と意味は口ごと (v1.1 の判断):

| 口 | 釦の字 | 返す値 | 効き |
|---|---|---|---|
| 権限 | 作業を止める | deny + `interrupt: true` | Claude を止める ("if `true`, stops Claude"・裏取り §1.5) |
| Claude の質問 | この質問に答えない | deny (PreToolUse) | この道具の呼び出しを断る。Claude は続けうる |
| MCP の問い・ask_board | この問い合わせを閉じる | `cancel` | 問うた server に「閉じた」を返す。server と Claude は続けうる |

  作業全体を止められる範囲 = §5.4。
- **取り消す** = 押した後の猶予のうちだけ、上の中央に大きく出る (押した釦の上には出さない = 見続けていても誤って取り消さない)。視線・キー・スイッチ・携帯の 4 つとも取り消せる (§4.2)。
- **端末で答える** = 右下・96px 以上。押すと (猶予の後に) hook は無出力で終わり、端末の dialog / form が出る (自由記述・板で描けない物・キーで答えたい時の道)。§3.7 (b) の古い札では字を「端末で答えた・閉じる」に替えて同じ動き。
- **自由記述と入力の直しは端末へ** = 視線の利用者には機能の縮小 (打鍵が要る)。縮小を小さくする道:
  - 候補の釦 = Elicitation の string の `default` を釦に (§2.3)・ask_board はありそうな答えを先に選択肢に入れる (§2.5 の skill の作法)。
  - 端末の打鍵を最小にする公式の道 = screen reader mode (`--ax-screen-reader` など)。"menus you'd normally navigate with the arrow keys, including permission prompts, become numbered lists ... Type the number of the option you want and press Enter." (裏取り §3.5【raw】) = 番号と Enter の 2 打鍵。質問の dialog と form で同じに効くかは確かめていない = README の助言の 1 行に留める。

### 4.4 携帯で見る (server は 127.0.0.1 から広げない)
- 板の server は LAN にも外にも開かない。携帯で見る時は利用者が自分の転送で 127.0.0.1 へ届ける = Android の USB なら `adb reverse tcp:8765 tcp:8765` (携帯の `http://127.0.0.1:8765/#t=…` がそのまま通る)・`ssh -L`・自分の VPN の転送 (名が `127.0.0.1` / `localhost` でなければ `--allow-host <名>` で照合に足す)。
- その時は、利用者が設けた転送の先へ札の本文と token が渡る (BLEMMA の保証の外・§3.8)。機外へ一切出さない使い方では携帯を使わない。
- 頁の右上の「携帯で開く」で `#t=` つきの URL を大きな字で出す。token は起動ごとに替わる。
- 理由 (v1 の判断): LAN へ bind する旗は作らない (平文の HTTP では token が同じ網に見える・待ち受けを広げるのは利用者の転送の側に置く)。

### 4.5 計 (操作の数と時間)
- **数える物 = この頁の押下イベント** (滞留が満ちた・キーで釦を押した・スイッチで選んだ・触った・click した。取り消しも 1 と数える)。**送った答えの数** (answered と released) とは別に出す。
- 表示 = 「押し N (視線 a・キー b・スイッチ c・触る d)・送った答え M・経過 mm:ss」。札ごとに「出てから決まるまでの秒」。
- 頁は札ごとの押した数と手段を `/answer` と `/undo` の `presses`・`by` で server へ渡し、記録は数だけ (§3.8)。
- 板の外の打鍵 (端末) は数えない (未計測)。OS の側の起動の 1 回は板の計に入れず、別に書く。
- 計を 0 に戻す = 頁の [計を 0 に] (キー・click だけ = 視線で誤って消さない)。

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
- 札ごとの一意の ID と、終わり 5 つの排他の確定・期限は表示から数え作成からの上限で抑える・「渡しました」と「許可されました」を分ける (§3.4〜§3.6)。
- 札は 1 件ずつ・出どころを頭に・Bash の command は省かない・「次から訊かない」は対象と保存期間を見せ、モードの切り替えは別の字・`bypassPermissions` へ移す suggestion は出さない (§2.1)。
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

### 5.6 提出版の外に置く物 (外部のレビュー 1 巡目を受けて外した)

| 物 | 外す理由 | 戻す時 |
|---|---|---|
| http 型の handler (板の server へ直に POST) | 本文の形・接続の切り方・timeout の上限・`allowedHttpHookUrls` の既定が未確認。採るなら別の契約と検収が要る | 提出の後に比べる。比べる所 = Windows の `.exe` の縛り・端末先着の時の切り方・token の渡し方 (env の展開は板を起こし直すと古くなる)・入力の形 |
| ExitPlanMode の調べ | 板に出さないので期間の中では要らない | 公式の不具合が直った後 |
| 板の text 欄 (自由記述)・視線の文字盤 | 期間の中では作らない (§4.3 の縮小を小さくする道で補う) | 提出の後 |
| 入力を直して許可 (`updatedInput`) | 直した文の確かめの画面が要る | 元の入力と差分を見て定型の候補から選ぶ形で |
| Stop の hook で次の一手 (5 本目) | 応答のたびに待ちが入り、キーで使う人の端末を塞ぐ | 提出の後 |
| 携帯の QR・plugin として配る形 | 余りの機能 | 提出の後 (plugin は公式の plugins の頁で確かめてから) |

---

## 6. 先行の道具と BLEMMA の 3 点

### 6.1 先行の道具 (URL と細目 = 裏取り §6)
- claude-remote-approver (GitHub・MIT) = 携帯から権限の承認・拒否 (PermissionRequest の hook + AskUserQuestion・通知の中継・時限で CLI の確認へ戻る)。
- claude-board (PyPI) = 携帯・物の釦から承認 (頁の中でライセンスが MIT と AGPL で食い違う)。
- = 「手元の外から権限を押す」は既に在る。

### 6.2 BLEMMA の 3 点 (README と動画の頭に・3 つとも動画で実の操作を見せる = §9)
1. **先回り** = 問いが出る前にエージェントが `ask_board` で選択肢を作る。人は選ぶだけ。
2. **選択式の問いは同じ板で全部** = 権限・Claude 自身の質問・MCP の問い (elicitation) を 1 枚の板で。
3. **視線・スイッチ・片手・携帯の UI** = 滞留で押す 96px 以上の釦・固定の位置の釦・取り消し 3 秒 (1 鍵でも)・1 鍵の走査・同じ頁が携帯でも動く。
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

### 7.1 file の木 (repo の根 = `blemma/`)
```
blemma/
  board/server.py               127.0.0.1 の小さな HTTP・待ち行列・状態の確定・期限・token・Host・取り消し・記録
  board/static/index.html       板の頁 (1 枚)
  board/static/board.js         long-poll・滞留・キー・走査・世代・取り消し・計
  board/static/board.css        無地・高コントラスト・96px
  board/state/                  (git の外) run.json・log-*.jsonl
  hooks/_client.py              4 本の共通 = run.json を読む・POST /ask・GET /wait・失敗は全部 None
  hooks/permission.py           PermissionRequest → 板 → decision
  hooks/ask.py                  PreToolUse (AskUserQuestion) → 板 → updatedInput
  hooks/elicitation.py          Elicitation → 板 → action / content
  hooks/notify.py               Notification → 板 (光・音)
  mcp/blemma_mcp.py             MCP server (stdio・JSON-RPC 2.0 を自前で)・道具 ask_board
  skills/board/SKILL.md         作法 (§2.5)
  examples/settings.blemma.json hooks 4 本 + 許可の 1 行の雛形
  examples/mcp.blemma.json      同梱の MCP server の雛形
  tests/                        pytest (試験だけ pytest・成果物は標準ライブラリだけ)
  docs/                         設計・裏取り
  README.md (JA + EN) / LICENSE (MIT)
```
- Python 3.10 以上・標準ライブラリだけ (`json`・`sys`・`os`・`pathlib`・`urllib.request`・`http.server`・`threading`・`secrets`・`time`・`webbrowser`)。Windows / mac / Linux。提出版の handler は command 型だけ。
- hook は `_client.py` を同じ dir から import する (script の dir は `sys.path` の頭)。

### 7.2 設定の雛形 (11/2 以後に `examples/` に作る・ここでは文書の中だけ)
`examples/settings.blemma.json` (`<BLEMMA>` = clone した場所の絶対パス・`<PY>` = mac / Linux は `python3`、Windows は `python.exe` の絶対パス):
```json
{
  "permissions": { "allow": ["mcp__blemma__ask_board"] },
  "hooks": {
    "PermissionRequest": [
      { "matcher": ".*",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["<BLEMMA>/hooks/permission.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: waiting on the board" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["<BLEMMA>/hooks/ask.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: waiting on the board" } ] }
    ],
    "Elicitation": [
      { "matcher": ".*",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["<BLEMMA>/hooks/elicitation.py"],
                     "timeout": 600, "statusMessage": "BLEMMA: waiting on the board" } ] }
    ],
    "Notification": [
      { "matcher": "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
        "hooks": [ { "type": "command", "command": "<PY>", "args": ["<BLEMMA>/hooks/notify.py"],
                     "timeout": 10 } ] }
    ]
  }
}
```
`examples/mcp.blemma.json`:
```json
{ "mcpServers": { "blemma": { "command": "<PY>", "args": ["<BLEMMA>/mcp/blemma_mcp.py"] } } }
```
- `permissions.allow` の `mcp__blemma__ask_board` = 無いと ask_board を呼ぶたびに権限の札が先に出る (札が 2 重)。MCP の道具の名 = `mcp__<server>__<tool>` (裏取り §1.3)。
- `onFailure` は書かない (§5.1)。`timeout` 600 を変える時は §3.4 の 3 つを一緒に直す。
- 使い方は 2 通り: ①**どの settings.json も書き換えずに** `claude --settings examples/settings.blemma.json --mcp-config examples/mcp.blemma.json` で起こす (試し・デモの既定。旗の名と形はこの裏取りの外 = 初日の確かめ 5・効かなければ隔離したデモ用の project の設定で) ②利用者が自分の `.claude/settings.json` と `.mcp.json` に写す (README の手順)。
- hook は起動時に読まれる (第三者の README・裏取り §3.4) = 設定を変えたら `claude` を起こし直す。初回は Claude Code の信頼の確かめが出る (人が 1 回押す)。
- Windows: `python.exe` の路は `py -3 -c "import sys; print(sys.executable)"` で引いて `<PY>` に書く (exec 形は `.exe` 必須 = "On Windows, exec form requires `command` to resolve to a real executable such as a `.exe`."・裏取り §1.3【断片】)。
- 形の出典: 3 段の形・`args`・`timeout`・`statusMessage`・matcher の規則 = hooks.md【断片】(裏取り §1.3)。`.mcp.json` の `mcpServers` の形は公式の mcp 頁 (この裏取りは elicitation の節だけ読んだ = 書き手の知識・初日の確かめ 3 の前提)。

### 7.3 試験と検収
- **自動の試験** (偽の Claude Code = stdin に JSON を流す・偽の頁 = HTTP で answer を打つ): hook の入出力の契約 (4 本 × 答え・断り・固定の位置の釦・端末で・期限・板なし・壊れた入力・範囲外の番号 → 公式の JSON か空・exit 0)・server の状態の確定 (§3.5 の全部の遷移・§3.6 の優先の順・§3.4 の数)・token と Host・ask_board の JSON-RPC (initialize・tools/list・tools/call の中の elicitation/create の往復・decline / cancel・capability なし)。自動の試験は pytest (実行の手順は README に書く)。
- **皿ごとの検収** (11/3・11/4) は実の `claude` で、完成版の hook の出力を Claude Code に解釈させる (偽の答えで済ませない)。
- **完成版の異常の経路の実機の検収** (11/5・実の `claude` と実のブラウザ): ①端末先着 (§3.7 の (a) か (b) の通りに閉じる) ②板先着 ③待機中の server 停止 ④2 件同時 (待ち行列と 2 件目の期限) ⑤2 画面からの競合 (PC と携帯で同時に押す) ⑥スイッチの取り消し (1 鍵で猶予のうちに)。6 つとも §3.5 の表の状態と頁の文になること。
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
| 11/6 (金) | README (日本語が本体 + 英語の要約・差別化 3 点・テーマ・SDK の 1 節・計画の承認は板で出さない・選択式の範囲・通信の範囲・止められる範囲)・雛形・外部のレビュー 1 巡 (読むだけ・並行) → 直す + 録りの稽古 (尺 2:50・日本語の字幕) + 提出フォームの欄の下書き (概要の文) | 外の目の HIGH 0・稽古 1 回 | セッション⑤ |
| 11/7 (土) | **録り本番** (退化は別の撮り)・日本語の字幕・動画 v1 → 頭から終わりまで再生して確かめる (音と絵の同期) | 3 分 (2:50 前後) の動画 v1 | ライブ⑥ (録画で後から) |
| 11/8 (日) | 直し・動画 v2 (要れば)・**提出は 15:00 目標** (締切 20:00 の 5 時間前) → View Submission・別の口座でリンクの再生・repo の公開を確かめる。**提出の後は repo を動かさない** | 提出の受付・確かめ 3 つ | **締切 20:00** |
| 11/9 (月)〜11/10 (火) | 何もしない (11/10 13:00〜14:00 = 最終・クロージング) | — | 一次審査・最終 |

- 11/3 は文化の日 (祝日)。11/2 は 12:00 からの半日 = キックオフと門と確かめと分岐だけ。
- 失った余白 = v1.1 の「11/6 台本の通しと直しの 1 日」と「11/9〜10 の直しの 1.5 日」。代わりに通しを 11/5 の夜へ、稽古を 11/6 へ寄せた。
- 皿が延びたら、分岐 (§10.2) の縮小の側を先に選ぶ。**11/7 の録りと 11/8 15:00 の提出は動かさない**。11/6 の README が延びたら外部のレビューは録りの後 (11/8 午前) へ。

---

## 9. 3 分のデモの台本 (v1.2 = すべて日本語・尺 2:50 前後・冒頭 30 秒に 3 点とテーマ)

- 規約 (参加者ガイド・主催の PDF): 提出資料も含めてすべて日本語 / 動画は 3 分・審査員は制限時間で視聴を止める = 最も重要な点を冒頭に / 期間中に作った機能・コード・実装**のみ**を紹介し、審査員が「イベント中に作られたもの」を判別できないと失格 / スライドの発表は不可・実際に動いている所を中心に / 1080p 以上・全画面・タスクバーを隠す・録る前に通知を止める。
- 画面 = 左に板の頁 (ブラウザ)・右に端末 (`claude`)・板の右上に計。携帯の画面は場面の時だけ差し込む。作り手の個人の画面・通知・部屋は映さない (v1 の判断)。**画面の隅の札** (v1.2) = 場面ごとに「BLEMMA (期間中に作った物)」「OS の視線入力 (既存)」「Claude Code 本体 (既存)」の 3 種から当たる物を小さく出す = 審査員が期間中の物を判別できる。
- 仕事 = ダミーの公開 repo (**日本語の README**・v1.2 = 規約の「すべて日本語」) の誤字を直して commit。誤字 2 か所と表記の揺れ 1 つ (候補 = サーバー / サーバ) を**同じ 1 文**に置く (Edit が 1 回で済む)。ダミーの CLAUDE.md に「迷う所は AskUserQuestion か ask_board で訊く」の 1 行 (= Claude の質問が自然に出る)。ダミー repo の README の文案は前に用意してよい (文書)・repo とその設定は 11/5〜11/6 に作る (期間中の物)。訊かれるのを Edit と `git commit` だけにする許可の行 (`git add`・`git status`・`git diff`) は稽古 (11/6) で決める。
- 冒頭の 1 行 = デスクトップの shortcut (OS の視線クリック 1 回) が `claude --settings … --mcp-config … "README.md の誤字を直して commit して"` を開く。v0 の「板の定型の釦から 1 行」は公式の口が無い (研究版の Channels か 5 本目の Stop の hook が要る・v1 の判断)。字幕で「起動は視線クリック 1 回 (板の計の外)」と書く。
- 声 = 先に合成した日本語の声 (作り手の手元の TTS・repo の外・**BLEMMA の機能として見せない** = 隅の札にも出さない) を重ねる・**字幕は日本語** (提出資料はすべて日本語 = 英語の字幕は付けない)。録り = 作り手の PC の画面を 1 本 (OBS か ffmpeg の gdigrab・1080p 以上・全画面・タスクバーを隠す・通知を止める)。録りの `claude` は隔離した設定の dir で起こす (作り手の個人の hooks・statusline を映さない = §10.1 の 5)。声の文は案 (11/7 の録りの前に作り手が直す)。
- 冒頭 30 秒で言う物 = テーマ 2 (操作の壁・§1) と 3 点 (§6.2) = 0:00 の題の 1 行にテーマ 2・0:12〜0:25 の声に 3 点 (外部のレビュー 11/1 の指摘で入れた)。語りの並び (壁の外側の具体的なひとり = 視線の作り手が先 / 携帯・片手・視線の 3 人が先) は台本の精査で決める (割れたら作り手に 1 札) = 下の 0:00〜0:12 の声は v1.1 の案のまま。

| 秒 | 画面 | 声 (案) |
|---|---|---|
| 0:00〜0:12 | 題「BLEMMA — gaze-board」・屋号・一言・テーマ 2 の 1 行・3 点の字幕 (先回り・同じ板・視線とスイッチと携帯)。板と端末を並べた絵 | 「ビュプロです。わたしは視線だけで打ちます。今日は BLEMMA で、目だけで仕事を 1 つ仕上げます」 |
| 0:12〜0:25 | shortcut を視線で押す (OS の 1 回・隅の札「OS の視線入力 (既存)」) → 端末で Claude Code が README を読む | 「Claude Code に頼むのは、起動の 1 回だけ。問いは先回りの選択肢ごと 1 枚の板に出て、視線・スイッチ・携帯で答えます」 |
| 0:25〜0:35 | **AskUserQuestion** = 板に「表記を揃えます: サーバー / サーバ」の 2 択 → 視線で「サーバー」(10 秒) | 「Claude の質問も、板に大きな釦で出ます」 |
| 0:35〜1:05 | Edit の権限 → 視線で「許可 (今回)」→ 取り消しの猶予の数え → 端末で Edit が進む | 「権限の確認は視線 1 回。押し間違えても 3 秒のうちに取り消せます」 |
| 1:05〜1:30 | Bash (`git commit`) の権限 → **スイッチ 1 鍵の走査**で「次から訊かない: Bash(git commit …) — この project・この機械で恒久」を選ぶ | 「スイッチ 1 つでも同じ板です。次から訊かない、も選べます」 |
| 1:30〜2:00 | エージェントの `ask_board` の「次の一手」3 択 (PR の本文を書く / 試験を回す / ここで止める) → **携帯の画面**で「ここで止める」に触れる | 「問いが出る前に、エージェントが選択肢を用意します。携帯からも選べます」 |
| 2:00〜2:15 | 計 =「押し N (視線 a・スイッチ b・触る c)・送った答え M・経過」(録りの実測をそのまま) | 「Claude Code の公式の仕組み、hooks に乗っているだけで、本体は改造していません」 |
| 2:15〜2:40 | **退化 (別の撮り)** = 板の server を止めた状態で、2 つ目の shortcut が別の頼み (例「README の最後に 1 行足して」= Edit の権限が要る) で `claude` を起こす → 権限の確認が端末のいつもの dialog に出る (隅の札「Claude Code 本体 (既存)」) | 「板が無ければ、いつもの Claude Code のままです」 |
| 2:40〜2:50 | 締め | 「視線、スイッチ、片手、携帯で使う人へ届けます」 |

- 計の数は台本に決め打ちしない (録りの実測を出す)。板の計は板の押下だけ。冒頭と退化の撮りの shortcut は OS の側の操作として字幕と隅の札に別に書く。
- 3 点 (先回り・同じ板・視線とスイッチと携帯) は 3 つとも実の操作で映る。commit の場面の説明は短くした。尺は 2:50 で切り、3:00 までの 10 秒は余白 (審査員が止める前に締めが入る)。

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

---

## 11. 決め

### 11.1 決まっている事
- 名 = BLEMMA (gaze-board・視線の板)・MIT・Python 3.10 以上の標準ライブラリだけ (試験だけ pytest)・Windows / mac / Linux。
- この repo (11/2 に作った新しい repo・§11.4 の 6) に個人情報・鍵・作り手の環境の路は 1 バイトも入れない・デモの repo と本文はダミー。
- code は 11/2 12:00 から (それまでは設計と台本だけ)。public 化は作り手の go (11/2 以後)。
- 線 3 本 (§1)・127.0.0.1・起動ごとの token・記録は選択と時刻と数だけ。
- 提出版の handler は command 型に固定 (外部のレビュー 1 巡目を受けた)。
- デモの仕事 = README の誤字を直して commit。名乗りは屋号「ビュプロ」だけ。
- 作り手の手元の環境 (音声・手元の画面) との繋ぎは期間の外・この repo に入れない。

### 11.2 v1 と v1.1 で書き手が決めた事 (実装で覆してよい・覆したらこの file を直す)
- 釦 = 許可 (今回)・次から訊かない (対象と保存期間・モードの切り替えは別の字)・拒否 (定型 3)・固定の位置の釦 (口ごとの字と意味・§4.3)・端末で答える (96px 以上)。
- 板は選択式の問いだけ・自由記述と入力の直しは端末へ (候補の釦と最小の打鍵の道で補う・§4.3)。
- 板に出さない物 = ExitPlanMode・plan mode の権限・URL mode・描けない schema・`bypassPermissions` へ移す suggestion・除外の表の道具。
- server の口・choice は番号だけ・`seq` で古い画面を断る・token の見出し・Host の照合・待ち 20 件 (§3.3)。
- 期限と数 (§3.4)・札の状態と終わり 5 つの排他 (§3.5)・優先の順 (§3.6)・`/resolve` は 1 対 1 の鍵がある時だけ (§3.7)。
- 表示の世代で滞留と選択を解く・1 鍵の取り消し (§4.2)。
- 携帯は利用者の転送 (LAN に bind しない・§4.4)・計は押下と送った答えを分ける (§4.5)。
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

## 12. 未確定の一覧 (外部のレビューの振り分けを受けて 3 段に)

### 12.1 (i) 引用で確定 = 本文に移して未確定から外した物 (4 件)
- v1 の #1 = PermissionRequest の deny と `updatedPermissions` の契約 (欄の定義で確定・公式に無いのは完成した例だけ・§2.1)。
- v1 の #8 の matcher = `.*` で全部に当たる (正規表現の規則・§2.0・§2.3・§7.2)。
- v1 の #9 の Claude Code の側 = 2025-11-25 までの stdio の server に elicitation を宣言する (v2.1.287 以降・§2.5)。
- v1 の #13 の事実 = `requiresUserInteraction` の道具は allow で確認を飛ばせない (§2.1)。
- 別に、v1 の #11 (http 型・外部のレビューの分類は (iii)) は未確定のまま提出版の外へ移した (§5.6)。

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
