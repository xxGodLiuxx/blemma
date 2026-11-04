# -*- coding: utf-8 -*-
"""hooks/permission.py・ask.py・elicitation.py = stdin の JSON → 板 → 公式の JSON (§2.1〜§2.3・§10.3)。

偽の板 (http.server の thread) が `/ask` の本文を控えて `/wait` に固定の答えを返し、hook を subprocess で
走らせる。stdin の形は実機 (Claude Code v2.1.318) で受けた物に合わせた (値はダミー)。見る物 = stdout が
公式の形の JSON 1 個 (ASCII) か空・exit 0・stderr は空・板に出す物 (payload)・除外と板なしで無出力。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import _client as C

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
TOKEN = "fake-board-token"


class FakeBoard:
    """偽の板 = `/ask` の本文を控え、`/wait` に reply を返す (答えは即時)。"""

    def __init__(self, tmp: Path) -> None:
        self.asks: list = []
        self.reply: dict = {"state": "released"}
        board = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.headers.get("X-Blemma-Token") != TOKEN or self.path != "/ask":
                    return self._send(401, {"error": "token"})
                board.asks.append(json.loads(raw.decode("utf-8")))
                self._send(200, {"id": f"card-{len(board.asks)}", "hard_deadline_in": 30, "wait_giveup": 5})

            def do_GET(self):
                if self.headers.get("X-Blemma-Token") != TOKEN or not self.path.startswith("/wait?id="):
                    return self._send(401, {"error": "token"})
                self._send(200, board.reply)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.run_file = tmp / "run.json"
        self.run_file.write_text(json.dumps({"port": self.httpd.server_address[1], "token": TOKEN}),
                                 encoding="utf-8")
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def answer(self, choice: dict) -> None:
        self.reply = {"state": "answered", "answer": choice}

    def end(self, state: str) -> None:
        self.reply = {"state": state}

    @property
    def payload(self) -> dict:
        assert len(self.asks) == 1
        return self.asks[0]["payload"]

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def board(tmp_path):
    b = FakeBoard(tmp_path)
    yield b
    b.close()


def run(hook: str, data=None, run_file=None, env=None, raw=None):
    """hook を素の python で 1 回走らせる (偽の Claude Code)。stdout は Windows の既定に近い cp932 に。"""
    e = {k: v for k, v in os.environ.items() if not k.startswith("BLEMMA_")}
    e["PYTHONIOENCODING"] = "cp932"
    e[C.RUN_FILE_ENV] = str(run_file)
    e.update(env or {})
    body = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    return subprocess.run([sys.executable, str(HOOKS / hook)], input=body, capture_output=True,
                          timeout=60, env=e)


def one_json(p) -> dict:
    """stdout = ASCII の JSON 1 個だけ・exit 0・stderr は空。"""
    assert (p.returncode, p.stderr) == (0, b""), p.stderr
    s = p.stdout.decode("ascii")
    obj, end = json.JSONDecoder().raw_decode(s)
    assert s[end:].strip() == ""
    return obj


def silent(p) -> None:
    """判断なし = 何も書かず exit 0。"""
    assert (p.returncode, p.stdout, p.stderr) == (0, b"", b""), (p.stdout, p.stderr)


BASE = {"session_id": "abcdef-demo-session",
        "transcript_path": "/home/u/.claude/projects/demo/abcdef-demo-session.jsonl",
        "cwd": "/home/u/demo-repo", "prompt_id": "demo-prompt",
        "permission_mode": "default", "effort": {"level": "medium"}}


# ---------------------------------------------------------------------------
# 権限の口 = hooks/permission.py (§2.1)
# ---------------------------------------------------------------------------

def perm(tool_name, tool_input, suggestions=None, **extra) -> dict:
    d = dict(BASE, hook_event_name="PermissionRequest", tool_name=tool_name, tool_input=tool_input)
    if suggestions is not None:
        d["permission_suggestions"] = suggestions
    d.update(extra)
    return d


ACCEPT_EDITS = {"type": "setMode", "mode": "acceptEdits", "destination": "session"}
GIT_RULE = {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "git commit *"}],
            "behavior": "allow", "destination": "localSettings"}
DIRS = {"type": "addDirectories", "directories": ["/home/u/demo-repo"], "destination": "session"}
BYPASS = {"type": "setMode", "mode": "bypassPermissions", "destination": "session"}
EDIT = perm("Edit", {"file_path": "/home/u/demo-repo/README.md", "old_string": "行01: りんご",
                     "new_string": "行01: 林檎", "replace_all": False}, [ACCEPT_EDITS])
BASH = perm("Bash", {"command": 'git commit -m "誤字を直す"', "description": "Commit the fix"}, [GIT_RULE])
MCP = perm("mcp__blemma__ask_board",
           {"title": "次の一手を選んでください", "choices": ["PR の本文を書く", "試験を回す", "ここで止める"]},
           [{"type": "addRules", "rules": [{"toolName": "mcp__blemma__ask_board"}], "behavior": "allow",
             "destination": "localSettings"}],
           mcp_server={"name": "blemma", "source": "dynamic"},
           agent_id="demo-agent", agent_type="general-purpose")
ALLOW = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}


def blocks(payload) -> dict:
    """本文の blocks を {見出し: 字} に (見出しが {ja, en} なら en の頭の語)。"""
    out = {}
    for b in payload["blocks"]:
        label = b["label"] if isinstance(b["label"], str) else b["label"]["en"].split(" ")[0]
        out[label] = b["text"]
    return out


def test_perm_allow_once_edit(board):
    board.answer({"type": "allow_once"})
    assert one_json(run("permission.py", EDIT, board.run_file)) == ALLOW
    ask = board.asks[0]
    assert ask["kind"] == "permission"
    assert ask["from"] == {"cwd": "demo-repo", "session": "abcdef", "agent": None}
    p = board.payload
    assert (p["head"], p["text"]) == ("Edit", "README.md")
    assert blocks(p) == {"file": "/home/u/demo-repo/README.md", "old_string": "行01: りんご",
                         "new_string": "行01: 林檎"}     # replace_all: false は省く・日本語はそのまま
    assert p["suggestions"] == [ACCEPT_EDITS]


def test_perm_allow_always_copies_the_suggestion_verbatim(board):
    board.answer({"type": "allow_always", "suggestion": 0})
    out = one_json(run("permission.py", BASH, board.run_file))
    assert out["hookSpecificOutput"]["decision"] == {"behavior": "allow", "updatedPermissions": [GIT_RULE]}
    p = board.payload
    assert (p["head"], p["text"]) == ("Bash", "Commit the fix")
    assert blocks(p) == {"command": 'git commit -m "誤字を直す"'}


def test_perm_set_mode_suggestion(board):
    board.answer({"type": "allow_always", "suggestion": 1})
    data = perm("Bash", {"command": "mkdir 試し_一", "description": "Create a directory"}, [DIRS, ACCEPT_EDITS])
    out = one_json(run("permission.py", data, board.run_file))
    assert out["hookSpecificOutput"]["decision"]["updatedPermissions"] == [ACCEPT_EDITS]


def test_perm_offers_two_known_suggestions_without_bypass(board):
    """板に出すのは公式の 6 種だけ・bypassPermissions へ移す物は除く・2 件まで。番号はこの列で引く。"""
    third = dict(GIT_RULE, destination="userSettings")
    board.answer({"type": "allow_always", "suggestion": 1})
    data = perm("Bash", {"command": "git commit -m x"}, [BYPASS, "junk", {"type": "unknown"}, DIRS, GIT_RULE, third])
    out = one_json(run("permission.py", data, board.run_file))
    assert board.payload["suggestions"] == [DIRS, GIT_RULE]
    assert out["hookSpecificOutput"]["decision"]["updatedPermissions"] == [GIT_RULE]


@pytest.mark.parametrize("j", [0, 1, 2])
def test_perm_deny_with_a_fixed_reason(board, j):
    board.answer({"type": "deny", "reason": j})
    dec = one_json(run("permission.py", EDIT, board.run_file))["hookSpecificOutput"]["decision"]
    ja, en = C.DENY_REASONS[j]
    assert dec["behavior"] == "deny" and dec["interrupt"] is False
    assert ja in dec["message"] and en in dec["message"] and dec["message"].startswith("BLEMMA:")


def test_perm_stop_is_deny_with_interrupt(board):
    board.answer({"type": "stop"})
    assert one_json(run("permission.py", BASH, board.run_file)) == {"hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "deny", "message": "BLEMMA: the user stopped the work", "interrupt": True}}}


@pytest.mark.parametrize("state", ["released", "expired", "disconnected", "closed", "unknown-state"])
def test_perm_no_decision_ends_are_silent(board, state):
    if state == "unknown-state":
        board.reply = {"state": "?"}             # 知らない状態 = 壊れた返り
    else:
        board.end(state)
    silent(run("permission.py", EDIT, board.run_file))


@pytest.mark.parametrize("choice", [
    {"type": "terminal"},                         # 端末で答える (板は released で返すが、answered で来ても)
    {"type": "allow"},                            # 知らない語
    {"type": "allow_always", "suggestion": 1},    # 範囲の外 (出した suggestion は 1 件)
    {"type": "allow_always", "suggestion": True},
    {"type": "deny", "reason": 3},
    {"type": "deny"},
    "allow_once",
])
def test_perm_unknown_or_out_of_range_answers_are_silent(board, choice):
    board.answer(choice)
    silent(run("permission.py", EDIT, board.run_file))


@pytest.mark.parametrize("data,env", [
    (perm("ExitPlanMode", {"plan": "1. 直す"}), None),
    (perm("AskUserQuestion", {"questions": [{"question": "続けますか?", "header": "確認", "multiSelect": False,
                                             "options": [{"label": "はい"}, {"label": "いいえ"}]}]}), None),
    (dict(EDIT, permission_mode="plan"), None),
    (BASH, {"BLEMMA_TERMINAL_ONLY": "WebFetch, Bash"}),
    (dict(EDIT, hook_event_name="PreToolUse"), None),
    ({k: v for k, v in EDIT.items() if k != "tool_input"}, None),
    ({k: v for k, v in EDIT.items() if k != "tool_name"}, None),
])
def test_perm_excluded_never_reach_the_board(board, data, env):
    board.answer({"type": "allow_once"})
    silent(run("permission.py", data, board.run_file, env=env))
    assert board.asks == []


def test_perm_terminal_only_env_lets_other_tools_through(board):
    board.answer({"type": "allow_once"})
    assert one_json(run("permission.py", EDIT, board.run_file, env={"BLEMMA_TERMINAL_ONLY": "Bash"})) == ALLOW


def test_perm_without_board_is_silent_and_quick(tmp_path):
    t = time.monotonic()
    silent(run("permission.py", EDIT, tmp_path / "none.json"))
    assert time.monotonic() - t < 10


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1, 2]", '{"tool_name": "日本"}'.encode("cp932"),
                                 b'{"tool_name": "Edit", "tool_input": {"file_path": 1}'])
def test_perm_broken_stdin_is_silent(board, raw):
    board.answer({"type": "allow_once"})
    silent(run("permission.py", run_file=board.run_file, raw=raw))
    assert board.asks == []


def test_perm_bash_command_is_never_cut(board):
    cmd = "echo " + "あ" * 20000 + " && rm -rf ./build"
    board.answer({"type": "allow_once"})
    assert one_json(run("permission.py", perm("Bash", {"command": cmd}), board.run_file)) == ALLOW
    assert blocks(board.payload)["command"] == cmd


def test_perm_too_big_card_goes_to_the_terminal(board):
    board.answer({"type": "allow_once"})
    silent(run("permission.py", perm("Bash", {"command": "echo " + "x" * 300_000}), board.run_file))
    assert board.asks == []


def test_perm_hidden_characters_are_shown(board):
    board.answer({"type": "allow_once"})
    one_json(run("permission.py", perm("Bash", {"command": "echo ok‮; rm -rf ./tmp​\r"}),
                 board.run_file))
    assert blocks(board.payload)["command"] == "echo ok⟨U+202E⟩; rm -rf ./tmp⟨U+200B⟩⟨U+000D⟩"


def test_perm_other_bash_input_is_not_hidden(board):
    board.answer({"type": "allow_once"})
    one_json(run("permission.py", perm("Bash", {"command": "ls", "description": "list", "timeout": 600000,
                                                "dangerouslyDisableSandbox": True,
                                                "run_in_background": False}), board.run_file))
    other = json.loads(blocks(board.payload)["other input"])
    assert other == {"timeout": 600000, "dangerouslyDisableSandbox": True}


def test_perm_mcp_tool_shows_server_tool_and_input(board):
    board.answer({"type": "allow_always", "suggestion": 0})
    out = one_json(run("permission.py", MCP, board.run_file))
    assert out["hookSpecificOutput"]["decision"]["updatedPermissions"] == MCP["permission_suggestions"]
    assert board.asks[0]["from"]["agent"] == "general-purpose"
    b = blocks(board.payload)
    assert (board.payload["head"], b["server"], b["tool"]) == ("mcp__blemma__ask_board", "blemma", "ask_board")
    assert json.loads(b["input"]) == MCP["tool_input"]


def test_perm_long_json_input_is_clipped_with_a_note(board):
    board.answer({"type": "allow_once"})
    one_json(run("permission.py", perm("mcp__docs__save", {"text": "字" * 5000}), board.run_file))
    b = board.payload["blocks"][-1]
    assert "続きは端末で" in b["label"]["ja"] and b["label"]["en"].startswith("input (first 2000 of ")
    assert len(b["text"]) == 2002                 # 2,000 字 + 「\n…」


def test_perm_write_shows_the_first_40_lines(board):
    board.answer({"type": "allow_once"})
    content = "".join(f"行{i}\n" for i in range(100))
    one_json(run("permission.py", perm("Write", {"file_path": "/home/u/demo-repo/新規.md", "content": content}),
                 board.run_file))
    b = board.payload["blocks"]
    assert board.payload["text"] == "新規.md"
    assert b[1]["text"].startswith("行0\n") and "行39\n" in b[1]["text"] and "行40" not in b[1]["text"]
    assert "全 100 行" in b[1]["label"]["ja"]


def test_perm_debug_writes_only_blemma_lines(tmp_path):
    p = run("permission.py", EDIT, tmp_path / "none.json", env={"BLEMMA_DEBUG": "1"})
    assert (p.returncode, p.stdout) == (0, b"")
    lines = p.stderr.decode("cp932").splitlines()
    assert lines and all(x.startswith("BLEMMA: ") for x in lines)


# ---------------------------------------------------------------------------
# 質問の口 = hooks/ask.py (§2.2)
# ---------------------------------------------------------------------------

def opts(*labels) -> list:
    return [{"label": x, "description": f"{x} の説明"} for x in labels]


FRUIT = {"question": "どの果物にしますか?", "header": "果物", "multiSelect": False,
         "options": opts("りんご", "みかん", "ぶどう", "もも")}
COLOR = {"question": "どの色を使いますか? (複数可)", "header": "色", "multiSelect": True,
         "options": opts("赤", "青, 濃い", "緑")}
PRINT = {"question": "印刷しますか?", "header": "印刷", "multiSelect": False,
         "options": opts("印刷する", "印刷しない")}


def question(*qs, **extra) -> dict:
    ti = {"questions": list(qs)}
    ti.update(extra.pop("tool_input_extra", {}))
    d = dict(BASE, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_input=ti,
             tool_use_id="toolu_demo")
    d.update(extra)
    return d


def test_ask_two_questions_in_one_card(board):
    """2 問 (4 択 + multiSelect) を 1 枚で = §10.3 で通った形 (label のカンマはそのまま)。"""
    data = question(FRUIT, COLOR)
    board.answer({"type": "answer", "picks": [[1], [1, 2]]})
    out = one_json(run("ask.py", data, board.run_file))["hookSpecificOutput"]
    assert (out["hookEventName"], out["permissionDecision"]) == ("PreToolUse", "allow")
    assert out["updatedInput"] == dict(data["tool_input"], answers={
        "どの果物にしますか?": "みかん", "どの色を使いますか? (複数可)": "青, 濃い, 緑"})
    assert board.asks[0]["kind"] == "question"
    assert board.payload == {"questions": [FRUIT, COLOR]}     # 問いはそのまま (番号を照らす元)


def test_ask_one_question_keeps_other_input(board):
    data = question(PRINT, tool_input_extra={"metadata": {"source": "demo"}})
    board.answer({"type": "answer", "picks": [[0]]})
    out = one_json(run("ask.py", data, board.run_file))["hookSpecificOutput"]
    assert out["updatedInput"] == {"questions": [PRINT], "metadata": {"source": "demo"},
                                   "answers": {"印刷しますか?": "印刷する"}}


def test_ask_multiselect_with_one_pick_is_the_label(board):
    board.answer({"type": "answer", "picks": [[2]]})
    out = one_json(run("ask.py", question(COLOR), board.run_file))["hookSpecificOutput"]
    assert out["updatedInput"]["answers"] == {"どの色を使いますか? (複数可)": "緑"}


def test_ask_skip_is_deny_with_reason(board):
    board.answer({"type": "skip"})
    assert one_json(run("ask.py", question(PRINT), board.run_file)) == {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": "BLEMMA: the user did not answer this question"}}


@pytest.mark.parametrize("reply", [
    {"state": "released"}, {"state": "expired"}, {"state": "disconnected"},
    {"state": "answered", "answer": {"type": "terminal"}},
    {"state": "answered", "answer": {"type": "answer", "picks": [[1]]}},          # 問いの数と違う
    {"state": "answered", "answer": {"type": "answer", "picks": [[0, 1], [0]]}},  # 単一選択に 2 つ
    {"state": "answered", "answer": {"type": "answer", "picks": [[4], [0]]}},     # 範囲の外
    {"state": "answered", "answer": {"type": "answer", "picks": [[0], []]}},      # multiSelect も 1 つ以上
    {"state": "answered", "answer": {"type": "allow"}},
])
def test_ask_no_decision_is_silent(board, reply):
    board.reply = reply
    silent(run("ask.py", question(FRUIT, COLOR), board.run_file))


@pytest.mark.parametrize("data", [
    question(),                                                    # 0 問
    question(FRUIT, COLOR, PRINT, dict(PRINT, question="別"), dict(PRINT, question="もう 1 つ")),  # 5 問
    question(PRINT, dict(PRINT, header="同じ問い")),               # 問いの文が重なる = answers の鍵がぶつかる
    question(dict(PRINT, options=opts("1 つだけ"))),
    question(dict(PRINT, options=opts("a", "b", "c", "d", "e"))),
    question(dict(PRINT, options=[{"label": 1}, {"label": "b"}])),
    question(dict(PRINT, options=[{"label": ""}, {"label": "b"}])),
    question(dict(PRINT, multiSelect="yes")),
    question(dict(PRINT, question="")),
    dict(question(PRINT), tool_input={"questions": "印刷しますか?"}),
    {k: v for k, v in question(PRINT).items() if k != "tool_input"},
    dict(question(PRINT), tool_name="Bash"),
    dict(question(PRINT), hook_event_name="PermissionRequest"),
])
def test_ask_shapes_the_board_cannot_take_are_silent(board, data):
    board.answer({"type": "skip"})
    silent(run("ask.py", data, board.run_file))
    assert board.asks == []


def test_ask_terminal_only_env(board):
    board.answer({"type": "skip"})
    silent(run("ask.py", question(PRINT), board.run_file, env={"BLEMMA_TERMINAL_ONLY": "AskUserQuestion"}))
    assert board.asks == []


def test_ask_without_board_is_silent(tmp_path):
    silent(run("ask.py", question(FRUIT, COLOR), tmp_path / "none.json"))


# ---------------------------------------------------------------------------
# MCP の問いの口 = hooks/elicitation.py (§2.3)
# ---------------------------------------------------------------------------

def elicit(schema, message="次の一手を選んでください", **extra) -> dict:
    d = {k: v for k, v in BASE.items() if k not in ("permission_mode", "effort")}   # form では来ない (実機)
    d.update(hook_event_name="Elicitation", mcp_server_name="blemma", message=message, mode="form",
             requested_schema=schema)
    d.update(extra)
    return d


CHOICES = [{"const": "1", "title": "PR の本文を書く"}, {"const": "2", "title": "試験を回す"},
           {"const": "3", "title": "ここで止める"}]
ASK_BOARD = {"type": "object", "required": ["choice"], "properties": {
    "choice": {"type": "string", "title": "次の一手を選んでください", "oneOf": CHOICES}}}
ASK_BOARD_FREE = {"type": "object", "required": ["choice"], "properties": {
    "choice": {"type": "string", "title": "次の一手を選んでください",
               "oneOf": CHOICES + [{"const": "other", "title": "ほかの答え (書いて伝える)"}]},
    "other_text": {"type": "string", "title": "ほかの答え", "maxLength": 200}}}
CHOICE_FIELD = {"name": "choice", "title": "次の一手を選んでください", "multi": False, "required": True,
                "options": [{"label": "PR の本文を書く", "value": "1"}, {"label": "試験を回す", "value": "2"},
                            {"label": "ここで止める", "value": "3"}]}


def test_elicit_ask_board_accept(board):
    board.answer({"type": "accept", "picks": [[1]]})
    assert one_json(run("elicitation.py", elicit(ASK_BOARD), board.run_file)) == {"hookSpecificOutput": {
        "hookEventName": "Elicitation", "action": "accept", "content": {"choice": "2"}}}
    ask = board.asks[0]
    assert (ask["kind"], ask["from"]["agent"]) == ("elicitation", None)
    assert board.payload == {"head": "blemma", "text": "次の一手を選んでください", "fields": [CHOICE_FIELD]}


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_elicit_decline_and_cancel(board, action):
    board.answer({"type": action})
    assert one_json(run("elicitation.py", elicit(ASK_BOARD), board.run_file)) == {"hookSpecificOutput": {
        "hookEventName": "Elicitation", "action": action}}


def test_elicit_free_text_choice_goes_to_the_terminal(board):
    """「ほかの答え」は端末で答える釦・書く欄 other_text は板に出さない (空のまま)。"""
    board.answer({"type": "accept", "picks": [[0]]})
    out = one_json(run("elicitation.py", elicit(ASK_BOARD_FREE), board.run_file))
    assert out["hookSpecificOutput"]["content"] == {"choice": "1"}
    field = dict(CHOICE_FIELD, options=CHOICE_FIELD["options"] + [
        {"label": "ほかの答え (書いて伝える)", "terminal": True}])
    assert board.payload["fields"] == [field]


def test_elicit_free_text_picked_on_the_board_is_silent(board):
    board.answer({"type": "accept", "picks": [[3]]})        # 端末の印の釦は accept に入らない
    silent(run("elicitation.py", elicit(ASK_BOARD_FREE), board.run_file))


def test_elicit_boolean_enum_and_multi_select(board):
    schema = {"type": "object", "required": ["ok"], "properties": {
        "ok": {"type": "boolean", "title": "続けますか?", "default": True},
        "color": {"type": "string", "description": "色", "enum": ["red", "green", "blue"],
                  "enumNames": ["赤", "緑", "青"], "default": "green"},
        "tags": {"type": "array", "title": "札", "minItems": 1,
                 "items": {"anyOf": [{"const": "a", "title": "甲"}, {"const": "b", "title": "乙"},
                                     {"const": "c", "title": "丙"}]}, "default": ["b"]}}}
    board.answer({"type": "accept", "picks": [[1], [2], [0, 2]]})
    out = one_json(run("elicitation.py", elicit(schema, message="選んでください"), board.run_file))
    assert out["hookSpecificOutput"]["content"] == {"ok": False, "color": "blue", "tags": ["a", "c"]}
    ok, color, tags = board.payload["fields"]
    assert ok == {"name": "ok", "title": "続けますか?", "multi": False, "required": True, "default": [0],
                  "options": [{"label": {"ja": "はい", "en": "Yes"}, "value": True},
                              {"label": {"ja": "いいえ", "en": "No"}, "value": False}]}
    assert (color["title"], color["required"], color["default"]) == ("色", False, [1])
    assert [o["label"] for o in color["options"]] == ["赤", "緑", "青"]
    assert (tags["multi"], tags["default"], [o["value"] for o in tags["options"]]) == (True, [1], ["a", "b", "c"])


def test_elicit_optional_fields_left_empty(board):
    """任意の欄は空のまま送れる・板で描けない任意の欄 (文字・数) は札に出さない。"""
    schema = {"type": "object", "required": ["choice"], "properties": {
        "choice": ASK_BOARD["properties"]["choice"],
        "note": {"type": "string", "title": "メモ"},
        "count": {"type": "integer", "minimum": 1, "maximum": 3},
        "flag": {"type": "boolean"}}}
    board.answer({"type": "accept", "picks": [[2], []]})
    out = one_json(run("elicitation.py", elicit(schema), board.run_file))
    assert out["hookSpecificOutput"]["content"] == {"choice": "3"}
    assert [f["name"] for f in board.payload["fields"]] == ["choice", "flag"]


def _props(n):
    return {f"f{i}": {"type": "boolean"} for i in range(n)}


@pytest.mark.parametrize("data", [
    elicit(ASK_BOARD, mode="url", url="https://example.com/login"),
    elicit(ASK_BOARD, url="https://example.com/login"),
    elicit({"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}),
    elicit({"type": "object", "required": ["n"], "properties": {"n": {"type": "integer", "minimum": 1}}}),
    elicit({"type": "object", "properties": _props(7)}),
    elicit({"type": "object", "properties": {}}),
    elicit({"type": "object", "properties": {"note": {"type": "string"}}}),      # 描く欄が 0
    elicit({"type": "object", "required": ["t"], "properties": {"t": {
        "type": "array", "minItems": 2, "items": {"enum": ["a", "b", "c"]}}}}),
    elicit({"type": "object", "required": ["t"], "properties": {"t": {
        "type": "array", "maxItems": 1, "items": {"enum": ["a", "b", "c"]}}}}),
    elicit({"type": "object", "required": ["c"], "properties": {"c": {"enum": [str(i) for i in range(13)]}}}),
    elicit({"type": "object", "required": ["c"], "properties": {"c": {"enum": [{"x": 1}, "b"]}}}),
    elicit({"type": "array"}),
    elicit(None),
    {k: v for k, v in elicit(ASK_BOARD).items() if k != "mcp_server_name"},
    dict(elicit(ASK_BOARD), hook_event_name="PreToolUse"),
])
def test_elicit_forms_the_board_cannot_take_are_silent(board, data):
    board.answer({"type": "cancel"})
    silent(run("elicitation.py", data, board.run_file))
    assert board.asks == []


@pytest.mark.parametrize("reply", [
    {"state": "released"}, {"state": "expired"}, {"state": "disconnected"},
    {"state": "answered", "answer": {"type": "terminal"}},
    {"state": "answered", "answer": {"type": "accept", "picks": [[]]}},           # 必須の欄が空
    {"state": "answered", "answer": {"type": "accept", "picks": [[0, 1]]}},       # 単一に 2 つ
    {"state": "answered", "answer": {"type": "accept", "picks": [[5]]}},
    {"state": "answered", "answer": {"type": "deny", "reason": 0}},
])
def test_elicit_no_decision_is_silent(board, reply):
    board.reply = reply
    silent(run("elicitation.py", elicit(ASK_BOARD), board.run_file))


def test_elicit_without_board_is_silent(tmp_path):
    silent(run("elicitation.py", elicit(ASK_BOARD), tmp_path / "none.json"))


# ---------------------------------------------------------------------------
# 共通の入口 = _client.run_hook (何があっても exit 0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [ZeroDivisionError, KeyboardInterrupt, SystemExit])
def test_run_hook_always_exits_zero(capsys, exc):
    def main():
        raise exc()

    with pytest.raises(SystemExit) as e:
        C.run_hook(main)
    assert e.value.code == 0
    assert capsys.readouterr().out == ""


def test_run_hook_survives_a_broken_stdout(monkeypatch):
    class Broken:
        def write(self, s):
            raise BrokenPipeError()

        def flush(self):
            raise BrokenPipeError()

        def fileno(self):
            raise OSError("no fd")

    monkeypatch.setattr(sys, "stdout", Broken())
    with pytest.raises(SystemExit) as e:
        C.run_hook(lambda: C.emit({"a": 1}))
    assert e.value.code == 0
