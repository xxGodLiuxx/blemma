#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA を 1 行で起こす / Launch BLEMMA with one command (Python 3.10+)."""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    # 板も窓も起こす前に止める。古い python (3.7 から) でもこの行まで届くよう、file 全体を 3.7 の文法で書く
    # (walrus・match・位置専用引数を置かない)。版は tuple でも読める形で取る。
    _VERSION = "%d.%d" % tuple(sys.version_info[:2])
    sys.stderr.write("BLEMMA: Python 3.10 以上で実行してください (今の版は %s)\n"
                     "BLEMMA: Python 3.10 or later is required (this is %s)\n" % (_VERSION, _VERSION))
    sys.exit(1)

import argparse
import contextlib
import http.client
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import tempfile
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I・-P・PYTHONSAFEPATH=1 でも隣の hooks を読む
from hooks._client import _Connection as _DeadlineConnection

ROOT = Path(__file__).resolve().parent
START_TIMEOUT = 10.0
STOP_PROBE = 2.0                 # --stop の照会の期限 (人が打つ口なので、起動の照会の 0.3 秒より長く待ってよい)
STATUS_MESSAGE = "BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board"
HOOKS = (
    # (イベント, matcher, script, timeout, 板の答えを待つか = spinner の行に STATUS_MESSAGE を出すか)
    ("PermissionRequest", ".*", "permission.py", 600, True),
    ("PreToolUse", "AskUserQuestion", "ask.py", 600, True),
    ("Elicitation", ".*", "elicitation.py", 600, True),
    # 通知は 1 回送るだけで待たない = 「待っています」と出すと、札が無いのに嘘になる
    ("Notification", "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
     "notify.py", 10, False),
    ("UserPromptSubmit", None, "state.py", 5, False),
    ("Stop", None, "state.py", 5, False),
)
PAGE_KEYS = frozenset(("dwell", "scan", "key", "lang", "sound", "mode", "scale", "font", "theme", "desc", "trail", "click", "face", "pos", "clear"))
PAGE_KEY_SHAPE = re.compile(r"[A-Za-z0-9_-]{1,24}")   # 誤りの文に名を出してよい鍵の形 (頼みの文や秘密を写さない)
# 頁の parseOptions (board/static/board_core.js) が範囲の外で黙って既定 (切・Space) へ戻す 3 つの鍵は、起こす前に値も確かめる
PAGE_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]*)?|\.[0-9]+")          # 頁と同じ数の形 (符号・指数は読まない)
PAGE_SWITCH_KEYS = re.compile(r"[A-Za-z0-9]|Space|Enter|NumpadEnter|Tab|Escape|Backspace|Arrow(?:Left|Right|Up|Down)"
                              r"|F(?:[1-9]|1[0-9]|2[0-4])|Key[A-Z]|Digit[0-9]|Numpad[0-9]")   # 頁の key の一覧と同じ
PAGE_VALUE_SHAPE = re.compile(r"[A-Za-z0-9._-]{1,24}")             # 誤りの文に写してよい値の形
PAGE_RANGES = {
    "dwell": ("0 か 0.3〜5 秒", "0 or 0.3-5 seconds"),
    "scan": ("off か 0.5〜10 秒", "off or 0.5-10 seconds"),
    "key": ("Space・Enter・F13 などの鍵の名 = board/README.md", "a key name such as Space, Enter or F13; see board/README.md"),
}
UNSET = object()                 # 旗を打っていない印 (--window-position の None は「右下」という読めた値)
CLAUDE_MISSING = (
    # 第 2 の道は頁を開く板を手で起こす (--print-only は頁を開かないので、--keep-board で残した板には見る頁が無い)。
    "claude が見つかりません (claude が shell の alias だけで動く端末でも、こう出ます。その時は次の手順を使います)。"
    "Claude Code が使える端末で、もう一度 python blemma.py を実行してください。"
    "別の端末で Claude Code を起こす時は、python board/server.py で板を起こし (頁が開きます・Ctrl+C で止まります・"
    "開くのは大きな板 = 扇にするなら住所の # より前に ?mode=small を足す)、"
    "Claude Code を起こす端末で python blemma.py --print-only を実行して、(Windows では PowerShell で) 表示された 1 行を打ってください。\n"
    "claude was not found (this also happens when claude is only a shell alias; use the steps below). "
    "Run python blemma.py again in a terminal where Claude Code is available. "
    "To start Claude Code in another terminal, start the board with python board/server.py "
    "(it opens the large board; add ?mode=small before the # in the address for the fan; Ctrl+C stops it), then in the terminal for Claude Code, "
    "run python blemma.py --print-only and run the printed line (PowerShell on Windows).")

PAGE_OPEN = ("BLEMMA: 扇は既に開いています。この端末の確認も同じ扇に出ます "
             "(見当たらない時は、開いている板の頁を閉じてから起こし直してください)。"
             "設定 (--set・BLEMMA_OPTS・--large/--small・窓の大きさと位置) は、開いている扇のままです "
             "(変える時は、扇の窓を閉じてから設定を付けて起こし直すか、窓の歯車で替えます。歯車はキーかクリックで押します) / "
             "The fan is already open; prompts from this terminal appear there too "
             "(if you cannot find it, close the open board page and start again). "
             "Settings (--set, BLEMMA_OPTS, --large/--small, window size and position) stay as the open fan has them "
             "(to change them, close the fan window and start again with the new settings, or use the gear in the window; "
             "press the gear with a key or a click)")


class LaunchError(Exception):
    """利用者へ出せる、秘密を含まない英日の文 (ふつうは 1 行・main が行ごとに BLEMMA: を付ける)。"""


def page_value_ok(key: str, value: str) -> bool:
    """頁が受ける値か (頁の parseOptions と同じ決まり = dwell は 10 を、scan は 20 を超える値を ms と読む)。
    dwell・scan・key の外は頁が確かめる (範囲の外は頁の既定へ戻る)。"""
    if key == "key":
        return value == " " or PAGE_SWITCH_KEYS.fullmatch(value) is not None
    if key not in ("dwell", "scan"):
        return True
    if key == "scan" and value in ("", "on", "true", "off", "false"):
        return True
    if not PAGE_NUMBER.fullmatch(value):
        return False
    seconds = float(value)
    if seconds > (10 if key == "dwell" else 20):
        seconds /= 1000
    low, high = (0.3, 5) if key == "dwell" else (0.5, 10)
    return seconds == 0 or low <= seconds <= high


def page_options(environment: str, assignments: list[str]) -> dict[str, str]:
    """Only display keys enter the URL. dwell, scan and key values are checked here (the page would fall back
    silently); the page parser validates the rest.
    BLEMMA_OPTS の知らない鍵は黙って捨てる。--set の知らない鍵は止める (打ち間違いを黙って効かなくしない)。
    dwell・scan・key の値が頁の範囲の外なら、--set でも BLEMMA_OPTS でも止める (--set が勝った後の値で見る)。"""
    options = {k: v for k, v in parse_qsl(environment, keep_blank_values=True) if k in PAGE_KEYS}
    for assignment in assignments:
        key, _, value = assignment.partition("=")   # `=` の無い物 (例 scan) は空の値 = 頁の決まりの既定 (scan は 1.5 秒)
        if key not in PAGE_KEYS:
            if PAGE_KEY_SHAPE.fullmatch(key):
                raise LaunchError(f"頁の設定の名を確認してください: {key} (--help) / Unknown page option: {key}")
            raise LaunchError("引数を確認してください (--help) / Invalid arguments (see --help)")
        options[key] = value
    for key, (ja, en) in PAGE_RANGES.items():
        value = options.get(key)
        if value is not None and not page_value_ok(key, value):
            shown = f"{key}={value}" if PAGE_VALUE_SHAPE.fullmatch(value) else key
            raise LaunchError(f"頁の設定の値を確認してください: {shown} ({ja}) / Invalid page option value: {shown} ({en})")
    return options


def environment_value(name: str, convert, fallback: str):
    """環境変数の窓の寸法・位置を読む。読めない (空を含む) 時は変数の名だけを出す (値は写さない)。"""
    value = os.environ.get(name)
    try:
        return convert(fallback if value is None else value)
    except ValueError:
        raise LaunchError(f"環境変数 {name} の値を確認してください (--help) / Invalid {name} (see --help)") from None


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's original message can echo a private prompt or an environment value.
        raise LaunchError("引数を確認してください (--help) / Invalid arguments (see --help)")


def size_value(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"[0-9]+[,xX][0-9]+", value):
        raise ValueError("expected WIDTH,HEIGHT")
    width, height = (int(v) for v in re.split("[,xX]", value))
    if width <= 0 or height <= 0:
        raise ValueError("expected positive dimensions")
    return width, height


def position_value(value: str) -> tuple[int, int] | None:
    if value == "bottom-right":
        return None
    if not re.fullmatch(r"-?[0-9]+,-?[0-9]+", value):
        raise ValueError("expected X,Y")
    x, y = (int(v) for v in value.split(","))
    return x, y


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    split = argv.index("--") if "--" in argv else len(argv)
    parser = Parser(
        prog="python blemma.py", allow_abbrev=False, add_help=False,
        formatter_class=argparse.RawTextHelpFormatter,
        description="板と Claude Code を起こします (通信は 127.0.0.1 のみ)。\n"
                    "Launch the board and Claude Code (board traffic stays on 127.0.0.1).",
        epilog="-- 以後の引数は Claude Code にそのまま渡します。\n"
               "Arguments after -- are passed unchanged to Claude Code.\n"
               "在処の記録 (board/state/run.json) の板が認証付きの照会に答えれば、その板を再利用します。\n"
               "Reuse the board in board/state/run.json when it answers an authenticated check.\n"
               "画面の寸法が取得できない時は既定のブラウザで開きます (位置の指定で小窓を使えます・画面の無い Linux では開けないので --print-only を)。\n"
               "Use the default browser if display geometry is unavailable (set a position for app mode; a Linux box without a display cannot open it: use --print-only).")
    parser.add_argument("-h", "--help", action="help", help="使い方を表示\nShow this help")
    parser.add_argument("--demo", action="store_true", help="個人の設定・MCP を混ぜない\nUse project/local settings and only BLEMMA MCP")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--small", dest="mode", action="store_const", const="small",
                      help="小窓 (既定)\nSmall app window (default)")
    mode.add_argument("--large", dest="mode", action="store_const", const="large",
                      help="既定のブラウザで開く\nOpen in the default browser")
    parser.set_defaults(mode=None)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="頁の設定 (繰り返し可・BLEMMA_OPTS より優先)\nPage option (repeatable; overrides BLEMMA_OPTS)")
    parser.add_argument("--port", type=int, default=None, metavar="PORT",
                        help="新しく起こす板のポート (既定 8765)\nPort for a new board (default: 8765)")
    parser.add_argument("--keep-board", action="store_true",
                        help="終了後 (--print-only なら表示の後) も板を残す (止めるには --stop)\n"
                             "Keep the board after Claude exits or --print-only prints (stop it with --stop)")
    parser.add_argument("--print-only", action="store_true",
                        help="板と設定を用意し、Claude の起動行だけ表示。頁は開かない\n"
                             "(見る頁が要る時は、先に python board/server.py で板を起こす)\n"
                             "Prepare the board and configs and print the Claude command. Opens no page\n"
                             "(for a page, start the board first with python board/server.py)")
    parser.add_argument("--stop", action="store_true",
                        help="この repo の板が照会に答えれば止める (ほかの旗と一緒には使わない)\n"
                             "Stop this repository's board if it answers (use alone)")
    parser.add_argument("--window-size", type=size_value, default=UNSET, metavar="W,H",
                        help="小窓の幅,高さ (BLEMMA_WINDOW_SIZE・既定 640,720)\n"
                             "Window size (BLEMMA_WINDOW_SIZE; default: 640,720)")
    parser.add_argument("--window-position", type=position_value, default=UNSET, metavar="X,Y",
                        help="小窓の位置 (BLEMMA_WINDOW_POSITION・既定 右下)\n"
                             "Window position (BLEMMA_WINDOW_POSITION; default: bottom-right)")
    args = parser.parse_args(argv[:split])
    if args.stop:
        # 止める口は単独で使う = 起こす旗や -- の後の引数と混ぜたら、何も止めず・何も起こさずに断る
        if (args.demo or args.mode or args.set or args.port is not None or args.keep_board or args.print_only
                or args.window_size is not UNSET or args.window_position is not UNSET or split < len(argv)):
            parser.error("--stop")
        return args
    args.port = 8765 if args.port is None else args.port
    if not 1 <= args.port <= 65535:
        parser.error("port")
    if args.window_size is UNSET:
        args.window_size = environment_value("BLEMMA_WINDOW_SIZE", size_value, "640,720")
    if args.window_position is UNSET:
        args.window_position = environment_value("BLEMMA_WINDOW_POSITION", position_value, "bottom-right")
    args.page_options = page_options(os.environ.get("BLEMMA_OPTS", ""), args.set)
    option_mode = args.page_options.pop("mode", "small")
    args.mode = args.mode or (option_mode if option_mode in ("small", "large") else "small")
    args.claude_args = argv[split + 1:]
    # Claude Code の --settings は値を 1 つだけ持ち、後に出た物が勝つ = -- の後ろに渡すと、生成した設定 (hooks 6 本と
    # ask_board の許可) が丸ごと外れ、扇に札が来ないまま端末だけで動く。黙って効かなくせず断る。値は写さない (頼みの文を
    # 含みうる)。判定は語の完全一致と --settings= の前置だけ = 頼みの文の 1 語や --setting-sources には当たらない。
    if any(value == "--settings" or value.startswith("--settings=") for value in args.claude_args):
        raise LaunchError("--settings は -- の後ろに渡せません (BLEMMA の設定と置き換わります)。"
                          "hooks などは .claude/settings.json に書いてください / "
                          "--settings cannot follow -- (it would replace BLEMMA's settings); "
                          "put hooks in .claude/settings.json")
    return args


def settings_data(root: Path) -> dict:
    root = root.resolve()
    return {
        "permissions": {"allow": ["mcp__blemma__ask_board"]},
        "hooks": {
            event: [{**({"matcher": matcher} if matcher else {}), "hooks": [{
                "type": "command", "command": python_executable(),
                "args": ["-I", str(root / "hooks" / name)], "timeout": timeout,
                **({"statusMessage": STATUS_MESSAGE} if waits else {}),
            }]}] for event, matcher, name, timeout, waits in HOOKS
        },
    }


def write_configs(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    state = root / "board" / "state"
    state.mkdir(parents=True, exist_ok=True)
    paths = (state / "settings.generated.json", state / "mcp.generated.json")
    mcp = {"mcpServers": {"blemma": {
        "command": python_executable(), "args": ["-I", str(root / "mcp" / "blemma_mcp.py")],
    }}}
    for path, data in zip(paths, (settings_data(root), mcp)):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=state, prefix=path.name + ".", suffix=".tmp",
                                             delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return paths



def python_executable() -> str:
    """子の process (板の server・hook・MCP server) を起こす python。
    venv の python.exe (Windows) は本体の interpreter を孫として起こす転送役なので、run.json の pid が子と合わず、
    hook の起動も 1 段遅い。_base_executable が在ればそれ (本体) を使う。
    子はどれも -I で起こす = 利用者の PYTHONPATH・PYTHONHOME・user site に標準と同じ名の module があっても負けない
    (3 つとも自分の dir を sys.path に足して隣の file を読むので、-I でも動く)。
    Use the base interpreter when running inside a venv (the Windows venv redirector spawns a grandchild)."""
    base = getattr(sys, "_base_executable", None)
    if base and Path(base).is_file():
        return str(base)
    return sys.executable


@dataclass(frozen=True)
class RunInfo:
    port: int
    token: str = field(repr=False)
    pid: int
    started: str = ""                  # run.json の started = 同じ pid を使い回した別の板と見分ける


def read_run(path: Path) -> RunInfo | None:
    """在処の記録の形だけを見る (port・pid・token の字・started が時刻として読める事)。年齢では捨てない =
    1 日を越えて動いている板や時計が戻った後の板も、使い回すかは token つきの照会 (board_responds) が決める。
    年齢で捨てると、生きている板を見ないまま同じ port に新しい板を起こし、起動ごと失敗する。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        port, token, pid = data["port"], data["token"], data["pid"]
        started = datetime.fromisoformat(data["started"])
        if (type(port) is not int or not 1 <= port <= 65535 or
                type(pid) is not int or pid <= 0 or not isinstance(token, str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", token) or started.tzinfo is None):
            return None
        return RunInfo(port, token, pid, data["started"])
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def board_responds(info: RunInfo, timeout: float = 0.3, *, deadline: float | None = None) -> bool:
    # A TCP listener alone is not enough. This authenticated request neither creates
    # a card nor marks a browser as present. HTTPConnection ignores proxy variables.
    attempt_deadline = time.monotonic() + timeout
    if deadline is not None:
        attempt_deadline = min(attempt_deadline, deadline)
    connection = _DeadlineConnection(info.port, attempt_deadline)
    try:
        connection.request("GET", "/wait?id=blemma-launcher-probe",
                           headers={"X-Blemma-Token": info.token})
        response = connection.getresponse()
        ready = response.status == 404 and json.loads(response.read(4096)) == {"error": "unknown"}
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()
    return ready and time.monotonic() < attempt_deadline


def board_has_page(info: RunInfo, timeout: float = 0.3) -> bool:
    """その板を見ている頁がもう在るか (GET /page)。答えない時と、この口を持たない古い板は「無い」= 今までどおり窓を開く。"""
    connection = _DeadlineConnection(info.port, time.monotonic() + timeout)
    try:
        connection.request("GET", "/page", headers={"X-Blemma-Token": info.token})
        response = connection.getresponse()
        return response.status == 200 and json.loads(response.read(4096)) == {"open": True}
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


@dataclass
class BoardSession:
    run_file: Path
    info: RunInfo | None = None
    process: subprocess.Popen | None = None

    def close(self) -> None:
        if self.process is None:
            return                         # An existing board belongs to its caller.
        stop_process(self.process)
        # TerminateProcess on Windows cannot run the server's finally/atexit cleanup.
        # 消せない時 (Windows で別の process が run.json を開いている一瞬の PermissionError など) も止まらない =
        # stop_reused_board と同じ扱い。残った run.json の pid は死んでいるので、後の回は使い回さずに上書きする。
        try:
            data = json.loads(self.run_file.read_text(encoding="utf-8"))
            if (isinstance(data, dict) and data.get("pid") == self.process.pid and
                    (self.info is None or data.get("token") == self.info.token)):
                self.run_file.unlink()
        except (OSError, ValueError):      # FileNotFoundError・PermissionError は OSError、UnicodeError は ValueError の子
            pass


def background_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}



def _written_after(path: Path, when: float) -> bool:
    try:
        return path.stat().st_mtime >= when
    except OSError:
        return False


def _check_start_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise LaunchError("板の起動が時間切れです (最長 10 秒) / Board startup timed out (up to 10 seconds)")


def ensure_board(root: Path, port: int, timeout: float = START_TIMEOUT) -> BoardSession:
    deadline = time.monotonic() + timeout
    root = root.resolve()
    run_file = root / "board" / "state" / "run.json"
    session = BoardSession(run_file)
    try:
        info = read_run(run_file)
        if info is not None and board_responds(info, deadline=deadline):
            session.info = info
            _check_start_deadline(deadline)
            return session
        _check_start_deadline(deadline)
        launched = time.time() - 1.0  # run.json がこの時刻より後なら、自分が起こした板 (pid が転送役で合わない時)
        # cwd は置き場 = 起こした端末の作業フォルダーを継がない (板は全部の路を自分の置き場から組む。Windows では cwd に
        # している process が居る間、そのフォルダーの改名・削除が「使用中」で失敗する = --keep-board の板が掴み続けた)。
        session.process = subprocess.Popen(
            [python_executable(), "-I", str(root / "board" / "server.py"), "--no-browser", "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(root),
            **background_options())
        while True:
            _check_start_deadline(deadline)
            if session.process.poll() is not None:
                raise LaunchError("板を起動できません (ポート・配置を確認) / Board server exited during startup")
            info = read_run(run_file)
            if (info is not None and info.port == port and
                    (info.pid == session.process.pid or _written_after(run_file, launched)) and
                    board_responds(info, deadline=deadline)):
                session.info = info
                _check_start_deadline(deadline)
                return session
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    except BaseException:
        session.close()
        raise


def pid_alive(pid: int) -> bool:
    """その pid の process が在るか (終わり切っていないか)。分からない時は True (ほかの回の板を止めるより、板が残る方が安全)。"""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel32.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
            if not handle:
                return ctypes.get_last_error() != 87            # ERROR_INVALID_PARAMETER = その pid の process は無い
            try:
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259:
                    return True                                 # 読めない・STILL_ACTIVE
                # 終わりの値は TerminateProcess の直後から付く。handle が signaled (終わり切る) までは在ると見る。
                return kernel32.WaitForSingleObject(handle, 0) == 0x102     # WAIT_TIMEOUT
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return True
    try:
        os.kill(pid, 0)                    # 届けずに在るかだけを見る (Windows の 0 は Ctrl+C の便なので使わない)
    except ProcessLookupError:
        return False
    except Exception:
        return True                        # PermissionError = 在るが別の利用者の process
    return True


def run_matches(run_file: Path, info: RunInfo) -> bool:
    """run.json が今もこの板 (pid と token) を指すか。1 日を越えて動いた板も止められるよう、年齢は見ない。"""
    try:
        data = json.loads(run_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("pid") == info.pid and data.get("token") == info.token


def stop_reused_board(session: BoardSession) -> None:
    """使い回した板を pid で止める (照合は呼び手)。Windows の os.kill は TerminateProcess になる。"""
    info = session.info

    def running() -> bool:
        # Windows は process の終わりまで待つ (TerminateProcess は終わりを待たずに返る)。POSIX は
        # 答えなくなるまで (終わった子の pid は、親が回収するまで残る)。
        return pid_alive(info.pid) and (os.name == "nt" or board_responds(info, timeout=0.2))

    try:
        os.kill(info.pid, signal.SIGTERM)
    except (OSError, OverflowError):
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and running():
        time.sleep(0.05)
    if os.name != "nt" and running():
        try:
            os.kill(info.pid, signal.SIGKILL)
        except OSError:
            pass
    if run_matches(session.run_file, info):   # TerminateProcess では板の後始末 (finally・atexit) が走らない
        try:
            session.run_file.unlink(missing_ok=True)
        except OSError:
            pass


CLIENT_FILE = re.compile(r"client-([0-9]{1,10})-[0-9a-f]{8}\.json")
LOCK_WAIT = 15.0     # 名簿の錠 (clients/.lock) を待つ最長 (秒)。待ち切れない時は守る区間に入らない (起こす側は止まり、終わる側は板を残す)
LOCK_STALE = 60.0    # 持ち主の記録 (pid) の無い錠を、後始末なしに消えた回の物として回収するまでの秒 (pid の在る錠は pid の生死だけで決める)
ROSTER_BUSY = (
    "名簿の錠が取れません。別の端末の blemma.py が起動か終わりの途中です。少し待ってから起こし直してください "
    "(ほかに blemma.py が動いていないのに 1 分を過ぎても続く時は、board/state/clients/.lock を消します)。\n"
    "Could not lock the launcher list: another blemma.py is starting or ending. Wait a moment and start again "
    "(if no other blemma.py is running and this lasts over a minute, delete board/state/clients/.lock).")
ROSTER_LEFT = ("BLEMMA: 名簿の錠が取れないため、板を止めずに残しました (止める時は python blemma.py --stop) / "
               "Could not lock the launcher list, so the board was left running (stop it with python blemma.py --stop)")


class Clients:
    """同じ置き場の板を使う起こし方の名簿 (board/state/clients/)。

    Claude を起こす回は 1 file で名乗る (名 = pid と乱数・中身 = pid と始めた時刻)。板を起こした回は
    「起こし方が起こした板」の印 board-<板の pid>.json を置く (手で起こした板には無い)。最後の使い手が、
    印のある板だけを止める。名簿の読み書きに失敗した回は、今までの動き (自分が起こした板だけを止める) に戻る。
    名簿の錠が取れない回は、名乗らずに止まる (起こす側)・板を止めずに残す (終わる側)。
    Launchers sharing one board register here; the last one stops only a launcher-started board."""

    def __init__(self, state: Path) -> None:
        self.dir = state / "clients"
        self.me: Path | None = None
        self.ok = True                     # False = 名簿を使わず、今までの動き

    @contextlib.contextmanager
    def _lock(self):
        """名簿の錠 (clients/.lock) = 名乗り (join) と、最後の使い手の「ほかの使い手を数える → 板を止める」(leave) を互いに
        割り込ませない (外の目の 8 巡目 = A が 0 人と数えた直後に B が名乗って板を使い回し、その後で A が板を止めた)。
        錠は file の作成の原子性 (O_EXCL) で取り、持ち主の pid と時刻を書く。取れない時は LOCK_WAIT まで待ち、待ち切れたら
        取れなかった事 (False) を渡す = 呼び手は守る区間に入らない (9 巡目 = 錠なしで進むと、数え終えて止める直前の回の板を
        使い回せた)。古い錠の回収は経過時間だけで決めない (_stale)。"""
        path = self.dir / ".lock"
        fd = None
        deadline = time.monotonic() + LOCK_WAIT
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            while True:
                try:
                    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except (FileExistsError, PermissionError):
                    # PermissionError = Windows で、別の回が開いている間に消された錠 (消える途中) = 在る錠と同じく待つ
                    if self._stale(path):
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass           # 別の回が開いている一瞬 (Windows) = 次の回で
                        else:
                            continue
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
        except OSError:
            fd = None
        try:
            if fd is not None:
                try:
                    os.write(fd, json.dumps({"pid": os.getpid(), "at": datetime.now().astimezone().isoformat(
                        timespec="seconds")}).encode("utf-8"))
                except OSError:
                    pass                   # 記録の無い錠も錠 (ほかの回は LOCK_STALE を過ぎるまで待つ)
            yield fd is not None
        finally:
            if fd is not None:
                self._unlock(path, fd)

    @staticmethod
    def _stale(path: Path) -> bool:
        """回収してよい古い錠か。持ち主の pid が書いてあれば、その生死だけで決める = 生きている pid の錠は、どれだけ古くても
        奪わない (止まっているだけの持ち主の名簿の区間に割り込まない・外の目の 9 巡目)。記録の無い錠 (作った直後でまだ
        書いていない・書けなかった・消せずに残った・前の版の錠) は、LOCK_STALE を過ぎた時だけ。読めない時は回収しない。"""
        try:
            age = time.time() - path.stat().st_mtime
            raw = path.read_bytes()
        except OSError:
            return False
        try:
            pid = json.loads(raw.decode("utf-8")).get("pid")
        except (ValueError, AttributeError, RecursionError):
            pid = None
        if type(pid) is int and 0 < pid < 2 ** 31:
            if not pid_alive(pid):
                return True
            # Windows = 持ち主が開いたままの錠は OS が消させない (共有の決まり) ので、生きている pid の錠でも LOCK_STALE を
            # 過ぎたら回収を試みる = kill された回の pid を別の process が使い回しても 1 分で外れる (生きている持ち主の錠は
            # 消せずに「在る錠」として待つ)。POSIX は pid の生死だけ = 消せてしまうので、古さでは奪わない
            return os.name == "nt" and age > LOCK_STALE
        return age > LOCK_STALE

    @staticmethod
    def _unlock(path: Path, fd: int) -> None:
        # 記録を先に空にする = 消せずに残った錠も、記録の無い錠として LOCK_STALE で回収される (空にしないと、生きている
        # この process の pid のまま残り、回の終わりまで、ほかの起こし方が待ち切って止まる)。
        try:
            os.ftruncate(fd, 0)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        for _ in range(20):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:        # Windows = 別の回が錠の記録を読んでいる一瞬 (_write の置き換えと同じ扱い)
                time.sleep(0.05)
            except OSError:
                return

    def join(self) -> None:
        with self._lock() as held:
            if not held:
                # 錠なしで名乗ると、数え終えて止める直前の回の板を使い回せる = 板も Claude Code も起こさずに止まる
                raise LaunchError(ROSTER_BUSY)
            pid = os.getpid()
            path = self.dir / f"client-{pid}-{secrets.token_hex(4)}.json"
            if self._write(path, {"pid": pid, "started": datetime.now().astimezone().isoformat(timespec="seconds")}):
                self.me = path

    def mark(self, session: BoardSession) -> None:
        # 印の pid は run.json の pid (Windows の venv の転送役では、子の pid と食い違う)。
        if self.ok and session.process is not None:
            info = session.info
            self._write(self._marker(info), {"pid": info.pid, "port": info.port, "started": info.started})

    def leave(self, session: BoardSession | None, keep: bool) -> None:
        """終わる時の順 = 自分の登録を消す → ほかの使い手を数える → 残すか、印のある板だけを止める。全部を名簿の錠の中で
        行う = 数えてから止めるまでの間に、新しい使い手が名乗って板を使い回せない。錠が取れない時は、数えも止めもしない
        (錠を持つ回の名乗りや数えの途中に板を止めない = 板は残し、次の起こし方の後始末か --stop に任せる)。錠なしでも
        安全な 2 つだけ、この順で行う = 残すと決めた板の印を外す (止めにくくする向き)・自分の登録を消す (数を減らすだけ)。"""
        with self._lock() as held:
            if held:
                self._leave(session, keep)
                return
        if session is not None and keep and self.ok:
            self._unmark(session.info)
        self._forget()
        if session is not None and not keep:
            print(ROSTER_LEFT, file=sys.stderr)

    def _forget(self) -> None:
        if self.me is not None:
            try:
                self.me.unlink(missing_ok=True)
            except OSError:
                pass                       # 消せなかった登録は、この pid が死んだ後に別の回が消す

    def _leave(self, session: BoardSession | None, keep: bool) -> None:
        self._forget()
        if session is None:
            return
        others = self._others() if self.ok else None
        if keep:
            if self.ok:
                self._unmark(session.info)  # 残すと決めた板は、後の起こし方も止めない
            return
        if others is None:
            session.close()                # 名簿が使えない = 今までの動き
            return
        if others:
            return                         # ほかの回の Claude Code が、まだこの板を使っている
        self._stop_used(session)
        # 自分が使っていた板と、今の run.json の板が食い違う事がある (--stop で止めた後に、別の回が新しい板を起こした)。
        # その回は「まだ使い手 (自分) が居る」と見て新しい板を残して終わる = 最後の使い手の自分が止めないと、誰も使わない
        # 板が残る。止めるのは、印 (起こし方が起こした板) と token つきの応答が合う板だけ = 使い回した板と同じ照合。
        current = read_run(session.run_file)
        if current is not None and session.info is not None and \
                (current.pid, current.token) != (session.info.pid, session.info.token):
            self._stop_used(BoardSession(session.run_file, current))

    def _stop_used(self, session: BoardSession) -> None:
        """最後の使い手として、板 1 つを止める (自分の子はそのまま止め、使い回した板は印と応答が合う時だけ)。"""
        marked = self._marked(session.info)
        if session.process is not None:    # 自分が起こした子 = 今の止め方 (印が読めない時も)
            if marked is False:
                return
            session.close()
            if not (run_matches(session.run_file, session.info) and board_responds(session.info)):
                self._unmark(session.info)
                return
            # 子を止めても板が答える = 自分の子は板ではなかった。板の無い所から 2 つを同時に起こすと、負けた側は
            # port を取れずに終わった子を持ったまま、相手の板を自分の板と見る (ensure_board は、自分の起動より後に
            # 書かれた run.json の板を自分の板と見る)。使い回した板と同じ照合で止める。
        if marked and run_matches(session.run_file, session.info) and board_responds(session.info):
            stop_reused_board(session)
            if not board_responds(session.info, timeout=0.2):
                self._unmark(session.info)  # 印は板が止まった時だけ消す (止められなかった板は、後の回が止める)

    def _others(self) -> int | None:
        """ほかの生きている使い手の数。pid が死んだ登録は消す。数えられない時は None。"""
        try:
            names = [path.name for path in self.dir.iterdir()]
        except FileNotFoundError:
            return 0
        except OSError:
            return None
        alive = 0
        for name in names:
            match = CLIENT_FILE.fullmatch(name)
            if match is None or (self.me is not None and name == self.me.name):
                continue
            pid = int(match[1])
            if 0 < pid < 2 ** 31 and pid_alive(pid):
                alive += 1
                continue
            try:
                (self.dir / name).unlink(missing_ok=True)
            except OSError:
                pass
        return alive

    def _marker(self, info: RunInfo) -> Path:
        return self.dir / f"board-{info.pid}.json"

    def _marked(self, info: RunInfo) -> bool | None:
        """印がこの板 (pid・port・run.json の started) を指すか。読めない時は None。"""
        try:
            data = json.loads(self._marker(info).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False
        except (OSError, ValueError):
            return None
        return data == {"pid": info.pid, "port": info.port, "started": info.started}

    def _unmark(self, info: RunInfo) -> None:
        if self._marked(info):
            try:
                self._marker(info).unlink(missing_ok=True)
            except OSError:
                pass

    def _write(self, path: Path, data: dict) -> bool:
        # 一時の名は書き手ごと = 同時に起こした 2 つの回が同じ印を書いても、互いの一時 file を消し合わない。
        temporary = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(data), encoding="utf-8")
            for attempt in range(20):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:    # Windows = 別の回が同じ file を置き換え中・開いている間 (board/server.py の run.json と同じ)
                    if attempt == 19:
                        raise
                    time.sleep(0.05)
            return True
        except OSError:
            self.ok = False
            return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def stop_board(root: Path) -> int:
    """--stop = この repo の run.json が指す板を、token つきの照会に答える時だけ止める。板も窓も Claude も起こさない。
    照合と止め方は使い回した板と同じ (run.json の pid と token・token つきの応答 → stop_reused_board)。--keep-board で
    残した板・後始末なしに残った板・手で起こした板も止める。ほかの回の Claude Code が使っている板も止める = その回の
    hook は板なしの動き (Claude Code のいつもの確認) に戻るだけで、勝手に許可する道は無い。"""
    state = root.resolve() / "board" / "state"
    session = BoardSession(state / "run.json", read_run(state / "run.json"))
    info = session.info
    if info is None or not (board_responds(info, timeout=STOP_PROBE) and run_matches(session.run_file, info)):
        print("BLEMMA: 動いている板はありません / No board is running")
        return 0
    stop_reused_board(session)
    if board_responds(info, timeout=0.2):
        # 別の利用者・管理者の権限で動く板など。印は残す (後の起こし方の後始末が止める)。
        raise LaunchError("板を止められませんでした / Could not stop the board")
    Clients(state)._unmark(info)           # 印は板が止まった時だけ消す (leave と同じ決まり)
    print("BLEMMA: 板を止めました / Board stopped")
    return 0


def _which(name: str) -> str | None:
    """PATH の絶対の dir の中だけで実行の file を探す (cwd も相対の dir も探さない)。shutil.which は Windows で cwd を
    先頭に足す (3.12 以降も、環境変数 NoDefaultCurrentDirectoryInExePath が無ければ) ので、信頼していない repo で
    起こすと、そこに置かれた claude.cmd・chrome.cmd を拾い、Claude Code の信頼の確認より前に実行してしまう。
    Windows は PATHEXT の拡張子を足して探し、拡張子の無い file は拾わない (名に PATHEXT の拡張子が在る時だけ、その名のまま)。"""
    tails = [""]
    if os.name == "nt":
        exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]
        if os.path.splitext(name)[1].upper() not in {e.upper() for e in exts}:
            tails = exts
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if os.name == "nt":            # Windows の PATH の欄は前後の空白と引用符を外して読む (POSIX では名の一部になりうる = そのまま)
            folder = folder.strip().strip('"')
        if not folder or not os.path.isabs(folder):
            continue
        for tail in tails:
            candidate = os.path.join(folder, name + tail)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def find_app_browser() -> str | None:
    for name in ("chrome", "google-chrome", "google-chrome-stable", "msedge", "microsoft-edge"):
        found = _which(name)
        if found:
            return found
    candidates = []
    if os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base:
                candidates.extend(Path(base) / tail for tail in (
                    "Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"))
    elif sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            candidates.extend(base / tail for tail in (
                "Google Chrome.app/Contents/MacOS/Google Chrome",
                "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
    return next((str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def work_area() -> tuple[int, int, int, int] | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        rectangle = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rectangle), 0):
            return rectangle.left, rectangle.top, rectangle.right, rectangle.bottom
        return None
    # tkinter is in the standard library, but may be absent on minimal Linux builds.
    try:
        import tkinter
    except ImportError:
        return None
    try:
        screen = tkinter.Tk()
        screen.withdraw()
        try:
            return 0, 0, screen.winfo_screenwidth(), screen.winfo_screenheight()
        finally:
            screen.destroy()
    except tkinter.TclError:
        return None


def open_board(info: RunInfo, mode: str, size: tuple[int, int],
               position: tuple[int, int] | None, options: dict[str, str] | None = None) -> None:
    query = urlencode({"mode": mode, **{k: v for k, v in (options or {}).items() if k in PAGE_KEYS and k != "mode"}})
    url = f"http://127.0.0.1:{info.port}/?{query}#t={quote(info.token, safe='')}"
    browser = find_app_browser() if mode == "small" else None
    if browser and position is None:
        area = work_area()
        if area is not None:
            left, top, right, bottom = area
            position = max(left, right - size[0]), max(top, bottom - size[1])
        else:
            browser = None                 # No usable display geometry: normal browser.
    if browser:
        profile = ROOT / "board" / "state" / "browser"   # 普段の窓の大きさの記憶に左右されない・普段の Chrome を汚さない
        subprocess.Popen([browser, f"--app={url}", f"--window-size={size[0]},{size[1]}",
                          f"--window-position={position[0]},{position[1]}", f"--user-data-dir={profile}",
                          "--no-first-run", "--no-default-browser-check"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, cwd=str(ROOT),     # 板と同じく作業フォルダーを継がない
                         **background_options())
    elif not webbrowser.open(url):
        raise LaunchError("ブラウザを開けません / Could not open the board browser")


def find_claude() -> str | None:
    names = ("claude", "claude.cmd", "claude.exe") if os.name == "nt" else ("claude",)
    return next(filter(None, map(_which, names)), None)   # 最初に見つかった物 (walrus を使わない = 3.7 の文法)


def claude_command(executable: str | None, paths: tuple[Path, Path],
                   args: argparse.Namespace) -> list[str]:
    command = [executable or "claude", "--settings", str(paths[0]), "--mcp-config", str(paths[1]),
               "--permission-mode", "default"]
    if args.demo:
        command.extend(["--setting-sources", "project,local", "--strict-mcp-config"])
    return command + args.claude_args


def format_command(command: list[str]) -> str:
    if os.name == "nt":
        # A pasteable PowerShell line, including paths containing spaces or apostrophes.
        def word(value: str) -> str:
            value = value.replace("`", "``").replace('"', '`"').replace("$", "`$")
            for quote in (chr(0x201C), chr(0x201D), chr(0x201E)):   # PowerShell は全角の二重引用符も文字列の閉じと読む
                value = value.replace(quote, "`" + quote)
            return '"' + value.replace("\r", "`r").replace("\n", "`n") + '"'
        return "& " + " ".join(word(value) for value in command)
    # Bash/zsh ANSI-C quoting keeps even multiline prompts on one printed line.
    def word(value: str) -> str:
        if "\n" in value or "\r" in value:
            value = value.replace("\\", "\\\\").replace("'", "\\'")
            return "$'" + value.replace("\r", "\\r").replace("\n", "\\n") + "'"
        return shlex.quote(value)
    return " ".join(word(value) for value in command)


def run_claude(command: list[str]) -> int:
    if os.name == "nt" and Path(command[0]).suffix.lower() in (".cmd", ".bat"):
        # A Windows command wrapper parses arguments twice: first cmd.exe, then
        # its %* forwarding line. Quote for the executable and protect each pass.
        def protect(value: str) -> str:
            return re.sub(r'([\s()\[\]%!^"`<>&|;,=*?])', r'^\1', value)

        def argument(value: str) -> str:
            value = re.sub(r'(\\*)"', lambda match: match[1] * 2 + '\\"', value)
            value = re.sub(r'(\\+)$', lambda match: match[1] * 2, value)
            return protect(protect('"' + value + '"'))

        if any("\n" in value or "\r" in value for value in command):
            raise LaunchError("改行を含む引数には claude.exe を使ってください / Use claude.exe for multiline arguments")
        shell = os.environ.get("COMSPEC", str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/cmd.exe"))
        script = " ".join([protect(command[0])] + [argument(value) for value in command[1:]])
        line = subprocess.list2cmdline([shell]) + ' /d /s /v:off /c "' + script + '"'
        process = subprocess.Popen(line, executable=shell)
    else:
        process = subprocess.Popen(command)
    try:
        return process.wait()
    except BaseException:
        stop_process(process)
        raise


def launch(args: argparse.Namespace, root: Path) -> int:
    executable = find_claude()
    if executable is None and not args.print_only:
        # 板も窓も開く前に止める (板が終了時に止まるので、起動の行だけを出しても扇は働かない)。
        raise LaunchError(CLAUDE_MISSING)
    clients = Clients(root.resolve() / "board" / "state")
    if not args.print_only:
        # 板を探す前に名乗る = 使い回すと決めた後で名乗るより、終わりかけの別の回に板を止められる窓が狭い。
        clients.join()
    session = None
    completed = False
    try:
        session = ensure_board(root, args.port)
        clients.mark(session)
        if not args.print_only:
            if session.process is None and board_has_page(session.info):
                # 使い回した板に見る頁がもう在る = 窓を増やさない (同じ板の窓が 2 枚になると、固定と透過が効かない)
                print(PAGE_OPEN, file=sys.stderr)
            else:
                open_board(session.info, args.mode, args.window_size, args.window_position, **(
                    {"options": args.page_options} if args.page_options else {}))
        paths = write_configs(root)
        command = claude_command(executable, paths, args)
        if args.print_only:
            # 命令の行だけは書けない字を ? に替えない (harden_streams の replace は案内の行のため) = pipe や file へ
            # 向けた時 (Windows は ANSI の code page) に、黙って違う頼み・違う路の命令を出さず、理由つきで止まる。
            line = format_command(command)
            try:
                line.encode(getattr(sys.stdout, "encoding", None) or "utf-8")
            except UnicodeEncodeError:
                raise LaunchError("この 1 行は今の出力先の文字コードで書けません。console に表示して写してください / "
                                  "The command line cannot be encoded for this output; "
                                  "print it to the console and copy it") from None
            print(line)
            result = 0
        else:
            result = run_claude(command)
        completed = True
        return result
    finally:
        clients.leave(session, keep=completed and args.keep_board)


def harden_streams(*streams: Any) -> None:
    """案内の行 (日本語を含む) を、console の文字コードが書けない時 (英語の Windows の cp1252 など) も落とさない = 書けない字は
    ? に替える。文字コードは変えない (日本語の console はそのまま読める)。Replace unencodable characters instead of raising."""
    for stream in streams or (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    harden_streams()
    try:
        args = parse_args(argv)
        if args.stop:
            return stop_board(ROOT)
        return launch(args, ROOT)
    except KeyboardInterrupt:
        print("BLEMMA: 中断しました / Interrupted", file=sys.stderr)
        return 130
    except LaunchError as error:
        print("\n".join("BLEMMA: " + line for line in str(error).splitlines()), file=sys.stderr)
        return 1
    except Exception:
        # Do not echo exceptions: they can contain the token-bearing URL or a prompt.
        print("BLEMMA: 起動処理に失敗しました (配置・権限を確認) / Launch failed (check files and permissions)",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
