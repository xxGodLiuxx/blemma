# -*- coding: utf-8 -*-
"""hooks/_client.py = 板との失敗は全部「判断なし」(None)・答えは payload と照らす (§2.0・§3.3)。"""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

import pytest

import _client as C
import server as S
from conftest import FAST

HOOK_IN = {"session_id": "abcdef0123", "cwd": "/home/u/demo-repo", "hook_event_name": "PermissionRequest"}
PERM = {"head": "Bash", "text": "list", "blocks": [{"label": "command", "text": "ls", "mono": True}],
        "suggestions": [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "ls"}],
                         "behavior": "allow", "destination": "localSettings"}]}
QUESTIONS = {"questions": [
    {"question": "Which framework?", "header": "Framework", "multiSelect": False,
     "options": [{"label": "React", "description": "a"}, {"label": "Vue", "description": "b"}]},
    {"question": "Which parts?", "header": "Parts", "multiSelect": True,
     "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}]},
]}
FIELDS = {"head": "blemma", "text": "pick", "fields": [
    {"name": "choice", "title": "next", "required": True, "multi": False,
     "options": [{"label": "one", "value": "1"}, {"label": "two", "value": "2"},
                 {"label": "other", "terminal": True}]},
    {"name": "tags", "title": "tags", "required": False, "multi": True,
     "options": [{"label": "x", "value": "x"}, {"label": "y", "value": "y"}]},
    {"name": "ok", "title": "ok?", "required": True,
     "options": [{"label": "yes", "value": True}, {"label": "no", "value": False}]},
]}


def run_ask(srv, kind, payload, answer_choice, by="dwell"):
    """hook (別の thread) が ask し、頁 (この thread) が答える。"""
    out = {}

    def hook():
        t = time.monotonic()
        out["res"] = C.ask_detail(HOOK_IN, kind, payload, run_file=srv.run_file)
        out["sec"] = time.monotonic() - t

    th = threading.Thread(target=hook)
    th.start()
    card = srv.wait_card()
    if answer_choice is not None:
        st, body, _, _ = srv.request("POST", "/answer", {"id": card["id"], "seq": card["view_seq"],
                                                         "choice": answer_choice, "by": by, "presses": 1})
        assert st == 200, body
    th.join(10)
    assert not th.is_alive()
    return out["res"], out["sec"], card


def test_answer_after_grace(live):
    srv = live()
    (end, choice), sec, card = run_ask(srv, "permission", PERM, {"type": "allow_always", "suggestion": 0})
    assert end == "answered" and choice == {"type": "allow_always", "suggestion": 0}
    assert sec >= FAST.undo_ms / 1000.0                 # 猶予の分だけ遅れて確定
    assert card["from"] == {"cwd": "demo-repo", "session": "abcdef", "agent": None}


@pytest.mark.parametrize("choice", [{"type": "allow_once"}, {"type": "stop"}, {"type": "deny", "reason": 2}])
def test_permission_choices(live, choice):
    (end, got), _, _ = run_ask(live(), "permission", PERM, choice)
    assert end == "answered" and got == choice


def test_terminal_is_released_and_none(live):
    (end, choice), _, _ = run_ask(live(), "permission", PERM, {"type": "terminal"})
    assert (end, choice) == ("released", None)


def test_expired_is_none(live):
    srv = live(replace(FAST, wait=0.6, perm_wait=0.6))
    (end, choice), sec, _ = run_ask(srv, "permission", PERM, None)
    assert end in ("expired", "closed") and choice is None   # /wait の合間に切れたら closed
    assert sec < 3


def test_out_of_range_answer_is_none(live):
    (end, choice), _, _ = run_ask(live(), "permission", PERM, {"type": "allow_always", "suggestion": 3})
    assert (end, choice) == ("invalid", None)


def test_question_picks(live):
    (end, choice), _, _ = run_ask(live(), "question", QUESTIONS, {"type": "answer", "picks": [[1], [0, 2]]})
    assert end == "answered" and choice == {"type": "answer", "picks": [[1], [0, 2]]}


def test_elicitation_values_are_built_by_client(live):
    (end, choice), _, _ = run_ask(live(), "elicitation", FIELDS,
                                  {"type": "accept", "picks": [[1], [], [0]]})
    assert end == "answered"
    assert choice["values"] == {"choice": "2", "ok": True}      # 空のままの欄は入れない


def test_server_stopped_while_waiting_is_none(live):
    srv = live()
    out = {}
    th = threading.Thread(target=lambda: out.setdefault(
        "r", C.ask_detail(HOOK_IN, "permission", PERM, run_file=srv.run_file)))
    th.start()
    srv.wait_card()
    srv.close()
    th.join(10)
    assert out["r"][1] is None


def test_no_run_file_is_none(tmp_path):
    t = time.monotonic()
    assert C.ask_detail(HOOK_IN, "permission", PERM, run_file=tmp_path / "none.json") == ("no_board", None)
    assert time.monotonic() - t < 0.5


def test_broken_run_file_is_none(tmp_path):
    p = tmp_path / "run.json"
    for text in ("{", "[]", '{"port": "8765", "token": "x"}', '{"port": 8765}', '{"port": 0, "token": "x"}'):
        p.write_text(text, encoding="utf-8")
        assert C.ask(HOOK_IN, "permission", PERM, run_file=p) is None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_connection_refused_is_none(tmp_path):
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"port": free_port(), "token": "x"}), encoding="utf-8")
    t = time.monotonic()
    assert C.ask_detail(HOOK_IN, "permission", PERM, run_file=p) == ("no_board", None)
    assert time.monotonic() - t < 3


def test_silent_server_times_out(tmp_path, monkeypatch):
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(4)                                  # 受けるだけで何も返さない
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"port": lsock.getsockname()[1], "token": "x"}), encoding="utf-8")
    monkeypatch.setattr(C, "ASK_GIVEUP_SEC", 0.3)
    try:
        t = time.monotonic()
        assert C.ask(HOOK_IN, "permission", PERM, run_file=p) is None
        assert time.monotonic() - t < 2
    finally:
        lsock.close()


class _Fake(BaseHTTPRequestHandler):
    mode = "garbage"

    def log_message(self, *a):
        pass

    def _reply(self, code, raw):
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.mode == "garbage":
            self._reply(200, b"not json")
        elif self.mode == "busy":
            self._reply(503, b'{"error":"queue_full"}')
        else:
            self._reply(200, json.dumps({"id": "abc", "hard_deadline_in": 5, "wait_giveup": 0.3}).encode())

    def do_GET(self):
        if self.mode == "hang":
            time.sleep(1.5)
        elif self.mode == "weird":
            self._reply(200, b'{"state": "answered", "answer": "allow_once"}')
        else:
            self._reply(200, b"{")


@pytest.mark.parametrize("mode,end", [("garbage", "error"), ("busy", "busy"), ("hang", "timeout"),
                                      ("weird", "invalid"), ("brokenwait", "timeout")])
def test_broken_server_replies_are_none(tmp_path, mode, end):
    handler = type("H", (_Fake,), {"mode": mode})
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    th = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    th.start()
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"port": httpd.server_address[1], "token": "x"}), encoding="utf-8")
    try:
        assert C.ask_detail(HOOK_IN, "permission", PERM, run_file=p) == (end, None)
    finally:
        httpd.shutdown()
        httpd.server_close()


def _serve(handler) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    httpd.block_on_close = False
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return httpd


def _stop(*servers) -> None:
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


class _Drip(BaseHTTPRequestHandler):
    """/ask = 自前の期限 0.3 秒・/wait = 答え (allow_once) を 2 byte ずつ 0.05 秒おきに返す。
    1 回の読みは 0.05 秒で届く = 1 回ごとの時間切れでは止まらない (全部を返し終えるのは 1.3 秒以上の後)。
    head = 状態の行と見出しも少しずつ返す。"""
    head = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        raw = json.dumps({"id": "abc", "hard_deadline_in": 0.3, "wait_giveup": 5}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        raw = json.dumps({"state": "answered", "answer": {"type": "allow_once"}}).encode()
        head = b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(raw)
        out, start = head + raw, 0
        self.close_connection = True
        try:
            if not self.head:
                self.wfile.write(head)
                start = len(head)
            for i in range(start, len(out), 2):
                self.wfile.write(out[i:i + 2])
                time.sleep(0.05)
        except OSError:
            pass                                         # client が諦めて切った


@pytest.mark.parametrize("head", [False, True])
def test_slow_reply_cannot_outlive_own_deadline(tmp_path, head):
    """自前の期限は受け終えるまで効く総期限 (§3.4)。少しずつ返されても延びず、判断なしで終わる。"""
    httpd = _serve(type("H", (_Drip,), {"head": head}))
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"port": httpd.server_address[1], "token": "x"}), encoding="utf-8")
    try:
        t = time.monotonic()
        assert C.ask_detail(HOOK_IN, "permission", PERM, run_file=p) == ("timeout", None)
        assert time.monotonic() - t < 1.0             # 返し終える (1.3 秒以上) のを待たない
    finally:
        _stop(httpd)


def test_answer_received_after_own_deadline_is_none(tmp_path, monkeypatch):
    """/wait を受け終えたのが自前の期限の後なら、答えでも使わない (受けた後にも期限を見直す)。"""
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"port": 9, "token": "x"}), encoding="utf-8")

    def late_call(method, port, token, path, body=None, timeout=0.0):
        if path == "/ask":
            return 200, {"id": "abc", "hard_deadline_in": 0.2, "wait_giveup": 5}
        time.sleep(0.3)                                  # 受け終えた時には期限 (0.2 秒) を過ぎている
        return 200, {"state": "answered", "answer": {"type": "allow_once"}}

    monkeypatch.setattr(C, "_call", late_call)
    assert C.ask_detail(HOOK_IN, "permission", PERM, run_file=p) == ("timeout", None)


def test_bad_kind_is_none(tmp_path):
    assert C.ask_detail(HOOK_IN, "plan", {}, run_file=tmp_path / "x") == ("invalid", None)


def test_run_file_env_override(tmp_path, monkeypatch):
    p = tmp_path / "run.json"
    monkeypatch.setenv(C.RUN_FILE_ENV, str(p))
    assert C.run_file_path() == p
    monkeypatch.delenv(C.RUN_FILE_ENV)
    assert C.run_file_path().parts[-3:] == ("board", "state", "run.json")


def test_notify(live, tmp_path):
    assert C.notify({"message": "m"}, run_file=tmp_path / "none.json") is False
    srv = live()
    assert C.notify({"notification_type": "idle_prompt", "message": "waiting", "cwd": "/x/repo"},
                    run_file=srv.run_file) is True
    light = srv.pending()["light"]
    assert light["type"] == "idle_prompt" and light["from"]["cwd"] == "repo"


def test_read_input():
    assert C.read_input(io.BytesIO('{"a": "日本語"}'.encode("utf-8"))) == {"a": "日本語"}
    assert C.read_input(io.BytesIO(b"\xef\xbb\xbf{}")) == {}
    assert C.read_input(io.BytesIO("{}".encode("cp932") + b"\x82")) is None
    assert C.read_input(io.BytesIO('{"a": "日本"}'.encode("cp932"))) is None
    assert C.read_input(io.BytesIO(b"[1]")) is None
    assert C.read_input(io.BytesIO(b"")) is None


def test_emit_is_ascii(capsys):
    C.emit({"message": "別のやり方でお願いします"})
    out = capsys.readouterr().out
    assert out.isascii() and json.loads(out) == {"message": "別のやり方でお願いします"}


def test_debug_only_with_env(capsys, monkeypatch):
    monkeypatch.delenv(C.DEBUG_ENV, raising=False)
    C.debug("x")
    assert capsys.readouterr().err == ""
    monkeypatch.setenv(C.DEBUG_ENV, "1")
    C.debug("line1\nline2")
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("BLEMMA:")


@pytest.mark.parametrize("ans,ok", [
    ({"type": "answer", "picks": [[0], [1]]}, True),
    ({"type": "answer", "picks": [[0, 1], [1]]}, False),     # 単一選択に 2 つ
    ({"type": "answer", "picks": [[0], []]}, False),         # multiSelect も 1 つ以上
    ({"type": "answer", "picks": [[0], [1, 1]]}, False),     # 重なり
    ({"type": "answer", "picks": [[2], [1]]}, False),        # 範囲の外
    ({"type": "answer", "picks": [[0]]}, False),             # 問いの数と違う
    ({"type": "answer", "picks": [[True], [1]]}, False),
    ({"type": "skip"}, True),
    ({"type": "deny", "reason": 0}, False),
])
def test_check_question(ans, ok):
    assert (C._check_choice("question", QUESTIONS, ans) is not None) is ok


@pytest.mark.parametrize("picks,ok", [
    ([[0], [0, 1], [1]], True),
    ([[2], [], [0]], False),          # terminal の選択肢は accept に入らない
    ([[], [], [0]], False),           # required が空
    ([[0], [], []], False),
    ([[0, 1], [], [0]], False),       # 単一に 2 つ
])
def test_check_elicitation(picks, ok):
    got = C._check_choice("elicitation", FIELDS, {"type": "accept", "picks": picks})
    assert (got is not None) is ok
    if ok:
        assert got["values"] == {"choice": "1", "tags": ["x", "y"], "ok": False}


def test_check_permission_reasons():
    custom = dict(PERM, reasons=["only one"])
    assert C._check_choice("permission", custom, {"type": "deny", "reason": 0}) == {"type": "deny", "reason": 0}
    assert C._check_choice("permission", custom, {"type": "deny", "reason": 1}) is None
    assert C._check_choice("permission", PERM, {"type": "deny", "reason": 2}) is not None
    assert C._check_choice("permission", {"head": "x"}, {"type": "allow_always", "suggestion": 0}) is None
    assert C._check_choice("permission", PERM, {"type": "terminal"}) is None


def test_ask_giveup_matches_server_limits():
    """client だけが写して持つ数は 1 つ = server の Limits と同じ値 (数は 1 か所)。"""
    assert C.ASK_GIVEUP_SEC == S.Limits().ask_giveup
