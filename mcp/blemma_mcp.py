#!/usr/bin/env python3
"""同梱の MCP server (stdio・2025-11-25・標準ライブラリだけ)。

ask_board の契約は docs/design.md §2.5。停止の戻りは Claude への指示であり、
作業が止まる保証ではない。stdout は UTF-8 の JSON-RPC だけ、記録は
BLEMMA_DEBUG=1 の時だけ stderr へ出す。問いや答えの内容は記録しない。
"""
import itertools
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

# 直接起動した時にも、期限の正本 (§3.4) を同梱の板から参照する。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from board.server import MAX_BODY, Limits

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "blemma", "version": "0.0.1"}
ELICIT_WAIT_SEC = Limits().hard_deadline
MAX_LINE = MAX_BODY   # 1 行 (改行を含む) の上限 = 板の本文の上限と同じ = 板に出せる大きさの問いは通し、際限なく読まない
STOP_CHOICE = "ここで止める"

ASK_BOARD_TOOL = {
    "name": "ask_board",
    "description": (
        "Ask the human to pick one of 2-6 short choices (big buttons on the BLEMMA board, "
        "or the normal form without it). Use at a decision point or to offer next steps. "
        "The server adds 'ここで止める' if absent; reserve one of the six slots for it. "
        "A stop or cancel answer instructs you to stop and wait; it cannot enforce a stop."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 80,
                      "description": "One-sentence question, up to 80 characters"},
            "choices": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 40},
                "minItems": 2,
                "maxItems": 6,
                "uniqueItems": True,
                "description": "Short, distinct labels; at most five if the stop choice is absent",
            },
            "allow_free_text": {
                "type": "boolean",
                "default": False,
                "description": "Also accept an answer in the human's own words",
            },
            "descriptions": {
                "type": "array", "items": {"type": "string"},
                "minItems": 2, "maxItems": 6,
                "description": "Optional short explanations, in the same order and length as choices",
            },
        },
        "required": ["title", "choices"],
    },
}

# initialize で返す使い方 (英語・Claude が読む)。同梱の skill (skills/board) は Claude Code の置き場に無く読まれない
# ので、作法の芯をここで渡す。tool search では起動時に載るのが道具の名とこの文だけ = 頭の文で「いつ使うか」を言う。
# 中身は skill の「In short (EN)」と同じ決まり (数は ASK_BOARD_TOOL・STOP_CHOICE・MSG_* と揃える)。
SERVER_INSTRUCTIONS = (
    "Use ask_board when the human's answer fits a few short choices: at a fork in the plan, and at "
    "milestones (after a commit, tests or research) to offer 2-5 next steps. Choices: 40 characters or "
    "fewer, distinct, verb first. The server adds '" + STOP_CHOICE + "' when it is absent, so pass at most "
    "five of your own. Never guess: index = do that choice; declined = offer other choices or ask in prose; "
    "cancelled, or an isError timeout = stop and wait for instructions without asking again. "
    "Not for free-text-only questions (names, prose, numbers) or permission checks: "
    "Claude Code asks for permission itself."
)

MSG_DECLINED = "人はどれも選びませんでした。別の案を出すか、文で訊いてください。"
MSG_CANCELLED = "人はこの問い合わせを閉じました。作業を止めて次の指示を待ってください。"
MSG_NO_ELICIT = "この環境では MCP の問いが出せません。AskUserQuestion か文で訊いてください。"
MSG_TIMEOUT = "回答の待ち時間を過ぎました。作業を止めて次の指示を待ってください。"


@dataclass
class Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: object = None
    cancelled: bool = False


class Server:
    def __init__(self, wait_timeout=ELICIT_WAIT_SEC):
        self._out_lock = threading.Lock()
        self._pending = {}
        self._calls = {}
        self._workers = set()
        self._pending_lock = threading.RLock()
        self._closed = threading.Event()
        self._ids = itertools.count(1)
        self.wait_timeout = wait_timeout
        self.client_caps = {}
        self.client_protocol = None

    # ---- 記録 ----
    def log(self, *parts):
        if os.environ.get("BLEMMA_DEBUG") != "1":
            return
        try:
            data = ("[blemma-mcp] " + " ".join(parts) + "\n").encode("utf-8")
            sys.stderr.buffer.write(data)
            sys.stderr.buffer.flush()
        except (OSError, ValueError):
            pass

    # ---- 送る ----
    def send(self, msg):
        data = (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with self._out_lock:
                if self._closed.is_set():
                    return False
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            return True
        except (OSError, ValueError):
            self.close()
            return False

    def reply(self, rid, result):
        self.send({"jsonrpc": "2.0", "id": rid, "result": result})

    def error(self, rid, code, message):
        self.send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    def request_client(self, method, params, timeout, pending):
        rid = f"blemma-{next(self._ids)}"
        with self._pending_lock:
            if pending.cancelled or self._closed.is_set():
                return {"action": "cancel"}, None
            self._pending[rid] = pending
            self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        pending.event.wait(timeout)
        with self._pending_lock:
            self._pending.pop(rid, None)
            timed_out = not pending.event.is_set()
        if pending.cancelled or timed_out:
            # 子の問いも閉じる。遅れて来た答えは _pending に無いので捨てる。
            self.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                       "params": {"requestId": rid}})
        if pending.cancelled:
            return {"action": "cancel"}, None
        if timed_out:
            return None, {"code": "timeout"}
        return pending.result, pending.error

    # ---- 受ける ----
    def on_message(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self.error(None, -32600, "Invalid Request")
            return
        if "method" in msg:
            if "id" in msg:
                rid = msg["id"]
                if type(rid) not in (int, str) or not isinstance(msg["method"], str):
                    self.error(None, -32600, "Invalid Request")
                    return
                pending = Pending() if msg["method"] == "tools/call" else None
                worker = threading.Thread(target=self.on_request, args=(msg, pending), daemon=True)
                with self._pending_lock:
                    if rid in self._calls:
                        self.error(rid, -32600, "Request already in progress")
                        return
                    if pending is not None:
                        # 起動前に控える = 直後の取消通知も取りこぼさない。
                        self._calls[rid] = pending
                    self._workers.add(worker)
                    worker.start()
            elif msg["method"] == "notifications/cancelled":
                params = msg.get("params")
                rid = params.get("requestId") if isinstance(params, dict) else None
                if type(rid) in (int, str):
                    with self._pending_lock:
                        # client が出した tools/call の ID を取り消す。
                        pending = self._calls.get(rid)
                        if pending is not None and not pending.event.is_set():
                            pending.cancelled = True
                            pending.event.set()
            return
        rid = msg.get("id")
        if type(rid) not in (int, str):
            return
        with self._pending_lock:
            pending = self._pending.get(rid)
            if pending is not None and not pending.event.is_set():
                pending.result = msg.get("result")
                pending.error = msg.get("error")
                pending.event.set()

    def on_request(self, msg, pending=None):
        rid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})
        try:
            if not isinstance(params, dict):
                self.error(rid, -32602, "params must be an object")
                return
            if method == "initialize":
                self.client_protocol = params.get("protocolVersion")
                caps = params.get("capabilities", {})
                self.client_caps = caps if isinstance(caps, dict) else {}
                self.log("initialize")
                self.reply(rid, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                    "instructions": SERVER_INSTRUCTIONS,
                })
            elif method == "ping":
                self.reply(rid, {})
            elif method == "tools/list":
                self.reply(rid, {"tools": [ASK_BOARD_TOOL]})
            elif method == "tools/call":
                result = self.call_tool(params, pending)
                if pending is None or not pending.cancelled:   # 取り消された要求には応答しない (MCP の決まり)
                    self.reply(rid, result)
            else:
                self.error(rid, -32601, "Method not found")
        except Exception as e:  # 1 つの要求の失敗で server を落とさない
            self.log("request failed:", type(e).__name__)
            self.error(rid, -32603, f"Internal error: {type(e).__name__}")
        finally:
            with self._pending_lock:
                if pending is not None:
                    self._calls.pop(rid, None)
                self._workers.discard(threading.current_thread())

    # ---- 道具 ----
    def call_tool(self, params, pending=None):
        name = params.get("name")
        args = params.get("arguments", {})
        if name != "ask_board":
            return tool_text("unknown tool", is_error=True)
        problem = validate_args(args)
        if problem:
            return tool_text(problem, is_error=True)
        capability = self.client_caps.get("elicitation")
        if not isinstance(capability, dict) or (capability and "form" not in capability):
            return tool_text(MSG_NO_ELICIT, is_error=True)
        title = args["title"].strip()
        choices = [c.strip() for c in args["choices"]]
        if STOP_CHOICE not in choices:
            choices.append(STOP_CHOICE)
        free = bool(args.get("allow_free_text", False))
        one_of = [{"const": str(i), "title": c} for i, c in enumerate(choices, start=1)]
        for option, description in zip(one_of, args.get("descriptions", [])):
            option["description"] = description
        props = {"choice": {"type": "string", "title": title, "oneOf": one_of}}
        if free:
            one_of.append({"const": "other", "title": "ほかの答え (書いて伝える)"})
            props["other_text"] = {"type": "string", "title": "ほかの答え", "maxLength": 200}
        req = {
            "mode": "form",
            "message": title,
            "requestedSchema": {"type": "object", "properties": props, "required": ["choice"]},
        }
        result, err = self.request_client("elicitation/create", req, self.wait_timeout,
                                          pending if pending is not None else Pending())
        if isinstance(err, dict) and err.get("code") == "timeout":
            return tool_text(MSG_TIMEOUT, is_error=True)
        if err is not None or not isinstance(result, dict):
            return tool_text("elicitation failed", is_error=True)
        action = result.get("action")
        if action == "accept":
            content = result.get("content")
            if not isinstance(content, dict):
                return tool_text("accept content must be an object", is_error=True)
            choice = content.get("choice")
            if choice == "other" and free:
                other = content.get("other_text", "")
                if not isinstance(other, str) or len(other) > 200:
                    return tool_text("other_text must be a string of at most 200 characters", is_error=True)
                return tool_text(json.dumps({"answer": other, "free_text": True},
                                            ensure_ascii=False))
            if isinstance(choice, str) and choice in {str(i) for i in range(1, len(choices) + 1)}:
                i = int(choice)
                return tool_text(json.dumps({"answer": choices[i - 1], "index": i}, ensure_ascii=False))
            return tool_text("choice must match a requested option", is_error=True)
        if action == "decline":
            return tool_text(json.dumps({"answer": None, "declined": True}) + "\n" + MSG_DECLINED)
        if action == "cancel":
            return tool_text(json.dumps({"answer": None, "cancelled": True}) + "\n" + MSG_CANCELLED)
        return tool_text("unexpected elicitation action", is_error=True)

    # ---- 回す ----
    def run(self):
        stdin = sys.stdin.buffer
        try:
            while not self._closed.is_set():
                line = stdin.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    # 長すぎる行は解釈しない。行の終わりまで読み捨て、次の行から読み続ける。
                    while line and not line.endswith(b"\n"):
                        line = stdin.readline(MAX_LINE + 1)
                    self.log("line too long")
                    self.error(None, -32700, "Parse error")
                    continue
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError):   # 壊れた JSON・UTF-8 でない・深すぎる入れ子
                    self.log("invalid JSON")
                    self.error(None, -32700, "Parse error")
                    continue
                self.on_message(msg)
        except (OSError, ValueError, KeyboardInterrupt):
            pass
        finally:
            self.close()
            with self._pending_lock:
                workers = list(self._workers)
            for worker in workers:
                worker.join()

    def close(self):
        self._closed.set()
        with self._pending_lock:
            for pending in self._calls.values():
                pending.cancelled = True
                pending.event.set()


def tool_text(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def validate_args(args):
    if not isinstance(args, dict):
        return "arguments must be an object"
    title = args.get("title")
    choices = args.get("choices")
    if not isinstance(title, str) or not title.strip():
        return "title must be a non-empty string"
    if len(title) > 80:
        return "title must be 80 characters or fewer"
    if not isinstance(choices, list) or not (2 <= len(choices) <= 6):
        return "choices must be a list of 2-6 strings"
    cleaned = []
    for c in choices:
        if not isinstance(c, str) or not c.strip():
            return "each choice must be a non-empty string"
        if len(c) > 40:
            return "each choice must be 40 characters or fewer"
        cleaned.append(c.strip())
    if len(set(cleaned)) != len(cleaned):
        return "choices must be distinct"
    if len(cleaned) == 6 and STOP_CHOICE not in cleaned:
        return "leave one of the six choices for 'ここで止める' (or supply at most five choices)"
    if "allow_free_text" in args and not isinstance(args["allow_free_text"], bool):
        return "allow_free_text must be a boolean"
    if "descriptions" in args:
        descriptions = args["descriptions"]
        if (not isinstance(descriptions, list) or len(descriptions) != len(choices)
                or not all(isinstance(d, str) for d in descriptions)):
            return "descriptions must be a string list with the same length as choices"
    return None


if __name__ == "__main__":
    Server().run()
