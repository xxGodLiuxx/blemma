# -*- coding: utf-8 -*-
"""BLEMMA の hook 共通の client (Python 3.10+・標準ライブラリだけ)。

板の server (`board/server.py`) と話す唯一の口。4 本の hook (permission / ask / elicitation /
notify) と、要れば `mcp/blemma_mcp.py` が同じ関数を呼ぶ。設計 = docs/design.md §2.0・§3.3。

## 約束 (§2.0)
- 板との通信の失敗 (`board/state/run.json` が無い・接続を断られた・時間切れ・壊れた返り) は、
  全部「判断なし」= `None` を返す。例外は外へ出さない。hook は `None` を受けたら
  **何も書かずに exit 0** する (Claude Code の通常の判断の流れへ)。
- stdin は bytes で読んで UTF-8 で解く (`read_input`)。JSON は `ensure_ascii=True` で書く (`emit`)。
- stderr は既定で空。環境変数 `BLEMMA_DEBUG=1` の時だけ 1 行 (`debug`)。
- 待つ秒・期限・取り消しの猶予の数は板の server の `Limits` (§3.4) が持つ。client は `/ask` の
  返りの `hard_deadline_in` (自前の期限) と `wait_giveup` (1 回の `/wait` を諦める秒) に従う。
  client だけが持つ数は `/ask` と `/notify` を諦める秒の 2 つ。
- 返る答えは**取り消しの猶予が過ぎて確定した物だけ** (猶予のうちは server が持つ)。

## 使い方 (hook の側)

    import sys
    import _client          # hook と同じ dir (script の dir は sys.path の頭)

    def main() -> None:
        data = _client.read_input()
        if data is None:
            return                                  # 解けない入力 = 無出力
        ans = _client.ask(data, "permission", {"head": data["tool_name"], ...})
        if ans is None:
            return                                  # 判断なし = 無出力
        if ans["type"] == "allow_once":
            _client.emit({"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                 "decision": {"behavior": "allow"}}})
        ...

    if __name__ == "__main__":
        try:
            main()
        except Exception as e:                      # 何があっても exit 0
            _client.debug(f"hook の例外: {type(e).__name__}")
        sys.exit(0)

終わり方まで知りたい時は `ask_detail()` = `(end, choice)` を使う。`end` は
`answered` (choice あり) / `released` (端末で答える) / `expired` / `disconnected` / `closed` /
`no_board` / `busy` (待ちが満杯) / `refused` / `timeout` / `invalid` / `error` のどれか。
`answered` の外は choice が `None` = どれも無出力。

## payload (札に描く物・表示に要る物だけ・札が閉じたら server は捨てる)

頁に出る字は、どこでも「文字列」か `{"ja": "…", "en": "…"}` (頁の言葉で選ぶ) のどちらでもよい。
頁の側の定型 (許可 (今回)・拒否・作業を止める・端末で答える・送る など) は頁が日英で持つ。
本文の長い物 (Bash の command 全部・Edit の差分) は頁が巻物にする。payload 全体は 256 KiB まで。

### kind = "permission" (`hooks/permission.py`)

    {"head": "Bash",                          # 札の頭 (道具の名・MCP なら mcp__<server>__<tool>)
     "text": "Remove node_modules",           # 1 行の要約 (任意・Bash の description など)
     "blocks": [                               # 本文 (任意・上から順に)
         {"label": "command", "text": "rm -rf node_modules", "mono": true},
         {"label": "file", "text": "README.md"}],
     "suggestions": [ <permission_suggestions の 1 件をそのまま> | {"label": "<字>"} , ...],
                                               # 「次から訊かない」の素 (任意)。頁が §2.1 の字にする
                                               # (addRules = 規則と保存期間・setMode = 別の字)。
                                               # 頁は先頭から 2 件まで出し、setMode の bypassPermissions は出さない。
     "reasons": ["…", "…", "…"]}              # 拒否の理由 (任意・無ければ DENY_REASONS の 3 つ)

返り = `{"type": "allow_once"}` / `{"type": "allow_always", "suggestion": i}` (渡した suggestions の
添字・0 から = その要素を `updatedPermissions` へ逐語で写す) / `{"type": "deny", "reason": j}`
(reasons の添字) / `{"type": "stop"}` (固定の位置の釦「作業を止める」= deny + interrupt) / `None`。

### kind = "question" (`hooks/ask.py`)

    {"questions": tool_input["questions"]}    # AskUserQuestion の questions をそのまま (1〜4 問)

頁は 1 問 = 1 画面。単一選択の 1 問だけなら選んだ 1 押しで送り、複数の問い・multiSelect は最後に
確かめの画面と「送る」を足す。返り = `{"type": "answer", "picks": [[i], [j, k], ...]}` (問いごとの
選んだ options の添字・0 から・単一選択は 1 個・multiSelect は 1 個以上) / `{"type": "skip"}`
(固定の位置の釦「この質問に答えない」) / `None`。`answers` の文は hook が自分の stdin の写しから組む。

### kind = "elicitation" (`hooks/elicitation.py`)

    {"head": "<MCP server の名>",              # 問うている server (MCP の MUST = 誰が訊いているか)
     "text": "<message>",
     "fields": [                               # 1 欄 = 1 画面 (hook が requested_schema から作る)
         {"name": "choice", "title": "次の一手を選んでください",
          "multi": false,                      # true = 複数選択 (array の enum)
          "required": true,                    # false なら頁は「空のまま」の釦を足す
          "default": [0],                      # 任意・印を付けるだけで、押すまで送らない
          "options": [
              {"label": "PR の本文を書く", "value": "1"},
              {"label": "はい", "value": true},
              {"label": "ほかの答え (書いて伝える)", "terminal": true}]}]}
                                               # terminal = 押すと「端末で答える」と同じ (板で文字は書かない)

返り = `{"type": "accept", "picks": [[i], ...], "values": {"choice": "1", ...}}` (`values` は
**client が自分の payload の写しから組む** = 板は添字しか返さない・空のままの欄は入れない・
multi は値の list) / `{"type": "decline"}` (断る) / `{"type": "cancel"}` (固定の位置の釦
「この問い合わせを閉じる」) / `None`。

### Notification (`hooks/notify.py`)

    _client.notify(data)                       # 1 回 POST して待たない (1 秒で諦める)・返りは見ない
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

# client だけが持つ数 (残りの数は board/server.py の Limits = §3.4 が持ち、/ask の返りで来る)
ASK_GIVEUP_SEC = 2.0        # POST /ask を諦める秒 (= Limits.ask_giveup)
NOTIFY_GIVEUP_SEC = 1.0     # POST /notify を諦める秒 (§2.4)
MAX_DEADLINE_SEC = 3600.0   # server が返す期限の正気の上限 (超える・負 = 壊れた返り)
MAX_RESPONSE_BYTES = 1_000_000

KINDS = ("permission", "question", "elicitation")

# 拒否の定型 3 つ (頁 board/static/board.js の DENY_REASONS と同じ順番・§2.1)。
# hook は Claude へ返す message にこの文を使う (どちらの言葉でも・両方でもよい)。
DENY_REASONS = (
    ("別のやり方でお願いします", "Please do it another way."),
    ("いまは要りません", "Not needed right now."),
    ("先に説明してください", "Please explain first."),
)

RUN_FILE_ENV = "BLEMMA_RUN_FILE"   # run.json の路を差し替える (試験・特別な置き方の時だけ)
DEBUG_ENV = "BLEMMA_DEBUG"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # proxy を通さない


def debug(msg: Any) -> None:
    """`BLEMMA_DEBUG=1` の時だけ stderr に 1 行。それ以外は何もしない。"""
    if os.environ.get(DEBUG_ENV) != "1":
        return
    try:
        line = str(msg).replace("\r", " ").replace("\n", " ")[:500]
        sys.stderr.write("BLEMMA: " + line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def read_input(stream: Any = None) -> Optional[dict]:
    """stdin を bytes で読み、UTF-8 で解いた JSON の object を返す。解けなければ None。"""
    try:
        raw = (stream if stream is not None else sys.stdin.buffer).read()
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        debug(f"stdin を解けない: {type(e).__name__}")
        return None
    return data if isinstance(data, dict) else None


def emit(obj: Any) -> None:
    """公式の JSON を 1 個だけ stdout へ書く (ASCII だけ = Windows の cp932 でも壊れない)。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=True))
    sys.stdout.flush()


def run_file_path(run_file: Any = None) -> Path:
    """run.json の路 = 引数 > 環境変数 BLEMMA_RUN_FILE > この file から見た ../board/state/run.json。"""
    if run_file:
        return Path(run_file)
    env = os.environ.get(RUN_FILE_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "board" / "state" / "run.json"


def source_of(hook_input: Any) -> dict:
    """札の「出どころ」= cwd の末尾の名・session の頭 6 字・agent_type (§2.0)。"""
    if not isinstance(hook_input, dict):
        return {"cwd": "", "session": "", "agent": None}
    cwd = hook_input.get("cwd")
    name = ""
    if isinstance(cwd, str) and cwd:
        name = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    sid = hook_input.get("session_id")
    agent = hook_input.get("agent_type")
    return {
        "cwd": name[:80],
        "session": sid[:6] if isinstance(sid, str) else "",
        "agent": agent[:80] if isinstance(agent, str) and agent else None,
    }


def _load_run(run_file: Any) -> Optional[Tuple[int, str]]:
    try:
        info = json.loads(run_file_path(run_file).read_text(encoding="utf-8"))
        port = info["port"]
        token = info["token"]
    except Exception:
        return None
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        return None
    if not isinstance(token, str) or not token:
        return None
    return port, token


def _call(method: str, port: int, token: str, path: str, body: Any = None,
          timeout: float = ASK_GIVEUP_SEC) -> Tuple[int, Any]:
    """127.0.0.1 の板へ 1 回だけ HTTP で話す。失敗は例外のまま呼び手へ (呼び手が None に変える)。"""
    headers = {"X-Blemma-Token": token}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=True).encode("ascii")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers=headers, method=method)
    with _OPENER.open(req, timeout=timeout) as resp:
        status = resp.status
        raw = resp.read(MAX_RESPONSE_BYTES)
    if not raw:
        return status, None
    return status, json.loads(raw.decode("utf-8"))


def _is_index(v: Any, n: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n


def _picks_ok(p: Any, n: int, multi: bool, required: bool) -> bool:
    if not isinstance(p, list) or not all(_is_index(i, n) for i in p):
        return False
    if len(set(p)) != len(p):
        return False
    if not multi and len(p) > 1:
        return False
    if required and not p:
        return False
    return True


def _check_choice(kind: str, payload: dict, ans: Any) -> Optional[dict]:
    """板の答えを自分の payload の写しと照らす。外れていれば None (= 無出力)。"""
    if not isinstance(ans, dict):
        return None
    t = ans.get("type")
    if kind == "permission":
        if t in ("allow_once", "stop"):
            return {"type": t}
        if t == "allow_always":
            sugg = payload.get("suggestions")
            i = ans.get("suggestion")
            if isinstance(sugg, list) and _is_index(i, len(sugg)):
                return {"type": t, "suggestion": i}
            return None
        if t == "deny":
            reasons = payload.get("reasons")
            n = len(reasons) if isinstance(reasons, list) and reasons else len(DENY_REASONS)
            j = ans.get("reason")
            return {"type": t, "reason": j} if _is_index(j, n) else None
        return None
    if kind == "question":
        if t == "skip":
            return {"type": t}
        if t != "answer":
            return None
        qs = payload.get("questions")
        picks = ans.get("picks")
        if not isinstance(qs, list) or not qs or not isinstance(picks, list) or len(picks) != len(qs):
            return None
        for q, p in zip(qs, picks):
            opts = q.get("options") if isinstance(q, dict) else None
            if not isinstance(opts, list):
                return None
            if not _picks_ok(p, len(opts), bool(q.get("multiSelect")), True):
                return None
        return {"type": t, "picks": [list(p) for p in picks]}
    if kind == "elicitation":
        if t in ("decline", "cancel"):
            return {"type": t}
        if t != "accept":
            return None
        fields = payload.get("fields")
        picks = ans.get("picks")
        if not isinstance(fields, list) or not fields or not isinstance(picks, list) \
                or len(picks) != len(fields):
            return None
        values: dict = {}
        for f, p in zip(fields, picks):
            if not isinstance(f, dict) or not isinstance(f.get("name"), str):
                return None
            opts = f.get("options")
            if not isinstance(opts, list):
                return None
            multi = bool(f.get("multi"))
            if not _picks_ok(p, len(opts), multi, bool(f.get("required"))):
                return None
            chosen = []
            for i in p:
                o = opts[i]
                if not isinstance(o, dict) or o.get("terminal") or "value" not in o:
                    return None
                chosen.append(o["value"])
            if chosen:
                values[f["name"]] = chosen if multi else chosen[0]
        return {"type": t, "picks": [list(p) for p in picks], "values": values}
    return None


def ask_detail(hook_input: Any, kind: str, payload: dict,
               run_file: Any = None) -> Tuple[str, Optional[dict]]:
    """板に札を出し、確定した答えを待つ。返り = (end, choice)。choice は answered の時だけ。"""
    try:
        return _ask(hook_input, kind, payload, run_file)
    except Exception as e:  # 何があっても判断なし
        debug(f"client の例外: {type(e).__name__}")
        return "error", None


def ask(hook_input: Any, kind: str, payload: dict, run_file: Any = None) -> Optional[dict]:
    """板に札を出し、確定した答え (choice の dict) を返す。判断なしは全部 None。

    hook_input = hook の stdin の JSON (出どころの表示に使う)・kind = permission / question /
    elicitation・payload = 上の docstring の形。端末で答える・期限・板なし・壊れた返りは None。
    """
    return ask_detail(hook_input, kind, payload, run_file)[1]


def _ask(hook_input: Any, kind: str, payload: dict, run_file: Any) -> Tuple[str, Optional[dict]]:
    if kind not in KINDS or not isinstance(payload, dict):
        return "invalid", None
    run = _load_run(run_file)
    if run is None:
        debug("板なし (run.json が無いか読めない)")
        return "no_board", None
    port, token = run
    t0 = time.monotonic()
    try:
        _, res = _call("POST", port, token, "/ask",
                       {"kind": kind, "from": source_of(hook_input), "payload": payload},
                       timeout=ASK_GIVEUP_SEC)
    except urllib.error.HTTPError as e:
        debug(f"/ask が {e.code}")
        return ("busy" if e.code == 503 else "refused"), None
    except ValueError:
        debug("/ask の返りが壊れている")
        return "error", None
    except Exception as e:
        debug(f"板へ繋がらない: {type(e).__name__}")
        return "no_board", None
    if not isinstance(res, dict):
        return "error", None
    cid = res.get("id")
    hard = res.get("hard_deadline_in")
    giveup = res.get("wait_giveup")
    if not isinstance(cid, str) or not cid:
        return "error", None
    for v in (hard, giveup):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= MAX_DEADLINE_SEC:
            return "error", None
    deadline = t0 + float(hard)
    path = "/wait?id=" + urllib.parse.quote(cid, safe="")
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            debug("自前の期限 (hard_deadline) を過ぎた")
            return "timeout", None
        try:
            _, res = _call("GET", port, token, path, timeout=min(float(giveup), remain))
        except Exception as e:
            debug(f"/wait が失敗: {type(e).__name__}")
            return "timeout", None
        state = res.get("state") if isinstance(res, dict) else None
        if state == "waiting":
            continue
        if state == "answered":
            choice = _check_choice(kind, payload, res.get("answer"))
            if choice is None:
                debug("板の答えが payload と合わない")
                return "invalid", None
            return "answered", choice
        if state in ("released", "expired", "disconnected", "closed"):
            debug(f"判断なしで終わり: {state}")
            return state, None
        return "error", None


def notify(hook_input: Any, run_file: Any = None) -> bool:
    """Notification を板へ 1 回 POST する (待たない・1 秒で諦める)。届いたかだけ返す。"""
    try:
        run = _load_run(run_file)
        if run is None:
            return False
        port, token = run
        d = hook_input if isinstance(hook_input, dict) else {}

        def s(key: str) -> str:
            v = d.get(key)
            return v[:2000] if isinstance(v, str) else ""

        _call("POST", port, token, "/notify",
              {"type": s("notification_type"), "from": source_of(d),
               "title": s("title"), "message": s("message")},
              timeout=NOTIFY_GIVEUP_SEC)
        return True
    except Exception as e:
        debug(f"/notify が失敗: {type(e).__name__}")
        return False
