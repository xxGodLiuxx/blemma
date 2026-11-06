# BLEMMA

このプロジェクト「BLEMMA」は、Claude Code を使う人の「確認に戻る手間」を、一瞥で選べる扇 (OhGi) に変える道具です。

Claude は作業の区切りで、次の一手を選択肢にして差し出します。権限の確認 (この操作をしてよいかの問い)・Claude の質問・MCP の問い (外部の道具からの問い) が同じ 1 枚の扇に出て、見つめるだけで選べます。

Claude Code 本体は改造しません。公式の hooks と MCP の elicitation (道具が人に訊く仕組み) に乗るだけです。

![左: 端末の小さな確認。右: 画面の隅の扇](docs/img/ohgi.png)

動画 (3 分): <提出時にリンクを置く>

BLEMMA はギリシャ語の βλέμμα (まなざし・一瞥) です。扇 (おうぎ・OhGi) は、画面の隅の小さな窓に選択肢を折り扇の羽根として開く見え方の名前です。[Built with Claude: Japan 2026](https://cerebralvalley.ai/e/built-with-claude-japan2026) のために作りました。

## テーマと、誰のためのものか

テーマ 2「本来、誰にでも届くべきものを。」に応えます。BLEMMA が取り払う壁は**操作の壁**です。

Claude Code は仕事の途中で何度も確認を求めます。確認は端末の小さな選択肢で、矢印キーと Enter で答えます。MCP の問いの form では、矢印キーと Space と Enter で 5 回の打鍵でした (作り手の実測・Claude Code v2.1.318)。

作り手は視線だけで PC を操作します。細い 1 行を目で狙うのは難しく、答えるまで仕事は進みません。BLEMMA はその確認を、画面の隅の扇に変えました。見つめて 1 秒、1 回で答えられます。スイッチ 1 つでも同じように選べます。

同じ壁は、端末から目を離して働く人の前にもあります。文書やブラウザを見ている間に Claude が確認を待っていて、端末へ戻って初めて気づきます。扇は画面の隅の小さな窓なので、確認が来たら一瞥して、その場で答えられます。片手で使う人にも、同じ入口が届きます。

## 5 分で試す

必要なもの: Python 3.10 以上 (試験は 3.10 と 3.13 で通しています)・ログイン済みの Claude Code (`claude` が端末から打てること)・Chrome か Edge (小さな窓に使います。無ければ既定のブラウザで開きます)。視線入力の機器は要りません (手 3)。

1. 取得します (zip で展開しても同じです)。

   ```
   git clone https://github.com/xxGodLiuxx/blemma
   ```

2. 使う project の folder で起動します。

   ```
   python <blemma を置いた所>/blemma.py
   ```

   **こう見えれば成功:** 画面の隅に小さな窓が開き、同じ端末で Claude Code が起きます。初回は folder の信頼の確認が端末に出るので、端末で答えます。

3. Claude に「次の一手を 3 つ、ask_board で出して」と頼みます (`ask_board` は同梱の道具の名前です。そのまま打てば通じます)。

   **こう見えれば成功:** 扇が開き、羽根に 一 二 三 四 が出ます (頼んだ 3 つと「ここで止める」)。羽根を見つめると全文が扇の内側に現れ、そのまま 1 秒で押されて、3 秒の取り消しの猶予の後に端末へ答えが返ります。視線入力が無くても、マウスを乗せて 1 秒待つか、数字キー 1〜6 で同じに押せます。

4. 「README.md の 1 行目に今日の日付を足して」のように、file を 1 か所直す頼みをします。

   **こう見えれば成功:** 権限の確認が扇に出ます。羽根の 一 (許可 (今回)) を押すと Edit が進みます。押した後の 3 秒は「取り消す」で戻せます。

終える時は Claude Code を `/exit` で閉じます。扇を動かしている PC の中の小さな server (以下「板」) も、`blemma.py` が起こしたものなら一緒に止まります。

大きなボタンの見え方で使う時は `python <blemma を置いた所>/blemma.py --large` です。明暗は窓の ☀ ☾ で切り替えられます。大きさ・字・配色・見つめる秒は、窓の歯車か `--set` で変えられます (例 `--set scale=1.25 --set theme=dark`)。

## うまくいかない時

| 起きる事 | 意味と、どうするか |
|---|---|
| 扇に何も出ず、端末に確認が出た | 正常です。板が動いていない・窓を閉じた・待ち時間 (既定 5 分・扇の要の上に残りの時間) を過ぎた時は、いつもの確認に戻ります |
| 権限の確認が扇に出ない | Claude Code の auto mode では権限の確認そのものが出ません。`blemma.py` は `--permission-mode default` (端末の帯に「manual mode on」) で起こします。帯が「auto mode on」なら、途中で mode を替えています |
| 文字で答える問いや計画の承認が扇に出ない | 扇が答えるのは選ぶ問いだけです。自由記述と計画の承認は端末で答えます |
| `blemma.py` が「打つ 1 行」を印字して終わった | `claude` が見つかりません。印字された 1 行を、`claude` が動く端末で打ちます |
| 「ポートが使用中」と出る | `python <blemma を置いた所>/blemma.py --port 8766` のように別の番号で起こします |
| 窓に「板の server に繋がりません」と出る | 板が止まっています。`blemma.py` を起こし直してください (窓も開き直します)。その間の確認は端末に出ます |
| 作業を全部止めたい | 権限の確認の「作業を止める」か、端末の Esc です。質問の「この質問に答えない」と MCP の「この問い合わせを閉じる」は、その問いを閉じるだけです |

## 安心の 3 行

- **勝手に許可しません。** 人が押した時だけ答えを返します。時間切れと異常は判断なしです。
- **板が無い時は、いつもの Claude Code です。** hook は何も返さず、端末のいつもの確認に戻ります。
- **外のサービスへ自動では送りません。** 板は 127.0.0.1 だけで待ち受け、起動ごとの token で守ります。記録は選択と時刻と数だけで、問いの本文は残しません。あなたの `settings.json` は書き換えません。

## BLEMMA の 3 点

1. **先回り** — Claude が作業の区切りで、次の一手を 2〜6 択で差し出します (同梱の MCP の道具 `ask_board` と skill `board`)。区切りごとに Claude に訊き返させる使い方でも、答える手間は一瞥 1 回です。Claude 自身が迷った時に訊く `AskUserQuestion` (2〜4 択) も同じ扇に出ます。板が無い時、`ask_board` の選択肢はいつもの form に出ます。
2. **選ぶ問いは全部 1 枚で** — 権限の確認・Claude の質問・MCP の問いが、同じ扇に同じ形で出ます。
3. **視線とスイッチで押せる** — 見つめて 1 秒で押す。スイッチ 1 つで走査して選ぶ。押した後 3 秒は取り消せる。「止」(作業を止める) と「端」(端末で答える) は親骨の左右で動かない。カードが替わった瞬間は押されない。読む所と押す所を分けた = 全文は押せない内側の帯に出るので、読む視線が他の羽根を押さない。

質問を小窓に集める道具や、携帯から承認する道具は先にあります。BLEMMA の芯は、Claude が次の一手を差し出す所と、3 種の問いを視線とスイッチで押せる 1 枚にまとめた所です。

## 携帯から答えたい時

板は PC の中だけで動きます。携帯から Claude Code を動かす道としては、公式の [Remote Control](https://code.claude.com/docs/en/remote-control) があります。BLEMMA の板を携帯に出すものではありません。

## しくみ (開発者向け)

公式の hooks 6 本 + 同梱の MCP server 1 つ + 127.0.0.1 だけの小さな板 (HTTP・Python の標準ライブラリだけ)。

| Claude Code の入口 | hook | 扇に出るもの | 返すもの |
|---|---|---|---|
| 権限の確認 | `PermissionRequest` | 道具と入力の要点・許可 (今回)・次から訊かない・拒否・作業を止める・端末で答える | `decision.behavior` |
| Claude の質問 (`AskUserQuestion`) | `PreToolUse` | 2〜4 択 | `allow` + `updatedInput` |
| MCP の問い (elicitation) | `Elicitation` | 選択肢・はい / いいえ | `action` |
| 次の一手 | 同梱の MCP server `blemma` の道具 `ask_board` | 2〜6 択・頭に「次の一手 (Claude の先回り)」 | elicitation の答え |
| 待ちの合図 | `Notification` | 窓が光る | 何も返さない |
| 作業の状態 | `UserPromptSubmit`・`Stop` | 印 = 作業中・あなたの番・完了 | 何も返さない |

- 設定は起動時に `--settings` と `--mcp-config` で渡すだけで、あなたの `settings.json` は書き換えません。書くのは repo の `board/state/` (起動の記録と、日ごとの数の記録) だけです。
- `ask_board` は subagent の中からも扇に出ます (Claude Code v2.1.318 で確かめました)。subagent の名はカードに出ません (Claude Code がその情報を渡さないため)。
- 答えが無いまま待ち時間を過ぎた時、hook は判断を返さずに終わります。線と細目は [`docs/design.md`](docs/design.md) に書きました。
- 扇に載るのは 1 画面で 1 つを選ぶ問いだけです。複数選択・2 問以上・7 択以上は、同じ窓の縦の一覧に切り替わります。羽根の外の「断る」は MCP の問いの補助のボタンです。
- 手元で試した OS は Windows だけです。mac と Linux は確かめていません。
- 小さな窓を常に手前に置く時は、窓の「常に手前」を押します (Chrome 系の Document Picture-in-Picture を使います)。

## この後

作り手は提出の後も、毎日の Claude Code の仕事でこの扇を使います。選択肢の中身は Claude が作るので、モデルが良くなるほど先回りの中身も良くなります。扇の側は変えません。次に足すのは、複数の Claude Code を同時に動かした時に 1 つの扇で受ける所と、mac / Linux での確かめです。

使ってみた人の声は、視線・スイッチ・片手の順に優先して反映します。

## 作り方

Claude Code を開発の中心に置きました。

- 設計の文書 (`docs/design.md`) を正本にして、実装は部品ごとの依頼書に分け、Claude Code の subagent と別の LLM の agent に並列で任せました。主催の資料の読み取りと計画の反証は、Claude Code の dynamic workflow で回しました (読み手 7 体 + 反証 82 体)。
- 実機の確かめを実装の初日 (11/4) に置きました。hook の欄名と挙動を公式 doc と実の `claude` (v2.1.318) で測り、結果を設計 §10.3 に残しました。この確かめで、auto mode (v2.1.318 時点の既定) では権限の確認が出ないことが分かり、起動の 1 行に `--permission-mode default` を入れました。
- 別の LLM による外部のレビューを、設計の前後と実装の後に入れました。tkinter の小窓へ全面で転換する案は、このレビューの反証を受けて「同じ頁の小型の見え方」に変えました。実装の後のレビューでは、自動の試験が全部通っている code に、線を破る道が 3 つ見つかりました (待ちの期限・滞留の入り直し・通知の hook の実行環境)。反例の試験を足してから直しました。
- 出荷の code を実の Claude Code に挟んで 15 の経路を検収しました。板なし・時限・見る頁なし・端末で先に答えた時のどれでも、勝手に続行した例はありません。

## 期間前に書いた文書について

`docs/` の設計の文書 (`design.md`・`research_official_docs.md`) は、ハッカソンの開始 (2026-11-02 12:00 JST) より前の 2026-10-14〜11-01 に書いたものです。開始前には code を 1 行も書いていません。BLEMMA の実装・試験・実行用の設定は、2026-11-02 12:00 JST 以後に新しく作りました。この repo の git の記録で区別できます。最初の commit (tag `pre-event-docs`) が期間前の文書の区切りで、実装は以後の履歴に入っています (以後の履歴には文書の直しも含みます)。期間前の文書を含めることは、主催者に事前に確認しました (2026-11-01)。

## License

MIT (see LICENSE).

---

## In short (EN)

**BLEMMA** (Greek βλέμμα, "a glance") turns the moments when Claude Code stops to ask you into OhGi, a small folding fan you answer with one glance. Claude also offers the next step as choices. Permission prompts, Claude's own questions and MCP elicitations land on the same fan. Free text still goes to the terminal. Claude Code itself is not modified: BLEMMA uses only the official hooks and MCP elicitation.

**Theme 2: "What should reach everyone, by right."** The wall is the operation wall: a small terminal prompt that wants arrow keys and Enter (an MCP form took 5 keystrokes in our measurement). The maker operates the PC with eye gaze alone. The same fan helps anyone working away from the terminal, one-handed users and switch users.

**Try it in 5 minutes.** Python 3.10+ (tests pass on 3.10 and 3.13), a logged-in Claude Code, and Chrome or Edge. Clone the repo, run `python <path to blemma>/blemma.py` in your project folder, then ask Claude: "Offer three next steps with ask_board". Blades show only a numeral; look at one and its full text appears on the fan's inner band, then it presses after one second (a mouse hover or the keys 1–6 work too). The answer is sent after a 3-second undo window. No eye tracker is needed to try it. Use `--large` for the big-button board.

**Safety.** Never auto-allows: only a human press returns an answer; timeouts and errors return no decision. Without the board you get the normal Claude Code prompt. The board listens on 127.0.0.1 only, with a per-launch token, logs only the choice, the time and counts, and never edits your `settings.json`. BLEMMA starts Claude Code with `--permission-mode default`; in auto mode there is no permission prompt to show.

**Three points.** (1) Pre-emptive choices with the bundled MCP tool `ask_board` and skill. (2) One surface for every selectable question. (3) Gaze and switch input: one-second dwell, one-key scanning, 3-second undo, fixed positions for stop and terminal, no accidental press when the card changes, and a reading band that cannot be pressed, so reading never presses another blade.

**Phone.** The board stays on your PC. To reach Claude Code from a phone, see the official [Remote Control](https://code.claude.com/docs/en/remote-control).

**Pre-event documents.** The design documents under `docs/` were written before the hackathon (Oct 14 – Nov 1, 2026). No code existed before Nov 2, 12:00 JST. All code, tests and config were created after the start, and the git history keeps them apart: the first commit, tagged `pre-event-docs`, is the documents-only baseline. Including these documents was confirmed with the organizers beforehand (Nov 1, 2026).

Tested on Windows only. MIT.

---

JaH — https://github.com/xxGodLiuxx
