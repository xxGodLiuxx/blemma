#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA を 1 行で起こす / Launch BLEMMA with one command (Python 3.10+)."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, parse_qsl, urlencode

from hooks._client import _Connection as _DeadlineConnection

ROOT = Path(__file__).resolve().parent
START_TIMEOUT = 10.0
RUN_MAX_AGE = 24 * 60 * 60       # Discovery records must be less than one day old.
STATUS_MESSAGE = "BLEMMA: 板 (ブラウザ) で答えを待っています / waiting on the board"
HOOKS = (
    ("PermissionRequest", ".*", "permission.py", 600),
    ("PreToolUse", "AskUserQuestion", "ask.py", 600),
    ("Elicitation", ".*", "elicitation.py", 600),
    ("Notification", "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
     "notify.py", 10),
    ("UserPromptSubmit", None, "state.py", 5),
    ("Stop", None, "state.py", 5),
)
PAGE_KEYS = frozenset(("dwell", "scan", "key", "lang", "sound", "mode", "scale", "font", "theme", "desc", "trail"))


def page_options(environment: str, assignments: list[str]) -> dict[str, str]:
    """Only display keys enter the URL. Values are validated by the shared page parser."""
    options = {k: v for k, v in parse_qsl(environment, keep_blank_values=True) if k in PAGE_KEYS}
    for assignment in assignments:
        key, sep, value = assignment.partition("=")
        if sep and key in PAGE_KEYS:
            options[key] = value
    return options


class LaunchError(Exception):
    """利用者へ出せる、秘密を含まない英日の 1 行。"""


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
               "既存の板は在処の記録が 24 時間以内で、認証付きの応答があれば再利用します。\n"
               "Reuse a board with a discovery record under 24 hours old and an authenticated response.\n"
               "画面の寸法が取得できない時は既定のブラウザで開きます (位置の指定で小窓を使えます)。\n"
               "Use the default browser if display geometry is unavailable (set a position for app mode).")
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
    parser.add_argument("--port", type=int, default=8765, metavar="PORT",
                        help="新しく起こす板のポート (既定 8765)\nPort for a new board (default: 8765)")
    parser.add_argument("--keep-board", action="store_true",
                        help="終了後も板を残す\nKeep the board after Claude exits")
    parser.add_argument("--print-only", action="store_true",
                        help="板と設定を用意し、Claude の起動行だけ表示 (板を残すには --keep-board)\n"
                             "Prepare the board/configs and print the Claude command (--keep-board retains the board)")
    parser.add_argument("--window-size", type=size_value,
                        default=os.environ.get("BLEMMA_WINDOW_SIZE", "520,760"), metavar="W,H",
                        help="小窓の幅,高さ (BLEMMA_WINDOW_SIZE・既定 520,760)\n"
                             "Window size (BLEMMA_WINDOW_SIZE; default: 520,760)")
    parser.add_argument("--window-position", type=position_value,
                        default=os.environ.get("BLEMMA_WINDOW_POSITION", "bottom-right"), metavar="X,Y",
                        help="小窓の位置 (BLEMMA_WINDOW_POSITION・既定 右下)\n"
                             "Window position (BLEMMA_WINDOW_POSITION; default: bottom-right)")
    args = parser.parse_args(argv[:split])
    args.page_options = page_options(os.environ.get("BLEMMA_OPTS", ""), args.set)
    option_mode = args.page_options.pop("mode", "small")
    args.mode = args.mode or (option_mode if option_mode in ("small", "large") else "small")
    if not 1 <= args.port <= 65535:
        parser.error("port")
    args.claude_args = argv[split + 1:]
    return args


def settings_data(root: Path) -> dict:
    root = root.resolve()
    return {
        "permissions": {"allow": ["mcp__blemma__ask_board"]},
        "hooks": {
            event: [{**({"matcher": matcher} if matcher else {}), "hooks": [{
                "type": "command", "command": python_executable(),
                "args": [str(root / "hooks" / name)], "timeout": timeout,
                **({"statusMessage": STATUS_MESSAGE} if name != "state.py" else {}),
            }]}] for event, matcher, name, timeout in HOOKS
        },
    }


def write_configs(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    state = root / "board" / "state"
    state.mkdir(parents=True, exist_ok=True)
    paths = (state / "settings.generated.json", state / "mcp.generated.json")
    mcp = {"mcpServers": {"blemma": {
        "command": python_executable(), "args": [str(root / "mcp" / "blemma_mcp.py")],
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


def read_run(path: Path) -> RunInfo | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        port, token, pid = data["port"], data["token"], data["pid"]
        started = datetime.fromisoformat(data["started"])
        now = time.time()
        if (type(port) is not int or not 1 <= port <= 65535 or
                type(pid) is not int or pid <= 0 or not isinstance(token, str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", token) or started.tzinfo is None or
                not -5 <= now - started.timestamp() <= RUN_MAX_AGE or
                not -5 <= now - path.stat().st_mtime <= RUN_MAX_AGE):
            return None
        return RunInfo(port, token, pid)
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
        try:
            data = json.loads(self.run_file.read_text(encoding="utf-8"))
            if (isinstance(data, dict) and data.get("pid") == self.process.pid and
                    (self.info is None or data.get("token") == self.info.token)):
                self.run_file.unlink()
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeError):
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
        session.process = subprocess.Popen(
            [python_executable(), str(root / "board" / "server.py"), "--no-browser", "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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


def find_app_browser() -> str | None:
    for name in ("chrome", "google-chrome", "google-chrome-stable", "msedge", "microsoft-edge"):
        found = shutil.which(name)
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
        subprocess.Popen([browser, f"--app={url}", f"--window-size={size[0]},{size[1]}",
                          f"--window-position={position[0]},{position[1]}"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **background_options())
    elif not webbrowser.open(url):
        raise LaunchError("ブラウザを開けません / Could not open the board browser")


def find_claude() -> str | None:
    names = ("claude", "claude.cmd", "claude.exe") if os.name == "nt" else ("claude",)
    return next((found for name in names if (found := shutil.which(name))), None)


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
    session = ensure_board(root, args.port)
    completed = False
    try:
        open_board(session.info, args.mode, args.window_size, args.window_position, **(
            {"options": args.page_options} if args.page_options else {}))
        paths = write_configs(root)
        executable = find_claude()
        command = claude_command(executable, paths, args)
        if args.print_only or executable is None:
            print(format_command(command))
            result = 0
        else:
            result = run_claude(command)
        completed = True
        return result
    finally:
        if not (completed and args.keep_board):
            session.close()


def main(argv: list[str] | None = None) -> int:
    try:
        return launch(parse_args(argv), ROOT)
    except KeyboardInterrupt:
        print("BLEMMA: 中断しました / Interrupted", file=sys.stderr)
        return 130
    except LaunchError as error:
        print("BLEMMA: " + str(error), file=sys.stderr)
        return 1
    except Exception:
        # Do not echo exceptions: they can contain the token-bearing URL or a prompt.
        print("BLEMMA: 起動処理に失敗しました (配置・権限を確認) / Launch failed (check files and permissions)",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
