# -*- coding: utf-8 -*-
"""起動処理の試験。板は本物の子プロセス、Claude とブラウザは起動しない。"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:  # どの cwd から pytest を打っても repo の根の blemma.py を読めるように
    sys.path.insert(0, str(REPO))

import blemma as L  # noqa: E402


@pytest.fixture(autouse=True)
def no_external_apps(monkeypatch):
    """Permit real Python children only; an accidental Claude/browser launch fails."""
    original = subprocess.Popen

    def guarded(command, *args, **kwargs):
        assert isinstance(command, list) and command[0] in (sys.executable, L.python_executable()), "外部アプリの起動は禁止"
        return original(command, *args, **kwargs)

    def unexpected_browser(*args, **kwargs):
        pytest.fail("ブラウザの実起動は禁止")

    monkeypatch.setattr(subprocess, "Popen", guarded)
    monkeypatch.setattr(L.webbrowser, "open", unexpected_browser)
    for name in ("BLEMMA_WINDOW_SIZE", "BLEMMA_WINDOW_POSITION", "BLEMMA_OPTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BLEMMA_DEBUG", "0")


@pytest.fixture
def isolated_repo(tmp_path):
    # Copy the unmodified production script: its __file__ controls state placement.
    root = tmp_path / "repo 空白"
    (root / "board").mkdir(parents=True)
    shutil.copy2(REPO / "board" / "server.py", root / "board" / "server.py")
    return root


@pytest.fixture
def sessions(monkeypatch):
    original = L.ensure_board
    opened = []

    def tracked(*args, **kwargs):
        session = original(*args, **kwargs)
        opened.append(session)
        return session

    monkeypatch.setattr(L, "ensure_board", tracked)
    yield opened
    for session in reversed(opened):
        session.close()


def unused_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@pytest.fixture
def probe_server():
    """実 HTTP で、通常の応答か、見出し/本文を細切れにした応答を返す。"""
    made = []

    def start(slow_part=None):
        stopped = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = b'{"error": "unknown"}'
                header = f"HTTP/1.0 404 Not Found\r\nContent-Length: {len(body)}\r\n".encode("ascii")
                if slow_part == "headers":
                    first, slow, last = header + b"X-Probe: ", b"x" * 24, b"\r\n\r\n" + body
                elif slow_part == "body":
                    first, slow, last = header + b"\r\n", body, b""
                else:
                    first, slow, last = header + b"\r\n" + body, b"", b""
                try:
                    self.wfile.write(first)
                    for byte in slow:
                        if stopped.wait(0.04):
                            return
                        self.wfile.write(bytes([byte]))
                    self.wfile.write(last)
                except OSError:
                    pass  # 期限を過ぎた呼び手は途中で接続を閉じる。

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        made.append((httpd, thread, stopped))
        return L.RunInfo(httpd.server_port, "test-placeholder", os.getpid())

    yield start
    for httpd, thread, stopped in made:
        stopped.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join(2)


@pytest.mark.parametrize("part", ["headers", "body"])
def test_probe_trickle_cannot_extend_total_deadline(probe_server, part):
    info = probe_server(part)
    started = time.monotonic()
    assert not L.board_responds(info, timeout=0.3)
    assert time.monotonic() - started < 0.7  # 細切れの応答を受け切れば 0.76 秒以上。


def test_probe_normal_response_succeeds(probe_server):
    assert L.board_responds(probe_server(), timeout=0.3)


def test_existing_board_probe_uses_startup_deadline(isolated_repo, probe_server, monkeypatch):
    info = probe_server("body")
    path = isolated_repo / "board" / "state" / "run.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"port": info.port, "token": info.token, "pid": info.pid,
                                "started": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")

    def unexpected_start(*args, **kwargs):
        pytest.fail("既存の板の照会で期限切れ = 新しい板を起こさない")

    monkeypatch.setattr(L.subprocess, "Popen", unexpected_start)
    started = time.monotonic()
    with pytest.raises(L.LaunchError, match="timed out"):
        L.ensure_board(isolated_repo, unused_port(), timeout=0.3)
    assert time.monotonic() - started < 0.7
    assert path.exists()  # 既存の板の記録は呼び手が所有する。


@pytest.mark.parametrize("reuse", [False, True])
def test_startup_checks_deadline_after_success(isolated_repo, sessions, monkeypatch, reuse):
    """照会の成功後に期限を越えた時も失敗。新しく起こした実プロセスだけを止める。"""
    existing = L.ensure_board(isolated_repo, unused_port()) if reuse else None
    original_probe = L.board_responds
    original_popen = L.subprocess.Popen
    children = []

    def delayed_probe(info, timeout=0.3, *, deadline=None):
        ready = original_probe(info, timeout, deadline=deadline)  # 接続・照会は本物。
        if ready:
            time.sleep(max(0, deadline - time.monotonic()) + 0.02)
        return ready

    def record(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(L, "board_responds", delayed_probe)
    monkeypatch.setattr(L.subprocess, "Popen", record)
    with pytest.raises(L.LaunchError, match="timed out"):
        L.ensure_board(isolated_repo, unused_port(), timeout=1.0)
    if reuse:
        assert not children and existing.process.poll() is None
    else:
        assert len(children) == 1 and children[0].poll() is not None
        assert not (isolated_repo / "board" / "state" / "run.json").exists()


def test_generated_configs_and_templates(isolated_repo, monkeypatch):
    monkeypatch.chdir(isolated_repo.parent)
    paths = L.write_configs(Path(isolated_repo.name))
    settings, mcp = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(path.is_absolute() and path.parent == isolated_repo / "board" / "state" for path in paths)
    assert settings["permissions"] == {"allow": ["mcp__blemma__ask_board"]}
    expected = {
        "PermissionRequest": (".*", "permission.py", 600),
        "PreToolUse": ("AskUserQuestion", "ask.py", 600),
        "Elicitation": (".*", "elicitation.py", 600),
        "Notification": ("permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
                         "notify.py", 10),
        "UserPromptSubmit": (None, "state.py", 5),
        "Stop": (None, "state.py", 5),
    }
    assert set(settings["hooks"]) == set(expected)
    for event, (matcher, name, timeout) in expected.items():
        assert settings["hooks"][event] == [{**({"matcher": matcher} if matcher else {}), "hooks": [{
            "type": "command", "command": L.python_executable(),
            "args": [str(isolated_repo / "hooks" / name)], "timeout": timeout,
            **({"statusMessage": L.STATUS_MESSAGE} if name != "state.py" else {}),
        }]}]
        assert (REPO / "hooks" / name).is_file()
    assert Path(L.python_executable()).is_absolute()
    assert mcp == {"mcpServers": {"blemma": {
        "command": L.python_executable(), "args": [str(isolated_repo / "mcp" / "blemma_mcp.py")],
    }}}

    def expand(value):
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        if value == "<PY>":
            return L.python_executable()
        if isinstance(value, str) and value.startswith("<BLEMMA>/"):
            return str(isolated_repo / value[len("<BLEMMA>/"):])
        return value

    for name, generated in (("settings", settings), ("mcp", mcp)):
        template = json.loads((REPO / "examples" / f"{name}.blemma.json").read_text(encoding="utf-8"))
        assert expand(template) == generated
    assert not list(paths[0].parent.glob("*.tmp"))


@pytest.mark.parametrize("demo", [False, True])
def test_flags_and_passthrough(tmp_path, demo):
    extra = ["--model", "sonnet", "引用 'a' と空白", "--demo", "--", "末尾"]
    args = L.parse_args((["--demo"] if demo else []) + ["--large", "--port", "12345", "--"] + extra)
    paths = (tmp_path / "settings.generated.json", tmp_path / "mcp.generated.json")
    expected = ["claude", "--settings", str(paths[0]), "--mcp-config", str(paths[1]),
                "--permission-mode", "default"]
    if demo:
        expected += ["--setting-sources", "project,local", "--strict-mcp-config"]
    assert L.claude_command(None, paths, args) == expected + extra
    assert args.mode == "large" and args.port == 12345
    defaults = L.parse_args([])
    assert defaults.mode == "small" and defaults.window_size == (660, 700)
    assert defaults.window_position is None and defaults.claude_args == []


def test_geometry_env_and_argument_precedence(monkeypatch):
    monkeypatch.setenv("BLEMMA_WINDOW_SIZE", "640x400")
    monkeypatch.setenv("BLEMMA_WINDOW_POSITION", "-200,20")
    args = L.parse_args([])
    assert args.window_size == (640, 400) and args.window_position == (-200, 20)
    args = L.parse_args(["--window-size", "500,300", "--window-position=30,-10"])
    assert args.window_size == (500, 300) and args.window_position == (30, -10)


def test_page_options_environment_repeated_set_and_url(monkeypatch):
    monkeypatch.setenv("BLEMMA_OPTS", "scale=1.25&theme=dark&mode=large&scan&unknown=ignored")
    args = L.parse_args(["--set", "theme=light", "--set", "theme=contrast", "--set", "desc=off"])
    assert args.mode == "large"
    assert args.page_options == {"scale": "1.25", "theme": "contrast", "scan": "", "desc": "off"}
    assert L.parse_args(["--small"]).mode == "small"
    assert L.parse_args(["--set", "mode=small"]).mode == "small"
    urls = []
    monkeypatch.setattr(L.webbrowser, "open", lambda url: urls.append(url) or True)
    L.open_board(L.RunInfo(18770, "test-placeholder", 123), args.mode, (420, 640), None, args.page_options)
    url = urlsplit(urls[0])
    assert parse_qs(url.query, keep_blank_values=True) == {
        "mode": ["large"], "scale": ["1.25"], "theme": ["contrast"], "scan": [""], "desc": ["off"]}
    assert url.fragment == "t=test-placeholder"


@pytest.mark.parametrize("argv", [
    ["--small", "--large"], ["--port", "0"], ["--port", "65536"],
    ["--window-size", "0,360"], ["--window-position", "bad"], ["--unknown"],
])
def test_bad_arguments_are_one_bilingual_line(argv, capsys):
    assert L.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "引数" in captured.err and "Invalid arguments" in captured.err


def test_help_runs_without_starting_apps():
    result = subprocess.run([sys.executable, "-B", str(REPO / "blemma.py"), "--help"],
                            capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0 and result.stderr == ""
    assert "板と Claude Code を起こします" in result.stdout and "Launch the board" in result.stdout
    assert "BLEMMA_WINDOW_SIZE" in result.stdout and "--keep-board" in result.stdout


def test_missing_claude_prints_one_line_and_exits_zero(isolated_repo, sessions, monkeypatch, capsys):
    # Exercise shutil.which itself with an empty executable search path.
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(isolated_repo)
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    opened = []
    monkeypatch.setattr(L.webbrowser, "open", lambda url: opened.append(url) or True)
    assert L.find_claude() is None
    assert L.main(["--large", "--port", str(unused_port()), "--", "日本語の頼み"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1 and captured.err == ""
    assert "claude" in captured.out and "--permission-mode" in captured.out and "日本語の頼み" in captured.out
    assert "#t=" not in captured.out
    assert len(opened) == 1
    assert sessions[0].process.poll() is not None
    assert not sessions[0].run_file.exists()
    assert not L.board_responds(sessions[0].info, timeout=0.05)
    assert (isolated_repo / "board" / "state" / "settings.generated.json").is_file()


@pytest.mark.parametrize("keep", [False, True])
def test_print_only_prepares_real_board_without_claude(isolated_repo, sessions, monkeypatch, capsys, keep):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L.shutil, "which", lambda name: "claude.exe" if name == "claude" else None)
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)
    argv = ["--large", "--demo", "--print-only", "--port", str(unused_port())]
    assert L.main(argv + (["--keep-board"] if keep else [])) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1 and captured.err == ""
    assert "--strict-mcp-config" in captured.out and "project,local" in captured.out
    session = sessions[0]
    assert session.run_file.exists() == keep
    assert (session.process.poll() is None) == keep
    assert L.board_responds(session.info, timeout=0.05) == keep


def test_real_server_start_reuse_and_stop(isolated_repo, sessions, monkeypatch):
    # A bogus proxy must not intercept even the launcher's readiness check.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    first = L.ensure_board(isolated_repo, unused_port())
    data = json.loads(first.run_file.read_text(encoding="utf-8"))
    assert data["pid"] == first.process.pid and data["port"] == first.info.port
    assert datetime.fromisoformat(data["started"]).tzinfo is not None
    assert L.board_responds(first.info)
    assert not L.board_responds(L.RunInfo(first.info.port, "wrong-test-token", first.info.pid))
    reused = L.ensure_board(isolated_repo, unused_port())
    assert reused.process is None and reused.info == first.info
    reused.close()
    assert first.process.poll() is None and L.board_responds(first.info)
    first.close()
    assert first.process.poll() is not None and not first.run_file.exists()
    assert not L.board_responds(first.info, timeout=0.05)


def test_cleanup_preserves_another_servers_run_file(isolated_repo, sessions):
    session = L.ensure_board(isolated_repo, unused_port())
    replacement = {"port": session.info.port, "token": "other-test-placeholder",
                   "pid": session.process.pid + 1, "started": datetime.now(timezone.utc).isoformat()}
    session.run_file.write_text(json.dumps(replacement), encoding="utf-8")
    session.close()
    assert session.process.poll() is not None
    assert json.loads(session.run_file.read_text(encoding="utf-8")) == replacement


def test_stale_and_invalid_run_records_are_ignored(tmp_path):
    path = tmp_path / "run.json"
    good = {"port": 8765, "token": "test-placeholder", "pid": 123,
            "started": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(good), encoding="utf-8")
    assert L.read_run(path) is not None
    old = time.time() - L.RUN_MAX_AGE - 1
    os.utime(path, (old, old))
    assert L.read_run(path) is None
    for patch in ({"port": True}, {"pid": 0}, {"token": "bad\r\nheader"},
                  {"started": "2000-01-01T00:00:00+00:00"}, {"started": "bad"}):
        path.write_text(json.dumps({**good, **patch}), encoding="utf-8")
        assert L.read_run(path) is None
    for raw in ("[1]", "null", "broken", "{}"):
        path.write_text(raw, encoding="utf-8")
        assert L.read_run(path) is None


def test_occupied_port_stops_before_browser_or_claude(isolated_repo, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    with socket.socket() as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert L.main(["--port", str(listener.getsockname()[1])]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "板を起動できません" in captured.err and "Board server exited" in captured.err
    assert not (isolated_repo / "board" / "state" / "run.json").exists()


def test_startup_timeout_stops_real_child(isolated_repo, monkeypatch):
    children = []
    original = L.subprocess.Popen

    def record(*args, **kwargs):
        process = original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(L.subprocess, "Popen", record)
    # Simulate an unreadable discovery file, while still starting the real server.
    monkeypatch.setattr(L, "read_run", lambda path: None)
    with pytest.raises(L.LaunchError, match="timed out"):
        L.ensure_board(isolated_repo, unused_port(), timeout=0.5)
    assert len(children) == 1 and children[0].poll() is not None
    assert not (isolated_repo / "board" / "state" / "run.json").exists()


@pytest.mark.parametrize("keep", [False, True])
def test_browser_failure_cleans_owned_board(isolated_repo, sessions, monkeypatch, capsys, keep):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L.webbrowser, "open", lambda url: False)
    assert L.main(["--large", "--port", str(unused_port())] + (["--keep-board"] if keep else [])) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "ブラウザ" in captured.err and "Could not open" in captured.err
    assert sessions[0].process.poll() is not None and not sessions[0].run_file.exists()


def test_claude_exit_code_and_caller_working_directory(isolated_repo, sessions, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.chdir(isolated_repo.parent)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)
    commands = []

    def pretend_claude(command):
        assert L.board_responds(sessions[0].info)
        assert Path.cwd() == isolated_repo.parent
        assert Path(command[2]).is_file() and Path(command[4]).is_file()
        commands.append(command)
        return 17

    monkeypatch.setattr(L, "run_claude", pretend_claude)
    assert L.main(["--large", "--port", str(unused_port()), "--", "頼み"]) == 17
    assert len(commands) == 1 and commands[0][-1] == "頼み"
    assert sessions[0].process.poll() is not None and not sessions[0].run_file.exists()
    assert capsys.readouterr() == ("", "")


def test_config_write_failure_stops_before_claude(isolated_repo, sessions, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)
    (isolated_repo / "board" / "state" / "settings.generated.json").mkdir(parents=True)
    assert L.main(["--large", "--keep-board", "--port", str(unused_port())]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "起動処理に失敗" in captured.err and "Launch failed" in captured.err
    assert sessions[0].process.poll() is not None and not sessions[0].run_file.exists()
    assert not list((isolated_repo / "board" / "state").glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows executable suffixes")
@pytest.mark.parametrize("name", ["claude.cmd", "claude.exe"])
def test_windows_claude_suffix_lookup(monkeypatch, name):
    monkeypatch.setattr(L.shutil, "which", lambda candidate: name if candidate == name else None)
    assert L.find_claude() == name


def test_real_child_wait_and_argument_preservation():
    # Only Python is executed. This verifies the subprocess path, not Claude itself.
    extra = ["空白 と日本語", "a\"b", "x&y", "", "trailing\\"]
    code = "import sys,time; time.sleep(0.05); sys.exit(23 if sys.argv[1:] == " + repr(extra) + " else 99)"
    assert L.run_claude([sys.executable, "-c", code] + extra) == 23


@pytest.mark.skipif(os.name != "nt", reason="Windows command wrapper")
def test_windows_cmd_argument_preservation(tmp_path, monkeypatch):
    # A disposable wrapper, not the installed Claude executable.
    wrapper = tmp_path / "test wrapper.cmd"
    capture = tmp_path / "capture.py"
    result = tmp_path / "arguments.json"
    wrapper.write_text('@echo off\n"%BLEMMA_TEST_PYTHON%" "%~dp0capture.py" %*\n', encoding="ascii")
    capture.write_text("import json,sys\nfrom pathlib import Path\n"
                       "Path(__file__).with_name('arguments.json').write_text("
                       "json.dumps(sys.argv[1:]), encoding='utf-8')\nsys.exit(23)\n", encoding="utf-8")
    monkeypatch.setenv("BLEMMA_TEST_PYTHON", sys.executable)
    monkeypatch.setenv("BLEMMA_LITERAL_TEST", "must-not-expand")
    extra = ["日本語 空白", "x&y", 'a"b', "%BLEMMA_LITERAL_TEST%", "bang!", "", "trailing\\"]
    code = "import sys; sys.path.insert(0, " + repr(str(REPO)) + "); import blemma; sys.exit(blemma.run_claude(sys.argv[1:]))"
    child = subprocess.run([sys.executable, "-c", code, str(wrapper)] + extra, capture_output=True)
    assert child.returncode == 23
    assert json.loads(result.read_text(encoding="utf-8")) == extra


@pytest.mark.skipif(os.name != "nt", reason="Windows command wrapper")
def test_windows_cmd_multiline_fails_before_launch():
    with pytest.raises(L.LaunchError, match="claude.exe"):
        L.run_claude(["test.cmd", "line1\nline2"])


def test_small_window_uses_token_fragment_and_bottom_right(monkeypatch):
    commands = []
    monkeypatch.setattr(L, "find_app_browser", lambda: "test-browser")
    monkeypatch.setattr(L, "work_area", lambda: (0, 0, 1920, 1040))
    monkeypatch.setattr(L.subprocess, "Popen", lambda command, **kwargs: commands.append(command))
    L.open_board(L.RunInfo(8765, "test-placeholder", 123), "small", (480, 360), None)
    command = commands[0]
    assert command[0] == "test-browser" and command[2:] == ["--window-size=480,360", "--window-position=1440,680"]
    url = urlsplit(command[1].removeprefix("--app="))
    assert url.hostname == "127.0.0.1" and url.port == 8765
    assert parse_qs(url.query) == {"mode": ["small"]} and url.fragment == "t=test-placeholder"
    L.open_board(L.RunInfo(8765, "test-placeholder", 123), "small", (600, 400), (-20, 10))
    assert commands[1][-1] == "--window-position=-20,10"


@pytest.mark.parametrize("mode,browser,area", [
    ("large", "test-browser", (0, 0, 1920, 1080)), ("small", None, None), ("small", "test-browser", None),
])
def test_default_browser_fallback(monkeypatch, mode, browser, area):
    urls = []
    monkeypatch.setattr(L, "find_app_browser", lambda: browser)
    monkeypatch.setattr(L, "work_area", lambda: area)
    monkeypatch.setattr(L.webbrowser, "open", lambda url: urls.append(url) or True)
    L.open_board(L.RunInfo(8765, "test-placeholder", 123), mode, (480, 360), None)
    assert len(urls) == 1 and f"?mode={mode}#t=" in urls[0]


def test_command_line_stays_on_one_line():
    line = L.format_command(["claude", "空白 と '引用'", "$value`", "line1\nline2\r"])
    assert len(line.splitlines()) == 1
    if os.name == "nt":
        assert line.startswith('& "claude" ') and "`$value``" in line and "`n" in line
    else:
        assert line.startswith("claude ") and "\\n" in line
