# -*- coding: utf-8 -*-
"""試験の共通。board/ と hooks/ を import の路に足し、速い数の板を立てる道具を置く。"""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for sub in ("board", "hooks"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import server as board_server  # noqa: E402


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# 試験の数 = 設計の数を縮めた物 (形は同じ)
FAST = board_server.Limits(
    wait=2.0, perm_wait=2.0, create_cap=4.0, min_show=0.5, undo_ms=200, undo_max_ms=500,
    hard_margin=1.0, ask_giveup=2.0, wait_giveup=2.0, wait_hold=0.3, pending_hold=0.5,
    disconnect=0.4, queue_max=20, light=0.5, tick=0.02,
    viewer=None,                       # 見る人の判定は専用の試験だけで使う
)


class Live:
    """port 0 で立てた本物の板 (HTTP)。"""

    def __init__(self, tmp: Path, limits: board_server.Limits, allow_hosts=None, static_dir=None):
        self.token = "test-token-" + "x" * 20
        self.state = tmp / "state"
        self.app = board_server.App(limits, self.token, allow_hosts=allow_hosts,
                                    log_dir=self.state, static_dir=static_dir)
        self.httpd = board_server.make_server(self.app, 0)
        self.port = self.httpd.server_address[1]
        self.run_file = self.state / "run.json"
        board_server.write_run_file(self.run_file, {"port": self.port, "token": self.token,
                                                    "pid": 0, "started": "test"})
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                                       daemon=True)
        self.thread.start()
        board_server.start_ticker(self.app.board)

    def request(self, method: str, path: str, body=None, token: "str | None" = "default",
                host: "str | None" = None, timeout: float = 5.0):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = {}
        if token == "default":
            token = self.token
        if token is not None:
            headers["X-Blemma-Token"] = token
        if host is not None:
            headers["Host"] = host
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        parsed = None
        if raw and hdrs.get("content-type", "").startswith("application/json"):
            parsed = json.loads(raw.decode("utf-8"))
        return resp.status, parsed, hdrs, raw

    def pending(self, seq: int = -1):
        st, body, _, _ = self.request("GET", f"/pending?seq={seq}")
        assert st == 200
        return body

    def wait_card(self, timeout: float = 3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            snap = self.pending()
            if snap["card"] is not None:
                return snap["card"]
            time.sleep(0.02)
        raise AssertionError("札が出ない")

    def close(self) -> None:
        self.app.board.close()
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def live(tmp_path):
    made = []

    def make(limits=FAST, **kw):
        s = Live(tmp_path / f"s{len(made)}", limits, **kw)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


@pytest.fixture
def clock():
    return FakeClock()
