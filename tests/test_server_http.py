# -*- coding: utf-8 -*-
"""HTTP の口 (§3.3) = token・Host・CORS なし・静的の頁・long-poll・run.json・port の使用中。"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from dataclasses import replace

import pytest

import server as S
from conftest import FAST

PERM = {"head": "Bash", "text": "一覧を出す", "blocks": [{"label": "command", "text": "echo 日本語 && ls", "mono": True}]}


def post_ask(srv, kind="permission", payload=None):
    st, body, _, _ = srv.request("POST", "/ask", {"kind": kind, "from": {"cwd": "repo"},
                                                  "payload": payload or dict(PERM)})
    assert st == 200, body
    return body


def test_ask_returns_id_and_deadlines(live):
    srv = live()
    body = post_ask(srv)
    assert isinstance(body["id"], str) and len(body["id"]) == 16
    assert body["hard_deadline_in"] == FAST.hard_deadline
    assert body["wait_giveup"] == FAST.wait_giveup
    assert body["hard_deadline"] > time.time()


def test_token_is_required(live):
    srv = live()
    assert srv.request("GET", "/pending", token=None)[0] == 401
    assert srv.request("GET", "/pending", token="wrong")[0] == 401
    assert srv.request("POST", "/ask", {"kind": "permission", "payload": {}}, token=None)[0] == 401
    assert srv.request("GET", "/pending")[0] == 200


def test_host_is_checked(live):
    srv = live(allow_hosts=["phone.example"])
    assert srv.request("GET", "/pending", host=f"evil.example:{srv.port}")[0] == 403
    assert srv.request("GET", "/", host="evil.example")[0] == 403
    assert srv.request("GET", "/pending", host=f"localhost:{srv.port}")[0] == 200
    assert srv.request("GET", "/pending", host=f"LOCALHOST:{srv.port}")[0] == 200
    assert srv.request("GET", "/pending", host="phone.example")[0] == 200
    assert srv.request("GET", "/pending", host="127.0.0.1.evil.example")[0] == 403


def test_no_cors_headers(live):
    srv = live()
    st, _, hdrs, _ = srv.request("GET", "/pending")
    assert "access-control-allow-origin" not in hdrs
    st, _, hdrs, _ = srv.request("OPTIONS", "/ask")
    assert st != 200 and "access-control-allow-origin" not in hdrs


def test_static_page_needs_no_token_and_has_csp(live, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (static / "board.js").write_text("// js", encoding="utf-8")
    (static / "fan-font.woff2").write_bytes(b"wOF2")
    srv = live(static_dir=static)
    st, _, hdrs, raw = srv.request("GET", "/", token=None)
    assert st == 200 and raw.startswith(b"<!doctype html>")
    assert hdrs["content-type"].startswith("text/html")
    assert "default-src 'self'" in hdrs["content-security-policy"]
    st, _, hdrs, _ = srv.request("GET", "/static/board.js", token=None)
    assert st == 200 and hdrs["content-type"].startswith("text/javascript")
    st, _, hdrs, _ = srv.request("GET", "/static/fan-font.woff2", token=None)
    assert st == 200 and hdrs["content-type"] == "font/woff2"
    assert srv.request("GET", "/static/../server.py", token=None)[0] == 404
    assert srv.request("GET", "/static/missing.js", token=None)[0] == 404


def test_static_opens_only_the_files_that_were_there_at_start(live, tmp_path, monkeypatch):
    """token の要らない静的の口は、起動の時に置き場に在った file だけを開く。Windows の装置名 (CON.js・COM1.js) と
    後から置かれた名は、開きに行かずに 404 (名の形の照合は通る名でも)。"""
    static = tmp_path / "static"
    static.mkdir()
    (static / "board.js").write_text("// js", encoding="utf-8")
    srv = live(static_dir=static)
    opened = []
    real = S.Path.read_bytes

    def spy(path):
        opened.append(path.name)
        if path.stem.upper() in ("CON", "COM1", "NUL", "AUX", "PRN", "LPT1"):
            raise FileNotFoundError(path.name)        # 試験の中では装置を本当には開かない
        return real(path)

    monkeypatch.setattr(S.Path, "read_bytes", spy)
    (static / "late.js").write_text("// late", encoding="utf-8")
    assert srv.request("GET", "/static/board.js", token=None)[0] == 200
    for name in ("CON.js", "COM1.js", "nul.css", "late.js", "missing.js"):
        assert S.STATIC_NAME.match(name)
        assert srv.request("GET", f"/static/{name}", token=None)[0] == 404, name
    assert opened == ["board.js"]


def test_page_flow_answer_undo_answer_and_hook_gets_it(live):
    srv = live(replace(FAST, disconnect=5.0))             # hook の /wait なしで頁を操る = 接続の終了を待たせる
    cid = post_ask(srv)["id"]
    card = srv.wait_card()
    assert card["id"] == cid and card["state"] == "shown" and card["payload"]["head"] == "Bash"
    assert card["payload"]["blocks"][0]["text"] == "echo 日本語 && ls" and card["payload"]["text"] == "一覧を出す"
    st, body, _, _ = srv.request("POST", "/answer", {"id": cid, "seq": card["view_seq"],
                                                     "choice": {"type": "allow_once"}, "by": "dwell",
                                                     "presses": 1, "tag": "page-1:1"})
    assert st == 200 and body["undo_ms"] == 200
    snap = srv.pending()
    assert snap["card"]["state"] == "deciding" and snap["card"]["choice"] == {"type": "allow_once"}
    assert "page-1" not in json.dumps(snap["card"])        # 答えの名札は、猶予の札の写しには載せない
    assert srv.request("POST", "/undo", {"id": cid, "by": "switch", "presses": 1})[0] == 200
    card2 = srv.pending()["card"]
    assert card2["state"] == "shown" and card2["view_seq"] != card["view_seq"]
    st, body, _, _ = srv.request("POST", "/answer", {"id": cid, "seq": card["view_seq"],
                                                     "choice": {"type": "stop"}, "by": "key", "presses": 1})
    assert st == 409 and body["error"] == "stale"
    assert srv.request("POST", "/answer", {"id": cid, "seq": card2["view_seq"], "choice": {"type": "stop"},
                                           "by": "key", "presses": 1, "tag": "page-2:1"})[0] == 200
    t0 = time.monotonic()
    while True:
        st, body, _, _ = srv.request("GET", f"/wait?id={cid}")
        if body["state"] != "waiting":
            break
        assert time.monotonic() - t0 < 3
    assert body == {"state": "answered", "answer": {"type": "stop"}}   # hook への返りに、頁の名札は載らない
    time.sleep(0.05)
    snap = srv.pending()
    assert snap["card"] is None and snap["last"]["end"] == "answered"
    assert snap["last"]["answered_by"] == "page-2:1"   # 渡ったのは、答え直した答え (HTTP の口から名札が届く)
    assert snap["stats"]["presses"] == {"dwell": 1, "key": 1, "switch": 1, "touch": 0, "click": 0}
    assert snap["stats"]["answers"] == 1


def test_wait_unknown_id_is_404(live):
    srv = live()
    assert srv.request("GET", "/wait?id=nope")[0] == 404


def test_unread_answer_reply_retries_press_batches_only_once(live):
    """実 HTTP: 答えの応答を読まずに接続を捨て、取り消しに同じ束と新しい押しを乗せる。"""
    srv = live(replace(FAST, disconnect=10.0, undo_ms=3000, undo_max_ms=3000))
    cid = post_ask(srv)["id"]
    card = srv.wait_card()
    first = {"id": "page:1", "presses": {"dwell": 1}}
    second = {"id": "page:2", "presses": {"switch": 1}}
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=2.0)
    try:
        conn.request("POST", "/answer", body=json.dumps({
            "id": cid, "seq": card["view_seq"], "choice": {"type": "allow_once"}, "by": "dwell",
            "presses": {"dwell": 1}, "press_batches": [first],
        }), headers={"X-Blemma-Token": srv.token, "Content-Type": "application/json"})
        until = time.monotonic() + 2.0
        while True:
            snap = srv.pending()
            if snap["card"]["state"] == "deciding":
                break
            assert time.monotonic() < until
            time.sleep(0.01)
        assert snap["stats"]["total"] == 1
    finally:
        conn.close()  # getresponse/read は呼ばない。server の受理だけを /pending で確かめた。
    assert srv.request("POST", "/undo", {
        "id": cid, "by": "switch", "presses": {"dwell": 1, "switch": 1},
        "press_batches": [first, second, first],  # 同じ要求内の重複も二度数えない。
    })[0] == 200
    snap = srv.pending()
    assert snap["stats"]["total"] == 2
    assert snap["stats"]["presses"] == {"dwell": 1, "switch": 1, "key": 0, "touch": 0, "click": 0}


def test_pending_long_poll_returns_when_seq_changes(live):
    srv = live(replace(FAST, pending_hold=5.0))
    seq = srv.pending()["seq"]
    out = {}

    def poll():
        t = time.monotonic()
        out["snap"] = srv.pending(seq)
        out["sec"] = time.monotonic() - t

    th = threading.Thread(target=poll)
    th.start()
    time.sleep(0.3)
    srv.request("POST", "/notify", {"type": "idle_prompt", "message": "waiting"})
    th.join(5)
    assert out["snap"]["seq"] > seq and out["snap"]["light"]["type"] == "idle_prompt"
    assert out["sec"] < 2.0


def test_notify_is_204(live):
    srv = live()
    st, _, _, raw = srv.request("POST", "/notify", {"type": "permission_prompt", "message": "m"})
    assert st == 204 and raw == b""


def test_window_answers_and_needs_token(live):
    srv = live()
    reply = srv.request("POST", "/window", {})
    assert reply[0] == 200 and "found" in reply[1]
    assert srv.request("POST", "/window", {}, token=None)[0] == 401


def test_window_call_names_this_boards_own_port(live, monkeypatch):
    """窓の操作は、この板の port の窓だけに向ける (別の port で動いている板の窓を取り違えない)。"""
    seen = []

    def fake(data, port=None):
        seen.append((data, port))
        return {"found": False}

    monkeypatch.setattr(S.window_win, "apply", fake)
    srv = live()
    reply = srv.request("POST", "/window", {"pin": True})
    assert reply[:2] == (200, {"found": False})
    assert seen == [({"pin": True}, srv.port)]


def test_stats_reset_needs_token(live):
    srv = live()
    assert srv.request("POST", "/stats/reset", {}, token=None)[0] == 401
    assert srv.request("POST", "/stats/reset", {})[0] == 204


def test_resolve_is_not_built(live):
    srv = live()
    assert srv.request("POST", "/resolve", {"session": "s", "event": "post_tool_use", "key": "k"})[0] == 404


def test_bad_bodies(live):
    srv = live()
    assert srv.request("POST", "/ask", ["list"])[0] == 400
    assert srv.request("POST", "/ask", {"kind": "nope", "payload": {}})[0] == 400


@pytest.mark.parametrize("token", [None, "right"])
def test_a_deeply_nested_body_is_refused_without_breaking_the_handler(live, capsys, token):
    """本文は鍵の確かめの後に解く = 鍵の無い相手の深い入れ子 (や Python 3.10.6 までの巨大な数) で、handler の thread を
    落とさず (返りの無いまま閉じない)、板を止めない。鍵のある相手の深い入れ子も、壊れた本文として 400 で断る
    (Python の点検 BL-PY-03 の再現 = 鍵なしの深さ 20 万の [ で RecursionError が捕まらず、応答なしで閉じた)。"""
    srv = live()
    body = b"[" * 200000
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    if token:
        headers["X-Blemma-Token"] = srv.token
    conn.request("POST", "/ask", body=body, headers=headers)
    resp = conn.getresponse()
    got = (resp.status, json.loads(resp.read()))
    conn.close()
    time.sleep(0.1)
    assert got == ((400, {"error": "bad_body"}) if token else (401, {"error": "token"}))
    err = capsys.readouterr().err
    assert "RecursionError" not in err and "Traceback" not in err
    assert srv.request("GET", "/pending")[0] == 200          # 板はそのまま答える


def test_the_body_is_parsed_only_after_the_token_passes(live, monkeypatch):
    """本文の JSON を解くのは、鍵が通った後だけ = 鍵の無い要求では 1 度も解かない (外の目の 6 巡目 = 返りの形だけを見る
    試験では、解く順を鍵の前へ戻す後戻りを見張れなかった)。"""
    calls = []
    real = S.Handler._parse_json
    monkeypatch.setattr(S.Handler, "_parse_json", staticmethod(lambda raw: calls.append(raw) or real(raw)))
    srv = live()
    body = {"kind": "permission", "from": {"cwd": "repo"}, "payload": dict(PERM)}
    assert srv.request("POST", "/ask", body, token=None)[0] == 401
    assert srv.request("POST", "/ask", body, token="wrong")[0] == 401
    assert calls == []
    assert srv.request("POST", "/ask", body)[0] == 200
    assert len(calls) == 1


def test_hook_that_dies_is_disconnected_quickly(live):
    """/wait を抱えている間に hook が死んでも、抱える秒を待たずに接続の終了へ (§3.7 (a))。"""
    srv = live(replace(FAST, wait_hold=10.0, disconnect=0.3))
    cid = post_ask(srv)["id"]
    s = socket.create_connection(("127.0.0.1", srv.port))
    req = (f"GET /wait?id={cid} HTTP/1.0\r\nHost: 127.0.0.1:{srv.port}\r\n"
           f"X-Blemma-Token: {srv.token}\r\n\r\n").encode("ascii")
    s.sendall(req)
    time.sleep(0.2)
    s.close()                                         # hook の process が殺された
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3:
        last = srv.pending()["last"]
        if last and last["id"] == cid:
            break
        time.sleep(0.05)
    assert last and last["end"] == "disconnected"
    assert time.monotonic() - t0 < 2.0


def test_answer_is_not_handed_to_a_hook_that_already_closed(clock):
    """渡す直前に hook が閉じていたら、答えを渡さず切断で閉じる (頁に「渡しました」と出さない)・次の札をすぐ出す。"""
    b = S.Board(replace(FAST, undo_ms=0, wait_hold=0.0, pending_hold=0.0, disconnect=60.0), clock=clock)
    first = b.ask("permission", {"cwd": "repo"}, dict(PERM))[1]["id"]
    second = b.ask("permission", {"cwd": "repo"}, {"head": "next"})[1]["id"]
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(first, seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    assert b.wait(first, alive=lambda: False) == (0, {}, None)
    snap = b.pending(-1)
    assert (snap["last"]["id"], snap["last"]["end"], snap["last"]["from_deciding"]) == (first, "disconnected", True)
    assert snap["card"]["id"] == second and snap["card"]["state"] == "shown"
    assert b.wait(first) == (200, {"state": "closed"}, None)        # 後から来た /wait にも答えは渡らない


def test_a_reply_that_cannot_be_written_still_closes_the_card(live, monkeypatch):
    """/wait の返りを書く所が OSError の外の例外で落ちても、渡しの途中の札は切断で閉じ、次の札が出る
    (前は delivering のまま先頭に残り、以後の札が表示されなかった)。"""
    srv = live(replace(FAST, disconnect=10.0))
    real = S.Handler._json

    def broken(self, code, obj):
        if isinstance(obj, dict) and obj.get("state") == "answered":
            raise RuntimeError("書けない (試験)")
        return real(self, code, obj)

    monkeypatch.setattr(S.Handler, "_json", broken)
    first = post_ask(srv)["id"]
    second = post_ask(srv, payload={"head": "next"})["id"]
    card = srv.wait_card()
    assert srv.request("POST", "/answer", {"id": first, "seq": card["view_seq"], "choice": {"type": "allow_once"},
                                           "by": "dwell", "presses": 1})[0] == 200
    for _ in range(30):
        try:
            st, body, _, _ = srv.request("GET", f"/wait?id={first}")
        except (http.client.HTTPException, OSError):
            break                                     # 返りを書く所で落ちた = 返りなしで接続が切れる
        assert body["state"] == "waiting", body
    else:
        raise AssertionError("答えを渡しに来ない")
    end = time.monotonic() + 3
    while True:
        snap = srv.pending()
        if snap["card"] and snap["card"]["id"] == second:
            break
        assert time.monotonic() < end, "渡せなかった札が先頭を塞いでいる"
        time.sleep(0.05)
    assert (snap["last"]["id"], snap["last"]["end"]) == (first, "disconnected")


def test_page_probe_needs_the_token_and_tells_an_open_page(live):
    """起こし方の照会 GET /page: token が要る・札を作らない・頁の見張りが来るまでは open にならない
    (見る人の判定と違い、起動の猶予は数えない)。"""
    srv = live()
    assert srv.request("GET", "/page", token=None)[0] == 401
    assert srv.request("GET", "/page")[:2] == (200, {"open": False})      # 起きたばかりの板
    srv.pending()                                                          # 頁の見張りが 1 回
    assert srv.request("GET", "/page")[:2] == (200, {"open": True})
    assert srv.pending()["card"] is None                                   # 照会は札を作らない


def test_port_in_use_is_refused(live):
    srv = live()
    app = S.App(FAST, "t")
    with pytest.raises(OSError):
        S.make_server(app, srv.port)


def test_run_file_write_and_remove_only_own(tmp_path):
    p = tmp_path / "state" / "run.json"
    S.write_run_file(p, {"port": 1, "token": "mine", "pid": 1, "started": "x"})
    assert json.loads(p.read_text(encoding="utf-8"))["token"] == "mine"
    S.remove_run_file(p, "other")
    assert p.exists()
    S.remove_run_file(p, "mine")
    assert not p.exists()


@pytest.mark.parametrize("argv", [["--undo-ms", "5001"], ["--wait", "541"], ["--port", "0"]])
def test_main_refuses_bad_numbers(argv):
    assert S.main(argv + ["--no-browser", "--no-log"]) == 2


def test_notify_text_and_session_are_not_kept(live, monkeypatch, capsys):
    """待ちの合図の文は記録にも server の debug の行にも出ない・session は 6 字に切る (§3.3・§3.8)。"""
    monkeypatch.setattr(S, "DEBUG", True)
    srv = live(replace(FAST, disconnect=1.0))
    secret = "SECRET-NOTIFY-TEXT"
    assert srv.request("POST", "/notify", {"type": "idle_prompt", "title": secret, "message": secret + "-m"})[0] == 204
    st, _, _, _ = srv.request("POST", "/ask", {"kind": "permission", "from": {"cwd": "repo", "session": "abcdefghij"},
                                               "payload": {"head": "x"}})
    assert st == 200
    assert srv.wait_card()["from"]["session"] == "abcdef"
    t0 = time.monotonic()
    logs = []
    while time.monotonic() - t0 < 4 and not logs:   # hook が居ない = 接続の終了で 1 行書かれる
        logs = list(srv.state.glob("log-*.jsonl"))
        time.sleep(0.05)
    assert logs, "記録が書かれない"
    text = logs[0].read_text(encoding="utf-8")
    assert '"end": "disconnected"' in text and secret not in text
    err = capsys.readouterr().err
    assert "POST /notify 204" in err and secret not in err


def test_open_long_poll_counts_as_a_viewer(live):
    """開いている GET /pending が在る間は札を受け、閉じて秒を過ぎたら 503 (no_viewer)。"""
    srv = live(replace(FAST, viewer=0.5, pending_hold=2.0))
    seq = srv.pending()["seq"]
    th = threading.Thread(target=lambda: srv.pending(seq))     # 変化が無ければ 2 秒抱える
    th.start()
    time.sleep(1.0)                                   # 最後の返りから 0.5 秒を過ぎた・long-poll は開いている
    st, body, _, _ = srv.request("POST", "/ask", {"kind": "permission", "payload": {"head": "x"}})
    assert st == 200, body
    th.join(5)                                        # 札が出て long-poll が返った = 見る人が閉じた
    time.sleep(0.8)
    st, body, _, _ = srv.request("POST", "/ask", {"kind": "permission", "payload": {"head": "y"}})
    assert (st, body) == (503, {"error": "no_viewer"})


@pytest.mark.parametrize("debug", [False, True])
def test_malformed_request_line_gets_400_without_crash(live, monkeypatch, capsys, debug):
    """壊れた要求の行 (TLS の hello に似た物・port の走査) でも handler が落ちずに 400 を返す。"""
    monkeypatch.setattr(S, "DEBUG", debug)
    srv = live()
    s = socket.create_connection(("127.0.0.1", srv.port))
    s.sendall(b"\x16\x03\x01\x02\x00 junk HTTP/9\r\n\r\n")
    data = s.recv(4096)
    s.close()
    time.sleep(0.1)
    assert data.startswith(b"HTTP/1.0 400")
    assert "Traceback" not in capsys.readouterr().err


def test_card_text_that_is_not_valid_unicode_does_not_break_the_board(live):
    """札の文に対のないサロゲートが混じっても、板の取得は落ちない (前は、その札が出ている間じゅう取得が切られ続けた)。"""
    srv = live()
    post_ask(srv, payload={"head": "Bash", "text": "壊れた字 \ud800 を含む", "blocks": []})
    card = srv.pending()["card"]
    assert card["payload"]["text"] == "壊れた字 \ud800 を含む"


def test_elicitation_card_carries_the_omitted_field_titles_to_the_page(live):
    """MCP の問いの札の omitted (板で描けない任意の欄の題) は、server が削らず足さず、そのまま頁へ届く。"""
    srv = live(replace(FAST, disconnect=5.0))
    payload = {"head": "demo-server", "text": "選んでください", "omitted": ["題", "reviewers"],
               "fields": [{"name": "ok", "title": "続けますか?", "multi": False, "required": True,
                           "options": [{"label": "はい", "value": True}, {"label": "いいえ", "value": False}]}]}
    post_ask(srv, kind="elicitation", payload=payload)
    assert srv.wait_card()["payload"] == payload


def test_slow_sender_is_dropped_before_the_token_check(live, monkeypatch):
    """本文を送り切らない相手を、時間の限りなく待たない (鍵を確かめる前の読み取り)。板はその後も答える。"""
    assert S.Handler.timeout == S.READ_TIMEOUT and 0 < S.READ_TIMEOUT <= 30      # 出荷の値に待ちの上限がある
    monkeypatch.setattr(S.Handler, "timeout", 0.3)                              # 試験では短くして確かめる
    srv = live()
    sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
    try:
        sock.sendall(b"POST /ask HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                     b"Content-Length: 10\r\n\r\n{")
        started = time.monotonic()
        reply = sock.recv(4096)
        assert time.monotonic() - started < 3, "読み取りの待ちに上限が無い"
        assert reply.startswith(b"HTTP/1.0 401")          # 本文は読み切れず、鍵も無い = 断る
    finally:
        sock.close()
    assert srv.pending()["card"] is None


def test_too_many_connections_are_closed_instead_of_piling_up(live, monkeypatch):
    """同時の接続が上限を超えたら、受けずに閉じる (thread を増やし続けない)。空けば元どおり受ける。"""
    monkeypatch.setattr(S.BoardHTTPServer, "max_connections", 2)
    monkeypatch.setattr(S.Handler, "timeout", 5.0)
    srv = live()
    held = [socket.create_connection(("127.0.0.1", srv.port), timeout=5) for _ in range(2)]   # 何も送らない 2 本
    extra = None
    try:
        time.sleep(0.3)
        extra = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        try:
            extra.sendall(b"GET /pending?seq=-1 HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            closed = extra.recv(100) == b""
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            closed = True
        assert closed, "上限を超えた接続に答えている"
    finally:
        for sock in held + ([extra] if extra else []):
            sock.close()
    time.sleep(0.4)
    assert srv.pending()["card"] is None


class _Done:
    def __init__(self, code=0, out=b""):
        self.returncode, self.stdout = code, out


def _fake_runner(calls, whoami=0, grant=0, cut=0, sid=b'"pc\\user","S-1-5-21-1-2-3-1001"\r\n'):
    def run(cmd, **_):
        name = cmd[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        calls.append([name] + list(cmd[1:]))
        if name == "whoami.exe":
            return _Done(whoami, sid)
        return _Done(grant if "/grant:r" in cmd else cut)
    return run


def test_state_folder_is_granted_to_the_user_before_inheritance_is_cut(tmp_path):
    """Windows: 先に自分の許可を足し、通った時だけ親からの継ぎを外す (逆の順で失敗すると、自分も読めない folder が残る)。"""
    calls = []
    assert S._restrict_windows(tmp_path, _fake_runner(calls)) is True
    assert [c[0] for c in calls] == ["whoami.exe", "icacls.exe", "icacls.exe"]
    assert calls[1][1:] == [str(tmp_path), "/grant:r", "*S-1-5-21-1-2-3-1001:(OI)(CI)F"]
    assert calls[2][1:] == [str(tmp_path), "/inheritance:r"]


def test_state_folder_keeps_its_permissions_when_the_grant_fails(tmp_path):
    calls = []
    assert S._restrict_windows(tmp_path, _fake_runner(calls, grant=5)) is False
    assert [c[0] for c in calls] == ["whoami.exe", "icacls.exe"]          # 継ぎは外していない
    calls = []
    assert S._restrict_windows(tmp_path, _fake_runner(calls, whoami=1)) is False
    assert [c[0] for c in calls] == ["whoami.exe"]
    calls = []
    assert S._restrict_windows(tmp_path, _fake_runner(calls, sid=b"no sid here")) is False
    assert [c[0] for c in calls] == ["whoami.exe"]


def _entries(folder) -> list:
    """Windows の folder に付いている許可の行 (icacls の出力のうち、許可を表す行)。"""
    listing = subprocess.run([os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "System32", "icacls.exe"), str(folder)],
                             capture_output=True, timeout=20).stdout.decode("mbcs", errors="replace")
    return [line for line in listing.splitlines() if ":(" in line]


def test_a_started_board_restricts_its_state_folder_before_writing_the_token(tmp_path):
    """板を実際に起こすと、鍵 (run.json) を書く置き場は、今のユーザーだけの物になっている。"""
    root = tmp_path / "repo"
    (root / "board").mkdir(parents=True)
    shutil.copy2(S.__file__, root / "board" / "server.py")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    board = subprocess.Popen([sys.executable, str(root / "board" / "server.py"), "--no-browser", "--no-log", "--port", str(port)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        run = root / "board" / "state" / "run.json"
        end = time.monotonic() + 10
        while not run.exists() and time.monotonic() < end:
            time.sleep(0.05)
        assert run.exists(), "板が起きない"
        if os.name == "nt":
            assert len(_entries(run.parent)) == 1
        else:
            assert stat.S_IMODE(os.stat(run.parent).st_mode) == 0o700
    finally:
        board.terminate()
        board.wait(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="Windows の許可 (ACL) の実物の確かめ")
def test_state_folder_is_readable_only_by_the_current_user_on_windows(tmp_path):
    """実の icacls で確かめる: 絞った後の folder に残る許可は、今のユーザーの 1 行だけ。"""
    folder = tmp_path / "state"
    folder.mkdir()
    assert len(_entries(folder)) > 1                                    # 絞る前は、親から継いだ許可が並ぶ
    assert S.restrict_to_user(folder) is True
    assert len(_entries(folder)) == 1
    (folder / "run.json").write_text("{}", encoding="utf-8")              # 絞った後も、自分は書ける・読める
    assert (folder / "run.json").read_text(encoding="utf-8") == "{}"
