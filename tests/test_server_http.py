# -*- coding: utf-8 -*-
"""HTTP の口 (§3.3) = token・Host・CORS なし・静的の頁・long-poll・run.json・port の使用中。"""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import replace

import pytest

import server as S
from conftest import FAST

PERM = {"head": "Bash", "text": "list", "blocks": [{"label": "command", "text": "ls", "mono": True}]}


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
    srv = live()
    cid = post_ask(srv)["id"]
    card = srv.wait_card()
    assert card["id"] == cid and card["state"] == "shown" and card["payload"]["head"] == "Bash"
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
