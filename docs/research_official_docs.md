# BLEMMA 準備の裏取り (2026-10-30)

> **この文書はハッカソン (Built with Claude: Japan 2026・2026-11-02 12:00 JST 開始) の前 (2026-10-30) に書いた公式 doc の裏取りです** (設計 `design.md` が「裏取り §x.y」で引く物)。§5 の規約の推測は 10/31 に参加者ガイドで覆った (§5.3 に訂正)。 実装は 11/2 12:00 以後に新しく作る。

2026-10-30 に読んだ (書き手 = 作り手の Claude Code のサブエージェント)。目的 = 「Built with Claude: Japan 2026」(Cerebral Valley × Anthropic、11/2 (月) 12:00 〜 11/10 (火) 14:00 JST、Remote、10/30 に参加承認) に出す BLEMMA (視線の板 = Claude Code の権限の確認・MCP の問い・先回りの選択肢を、視線入力の利用者が大きな釦の板で 1 回の注視で答える OSS) の準備。以前の調べ (非公開の作業メモ) は重複させず、新しい事実だけを足す。第三者の個人名は載せない (OSS は作品名と URL のみ)。

依頼の項目と節の対応: 項目 1 (hooks) = §1 / 項目 2 (MCP elicitation) = §2 / 項目 3 (権限の UI・modes・外に委ねる口) = §3 / 項目 4 (Agent SDK) = §4 / 項目 5 (イベントの規約) = §5 / 項目 6 (過去の傾向) = §6 / まとめと初日の確認 = §7 / 出典と未確認 = §8。

札の凡例 (信頼度の順):
- 【raw】公式頁の生 markdown を保存ファイルで Read した。逐語として使える。
- 【断片】WebFetch の要約器が返した逐語の断片。別の頁・別の取得と整合した物は「整合」と付す。
- 【報告】GitHub issue など利用者の報告。公式の文書ではない。
- 【二次】ニュース・ブログ。
- 推測 = 出典の無い読み。未確認 = 取れなかった / 書かれていない。

## §0 結論 (先に)

1. **板へ答えを出させる公式の口は 3 本 + 1 本**。①settings.json の hooks (command / http / mcp_tool) ②Agent SDK の `canUseTool` / `onElicitation` ③Channels の permission relay (research preview) ④Remote Control の one-tap。対話の `claude` をそのまま使うなら主経路は①。視線専用の公式機能は無い (accessibility 頁は screen reader・拡大鏡・動きの低減・色覚の theme・ベルまで)。
2. **3 種類の問いは 3 つの別の口で答える** (名前は今も合っている):

| 問い | hook | 答えの欄 |
|---|---|---|
| 権限の確認 | `PermissionRequest` | `hookSpecificOutput.decision.behavior` = `allow` / `deny` (+ `updatedInput` / `updatedPermissions` / `message` / `interrupt`) |
| Claude の質問 (`AskUserQuestion`、2〜4 択) | `PreToolUse` (matcher `AskUserQuestion`) | `permissionDecision: "allow"` + `updatedInput` に元の `questions` と `answers` (`allow` だけでは足りない) |
| MCP サーバーの問い (elicitation) | `Elicitation` | `hookSpecificOutput.action` = `accept` (+ `content`) / `decline` / `cancel` |

3. **安全弁は公式の仕様に在る**: タイムアウト・無出力・http の非 2xx / 接続失敗は「判断なし」= 端末の通常の確認に戻る。`PermissionRequest` は exit 2 も無効 (拒否は `decision` で返す)。板が落ちても Claude Code は止まらない。
4. **非対称に注意**: `Elicitation` hook は、利用者の【報告】(#103115) では hook が待っている間は端末の form が出ない。`PermissionRequest` は同報告で端末の dialog が同時に出て早い者勝ち。公式 doc には後者の同時表示の文が無い = 初日に実機で確かめる。
5. **既知の不具合 (open)**: `ExitPlanMode` を `PermissionRequest` の `allow` で飛ばせない回帰が 3 件 (v2.1.199 以降)。計画の承認は板で答えにくい恐れ → 初日に確認。
6. **規約は公式の頁にも報道 4 本にも無い** (→ §5.3 の訂正 10/31・11/1 = ログイン後の参加者ガイドと主催の回答で確定した): 着手時期・既存 code の持ち込み・提出物・提出先・審査基準・OSS の条件・Discord は全部「未確認」。4.6 の写し ("from scratch"・全部 OSS) は日本回に当たるか未確認。承認後に来る案内 (メール・Discord) で確かめる。
7. **新しい入賞傾向は無い** (10/14 以降に Anthropic 系の新しい回の受賞は見つからず)。権限承認の OSS の先行例は在る (§6) = 差別化は「選択肢を先回りで作る」と「視線向けの板」。

## §1 Claude Code の hooks の今の仕様 (2026-10-30)

### 1.1 版と取得の仕方

- 最新 = **v2.1.314** (2026-10-30T01:06:26Z)。直近 = v2.1.312 (10/27)・v2.1.311 (10/26)・v2.1.310 (10/23)。出典 https://github.com/anthropics/claude-code/releases.atom 【raw (XML)】
- hooks の公式頁 = https://code.claude.com/docs/en/hooks.md (283,467 字。WebFetch は 100,000 字ごとにしか読めない。`offset` を 100000・200000 と付けると続きが読める。200000 以降は生の markdown が保存ファイルに落ち、Elicitation 節・Stop 節を逐語で読めた)。
- 補助 = hooks-guide https://code.claude.com/docs/en/hooks-guide.md 【raw】、Agent SDK の hooks https://code.claude.com/docs/en/agent-sdk/hooks.md 【raw】。

### 1.2 hook の種類 (33 件、名前は今も合っている)

見出しの列挙と「Hook lifecycle」の表の 2 経路で 33 件が一致した。【断片】整合。出典 https://code.claude.com/docs/en/hooks.md (Hook lifecycle の表)。

SessionStart・Setup・UserPromptSubmit・UserPromptExpansion・PreToolUse・**PermissionRequest**・PermissionDenied・PostToolUse・PostToolUseFailure・PostToolBatch・**Notification**・MessageDisplay・SubagentStart・SubagentStop・TaskCreated・TaskCompleted・**Stop**・StopFailure・TeammateIdle・InstructionsLoaded・ConfigChange・CwdChanged・DirectoryAdded・FileChanged・WorktreeCreate・WorktreeRemove・PreCompact・PostCompact・PreModelSwitch・PostModelSwitch・**Elicitation**・**ElicitationResult**・SessionEnd。

BLEMMA に関わる行の「発火」の逐語 (表の When it fires):
- PermissionRequest = "When a tool call needs a permission decision"
- PreToolUse = "Before a tool call executes. Can block it"
- Notification = "When Claude Code sends a notification"
- Elicitation = "When an MCP server requests user input during a tool call"
- ElicitationResult = "After a user responds to an MCP elicitation, before the response is sent back to the server"
- Stop = "When Claude finishes responding"
- UserPromptSubmit = "When a prompt is submitted, before Claude processes it."

SDK 側の対応 (Agent SDK hooks 頁の表、【raw】): PermissionRequest・Notification・PreToolUse は Python / TypeScript とも Yes。**Elicitation・ElicitationResult は Python = No、TypeScript = Yes**。Python の `HookEvent` は 10 種 (PreToolUse・PostToolUse・PostToolUseFailure・UserPromptSubmit・Stop・SubagentStop・PreCompact・Notification・SubagentStart・PermissionRequest)【raw】。

### 1.3 settings.json での配線・matcher・handler・timeout・順

**配線の形** (3 段 = イベント → matcher の組 → hook の定義)【断片】:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "if": "Bash(rm *)", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh", "args": [] }
        ]
      }
    ]
  }
}
```

- 置き場所: `~/.claude/settings.json` (全プロジェクト)・`.claude/settings.json` (プロジェクト、commit 可)・`.claude/settings.local.json`・管理ポリシー・プラグインの `hooks/hooks.json`・skill / subagent の frontmatter。`/hooks` は読み取り専用。`disableAllHooks: true` で全停止。【断片】(プラグインの `hooks/hooks.json` は hooks-guide の Limitations 節にも出る【raw】)
- 同じ handler が複数の設定ファイルにあれば 1 回だけ実行: "If you define the same handler in more than one settings file, it runs once." 【断片】
- **同じイベントの hook は並列**: "When an event fires, its matching hooks run in parallel." 【断片】 SDK 頁 (【raw】): "For permission decisions, the most restrictive result applies. One hook's `deny` blocks the tool call." 順序は保証されない: "Because completion order is non-deterministic, write each hook to act independently".
- **matcher の評価**: "Only letters, digits, `_`, `-`, spaces, `,`, and `|`" は完全一致 (`|` か `,` 区切りの一覧)、それ以外の文字を含めば "JavaScript regular expression, unanchored"。matcher を持たないイベントに付けても "silently ignored"。【断片】
- イベント別の matcher の対象 (表の行、【断片】): PreToolUse / PostToolUse / PermissionRequest / PermissionDenied = tool name (例 `Bash`・`Edit|Write`・`mcp__.*`)、**Notification = notification type**、**Elicitation = MCP server name** (ElicitationResult も同じ)、UserPromptSubmit・Stop = matcher 無し (毎回発火)。MCP の tool 名は `mcp__<server>__<tool>`。
- `if` は "Only evaluated on tool events: PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, and PermissionDenied"。他のイベントでは "a hook with `if` set never runs"。【断片】

**handler の種類 (type)** = `command` / `http` / `mcp_tool` / `prompt` / `agent` の 5 つ。【raw】hooks.md の "Prompt-based hooks" 節:
- "`PermissionRequest` supports `command`, `http`, `mcp_tool`, and `prompt` hooks but not `agent` hooks. If you configure an agent hook on this event, Claude Code skips it and the permission flow proceeds unchanged. To allow or deny from a hook, return the decision object from a command or HTTP hook."
- PreToolUse・Stop・UserPromptSubmit は 5 種すべて。**Elicitation・ElicitationResult・Notification は `command` / `http` / `mcp_tool` の 3 種** (prompt・agent は不可)。

**共通の欄** (【断片】): `type` (必須)・`if`・`timeout`・`statusMessage`・`once` (skill の frontmatter だけ)・`onFailure` ("continue" 既定 / "block"、v2.1.295 以降)。
**timeout**: "Defaults: 600 for `command`, `http`, and `mcp_tool`; 30 for `prompt`; 60 for `agent`." UserPromptSubmit・PreModelSwitch・PostModelSwitch は 30、MessageDisplay は 10 に下がる。SessionEnd は全体で 1.5 秒。単位は秒。上限の記載は読んだ範囲に無い。(hooks-guide の Limitations 節【raw】も同じ数字。)
**http の欄** (【断片】): `url` (必須)・`headers` (環境変数は `allowedEnvVars` に挙げた物だけ展開)・`onFailure`。設定の例に `"url": "http://localhost:8080/hooks/pre-tool-use"` が在る。`allowedHttpHookUrls` が設定されていれば URL が許可リストに合う物だけ実行 (管理側の設定。既定は未確認)。
**http の応答の扱い** (【断片】): "HTTP hooks use HTTP status codes and response bodies instead of exit codes and stdout." / "To block a tool call or deny a permission, return a 2xx response with a JSON body containing the appropriate decision fields." / 2xx で空 = 成功 (exit 0 で無出力と同じ) / 2xx で JSON = command hook と同じ schema で解釈 / **2xx で JSON でない本文・非 2xx・接続失敗 = 非ブロッキングのエラー (処理は進む)**。
**mcp_tool の欄** (【断片】): `server`・`tool`・`input` (`${tool_input.file_path}` のように hook の入力から代入可)。"Claude Code reads the tool's text content the same way it reads command-hook stdout" = tool の text が 1 つの JSON object ならその hook の出力になる。`isError: true` は非ブロッキングのエラー。PreToolUse・Stop など止められるイベントでは、接続中のサーバーを `MCP_TIMEOUT` まで待つ。OAuth は hook からは始めない。
**command の形** (【断片】): exec 形 (`command` + `args`) は "No shell tokenization happens on any platform."、**"On Windows, exec form requires `command` to resolve to a real executable such as a `.exe`."**。shell 形の既定は "Defaults to "bash", or to "powershell" on Windows when Git Bash isn't installed." Windows の実例 (Elicitation 節、【raw】): `"command": "powershell.exe", "args": ["-NoProfile","-ExecutionPolicy","Bypass","-File","${CLAUDE_PROJECT_DIR}/.claude/hooks/answer-project-key.ps1"]`。

→ BLEMMA への含意: 板は常駐の小さなローカル server (localhost) にして、hook は `http` か `mcp_tool` で呼ぶのが Windows でいちばん素直 (shell の引用符問題が出ない)。注視は遅いので timeout を既定 600 秒より長く取る (上限は未確認 = 初日に確かめる)。

### 1.4 hook が受け取る JSON (stdin) と返せる JSON (stdout) の共通の決まり

出典 https://code.claude.com/docs/en/hooks.md ("Hook input and output" 節)。

**共通の入力欄** (【断片】): `session_id`・`prompt_id`・`transcript_path`・`cwd`・`scratchpad_dir`・`permission_mode` (default / plan / acceptEdits / auto / dontAsk / bypassPermissions。Manual は "arrives as "default", never as "manual"")・`effort`・`hook_event_name`・`agent_id` / `agent_type` (subagent の中だけ)。

**出力の決まり** (【断片】):
- "Exit 0 means success, and is the intended exit code when you print JSON for structured control." / "Print nothing but the JSON object to stdout." (他の行が混じると JSON と読まれない。シェルの profile が echo する行も壊す)。
- 共通の出力欄: `continue` (false で処理全体を止める)・`stopReason`・`suppressOutput` (効果なし)・`systemMessage` (利用者への警告)・`terminalSequence` (OSC 0/1/2/9/99/777 と BEL だけ。デスクトップ通知用)。
- exit code 2 の効きはイベントごとに違う (表)。**PermissionRequest は "Exit code 2 isn't honored for this event and the permission flow proceeds unchanged."、"Deny through the `decision` object instead"**。Elicitation は "Declines the request, and no dialog appears"、ElicitationResult は "Blocks the response (action becomes decline)"、Notification は "Exit code and stderr are ignored"、PreToolUse は "Blocks the tool call"。

→ 含意: 板の server が http で JSON を返す形なら「stdout に余計な行が混じる」事故が起きない。拒否は exit 2 でなく JSON の `decision` / `action` で返す。

### 1.5 権限の確認を hook で答える = `PermissionRequest`

事実 (【断片】、出典 hooks.md の PermissionRequest 節。入出力の欄は Python SDK の `PermissionRequestHookInput` 【raw】と一致):
- 発火: "Runs when Claude Code is about to ask you for permission to use a tool." / hooks-guide (【raw】): "Claude Code runs `PermissionRequest` hooks when it's about to ask you for permission, and if your hook returns `"behavior": "allow"`, Claude Code answers the request on your behalf." / "The transcript shows "Allowed by PermissionRequest hook" where the dialog would have appeared."
- matcher = "Matches on tool name, same values as PreToolUse."
- 入力: "`tool_name` and `tool_input` fields like PreToolUse hooks, but without `tool_use_id`" / MCP の tool には `mcp_server` / 任意の `permission_suggestions` (Claude Code が勧める許可の更新の配列):

```json
{
  "session_id": "abc123", "transcript_path": "/Users/.../00893aaf-....jsonl", "cwd": "/Users/...",
  "permission_mode": "default", "hook_event_name": "PermissionRequest",
  "tool_name": "Bash",
  "tool_input": { "command": "rm -rf node_modules", "description": "Remove node_modules directory" },
  "permission_suggestions": [
    { "type": "addRules", "rules": [{ "toolName": "Bash", "ruleContent": "rm -rf node_modules" }],
      "behavior": "allow", "destination": "localSettings" }
  ]
}
```

- 出力 (公式の例は allow の 1 つだけ。**deny 版の JSON 例は公式頁に無い** = 2 回の取得で一致):

```json
{ "hookSpecificOutput": { "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow", "updatedInput": { "command": "npm run lint" } } } }
```

  欄: `behavior` ("`"allow"` grants the permission, `"deny"` denies it.")・`updatedInput` (allow のみ。実行前に入力を差し替える)・`updatedPermissions` (allow のみ。許可の更新の配列)・`message` (deny のみ。"tells Claude why the permission was denied")・`interrupt` (deny のみ。"if `true`, stops Claude")。
- **「常に許可」も返せる**: hooks-guide の例 (【raw】) は `"updatedPermissions": [ { "type": "setMode", "mode": "acceptEdits", "destination": "session" } ]`。許可の更新の種類は `addRules`・`replaceRules`・`removeRules`・`setMode`・`addDirectories`・`removeDirectories` の 6 つ、`destination` は `session` / `localSettings` (.claude/settings.local.json) / `projectSettings` / `userSettings`。`setMode` の mode は `default`・`auto`・`acceptEdits`・`dontAsk`・`bypassPermissions`・`plan` (と `default` の別名 `manual`)。`bypassPermissions` は起動時に bypass が使える時だけ効き、`defaultMode` としては保存されない。【断片】
- **exit 2 は無効**: "A hook that exits 2 without a `decision` object leaves the permission flow unchanged, and its stderr is discarded." 【断片】
- 非対話: hooks-guide の Limitations (【raw】): "`PermissionRequest` hooks fire when Claude Code is about to ask you for permission, or when it would otherwise auto-deny a call that can't prompt. In non-interactive mode with the `-p` flag, they still run outside `dontAsk` mode, and a call that no hook decides and nothing else can answer is denied."
- ホストとの先着 (【断片】): "For a call that reaches a `--permission-prompt-tool` or the Agent SDK's `canUseTool` callback, the hooks run alongside your host, and whichever decides first applies."
- 狭く絞る: "Matching on `.*` or leaving the matcher empty would auto-approve every tool permission prompt" (【raw】、allow を返す hook の場合の注意)。
- `agent` 型の hook は使えない (上の 1.3)。

→ 含意: 板は hook の入力 (`tool_name` / `tool_input` / `permission_suggestions`) から「許可」「今回だけ」「常に許可」「拒否」の大きな釦を作り、`behavior` を返す。MCP の tool は `_meta["anthropic/requiresUserInteraction"]` が付いた物だけ hook の `allow` で飛ばせない (§3.4)。

### 1.6 Claude の質問と計画の承認 = `PreToolUse` で答える (AskUserQuestion / ExitPlanMode)

事実 (【断片】、PreToolUse 節。SDK 頁の形【raw】と整合):
- "`AskUserQuestion` and `ExitPlanMode` require user interaction." / hook が満たす手順 = 入力を stdin から読む → "Collects the answer through your own UI" → `permissionDecision: "allow"` と答えを入れた `updatedInput` を返す。**"Returning "allow" alone is not sufficient for these tools."**
- `AskUserQuestion` の入力 = "Asks the user one to four multiple-choice questions." 欄は `questions` (各 `question`・`header`・`options` [`label`・`description`]・`multiSelect`)。`answers` は "Optional. Maps question text to the selected option label." / "Claude doesn't set this field; supply it via `updatedInput` to answer programmatically"。
- 答えの形:

```json
{ "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "allow",
    "updatedInput": {
      "questions": [ { "question": "Which framework?", "header": "Framework",
        "options": [ {"label":"React","description":"Component library"}, {"label":"Vue","description":"Progressive framework"} ],
        "multiSelect": false } ],
      "answers": { "Which framework?": "React" } } } }
```

- 質問の制限 (Agent SDK の user-input 頁、【raw】): "each `AskUserQuestion` call supports 1-4 questions with 2-4 options each"、`header` は "Short label for the question (max 12 characters)"、複数選択の答えは label の配列か ", " 区切り、自由記述は `answers[question]` に利用者の文を入れる。subagent の中では `AskUserQuestion` は使えない: "`AskUserQuestion` is not currently available in subagents spawned via the Agent tool"。
- `permissionDecision` の 4 値: `allow` ("skips the permission prompt, except for actions no mode auto-approves")・`deny`・`ask` ("prompts the user to confirm")・`defer` ("ends the turn so the tool can be resumed later"、`-p` のみ)。複数 hook が食い違えば **deny > defer > ask > allow** (SDK 頁【raw】も同じ)。exit 2 は deny と同じ。
- `defer` = `claude -p` を子プロセスで動かす統合向け。"`"defer"` only works when Claude makes a single tool call in the turn." 結果は `stop_reason: "tool_deferred"` と `deferred_tool_use`、`claude -p --resume <session-id>` で再開。保存は 既定 30 日。SDK 頁 (【raw】): 答えに時間がかかるなら `canUseTool` で待たず `defer` を使う。
- MCP の tool が `_meta["anthropic/requiresUserInteraction"]` を付けていれば "a hook can't skip its approval prompt with "allow", with or without `updatedInput`"。
- **PreToolUse の hook は許可の dialog より前に走る** (permissions 頁【raw】): "PreToolUse hooks run before the permission prompt, for every tool except `EndConversation`. The hook output can deny the tool call, force a prompt, or skip the prompt to let the call proceed." ただし hook の `allow` は deny / ask の規則を超えない (同頁 "Precedence among rules, hooks, and mods")。
- plan mode では `ExitPlanMode` 以外の編集には hook の `allow` が効かない (同頁 "Hook approvals in plan mode"【raw】)。

→ 含意: 「Claude が先回りで 3〜4 個の選択肢を作る」は **Claude Code が既に持っている `AskUserQuestion` (2〜4 択・header 12 字) をそのまま板にする**のが公式の形。CLAUDE.md で「判断が要る所は AskUserQuestion で 2〜4 択にする」と書けば、選択肢の生成は Claude の仕事のまま (以前の調べ (非公開の作業メモ)の「モデルの使い方」)。自由記述 (Other) は注視の文字盤が要る = 板の別画面。

### 1.7 MCP の問いを hook で答える = `Elicitation` / `ElicitationResult`

**ここは生の markdown で読めた【raw】** (hooks.md の Elicitation 節)。

- 発火: "Runs when an MCP server requests user input mid-task. By default, Claude Code shows an interactive dialog for the user to respond. Hooks can intercept this request and respond programmatically, skipping the dialog entirely." matcher = MCP server 名。
- 入力: 共通欄 + `mcp_server_name`・`message`、任意の `mode` (`form` / `url`)・`url`・`elicitation_id`・`requested_schema`。form の例:

```json
{ "hook_event_name": "Elicitation", "mcp_server_name": "my-mcp-server",
  "message": "Please provide your credentials", "mode": "form",
  "requested_schema": { "type": "object", "properties": { "username": { "type": "string", "title": "Username" } } } }
```

  url の例は `"mode": "url", "url": "https://auth.example.com/login"`。
- 出力 (exit 0 で `hookSpecificOutput` に `action`):

| したい事 | 返す | サーバーが受け取る |
|---|---|---|
| 利用者の代わりに答える | `"action": "accept"` + `content` (form の欄の値) | `accept` と `content` |
| 断る | `"action": "decline"` | `decline` |
| 取り消す | `"action": "cancel"` | `cancel` |
| 利用者に任せる | 出力なしで exit 0 | dialog での利用者の答え |

  `content` の鍵は `requested_schema.properties` の名前。dialog では **Decline の選択 = `decline`、`Esc` = `cancel`**。URL mode で `accept` を返すと dialog が出ず URL は開かない。"Claude Code discards `reason`, `systemMessage`, and `continue` from an Elicitation hook's JSON output, whichever `action` you return."
- 断る別の手: exit 2 (同じ hook の `hookSpecificOutput` は無視) / トップの `"decision": "block"` (同じ出力の `action` に勝つ)。複数 hook なら "a decline from one of them overrides an `accept` or `cancel` from another"。どちらも "Neither the user nor the server sees why your hook declined"。**v2.1.105〜v2.1.284 の間は `Elicitation` / `ElicitationResult` のトップの `decision` が無視された** (v2.1.284 で修正) = v2.1.284 以降を前提にする。
- ElicitationResult: "Runs after a user responds to an MCP elicitation." 利用者が答えた後、サーバーに返す前に、値を変える (`accept` + 新しい `content`)・止める (`decline`)・取り消す (`cancel`)。**"When an Elicitation hook answers a request, Claude Code sends that answer to the server without running ElicitationResult hooks."** 利用者が decline / cancel した時も走り、`action` が利用者の物を置き換える (accept を返す前に入力の `action` が `accept` かを確かめる)。`content` は丸ごと置き換え。
- 動作確認: `claude --debug` のログに `Elicitation resolved by hook: {"action":"accept","content":{...}}`。
- 通知側: Notification の型に `elicitation_dialog` ("An MCP server opens an elicitation form and you haven't typed for about six seconds")・`elicitation_url_dialog`・`elicitation_complete`・`elicitation_response`。【断片】

【報告】 GitHub issue #103115 (open、2026-10-18、feature 要望) の本文の断片: "Claude Code awaits every Elicitation hook before it draws the form" / "While a hook runs, the terminal shows the tool's card" / "PermissionRequest hooks do not have this problem: for AskUserQuestion the dialog is drawn at once and stays answerable at the terminal while a PermissionRequest hook runs, and whichever answer comes first wins". = **Elicitation は hook が待つ間は端末に form が出ない**。公式 doc の「出力なし = dialog」と矛盾はしない (hook が終わってから dialog) が、待ち時間の長い板では端末側が無反応に見える。

→ 含意: 板の Elicitation hook は「待つ上限 (例: 数十秒)」を決め、答えが無ければ **出力なしで exit 0** にして端末の form に戻す。`requested_schema` の `enum` / `oneOf` + `title` を大きな釦に、`boolean` を 2 釦に、`string` は注視の文字盤か「あとで」(= cancel) にする。

### 1.8 板を起こす・次の一手を差し込む = `Notification` / `Stop` / `UserPromptSubmit`

- **Notification** は止められず (“Notification hooks can't block or modify notifications.”)、answer は返せない。【断片】型 (matcher) = `permission_prompt`・`idle_prompt` (応答後 約 60 秒操作なし)・`auth_success`・`elicitation_dialog`・`elicitation_url_dialog`・`elicitation_complete`・`elicitation_response`・`agent_needs_input`・`agent_completed`・`quota_auto_resume_fired` / `_stale` / `_disabled`・`plugin_notification`。入力は `message`・任意の `title`・`notification_type`。**`permission_prompt` は端末では「約 6 秒入力が無い時」に発火** ("Expect `permission_prompt` once you haven't typed for about six seconds."、打鍵のたびに延びる)。hooks-guide (【raw】): "Claude needs you to approve a tool use or a sandboxed command's network request, and the prompt has waited about six seconds"。→ 板の主経路にはならない (遅い)。主経路は PermissionRequest / PreToolUse / Elicitation。
- **Stop** (【raw】): 入力に `stop_hook_active`・`last_assistant_message`・`background_tasks`・`session_crons`。出力 = `"decision": "block"` + `reason` (Claude は止まらず `reason` を指示として続ける)、または `hookSpecificOutput.additionalContext` (非エラーの助言として続ける)。"Claude Code applies an 8-consecutive-continuation cap" (連続 8 回で打ち切り、`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` で上げられる)。→ **板で選んだ「次の一手」を、止まる前の Claude に `reason` / `additionalContext` として渡す公式の口**。`Stop` は応答が終わるたびに発火し、利用者の割り込みでは発火しない。
- **UserPromptSubmit** (【断片】): 入力に `prompt`。出力 = 文脈の追加 (`additionalContext`)・`decision: "block"`・`sessionTitle`。既定 timeout は 30 秒に下がる (長く待つなら timeout を明示)。
- 待機中のセッションへ新しい 1 手を差し込む別の公式の口は **Channels** (§3.4)。

出典 https://code.claude.com/docs/en/hooks.md (Notification・Stop・UserPromptSubmit の各節) と https://code.claude.com/docs/en/hooks-guide.md。→ 含意: 「先回りの選択肢」を板に出すのは Stop 後 (Claude が止まった時)・選んだ答えを渡すのは同じ Stop hook か AskUserQuestion の答え。Notification は板を起こす用途には遅い (6 秒・60 秒)。

### 1.9 失敗・タイムアウト時の挙動 (安全弁の根拠)

| 場面 | 結果 | 出典 |
|---|---|---|
| hook が timeout | "Claude Code cancels a `command`, `http`, or `mcp_tool` hook that reaches its `timeout`, discarding the hook's output, so on most events a timed-out hook renders no decision." | hooks.md Timeouts 【断片】 |
| PreToolUse の hook が timeout | "doesn't block the tool call" / "The call continues through the normal permission flow, so don't count on a stalled hook to act as a gate." (`onFailure: "block"` で止められる) | 同 |
| PermissionRequest が exit 2 / decision 無し | 流れは変わらず (= dialog に戻る) | 1.5 |
| http の非 2xx・接続失敗・JSON でない本文 | 非ブロッキングのエラー (処理は進む) | 1.3 |
| mcp_tool が `isError: true` / サーバー未接続 | 非ブロッキングのエラー | 1.3 |
| Elicitation で出力なし exit 0 | dialog に任せる | 1.7 【raw】 |
| Agent SDK の callback hook が timeout | PreToolUse は **ブロック** (shell の command hook と逆)、Stop は止まる、Notification は続行 | agent-sdk/hooks 【raw】 |

出典 https://code.claude.com/docs/en/hooks.md ("Timeouts"・"HTTP response handling"・"Exit code 2 behavior per event") と https://code.claude.com/docs/en/agent-sdk/hooks.md。→ 含意: 板が落ちても詰まない (Claude Code は通常の確認に戻る)。ただし PreToolUse の hook が詰まっても「止める門」にはならない = 板は門ではなく窓口。止めたい物は deny 規則か `onFailure: "block"` (v2.1.295 以降)。

### 1.10 既知の不具合 (GitHub、利用者の報告・2026-10-30 に API で確認)

`repo:anthropics/claude-code PermissionRequest hook in:title` = 62 件 (うち更新の新しい順に関係する物):

| # | 状態 | 作成 | 題名の要点 |
|---|---|---|---|
| 74256 | open | 2026-07-04 | `ExitPlanMode` の PermissionRequest `allow` が v2.1.199 以降で無視され、承認の chooser が出る (2.1.198 までは効いた) |
| 97656 | open | 2026-09-27 | `ExitPlanMode` の `allow` が dialog を飛ばさない回帰 (#15755 の再発、v2.1.283 で計測。bare の allow も `updatedPermissions` 付きも dialog が出た) |
| 90498 | open | 2026-08-29 | `ExitPlanMode` の `allow` は `updatedInput` を付けないと黙って無視される (2.1.246) |
| 90685 | open | 2026-08-30 | `systemMessage` が ExitPlanMode の承認で描かれない |
| 91216 | open | 2026-09-01 | `permission_suggestions` が dialog の実際の行と一致しない |
| 88698 | open | 2026-08-21 | `--bg` セッションで PermissionRequest の判断が捨てられる |
| 101334 | open | 2026-10-11 | Remote Control: hook が承認した後も iOS に ExitPlanMode の確認が残る |
| 103115 | open | 2026-10-18 | Elicitation hook の間は form が描かれない (要望、§1.7) |
| 13203 | closed (2026-02-06) | 2025-12-06 | VS Code 拡張で PermissionRequest hook が発火しない (labels: bug, platform:windows, area:ide) |

→ 含意: **`ExitPlanMode` を板で答えるのは危うい**。作り手は端末の `claude` を使う前提だが、計画の承認は初日に実機で確かめ、効かなければ PreToolUse + `updatedInput` の道 (1.6) か、端末の dialog に残す。これらは【報告】で、直した版・現状は未確認。

## §2 MCP の elicitation の仕様 (modelcontextprotocol.io)

### 2.1 版

仕様の版 = **2026-07-28 (最新の日付つき)**・2025-11-25・2025-06-18・draft (索引 https://modelcontextprotocol.io/llms.txt 【断片】)。elicitation の頁は 2025-06-18 以降。URL mode は 2025-11-25 で導入 ("URL mode elicitation is introduced in the `2025-11-25` version of the MCP specification")。Claude Code は **2026-07-28 と それ以前の両方**を扱う (§2.4)。

### 2.2 要求と応答の形 (2025-11-25 の版、【raw】 https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation.md)

- サーバーが `elicitation/create` を送る。全要求の params: `mode` (string、`form` / `url`、form は省略可で既定 form) と `message` (人に見せる説明)。
- form mode は `requestedSchema` (object) を足す。"To simplify client user experience, form mode elicitation schemas are limited to flat objects with primitive properties only." 許される型 = string (`minLength`・`maxLength`・`pattern`・`format` = email / uri / date / date-time)・number / integer (`minimum`・`maximum`)・boolean・enum。**enum は単一選択 (`enum` か `oneOf` [{`const`,`title`}]) と複数選択 (`type: array` + `items` の `enum` か `anyOf`)**。全型に `default`。"Clients that support defaults SHOULD pre-populate form fields with these values."
- 要求の例:

```json
{ "jsonrpc": "2.0", "id": 1, "method": "elicitation/create",
  "params": { "mode": "form", "message": "Please provide your GitHub username",
    "requestedSchema": { "type": "object", "properties": { "name": { "type": "string" } }, "required": ["name"] } } }
```

- 応答 (result) は 3 つの action: `{ "action": "accept" | "decline" | "cancel", "content": {...} }`。
  - **accept** = "User explicitly approved and submitted with data" (form は `content` に値、URL mode は `content` なし)
  - **decline** = "User explicitly declined the request" (例: Reject / Decline / No)
  - **cancel** = "User dismissed without making an explicit choice" (例: 閉じた・外を押した・Escape)
- URL mode は `mode: "url"` + `url` + `elicitationId`。応答の `accept` は同意で、完了ではない。サーバーは任意で `notifications/elicitation/complete` (`elicitationId` つき) を送れる。要求を続けられない時は `URLElicitationRequiredError` (code `-32042`)。
- 対応の宣言 (initialize の capabilities): `"elicitation": { "form": {}, "url": {} }`。空 `{}` は form のみと同じ。
- 利用者側の MUST (抜粋): "Provide UI that makes it clear which server is requesting information" / "Respect user privacy and provide clear decline and cancel options" / "For form mode, allow users to review and modify their responses before sending"。機密 (パスワード・API key・決済) を form で求めてはならない (URL mode を使う)。

### 2.3 2026-07-28 の版での変化 (【raw】 https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md)

- 要求は **`InputRequiredResult` の中の `elicitation/create`** として運ばれる ("Servers MAY request information from a user during the processing of a client request, by sending an `InputRequiredResult` containing an `elicitation/create` request.")。応答は **再試行の要求の `inputResponses`** に入れて返す (multi round-trip requests = MRTR)。`action` / `content` の形は同じ。
- capability の宣言は各要求の `_meta.io.modelcontextprotocol/clientCapabilities` に入れる (initialize ではない)。空 `{}` = form のみ、は同じ。
- URL mode の要求から `elicitationId` が消え、`requestState` を使う。

### 2.4 Claude Code の対応 (公式の記述、【raw】 https://code.claude.com/docs/en/mcp.md の "Respond to MCP elicitation requests")

- "MCP servers can request structured input from you mid-task using elicitation. When a server needs information it can't get on its own, Claude Code displays an interactive dialog and passes your response back to the server. No configuration is required on your side."
- **UI の形**: "**Form mode**: Claude Code shows a dialog with form fields defined by the server (for example, a username and password prompt). Fill in the fields and submit." / "**URL mode**: Claude Code asks whether to open a link in your browser." (URL は escape 後 約 8,000 字が上限で、超えると断ることしかできない。)
- 自動応答: "To auto-respond to elicitation requests without showing a dialog, use the `Elicitation` hook."
- 宣言: Claude Code は **`elicitation: {form: {}, url: {}}`** を、①プロトコル 2026-07-28 の接続、②それ以前 (2025-11-25 まで) の stdio / sse / http / ws の利用者設定の MCP server (v2.1.287 以降) で宣言する。claude.ai の connector 等は空 `elicitation: {}` (= form のみ)。Java MCP SDK 0.17.0 以前の server は両方入りの宣言を拒む場合がある。

→ 含意: 板が扱うべき最小の形は **flat な object の primitive**。enum (`oneOf` + `title`) が大きな釦にそのまま写る。MCP の server を自作する時 (BLEMMA が見せる「問い」の源) は `requestedSchema` を enum 中心にして、`default` を入れておけば 1 回の注視で終わる。

## §3 権限の確認の UI と `--permission-mode`・`permissions`・外に委ねる口

### 3.1 UI の形 (【raw】 https://code.claude.com/docs/en/permissions.md)

- 権限の確認は「何をしようとしているか」と選択肢を出す。Bash の例 (図の説明文): "titled Bash command ... asks 'Do you want to proceed?' with four options: Yes; Yes, and don't ask again for: npm test *; Yes, and switch to auto mode; and No. A footer lists two keys: Esc to cancel and Tab to amend." 第 3 の選択肢は全ての確認には出ない。確認が 1 回きりの承認だけを出す場合も在る ("no 'don't ask again' option")。
- 「Yes, and don't ask again」の保存先: Bash / WebFetch は `.claude/settings.local.json` (git の root) に恒久、ファイルの編集は「セッションの終わりまで」。
- 利用者の一言: **Yes / No の上で `Tab` を押すと comment 欄**。Yes = 実行後に comment を Claude へ、No = comment が拒否の理由。"If you select **No** without a comment on a prompt from the main conversation, Claude Code stops the turn."

### 3.2 `permissions` の allow / ask / deny (【raw】)

- "**Allow** rules let Claude Code use the specified tool without manual approval. **Ask** rules prompt for confirmation whenever Claude Code tries to use the specified tool. **Deny** rules prevent Claude Code from using the specified tool."
- 評価順: "Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order." deny の中の広い規則は狭い allow に勝つ。
- 書式 (settings.json): `"permissions": { "allow": ["Bash(npm run *)", "Bash(git commit *)"], "deny": ["Bash(git push *)"] }`。MCP は `mcp__<server>__<tool>`、allow の glob は `mcp__<server>__` の後ろだけ。
- Agent SDK 側の評価の 6 段 (【raw】 agent-sdk/permissions): **①hooks → ②deny 規則 → ③ask 規則 → ④permission mode → ⑤allow 規則 → ⑥`canUseTool`**。hook の `allow` は deny / ask を超えない。

### 3.3 `--permission-mode` と modes (【raw】 https://code.claude.com/docs/en/cli-reference.md と agent-sdk/permissions)

- `--permission-mode` = "Accepts `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`, or `manual` as an alias for `default`" (`manual` は v2.1.200 以降)。`--dangerously-skip-permissions` = `bypassPermissions` と同じ。`--enable-auto-mode` は v2.1.111 で廃止 ("Auto mode is now in the `Shift+Tab` cycle by default")。
- modes: `default` (確認が要る物は確認) / `dontAsk` (確認の代わりに拒否) / `acceptEdits` (編集とファイル操作を承認) / `bypassPermissions` (確認なし、ただし「どの mode も自動承認しない操作」を除く) / `plan` (編集は承認されない) / `auto` (分類器が実行前に審査して許可か拒否)。
- 非対話 (`claude -p`・Agent SDK) は `default` で始まり、確認が要る呼び出しは hook・許可規則・`canUseTool`・permission prompt tool が答えなければ**拒否**される。

### 3.4 確認を「外の UI」に委ねる公式の口 (視線入力で押しやすい代替) の比較

| 口 | 何を答えられる | 動く場面 | 弱点・条件 | 出典 |
|---|---|---|---|---|
| ①settings.json の hook (`PermissionRequest` / `PreToolUse` / `Elicitation`) | 権限の許可・拒否・常に許可、AskUserQuestion の答え、elicitation の accept / decline / cancel | 対話の `claude` ですぐ | ExitPlanMode に回帰 (§1.10)。hook は起動時に読まれる (第三者 README) | §1 |
| ②Agent SDK `canUseTool` (+ TS `onElicitation`) | 権限・AskUserQuestion・(TS) elicitation | 自作の app から Claude Code を動かす時 | 対話の `claude` 画面ではない。Python に elicitation の口は確認できず | §4 |
| ③Channels の permission relay | Bash / Write / Edit など tool の許可・拒否 | 対話の `claude` に MCP server を足す | research preview・`--dangerously-load-development-channels` が要る・claude.ai か Console の認証・MCP の 2026-07-28 を話す channel は v2 runtime で登録されない・MCP 同意 dialog と trust は中継されない・AskUserQuestion は対象外 (記載なし) | channels / channels-reference 【raw】 |
| ④Remote Control | 携帯・ブラウザから承認 ("let you approve tool calls with one tap") | 自分の PC の `claude` を遠隔で | Pro / Max / Team / Enterprise のみ・API key 不可・端末でしか描けない要求は one-tap が外れる | remote-control / mcp.md 【raw】 |
| ⑤`--permission-prompt-tool mcp__<server>__<tool>` | 非対話 (`-p`) の許可 | `claude -p` | `requiresUserInteraction` の tool は allow が deny に変えられる (v2.1.199 以降) | cli-reference 【raw】 |

Channels の詳細 (【raw】 https://code.claude.com/docs/en/channels-reference.md の "Relay permission prompts"):
- server が `capabilities.experimental['claude/channel/permission']: {}` を宣言すると、Claude Code が `notifications/claude/channel/permission_request` (params = `request_id` [a〜z から l を除く 5 文字]・`tool_name`・`description`・`input_preview`) を送る。返事は `notifications/claude/channel/permission` (`request_id` と `behavior: 'allow' | 'deny'`)。
- "When Claude calls a tool that needs approval, the local terminal dialog opens and the session waits. A two-way channel can opt in to receive the same prompt in parallel ... Both stay live: you can answer in the terminal or on your phone, and Claude Code applies whichever answer arrives first and closes the other."
- 注意: "anyone who can reply through your channel can approve or deny tool use in your session" = 送り手の確認 (allowlist) が要る。`-p` では channel の旗は無視される。
- 入力の側: channel は `notifications/claude/channel` で待機中のセッションへ**新しい 1 手を入れられる** (これが「次の一手」の板を端末に打たずに差し込む、公式のもう 1 つの口)。

### 3.5 Claude Code の accessibility の公式機能 (視線は記載なし)

【raw】 https://code.claude.com/docs/en/accessibility.md: screen reader mode (`--ax-screen-reader`・`CLAUDE_AX_SCREEN_READER=1`・`"axScreenReader": true`)。"In screen reader mode, menus you'd normally navigate with the arrow keys, including permission prompts, become numbered lists ... Type the number of the option you want and press Enter." 他に `CLAUDE_CODE_ACCESSIBILITY` (拡大鏡向けのカーソル)・`prefersReducedMotion`・色覚向け theme・`preferredNotifChannel: "terminal_bell"`。**eye tracking・switch・視線に触れる文は無い** (頁内の語の探索)。

→ 含意: BLEMMA の主張「キーボード前提の壁」は公式の accessibility の隙間 (screen reader 以外の入力手段) に当たる、と書ける。screen reader mode の「番号を打って Enter」は、視線の板が打鍵 1 回 (番号) に落とす案の下敷き (推測)。

## §4 Claude Agent SDK の `can_use_tool` / permission の callback (hooks で足りない時の道)

【raw】 https://code.claude.com/docs/en/agent-sdk/user-input.md と permissions.md。

- "Claude requests user input in two situations: when it needs **permission to use a tool** ..., and when it has **clarifying questions** (via the `AskUserQuestion` tool). Both trigger your `canUseTool` callback, which pauses execution until you return a response." / "**The callback can stay pending indefinitely.**" (長く待つなら `PreToolUse` の `defer`。)
- 型 (Python): `CanUseTool = Callable[[str, dict[str, Any], ToolPermissionContext], Awaitable[PermissionResult]]`。返り値 = `PermissionResultAllow(updated_input=..., updated_permissions=...)` か `PermissionResultDeny(message=..., interrupt=False)`。`ToolPermissionContext` = `signal`(予約)・`suggestions`・`tool_use_id`・`agent_id`・`blocked_path`・`decision_reason`・`title`・`display_name`・`description`。TS は `{ behavior: "allow", updatedInput, updatedPermissions }` / `{ behavior: "deny", message }` で、第 3 引数に `signal`・`suggestions`・`suppressAlwaysAllowRule` (Agent SDK v0.3.268 以降)。
- 返せる形: 承認・変更つき承認 (`updated_input`)・**承認して覚える** (`suggestions` を `updated_permissions` に返す、Python は `claude-agent-sdk` 0.1.80 以降)・拒否 (Claude に理由が見える)・代案の提示 (deny の message)・向きを変える (streaming input)。
- **`AskUserQuestion` も同じ callback に来る**。`input.questions` を見せ、`answers` = {質問文: 選んだ label} を `updated_input` に入れて返す。「Claude generates the questions and options. Your role is to present them to users and return their selections. You can't add your own questions to this flow」。TS は `toolConfig.askUserQuestion.previewFormat` (`"markdown"` / `"html"`) で選択肢に見本 (`preview`) を付けられる。
- **callback が呼ばれない場合**: allow 規則・`acceptEdits` / `bypassPermissions` で先に承認された呼び出し ("The callback never fires for auto-approved tools")。全呼び出しで効かせたいなら `PreToolUse` hook。`dontAsk` は拒否。TS の `permissionPrompts: 'none'` (v2.1.259 以降) では callback を呼ばず、`PermissionRequest` hook だけが決められる。
- **Python の落とし穴**: callback 用に stream を開けておく "Required workaround: dummy hook keeps the stream open for can_use_tool" (`hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[dummy_hook])]}` と `prompt_stream()`)。
- **MCP の elicitation**: TS の options に `onElicitation: (request: ElicitationRequest, options: { signal: AbortSignal }) => Promise<ElicitationResult>` ("Callback for handling MCP elicitation requests."、"When not provided, unhandled elicitation requests are declined automatically" 【断片】)。Python の `ClaudeAgentOptions` / `HookEvent` に elicitation の口は**確認できず** (HookEvent に Elicitation 無し【raw】。Options 側は頁の前半が要約器経由で「見えない」= 未確認)。Python で Elicitation を扱うなら settings-file の command / http hook で代替 (agent-sdk/hooks の注: SessionStart / SessionEnd も同様)。
- 通知: `permission_prompt` の Notification は SDK では「`canUseTool` で約 6 秒待たれた時」に発火 (TS v0.3.233・Python v0.2.139 以降)。

→ 含意: hooks で足りない場面 (Python から elicitation、`-p` の無人実行) は SDK / `defer` の道。ただし「利用者が普段の `claude` 画面で作業する」形にするなら hooks が本線。デモ用に「板だけで動く別の入口」(SDK 製) を足すのは範囲外の拡張 (推測)。

## §5 イベントの規約 (Cerebral Valley の頁と報道)

### 5.1 公式の頁の事実 (https://cerebralvalley.ai/e/built-with-claude-japan2026、3 回の取得で一致、【断片】)

- 題 "Built with Claude: Japan 2026"。日時 "11月2日(月) 12:00〜11月10日(火) 14:00"、GMT+9。"完全オンラインで開催します。" (gallery の副頁は "Nov 2, 2026 · Remote" のみ)。主催 = Cerebral Valley + Anthropic。
- 対象 = 日本在住。**チームは 2 名まで。チームで参加する場合も全員の応募と選考が必要**。参加者は 250 名 (選考あり)。
- 特典 = 参加者 1 名につき **Max 5x Plan と $500 の Claude API クレジット**。入賞者には総額 **$50,000 (約 8,000,000 円) 相当の Claude API クレジット**。
- 審査員 = 「近日発表」。応募締切 = 10 月 26 日 23:59 (日本時間)。「ハッカソンから生まれたプロジェクトと開発者は、Anthropic から世界に向けて紹介される予定」。
- 頁の見出しは「概要」と「注意事項」の 2 つだけ。href は /events・/search・/auth/login・/u/cv・/u/anthropicai のみ。**ルール・FAQ・審査基準・提出・Discord・OSS の見出しは無い**。

### 5.2 二次の報道 (【二次】、2026-10-14〜21)

- GameBusiness 10/21 https://www.gamebusiness.jp/article/2026/10/21/28404.html: "初めてコードに触れるプログラミング未経験者も応募可能" / "参加は個人または最大2名までのチームで可能です" / "審査員の詳細は後日発表される予定です" / "2026年11月10日（火）オンライン上で発表予定" (結果の発表)。
- techno-edge 10/14 https://www.techno-edge.net/article/2026/10/14/5584.html: 締切は "米国太平洋時間では同日午前7時59分"、応募は CV のイベント頁から (CV のアカウント作成が必要)、賞は "現金ではありません"、作る物の出発点は「本人が最もよく知る領域」。
- st-hakky 10/17 https://book.st-hakky.com/en/news/claude-hackathon-november: "aged 18 and older" (年齢 18 歳以上はこの 1 本だけ。他は記載なし)、"The distribution of prizes based on ranking has not been disclosed."
- smartscope 10/14 https://smartscope.blog/blog/claude-code-japan-hackathon-max-credits-2026/: 未確認と明記された項目 = Max 5x の使える期間・特典の付与日・既存の有料プラン契約者の扱い・API クレジットの有効期限と失効条件・詳細な参加規約・年齢制限・選考基準。

### 5.3 依頼の項目ごとの答え

| 項目 | 結果 |
|---|---|
| ⭐ code を書き始めてよい時期 (期間中だけか・事前の設計や既存 code の持ち込み) | **未確認**。CV の頁・報道 4 本のどれにも文が無い。 |
| チームの人数 | 2 名まで (全員が応募・選考)。 |
| 提出の形 (repo・動画・デモ・提出先 portal・締切の時刻) | **未確認**。応募の締切は 10/26 23:59 JST だが、提出の締切は 11/10 14:00 が期間の終わり (推測、提出の締切が別かは未確認)。 **→ 訂正 (2026-10-31・ログイン後の参加者ガイドで確定): 提出の締切は 11/8 (日) 20:00 JST。11/10 14:00 は期間の終わり (11/9 一次審査・11/10 13:00〜14:00 最終)。提出 = 概要 + 3 分の動画のリンク + 公開 repo・すべて日本語。主催の回答 (2026-11-01): 期限以降の編集は不可・期間前の設計の文書 (code なし) は開始後に作る repo に入れてよい・自作の開発環境 (設定・skill・hooks) は使ってよい (成果物に含めない)。** |
| 審査の基準 | **未確認**。審査員も「近日発表」。 |
| 賞 | 入賞者に総額 $50,000 の API クレジット (現金でない)。順位ごとの内訳は未公表。 |
| Max の付与 | 選ばれた 250 名に Max 5x + $500 の API クレジット。期間・付与日・既存契約者の扱いは未確認。 |
| Discord・コミュニティの案内 | **未確認** (頁に無い)。 |
| 公開の条件 (OSS・ライセンス) | **未確認**。"Anthropic が世界に紹介" とだけ。 |

### 5.4 参考 = 4.6 の規則の写し (日本回に当たるかは未確認)

出典 https://huggingface.co/datasets/introvoyz041/postvisit/blob/main/data/docs/hackathon-rules.md (冒頭の注記 "Source: Official event page (Cerebral Valley / Anthropic), pasted 2026-02-11"、今日再取得して一致、【断片】):
- "All projects must be started from scratch during the hackathon. No pre-existing work."
- "Everything shown in the demo must be fully open source" ... "under an approved open source license."
- 提出 = 動画 "**3-minute maximum** (YouTube, Loom, or similar)"・"GitHub repository or code link (public)"・要約 "100–200 words"・"Submit via Cerebral Valley platform"。
- チーム "Up to 2 members. Solo OK."。審査 "Stage 1 — Async judging" → "Stage 2 (Live)"。基準 = Demo 30 / Impact 25 / Opus 4.6 Use 25 / Depth & Execution 20。
- 既存のライブラリ・フレームワーク・事前の設計の使用可否に触れる文は無い (禁止事項に "uses code/data/assets without rights")。
- 他の回の頁 (Life Sciences、https://cerebralvalley.ai/e/built-with-claude-life-sciences) も、規則の文は無い (500 名・2 名まで・Max 20x 1 か月 + $200・"All participants must submit an application for approval" のみ)。

### 5.5 BLEMMA への含意と次の手

- 4.6 の規則どおりなら「期間中に from scratch」「全部 OSS」「3 分の動画」。**11/2 12:00 より前に BLEMMA の code を書き始めるのは危うい** (推測)。準備として許される範囲 = 公式 doc の読み・設計の紙・試作でない確認 (本調べ) まで、と読むのが安全 (未確認)。BLEMMA の hook 試作を 11/2 以前に走らせたい時は先に主催へ確かめる。
- 確かめる先: 10/30 の承認の案内 (メール・Discord)・CV のアカウントの画面・参加者向けの規約。聞く文面の案 (短く):「(1) 11/2 12:00 より前の設計メモ・調査は可か。既存の自作の道具立て (設定・skill) の持ち込みは可か。(2) 提出物 (repo・動画) の形と提出先、締切の時刻。(3) 公開の条件 (OSS・ライセンス)。(4) 既に Max 契約がある場合の特典の扱い。」

## §6 過去の入賞傾向 (以前の調べ (非公開の作業メモ)に足す新しい事実だけ)

- **新しい受賞は見つからず**: 10/14 以降に Anthropic 系の新しい回 (Opus 5 系・Fable・Sonnet 5.5 の回) の受賞は、検索で出なかった。以前の表 (非公開の作業メモ・7 回・28 件) が最新。
- **日本回の背景 (報道)**: 日本版は参加 250 名・賞 $50,000 = 世界版 (500 名・$100,000) の約半分。Claude Code のハッカソンとして初の日本向けオンライン (GameBusiness 10/21 の見出し)。未経験者も可。
- **権限承認の先行例 (OSS)**: ①claude-remote-approver https://github.com/yuuichieguchi/claude-remote-approver (MIT、star 73、README 逐語 "Approve or deny Claude Code permission prompts from your phone." / PermissionRequest hook + AskUserQuestion / ntfy.sh で携帯へ / "the hook falls back to the **CLI prompt** (`ask`)" [timeout 時]) 【断片、README 直読】 ②claude-board https://pypi.org/project/claude-board/ ("Physical console for Claude Code - approve/deny permissions from your phone or hardware device"、0.3.21、2026-03-03。**頁内でライセンスが MIT と AGPL で食い違う**。物理の釦は計画段階) 【断片】 ③claude-push・cc-remote-approval は WebSearch の要約だけ = 未検証。
  → 含意: 「携帯で承認」は既にある。BLEMMA の差は **(1) 選択肢を Claude が先回りで作る (AskUserQuestion の板) (2) MCP の問い (Elicitation) まで板で答える (3) 視線・スイッチ向けの大きな釦と dwell・誤操作の設計 (4) 作り手本人が、期間中に実装した板を視線で操作して実証する計画 (未実施)** (推測)。
- **視線 / AAC の Claude 系ハッカソンの入賞**: 検索で見つからず (Claude 系では不在。別系の hackathon に視線の例は在る)。以前の「受賞に無い物」の判断 (非公開の作業メモ)を変えない。
- **東京の Code with Claude 拡張セッション**: 「Claude Code hackathon で 1 週間・単独で、2.8 億人向けの国の法律の platform を作った」創業者の登壇が在る (https://claude.com/code-with-claude/session/tyo-ext-legal-platform-280-million 、受賞か否かは記載なし)。弱い情報。

## §7 BLEMMA の設計への含意 (まとめ) と初日に確かめる事

### 7.1 構成の素案 (推測・未検証。公式の形に沿った書き下ろし)

```json
{
  "hooks": {
    "PermissionRequest": [
      { "hooks": [ { "type": "http", "url": "http://127.0.0.1:8765/permission", "timeout": 3600 } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion",
        "hooks": [ { "type": "http", "url": "http://127.0.0.1:8765/ask", "timeout": 3600 } ] }
    ],
    "Elicitation": [
      { "hooks": [ { "type": "http", "url": "http://127.0.0.1:8765/elicit", "timeout": 60 } ] }
    ]
  }
}
```

- 板の server は localhost の常駐。hook は応答を保留し、注視の答えを JSON で返す (http の 2xx + JSON)。落ちている・遅い時は「判断なし」で端末の確認に戻る (§1.9)。
- 先回りの選択肢: ①Claude 自身が `AskUserQuestion` で 2〜4 択を作る (CLAUDE.md で促す) → 板が答える ②止まる前の `Stop` hook が板の選択 (次の一手) を `reason` / `additionalContext` で返す (連続 8 回の上限) ③待機中のセッションへは Channels で入れる (research preview)。
- 板の選択を利用者が自分の許可の規則に残す口は、`permission_suggestions` の `addRules` / `destination` を使う「次から訊かない」の釦が下敷きになる (自動では許可の範囲を広げない・推測)。

### 7.2 初日に実機で確かめる事 (公式 doc だけでは決まらない)

| # | 確かめる事 | 理由 |
|---|---|---|
| 1 | `PermissionRequest` の hook が待つ間、端末の dialog が同時に出るか (早い者勝ちか) | 公式に文が無い。#103115 の報告のみ |
| 2 | `ExitPlanMode` の `allow` が dialog を飛ばすか (v2.1.314 で) | open の回帰 3 件 (#74256・#97656・#90498) |
| 3 | `AskUserQuestion` を `PreToolUse` の `allow` + `updatedInput.answers` で答えられるか。`PermissionRequest` でも答えられるか | 公式の例は PreToolUse のみ |
| 4 | `Elicitation` hook が待つ間の端末の見え方と、待つ上限の置き方 | #103115 |
| 5 | http hook の localhost・`timeout` の上限 (3600 秒が通るか)・`allowedHttpHookUrls` の既定 | 上限と既定は未確認 |
| 6 | Windows で http / exec 形 (`.exe`) が通るか。command なら `powershell.exe` + `args` | 公式: exec 形は `.exe` 必須 |
| 7 | hook の読み込み時期 (起動時のみか)、`--bg`・IDE 拡張・Remote Control で発火するか | 第三者 README / #88698 / #13203 / #101334 |
| 8 | MCP の問いを出す server を 1 つ用意して、`requested_schema` の enum が実際にどう渡るか | 公式の例は username 1 欄だけ |
| 9 | `permission_suggestions` が dialog の行と一致するか | #91216 |

### 7.3 範囲外・触れていない物

視線の板の UI 側 (dwell 時間・誤操作の防止・視線入力の機器との連携)、Python SDK の elicitation の口の最終確認、`--bg` セッション、Claude Desktop・IDE 拡張での発火。

## §8 出典・取得の注意・食い違い・未確認

### 8.1 出典

公式 doc (Claude Code):
- hooks https://code.claude.com/docs/en/hooks.md / hooks-guide https://code.claude.com/docs/en/hooks-guide.md
- mcp https://code.claude.com/docs/en/mcp.md / permissions https://code.claude.com/docs/en/permissions.md / permission-modes https://code.claude.com/docs/en/permission-modes.md (前半のみ)
- cli-reference https://code.claude.com/docs/en/cli-reference.md / accessibility https://code.claude.com/docs/en/accessibility.md
- channels https://code.claude.com/docs/en/channels.md / channels-reference https://code.claude.com/docs/en/channels-reference.md / remote-control https://code.claude.com/docs/en/remote-control.md
- Agent SDK: user-input https://code.claude.com/docs/en/agent-sdk/user-input.md / permissions https://code.claude.com/docs/en/agent-sdk/permissions.md / hooks https://code.claude.com/docs/en/agent-sdk/hooks.md / python https://code.claude.com/docs/en/agent-sdk/python.md / typescript https://code.claude.com/docs/en/agent-sdk/typescript.md (前半のみ)
- 索引 https://code.claude.com/docs/llms.txt
MCP の仕様:
- https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md / https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation.md / 索引 https://modelcontextprotocol.io/llms.txt
イベント:
- https://cerebralvalley.ai/e/built-with-claude-japan2026 (と /hackathon/gallery)・二次は §5.2・4.6 の写しは §5.4
GitHub:
- https://github.com/anthropics/claude-code/releases.atom ・ issues #13203 #74256 #88698 #90498 #90685 #91216 #97656 #100419 #101100 #101334 #103115 (api.github.com/repos/anthropics/claude-code/issues/<番号> と search API)

### 8.2 取得の注意 (読み手が値を使う時の札)

- 【raw】の範囲 = Elicitation / ElicitationResult / Stop の節 (hooks.md の 200000 字以降の保存ファイル)・hooks-guide・mcp.md の elicitation と requiresUserInteraction・permissions.md の抜粋・Agent SDK 3 頁と Python 頁の型・channels 2 頁・remote-control 抜粋・accessibility・cli-reference 抜粋・MCP 仕様 2 版。
- 【断片】の範囲 = hooks.md の最初の 200,000 字 (イベント表・matcher 表・共通欄・http / mcp_tool の欄・exit code の表・Timeouts・PermissionRequest・Notification・PreToolUse)・CV の頁・TS SDK 頁の前半。PermissionRequest の入出力は Python SDK の型と hooks-guide の例で裏が取れた。
- **要約器の混入**: hooks.md の "PreToolUse `ask` decisions in auto mode" 節の要約に、頁に無い語 (私の道具の名前に見える語) が混じった。その節の要約は不採用。他の断片は別の頁と照合できた物だけ採った。
- WebSearch の要約は、OSS 3 件の名前と機能に使っただけで、README / PyPI を直読した 2 件以外は未検証と書いた。

### 8.3 食い違い・未確認の一覧

- 食い違い: ①claude-board の頁内ライセンス (MIT と AGPL-3.0-or-later) ②年齢の条件 (st-hakky = 18 歳以上 / 他は記載なし) ③`PermissionRequest` と端末 dialog の同時表示 (公式に文なし / #103115 の報告は同時)。
- 未確認: Python SDK の elicitation の口・http hook の timeout の上限・`allowedHttpHookUrls` の既定・上の §7.2 の 9 項目・permission-modes 頁の後半 (117,027 字のうち 100,000 字まで)・TS SDK 頁の後半 (329,464 字のうち 100,000 字まで)・イベントの規約の全て (§5.3)・Max 5x の期間と既存契約者の扱い・日本回の提出の形。
