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
- 諦めの秒と自前の期限は**通信の全体に効く総期限** (単調時計・繋ぐ・送る・見出しと本文を受け終えるまで)。
  読み書き 1 回ごとに残りの秒を当てる = 少しずつ返されても延びない。受け終えた後にも見直し、過ぎていれば
  答えでも使わない (判断なし)。通信は 127.0.0.1 へだけ・proxy を通さない・**転送 (3xx) を追わない**
  (2xx の外は全部 判断なし = token の見出しを別の宛先へ渡さない)。
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

上の `__main__` の 4 行は `_client.run_hook(main)` 1 行でもよい (中断と stdout の切断も exit 0 にする)。

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
          "min_picks": 1,                      # multi だけ・必須の欄で送れる最小の印の数 (0 か 1・無ければ 1。
                                               # 0 = minItems 0 = 印 0 個で送れて値は [])。任意の欄は常に 0
          "default": [0],                      # 任意・印を付けるだけで、押すまで送らない
          "options": [
              {"label": "PR の本文を書く", "value": "1"},
              {"label": "はい", "value": true},
              {"label": "ほかの答え (書いて伝える)", "terminal": true}]}]}
                                               # terminal = 押すと「端末で答える」と同じ (板で文字は書かない)

返り = `{"type": "accept", "picks": [[i], ...], "values": {"choice": "1", ...}}` (`values` は
**client が自分の payload の写しから組む** = 板は添字しか返さない・空のままの欄は入れない・
multi は値の list・必須の multi を印 0 個で送った時 (min_picks 0) は `[]`) / `{"type": "decline"}` (断る) /
`{"type": "cancel"}` (固定の位置の釦「この問い合わせを閉じる」) / `None`。

### Notification (`hooks/notify.py`)

    _client.notify(data)                       # 1 回 POST して待たない (notify.py は 2 秒で諦める)・返りは見ない
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

# client だけが持つ数 (残りの数は board/server.py の Limits = §3.4 が持ち、/ask の返りで来る)
# どちらも通信の全体の秒 (総期限・1 回の読み書きの待ちではない)
ASK_GIVEUP_SEC = 2.0        # POST /ask を諦める秒 (= Limits.ask_giveup)
NOTIFY_GIVEUP_SEC = 1.0     # POST /notify を諦める秒の既定 (§2.4・notify.py は 2.0 に上書きする)
MAX_DEADLINE_SEC = 3600.0   # server が返す期限の正気の上限 (超える・負 = 壊れた返り)
MAX_RESPONSE_BYTES = 1_000_000
MAX_PAYLOAD_BYTES = 256 * 1024   # 札の payload の上限 (ensure_ascii の JSON の bytes・上の docstring)

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
TERMINAL_ONLY_ENV = "BLEMMA_TERMINAL_ONLY"   # 板に出さず端末で答える道具の名 (カンマ区切り・§2.1)


class _HTTPStatus(Exception):
    """板が 2xx の外を返した (転送の 3xx も = 追わない)。`code` = HTTP の状態の数。"""

    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


class _DeadlineSocket(socket.socket):
    """総期限つきの socket。繋ぐ・読み書きの 1 回ごとに「総期限までの残り」を timeout にし、過ぎていれば
    timeout を起こす。標準の timeout は 1 回ごと = 本文を少しずつ返されると全体はいくらでも延びる (§3.4)。"""

    deadline = 0.0                   # time.monotonic() の総期限 (作った後に入れる)

    def _arm(self) -> None:
        remain = self.deadline - time.monotonic()
        if remain <= 0:
            raise socket.timeout("BLEMMA: the total deadline passed")
        self.settimeout(remain)

    def connect(self, address: Any) -> None:
        self._arm()
        super().connect(address)

    def send(self, data: Any, flags: int = 0) -> int:
        self._arm()
        return super().send(data, flags)

    def sendall(self, data: Any, flags: int = 0) -> None:
        self._arm()
        super().sendall(data, flags)

    def recv(self, bufsize: int, flags: int = 0) -> bytes:
        self._arm()
        return super().recv(bufsize, flags)

    def recv_into(self, buffer: Any, nbytes: int = 0, flags: int = 0) -> int:
        self._arm()
        return super().recv_into(buffer, nbytes, flags)


class _Connection(http.client.HTTPConnection):
    """127.0.0.1 の板への 1 回きりの接続 = 総期限つきの socket で繋ぐ (proxy も転送の追いかけも無い)。"""

    def __init__(self, port: int, deadline: float) -> None:
        super().__init__("127.0.0.1", port)
        self._blemma_deadline = deadline

    def connect(self) -> None:
        sock = _DeadlineSocket(socket.AF_INET, socket.SOCK_STREAM)
        sock.deadline = self._blemma_deadline
        try:
            sock.connect((self.host, self.port))
        except BaseException:
            sock.close()
            raise
        try:                         # 標準の connect と同じ (見出しと本文の 2 回の送りで ACK を待たない)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.sock = sock


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


def run_hook(main: Callable[[], Any]) -> None:
    """hook の入口。main() を走らせ、何があっても (例外・中断・stdout の切断) exit 0 で終わる (§2.0)。

    main() の途中の例外は無出力のまま (`emit` は最後の 1 回だけ = その前の例外では何も出ない)。
    stdout が切れていた (BrokenPipe) 時は、終わりの flush で騒がないよう stdout を空の行き先へ付け替える。
    """
    try:
        main()
    except BaseException as e:      # KeyboardInterrupt・SystemExit も含めて
        debug(f"hook の例外: {type(e).__name__}")
    try:
        sys.stdout.flush()
    except BaseException:
        try:
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
        except BaseException:
            pass
    sys.exit(0)


def payload_fits(payload: Any) -> bool:
    """payload が札にできる大きさか (ensure_ascii の JSON で MAX_PAYLOAD_BYTES 以下)。

    超える札は出さない = hook は無出力で端末へ (Bash の command は切らない約束なので、切らずに諦める)。
    """
    try:
        return len(json.dumps(payload, ensure_ascii=True)) <= MAX_PAYLOAD_BYTES
    except (TypeError, ValueError):
        return False


def terminal_only(tool_name: Any) -> bool:
    """道具の名が環境変数 BLEMMA_TERMINAL_ONLY (カンマ区切り) に在るか = 板に出さず端末で答える (§2.1)。"""
    if not isinstance(tool_name, str) or not tool_name:
        return False
    names = os.environ.get(TERMINAL_ONLY_ENV, "")
    return tool_name in {n.strip() for n in names.split(",") if n.strip()}


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
    """127.0.0.1 の板へ 1 回だけ HTTP で話す。失敗は例外のまま呼び手へ (呼び手が None に変える)。

    timeout = 通信の全体 (繋ぐ・送る・見出しと本文を受け終える) の総期限の秒 (単調時計)。読み書き 1 回ごとに
    残りを当て、受け終えた後にも見直す。2xx の外は `_HTTPStatus` (転送の 3xx も追わない)。
    """
    deadline = time.monotonic() + timeout
    headers = {"X-Blemma-Token": token, "Connection": "close"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=True).encode("ascii")
        headers["Content-Type"] = "application/json"
    conn = _Connection(port, deadline)
    resp = None
    try:
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        if not 200 <= status < 300:
            raise _HTTPStatus(status)
        raw = resp.read(MAX_RESPONSE_BYTES)
    finally:
        if resp is not None:
            resp.close()
        conn.close()
    if time.monotonic() >= deadline:
        raise socket.timeout("BLEMMA: the total deadline passed")
    if not raw:
        return status, None
    return status, json.loads(raw.decode("utf-8"))


def _is_index(v: Any, n: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n


def _picks_ok(p: Any, n: int, multi: bool, least: int) -> bool:
    """選んだ番号の列が n 個の選択肢に合うか (範囲の内・重なりなし・単一は 1 個まで・least 個以上)。"""
    if not isinstance(p, list) or not all(_is_index(i, n) for i in p):
        return False
    if len(set(p)) != len(p):
        return False
    if not multi and len(p) > 1:
        return False
    return len(p) >= least


def _least(field: dict, multi: bool) -> int:
    """MCP の問いの 1 欄で送れる最小の選択の数。欄の必須と最小の選択の数は別 (§2.3)。

    任意の欄 = 0 (空のまま = content に入れない)・必須の単一選択 = 1・必須の複数選択 = `min_picks` (0 か 1・
    無ければ 1。0 = minItems 0 の欄 = 空の配列も合法)。
    """
    if not field.get("required"):
        return 0
    mp = field.get("min_picks")
    if multi and isinstance(mp, int) and not isinstance(mp, bool) and mp in (0, 1):
        return mp
    return 1


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
            if not _picks_ok(p, len(opts), bool(q.get("multiSelect")), 1):
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
            if not _picks_ok(p, len(opts), multi, _least(f, multi)):
                return None
            chosen = []
            for i in p:
                o = opts[i]
                if not isinstance(o, dict) or o.get("terminal") or "value" not in o:
                    return None
                chosen.append(o["value"])
            if chosen:
                values[f["name"]] = chosen if multi else chosen[0]
            elif multi and f.get("required"):
                values[f["name"]] = []             # 必須の複数選択で 0 個が許される (min_picks 0) = 空の配列を値に
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
    except _HTTPStatus as e:
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
        if time.monotonic() >= deadline:           # 受け終えた後にも見直す = 期限の後の答えは使わない
            debug("自前の期限 (hard_deadline) を過ぎてから受けた = 使わない")
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


def state(hook_input: Any, run_file: Any = None) -> bool:
    """Send one status update with a 250 ms total deadline; never send input text."""
    try:
        if not isinstance(hook_input, dict):
            return False
        value = {"UserPromptSubmit": "working", "Stop": "done"}.get(hook_input.get("hook_event_name"))
        sid = hook_input.get("session_id")
        if value is None or not isinstance(sid, str) or not sid:
            return False
        run = _load_run(run_file)
        if run is None:
            return False
        port, token = run
        _call("POST", port, token, "/state", {"session": sid[:6], "state": value}, timeout=0.25)
        return True
    except Exception:
        return False


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
