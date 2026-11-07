# -*- coding: utf-8 -*-
"""起動処理の試験。板は本物の子プロセス、Claude とブラウザは起動しない。"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
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


def run_info(root):
    return L.read_run(root / "board" / "state" / "run.json")


def client_files(root):
    folder = root / "board" / "state" / "clients"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


class Launchers:
    """起こし方を thread で回す。Claude の代わりは、名 (最後の引数) ごとに end() まで終わらない。"""

    def __init__(self, port):
        self.port = port
        self.running, self.finish, self.codes, self.threads = {}, {}, {}, {}

    def pretend_claude(self, command):
        self.running[command[-1]].set()
        assert self.finish[command[-1]].wait(10)
        return 0

    def start(self, name, *flags):
        self.running[name], self.finish[name] = threading.Event(), threading.Event()
        argv = ["--large", "--port", str(self.port), *flags, "--", name]
        thread = threading.Thread(target=lambda: self.codes.setdefault(name, L.main(argv)), daemon=True)
        self.threads[name] = thread
        thread.start()
        deadline = time.monotonic() + 10
        while not self.running[name].wait(0.05):
            assert thread.is_alive() and time.monotonic() < deadline, "起こし方が Claude の起動まで届かない"

    def end(self, name):
        self.finish[name].set()
        self.threads[name].join(10)
        assert not self.threads[name].is_alive() and self.codes[name] == 0

    def release_all(self):
        for event in self.finish.values():
            event.set()
        for thread in self.threads.values():
            thread.join(10)


@pytest.fixture
def launchers(isolated_repo, monkeypatch):
    runner = Launchers(unused_port())
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(L, "run_claude", runner.pretend_claude)
    yield runner
    runner.release_all()


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
    # 「待っています」は板の答えを待つ 3 本だけ。通知 (1 回送るだけ) と状態の 2 本には付けない。
    expected = {
        "PermissionRequest": (".*", "permission.py", 600, True),
        "PreToolUse": ("AskUserQuestion", "ask.py", 600, True),
        "Elicitation": (".*", "elicitation.py", 600, True),
        "Notification": ("permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
                         "notify.py", 10, False),
        "UserPromptSubmit": (None, "state.py", 5, False),
        "Stop": (None, "state.py", 5, False),
    }
    assert set(settings["hooks"]) == set(expected)
    for event, (matcher, name, timeout, waits) in expected.items():
        assert settings["hooks"][event] == [{**({"matcher": matcher} if matcher else {}), "hooks": [{
            "type": "command", "command": L.python_executable(),
            "args": ["-I", str(isolated_repo / "hooks" / name)], "timeout": timeout,
            **({"statusMessage": L.STATUS_MESSAGE} if waits else {}),
        }]}]
        assert (REPO / "hooks" / name).is_file()
    assert Path(L.python_executable()).is_absolute()
    assert mcp == {"mcpServers": {"blemma": {
        "command": L.python_executable(), "args": ["-I", str(isolated_repo / "mcp" / "blemma_mcp.py")],
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


@pytest.fixture
def shadowing_pythonpath(tmp_path, monkeypatch):
    """利用者の PYTHONPATH に、標準と同じ名の module (json) がある形。子の process だけが受け継ぐ。"""
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "json.py").write_text("raise ImportError('shadowed json (test stand-in)')\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    return shadow


def test_generated_hooks_and_mcp_survive_a_shadowing_pythonpath(isolated_repo, tmp_path, shadowing_pythonpath):
    """生成の設定の起こし方 (-I) のまま、6 本の hook は無出力 exit 0 で、MCP server は initialize に答える。
    -I が無いと permission.py と MCP server は traceback を出して exit 1 になる (hook のほかの 4 本も _client を
    読めず、黙って板なしの動きになる)。木を汚さないよう、写した repo から起こす。"""
    for sub in ("hooks", "mcp"):
        shutil.copytree(REPO / sub, isolated_repo / sub, ignore=shutil.ignore_patterns("__pycache__"))
    settings, mcp = [json.loads(path.read_text(encoding="utf-8")) for path in L.write_configs(isolated_repo)]
    env = {**os.environ, "BLEMMA_RUN_FILE": str(tmp_path / "no-board.json"), "BLEMMA_DEBUG": "0"}
    hooks = [group["hooks"][0] for groups in settings["hooks"].values() for group in groups]
    assert len(hooks) == 6
    for hook in hooks:
        result = subprocess.run([hook["command"], *hook["args"]], input=b"{}", capture_output=True, env=env,
                                timeout=30)
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), hook["args"][-1]
    server = mcp["mcpServers"]["blemma"]
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}
    result = subprocess.run([server["command"], *server["args"]], input=(json.dumps(request) + "\n").encode(),
                            capture_output=True, env=env, timeout=30)
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout)["result"]["serverInfo"]["name"] == "blemma"


def test_board_starts_despite_a_shadowing_pythonpath(isolated_repo, sessions, shadowing_pythonpath):
    session = L.ensure_board(isolated_repo, unused_port())   # -I が無いと板の server が起動で落ちる
    assert session.process is not None and L.board_responds(session.info)


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
    assert defaults.mode == "small" and defaults.window_size == (640, 720)
    assert defaults.window_position is None and defaults.claude_args == []


@pytest.mark.parametrize("extra", [["--settings", "my.json"], ["--settings=my.json"], ["--settings", "{}"]])
def test_settings_after_the_separator_is_refused(monkeypatch, capsys, extra):
    """`--` の後ろの --settings は断る (2 巡目 i8)。Claude Code の --settings は後に出た物が勝つ = 渡すと生成した設定
    (hooks 6 本と ask_board の許可) が丸ごと外れ、扇に札が来ないまま端末だけで動く。断る文は 1 行で、値は写さない。
    --setting-sources (前が同じ別の旗) は今までどおり通す。"""
    def unexpected(*args, **kwargs):
        pytest.fail("--settings を断る時は何も起こさない")

    monkeypatch.setattr(L, "launch", unexpected)
    with pytest.raises(L.LaunchError, match="--settings"):
        L.parse_args(["--large", "--", "--continue", *extra])
    assert L.main(["--", "--continue", *extra]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "--settings" in captured.err and "my.json" not in captured.err and "{}" not in captured.err
    args = L.parse_args(["--", "--setting-sources", "project,local", "--continue"])
    assert args.claude_args == ["--setting-sources", "project,local", "--continue"]


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
    # --print-only は頁を開かない = 見る頁が要る時は板を手で起こす (日英)。残した板は --stop で止める。
    assert "頁は開かない" in result.stdout and "Opens no page" in result.stdout
    assert result.stdout.count("python board/server.py") == 2
    assert "止めるには --stop" in result.stdout and "stop it with --stop" in result.stdout
    assert "Stop this repository's board" in result.stdout
    # 使い回しは記録の年齢でなく、認証付きの照会で決める
    assert "24 時間" not in result.stdout and "24 hours" not in result.stdout
    assert "認証付きの照会に答えれば" in result.stdout and "answers an authenticated check" in result.stdout


def test_help_runs_under_isolated_and_safepath_modes(tmp_path):
    """script の dir を sys.path に置かない起こし方 (-I・3.11 からの -P と PYTHONSAFEPATH=1) でも、隣の hooks を読んで
    --help まで届く (1 巡目 #2 = blemma.py だけが自分の dir を足さず、板も claude も起きる前に import で落ちた)。
    -I は PYTHON* の環境変数を見ないので、どの形も環境変数を外し、-X utf8 で同じ文字コードにして比べる。"""
    script = str(REPO / "blemma.py")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}

    def help_of(*flags, **extra):
        return subprocess.run([sys.executable, *flags, "-X", "utf8", "-B", script, "--help"], cwd=tmp_path,
                              capture_output=True, encoding="utf-8", env={**env, **extra}, timeout=30)

    plain = help_of()
    assert plain.returncode == 0 and plain.stderr == "" and "Launch the board" in plain.stdout
    runs = {"-I": help_of("-I")}
    if sys.version_info >= (3, 11):                 # -P と PYTHONSAFEPATH は 3.11 から (3.10 は -I だけで確かめる)
        runs["-P"] = help_of("-P")
        runs["PYTHONSAFEPATH=1"] = help_of(PYTHONSAFEPATH="1")
    for name, result in runs.items():
        assert (result.returncode, result.stderr, result.stdout) == (0, "", plain.stdout), name


def test_old_python_stops_before_the_board_and_window(tmp_path):
    """3.10 未満なら、ほかの import より前に日英 1 行ずつで止まる。版を 3.7 に差し替えて、blemma.py だけを置いた
    写しで走らせる (hooks も board も無い = 確かめが import の後ろにずれると ImportError で落ちる)。file 全体が
    3.7 の文法で読める = 3.7〜3.9 で起こしても、構文の誤りにならずに案内まで届く (1 巡目 #35)。"""
    source = (REPO / "blemma.py").read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 7))   # 3.7 で起こしても、構文の誤りにならずに確かめの行へ届く
    docstring, future, imported, check = tree.body[:4]
    assert isinstance(docstring, ast.Expr) and isinstance(future, ast.ImportFrom) and future.module == "__future__"
    assert isinstance(imported, ast.Import) and [alias.name for alias in imported.names] == ["sys"]
    assert isinstance(check, ast.If) and ast.unparse(check.test) == "sys.version_info < (3, 10)"
    copy = tmp_path / "blemma 写し"
    copy.mkdir()
    shutil.copy2(REPO / "blemma.py", copy / "blemma.py")
    code = ("import runpy, sys; sys.version_info = (3, 7, 17, 'final', 0); "
            "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')")
    result = subprocess.run([sys.executable, "-B", "-c", code, str(copy / "blemma.py"), "--large", "--port",
                             str(unused_port()), "--", "日本語の頼み"], cwd=copy, capture_output=True,
                            encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.splitlines() == [
        "BLEMMA: Python 3.10 以上で実行してください (今の版は 3.7)",
        "BLEMMA: Python 3.10 or later is required (this is 3.7)",
    ]
    assert sorted(path.name for path in copy.iterdir()) == ["blemma.py"]   # board/state も窓の profile も作らない


def test_set_names_an_unknown_key_and_takes_a_bare_key(monkeypatch, capsys):
    """--set の打ち間違いは黙って捨てず、鍵の名だけを出して止める。`=` の無い鍵は空の値 (頁の既定) で通す。
    BLEMMA_OPTS の知らない鍵は今までどおり黙って捨てる。"""
    monkeypatch.setenv("BLEMMA_OPTS", "dwel=1&theme=dark")
    args = L.parse_args(["--set", "scan", "--set", "desc"])
    assert args.page_options == {"theme": "dark", "scan": "", "desc": ""}

    def unexpected(*args, **kwargs):
        pytest.fail("設定の誤りでは何も起こさない")

    monkeypatch.setattr(L, "launch", unexpected)
    for key in ("dwel", "Dwell", "x" * 24, "no_such-key9"):
        assert L.main(["--set", f"{key}=1"]) == 1
        assert capsys.readouterr() == (
            "", f"BLEMMA: 頁の設定の名を確認してください: {key} (--help) / Unknown page option: {key}\n")
    # 字の形が鍵らしくない時は名を写さない (頼みの文・秘密・長い文字列)
    for assignment in ("日本語の頼み=1", "x" * 25 + "=1", "a b=1", "secret/value=1", "=1", "", "dwell\n=1"):
        assert L.main(["--set", assignment]) == 1
        captured = capsys.readouterr()
        assert captured == ("", "BLEMMA: 引数を確認してください (--help) / Invalid arguments (see --help)\n")


def test_set_and_opts_values_outside_the_page_ranges_are_refused(monkeypatch, capsys):
    """dwell・scan・key は、頁が範囲の外で黙って既定 (切・Space) へ戻す値なら、板も窓も開く前に止める (1 巡目 #6・#24 =
    scan=12 は走査なし・key=PageDown は Space に黙って戻った)。頁と同じ決まり = dwell は 10 を、scan は 20 を超える値を
    ms と読む。--set が BLEMMA_OPTS に勝つ。値は短い英数の形の時だけ写す (頼みの文や秘密を写さない)。"""
    def unexpected(*args, **kwargs):
        pytest.fail("値の誤りでは何も起こさない")

    monkeypatch.setattr(L, "launch", unexpected)
    for bad in ("scan=12", "scan=0.4", "scan=25", "dwell=6", "dwell=0.2", "dwell=1e3", "key=PageDown", "key=Home"):
        assert L.main(["--set", bad]) == 1
        out, err = capsys.readouterr()
        assert out == "" and len(err.splitlines()) == 1, bad
        assert err.startswith(f"BLEMMA: 頁の設定の値を確認してください: {bad} (") and f"page option value: {bad} (" in err
    for bad, shown in (("dwell", "dwell"), ("key=日本語の頼み", "key")):      # 空の値・鍵らしくない値は名だけ
        assert L.main(["--set", bad]) == 1
        err = capsys.readouterr().err
        assert err.startswith(f"BLEMMA: 頁の設定の値を確認してください: {shown} (") and "日本語" not in err
    monkeypatch.setenv("BLEMMA_OPTS", "theme=dark&scan=25")
    assert L.main([]) == 1 and "scan=25 (" in capsys.readouterr().err
    assert L.parse_args(["--set", "scan=1"]).page_options == {"theme": "dark", "scan": "1"}   # --set が勝つ
    monkeypatch.delenv("BLEMMA_OPTS")
    for good in ("scan=1.5", "scan=off", "scan=0", "scan=true", "scan=1500", "dwell=0", "dwell=1", "dwell=300",
                 "key=F13", "key=Space", "key=a", "key=KeyQ", "key=Numpad0", "key=ArrowLeft", "key= "):
        key, _, value = good.partition("=")
        assert L.parse_args(["--set", good]).page_options == {key: value}, good


@pytest.mark.parametrize("name,flag,value", [
    ("BLEMMA_WINDOW_SIZE", "--window-size", "640x"), ("BLEMMA_WINDOW_SIZE", "--window-size", ""),
    ("BLEMMA_WINDOW_POSITION", "--window-position", "秘密の値"), ("BLEMMA_WINDOW_POSITION", "--window-position", ""),
])
def test_bad_geometry_environment_names_the_variable(monkeypatch, capsys, name, flag, value):
    """引数を何も打っていないのに「引数を確認」と出さない。変数の名だけを出し、値は写さない。引数が勝つ。"""
    monkeypatch.setenv(name, value)

    def unexpected(*args, **kwargs):
        pytest.fail("環境変数の誤りでは何も起こさない")

    monkeypatch.setattr(L, "launch", unexpected)
    assert L.main([]) == 1
    assert capsys.readouterr() == (
        "", f"BLEMMA: 環境変数 {name} の値を確認してください (--help) / Invalid {name} (see --help)\n")
    args = L.parse_args([flag, "30,40"])
    assert (args.window_size if flag == "--window-size" else args.window_position) == (30, 40)


def test_missing_claude_stops_before_board_and_window(isolated_repo, sessions, monkeypatch, capsys):
    # Exercise shutil.which itself with an empty executable search path.
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(isolated_repo)
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    opened = []
    monkeypatch.setattr(L.webbrowser, "open", lambda url: opened.append(url) or True)
    assert L.find_claude() is None
    assert L.main(["--large", "--keep-board", "--port", str(unused_port()), "--", "日本語の頼み"]) == 1
    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    assert captured.out == "" and len(lines) == 2 and all(line.startswith("BLEMMA: ") for line in lines)
    assert "claude が見つかりません" in lines[0] and "claude was not found" in lines[1]
    # 別の端末の道 = 頁を開く板を手で起こし、--print-only の 1 行を使う。--print-only は頁を開かないので、
    # --keep-board で残した板には見る頁が無い (30 秒の後の札は no_viewer で全部端末へ戻る)。
    assert all("python board/server.py" in line and "python blemma.py --print-only" in line for line in lines)
    assert "Ctrl+C" in lines[0] and "Ctrl+C" in lines[1] and "--keep-board" not in captured.err
    # 板の server は起こした端末を塞ぐ = --print-only を打つ所は Claude Code の端末と書く (README の行と同じ)
    assert "Claude Code を起こす端末で python blemma.py --print-only" in lines[0]
    assert "in the terminal for Claude Code, run python blemma.py --print-only" in lines[1]
    assert "日本語の頼み" not in captured.err and "#t=" not in captured.err
    assert opened == [] and sessions == []
    assert not (isolated_repo / "board" / "state").exists()
    # 案内の通りに打つ。手で起こした板 (頁は server が開く・試験では開かない) を、claude が無くても --print-only が使い
    # 回し、起動の行を出し、終わっても板を止めない。
    board = subprocess.Popen([L.python_executable(), str(isolated_repo / "board" / "server.py"),
                              "--no-browser", "--port", str(unused_port())],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while (info := run_info(isolated_repo)) is None or not L.board_responds(info):
            assert board.poll() is None and time.monotonic() < deadline, "手で起こした板が立たない"
            time.sleep(0.05)
        assert L.main(["--large", "--print-only", "--port", str(unused_port()), "--", "日本語の頼み"]) == 0
        captured = capsys.readouterr()
        assert len(captured.out.splitlines()) == 1 and captured.err == ""
        assert "claude" in captured.out and "--permission-mode" in captured.out and "日本語の頼み" in captured.out
        assert "#t=" not in captured.out and opened == [] and sessions[0].process is None
        assert L.board_responds(info) and board.poll() is None and client_files(isolated_repo) == []
    finally:
        L.stop_process(board)


@pytest.mark.parametrize("keep", [False, True])
def test_print_only_prepares_real_board_without_claude(isolated_repo, sessions, monkeypatch, capsys, keep):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "_which", lambda name: "claude.exe" if name == "claude" else None)
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


def test_print_only_refuses_to_write_a_mangled_command(isolated_repo, sessions, monkeypatch):
    """--print-only の 1 行を pipe や file へ向けた時 (Windows は ANSI の code page = 日本語の Windows は cp932) に、書けない字
    (é など) を ? に替えた命令を黙って出さず、理由つきの 1 行で止まる (2 巡目 i29)。stream は main の harden_streams が
    errors="replace" に替える本物の道を通す。書ける行 (日本語の頼み) は今までどおり出る。"""
    import io
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "_which", lambda name: "claude.exe" if name == "claude" else None)
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)

    def print_only(prompt):
        out, err = io.BytesIO(), io.BytesIO()
        for name, raw in (("stdout", out), ("stderr", err)):
            monkeypatch.setattr(sys, name, io.TextIOWrapper(raw, encoding="cp932", errors="strict", write_through=True))
        code = L.main(["--large", "--print-only", "--port", str(unused_port()), "--", prompt])
        return code, out.getvalue(), err.getvalue().decode("cp932")

    code, out, err = print_only("café の案を 3 つ")
    assert code == 1 and out == b"" and b"caf?" not in out
    assert len(err.splitlines()) == 1 and "console に表示して" in err and "print it to the console" in err
    assert "caf" not in err                                    # 頼みの文は写さない
    code, out, err = print_only("日本語の案を 3 つ")
    assert code == 0 and err == ""
    assert len(out.splitlines()) == 1 and "日本語の案を 3 つ" in out.decode("cp932")
    assert len(sessions) == 2 and all(session.process.poll() is not None for session in sessions)


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


def test_close_survives_a_permission_error_on_run_json(isolated_repo, sessions, monkeypatch, capsys):
    """Windows では、別の process (名簿の外の回の hook・別の --print-only の read_run) が run.json を開いている一瞬に、
    unlink が PermissionError になる。後始末 (close) はそれで止まらない = Claude Code の終わりの値を返し、名簿の後始末
    (自分の名乗りと板の印の消し) も最後まで走る (2 巡目 i33・前は「起動処理に失敗しました」・exit 1 で、印が残った)。"""
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
    monkeypatch.setattr(L, "open_board", lambda *args, **kwargs: None)
    monkeypatch.setattr(L, "run_claude", lambda command: 0)
    original = Path.unlink
    refused = []

    def unlink_in_use(self, missing_ok=False):
        if self.name == "run.json" and not refused:        # 最初の 1 回だけ = 試験の後始末では消せる
            refused.append(self)
            raise PermissionError(13, "in use")
        return original(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink_in_use)
    assert L.main(["--port", str(unused_port())]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "起動処理に失敗しました" not in captured.err
    assert len(refused) == 1                                  # 消せない道を通った
    assert sessions[0].process.poll() is not None              # 自分が起こした板は止まった
    assert client_files(isolated_repo) == []                   # 名乗りと板の印も消えた = 後始末が途中で止まらない


def test_run_record_shape_is_checked_but_not_its_age(tmp_path):
    path = tmp_path / "run.json"
    good = {"port": 8765, "token": "test-placeholder", "pid": 123,
            "started": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(good), encoding="utf-8")
    assert L.read_run(path) == L.RunInfo(8765, "test-placeholder", 123, good["started"])
    # 年齢では捨てない = 使い回すかは token つきの照会が決める (1 日を越えて動く板・時計が戻った後の記録)
    old = time.time() - 3 * 24 * 60 * 60
    for started in ("2000-01-01T00:00:00+00:00", (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()):
        path.write_text(json.dumps({**good, "started": started}), encoding="utf-8")
        os.utime(path, (old, old))
        assert L.read_run(path) == L.RunInfo(8765, "test-placeholder", 123, started)
    for patch in ({"port": True}, {"port": 65536}, {"pid": 0}, {"pid": "123"}, {"token": "bad\r\nheader"},
                  {"token": ""}, {"started": "bad"}, {"started": 0}, {"started": "2026-11-06T12:00:00"}):
        path.write_text(json.dumps({**good, **patch}), encoding="utf-8")
        assert L.read_run(path) is None, patch
    for raw in ("[1]", "null", "broken", "{}"):
        path.write_text(raw, encoding="utf-8")
        assert L.read_run(path) is None


@pytest.mark.parametrize("shift", [-25 * 60 * 60, 2 * 60 * 60])   # 1 日を越えて動いた板 / 時計が戻った (記録が先)
def test_answering_board_is_reused_whatever_the_record_age(isolated_repo, sessions, monkeypatch, shift):
    """年齢で記録を捨てると、生きている板を照会しないまま同じ port に新しい板を起こし、「板を起動できません」で
    終わる。答える板は、記録の started と mtime がいつでも使い回す。"""
    first = L.ensure_board(isolated_repo, unused_port())
    data = json.loads(first.run_file.read_text(encoding="utf-8"))
    when = time.time() + shift
    data["started"] = datetime.fromtimestamp(when, timezone.utc).isoformat()
    first.run_file.write_text(json.dumps(data), encoding="utf-8")
    os.utime(first.run_file, (when, when))

    def unexpected_start(*args, **kwargs):
        pytest.fail("答える板があるのに、同じ port に新しい板を起こした")

    monkeypatch.setattr(L.subprocess, "Popen", unexpected_start)
    reused = L.ensure_board(isolated_repo, first.info.port)
    assert reused.process is None and reused.info.started == data["started"]
    assert (reused.info.port, reused.info.pid, reused.info.token) == (first.info.port, first.info.pid, first.info.token)


def test_occupied_port_stops_before_browser_or_claude(isolated_repo, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")  # PATH に claude が無い機械でも同じ経路を通す
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


def test_wildcard_listener_on_the_port_stops_before_browser_or_claude(isolated_repo, monkeypatch, capsys):
    """0.0.0.0 で待つ相手 (同じ利用者の別のプログラム) の port でも、板を起こさずに止まる (1 巡目 #16 = Windows では板が
    起き、相手の 127.0.0.1 の客を奪った)。README の「板を起動できません (ポート・配置を確認)」の行がそのまま当たる。"""
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")

    def unexpected(*args, **kwargs):
        pytest.fail("板が起きて、窓か claude まで進んだ")

    monkeypatch.setattr(L, "open_board", unexpected)
    monkeypatch.setattr(L, "run_claude", unexpected)
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
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
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
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
        # Claude の間だけ、使い手の登録 (pid と始めた時刻) と、起こし方が起こした板の印がある。
        names = client_files(isolated_repo)
        mine = [name for name in names if name.startswith(f"client-{os.getpid()}-")]
        assert len(names) == 2 and len(mine) == 1 and f"board-{sessions[0].info.pid}.json" in names
        record = json.loads((isolated_repo / "board" / "state" / "clients" / mine[0]).read_text(encoding="utf-8"))
        assert record["pid"] == os.getpid() and datetime.fromisoformat(record["started"]).tzinfo is not None
        commands.append(command)
        return 17

    monkeypatch.setattr(L, "run_claude", pretend_claude)
    assert L.main(["--large", "--port", str(unused_port()), "--", "頼み"]) == 17
    assert len(commands) == 1 and commands[0][-1] == "頼み"
    assert sessions[0].process.poll() is not None and not sessions[0].run_file.exists()
    assert client_files(isolated_repo) == []
    assert capsys.readouterr() == ("", "")


def test_children_do_not_inherit_the_callers_cwd(isolated_repo, sessions, monkeypatch, tmp_path):
    """Claude Code は起こした端末の作業フォルダーで動く (上の試験) が、板と小窓のブラウザはそれを cwd に継がない
    (2 巡目 i31)。Windows では cwd にしている process が居る間、そのフォルダーの改名・削除が「使用中」で失敗する
    (--keep-board で残した板が、最初に起こしたフォルダーを掴み続けた)。"""
    caller = tmp_path / "作業 フォルダー"
    caller.mkdir()
    monkeypatch.chdir(caller)
    original = L.subprocess.Popen
    started = []

    def record(*args, **kwargs):
        started.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(L.subprocess, "Popen", record)
    session = L.ensure_board(isolated_repo, unused_port())
    assert session.process is not None and len(started) == 1
    assert started[0].get("cwd") == str(isolated_repo.resolve())
    opened = []
    monkeypatch.setattr(L.subprocess, "Popen", lambda command, **kwargs: opened.append(kwargs))
    monkeypatch.setattr(L, "find_app_browser", lambda: "chrome")
    monkeypatch.setattr(L, "work_area", lambda: (0, 0, 1920, 1080))
    L.open_board(L.RunInfo(18770, "test-placeholder", 123), "small", (640, 720), None)
    assert len(opened) == 1 and opened[0].get("cwd") == str(L.ROOT)


def test_config_write_failure_stops_before_claude(isolated_repo, sessions, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
    monkeypatch.setattr(L.webbrowser, "open", lambda url: True)
    (isolated_repo / "board" / "state" / "settings.generated.json").mkdir(parents=True)
    assert L.main(["--large", "--keep-board", "--port", str(unused_port())]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert "起動処理に失敗" in captured.err and "Launch failed" in captured.err
    assert sessions[0].process.poll() is not None and not sessions[0].run_file.exists()
    assert not list((isolated_repo / "board" / "state").glob("*.tmp"))


@pytest.mark.parametrize("first", ["starter", "reuser"])
def test_shared_board_lives_until_the_last_launcher_ends(isolated_repo, sessions, launchers, first):
    launchers.start("starter")
    info = run_info(isolated_repo)
    launchers.start("reuser")
    assert sessions[0].process is not None and sessions[1].process is None   # 2 つ目は使い回し
    names = client_files(isolated_repo)
    assert len(names) == 3 and f"board-{info.pid}.json" in names            # 使い手 2 つと印
    launchers.end(first)
    assert L.board_responds(info)            # 残った回の Claude Code は、まだ扇から答えを受けられる
    launchers.end("reuser" if first == "starter" else "starter")
    assert not L.board_responds(info, timeout=0.05) and sessions[0].process.poll() is not None
    assert not sessions[0].run_file.exists() and client_files(isolated_repo) == []


def test_second_launcher_does_not_open_another_page(isolated_repo, sessions, launchers, monkeypatch, capsys):
    """使い回した板に見る頁がもう在る時は、頁をもう 1 枚開かない (同じ板の窓が 2 枚になると、固定と透過が効かない)。
    見る頁が無い板を使い回す時は、今までどおり開く。"""
    import http.client
    opened = []
    monkeypatch.setattr(L.webbrowser, "open", lambda url: opened.append(url) or True)
    launchers.start("starter")
    info = run_info(isolated_repo)
    assert len(opened) == 1 and not L.board_has_page(info)       # 板を起こした回は開く (偽のブラウザ = 頁はまだ無い)
    launchers.start("no-page")
    assert len(opened) == 2                                      # 見る頁の無い板を使い回す = 開く
    headers = {"X-Blemma-Token": info.token}
    first = http.client.HTTPConnection("127.0.0.1", info.port, timeout=3)
    first.request("GET", "/pending?seq=-1", headers=headers)
    seq = json.loads(first.getresponse().read())["seq"]
    first.close()
    page = http.client.HTTPConnection("127.0.0.1", info.port, timeout=3)
    page.request("GET", f"/pending?seq={seq}", headers=headers)  # 頁の代わりの見張り = 返事を読まず、開いたまま
    try:
        assert L.board_has_page(info)
        launchers.start("with-page")
        assert len(opened) == 2 and sessions[2].process is None  # 開かない
    finally:
        page.close()
    assert "扇は既に開いています" in capsys.readouterr().err


def test_page_probe_failure_means_no_page(probe_server):
    """頁の照会に板が答えない・この口を持たない古い板 (404) の時は「頁は無い」= 今までどおり窓を開く側に倒す。"""
    old_board = probe_server()                        # どの GET にも 404 を返す = /page の口が無い板
    assert L.board_has_page(old_board) is False
    with socket.socket() as listener:                 # 誰も聞いていない port
        listener.bind(("127.0.0.1", 0))
        dead = L.RunInfo(listener.getsockname()[1], "test-placeholder", os.getpid())
    assert L.board_has_page(dead, timeout=0.2) is False


def test_dead_launchers_registration_does_not_keep_the_board(isolated_repo, sessions, launchers):
    # 名乗ったまま後始末をせずに消えた起こし方 (端末の窓ごと閉じた時など) を、本物の別 process で作る。
    code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import blemma; "
            "blemma.Clients(Path(sys.argv[2])).join()")
    dead = subprocess.Popen([L.python_executable(), "-c", code, str(REPO), str(isolated_repo / "board" / "state")])
    assert dead.wait(10) == 0   # Popen が handle を持つ間、Windows はこの pid を別の process に使わない
    leftover = client_files(isolated_repo)
    assert len(leftover) == 1 and leftover[0].startswith(f"client-{dead.pid}-")
    launchers.start("only")
    info = run_info(isolated_repo)
    launchers.end("only")
    assert not L.board_responds(info, timeout=0.05) and sessions[0].process.poll() is not None
    assert client_files(isolated_repo) == []


def test_hand_started_board_is_left_running(isolated_repo, sessions, launchers):
    board = subprocess.Popen([L.python_executable(), str(isolated_repo / "board" / "server.py"),
                              "--no-browser", "--port", str(unused_port())],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while (info := run_info(isolated_repo)) is None or not L.board_responds(info):
            assert board.poll() is None and time.monotonic() < deadline, "手で起こした板が立たない"
            time.sleep(0.05)
        launchers.start("guest")
        assert sessions[0].process is None   # 手で起こした板を使い回した
        launchers.end("guest")
        assert L.board_responds(info) and board.poll() is None
        assert client_files(isolated_repo) == []
    finally:
        L.stop_process(board)


def test_kept_board_is_not_stopped_by_a_later_launcher(isolated_repo, sessions, launchers):
    launchers.start("keeper", "--keep-board")
    info = run_info(isolated_repo)
    launchers.end("keeper")
    assert L.board_responds(info) and client_files(isolated_repo) == []   # 印も消えた = 残すと決めた板
    launchers.start("later")
    assert sessions[1].process is None
    launchers.end("later")
    assert L.board_responds(info) and sessions[0].process.poll() is None
    assert client_files(isolated_repo) == []


@pytest.mark.parametrize("first", ["winner", "loser"])
def test_simultaneous_start_loser_does_not_orphan_the_board(isolated_repo, sessions, launchers, monkeypatch, first):
    """板の無い所から 2 つをほぼ同時に起こした形を、実の ensure_board で作る。負けた側は勝った板の run.json を
    見る前に自分の板を起こし (port を取れずに終わる)、自分の起動より後に書かれた run.json を見て、勝った板を
    自分の板と取り違える。取り違えた側が最後に終わっても、板を止める (印だけ消して板を残さない)。"""
    launchers.start("winner")
    info = run_info(isolated_repo)
    original = L.read_run
    blind = []

    def before_the_winner_wrote(path):
        if not blind:                      # 負けた側の 1 回目の照会 = 勝った板の run.json はまだ無かった
            blind.append(path)
            os.utime(path)                 # 勝った板はその直後 (負けた側の起動の 1 秒の内) に書いた
            return None
        return original(path)

    monkeypatch.setattr(L, "read_run", before_the_winner_wrote)
    launchers.start("loser")
    loser = sessions[1]
    assert blind and loser.process is not None and loser.info == info
    assert loser.process.wait(10) != 0     # 負けた側の子は板ではない (port は勝った板が持つ)
    launchers.end(first)
    assert L.board_responds(info)          # 残った回の Claude Code は、まだ扇から答えを受けられる
    launchers.end("loser" if first == "winner" else "winner")
    assert not L.board_responds(info, timeout=0.05) and sessions[0].process.poll() is not None
    assert not sessions[0].run_file.exists() and client_files(isolated_repo) == []


def test_marker_stays_until_the_board_is_stopped(isolated_repo, sessions, launchers, monkeypatch):
    """使い回した板を止められなかった時 (別の利用者・管理者の権限で動く板など) は印を残し、後の回が止める。"""
    launchers.start("starter")
    info = run_info(isolated_repo)
    launchers.start("reuser")
    launchers.end("starter")
    real_stop = L.stop_reused_board
    attempts = []
    monkeypatch.setattr(L, "stop_reused_board", attempts.append)    # 止めに失敗した = 板は答え続ける
    launchers.end("reuser")
    assert len(attempts) == 1 and L.board_responds(info)
    assert client_files(isolated_repo) == [f"board-{info.pid}.json"]
    monkeypatch.setattr(L, "stop_reused_board", real_stop)
    launchers.start("later")
    assert sessions[2].process is None
    launchers.end("later")
    assert not L.board_responds(info, timeout=0.05) and sessions[0].process.poll() is not None
    assert not sessions[0].run_file.exists() and client_files(isolated_repo) == []


def test_two_launchers_writing_the_same_marker_keep_the_roster(isolated_repo, sessions):
    """取り違えた 2 つは同じ印を同時に書く。2 thread で本当に同時に書く (差し替え無しの os.replace)。一時の名が
    同じだと互いの一時 file を消し合い、Windows は同じ file への置き換えが重なると PermissionError を返す
    (どちらも名簿を捨てて、今までの動きに戻る)。作り手の機械 (Windows) では、直す前は書き 600 回のうち 358 回、
    一時の名を分けるだけでは書き 2000 回のうち 78〜150 回が落ちた = 100 回 (書き 200 回) で直しの抜けを捕まえる。"""
    board = L.ensure_board(isolated_repo, unused_port())
    marker = f"board-{board.info.pid}.json"
    failed = 0
    for number in range(100):
        state = isolated_repo / "board" / "state" / f"race-{number}"
        pair = [L.Clients(state), L.Clients(state)]
        barrier = threading.Barrier(2)

        def write(clients):
            barrier.wait(10)
            clients.mark(board)

        threads = [threading.Thread(target=write, args=(clients,)) for clients in pair]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        failed += sum(not clients.ok for clients in pair)
        assert sorted(path.name for path in (state / "clients").iterdir()) == [marker]   # 一時 file も残らない
        assert json.loads((state / "clients" / marker).read_text(encoding="utf-8")) == {
            "pid": board.info.pid, "port": board.info.port, "started": board.info.started}
    assert failed == 0


STOPPED = "BLEMMA: 板を止めました / Board stopped\n"
NO_BOARD = "BLEMMA: 動いている板はありません / No board is running\n"


def forbid_starting_anything(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("--stop は板も窓も Claude も起こさない")

    for owner, name in ((L.subprocess, "Popen"), (L.webbrowser, "open"), (L, "find_claude"), (L, "launch")):
        monkeypatch.setattr(owner, name, unexpected)


def test_stop_stops_a_kept_board(isolated_repo, sessions, launchers, monkeypatch, capsys):
    """--keep-board で残した板には、止める道が要る。--stop は照会に答える板を止め、2 回目は「ありません」で 0。"""
    launchers.start("keeper", "--keep-board")
    info = run_info(isolated_repo)
    launchers.end("keeper")
    assert L.board_responds(info) and client_files(isolated_repo) == []
    forbid_starting_anything(monkeypatch)
    capsys.readouterr()
    assert L.main(["--stop"]) == 0
    assert capsys.readouterr() == (STOPPED, "")
    sessions[0].process.wait(10)
    assert not L.board_responds(info, timeout=0.05) and not sessions[0].run_file.exists()
    assert L.main(["--stop"]) == 0
    assert capsys.readouterr() == (NO_BOARD, "")


def test_stop_while_a_launcher_runs_clears_the_marker(isolated_repo, sessions, launchers, monkeypatch, capsys):
    """Claude Code の回が使っている間に --stop = 板を止め、起こし方の印も片づける。その回の hook は板なしの動き
    (いつもの確認) に戻るだけ。その回が終わる時も何も壊さず、名簿は空になる。"""
    launchers.start("running")
    info = run_info(isolated_repo)
    assert f"board-{info.pid}.json" in client_files(isolated_repo)
    capsys.readouterr()
    assert L.main(["--stop"]) == 0
    assert capsys.readouterr() == (STOPPED, "")
    assert not L.board_responds(info, timeout=0.05)
    names = client_files(isolated_repo)
    assert len(names) == 1 and names[0].startswith(f"client-{os.getpid()}-")   # 走っている回の名乗りだけが残る
    launchers.end("running")
    sessions[0].process.wait(10)
    assert client_files(isolated_repo) == []


def test_a_board_started_after_stop_does_not_outlive_its_users(isolated_repo, sessions, launchers, capsys):
    """回 A が走っている間に --stop → 別の回 B が新しい板を起こす → B が先に終わる (A が居るので板を残す) → A が終わる。
    最後の使い手の A が、今の run.json の板 (B が起こした・印つき) を止める = 誰も使わない板が残らない。"""
    launchers.start("a")
    first = run_info(isolated_repo)
    capsys.readouterr()
    assert L.main(["--stop"]) == 0
    assert capsys.readouterr() == (STOPPED, "")
    assert not L.board_responds(first, timeout=0.05)
    launchers.start("b")
    second = run_info(isolated_repo)
    assert second.pid != first.pid and L.board_responds(second)
    launchers.end("b")
    assert L.board_responds(second) and f"board-{second.pid}.json" in client_files(isolated_repo)   # A が居る = 残す
    launchers.end("a")
    sessions[1].process.wait(10)
    assert not L.board_responds(second, timeout=0.05)
    assert client_files(isolated_repo) == [] and not sessions[1].run_file.exists()


def test_the_last_user_leaves_a_hand_started_board_alone(isolated_repo, sessions, launchers, capsys):
    """上と同じ順でも、止めた後の板が手で起こした物 (印が無い) なら、最後の使い手は止めない (手で起こした板は手で止める)。"""
    launchers.start("a")
    capsys.readouterr()
    assert L.main(["--stop"]) == 0
    capsys.readouterr()
    by_hand = L.ensure_board(isolated_repo, launchers.port)       # 印を置かない = 手で起こした板と同じ
    launchers.end("a")
    assert by_hand.process.poll() is None and L.board_responds(by_hand.info)


def test_stop_needs_the_token_answer(isolated_repo, sessions, monkeypatch, capsys):
    """run.json の token で照会に答えない板は止めない (別の鍵の板・同じ port の別の server)。"""
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    board = L.ensure_board(isolated_repo, unused_port())
    genuine = board.run_file.read_text(encoding="utf-8")
    board.run_file.write_text(json.dumps({**json.loads(genuine), "token": "other-test-placeholder"}), encoding="utf-8")
    try:
        assert L.main(["--stop"]) == 0
        assert capsys.readouterr() == (NO_BOARD, "")
        assert board.process.poll() is None and L.board_responds(board.info)
    finally:
        board.run_file.write_text(genuine, encoding="utf-8")


def test_stop_without_a_board_touches_nothing(isolated_repo, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    forbid_starting_anything(monkeypatch)
    assert L.main(["--stop"]) == 0
    assert capsys.readouterr() == (NO_BOARD, "")
    assert not (isolated_repo / "board" / "state").exists()


def test_stop_is_used_alone(isolated_repo, sessions, monkeypatch, capsys):
    """--stop と起こす旗・-- の後の引数を混ぜたら、何も止めず・何も起こさず、引数の誤りの 1 行で 1 を返す。"""
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    board = L.ensure_board(isolated_repo, unused_port())
    forbid_starting_anything(monkeypatch)
    for extra in (["--print-only"], ["--keep-board"], ["--port", "8765"], ["--large"], ["--small"], ["--demo"],
                  ["--set", "theme=dark"], ["--window-size", "640,720"], ["--window-position", "0,0"],
                  ["--"], ["--", "日本語の頼み"]):
        assert L.main(["--stop", *extra]) == 1, extra
        captured = capsys.readouterr()
        assert captured.out == "" and len(captured.err.splitlines()) == 1, extra
        assert "引数を確認" in captured.err and "Invalid arguments" in captured.err
        assert "日本語の頼み" not in captured.err
    assert board.process.poll() is None and L.board_responds(board.info) and len(sessions) == 1


def test_stop_failure_keeps_the_marker(isolated_repo, sessions, launchers, monkeypatch, capsys):
    """止められなかった板 (別の利用者・管理者の権限で動く板など) は 1 を返し、印を残す = 最後の回が止める。"""
    launchers.start("running")
    info = run_info(isolated_repo)
    monkeypatch.setattr(L, "stop_reused_board", lambda session: None)
    capsys.readouterr()
    assert L.main(["--stop"]) == 1
    assert capsys.readouterr() == ("", "BLEMMA: 板を止められませんでした / Could not stop the board\n")
    assert L.board_responds(info) and f"board-{info.pid}.json" in client_files(isolated_repo)
    launchers.end("running")
    assert not L.board_responds(info, timeout=0.05) and sessions[0].process.poll() is not None
    assert client_files(isolated_repo) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows executable suffixes")
@pytest.mark.parametrize("name", ["claude.cmd", "claude.exe"])
def test_windows_claude_suffix_lookup(monkeypatch, name):
    monkeypatch.setattr(L, "_which", lambda candidate: name if candidate == name else None)
    assert L.find_claude() == name


def test_the_lookup_never_runs_a_claude_or_browser_placed_in_the_working_folder(tmp_path, monkeypatch):
    """claude とブラウザは PATH の絶対の dir だけで探す。起こした所 (cwd)・PATH の空の欄・相対の dir に置かれた
    claude.cmd や chrome.cmd は拾わない = 信頼していない repo で起こしても、そこの file を Claude Code の信頼の確認より前に
    実行しない (Python の点検 BL-PY-02 の再現 = Windows の shutil.which は cwd を先に探した)。"""
    windows = os.name == "nt"
    repo, bin_dir = tmp_path / "untrusted", tmp_path / "bin"
    repo.mkdir(); bin_dir.mkdir()
    def plant(folder, name):
        path = folder / (name + (".cmd" if windows else ""))
        path.write_text("@echo off\n" if windows else "#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        return path
    for name in ("claude", "chrome"):
        plant(repo, name)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)   # shutil.which なら cwd を探す条件
    seen = {}
    for path_value in ("", os.pathsep, ".", "untrusted", os.pathsep.join(["", ".", "untrusted"])):
        monkeypatch.setenv("PATH", path_value)
        seen[path_value] = (L._which("claude"), L._which("chrome"))
    assert all(found == (None, None) for found in seen.values()), seen
    real = os.path.normcase(str(plant(bin_dir, "claude")))   # Windows の名は大小を区別しない (拡張子は PATHEXT の綴りで返る)
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(bin_dir)]))
    assert os.path.normcase(L._which("claude") or "") == real
    assert os.path.normcase(L.find_claude() or "") == real
    if windows:                                    # 拡張子の無い file (npm の sh の写し) は Windows では拾わない
        (bin_dir / "chrome").write_text("#!/bin/sh\n", encoding="utf-8")
        assert L._which("chrome") is None
        assert os.path.normcase(L._which("claude.cmd") or "") == real


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
    assert command[0] == "test-browser" and command[2:4] == ["--window-size=480,360", "--window-position=1440,680"]
    assert any(arg.startswith("--user-data-dir=") for arg in command)
    url = urlsplit(command[1].removeprefix("--app="))
    assert url.hostname == "127.0.0.1" and url.port == 8765
    assert parse_qs(url.query) == {"mode": ["small"]} and url.fragment == "t=test-placeholder"
    L.open_board(L.RunInfo(8765, "test-placeholder", 123), "small", (600, 400), (-20, 10))
    assert "--window-position=-20,10" in commands[1]


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


@pytest.mark.skipif(os.name != "nt" or not (shutil.which("pwsh") or shutil.which("powershell")),
                    reason="PowerShell に貼る 1 行の試験 (Windows だけ)")
def test_the_printed_powershell_line_keeps_full_width_quotes_inside_the_argument(tmp_path):
    """--print-only の PowerShell の 1 行は、全角の二重引用符 (U+201C・U+201D・U+201E) も文字列の中に留める = 引数のまま
    子へ渡り、続きが命令として走らない (Python の点検 BL-PY-06 の再現 = 全角の閉じ引用で文字列が終わり、続きが走った)。"""
    marker = tmp_path / "ran.txt"
    left, right, low = chr(0x201C), chr(0x201D), chr(0x201E)
    args = [f"a{right}; New-Item -ItemType File '{marker}'; {left}b", f"{low}x{right}", "plain"]
    line = L.format_command([sys.executable, "-c", "import sys; print(ascii(sys.argv[1:]))", *args])
    shell = shutil.which("pwsh") or shutil.which("powershell")
    # 外部アプリの起動の番 (no_external_apps) は Python の子だけを通す = PowerShell は、その Python の子から起こす
    relay = ("import subprocess, sys\n"
             "r = subprocess.run(sys.argv[1:], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)\n"
             "print(r.stdout, end=''); print(r.stderr, end='', file=sys.stderr)\n")
    done = subprocess.run([sys.executable, "-c", relay, shell, "-NoProfile", "-NonInteractive", "-Command", line],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert not marker.exists(), done.stdout + done.stderr
    assert done.stdout.strip() == ascii(args), done.stdout + done.stderr


def test_command_line_stays_on_one_line():
    line = L.format_command(["claude", "空白 と '引用'", "$value`", "line1\nline2\r"])
    assert len(line.splitlines()) == 1
    if os.name == "nt":
        assert line.startswith('& "claude" ') and "`$value``" in line and "`n" in line
    else:
        assert line.startswith("claude ") and "\\n" in line


def test_the_roster_lock_covers_joining_and_the_last_users_stop(isolated_repo, monkeypatch):
    """名乗り (join) と、最後の使い手の「ほかの使い手を数える → 板を止める」(leave) は、同じ錠 (clients/.lock) の中で行う
    = A が 0 人と数えた直後に B が名乗って板を使い回し、その後で A が板を止める隙間が無い (外の目の 8 巡目)。錠は終わると消える。"""
    state = isolated_repo / "board" / "state"
    lock = state / "clients" / ".lock"
    a = L.Clients(state)
    seen = {}
    monkeypatch.setattr(a, "_write", lambda path, data: seen.__setitem__("join_locked", lock.exists()) or True)
    a.join()
    assert seen == {"join_locked": True} and not lock.exists()
    a.me = state / "clients" / f"client-{os.getpid()}-deadbeef.json"
    monkeypatch.setattr(a, "_others", lambda: seen.__setitem__("count_locked", lock.exists()) or 0)
    monkeypatch.setattr(a, "_stop_used", lambda session: seen.__setitem__("stop_locked", lock.exists()))
    a.leave(L.BoardSession(state / "run.json", L.RunInfo(1, "t", 1)), keep=False)
    assert seen == {"join_locked": True, "count_locked": True, "stop_locked": True} and not lock.exists()


def test_a_held_roster_lock_delays_the_stop_and_a_stale_lock_is_broken(isolated_repo, monkeypatch):
    """別の回が錠を持っている間は、最後の使い手の止めは待つ (錠が外れてから止める)。持ち主の記録 (pid) の無い錠は、
    LOCK_STALE を過ぎた時だけ、後始末なしに消えた回の古い錠として壊して進む (外の目の 9 巡目の後 = pid の在る錠は
    pid の生死だけで決める・下の試験。この試験の錠は平文なので、記録の無い錠の枝を通る)。"""
    state = isolated_repo / "board" / "state"
    (state / "clients").mkdir(parents=True)
    lock = state / "clients" / ".lock"
    a = L.Clients(state)
    order = []
    monkeypatch.setattr(a, "_others", lambda: 0)
    monkeypatch.setattr(a, "_stop_used", lambda session: order.append("stop"))
    lock.write_text("held", encoding="utf-8")                           # 別の回が錠を持っている

    def release():
        time.sleep(0.5)
        order.append("release")
        lock.unlink()
    threading.Thread(target=release, daemon=True).start()
    a.leave(L.BoardSession(state / "run.json", L.RunInfo(1, "t", 1)), keep=False)
    assert order == ["release", "stop"] and not lock.exists()
    lock.write_text("stale", encoding="utf-8")                          # 持ち主が死んで残った古い錠
    old = time.time() - L.LOCK_STALE - 5
    os.utime(lock, (old, old))
    started = time.monotonic()
    a.leave(L.BoardSession(state / "run.json", L.RunInfo(1, "t", 1)), keep=False)
    assert order == ["release", "stop", "stop"] and time.monotonic() - started < 2 and not lock.exists()


HOLD_LOCK = ("import os, sys\n"
             "from pathlib import Path\n"
             "sys.path.insert(0, sys.argv[1])\n"
             "import blemma\n"
             "with blemma.Clients(Path(sys.argv[2]))._lock():\n"
             "    print('held', flush=True)\n"
             "    if sys.argv[3] == 'die':\n"
             "        os._exit(0)\n"
             "    sys.stdin.read()\n")


@contextlib.contextmanager
def roster_lock_held(state, how="hold"):
    """別の起こし方 (実の python の process) が、本物の _lock で名簿の錠を取る。hold = 錠を持ったまま止まっている
    (stdin を閉じると外して終わる)・die = 錠の中で後始末なしに消えた (錠の file が残る)。python は本体 (venv の転送役は
    孫を起こすので、錠に書かれる pid と child.pid が合わない)。"""
    child = subprocess.Popen([L.python_executable(), "-I", "-c", HOLD_LOCK, str(REPO), str(state), how],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        assert child.stdout.readline().strip() == "held"
        if how == "die":
            child.wait(10)
        yield child
    finally:
        if child.poll() is None:
            child.stdin.close()
            child.wait(10)
        child.stdout.close()


def test_a_launcher_that_cannot_take_the_roster_lock_starts_nothing(isolated_repo, monkeypatch, capsys):
    """名簿の錠が待ち時間 (LOCK_WAIT) の内に取れない起こし方は、名乗らずに止まる = 板も窓も Claude Code も起こさず、
    理由を日英 1 行ずつ出して戻り値 1 (外の目の 9 巡目 = 錠を待ち切ると錠なしで名乗り、人数を数え終えて止める直前の
    別の回の板を使い回した。その回が再開すると、使い中の板を止めた)。持ち主の錠には触らない。"""
    state = isolated_repo / "board" / "state"
    monkeypatch.setattr(L, "ROOT", isolated_repo)
    monkeypatch.setattr(L, "find_claude", lambda: "claude")
    monkeypatch.setattr(L, "LOCK_WAIT", 0.3)

    def unexpected(*args, **kwargs):
        pytest.fail("名簿の錠が無いまま、板・窓・claude へ進んだ")

    for name in ("ensure_board", "open_board", "run_claude"):
        monkeypatch.setattr(L, name, unexpected)
    with roster_lock_held(state) as holder:
        record = (state / "clients" / ".lock").read_text(encoding="utf-8")
        assert L.main(["--port", str(unused_port())]) == 1
        assert client_files(isolated_repo) == [".lock"]                       # 名乗っていない
        assert (state / "clients" / ".lock").read_text(encoding="utf-8") == record
        assert holder.poll() is None
    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    assert captured.out == "" and len(lines) == 2, captured.err
    assert lines[0].startswith("BLEMMA: 名簿の錠が取れません") and lines[1].startswith("BLEMMA: Could not lock")
    assert not (state / "run.json").exists()


def test_a_last_user_that_cannot_take_the_roster_lock_leaves_the_board_running(isolated_repo, sessions, monkeypatch,
                                                                              capsys):
    """終わる側も、名簿の錠が取れない時は数えも止めもしない = 板は止めずに残し (印も残す = 次の起こし方の後始末か
    --stop が止める)、理由を stderr に 1 行出す。錠を持つ回が名乗りや数えの途中の間に、錠なしで板を止めない。
    止めの道は実物 (_stop_used・実の子の板)。自分の登録は消す (数を減らすだけ = 錠なしでも誰の板も止めない)。"""
    state = isolated_repo / "board" / "state"
    monkeypatch.setattr(L, "LOCK_WAIT", 0.3)
    session = L.ensure_board(isolated_repo, unused_port())                      # 自分が起こした板 (実の子 process)
    a = L.Clients(state)
    a.join()
    a.mark(session)
    stops = []
    real_stop = a._stop_used
    monkeypatch.setattr(a, "_stop_used", lambda board: stops.append(board) or real_stop(board))
    with roster_lock_held(state):
        a.leave(session, keep=False)
        assert stops == []
        assert session.process.poll() is None and L.board_responds(session.info)   # 板は動いたまま
        assert client_files(isolated_repo) == [".lock", f"board-{session.info.pid}.json"]
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and "名簿の錠が取れない" in err[0] and "python blemma.py --stop" in err[0], err


def test_a_live_holders_roster_lock_is_never_broken_but_a_dead_holders_lock_is(isolated_repo, monkeypatch):
    """古い錠の回収は経過時間だけで決めない = 錠に持ち主の pid を書き、生きている pid の錠は LOCK_STALE (60 秒) を
    過ぎても奪わない (止まっているだけの持ち主の名簿の区間に割り込まない)。pid が死んだ錠 (錠の中で後始末なしに消えた
    回) は、待たずに回収して進む。記録の無い錠の決まり (60 秒) は上の試験。実の持ち主 (錠を開いたまま) は、Windows では
    OS も消させない (共有の決まり・実測) = 誰も開いていない錠の段が、pid の決まりそのものを見る。"""
    state = isolated_repo / "board" / "state"
    lock = state / "clients" / ".lock"
    a = L.Clients(state)
    monkeypatch.setattr(L, "LOCK_WAIT", 0.5)
    old = time.time() - L.LOCK_STALE - 5
    with roster_lock_held(state) as holder:
        os.utime(lock, (old, old))
        with pytest.raises(L.LaunchError, match="名簿の錠が取れません"):
            a.join()
        assert a.me is None and json.loads(lock.read_text(encoding="utf-8"))["pid"] == holder.pid
    assert not lock.exists()                                                    # 持ち主が外した
    record = json.dumps({"pid": os.getpid(), "at": "2026-11-08T00:00:00+09:00"})
    lock.write_text(record, encoding="utf-8")                                   # 生きている pid・誰も開いていない錠
    os.utime(lock, (old, old))
    if os.name == "nt":
        # Windows = 持ち主が開いたままの錠は OS が消させないので、生きている pid でも 60 秒を過ぎた錠は回収する
        # (kill された回の pid の使い回しで止まり続けない)。若い錠 (60 秒の内) は pid が生きていれば奪わない。
        b = L.Clients(state)
        b.join()
        assert b.me is not None and b.me.exists() and not lock.exists()
        lock.write_text(record, encoding="utf-8")
        with pytest.raises(L.LaunchError, match="名簿の錠が取れません"):
            L.Clients(state).join()
        assert lock.read_text(encoding="utf-8") == record
    else:
        with pytest.raises(L.LaunchError, match="名簿の錠が取れません"):
            a.join()
        assert a.me is None and lock.read_text(encoding="utf-8") == record
    lock.unlink()
    monkeypatch.setattr(L, "LOCK_WAIT", 3.0)
    with roster_lock_held(state, "die") as dead:
        assert lock.exists() and not L.pid_alive(dead.pid)
        started = time.monotonic()
        a.join()
        assert time.monotonic() - started < 2 and a.me is not None and a.me.exists() and not lock.exists()


def test_hardened_streams_do_not_raise_on_a_console_that_cannot_write_japanese():
    """英語の Windows の console (cp1252) のように日本語を書けない stream でも、案内の行で落ちない = 書けない字は ? になる。
    文字コードは変えない (日本語の console はそのまま読める)。付け替えられない stream は放っておく。"""
    import io
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="\n")
    with pytest.raises(UnicodeEncodeError):
        print("BLEMMA: 板を開きました", file=stream)
    L.harden_streams(stream, object())                                   # 2 つ目 = reconfigure の無い物も通る
    print("BLEMMA: 板 / board", file=stream, flush=True)
    assert raw.getvalue() == b"BLEMMA: ? / board\n" and stream.encoding == "cp1252"
