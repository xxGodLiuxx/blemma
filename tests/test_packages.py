# -*- coding: utf-8 -*-
"""repo の board/・hooks/ は通常の package = sys.path の後ろに同じ名の module が在っても取り違えない。

site-packages の頭に board.py を置く道具 (基板の制御の lib など) を入れた python では、名前空間の package が
後ろの module に負けて `from board.server import …` (同梱の MCP server) が起動で落ちた。直の起動
(`python board/server.py`・`python hooks/permission.py`) は今までどおり動く。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _python(*args: str, stdin: bytes = b""):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BLEMMA_")}
    env["BLEMMA_RUN_FILE"] = str(ROOT / "tests" / "no-such-run.json")      # 板へは繋がない
    return subprocess.run([sys.executable, "-B", *args], input=stdin, capture_output=True, timeout=60, env=env)


def test_repo_packages_win_over_same_named_modules_later_on_the_path(tmp_path):
    site = tmp_path / "site-packages"
    (site / "hooks").mkdir(parents=True)
    (site / "board.py").write_text("FAKE = True\n", encoding="utf-8")                # module の形
    (site / "hooks" / "__init__.py").write_text("FAKE = True\n", encoding="utf-8")   # package の形
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); sys.path.append(sys.argv[2]); "
            "from board.server import Limits; from hooks._client import _Connection; import board, hooks; "
            "print(json.dumps([board.__file__, hooks.__file__, Limits().hard_deadline, _Connection.__name__]))")
    p = _python("-I", "-c", code, str(ROOT), str(site))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    board_file, hooks_file, deadline, name = json.loads(p.stdout)
    assert Path(board_file).parent == ROOT / "board" and Path(hooks_file).parent == ROOT / "hooks"
    assert (deadline, name) == (555, "_Connection")


def test_board_started_by_hand_stops_on_an_old_python(tmp_path):
    """板を手で起こした時 (`python board/server.py`) も、3.10 未満なら ほかの import より前に、起こし方と同じ
    日英 1 行ずつで止まる。版を 3.7 に差し替えて、server.py だけを置いた写しで走らせる。"""
    import ast
    import shutil
    source = (ROOT / "board" / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 7))     # 3.7 でも、構文の誤りにならずに確かめの行へ届く
    docstring, future, imported, check = tree.body[:4]
    assert isinstance(docstring, ast.Expr) and isinstance(future, ast.ImportFrom) and future.module == "__future__"
    assert isinstance(imported, ast.Import) and [alias.name for alias in imported.names] == ["sys"]
    assert isinstance(check, ast.If) and ast.unparse(check.test) == "sys.version_info < (3, 10)"
    copy = tmp_path / "写し"
    copy.mkdir()
    shutil.copy2(ROOT / "board" / "server.py", copy / "server.py")
    code = ("import runpy, sys; sys.version_info = (3, 7, 17, 'final', 0); "
            "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')")
    p = subprocess.run([sys.executable, "-B", "-c", code, str(copy / "server.py"), "--no-browser", "--port", "18899"],
                       cwd=copy, capture_output=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
    assert p.returncode == 1 and p.stdout == ""
    assert p.stderr.splitlines() == [
        "BLEMMA: Python 3.10 以上で実行してください (今の版は 3.7)",
        "BLEMMA: Python 3.10 or later is required (this is 3.7)",
    ]
    assert sorted(path.name for path in copy.iterdir()) == ["server.py"]      # 置き場 (state) も作らない


def test_direct_launch_still_reads_the_files_next_to_it():
    """直の起動は script の dir (-I では自分で足す) から隣の file を読む = package にしても今までどおり。"""
    for flags in ((), ("-I",)):
        p = _python(*flags, str(ROOT / "board" / "server.py"), "--help")
        assert p.returncode == 0 and b"--no-browser" in p.stdout, p.stderr.decode("utf-8", "replace")
        p = _python(*flags, str(ROOT / "hooks" / "permission.py"), stdin=b"{}")
        assert (p.returncode, p.stdout, p.stderr) == (0, b"", b"")
