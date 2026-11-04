# BLEMMA — gaze-board (視線の板)

> **Built with Claude: Japan 2026** (2026-11-02 12:00 〜 11-08 20:00 JST) の作品。この README は repo を作った時点 (2026-11-04) の仕様 = **設計 (docs/design.md) に書いた予定**です。code は 11/2 12:00 以後に書き、作った物に合わせて期間中にこの README を直します。

## 一言で

Claude Code が人に訊く瞬間 (権限の確認・Claude 自身の質問・MCP の問い・待ちの合図) と、エージェントが先回りして用意した「次の一手」の選択肢を、**大きな釦の板**に出して、**視線 1 回** (スイッチ 1 回・片手 1 押し・携帯 1 タップ) で答えて進める OSS です。Claude Code 本体は改造しません。公式の hooks と MCP の elicitation に乗るだけです。

## テーマと、誰のための物か

テーマ 2「**本来、誰にでも届くべきものを。**」— BLEMMA が取り払う壁は**操作の壁**です。Claude Code は仕事の途中で何度も人に訊きます。どれも端末の小さな dialog に出て、矢印キーと Enter で答える形なので、視線・スイッチ・片手では狙いにくく、結局は打鍵が要ります。

壁の外側にいる具体的なひとり = **視線だけで打つ作り手本人**。同じ板が、机を離れた人 (携帯)・両手が塞がった人 (片手)・スイッチで操作する人にも届きます。

## BLEMMA の 3 点

1. **先回り** — 問いが出る前に、エージェントが同梱の MCP の道具 `ask_board` で選択肢を作ります。人は選ぶだけ。
2. **選択式の問いは同じ板で全部** — 権限の確認・Claude 自身の質問・MCP の問い (elicitation) を 1 枚の板で。
3. **視線・スイッチ・片手・携帯の UI** — 滞留 (dwell) で押す 96px 以上の釦・固定の位置の釦・押した後 3 秒の取り消し (1 鍵でも)・1 鍵の走査・同じ頁が携帯でも動く。

## 作り (予定・設計 v1.2)

公式の hooks 4 本 + 同梱の MCP server 1 つ + 127.0.0.1 だけの小さな板 (HTTP・Python の標準ライブラリだけ)。

| Claude Code の口 | hook | 板に出る物 | 板から返す物 |
|---|---|---|---|
| 権限の確認 | `PermissionRequest` | 道具と入力の要点・釦 = 許可 (今回)・次から訊かない (対象と保存期間つき)・拒否・作業を止める・端末で答える | `decision.behavior` (allow / deny) + `updatedPermissions` など |
| Claude 自身の質問 (`AskUserQuestion`) | `PreToolUse` (matcher `AskUserQuestion`) | 2〜4 択の釦 | `allow` + `updatedInput` (元の質問と答え) |
| MCP の問い (elicitation) | `Elicitation` | enum → 釦・boolean → 2 つの釦 | `action` (accept + content / decline / cancel) |
| 待ちの合図 | `Notification` | 板が光る (音・携帯は任意) | 何も返さない (観察だけ) |
| 先回りの「次の一手」 | 同梱の MCP server `blemma` の道具 `ask_board` | エージェントが用意した 2〜6 択 | elicitation の答え |

- 板が答えるのは**選択式の問い**だけです。自由記述と入力の直しは端末へ戻します (候補の釦と最小の打鍵の道で補います)。
- 計画の承認 (`ExitPlanMode`)・plan mode の権限・URL の問いは板に出しません。

## 安全と退化

- **公式の口だけに乗る** — Claude Code 本体の fork・patch・端末への打鍵の注入はしません。
- **板が無ければ退化** — 板が居ない・時限を過ぎた・壊れた時、hook は判断を返さず (無出力・exit 0)、Claude Code の通常の判断の流れに委ねます。いつもの確認が端末に出ます。
- **勝手に許可しない** — 人が板で選んだ時だけ allow を返します。時限・不明・誤り = 判断なし (allow でも deny でもない)。
- 板は 127.0.0.1 だけ・起動ごとの token・記録は選択と時刻と数だけ (問いの本文は残しません)。携帯で見る時は利用者の転送 (例 `adb reverse`) で届け、LAN には bind しません。
- 作業全体を止められるのは権限の口の「作業を止める」だけです。質問の口と MCP の口の釦は、その問いを閉じるだけです。

## 使い方 (予定)

Python 3.10 以上・標準ライブラリだけ・Windows / mac / Linux。

```
claude --settings examples/settings.blemma.json --mcp-config examples/mcp.blemma.json
```

どの `settings.json` も書き換えずに hooks と MCP server を足して起こします。自分の設定に写す手順と、hooks の雛形は期間中に `examples/` に置きます。

## 工程

11/4 repo を作って初日の確かめ → 11/4〜11/5 板の server と頁・4 本の口・`ask_board`・スイッチと携帯・実機の検収 → 11/6 README と外の目 → 11/7 デモの録り → 11/8 提出 (毎日 push)。

## 期間前に書いた文書について

`docs/` の設計の文書 (`design.md`・`research_official_docs.md`) は、ハッカソンの開始 (2026-11-02 12:00 JST) より前の 2026-10-14〜11-01 に書いた物です (各 file の冒頭に日付)。開始前には code を 1 行も書いていません。BLEMMA の実装・試験・実行用の設定は 2026-11-02 12:00 JST 以後に新しく作ります。この repo の git の記録で区別できます = 最初の commit (tag `pre-event-docs`) が期間前の文書の区切りで、実装は以後の履歴に入ります (以後の履歴には文書の直しも含みます)。tag `pre-event-docs` の時点では実装は未着手です。期間前の文書を含めることは、主催者に事前に確認しました (2026-11-01)。

## 文書

- `docs/design.md` — 設計 v1.2 (口の契約・板の server・頁・安全と退化・作り・工程・デモ・初日の確かめ・未確定の一覧)
- `docs/research_official_docs.md` — 公式 doc の裏取り (Claude Code の hooks・MCP の elicitation・権限の UI・Agent SDK) と、読んだ日と出典

## License

MIT (see LICENSE).

---

## In short (EN)

**BLEMMA** (Greek βλέμμα, "a glance") puts every moment Claude Code asks a human — permission prompts, Claude's own questions (`AskUserQuestion`), MCP elicitations, "waiting for you" signals — and the agent's pre-prepared "next step" choices onto a **big-button board**, so the human answers with **one gaze** (or one switch press, one hand, one tap on a phone). Built only on the official hooks (`PermissionRequest`, `PreToolUse`, `Elicitation`, `Notification`) and MCP elicitation; Claude Code itself is not modified. Python 3.10+, standard library only, MIT.

Theme: "What should reach everyone, by right." The wall BLEMMA removes is the **operation wall** — the small terminal dialog and the keystrokes it demands. The one person outside the wall is the maker, who types with eye gaze alone; the same board reaches people away from the desk (phone), with one hand, or on a switch.

Three points: (1) **pre-emptive choices** — the agent prepares 2–6 options via the bundled MCP tool `ask_board` before the question appears; (2) **every selectable question on one board** — permissions, Claude's questions, MCP elicitations; (3) **gaze / switch / one-hand / phone UI** — dwell-pressed buttons ≥ 96px, fixed-position buttons, a 3-second undo (works with a single key), one-key scanning, the same page on a phone.

Safety: official hooks only; if the board is absent or times out, the hook returns nothing and Claude Code falls back to its normal prompt; **never auto-allow**; 127.0.0.1 only, per-launch token, logs keep only the choice, the time and counts.

**Pre-event documents:** the design documents under `docs/` were written before the hackathon started (Oct 14 – Nov 1, 2026; each file is dated). Nothing but documents existed before Nov 2, 12:00 JST — no code. All code, tests and config are created after the start, and the git history keeps them apart (the first commit, tagged `pre-event-docs`, is the documents-only baseline; the implementation lands in later commits, which may also update the documents). At the `pre-event-docs` tag, no implementation exists yet. Including the pre-event documents was confirmed with the organizers beforehand (Nov 1, 2026).

---

ビュプロ (BIW STUDIO) — https://biw.studio/
