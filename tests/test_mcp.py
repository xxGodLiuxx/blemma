# -*- coding: utf-8 -*-
"""実際の MCP 処理を別プロセスの UTF-8 の入出力で検証する。"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import server as board_server


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "mcp" / "blemma_mcp.py"
STOP = "ここで止める"
ARGS = {"title": "次の一手を選んでください 🧭", "choices": ["案を見る", "試験を回す"]}
DECLINED = "人はどれも選びませんでした。別の案を出すか、文で訊いてください。"
CANCELLED = "人はこの問い合わせを閉じました。作業を止めて次の指示を待ってください。"


class Client:
    def __init__(self, *, wait_timeout=None, debug=False):
        env = os.environ.copy()
        env.update(PYTHONIOENCODING="cp932", PYTHONDONTWRITEBYTECODE="1",
                   BLEMMA_DEBUG="1" if debug else "0")
        if wait_timeout is None:
            command = [sys.executable, str(SCRIPT)]
        else:
            # 待つ秒だけ縮める。Server・Event・JSON-RPC・入出力は本物を通す。
            command = [sys.executable, "-c",
                       "import runpy, sys; m = runpy.run_path(sys.argv[1]); "
                       "m['Server'](wait_timeout=float(sys.argv[2])).run()",
                       str(SCRIPT), str(wait_timeout)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env, cwd=ROOT)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.reader.start()
        self.next_id = 1
        self.debug = debug
        self.closed = False
        self.stderr = b""

    def _read_lines(self):
        for raw in self.process.stdout:
            self.lines.put(raw)
        self.lines.put(None)

    def send(self, message):
        self.raw((json.dumps(message, ensure_ascii=False) + "\r\n").encode("utf-8"))

    def raw(self, data):
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def receive(self):
        raw = self.lines.get(timeout=5)
        assert raw is not None, "MCP closed stdout before replying"
        assert raw.endswith(b"\n") and b"\r" not in raw
        msg = json.loads(raw.decode("utf-8"))
        assert isinstance(msg, dict) and msg["jsonrpc"] == "2.0"
        return msg

    def request(self, method, params):
        rid = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return rid

    def initialize(self, capabilities=None):
        if capabilities is None:
            capabilities = {"elicitation": {"form": {}, "url": {}}}
        rid = self.request("initialize", {"protocolVersion": "2025-11-25",
                                          "capabilities": capabilities})
        reply = self.receive()
        assert reply["id"] == rid
        assert reply["result"]["protocolVersion"] == "2025-11-25"
        assert reply["result"]["capabilities"] == {"tools": {}}
        assert reply["result"]["serverInfo"]["name"] == "blemma"
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        rid = self.request("tools/list", {})
        reply = self.receive()
        assert reply["id"] == rid
        tools = reply["result"]["tools"]
        assert len(tools) == 1 and tools[0]["name"] == "ask_board"
        schema = tools[0]["inputSchema"]
        assert schema["required"] == ["title", "choices"]
        assert schema["properties"]["choices"]["minItems"] == 2
        assert schema["properties"]["choices"]["maxItems"] == 6

    def call(self, args=None):
        return self.request("tools/call", {"name": "ask_board",
                                            "arguments": ARGS if args is None else args})

    def elicit(self):
        msg = self.receive()
        assert msg["method"] == "elicitation/create"
        assert msg["params"]["mode"] == "form"
        assert "_meta" not in msg["params"]
        schema = msg["params"]["requestedSchema"]
        assert schema["type"] == "object" and schema["required"] == ["choice"]
        field = schema["properties"]["choice"]
        assert field["type"] == "string"
        assert "default" not in field
        assert sum(option["title"] == STOP for option in field["oneOf"]) == 1
        return msg

    def answer(self, elicit, result):
        self.send({"jsonrpc": "2.0", "id": elicit["id"], "result": result})

    def result(self, rid):
        msg = self.receive()
        assert msg["id"] == rid and "error" not in msg
        return msg["result"]

    def cancel(self, rid):
        self.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                   "params": {"requestId": rid}})

    def child_cancel(self, elicit):
        assert self.receive() == {"jsonrpc": "2.0", "method": "notifications/cancelled",
                                  "params": {"requestId": elicit["id"]}}

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.reader.join(timeout=5)
            self.stderr = self.process.stderr.read()
            self.process.stdout.close()
            self.process.stderr.close()
        assert self.process.returncode == 0
        if not self.debug:
            assert self.stderr == b""


@pytest.fixture
def client_factory():
    clients = []

    def make(**kwargs):
        client = Client(**kwargs)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def client(client_factory):
    instance = client_factory()
    instance.initialize()
    return instance


def text_result(result):
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
    return result["content"][0]["text"]


@pytest.mark.parametrize("descriptions", [None, ["案を確認します", "試験だけを実行します"]])
def test_descriptions_are_optional_schema_annotations(client, descriptions):
    args = dict(ARGS)
    if descriptions is not None:
        args["descriptions"] = descriptions
    rid = client.call(args)
    elicit = client.elicit()
    opts = elicit["params"]["requestedSchema"]["properties"]["choice"]["oneOf"]
    if descriptions is None:
        assert all("description" not in o for o in opts)
    else:
        assert [o["description"] for o in opts[:2]] == descriptions
        assert "description" not in opts[-1]  # The automatically added stop has no invented explanation.
    client.answer(elicit, {"action": "cancel"})
    assert not client.result(rid).get("isError")


@pytest.mark.parametrize("descriptions", [[], ["one"], ["a", "b", "c"], "bad", ["a", 2], None])
def test_invalid_descriptions_are_rejected(client, descriptions):
    rid = client.call({**ARGS, "descriptions": descriptions})
    assert client.result(rid)["isError"]


@pytest.mark.parametrize("drop_descriptions", [False, True])
def test_descriptions_through_real_elicitation_hook_and_board(client, live, drop_descriptions):
    srv = live()
    rid = client.call({**ARGS, "descriptions": ["案の全文を読みます", "試験を実行します"]})
    elicitation = client.elicit()
    schema = elicitation["params"]["requestedSchema"]
    if drop_descriptions:
        for option in schema["properties"]["choice"]["oneOf"]:
            option.pop("description", None)
    data = {"hook_event_name": "Elicitation", "mode": "form", "mcp_server_name": "blemma",
            "session_id": "abcdef1234", "message": ARGS["title"], "requested_schema": schema}
    env = {**os.environ, "BLEMMA_RUN_FILE": str(srv.run_file), "BLEMMA_DEBUG": "0"}
    process = subprocess.Popen([sys.executable, "-I", "-B", str(ROOT / "hooks" / "elicitation.py")],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        process.stdin.write(json.dumps(data).encode())
        process.stdin.close()
        card = srv.wait_card()
        option = card["payload"]["fields"][0]["options"][1]
        assert option.get("description") == (None if drop_descriptions else "試験を実行します")
        assert srv.request("POST", "/answer", {"id": card["id"], "seq": card["view_seq"],
                                                "choice": {"type": "accept", "picks": [[1]]}, "by": "key"})[0] == 200
        process.wait(timeout=5)
        assert process.returncode == 0 and process.stderr.read() == b""
        output = json.loads(process.stdout.read())["hookSpecificOutput"]
        assert output == {"hookEventName": "Elicitation", "action": "accept", "content": {"choice": "2"}}
        client.answer(elicitation, {k: output[k] for k in ("action", "content")})
        assert json.loads(text_result(client.result(rid)))["answer"] == ARGS["choices"][1]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("action", ["accept", "decline", "cancel", "cancelled"])
def test_response_table(client, action):
    rid = client.call()
    elicit = client.elicit()
    assert elicit["params"]["message"] == ARGS["title"]
    props = elicit["params"]["requestedSchema"]["properties"]
    assert list(props) == ["choice"]
    assert props["choice"]["title"] == ARGS["title"]
    assert props["choice"]["oneOf"] == [
        {"const": "1", "title": "案を見る"},
        {"const": "2", "title": "試験を回す"},
        {"const": "3", "title": STOP},
    ]
    if action == "cancelled":
        client.cancel(rid)
        client.child_cancel(elicit)
    else:
        reply = {"action": action}
        if action == "accept":
            reply["content"] = {"choice": "2"}
        client.answer(elicit, reply)
    result = client.result(rid)
    assert result["isError"] is False
    text = text_result(result)
    if action == "accept":
        assert json.loads(text) == {"answer": "試験を回す", "index": 2}
    else:
        head, instruction = text.split("\n", 1)
        key = "declined" if action == "decline" else "cancelled"
        assert json.loads(head) == {"answer": None, key: True}
        assert instruction == (DECLINED if action == "decline" else CANCELLED)


@pytest.mark.parametrize("choices", [[], ["一つ"], [str(i) for i in range(7)]])
def test_choice_count_rejected_without_elicitation(client, choices):
    result = client.result(client.call({**ARGS, "choices": choices}))
    assert result["isError"] is True
    assert "2-6" in text_result(result)


@pytest.mark.parametrize("choices", [
    ["案", STOP], ["案", " ここで止める "],
    ["1", "2", "3", "4", "5"], ["1", "2", "3", "4", "5", STOP],
    [STOP, "1", "2", "3", "4", "5"],
])
def test_exactly_one_stop_with_at_most_six_choices(client, choices):
    rid = client.call({**ARGS, "choices": choices})
    elicit = client.elicit()
    options = elicit["params"]["requestedSchema"]["properties"]["choice"]["oneOf"]
    assert 2 <= len(options) <= 6
    stop = next(option for option in options if option["title"] == STOP)
    client.answer(elicit, {"action": "accept", "content": {"choice": stop["const"]}})
    result = client.result(rid)
    assert result["isError"] is False
    assert json.loads(text_result(result)) == {"answer": STOP, "index": int(stop["const"])}


def test_six_choices_without_room_for_stop_are_rejected(client):
    rid = client.call({**ARGS, "choices": [str(i) for i in range(6)]})
    result = client.result(rid)
    assert result["isError"] is True
    assert STOP in text_result(result)


@pytest.mark.parametrize("args", [
    None, [], {**ARGS, "title": " "}, {**ARGS, "title": "a" * 81},
    {**ARGS, "choices": ["a" * 41, "b"]}, {**ARGS, "choices": ["a", " a "]},
    {**ARGS, "choices": [" ", "b"]}, {**ARGS, "choices": [1, "b"]},
    {**ARGS, "choices": "ab"}, {**ARGS, "allow_free_text": 1},
])
def test_invalid_arguments_are_tool_errors(client, args):
    rid = client.request("tools/call", {"name": "ask_board", "arguments": args})
    assert client.result(rid)["isError"] is True


@pytest.mark.parametrize("content", [
    None, [], {}, {"choice": 1}, {"choice": True}, {"choice": "01"},
    {"choice": "１"}, {"choice": "9"}, {"choice": "other"},
])
def test_accept_requires_an_exact_requested_choice(client, content):
    rid = client.call()
    client.answer(client.elicit(), {"action": "accept", "content": content})
    assert client.result(rid)["isError"] is True


@pytest.mark.parametrize("other, valid", [("別の案 🧭", True), ("a" * 200, True),
                                         ("a" * 201, False), (None, False)])
def test_optional_free_text(client, other, valid):
    rid = client.call({**ARGS, "allow_free_text": True})
    elicit = client.elicit()
    props = elicit["params"]["requestedSchema"]["properties"]
    assert props["choice"]["oneOf"][-1] == {"const": "other", "title": "ほかの答え (書いて伝える)"}
    assert props["other_text"]["maxLength"] == 200
    client.answer(elicit, {"action": "accept", "content": {"choice": "other", "other_text": other}})
    result = client.result(rid)
    assert result["isError"] is not valid
    if valid:
        assert json.loads(text_result(result)) == {"answer": other, "free_text": True}


@pytest.mark.parametrize("capabilities, supported", [
    ({}, False), ({"elicitation": {"url": {}}}, False),
    ({"elicitation": None}, False), ({"elicitation": {}}, True),
    ({"elicitation": {"form": {}}}, True),
])
def test_form_capability(client_factory, capabilities, supported):
    client = client_factory()
    client.initialize(capabilities)
    rid = client.call()
    if supported:
        client.answer(client.elicit(), {"action": "cancel"})
    result = client.result(rid)
    assert result["isError"] is not supported
    if not supported:
        assert text_result(result) == "この環境では MCP の問いが出せません。AskUserQuestion か文で訊いてください。"


def test_pending_calls_are_independent_and_ping_still_works(client):
    first_id = client.call()
    first = client.elicit()
    second_id = client.call()
    second = client.elicit()
    for invalid_id in ("unknown", [], None, True, second["id"]):
        client.cancel(invalid_id)
    ping_id = client.request("ping", {})
    assert client.result(ping_id) == {}
    client.cancel(first_id)
    client.child_cancel(first)
    assert text_result(client.result(first_id)).endswith(CANCELLED)
    client.answer(first, {"action": "accept", "content": {"choice": "1"}})
    client.cancel(first_id)
    client.answer(second, {"action": "accept", "content": {"choice": "2"}})
    assert json.loads(text_result(client.result(second_id))) == {"answer": "試験を回す", "index": 2}


def test_cancellation_immediately_after_call_is_not_lost(client):
    rid = client.call()
    client.cancel(rid)
    while True:
        msg = client.receive()
        if msg.get("id") == rid:
            assert text_result(msg["result"]).endswith(CANCELLED)
            break
        assert msg.get("method") in ("elicitation/create", "notifications/cancelled")


@pytest.mark.parametrize("waiting", [False, True])
def test_stdin_eof_exits_quietly_even_while_waiting(client, waiting):
    if waiting:
        client.call()
        client.elicit()
    client.process.stdin.close()
    client.process.wait(timeout=3)
    client.close()
    assert client.lines.get(timeout=3) is None


def test_wait_timeout_uses_real_event_wait(client_factory):
    client = client_factory(wait_timeout=0.1)
    client.initialize()
    rid = client.call()
    elicit = client.elicit()
    client.child_cancel(elicit)
    result = client.result(rid)
    assert result["isError"] is True
    assert text_result(result) == "回答の待ち時間を過ぎました。作業を止めて次の指示を待ってください。"
    # 期限後の答えを捨て、後続の要求を処理できる。
    client.answer(elicit, {"action": "accept", "content": {"choice": "1"}})
    assert client.result(client.request("ping", {})) == {}


def test_default_wait_is_shared_with_board():
    import runpy

    module = runpy.run_path(str(SCRIPT))
    assert module["ELICIT_WAIT_SEC"] == board_server.Limits().hard_deadline


@pytest.mark.parametrize("raw", [b"{bad JSON}\n", b"\xff\n"])
def test_bad_input_reports_json_rpc_error_and_recovers(client, raw):
    client.raw(raw)
    assert client.receive()["error"]["code"] == -32700
    assert client.result(client.request("ping", {})) == {}


def test_debug_is_opt_in_and_omits_input(client_factory):
    client = client_factory(debug=True)
    client.initialize()
    client.raw(b"{private-input-marker}\n")
    assert client.receive()["error"]["code"] == -32700
    client.close()
    assert b"[blemma-mcp]" in client.stderr
    assert b"private-input-marker" not in client.stderr


@pytest.mark.parametrize("reply", [
    {"result": {"action": "unexpected"}}, {"result": []},
    {"error": {"code": -32603, "message": "private-error-marker"}},
])
def test_client_errors_are_tool_errors_without_echoing_content(client, reply):
    rid = client.call()
    elicit = client.elicit()
    client.send({"jsonrpc": "2.0", "id": elicit["id"], **reply})
    result = client.result(rid)
    assert result["isError"] is True
    assert "private-error-marker" not in text_result(result)
