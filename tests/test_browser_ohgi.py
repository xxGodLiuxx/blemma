"""Real, isolated headless Chromium. No browser/profile belonging to the user is used."""
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest
import server as S

ROOT = Path(__file__).resolve().parents[1]


def chromium():
    candidates = [os.environ.get("BLEMMA_TEST_BROWSER")] + [shutil.which(n) for n in ("chromium", "google-chrome", "chrome", "msedge")]
    for base in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")):
        candidates += [str(Path(base) / tail) for tail in (
            "Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe")]
    candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next((p for p in candidates if p and Path(p).is_file()), None)


def free_port():
    for port in range(18770, 18970):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    raise RuntimeError("No isolated test port is free")


def serve(app):
    """The server binds exclusively on Windows, so a port in TIME_WAIT passes free_port but not this."""
    for port in range(18770, 18970):
        try:
            return S.make_server(app, port)
        except OSError:
            pass
    raise RuntimeError("No isolated test port is free")


def close_browser(node, opener, port):
    """On Windows chrome.exe hands off to another process and exits with 0, so stopping the
    process we started leaves the real browser running. Close it over the debugging port."""
    try:
        with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
            url = json.load(response)["webSocketDebuggerUrl"]
    except (OSError, ValueError, KeyError):
        return
    script = ("const s=new WebSocket(process.argv[1]);"
              "s.onopen=()=>s.send(JSON.stringify({id:1,method:'Browser.close'}));"
              "s.onmessage=s.onclose=s.onerror=()=>process.exit(0);"
              "setTimeout(()=>process.exit(0),3000);")
    subprocess.run([node, "-e", script, url], capture_output=True, timeout=6)


def test_real_browser_fan_inputs_and_fallback(tmp_path):
    browser, node = chromium(), shutil.which("node")
    if not browser or not node:
        pytest.skip("Isolated Chromium and node are needed for real browser checks")
    support = subprocess.run([node, "-p", "typeof WebSocket"], capture_output=True, text=True, encoding="utf-8", timeout=5)
    if support.stdout.strip() != "function":
        pytest.skip("The optional browser harness needs node with built-in WebSocket support")
    app = S.App(replace(S.Limits(), pending_hold=.15, wait_hold=.1, disconnect=120, undo_ms=1000,
                        viewer=None), "ohgi-browser-test", static_dir=ROOT / "board" / "static")
    httpd = serve(app)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    S.start_ticker(app.board)
    port = free_port()
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = None
    browser_log = (tmp_path / "chromium.log").open("w", encoding="utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # From an elevated shell Chrome re-launches itself de-elevated and the process we started exits.
        # Inside a job object (a memory-capped test runner) that hand-off never yields a browser, and this
        # test would skip without a word. Keep the process we start as the browser itself.
        process = subprocess.Popen([browser, "--do-not-de-elevate",
                                    "--headless=new", "--disable-gpu", "--in-process-gpu", "--no-first-run", "--no-default-browser-check",
                                    "--disable-background-networking", "--disable-extensions",
                                    "--disable-component-update", "--disable-sync", "--remote-debugging-address=127.0.0.1",
                                    f"--remote-debugging-port={port}", f"--user-data-dir={tmp_path / 'chromium'}",
                                    "about:blank"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=browser_log, **flags)
        endpoint = None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:   # The process we started may exit at once: see close_browser.
            try:
                with opener.open(f"http://127.0.0.1:{port}/json", timeout=.5) as response:
                    targets = json.load(response)
                endpoint = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
                break
            except (OSError, ValueError, StopIteration):
                time.sleep(.05)
        if not endpoint:
            pytest.skip("Isolated headless Chromium did not start (no page renderer)")
        output = Path(os.environ.get("BLEMMA_SCREENSHOT_DIR", str(tmp_path / "screenshots")))
        output.mkdir(parents=True, exist_ok=True)
        config = {"endpoint": endpoint, "origin": f"http://127.0.0.1:{httpd.server_port}",
                  "output": str(output.resolve())}
        result = subprocess.run([node, str(ROOT / "tests" / "browser_ohgi.cjs")], input=json.dumps(config),
                                capture_output=True, text=True, encoding="utf-8", timeout=75, **flags)
        if "browser unavailable:" in result.stdout:
            pytest.skip("Isolated Chromium renderer could not start; no real DOM or PiP check ran")
        if result.returncode:
            browser_log.flush()
        assert result.returncode == 0, result.stderr + result.stdout + (tmp_path / "chromium.log").read_text(encoding="utf-8", errors="replace")[-3000:]
        assert "browser checks passed" in result.stdout
    finally:
        close_browser(node, opener, port)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        app.board.close()
        httpd.shutdown()
        httpd.server_close()
        browser_log.close()

