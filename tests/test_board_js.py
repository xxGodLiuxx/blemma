# -*- coding: utf-8 -*-
"""板の頁の JS (board/static/board_core.js・board.js) を node で走らせて確かめる (§4.2)。

board_core.js は require() で読む (純粋な計算)。board.js は DOM を持たない vm の中で読み、最後の `init();` を
内部の関数の書き出しに差し替える (通信は試験の偽の fetch)。node が無い環境では skip。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node が無い (頁の JS の試験は node で走らせる)")

STATIC = Path(__file__).resolve().parent.parent / "board" / "static"

PRELUDE = r"""
const fs = require("fs"), vm = require("vm");
const core = require(%(core)s);

/* from から to まで step ms ごとのこまで update する (to を含む)。押した時刻の列と最後の返り */
function frames(d, key, from, to, step) {
  step = step || 16;
  let last = null;
  const fired = [];
  for (let t = from; t <= to; t += step) {
    last = d.update(key, t);
    if (last.fire) fired.push(t);
  }
  return { last: last, fired: fired };
}

/* board.js を DOM なしの vm で読み、init() の代わりに内部を書き出す */
function loadPage(fetchImpl) {
  let src = fs.readFileSync(%(page)s, "utf8");
  const re = /\n  init\(\);(\r?\n)/;
  if (!re.test(src)) throw new Error("board.js の init(); の行が見つからない");
  src = src.replace(re, "\n  window.__t = { S: S, press: press, releaseDwell: releaseDwell };$1");
  const win = { BlemmaCore: core };
  vm.runInNewContext(src, { window: win, document: {}, performance: performance, fetch: fetchImpl,
                            setTimeout: setTimeout, clearTimeout: clearTimeout, console: console });
  return win.__t;
}
"""


def node(tmp_path: Path, body: str):
    """PRELUDE + body を node で走らせ、stdout の JSON を返す。"""
    script = tmp_path / "t.js"
    script.write_text(PRELUDE % {"core": json.dumps(str(STATIC / "board_core.js")),
                                 "page": json.dumps(str(STATIC / "board.js"))} + body, encoding="utf-8")
    p = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


# ---- 滞留 (視線) = 外れた長さと途切れたこまを見る (戻った瞬間に古い滞留で押さない) ----

DWELL_CASES = r"""
const out = {};
let d = new core.Dwell(1000, 150);
/* 外のレビューの反例 = 釦の上 0ms → 外 100ms → (こまなし) → 同じ釦 1500ms */
d.update("allow_once", 0); d.update(null, 100);
out.review = { back: d.update("allow_once", 1500), rest: frames(d, "allow_once", 1516, 2600).fired };

/* こまは 100ms ごと (grace の内) で、外れていた 200ms は grace を超える = 戻った時に数え直す */
d = new core.Dwell(1000, 150);
d.update("allow_once", 0); d.update(null, 100); d.update(null, 200);
out.away = d.update("allow_once", 300);

/* 揺れ (外れて 150ms のうちに戻る) は数え続ける = 最初に入ってから 1 秒で押す */
d = new core.Dwell(1000, 150);
frames(d, "allow_once", 0, 496);
frames(d, null, 512, 608);
out.jitter = frames(d, "allow_once", 624, 1200).fired;

/* 外へ出たと分からなくても、こまが grace より長く途切れたら数え直す (頁が隠れた・描画が止まった) */
d = new core.Dwell(1000, 150);
d.update("allow_once", 0);
out.gap = { back: d.update("allow_once", 1500), rest: frames(d, "allow_once", 1516, 2600).fired };

/* 途切れずに留まれば 1 秒で 1 回だけ押す (見続けても 2 回押さない) */
d = new core.Dwell(1000, 150);
out.steady = frames(d, "allow_once", 0, 3000).fired;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def dwell_cases(tmp_path_factory):
    return node(tmp_path_factory.mktemp("dwell"), DWELL_CASES)


def test_dwell_review_counterexample_does_not_fire_on_return(dwell_cases):
    """外のレビューの反例: 長く外れて (こまなしで) 戻った瞬間は押さない = 戻ってから 1 秒留まって押す。"""
    c = dwell_cases["review"]
    assert c["back"] == {"target": "allow_once", "progress": 0, "fire": False}
    assert c["rest"] and c["rest"][0] >= 2500


def test_dwell_return_after_more_than_grace_starts_over(dwell_cases):
    assert dwell_cases["away"] == {"target": "allow_once", "progress": 0, "fire": False}


def test_dwell_jitter_within_grace_keeps_counting(dwell_cases):
    assert dwell_cases["jitter"] and 1000 <= dwell_cases["jitter"][0] < 1020


def test_dwell_frame_gap_starts_over(dwell_cases):
    c = dwell_cases["gap"]
    assert c["back"]["fire"] is False and c["back"]["progress"] == 0
    assert c["rest"] and c["rest"][0] >= 2500


def test_dwell_steady_fires_once(dwell_cases):
    assert len(dwell_cases["steady"]) == 1 and 1000 <= dwell_cases["steady"][0] < 1020


def test_release_dwell_blocks_the_button_under_the_pointer(tmp_path):
    """頁が隠れた・焦点を失った (releaseDwell) = 0.9 秒の滞留を捨て、同じ釦は一度外へ出て入り直すまで数えない。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.over = "allow_once";
const before = frames(t.S.dwell, "allow_once", 0, 896);
t.releaseDwell();
const stay = frames(t.S.dwell, "allow_once", 912, 3000);
frames(t.S.dwell, null, 3016, 3032);
const again = frames(t.S.dwell, "allow_once", 3048, 4100);
console.log(JSON.stringify({ before: before.fired, stay: stay.fired, stayLast: stay.last, again: again.fired }));
""")
    assert out["before"] == [] and out["stay"] == []
    assert out["stayLast"] == {"target": None, "progress": 0, "fire": False}
    assert out["again"] and out["again"][0] >= 3048 + 1000
