"""Status uses real HTTP and subprocesses; only long elapsed time uses a clock."""
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
import server as S
from conftest import FAST
from test_notify import fake_server  # Reuse its real HTTP recorder, not a mocked client.

SCRIPT = Path(__file__).resolve().parents[1] / "hooks" / "state.py"


def run_state(path, event="UserPromptSubmit", raw=None):
    env = {**os.environ, "BLEMMA_RUN_FILE": str(path), "BLEMMA_DEBUG": "0", "PYTHONIOENCODING": "cp932"}
    data = {"hook_event_name": event, "session_id": "abcdef123456", "prompt": "do not transmit",
            "tool_input": {"secret": "do not transmit"}, "cwd": "do not transmit"}
    started = time.monotonic()
    p = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT)],
                       input=json.dumps(data).encode() if raw is None else raw,
                       capture_output=True, env=env, timeout=3)
    assert p.returncode == 0 and p.stdout == p.stderr == b""
    return time.monotonic() - started


@pytest.mark.parametrize("event,expected", [("UserPromptSubmit", "working"), ("Stop", "done")])
def test_state_script_real_board_isolated_and_silent(live, event, expected):
    srv = live()
    run_state(srv.run_file, event)
    snap = srv.pending()
    assert snap["card"] is None
    # ago は 0.1 秒の丸め = 負荷で hook の POST から読むまでに 50 ms を超えると 0.1 になる (11/8 の 3.10 の全体回帰で 1 回) = 幅で見る
    ago = snap["states"][0].pop("ago")
    assert 0 <= ago < 1
    assert snap["states"] == [{"session": "abcdef", "state": expected, "stale": False, "reason": ""}]


@pytest.mark.parametrize("raw", [b"{}", b"{bad", b"null", b"\xff"])
def test_state_bad_input_is_silent(live, raw):
    srv = live()
    run_state(srv.run_file, raw=raw)
    assert srv.pending()["states"] == []


def test_state_missing_board_returns_quickly(tmp_path):
    assert run_state(tmp_path / "absent.json") < 1.5


def test_state_posts_only_session_and_status_once(fake_server):
    path, requests = fake_server()
    run_state(path)
    assert len(requests) == 1
    method, route, body, _ = requests[0]
    assert (method, route, body) == ("POST", "/state", {"session": "abcdef", "state": "working"})


@pytest.mark.parametrize("status", [302, 401, 500])
def test_state_never_retries_or_redirects(fake_server, status):
    path, requests = fake_server(status=status)
    run_state(path)
    assert len(requests) == 1


def test_state_total_deadline_is_short(fake_server):
    path, requests = fake_server(block=True)
    assert run_state(path) < 1.5
    assert len(requests) == 1


def test_state_auth_host_and_validation(live):
    srv = live()
    body = {"session": "abcdef", "state": "working"}
    assert srv.request("POST", "/state", body, token=None)[0] == 401
    assert srv.request("POST", "/state", body, token="wrong")[0] == 401
    assert srv.request("POST", "/state", body, host="evil.example")[0] == 403
    for bad in ({**body, "state": "allow"}, {**body, "session": "too-long"},
                {**body, "prompt": "not allowed"}, {"state": "done"}):
        assert srv.request("POST", "/state", bad)[0] == 400
    assert srv.pending()["states"] == []
    assert srv.request("POST", "/state", body)[0] == 204
    assert srv.pending()["states"][0]["state"] == "working"


def test_status_card_answer_disconnect_and_age(clock):
    board = S.Board(replace(FAST, wait_hold=0, pending_hold=0, disconnect=1000), clock=clock)
    board.set_state({"session": "abcdef", "state": "done"})
    board.ask("permission", {"session": "abcdef"}, {})
    c = board.pending(-1)["card"]
    assert board.pending(-1)["states"][0]["state"] == "waiting on you"
    board.set_state({"session": "abcdef", "state": "done"})
    assert board.pending(-1)["states"][0]["reason"] == "card"
    board.answer(c["id"], c["view_seq"], {"type": "allow_once"}, "key", {})
    clock.advance(.3)
    _, _, delivered = board.wait(c["id"])
    board.delivered(delivered, True)
    assert board.pending(-1)["states"][0]["state"] == "working"
    clock.advance(599)
    assert not board.pending(-1)["states"][0]["stale"]
    clock.advance(1)
    assert board.pending(-1)["states"][0]["stale"]
    board.ask("permission", {"session": "abcdef"}, {})
    board.lim = replace(board.lim, disconnect=.4)
    clock.advance(.5)
    state = board.pending(-1)["states"][0]
    assert state["state"] == "waiting on you" and state["reason"] == "disconnected"


def test_notification_and_session_status_stay_separate(live):
    srv = live()
    srv.request("POST", "/state", {"session": "first", "state": "working"})
    srv.request("POST", "/notify", {"type": "idle_prompt", "from": {"session": "second"}})
    states = {s["session"]: s["state"] for s in srv.pending()["states"]}
    assert states == {"first": "working", "second": "waiting on you"}
