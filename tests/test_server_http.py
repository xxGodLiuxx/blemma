# -*- coding: utf-8 -*-
"""HTTP の口 (§3.3) = token・Host・CORS なし・静的の頁・long-poll・run.json・port の使用中。"""

from __future__ import annotations

import http.client
import json
import socket
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
    srv = live(static_dir=static)
    st, _, hdrs, raw = srv.request("GET", "/", token=None)
    assert st == 200 and raw.startswith(b"<!doctype html>")
    assert hdrs["content-type"].startswith("text/html")
    assert "default-src 'self'" in hdrs["content-security-policy"]
    st, _, hdrs, _ = srv.request("GET", "/static/board.js", token=None)
    assert st == 200 and hdrs["content-type"].startswith("text/javascript")
    assert srv.request("GET", "/static/../server.py", token=None)[0] == 404
    assert srv.request("GET", "/static/missing.js", token=None)[0] == 404


def test_page_flow_answer_undo_answer_and_hook_gets_it(live):
    srv = live(replace(FAST, disconnect=5.0))             # hook の /wait なしで頁を操る = 接続の終了を待たせる
    cid = post_ask(srv)["id"]
    card = srv.wait_card()
    assert card["id"] == cid and card["state"] == "shown" and card["payload"]["head"] == "Bash"
    assert card["payload"]["blocks"][0]["text"] == "echo 日本語 && ls" and card["payload"]["text"] == "一覧を出す"
    st, body, _, _ = srv.request("POST", "/answer", {"id": cid, "seq": card["view_seq"],
                                                     "choice": {"type": "allow_once"}, "by": "dwell",
                                                     "presses": 1})
    assert st == 200 and body["undo_ms"] == 200
    snap = srv.pending()
    assert snap["card"]["state"] == "deciding" and snap["card"]["choice"] == {"type": "allow_once"}
    assert srv.request("POST", "/undo", {"id": cid, "by": "switch", "presses": 1})[0] == 200
    card2 = srv.pending()["card"]
    assert card2["state"] == "shown" and card2["view_seq"] != card["view_seq"]
    st, body, _, _ = srv.request("POST", "/answer", {"id": cid, "seq": card["view_seq"],
                                                     "choice": {"type": "stop"}, "by": "key", "presses": 1})
    assert st == 409 and body["error"] == "stale"
    assert srv.request("POST", "/answer", {"id": cid, "seq": card2["view_seq"], "choice": {"type": "stop"},
                                           "by": "key", "presses": 1})[0] == 200
    t0 = time.monotonic()
    while True:
        st, body, _, _ = srv.request("GET", f"/wait?id={cid}")
        if body["state"] != "waiting":
            break
        assert time.monotonic() - t0 < 3
    assert body == {"state": "answered", "answer": {"type": "stop"}}
    time.sleep(0.05)
    snap = srv.pending()
    assert snap["card"] is None and snap["last"]["end"] == "answered"
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

