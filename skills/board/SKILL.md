---
name: board
description: 迷う所・作業の区切りで「次の一手」を 2〜6 択にして人に訊く手順 (同梱の MCP の道具 ask_board)。板 (BLEMMA) があれば扇か大きなボタンに、無ければ端末のいつもの確認に同じ選択肢が出る。「次の一手を出して」「選択肢で訊いて」「ask_board で」の時に読む。
---

# board — 2〜6 択で訊く作法 (BLEMMA 同梱の skill)

人に訊く時は、**答えやすい形**にする。選べば決まる問いは `ask_board` で 2〜6 択にして出す。板 (BLEMMA) が動いていれば扇か大きなボタンに出て、板が無ければ Claude Code のいつもの確認に同じ選択肢が出る。

扇は既定でマウス向け。1 回目で選び、同じ羽根を 1.5 秒以内にもう 1 回押すと決まる (ダブルクリックも可)。`click=single` なら 1 回に戻せる。大きな板・キー・有効にした視線やスイッチは 1 回で決まる。確定後は既定 3 秒の取り消しの猶予があり、扇の内側の帯が「取り消す (n)」になる。取り消しのクリックは 1 回。最初の選択だけで作業を進めず、道具の答えを待つ。

視線の機能 (見つめて押す・視線で文章を送る・視線の点・走査) はすべて既定で切。作り手は視線で PC を使い、OS の視線の道具からクリックを送る。見つめるだけで押したい人は設定か `--set dwell=1` で入れられる。本人の操作方法を推測して設定を変えない。

## 1. いつ使うか
1. **答えが 2〜6 個の選択肢に絞れる問い** = 方針の分かれ道・どの file を直すか・どの案で進めるか。文で訊くより先に選択肢にする。
2. **作業の区切り** (commit の後・試験の後・調べが終わった後) で「次の一手」を 3 つ前後 = 人は選ぶだけで進む。
3. 自分 (Claude) の確かめの 2〜4 択は `AskUserQuestion` でもよい (板はどちらも同じボタンに出す)。**subagent の中からは `ask_board`** (subagent には AskUserQuestion が無い)。
4. 自由記述が要りそうな問いも、**ありそうな答えを先に選択肢に入れてから** `allow_free_text: true` を付ける (候補のボタンが増えるほど、端末へ戻る回が減る)。

## 2. 選択肢の決まり
- 1 つ 40 字以内・互いに違う・動詞で始める (「PR の本文を書く」「試験を回す」)。
- **必ず「止める / 待つ」の 1 つを入れる**。無ければ server が「ここで止める」を足す = 6 つの枠のうち 1 つはそのために空けておく (自分の選択肢は 5 つまで)。
- `title` は 1 文・80 字以内の問い (「次はどれにしますか」でよい)。
- 短い解説があれば、`choices` と同じ順・同じ数の文字列を任意の `descriptions` に付ける。扇では注目した羽根の全文を内側の押せない帯で読み、解説は `desc=on` の時に別の欄へ出る。問いは扇の下の和紙 (横長では左)。長い本文は「▼ 続き」で送り、読んでいる間は動かない。
- 答えを**推測で進めない**。`declined` なら別の案を出すか文で訊く。`cancelled` = 人がこの問い合わせを閉じた = **作業を止めて次の指示を待つ** (止まる保証ではなく、あなたへの指示)。

## 3. 戻りの読み方 (`tools/call` の text)
| 戻り | 意味 | 次 |
|---|---|---|
| `{"answer": "<選択肢の文>", "index": n}` | n 番目 (1 から) を選んだ | その文のとおりに進む |
| `{"answer": "<人の文>", "free_text": true}` | 自由記述 (板では端末で答える) | 文を指示として読む |
| `{"answer": null, "declined": true}` | どれも選ばなかった | 別の案 2〜6 択か、文で訊く |
| `{"answer": null, "cancelled": true}` | 問い合わせを閉じた | 止めて待つ |
| `isError: true` + 本文が「回答の待ち時間を過ぎました。作業を止めて次の指示を待ってください。」 | 人が答えないまま期限が切れた (板の待ちと、その後の端末の form を合わせて約 9 分) | **止めて次の指示を待つ** (同じ問いを繰り返さない) |
| `isError: true` (それ以外) | 引数の誤り (字数・数・重複) か、この環境では問いが出せない | 引数を直す / AskUserQuestion か文で訊く |

## 4. 例
```json
{"title": "試験が通りました。次はどれにしますか", "choices": ["PR の本文を書く", "README を直す", "ここで止める"]}
```
```json
{"title": "どの直し方で進めますか", "choices": ["A: 期限を 120 秒に縮める", "B: 札を閉じるボタンを足す", "両方", "ここで止める"]}
```
```json
{"title": "commit の文はこれでよいですか", "choices": ["よい", "短くする", "英語の要約も足す", "ここで止める"], "allow_free_text": true}
```

## 5. 使わない時
- 自由記述でしか答えられない問い (名前・文章・数値の入力) = 文で訊く (板は選択式だけ)。
- 権限の確認は自分で出さない (Claude Code が `PermissionRequest` で出し、板が受ける)。
- 1 回の呼び出しは 1 問。問いが 2 つあるなら 2 回に分ける (または `AskUserQuestion` の 2 問)。

CLAUDE.md へ誘導する 1 行の例 =「迷う所は ask_board か AskUserQuestion で 2〜6 択にして訊く」。

---

## In short (EN)
Use `ask_board` whenever the human's answer fits 2–6 short choices: at decision points and after milestones (commit, tests). Each label ≤ 40 chars, distinct, verb first; always leave one slot for a stop/wait choice (the server adds "ここで止める" if you omit it). Never guess: `declined` → offer other choices or ask in prose; `cancelled` → stop and wait for instructions (an instruction to you, not an enforced stop). If free text is likely, put the probable answers first, then set `allow_free_text: true`. Subagents must use `ask_board` (they have no `AskUserQuestion`). Without the board, the same choices appear as Claude Code's default form.

The default fan uses mouse input: one click selects and a second on the same blade within 1.5 seconds confirms (double-click works too). `click=single` restores one-click confirmation. The large board, keys, enabled dwell and switches use one action. Wait for the tool's answer, including the default 3-second undo period; Undo itself needs only one click on the inner band. Dwell, gaze scrolling, trail and scanning are off by default. The maker uses OS gaze tools that send clicks; users who want dwell can enable it in Settings or with `--set dwell=1`.
