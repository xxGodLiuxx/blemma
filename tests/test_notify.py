# -*- coding: utf-8 -*-
"""notify.py と共通 client を別プロセスで動かし、実際の HTTP で検証する。"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "notify.py"
TYPES = ("permission_prompt", "idle_prompt", "elicitation_dialog",
         "elicitation_url_dialog", "agent_needs_input")
INPUT = {"hook_event_name": "Notification", "notification_type": "agent_needs_input",
         "title": "確認", "message": "次の指示を待っています 🧭",
         "cwd": "/example/project", "session_id": "abcdef123456", "agent_type": "worker"}


def run_hook(run_file, data=INPUT, *, raw=None, extra_env=None):
    env = os.environ.copy()
    env.update(BLEMMA_RUN_FILE=str(run_file), BLEMMA_DEBUG="0",
               PYTHONIOENCODING="cp932", PYTHONDONTWRITEBYTECODE="1")
    if extra_env:
        env.update(extra_env)
    result = subprocess.run([sys.executable, str(SCRIPT)],
                            input=raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=ROOT, env=env, timeout=5)
    assert result.returncode == 0
    assert result.stdout == b"" and result.stderr == b""


def write_run(path, port):
    path.write_text(json.dumps({"port": port, "token": "test-only-token"}), encoding="utf-8")
    return path


@pytest.fixture
def fake_server(tmp_path):
    running = []

    def make(*, status=204, block=False):
        requests = []
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                size = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(size).decode("utf-8"))
                requests.append(("POST", self.path, body, dict(self.headers)))
                if block:
                    release.wait(4)
                self.send_response(status)
                if 300 <= status < 400:
                    # 同じ板の別口へも転送しない = 1 回だけの通信。
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirected")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                requests.append(("GET", self.path, None, dict(self.headers)))
                self.send_response(204)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        running.append((server, thread, release))
        run_file = write_run(tmp_path / f"run-{len(running)}.json", server.server_port)
        return run_file, requests

    yield make
    for server, thread, release in running:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("notification_type", TYPES)
def test_sends_one_notification_and_prints_nothing(fake_server, notification_type):
    run_file, requests = fake_server()
    run_hook(run_file, {**INPUT, "notification_type": notification_type})
    assert len(requests) == 1
    method, path, body, headers = requests[0]
    assert (method, path) == ("POST", "/notify")
    assert body == {"type": notification_type, "title": INPUT["title"], "message": INPUT["message"],
                    "from": {"cwd": "project", "session": "abcdef", "agent": "worker"}}
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Blemma-Token"] == "test-only-token"


def test_real_board_receives_light_without_creating_card(live):
    server = live()
    run_hook(server.run_file)
    snapshot = server.pending()
    assert snapshot["card"] is None and snapshot["queue"] == 0
    assert snapshot["light"]["type"] == INPUT["notification_type"]
    assert snapshot["light"]["message"] == INPUT["message"]


def test_absent_server_exits_zero_without_output(tmp_path):
    # port を予約したまま listen しない。他の処理による port の再利用を避ける。
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        run_file = write_run(tmp_path / "run.json", sock.getsockname()[1])
        run_hook(run_file)


def test_missing_run_file_exits_zero_without_output(tmp_path):
    run_hook(tmp_path / "missing.json")


@pytest.mark.parametrize("raw", [b"{broken", b"\xff", b"", b"[]", b"null"])
def test_invalid_stdin_does_not_contact_server(fake_server, raw):
    run_file, requests = fake_server()
    run_hook(run_file, raw=raw)
    assert requests == []


@pytest.mark.parametrize("data", [
    {}, {**INPUT, "hook_event_name": "PreToolUse"},
    {**INPUT, "notification_type": "unknown"}, {**INPUT, "notification_type": []},
])
def test_unrelated_inputs_are_ignored(fake_server, data):
    run_file, requests = fake_server()
    run_hook(run_file, data)
    assert requests == []


@pytest.mark.parametrize("raw", ["{broken", "[]", '{"port": true, "token": "test"}',
                                 '{"port": 0, "token": "test"}'])
def test_invalid_run_file_is_silent(tmp_path, raw):
    path = tmp_path / "run.json"
    path.write_text(raw, encoding="utf-8")
    run_hook(path)


@pytest.mark.parametrize("status", [302, 307, 401, 500])
def test_failed_requests_are_not_retried_or_redirected(fake_server, status):
    run_file, requests = fake_server(status=status)
    run_hook(run_file)
    assert len(requests) == 1 and requests[0][1] == "/notify"


def test_slow_server_times_out_after_two_seconds(fake_server):
    run_file, requests = fake_server(block=True)
    start = time.monotonic()
    run_hook(run_file)
    elapsed = time.monotonic() - start
    assert 1.8 <= elapsed < 3.5
    assert len(requests) == 1


def test_proxy_environment_does_not_change_loopback_destination(fake_server):
    run_file, requests = fake_server()
    # 到達しない代理口を指定しても、実際の板へ直接 1 回だけ届く。
    run_hook(run_file, extra_env={"HTTP_PROXY": "http://127.0.0.1:1",
                                  "http_proxy": "http://127.0.0.1:1",
                                  "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""})
    assert len(requests) == 1
