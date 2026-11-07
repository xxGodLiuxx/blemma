# -*- coding: utf-8 -*-
"""板の頁の JS (board/static/board_core.js・board.js) を node で走らせて確かめる (§4.2)。

board_core.js は require() で読む (純粋な計算)。board.js は DOM を持たない vm の中で読み、最後の `init();` を
内部の関数の書き出しに差し替える (通信は試験の偽の fetch)。node が無い環境では skip。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import server as board_server
import window_win

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
  src = src.replace(re, "\n  window.__t = { S: S, press: press, releaseDwell: releaseDwell, bindInputs: bindInputs, inputActive: inputActive, selectWindow: function(w) { viewWindow=w; viewDocument=w.document; }, onClick: onClick, disarm: disarm, fitFan: fitFan, windowCall: windowCall, poll: poll, goneSince: goneSince, bumpGen: bumpGen, onPointer: onPointer, letGo: letGo, pushShape: pushShape, window: window, frame: frame, forgetSends: forgetSends, startDrag: startDrag, endDrag: endDrag, fitWindow: fitWindow, windowMoved: windowMoved, onKeyDown: onKeyDown, togglePin: togglePin, scrolled: scrolled, placeWindow: placeWindow, apply: apply };$1");
  const win = { BlemmaCore: core, crypto: require("crypto").webcrypto };
  vm.runInNewContext(src, { window: win, document: {}, performance: performance, fetch: fetchImpl,
                            setTimeout: setTimeout, clearTimeout: clearTimeout, console: console,
                            AbortController: AbortController });
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

/* 守り (block) は釦なしの 1 こまの揺れでは解けない (羽根の縁に休む視線が帯へ 1 こま揺れた) = 入り直していない釦を押さない */
d = new core.Dwell(1000, 150);
d.block("allow_once"); d.update("allow_once", 0); d.update(null, 16);
out.edge = frames(d, "allow_once", 32, 1200).fired;

/* 釦なしが grace を超えて続いた = 外へ出た = 守りを解く。入り直してから 1 秒で押す */
d = new core.Dwell(1000, 150);
d.block("allow_once"); d.update("allow_once", 0);
frames(d, null, 16, 208);
out.leftLong = frames(d, "allow_once", 224, 1400).fired;

/* 別の釦に入った = すぐ解く (その釦は入ってから 1 秒で押す) */
d = new core.Dwell(1000, 150);
d.block("allow_once");
out.other = frames(d, "deny", 0, 1100).fired;
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


def test_dwell_block_survives_a_one_frame_slip_off_the_button(dwell_cases):
    """入り直すまで数えない守り (block) は、釦なしの 1 こま (羽根の縁に休む視線が書の帯・地紙へ揺れた) では解けない =
    数える側の揺れの許し (150 ms) と揃える。直す前は 1 こまで解け、入り直していない羽根を 1 秒後に押した ([1040]・2 巡目 i19)。"""
    assert dwell_cases["edge"] == []


def test_dwell_block_lifts_after_being_off_for_longer_than_grace(dwell_cases):
    """釦なしが 150 ms を超えて続いた = 外へ出た = 守りを解く。入り直してから 1 秒で押す。"""
    assert dwell_cases["leftLong"] and dwell_cases["leftLong"][0] >= 224 + 1000


def test_dwell_block_lifts_at_once_on_another_button(dwell_cases):
    """守りの釦から別の釦へ入った = すぐ解く (別の釦は入ってから 1 秒で押す)。"""
    assert dwell_cases["other"] and 1000 <= dwell_cases["other"][0] < 1020


def test_release_dwell_blocks_the_button_under_the_pointer(tmp_path):
    """頁が隠れた・焦点を失った (releaseDwell) = 0.9 秒の滞留を捨て、同じ釦は一度外へ出て入り直すまで数えない。
    外へ出たと見るのは、釦の無い所に 150 ms (揺れの許し) より長く居た時 (か、別の釦に入った時)。11/7 に期待を安全の向きへ
    書き換えた = 前は釦なしの 2 こま (16 ms) で守りが解け、入り直したと見ていた。縁の揺れ 1 こまで、見ていない釦を
    押さないため (2 巡目 i19)。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.over = "allow_once";
const before = frames(t.S.dwell, "allow_once", 0, 896);
t.releaseDwell();
const stay = frames(t.S.dwell, "allow_once", 912, 3000);
frames(t.S.dwell, null, 3016, 3200);                 /* 釦の外に 150 ms より長く居る */
const again = frames(t.S.dwell, "allow_once", 3216, 4300);
console.log(JSON.stringify({ before: before.fired, stay: stay.fired, stayLast: stay.last, again: again.fired }));
""")
    assert out["before"] == [] and out["stay"] == []
    assert out["stayLast"] == {"target": None, "progress": 0, "fire": False}
    assert out["again"] and out["again"][0] >= 3216 + 1000


def test_required_multi_with_min_picks_0_can_send_no_marks(tmp_path):
    """必須の複数選択で min_picks 0 (minItems 0) = 印 0 個でも「次へ」→「送る」で [] を送れる。
    min_picks が無い必須の欄は今までどおり 1 個以上 (「次へ」を押せない)。"""
    out = node(tmp_path, r"""
function card(minPicks) {
  const f = { name: "tags", title: "札", multi: true, required: true,
              options: [{ label: "a", value: "a" }, { label: "b", value: "b" }] };
  if (minPicks !== undefined) f.min_picks = minPicks;
  return { id: "c", kind: "elicitation", state: "shown", view_seq: 1, payload: { head: "srv", text: "t", fields: [f] } };
}
function nextOf(c) {
  return core.buildScreen(c, core.newUi(c.id), "ja").options.filter(function (o) { return o.key === "next"; })[0];
}
const zero = card(0), none = card(undefined);
const step = core.pressKey(zero, core.newUi(zero.id), "next");
const send = step && step.ui ? core.pressKey(zero, step.ui, "send") : null;
console.log(JSON.stringify({ zeroNext: nextOf(zero).disabled, noneNext: nextOf(none).disabled,
                             noneStep: core.pressKey(none, core.newUi(none.id), "next"),
                             send: send && send.send }));
""")
    assert out["zeroNext"] is False and out["send"] == {"type": "accept", "picks": [[]]}
    assert out["noneNext"] is True and out["noneStep"] is None


# ---- 計 (押しの数) = 要求ごとに切り離して送る (§4.5) ----

PAGE_SETUP = r"""
const card = __CARD__;
const sent = [];
function reply(status, data) { return { status: status, json: function () { return Promise.resolve(data); } }; }
function show(t) {                                   /* render() の代わりに、札と釦を頁の状態に置く */
  t.S.card = card;
  t.S.ui = core.newUi(card.id);
  t.S.key = core.viewKey(card, t.S.ui, "ja");
  t.S.btns = { allow_once: { disabled: false } };
  t.S.dwell = new core.Dwell(1000, 150);
  t.S.token = "x";
}
"""


def _board(clock):
    lim = replace(board_server.Limits(), wait_hold=0.0, pending_hold=0.0, viewer=None)
    board = board_server.Board(lim, clock=clock)
    assert board.ask("permission", {"cwd": "repo"}, {"head": "Bash"})[0] == 200
    return board, board.pending(-1)["card"]


def _sum(body) -> int:
    return sum(body["presses"].values())


def test_undo_before_answer_reply_sends_each_press_once(tmp_path, clock):
    """外のレビューの反例: /answer の返りより先に取り消す = 押しは 2 回。送る数も 1 + 1 で、server の計は 2。"""
    board, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
let releaseAnswer = null;
const gate = new Promise(function (r) { releaseAnswer = r; });
const t = loadPage(function (path, opt) {
  sent.push({ path: path, body: JSON.parse(opt.body) });
  if (path === "/answer") return gate.then(function () { return reply(200, { undo_ms: 3000, undo_remaining: 3 }); });
  return Promise.resolve(reply(200, { state: "shown" }));
});
show(t);
t.press("allow_once", "dwell");                      /* 1 押し = /answer (返りはまだ来ない) */
t.S.card = Object.assign({}, card, { state: "deciding" });
t.S.undoAt = performance.now() + 3000;               /* 写しは deciding = 猶予のうち */
t.press("undo", "switch");                           /* 1 押し = /undo (/answer の返りより先) */
setTimeout(function () {
  releaseAnswer();
  setTimeout(function () { console.log(JSON.stringify({ sent: sent, delta: t.S.delta })); }, 20);
}, 20);
""").replace("__CARD__", json.dumps(card)))
    answer, undo = out["sent"]
    assert (answer["path"], undo["path"]) == ("/answer", "/undo")
    assert (_sum(answer["body"]), _sum(undo["body"])) == (1, 1)
    assert sum(out["delta"].values()) == 0
    a, u = answer["body"], undo["body"]                # 頁が送った物をそのまま server へ
    assert a["press_batches"][0]["id"] != u["press_batches"][0]["id"]
    assert board.answer(a["id"], a["seq"], a["choice"], a["by"], a["presses"], a["press_batches"])[0] == 200
    assert board.undo(u["id"], u["by"], u["presses"], u["press_batches"]) == (200, {"state": "shown"})
    stats = board.pending(-1)["stats"]
    assert stats["total"] == 2 and (stats["presses"]["dwell"], stats["presses"]["switch"]) == (1, 1)


def test_refused_answer_gives_its_presses_to_the_next_send(tmp_path, clock):
    """返りが 200 でない (409 = server は数えていない) 押しは、同じ札の次の送りに乗せる (元の動きのまま)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
const codes = [409, 200];
const t = loadPage(function (path, opt) {
  sent.push({ path: path, body: JSON.parse(opt.body) });
  const st = codes.shift();
  return Promise.resolve(reply(st, st === 200 ? { undo_ms: 3000, undo_remaining: 3 } : { error: "stale" }));
});
show(t);
t.press("allow_once", "dwell");
setTimeout(function () {
  t.press("allow_once", "dwell");
  setTimeout(function () { console.log(JSON.stringify({ sent: sent, delta: t.S.delta })); }, 20);
}, 20);
""").replace("__CARD__", json.dumps(card)))
    assert [_sum(s["body"]) for s in out["sent"]] == [1, 2]
    assert out["sent"][0]["body"]["press_batches"][0] == out["sent"][1]["body"]["press_batches"][0]
    assert sum(out["delta"].values()) == 0


def test_press_batches_keep_ids_across_lost_replies_and_retries(tmp_path):
    """純粋な計算: 別の要求が先に戻っても、再送する古い束の ID と数は変わらない。"""
    out = node(tmp_path, r"""
const first = core.takePressBatches(core.newPressLedger("page"), { dwell: 1 });
const second = core.takePressBatches(first.ledger, { switch: 1 });
let returned = core.returnPressBatches(second.ledger, second.batches);
returned = core.returnPressBatches(returned, first.batches);
const retry = core.takePressBatches(returned, { key: 1 });
const again = core.takePressBatches(core.returnPressBatches(retry.ledger, retry.batches), core.zeroPresses());
console.log(JSON.stringify({ first: first.batches, second: second.batches, retry: retry.batches,
                             again: again.batches, total: core.sumPressBatches(again.batches),
                             pending: again.ledger.pending }));
""")
    first, second = out["first"][0], out["second"][0]
    assert out["retry"][:2] == [second, first]
    assert out["again"] == out["retry"]
    assert len({b["id"] for b in out["retry"]}) == 3
    assert out["total"] == {"dwell": 1, "switch": 1, "key": 1, "touch": 0, "click": 0}
    assert out["pending"] == []


def test_lost_answer_reply_retries_same_batch_on_undo(tmp_path, clock):
    """/answer は受理されたが応答だけ喪失。/undo の再送分は同じ ID = 実操作 2 回は計 2。"""
    board, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, body: JSON.parse(opt.body) });
  if (path === "/answer") return Promise.reject(new Error("reply lost"));
  return Promise.resolve(reply(200, { state: "shown" }));
});
show(t);
t.press("allow_once", "dwell");
setTimeout(function () {
  t.S.card = Object.assign({}, card, { state: "deciding" });
  t.S.undoAt = performance.now() + 3000;
  t.press("undo", "switch");
  setTimeout(function () {
    console.log(JSON.stringify({ sent: sent, pending: t.S.pressLedger.pending }));
  }, 20);
}, 20);
""").replace("__CARD__", json.dumps(card)))
    answer, undo = out["sent"]
    assert (answer["path"], undo["path"]) == ("/answer", "/undo")
    a, u = answer["body"], undo["body"]
    assert (_sum(a), _sum(u)) == (1, 2)
    assert u["press_batches"][0] == a["press_batches"][0]
    assert len({b["id"] for b in u["press_batches"]}) == 2
    assert board.answer(a["id"], a["seq"], a["choice"], a["by"], a["presses"], a["press_batches"])[0] == 200
    assert board.undo(u["id"], u["by"], u["presses"], u["press_batches"])[0] == 200
    assert board.pending(-1)["stats"]["presses"] == {
        "dwell": 1, "switch": 1, "key": 0, "touch": 0, "click": 0,
    }
    assert board.pending(-1)["stats"]["total"] == 2 and out["pending"] == []


@pytest.mark.parametrize("n", range(2, 7))
def test_fan_geometry_fixed_exits_numbering_and_minimum_width(tmp_path, n):
    out = node(tmp_path, f"console.log(JSON.stringify(core.fanLayout({n}))); ")
    parts = out["parts"]
    assert len(parts) == n + 2
    by_angle = sorted(parts, key=lambda p: p["angle"])
    assert by_angle[0]["key"] == "fixed" and by_angle[-1]["key"] == "terminal"    # 親骨の左右で動かない
    assert by_angle[0]["angle"] < -60 and by_angle[-1]["angle"] > 60
    numbered = [p for p in by_angle if p["key"] == "option"]
    assert [p["index"] for p in numbered] == list(range(n))                        # 左から右へ 1 番から
    assert [p["key"] for p in parts][-2:] == ["fixed", "terminal"]                 # 走査は選択肢が先
    assert all(p["width"] >= 84 for p in parts)
    assert out["depth"] >= 90
    assert all(p["start"] >= -84 and p["end"] <= 84.0001 for p in parts)           # 要の下へ回り込まない = 円にならない
    assert all(abs(((p["label"][0] - out["cx"]) ** 2 +
                    (p["label"][1] - out["cy"]) ** 2) ** .5 - out["middle"]) < .001 for p in parts)
    assert out["inner"] + 60 <= out["press"] < out["middle"] < out["outer"]        # 書の帯は押す帯の内側
    assert len(out["ribs"]) == n + 3


def test_fan_falls_back_without_losing_complex_actions(tmp_path):
    out = node(tmp_path, r"""
function fits(kind, payload, sub, step) {
  const c = {kind, payload}, u = core.newUi(); u.sub = sub; u.step = step || 0;
  return core.fanEligible(c, u, core.buildScreen(c, u, 'ja'));
}
const q = { options: [{label:'a'}, {label:'b'}] };
console.log(JSON.stringify([
  fits('permission', {}), fits('permission', {}, 'deny'),
  fits('question', {questions:[q]}), fits('question', {questions:[{...q,multiSelect:true}]}),
  fits('question', {questions:[q,q]}), fits('question', {questions:[q]}, null, 1),
  fits('question', {questions:[{options:Array(7).fill({label:'x'})}]}),
  fits('elicitation', {fields:[{...q,required:true}]}),
  fits('elicitation', {fields:[{...q,multi:true,required:true}]})
]));
""")
    assert out == [True, True, True, False, False, False, False, True, False]


def test_status_priority(tmp_path):
    out = node(tmp_path, r"""
const states = ['working', 'done', 'waiting on you'].map(state => ({state}));
console.log(JSON.stringify([core.priorityState(states), core.priorityState(states.slice(0,2)),
  core.priorityState(states.slice(0,1)), core.priorityState([], {}), core.priorityState([])]));
""")
    assert [s["state"] for s in out[:4]] == ["waiting on you", "done", "working", "waiting on you"]
    assert out[4] is None


def test_settings_precedence_and_invalid_values(tmp_path):
    out = node(tmp_path, r"""
console.log(JSON.stringify([
 core.parseOptions('', {}),
 core.parseOptions('scale=1.25&theme=dark&scan&trail', {scale:2,theme:'light',font:1.5,mode:'small'}),
 core.parseOptions('scale=9&font=NaN&mode=broken&theme=bad&desc=bad&key=%3C&dwell=1oops&scan=-1',
                   {scale:1.5,font:1.5,mode:'small',theme:'dark',desc:'off',key:'Enter',dwell:2,scan:3}),
 core.parseOptions('scan=off&desc=off&trail=off&sound=off', {scan:'on',desc:'on',trail:'on',sound:'on'})
]));
""")
    defaults, merged, invalid, disabled = out
    assert defaults["mode"] == "large" and defaults["scan"] == "off"
    assert (merged["scale"], merged["theme"], merged["font"], merged["mode"], merged["scan"], merged["trail"]) == (
        1.25, "dark", 1.5, "small", "1.5", "on")
    assert invalid == defaults
    assert all(disabled[k] == "off" for k in ("scan", "desc", "trail", "sound"))


def test_pip_uses_visible_window_focus_and_retains_held_keys(tmp_path):
    """Synthetic windows test event routing only; requestWindow and rendering need Chromium."""
    out = node(tmp_path, r"""
function target() {
  const handlers={}; return {addEventListener(name, fn) {(handlers[name] ||= []).push(fn);},
    fire(name, event={}) {(handlers[name] || []).forEach(fn=>fn(event));}};
}
function win() {
  const w=target(), d=target(); d.documentElement=target(); d.hidden=false; d.focused=true;
  d.hasFocus=()=>d.focused; w.document=d; return w;
}
const t=loadPage(()=>{throw Error('no HTTP');}), original=win(), pip=win();
t.S.dwell=new core.Dwell(1000,150); t.S.scan=new core.Scan(1500); t.S.over='allow_once';
t.S.held.Space=true; t.bindInputs(original); t.bindInputs(pip); t.selectWindow(pip);
frames(t.S.dwell,'allow_once',0,800);
original.document.hidden=true; original.fire('blur'); original.document.fire('visibilitychange');
const before=t.S.dwell.target, active=t.inputActive();
pip.document.focused=false; pip.fire('blur');
const stopped=t.S.dwell.target, blocked=t.S.dwell.blocked, unfocused=t.inputActive();
pip.document.hidden=true; const inactive=t.inputActive(); pip.document.hidden=false;
const held=t.S.held.Space;
pip.document.fire('keyup',{code:'Space'});
console.log(JSON.stringify({before,active,stopped,blocked,unfocused,inactive,held,released:!t.S.held.Space}));
""")
    assert out == {"before": "allow_once", "active": True, "stopped": None,
                   "blocked": "allow_once", "unfocused": True, "inactive": False, "held": True, "released": True}


def test_light_text_keeps_the_japanese_board_japanese(tmp_path):
    """Claude Code の合図の文は英語で来る = 日本語の板に英語を混ぜない (実機の検収 11/6)。"""
    out = node(tmp_path, r"""
console.log(JSON.stringify({
  perm: core.lightText({type:'permission_prompt', message:'Claude needs your permission'}, 'ja'),
  idle: core.lightText({type:'idle_prompt', message:'Claude is waiting for your input'}, 'ja'),
  ja: core.lightText({type:'idle_prompt', message:'日本語の補足'}, 'ja'),
  en: core.lightText({type:'permission_prompt', message:'Claude needs your permission'}, 'en'),
}));
""")
    assert out["perm"] == "権限の確認が届いています"
    assert out["idle"] == "Claude が次の指示を待っています (端末へ)"
    assert out["ja"].endswith("日本語の補足")
    assert out["en"] == "Claude needs your permission"


def test_fan_blades_carry_one_mark_only(tmp_path):
    """羽根は一文字だけ = 全文は見つめた時に上へ出す。"""
    out = node(tmp_path, r"""
console.log(JSON.stringify({
  ja: [0, 1, 5].map(i => core.fanMark(i, 'option', 'ja')),
  fixed: [core.fanMark(undefined, 'fixed', 'ja'), core.fanMark(undefined, 'terminal', 'ja')],
  en: [core.fanMark(0, 'option', 'en'), core.fanMark(undefined, 'fixed', 'en'), core.fanMark(undefined, 'terminal', 'en')],
}));
""")
    assert out == {"ja": ["一", "二", "六"], "fixed": ["止", "戻"], "en": ["1", "Esc", "0"]}


def test_fan_script_fits_the_band_and_never_loses_the_full_text_silently(tmp_path):
    out = node(tmp_path, r"""
const lens = [360, 280];
console.log(JSON.stringify([core.fanScript('許可 (今回)', lens), core.fanScript('あ'.repeat(24), lens), core.fanScript('あ'.repeat(40), lens)]));
""")
    assert out[0]["size"] == 28 and out[0]["lines"][1] == "" and not out[0]["clipped"]
    assert out[1]["size"] == 20 and "".join(out[1]["lines"]) == "あ" * 24 and not out[1]["clipped"]
    assert out[2]["clipped"] and out[2]["lines"][1].endswith("…")


def test_newer_work_is_not_hidden_by_an_old_done(tmp_path):
    out = node(tmp_path, r"""
console.log(JSON.stringify([
  core.priorityState([{state:'done',ago:3600,stale:false},{state:'working',ago:0,stale:false}]).state,
  core.priorityState([{state:'working',ago:600,stale:false},{state:'done',ago:5,stale:false}]).state,
  core.priorityState([{state:'working',ago:0,stale:false},{state:'waiting on you',ago:900,stale:false}]).state,
]));
""")
    assert out == ["working", "done", "waiting on you"]


def test_decline_stays_available_on_ask_board_outside_the_blades(tmp_path):
    """MCP の決まり = 断ると閉じるの両方。ask_board でも断るは残し、羽根の数には数えない。"""
    out = node(tmp_path, r"""
const card = {kind:'elicitation', payload:{head:'blemma', fields:[{required:true, options:Array.from({length:6},(_, i)=>({label:'x'+i}))}]}};
const ui = core.newUi(); const m = core.buildScreen(card, ui, 'ja');
console.log(JSON.stringify({keys:m.options.map(o=>o.key), fits:core.fanEligible(card, ui, m)}));
""")
    assert "decline" in out["keys"] and out["fits"] is True


def test_the_dont_ask_again_button_shows_hidden_characters(tmp_path):
    """「次から訊かない」(恒久の許可を書く釦) の文も、見えない字 (書字方向の字・幅ゼロの字・制御の字) を ⟨U+XXXX⟩ にして見せる
    (外部の点検の所見 = 本文は hook が直していたのに、頁がここで作る釦の文だけ素のままで、書字方向の字で別の規則に見せられた)。
    規則・フォルダ・名の付いた文・形の分からない suggestion の全部で同じ。改行とタブ、ふつうの字はそのまま。"""
    out = node(tmp_path, r"""
const rlo = String.fromCharCode(0x202e), zw = String.fromCharCode(0x200b), bel = String.fromCharCode(7);
const cards = [
  { type: 'addRules', behavior: 'allow', destination: 'localSettings', rules: [{ toolName: 'Bash', ruleContent: 'git ' + rlo + 'sutats:*' }] },
  { type: 'addDirectories', destination: 'session', directories: ['/tmp/a' + zw + 'b'] },
  { type: 'setMode', mode: 'acceptEdits', label: 'ok' + bel },
  { type: 'replaceRules', rules: [{ toolName: 'Read', ruleContent: 'x' + rlo }] },
];
const card = { kind: 'permission', payload: { head: 'Bash', text: 'git status', blocks: [], suggestions: cards.slice(0, 2) } };
const m = core.buildScreen(card, core.newUi(card), 'ja');
console.log(JSON.stringify({
  labels: cards.map(function (s) { return core.suggestionLabel(s, 'ja'); }),
  buttons: m.options.filter(function (o) { return o.key.indexOf('sugg:') === 0; }).map(function (o) { return o.label; }),
  keep: core.visibleText('a\tb\nc 日本語'),
}));
""")
    labels = out["labels"]
    assert "⟨U+202E⟩" in labels[0] and chr(0x202E) not in labels[0], labels
    assert "⟨U+200B⟩" in labels[1] and chr(0x200B) not in labels[1], labels
    assert labels[2] == "ok⟨U+0007⟩", labels
    assert "⟨U+202E⟩" in labels[3], labels
    assert all("⟨U+" in b for b in out["buttons"]) and len(out["buttons"]) == 2, out["buttons"]
    assert out["keep"] == "a\tb\nc 日本語"


def test_script_and_arrow_keys_cannot_change_the_text_while_dwelling():
    """滞留の間は全文を数えている羽根に固定し、走査を止める (外部のレビュー 4 巡目の BLOCKER の反例)。"""
    src = (Path(__file__).resolve().parent.parent / "board" / "static" / "board.js").read_text(encoding="utf-8")
    assert "if (dwelling && S.spotKey !== r.target && S.btns[r.target]) spotlight(S.btns[r.target]);" in src
    assert "var moving = dwelling || now - (S.pointerAt || -1e9) < 1500;" in src


def test_diff_range_finds_the_changed_part(tmp_path):
    got = node(tmp_path, r"""
console.log(JSON.stringify([core.diffRange('サーバーを起動', 'サーバを起動'), core.diffRange('同じ文', '同じ文'),
  core.diffRange('まるで違う', 'abcdefghij'), core.diffRange('a😀b', 'a😁b')]));
""")
    assert got[0] == {"start": 3, "oldEnd": 4, "newEnd": 3}
    assert got[1] is None and got[2] is None
    assert got[3] == {"start": 1, "oldEnd": 3, "newEnd": 3}, "サロゲートの対を割らない"


def test_edit_card_shows_the_change_first(tmp_path):
    got = node(tmp_path, r"""
const card = { kind: 'permission', payload: { head: 'Edit', text: 'README.md', blocks: [
  { label: 'old_string', text: 'サーバーを起動', mono: true }, { label: 'new_string', text: 'サーバを起動', mono: true }] } };
console.log(JSON.stringify(core.buildScreen(card, core.newUi(card), 'ja').blocks));
""")
    assert got[0]["label"] == "変更" and got[0]["text"] == "サーバー → サーバ" and got[0]["change"] is True
    assert got[1]["mark"] == [3, 4] and got[1]["markKind"] == "del"
    assert got[2]["mark"] == [3, 3] and got[2]["markKind"] == "ins"


# ---- 扇の 2 回押し = 1 回の click では答えが出ない ----

def test_fan_needs_a_second_press_on_the_same_blade(tmp_path):
    """純粋な判定: 1 回目は選ぶだけ。同じ羽根を 1.5 秒のうちにもう 1 回押した時だけ決まる。"""
    out = node(tmp_path, r"""
const ms = 1500, first = core.armStep(null, "opt:0", 1000, ms);
console.log(JSON.stringify({
  first: first,
  second: core.armStep(first.arm, "opt:0", 2500, ms).confirm,     /* ちょうど 1.5 秒 = まだ決まる */
  late: core.armStep(first.arm, "opt:0", 2501, ms),               /* 過ぎた = 選び直し */
  other: core.armStep(first.arm, "opt:1", 1200, ms),              /* 別の羽根 = そちらを選ぶだけ */
  cleared: core.armStep(null, "opt:0", 1200, ms).confirm          /* 選択が解けた後 = 1 回では決まらない */
}));
""")
    assert out["first"] == {"confirm": False, "arm": {"key": "opt:0", "at": 1000}}
    assert out["second"] is True
    assert out["late"] == {"confirm": False, "arm": {"key": "opt:0", "at": 2501}}
    assert out["other"] == {"confirm": False, "arm": {"key": "opt:1", "at": 1200}}
    assert out["cleared"] is False


def test_fan_click_answers_only_on_the_second_press(tmp_path, clock):
    """頁の配線: 扇の click は 1 回では /answer を送らない。時間切れの後・描き直して選択が解けた後・別の羽根の後も
    選ぶだけ。同じ羽根を 1.5 秒のうちにもう 1 回押した時にだけ送る。設定で 1 回押しにした時は 1 回で送る。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
let now = 1000;                                        /* 頁の時計を試験が進める */
Object.defineProperty(globalThis, "performance", { value: { now: function () { return now; } },
                                                   configurable: true, writable: true });
function page(click) {
  const t = loadPage(function (path, opt) {
    sent.push({ path: path, body: JSON.parse(opt.body) });
    return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
  });
  show(t);
  const fan = {};                                      /* 扇の枠と羽根の代用品 */
  function blade(key) {
    const b = { dataset: { key: key }, disabled: false, parentNode: fan,
                classList: { add: function () {}, remove: function () {} },
                closest: function (sel) { return sel === "[data-key]" ? b : null; } };
    return b;
  }
  t.S.btns = { allow_once: blade("allow_once"), terminal: blade("terminal") };
  t.S.fan = true;
  t.S.options = core.parseOptions("click=" + click, {});
  t.selectWindow({ document: { getElementById: function (id) { return id === "fan" ? fan : null; } } });
  t.click = function (key, at) { now = at; t.onClick({ detail: 1, target: t.S.btns[key] }); return sent.length; };
  return t;
}
const t = page("double"), counts = [];
counts.push(t.click("allow_once", 1000));              /* 1 回目 = 選ぶだけ */
counts.push(t.click("allow_once", 2600));              /* 1.6 秒後 = 時間切れ → 選び直し */
t.disarm();                                            /* 描き直し (札の交代・状態の変化) は選択を解く */
counts.push(t.click("allow_once", 2700));              /* 解けた後 = また選ぶだけ */
counts.push(t.click("terminal", 2800));                /* 別の羽根 = そちらを選ぶだけ */
counts.push(t.click("allow_once", 2900));              /* 元の羽根へ戻る = 選ぶだけ */
counts.push(t.click("allow_once", 3000));              /* 同じ羽根をもう 1 回 = 決まる */
const single = page("single"), before = sent.length;
const one = single.click("allow_once", 5000) - before; /* 設定で 1 回押し = 1 回で決まる */
setTimeout(function () {
  console.log(JSON.stringify({ counts: counts, one: one, paths: sent.map(function (s) { return s.path; }),
                               by: sent.map(function (s) { return s.body.by; }) }));
}, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out["counts"] == [0, 0, 0, 0, 0, 1]
    assert out["one"] == 1
    assert out["paths"] == ["/answer", "/answer"] and out["by"] == ["click", "click"]


# ---- 窓: 字の倍率の書き手は 1 か所・窓の名は板の側と同じ決まり ----

def test_window_reply_does_not_reset_the_fitted_text_size(tmp_path):
    """窓に合わせて大きくした字 (設定の倍率 × 補正) を、窓の操作の応答が設定の倍率だけへ戻さない
    (外部のレビューの再現 = 倍率 1.3・補正 1.4 で 1.82 → 1.3)。API の失敗は「当たらなかった」と返る。"""
    out = node(tmp_path, r"""
const root = { props: {}, clientWidth: 1200, style: { setProperty: function (k, v) { root.props[k] = v; } } };
const els = { fan: { style: { width: "560px", height: "330px" } }, "fan-scroll": { style: {} }, "pip-btn": {} };
const replies = [{ found: true, ok: true, pin: true }, { found: true, ok: false, pin: false }, { found: false }];
const t = loadPage(function () {
  const data = replies.shift();
  return Promise.resolve({ status: 200, json: function () { return Promise.resolve(data); } });
});
t.S.options = core.parseOptions("font=1.3", {});
t.S.fan = true;
t.S.token = "x";
t.selectWindow({ innerWidth: 1200, innerHeight: 2000,
                 document: { documentElement: root, getElementById: function (id) { return els[id] || null; } } });
t.fitFan();
const before = root.props["--font"], done = [];
t.windowCall({ pin: true }).then(function (d) { done.push(d); return t.windowCall({ shape: null }); })
  .then(function (d) { done.push(d); return t.windowCall({}); })
  .then(function (d) {
    done.push(d);
    console.log(JSON.stringify({ before: before, after: root.props["--font"], done: done, pinned: t.S.pinned }));
  });
""")
    assert out["before"] == out["after"] == str(1.3 * 1.4)
    assert out["done"] == [True, False, False] and out["pinned"] is False


def test_window_name_matches_the_board_side(tmp_path):
    """窓の名の決まりは、頁 (windowTitle) と板 (window_win.title_for) で同じ = 食い違うと板が自分の窓を見つけられない。"""
    out = node(tmp_path, r"""
console.log(JSON.stringify([core.windowTitle("small", "8765"), core.windowTitle("small", "9123"),
                            core.windowTitle("small", ""), core.windowTitle("large", "9123")]));
""")
    assert out[:3] == [window_win.title_for(8765), window_win.title_for(9123), window_win.title_for(80)]
    assert out[3] == "BLEMMA"


# ---- 板の見張り = 1 回の通信の失敗で「板が止まった」と見ない (動いている板の窓を閉じない) ----

def test_board_health_needs_failures_in_a_row(tmp_path):
    out = node(tmp_path, r"""
const h = new core.Health(3), seen = [];
h.fail(100); seen.push(h.goneSince());                 /* 1 回落ちただけ */
h.fail(1100); seen.push(h.goneSince());
h.ok(); h.fail(5000); h.fail(6000); seen.push(h.goneSince());   /* 途中で 1 回通った = 頭から数え直す */
h.fail(8000); seen.push(h.goneSince());                /* 続けて 3 回 = 最初に落ちた時刻 */
h.ok(); seen.push(h.goneSince());
console.log(JSON.stringify(seen));
""")
    assert out == [None, None, None, 5000, None]


def test_one_lost_call_does_not_count_as_a_stopped_board(tmp_path):
    """頁の配線: 板が止まったと見るのは、見張り (/pending) が続けて 3 回落ちた時か、鍵が違って見張りをやめた時だけ。
    送信が 1 回届かなかっただけでは「つながらない」と出すだけで、窓を閉じる時計は回さない。"""
    out = node(tmp_path, r"""
const realSetTimeout = setTimeout;
globalThis.setTimeout = function (fn, ms) { return realSetTimeout(fn, Math.min(ms, 2)); };     /* 頁の待ちを縮める */
let pending = 0;
const t = loadPage(function (path) {
  if (path.indexOf("/pending") === 0) {
    pending += 1;
    return pending <= 3 ? Promise.reject(new Error("down")) : new Promise(function () {});
  }
  return Promise.reject(new Error("lost"));
});
t.S.token = "x";
const out = {};
t.press("reset", "click");                             /* 送信が 1 回届かない */
realSetTimeout(function () {
  out.lost = { offline: t.S.offline, gone: t.goneSince(50) };
  t.poll();                                            /* 見張りが 3 回続けて落ちる (4 回目はつながったまま) */
  realSetTimeout(function () {
    out.down = { fails: t.S.health.fails, calls: pending, gone: t.goneSince(60) !== null };
    t.S.stopped = true;                                /* 鍵が違って見張りをやめた = その時から数える */
    out.stopped = [t.goneSince(70), t.goneSince(90)];
    t.S.stopped = false;
    t.S.health.ok();
    out.back = t.goneSince(100);
    console.log(JSON.stringify(out));
  }, 100);
}, 20);
""")
    assert out["lost"] == {"offline": True, "gone": None}
    assert out["down"] == {"fails": 3, "calls": 4, "gone": True}
    assert out["stopped"] == [70, 70] and out["back"] is None


def test_a_new_view_or_a_lost_focus_lets_go_of_paging_and_dragging(tmp_path):
    """動かさないままの pointer で新しい札の和紙を送り続けない。焦点を失ったら窓のドラッグも手放す。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.scan = new core.Scan(0);
t.S.overMore = true;
t.bumpGen();                                           /* 表示の世代が進んだ (札の交代・状態の変化) */
const afterGen = t.S.overMore;
t.S.overMore = true;
t.S.drag = { x: 1, y: 1 };
t.letGo();                                             /* 焦点を失った・頁が隠れた */
console.log(JSON.stringify({ afterGen: afterGen, afterBlur: t.S.overMore, drag: t.S.drag }));
""")
    assert out == {"afterGen": False, "afterBlur": False, "drag": None}


def test_window_moves_only_to_whole_device_pixels(tmp_path):
    """純粋な計算: 窓を動かす位置の刻み。表示倍率 150% は 2、125%・175% と頁の拡大中は 4、整数倍は 1。"""
    out = node(tmp_path, r"""
console.log(JSON.stringify({
  steps: [1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 3, 1.65, 0, NaN, undefined].map(function (r) { return core.gridStep(r); }),
  snaps: [core.snap(1001, 2), core.snap(1003, 4), core.snap(-7, 4), core.snap(-1, 4), core.snap(12.4, 1)]
}));
""")
    assert out["steps"] == [1, 4, 2, 4, 1, 4, 2, 1, 4, 1, 1, 1]
    assert out["snaps"] == [1002, 1004, -8, 0, 12]


def test_dragging_the_fan_keeps_the_window_size(tmp_path):
    """頁の配線: 掴んで運ぶ位置は刻みの倍数だけ (表示倍率 150% の画面で、奇数の位置へ動かすたびに窓が 1 画素ずつ
    育つのを防ぐ)。それでも育った窓は掴んだ時の大きさへ戻す。動かさずに離した時と、運んでいる最中に窓の大きさが
    替わった時 (札が来て開いた) は、大きさに触らない。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
const w = t.window, moves = [], sizes = [];
w.devicePixelRatio = 1.5; w.screenX = 1001; w.screenY = 301; w.outerWidth = 640; w.outerHeight = 720;
w.moveTo = function (x, y) { moves.push([x, y]); };
w.resizeTo = function (a, b) { sizes.push([a, b]); };
const target = { closest: function (s) { return s === "#fan-scroll, #closed" ? this : null; }, setPointerCapture: function () {} };
const grab = function (x, y) { t.startDrag({ button: 0, pointerType: "mouse", target: target, screenX: x, screenY: y, pointerId: 1 }); };
grab(1101, 401);
t.onPointer({ buttons: 1, screenX: 1112, screenY: 408 });      /* 窓は (1012, 308) へ */
t.onPointer({ buttons: 1, screenX: 1125, screenY: 419 });      /* (1025, 319) は奇数 = (1026, 320) へ寄せる */
const steady = sizes.length;
w.outerWidth = 646;                                            /* それでも育った (頁を拡大している時など) */
t.onPointer({ buttons: 1, screenX: 1130, screenY: 420 });
const grown = sizes.slice();
w.outerWidth = 641;
t.endDrag();                                                   /* 離す時に、残りの 1 画素も揃える */
const letGo = sizes.slice(grown.length);

sizes.length = 0; w.outerWidth = 640;
grab(1101, 401);
w.outerWidth = 700;
t.endDrag();                                                   /* 動かさずに離した = 大きさに触らない */
const still = sizes.slice();

/* 運んでいる最中に札が来て、待機の小さな窓が開いた = 掴み直してもらう (掴んだ時の小さな大きさへ戻さない) */
w.matchMedia = function () { return { matches: true }; };
w.screen = { availLeft: 0, availTop: 0, availWidth: 2560, availHeight: 1392 };
w.outerWidth = 320; w.outerHeight = 120; w.screenX = 2240; w.screenY = 1272;
t.S.mode = "small"; t.S.options = core.parseOptions("", {}); t.S.card = { id: "c1", state: "shown" };
t.S.dwell = new core.Dwell(1000, 150);
grab(2300, 1330);
t.onPointer({ buttons: 1, screenX: 2330, screenY: 1360 });
sizes.length = 0;
t.fitWindow();
const opened = sizes.slice(), dropped = t.S.drag;
w.outerWidth = 640; w.outerHeight = 720;
t.endDrag();
console.log(JSON.stringify({ moves: moves.slice(0, 3), steady: steady, grown: grown, letGo: letGo, still: still,
                             opened: opened, dropped: dropped, after: sizes.slice(opened.length) }));
""")
    assert out["moves"] == [[1012, 308], [1026, 320], [1030, 320]]
    assert out["steady"] == 0 and out["grown"] == [[640, 720]] and out["letGo"] == [[640, 720]]
    assert out["still"] == []
    assert out["opened"] == [[640, 720]] and out["dropped"] is None and out["after"] == []


def test_window_shape_waits_for_settled_sizes_and_goes_one_at_a_time(tmp_path):
    """窓の大きさを変えた直後は、外の寸法だけが先に新しくなる。その間に作った形 (枠の幅がマイナスなど) を送ると、
    板は壊れた形として窓を四角へ戻してしまう。寸法が揃うまで送らない。前の頼みの返事が来るまで、次の形も送らない
    (続けて送ると板に届く順が入れ替わり、古い方が後から当たる)。"""
    out = node(tmp_path, r"""
const reqs = [];
let release = null;
const t = loadPage(function (path, opt) {
  reqs.push(JSON.parse(opt.body));
  return new Promise(function (resolve) {
    release = function () { resolve({ status: 200, json: function () { return Promise.resolve({ found: true, ok: true, pin: false }); } }); };
  });
});
const svg = { getBoundingClientRect: function () { return { left: 10, top: 10, width: 300 }; } };
const els = { closed: { querySelector: function () { return svg; } }, "pip-btn": {} };
const w = t.window;                                    /* 頁の window そのもの = 扇の窓 */
w.document = { getElementById: function (id) { return els[id] || null; } };
t.selectWindow(w);
t.S.mode = "small";
t.S.token = "x";
t.S.options = core.parseOptions("clear=on", {});
t.S.shapeSig = "null";
w.devicePixelRatio = 1.5;
w.outerWidth = 320; w.outerHeight = 120; w.innerWidth = 626; w.innerHeight = 683;   /* 縮めた直後 = 内の寸法がまだ古い */
t.pushShape();
const unsettled = reqs.length;
w.innerWidth = 306; w.innerHeight = 83;                /* 揃った = 枠 7・題の帯 30 */
t.pushShape();
const settled = reqs.length;
svg.getBoundingClientRect = function () { return { left: 20, top: 10, width: 300 }; };
t.pushShape();                                         /* 形が変わっても、返事を待つ間は送らない */
const busy = reqs.length;
release();
setTimeout(function () {
  t.pushShape();                                       /* 返事が来た後 = 新しい形を送る */
  console.log(JSON.stringify({ unsettled: unsettled, settled: settled, busy: busy, after: reqs.length,
                               first: [reqs[0].shape.left, reqs[0].shape.top, reqs[0].shape.bare] }));
}, 20);
""")
    assert out == {"unsettled": 0, "settled": 1, "busy": 1, "after": 2, "first": [7, 30, True]}


# ---- 表示や窓が替わった直後の守り (前の表示へ向けた押し・置いたままの pointer で、新しい札が押されない) ----

FAKE_CLOCK = r"""
let now = 0;
Object.defineProperty(globalThis, "performance", { value: { now: function () { return now; } },
                                                   configurable: true, writable: true });
"""


def test_scan_shows_no_light_until_presses_count_again(tmp_path):
    """純粋な計算: 走査は、頭を先の時刻に置くとその時刻まで何も光らせない (光っていない物は押せない)。"""
    out = node(tmp_path, r"""
const s = new core.Scan(1500);
s.restart(1400);
console.log(JSON.stringify([s.index(1000, 3), s.index(1399, 3), s.index(1400, 3), s.index(2899, 3), s.index(2900, 3), s.index(5900, 3)]));
""")
    assert out == [-1, -1, 0, 0, 1, 0]


def test_a_press_right_after_the_view_changes_is_not_counted(tmp_path, clock):
    """頁の配線: 表示が替わってから 0.4 秒は、鍵・スイッチ・click の押しを数えない (前の表示へ向けた遅れた 1 押しや
    ばたつきが、新しい札の先頭 = 許可に当たらない)。過ぎれば今までどおり 1 回で送る。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
t.S.genAt = 5000;                                      /* 表示が替わった */
now = 5100;
t.press("allow_once", "key"); t.press("allow_once", "switch"); t.press("allow_once", "click"); t.press("allow_once", "touch");
const early = sent.length;
now = 5399; t.press("allow_once", "switch");
const edge = sent.length;
now = 5400; t.press("allow_once", "switch");
setTimeout(function () { console.log(JSON.stringify({ early: early, edge: edge, sent: sent })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"early": 0, "edge": 0, "sent": [{"path": "/answer", "by": "switch"}]}


def test_a_click_right_after_the_view_changes_does_not_arm_a_blade(tmp_path, clock):
    """扇の 2 回押し: 表示が替わった直後 0.4 秒の click は、選ぶ 1 回目にも数えない (外部のレビューの再現 = 替わって 0.1 秒後と
    0.5 秒後の click で許可が送られた)。前の札へ向けた 2 回押しの 2 回目が新しい札の羽根を選ぶと、人が見てから押す click は
    1 回で決まってしまう。過ぎた後は今までどおり 2 回で決まる。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
const fan = {};
const blade = { dataset: { key: "allow_once" }, disabled: false, parentNode: fan,
                classList: { add: function () {}, remove: function () {} },
                closest: function (sel) { return sel === "[data-key]" ? blade : null; } };
t.S.btns = { allow_once: blade };
t.S.fan = true;
t.S.options = core.parseOptions("", {});
t.selectWindow({ document: { getElementById: function (id) { return id === "fan" ? fan : null; } } });
function click(at) { now = at; t.onClick({ detail: 1, target: blade }); return { armed: t.S.armKey || null, sent: sent.length }; }
t.S.genAt = 5000;                                      /* 板から表示が替わった */
const seen = [click(5100), click(5500), click(5700)];  /* 0.1 秒後 = 数えない・0.5 秒後 = 選ぶだけ・0.7 秒後 = 決まる */
setTimeout(function () { console.log(JSON.stringify({ seen: seen, sent: sent })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out["seen"] == [{"armed": None, "sent": 0}, {"armed": "allow_once", "sent": 0}, {"armed": None, "sent": 1}]
    assert out["sent"] == [{"path": "/answer", "by": "click"}]


def test_undo_can_be_pressed_inside_a_short_grace(tmp_path, clock):
    """取り消しの猶予が短い板 (--undo-ms 300) でも、猶予の間に取り消しが押せる (外部のレビューの再現 = 0.4 秒の「数えない間」に
    猶予がまるごと埋まり、10 ms 刻みで押しても 1 度も送られなかった)。数えない間は猶予の半分まで。既定の 3 秒では 0.4 秒のまま。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
function run(undoMs, times) {
  const posted = [];
  const t = loadPage(function (path) { posted.push(path); return Promise.resolve(reply(200, { state: "shown" })); });
  show(t);
  t.S.card = Object.assign({}, card, { state: "deciding" });
  t.S.snap = { undo_ms: undoMs };
  t.S.genAt = 5000;                                    /* 取り消しの画面が出た */
  t.S.undoAt = 5000 + undoMs;
  return times.map(function (at) { now = at; t.S.undoing = false; t.press("undo", "switch"); return posted.length; });
}
function clickUndo(undoMs, at) {                       /* マウスの道 (onClick)。取り消しは扇の中の帯に居るが、羽根ではない */
  const posted = [];
  const t = loadPage(function (path) { posted.push(path); return Promise.resolve(reply(200, { state: "shown" })); });
  show(t);
  const fan = {}, zone = { parentNode: fan };
  const undo = { dataset: { key: "undo" }, disabled: false, parentNode: zone,
                 closest: function (sel) { return sel === "[data-key]" ? undo : null; } };
  t.S.fan = true;
  t.S.options = core.parseOptions("", {});
  t.selectWindow({ document: { getElementById: function (id) { return id === "fan" ? fan : null; } } });
  t.S.card = Object.assign({}, card, { state: "deciding" });
  t.S.snap = { undo_ms: undoMs };
  t.S.genAt = 5000;
  t.S.undoAt = 5000 + undoMs;
  now = at;
  t.onClick({ detail: 1, target: undo });
  return posted.length;
}
console.log(JSON.stringify({ short: run(300, [5100, 5149, 5150, 5299, 5300]), usual: run(3000, [5100, 5399, 5400]),
                             click: [clickUndo(300, 5100), clickUndo(300, 5150), clickUndo(3000, 5399), clickUndo(3000, 5400)] }));
""").replace("__CARD__", json.dumps(card)))
    assert out["short"] == [0, 0, 1, 2, 2]             # 0.15 秒から押せる・猶予が切れた 0.3 秒では送らない
    assert out["usual"] == [0, 0, 1]
    assert out["click"] == [0, 1, 0, 1]                # click の取り消しも同じ線・1 回で送る (2 回押しにしない)


def test_quiet_moment_is_set_only_by_a_settling_change(tmp_path):
    """bumpGen(true) (板から来た替わり・位置や焦点で行き先が決まる押しで札の中を進めた時) だけ、押しを数えない間と、
    走査の静かな 1 こまを置く。bumpGen() (数字の鍵・滞留で札の中を進めた時) は置かない = 続けて打つ 2 打目を捨てない。"""
    out = node(tmp_path, FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.scanMs = 1500; t.S.scan = new core.Scan(1500);
now = 1000; t.bumpGen(true);                           /* 板から替わった */
const fromBoard = { genAt: t.S.genAt, quiet: t.S.scan.index(2499, 3), first: t.S.scan.index(2500, 3) };
now = 5000; t.bumpGen();                               /* 札の中で画面を進めた */
const inPage = { genAt: t.S.genAt, first: t.S.scan.index(5000, 3) };
t.S.scanMs = 5000; t.S.scan = new core.Scan(5000);
now = 9000; t.bumpGen(true);                           /* 遅い走査でも、静かな間は 1.5 秒まで */
const slow = [t.S.scan.index(10499, 3), t.S.scan.index(10500, 3)];
t.S.scanMs = 0; t.S.scan = new core.Scan(0);
now = 20000; t.bumpGen(true);                          /* 走査なし = 押しを数えない間は 0.4 秒 */
console.log(JSON.stringify({ fromBoard: fromBoard, inPage: inPage, slow: slow, noScan: t.S.genAt }));
""")
    assert out["fromBoard"] == {"genAt": 1000, "quiet": -1, "first": 0}
    assert out["inPage"] == {"genAt": 1000, "first": 0}
    assert out["slow"] == [-1, 0] and out["noScan"] == 20000


def test_dwell_waits_for_the_window_to_settle(tmp_path, clock):
    """待機の小窓が札で開くと、置いたままの pointer の下に羽根が来る。開き切る前に届いた pointer (前の配置の物) で
    守りを使い切らず、落ち着いた後に pointer の下に居た釦は、入り直すまで数えない。入り直せば 1 秒で押す。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
const plain = { disabled: false, style: { setProperty: function () {} } };
t.S.btns = { allow_once: plain, deny: plain };
t.S.dwellMs = 1000; t.S.sideAt = Infinity; t.S.mode = "small"; t.S.options = core.parseOptions("", {});
const w = t.window;
w.matchMedia = function () { return { matches: true }; };
w.screen = { availLeft: 0, availTop: 0, availWidth: 2560, availHeight: 1392 };
w.outerWidth = 320; w.outerHeight = 120; w.screenX = 0; w.screenY = 0;      /* 待機の小窓が画面の左上に居る */
w.moveTo = function () {}; w.resizeTo = function () {};
w.document = { hidden: false, elementFromPoint: function () { return null; } };
w.requestAnimationFrame = function () { return 1; };
t.selectWindow(w);
function under(key) { return { closest: function (s) { return key && s === "[data-dwell]" ? { disabled: false, hidden: false, dataset: { key: key } } : null; } }; }
function move(key) { t.onPointer({ buttons: 0, pointerType: "mouse", clientX: 40, clientY: 40, target: under(key) }); }
function frames(from, to) { for (now = from; now <= to; now += 16) t.frame(now); return sent.length; }
const counts = {};
now = 0; t.fitWindow();                                /* 札が来て、小窓が 640×720 へ開き始める */
now = 20; move("deny");                                /* 開き切る前に届いた pointer = 前の配置で下に居た物 */
frames(32, 192);
now = 200; move("allow_once");                         /* 開き切った = 置いたままの pointer の下に「許可」が来た */
counts.resting = frames(216, 3000);                    /* 動かさずに約 3 秒 */
now = 3010; move(null);                                /* 一度外へ */
frames(3016, 3200);
now = 3210; move("allow_once");
counts.reentered = frames(3216, 4400);                 /* 入り直して 1 秒 */
setTimeout(function () { console.log(JSON.stringify(Object.assign(counts, { sent: sent }))); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"resting": 0, "reentered": 1, "sent": [{"path": "/answer", "by": "dwell"}]}


def test_a_window_resize_forgets_where_the_pointer_was(tmp_path):
    """窓の縁を引いた時・OS が大きさを変えた時も同じ = 前の窓の座標と、その下に居た釦を捨てて、落ち着くのを待つ。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
const handlers = {};
const doc = { hidden: false, addEventListener: function () {}, documentElement: { addEventListener: function () {} } };
const win = { document: doc, addEventListener: function (name, fn) { handlers[name] = fn; } };
t.selectWindow(win);
t.bindInputs(win);
t.S.dwell = new core.Dwell(1000, 150);
t.S.lastX = 50; t.S.over = "allow_once"; t.S.firstPointer = false;
try { handlers.resize(); } catch (e) { /* 扇の寸法合わせは DOM が要る = ここでは守りの側だけを見る */ }
console.log(JSON.stringify({ lastX: t.S.lastX, over: t.S.over, first: t.S.firstPointer, at: typeof t.S.windowAt }));
""")
    assert out == {"lastX": -1, "over": None, "first": True, "at": "number"}


# ---- 支援技術の押し・修飾キーつきのスイッチ・固定を外す・取り消せなかった知らせ ----

def test_a_click_without_a_pointer_counts_unless_a_key_made_it(tmp_path, clock):
    """読み上げの「押す」や音声操作は、pointer の無い click (detail 0) で届く = 鍵と同じ 1 回の押しとして受ける。
    鍵が自分で起こした click (直前に鍵が動いている) は、keydown で扱ったので数えない。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
const fan = {};
const btn = { dataset: { key: "allow_once" }, disabled: false, parentNode: fan };
btn.closest = function (s) { return s === "[data-key]" ? btn : null; };
t.selectWindow({ document: { hidden: false, getElementById: function (id) { return id === "fan" ? fan : null; } } });
t.S.fan = true;                                        /* 2 回押しの扇でも、支援技術の押しは 1 回で決まる */
t.S.options = core.parseOptions("", {});
now = 1000; t.S.keyAt = 900;
t.onClick({ detail: 0, target: btn });                 /* 鍵の 0.1 秒後 = 鍵が起こした click */
const afterKey = sent.length;
now = 2000;
t.onClick({ detail: 0, target: btn });                 /* 鍵は動いていない = 支援技術の押し */
setTimeout(function () { console.log(JSON.stringify({ afterKey: afterKey, sent: sent })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"afterKey": 0, "sent": [{"path": "/answer", "by": "key"}]}


def test_switch_key_with_a_modifier_does_not_press(tmp_path, clock):
    """走査中に Ctrl+Space (IME の切り替えなど) を押しても、光っている釦は押されない。素の鍵は今までどおり押す。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
t.selectWindow({ document: { hidden: false, activeElement: null } });
t.S.scanMs = 1500; t.S.switchKey = "Space"; t.S.held = {};
t.S.scanEl = { dataset: { key: "allow_once" } };
function space(extra) { t.onKeyDown(Object.assign({ code: "Space", key: " ", repeat: false, preventDefault: function () {} }, extra)); delete t.S.held.Space; }
space({ ctrlKey: true }); space({ altKey: true }); space({ metaKey: true });
const withModifier = sent.length;
space({});
setTimeout(function () { console.log(JSON.stringify({ withModifier: withModifier, sent: sent })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"withModifier": 0, "sent": [{"path": "/answer", "by": "switch"}]}


def test_unpin_that_misses_the_window_opens_no_extra_window(tmp_path):
    """「固定を外す」が窓に当たらなかった時に、常に手前の別の窓 (PiP) を増やさない。固定できなかった時は今までどおり PiP。"""
    out = node(tmp_path, r"""
const t = loadPage(function () {
  return Promise.resolve({ status: 200, json: function () { return Promise.resolve({ found: false }); } });
});
const w = t.window;
let pip = 0;
w.documentPictureInPicture = { requestWindow: function () { pip += 1; return new Promise(function () {}); } };
w.screen = { availWidth: 2560, availHeight: 1392 };
w.document = { getElementById: function (id) { return id === "pip-btn" ? {} : null; } };
t.selectWindow(w);
t.S.token = "x"; t.S.mode = "small"; t.S.options = core.parseOptions("", {});
const seen = {};
t.S.pinned = true;
t.togglePin();                                         /* 外す側が当たらない */
setTimeout(function () {
  seen.unpin = pip;
  t.S.pinned = false;
  t.togglePin();                                       /* 固定する側が当たらない = PiP で手前に出す */
  setTimeout(function () { seen.pin = pip; console.log(JSON.stringify(seen)); }, 20);
}, 20);
""")
    assert out == {"unpin": 0, "pin": 1}


def test_undo_that_came_too_late_says_so(tmp_path, clock):
    """取り消しが間に合わなかった時は、黙らずに知らせる。答えが実際に渡った (板の 409 が終わり方 answered か released を添える) なら
    「答えは渡りました」、同じ札がまだ頭に居て渡している途中 (state が deciding = 猶予が切れ、hook が受け取る所) なら
    「答えを渡している所です」= まだ渡っていない答えを「渡りました」とは言わない。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
function run(body) {
  const t = loadPage(function (path, opt) {
    sent.push(path);
    return Promise.resolve(reply(409, body));
  });
  show(t);
  t.S.lang = "ja";
  t.S.card = Object.assign({}, card, { state: "deciding" });
  t.S.undoAt = performance.now() + 3000;
  t.press("undo", "key");
  return t;
}
const answered = run({ error: "not_undoable", end: "answered" }), released = run({ error: "not_undoable", end: "released" });
const going = run({ error: "not_undoable", state: "deciding" });
setTimeout(function () {
  console.log(JSON.stringify({ sent: sent, answered: answered.S.notice || "", released: released.S.notice || "", going: going.S.notice || "" }));
}, 30);
""").replace("__CARD__", json.dumps(card)))
    late = "取り消しは間に合いませんでした (答えは渡りました)"
    assert out == {"sent": ["/undo", "/undo", "/undo"], "answered": late, "released": late,
                   "going": "取り消しは間に合いませんでした (答えを渡している所です)"}


def test_undo_refused_because_another_page_undid_it_is_not_called_late(tmp_path, clock):
    """答えが渡らない 409 では「間に合わなかった」と言わない = ほかの頁が先に取り消した (shown・外部のレビューの再現)・
    時間切れ (expired)・接続の終了 (disconnected・反証役の再現)・終わり方が分からない (札が替わった後の形と、板が返さない形)。
    取り直した表示と終わりの文に任せる。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
function run(body) {
  const t = loadPage(function () { return Promise.resolve(reply(409, body)); });
  show(t);
  t.S.lang = "ja";
  t.S.card = Object.assign({}, card, { state: "deciding" });
  t.S.undoAt = performance.now() + 3000;
  t.press("undo", "key");
  return t;
}
const pages = { undone: run({ error: "not_undoable", state: "shown" }),
                expired: run({ error: "not_undoable", end: "expired" }), disconnected: run({ error: "not_undoable", end: "disconnected" }),
                unknown: run({ error: "not_undoable" }), other: run({ error: "too_late" }) };
setTimeout(function () {
  const out = {};
  Object.keys(pages).forEach(function (k) { out[k] = pages[k].S.notice || ""; });
  console.log(JSON.stringify(out));
}, 30);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"undone": "", "expired": "", "disconnected": "", "unknown": "", "other": ""}


def test_a_failed_watch_is_not_kept_as_the_target_of_a_kick(tmp_path):
    """終わった見張りを「今の見張り」として持ち続けない = 後から来た取り直し (kick) が、印だけを残して 1 回ぶんの失敗を
    数え落とす事が無い。"""
    out = node(tmp_path, r"""
const realSetTimeout = setTimeout;
globalThis.setTimeout = function (fn, ms) { return ms >= 1000 ? 0 : realSetTimeout(fn, ms); };   /* 見張りの期限と、次の見張りは走らせない */
const t = loadPage(function () { return Promise.reject(new Error("down")); });
t.S.token = "x";
t.poll();
realSetTimeout(function () { console.log(JSON.stringify({ abort: t.S.abort, fails: t.S.health.fails })); }, 20);
""")
    assert out == {"abort": None, "fails": 1}


def test_scan_light_is_brought_into_view_outside_the_fan(tmp_path, clock):
    """扇に載らない札は列が窓より長くなる = 走査の光が当たった釦を、見える所へ送る (扇は窓に収まるので送らない)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
show(t);
let brought = 0;
function item() { return { classList: { add: function () {}, remove: function () {} }, scrollIntoView: function () { brought += 1; },
                           getBoundingClientRect: function () { return { top: 10, left: 10 }; } }; }
t.selectWindow({ document: { hidden: false }, requestAnimationFrame: function () { return 1; } });
t.S.sideAt = Infinity; t.S.scanMs = 1500; t.S.scan = new core.Scan(1500); t.S.scanList = [item(), item()];
const seen = {};
t.S.fan = false; t.S.scan.restart(0);
now = 10; t.frame(now); seen.list = brought;               /* 1 つ目に光 */
now = 1510; t.frame(now); seen.next = brought;             /* 2 つ目へ */
t.S.fan = true; t.S.mode = "large"; t.S.scan.restart(3000);
now = 3010; t.frame(now); seen.fan = brought;              /* 扇では送らない */
console.log(JSON.stringify(seen));
""").replace("__CARD__", json.dumps(card)))
    assert out == {"list": 1, "next": 2, "fan": 2}


# ---- 4 巡目 (反証役の所見): 送られた列・人が置いた焦点・スイッチの 2 打目・入口ごとの見張り ----

DWELL_STAGE = r"""
const plain = { disabled: false, style: { setProperty: function () {} } };
function stage(t, dwellMs) {                           /* 滞留を回せる最小の窓 (DOM なし) */
  t.S.btns = { allow_once: plain, deny: plain };
  t.S.dwellMs = dwellMs; t.S.dwell = new core.Dwell(dwellMs, 150);
  t.S.sideAt = Infinity; t.S.mode = "small"; t.S.options = core.parseOptions("", {});
  t.selectWindow({ document: { hidden: false, elementFromPoint: function () { return null; } },
                   requestAnimationFrame: function () { return 1; } });
}
function under(key) { return { closest: function (s) { return key && s === "[data-dwell]" ? { disabled: false, hidden: false, dataset: { key: key } } : null; } }; }
function move(t, key, buttons) { t.onPointer({ buttons: buttons || 0, pointerType: "mouse", clientX: 40, clientY: 40, target: under(key) }); }
function frames(t, from, to) { for (now = from; now <= to; now += 16) t.frame(now); return sent.length; }
"""


def test_a_scrolled_list_does_not_press_what_arrives_under_the_pointer(tmp_path, clock):
    """頁や列が送られると、置いたままの pointer の下の物が入れ替わる (走査の光が窓の外の釦を見える所へ送る・ホイール)。
    送られた後に pointer の下へ来た釦は、入り直すまで滞留で押さない (反証役の再現 = 滞留と走査を両方入れた板で、
    誰も押していないのに答えが送られた)。入り直せば押せる。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + DWELL_STAGE + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t); stage(t, 500);
const counts = {};
now = 0; move(t, null);                                /* 釦と釦の間に pointer を置いたまま */
frames(t, 16, 2000);
now = 2010; t.scrolled();                              /* 列が送られた (scroll の知らせ) */
now = 2020; move(t, "allow_once");                     /* ブラウザが配る知らせ = 置いたままの pointer の下に釦が来た */
counts.resting = frames(t, 2036, 5000);                /* 動かさずに約 3 秒 (滞留 0.5 秒の 6 倍) */
now = 5010; move(t, null);
frames(t, 5016, 5200);
now = 5210; move(t, "allow_once");                     /* 入り直す */
counts.reentered = frames(t, 5216, 6000);
setTimeout(function () { console.log(JSON.stringify(Object.assign(counts, { sent: sent }))); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"resting": 0, "reentered": 1, "sent": [{"path": "/answer", "by": "dwell"}]}


def test_the_scan_light_scrolling_the_list_arms_the_same_guard(tmp_path, clock):
    """走査の光が釦を見える所へ実際に送った時は、scroll の知らせを待たずに、その場で同じ守りを掛ける (知らせは次のこまに来る)。
    光が進んでも何も送らなかった時 (列が窓に収まる) は掛けない。文書の scroll の聞き手は capture で付く (要素の送りは泡立たない)。
    聞き手が守るのは、文書そのものと、押せる的 (滞留の釦) を含む列の送りだけ = 本文の枠・和紙の送りは素通し。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
show(t);
function item(moves) {                                 /* moves = scrollIntoView で列が送られて、釦の位置が変わる */
  let top = 300;
  return { classList: { add: function () {}, remove: function () {} }, scrollIntoView: function () { if (moves) top -= 120; },
           getBoundingClientRect: function () { return { top: top, left: 20 }; } };
}
const handlers = {}, opts = {};
const doc = { nodeType: 9, hidden: false, addEventListener: function (name, fn, opt) { handlers[name] = fn; opts[name] = opt; },
              documentElement: { addEventListener: function () {} } };
const win = { document: doc, addEventListener: function () {}, requestAnimationFrame: function () { return 1; } };
t.selectWindow(win); t.bindInputs(win);
t.S.sideAt = Infinity; t.S.scanMs = 500; t.S.scan = new core.Scan(500); t.S.scanList = [item(true), item(true)];
t.S.fan = false; t.S.scan.restart(0);
t.S.dwellMs = 0;                                       /* ここでは守りが掛かる所だけを見る (滞留のこまは回さない) */
const seen = { capture: !!(opts.scroll && opts.scroll.capture) };
function reset() { t.S.windowAt = -1e9; t.S.firstPointer = false; t.S.over = "allow_once"; t.S.lastX = 77; }
reset();
now = 10; t.frame(now);                                /* 光が当たり、見える所へ送った */
seen.byLight = { at: t.S.windowAt, first: t.S.firstPointer, over: t.S.over };
t.S.scanList = [item(false), item(false)]; t.S.scan.restart(1000); t.S.scanEl = null; reset();
now = 1010; t.frame(now);                              /* 光が進んだだけ (送っていない) */
seen.stillLight = { at: t.S.windowAt, first: t.S.firstPointer, over: t.S.over };
reset();
now = 1900; handlers.scroll();                         /* 知らせの形が分からない = 守る */
seen.byEvent = { at: t.S.windowAt, first: t.S.firstPointer, over: t.S.over, lastX: t.S.lastX };
function box(buttons) { return { nodeType: 1, querySelectorAll: function (s) { return s === "[data-dwell]" ? buttons : []; } }; }
const scrolls = { list: box([{ hidden: false, disabled: false }]), text: box([]), hiddenMore: box([{ hidden: true, disabled: false }]),
                  disabledOnly: box([{ hidden: false, disabled: true }]), page: doc };
seen.targets = {};
Object.keys(scrolls).forEach(function (k, i) {
  reset();
  now = 3000 + i; handlers.scroll({ target: scrolls[k] });
  seen.targets[k] = t.S.windowAt === now;
});
console.log(JSON.stringify(seen));
""").replace("__CARD__", json.dumps(card)))
    assert out["capture"] is True
    assert out["byLight"] == {"at": 10, "first": True, "over": None}
    assert out["stillLight"] == {"at": -1e9, "first": False, "over": "allow_once"}
    assert out["byEvent"] == {"at": 1900, "first": True, "over": None, "lastX": 77}   # 位置は捨てない (見つめて送る動きが続く)
    assert out["targets"] == {"list": True, "text": False, "hiddenMore": False, "disabledOnly": False, "page": True}


def test_a_key_press_on_a_page_button_keeps_the_focus_where_the_person_put_it(tmp_path, clock):
    """鍵で使う人のために、表示が替わると先頭の釦へ焦点を置く。ただし、人が自分で置いた焦点 (配色・設定などの釦) は奪わない
    (反証役の再現 = 配色の釦を鍵で 2 回押すと、2 回目が焦点の移った先頭の羽根 = 許可に当たった)。
    焦点がどこにも無い時は先頭へ置く。隠れた釦・押せなくなった釦に残る焦点は「どこにも無い」と数える。前に来た焦点が
    使われないまま消えた後 (S.focusSeen) は置かない = その決まりは、頁を init() ごと回す試験 (page(...)) が見る。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
show(t);
t.S.scan = new core.Scan(0); t.S.scanMs = 0; t.S.lastInput = "key"; t.S.fan = true;
let focused = 0;
const first = { focus: function () { focused += 1; } };
t.S.scanList = [first];
const body = { classList: { toggle: function () {} } }, theme = { dataset: { key: "theme" } }, gone = { dataset: { key: "allow_once" } };
const inHidden = { dataset: { key: "undo" }, closest: function (s) { return s === "[hidden]" ? {} : null; } };   /* 入れ物が隠れた釦 */
const disabled = { dataset: { key: "undo" }, disabled: true };                  /* 押せなくなった釦 */
const doc = { hidden: false, body: body, documentElement: {}, elementFromPoint: function () { return null; },
              contains: function (e) { return e === theme || e === body || e === inHidden || e === disabled; } };
t.selectWindow({ document: doc });
const seen = {};
/* この試験は bumpGen を直に呼ぶ (焦点の知らせの聞き手を通らない) = 「来た焦点」の印は、ここで手で置く */
t.S.focusSeen = false;
doc.activeElement = theme; t.bumpGen(true); seen.onThemeButton = focused;      /* 人が置いた焦点 = 奪わない */
doc.activeElement = body; t.bumpGen(true); seen.nowhere = focused;             /* どこにも無い = 先頭へ */
t.S.focusSeen = false;                                                         /* (代用品の first.focus は焦点を動かさない) */
doc.activeElement = inHidden; t.bumpGen(true); seen.hiddenBox = focused;       /* ブラウザが外す前の、隠れた入れ物の中の釦 = どこにも無い */
doc.activeElement = disabled; t.bumpGen(true); seen.disabledButton = focused;  /* ブラウザが外す前の、押せなくなった釦 = どこにも無い */
doc.activeElement = body; t.bumpGen(true, true); seen.leftAlone = focused;     /* 置かない印 (取り消して戻った・窓を移った) */
t.S.focusSeen = true;                                                          /* 来た焦点が、使われないまま消えている */
doc.activeElement = body; t.bumpGen(true); seen.lostFocus = focused;           /* = 置かない */
doc.activeElement = gone; t.bumpGen(true); seen.removedBlade = focused;        /* 描き直しで消えた羽根に在った焦点 = 置かない */
console.log(JSON.stringify(seen));
""").replace("__CARD__", json.dumps(card)))
    assert out == {"onThemeButton": 0, "nowhere": 1, "hiddenBox": 2, "disabledButton": 3, "leftAlone": 3,
                   "lostFocus": 3, "removedBlade": 3}, out


def test_a_press_and_release_inside_one_frame_still_blocks_the_dwell(tmp_path, clock):
    """押した・離したその場で滞留を解く (こま単位の見張りだけだと、1 こまの内に押して離す速い click の後に
    「入り直すまで数えない」が掛からない)。pointerdown / pointerup の聞き手から入る。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + DWELL_STAGE + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t); stage(t, 1000);
const handlers = {};
const doc = { hidden: false, elementFromPoint: function () { return null; }, addEventListener: function (name, fn, opt) { if (opt && opt.capture) handlers[name] = fn; },
              documentElement: { addEventListener: function () {} } };
const win = { document: doc, addEventListener: function () {}, requestAnimationFrame: function () { return 1; } };
t.selectWindow(win); t.bindInputs(win);
const counts = {};
now = 0; move(t, null); frames(t, 16, 700);            /* 守りを使い切ってから */
now = 710; move(t, "allow_once");
frames(t, 726, 1200);                                  /* 0.5 秒ぶん数えた所で */
now = 1204; handlers.pointerdown({ pointerType: "mouse" });
const down = t.S.down;
now = 1206; handlers.pointerup({});                    /* 同じこまの内に押して離した */
counts.afterClick = frames(t, 1216, 4000);             /* そのまま 2.8 秒 = 滞留では押されない */
now = 4010; move(t, null); frames(t, 4016, 4200);
now = 4210; move(t, "allow_once");
counts.reentered = frames(t, 4216, 5400);
setTimeout(function () { console.log(JSON.stringify(Object.assign(counts, { down: down, sent: sent }))); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"afterClick": 0, "reentered": 1, "down": True, "sent": [{"path": "/answer", "by": "dwell"}]}


def test_a_dwell_shorter_than_the_quiet_moment_cannot_press_right_after_a_change(tmp_path, clock):
    """0.4 秒より短い滞留 (URL や --set で入れた時) でも、板から表示が替わって 0.4 秒の内には押さない
    (反証役の再現 = dwell=0.3 と pointer の揺れ 1 こまで、替わって 368 ms 後に新しい札の許可が出た)。
    押しを捨てるのではなく、数え始めを遅らせる = 見続けていれば 0.4 秒を過ぎた所で押せる。1 秒の滞留は今までどおり。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + DWELL_STAGE + r"""
function run(dwellMs, until) {
  const posted = [];
  const t = loadPage(function (path, opt) { posted.push(now); return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 })); });
  show(t); stage(t, dwellMs);
  now = 0; move(t, null);
  for (now = 16; now <= 4990; now += 16) t.frame(now);  /* 守りを使い切ってから */
  now = 5000; t.S.genAt = 5000;                         /* 板から表示が替わった */
  now = 5010; move(t, "allow_once");                    /* 揺れで入り直した pointer が、新しい札の許可の上に来た */
  for (now = 5016; now <= until; now += 16) t.frame(now);
  return posted;
}
const short = run(300, 6000), usual = run(1000, 6500);
setTimeout(function () { console.log(JSON.stringify({ short: short, usual: usual })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert len(out["short"]) == 1 and 5400 <= out["short"][0] <= 5460, out   # 替わって 0.4 秒より後・見続けていれば押せる
    assert len(out["usual"]) == 1 and 6010 <= out["usual"][0] <= 6050, out   # 1 秒の滞留は入ってから 1 秒 (遅らせない)


def test_the_first_pointer_after_the_window_settles_is_the_one_that_is_blocked(tmp_path, clock):
    """窓が開く途中に届いた pointer (前の配置の物) で「最初の 1 つ」を使い切らない。窓が落ち着いた後 (0.7 秒後) に初めて
    「許可」の上で届いた pointer も、入り直すまで数えない (反証役の再現 = 落ち着くまでの間に「最初の 1 つ」を立て直す行を
    外しても、今までの試験は通った)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + DWELL_STAGE + r"""
const t = loadPage(function (path, opt) {
  sent.push({ path: path, by: JSON.parse(opt.body).by });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t); stage(t, 1000);
const counts = {};
now = 0; t.windowMoved();                              /* 窓が開き始めた */
now = 20; move(t, "deny");                             /* 開く途中に届いた pointer = 前の配置で下に居た物 */
frames(t, 32, 690);                                    /* 落ち着くまで (0.6 秒) */
now = 700; move(t, "allow_once");                      /* 落ち着いた後に初めて届いた pointer = 置いたままの所に「許可」が来ていた */
counts.resting = frames(t, 716, 3500);                 /* 動かさずに約 2.8 秒 */
now = 3510; move(t, null);
frames(t, 3516, 3700);
now = 3710; move(t, "allow_once");
counts.reentered = frames(t, 3716, 4900);
setTimeout(function () { console.log(JSON.stringify(Object.assign(counts, { sent: sent }))); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"resting": 0, "reentered": 1, "sent": [{"path": "/answer", "by": "dwell"}]}


def test_the_scan_stays_quiet_after_a_change_even_when_it_resumes(tmp_path, clock):
    """板から表示が替わった後の「走査の静かな 1 こま」は、走査が止まっていた所から動き出す時にも持ち越す
    (pointer が止まって走査が戻る時)。持ち越さないと、替わった直後に先頭 (許可) が光る。窓に焦点が戻る時は、焦点の時刻から
    静かな 1 こまを数え直す (替わった後の間より長い = 焦点を得た瞬間に、光が許可へ跳ばない・頁の点検 F3)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
show(t);
function item(name) { return { name: name, classList: { add: function () {}, remove: function () {} } }; }
const handlers = {};
const doc = { hidden: false, body: { classList: { toggle: function () {} } }, addEventListener: function () {}, documentElement: { addEventListener: function () {} },
              elementFromPoint: function () { return null; } };
const win = { document: doc, addEventListener: function (name, fn) { handlers[name] = fn; }, requestAnimationFrame: function () { return 1; } };
t.selectWindow(win); t.bindInputs(win);
t.S.dwellMs = 0; t.S.dwell = new core.Dwell(0, 150); t.S.sideAt = Infinity; t.S.fan = true; t.S.mode = "large";
t.S.scanMs = 1500; t.S.scan = new core.Scan(1500); t.S.scanList = [item("first"), item("second")];
function lit(at) { now = at; t.frame(now); return t.S.scanEl ? t.S.scanEl.name : null; }
const seen = {};
t.S.pointerAt = 3600;                                  /* 札が替わる 1.4 秒前に pointer が動いた = 走査は 5100 まで止まる */
lit(4000);
now = 5000; t.bumpGen(true);                           /* 板から表示が替わった = 静かな間は 6500 まで */
seen.resumed = [lit(5116), lit(6400), lit(6510)];      /* pointer が止まって走査が戻っても、6500 までは光らない */
now = 9000; t.bumpGen(true);                           /* もう 1 度替わった = 静かな間は 10500 まで */
now = 9200; handlers.focus();                          /* 窓に焦点が戻った = 静かな間は焦点から 1.5 秒 (10700 まで) */
seen.focused = [lit(9216), lit(10600), lit(10710)];
console.log(JSON.stringify(seen));
""").replace("__CARD__", json.dumps(card)))
    assert out == {"resumed": [None, None, "first"], "focused": [None, None, "first"]}


def test_moving_the_window_to_a_corner_counts_as_a_window_change(tmp_path):
    """設定で窓を隅へ動かした時も「窓の位置が変わった」= 前の位置での pointer と、その下に居た釦を捨てる。"""
    out = node(tmp_path, FAKE_CLOCK + r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.options = core.parseOptions("pos=br", {});
const w = t.window;
const moved = [];
w.screen = { availLeft: 0, availTop: 0, availWidth: 2560, availHeight: 1392 };
w.outerWidth = 640; w.outerHeight = 720;
w.moveTo = function (x, y) { moved.push([x, y]); };
t.S.lastX = 50; t.S.over = "allow_once"; t.S.firstPointer = false; t.S.windowAt = -1e9;
now = 700; t.placeWindow();
const corner = { moved: moved, lastX: t.S.lastX, over: t.S.over, first: t.S.firstPointer, at: t.S.windowAt };
t.S.options = core.parseOptions("pos=keep", {});
t.S.lastX = 50; t.S.windowAt = -1e9;
now = 900; t.placeWindow();                            /* 動かさない設定 = 何も捨てない */
console.log(JSON.stringify({ corner: corner, keep: { moved: moved.length, lastX: t.S.lastX, at: t.S.windowAt } }));
""")
    assert out["corner"] == {"moved": [[1920, 672]], "lastX": -1, "over": None, "first": True, "at": 700}
    assert out["keep"] == {"moved": 1, "lastX": 50, "at": -1e9}


def test_a_waiting_retry_and_a_new_token_do_not_run_two_watches(tmp_path):
    """板が落ちている間は、次の取り直しを timer で待つ。その間に見張りを起こし直しても (新しい token の URL を貼った時)、
    待っていた取り直しは捨てる = 見張りは常に 1 本 (反証役の再現 = 2 本が並走し続けた)。"""
    out = node(tmp_path, r"""
const timers = [];
const realSetTimeout = setTimeout;
globalThis.setTimeout = function (fn, ms) { if (ms >= 1000) { const id = { fn: fn, ms: ms, live: true }; timers.push(id); return id; } return realSetTimeout(fn, ms); };
globalThis.clearTimeout = function (id) { if (id && typeof id === "object" && "live" in id) id.live = false; };
let calls = 0;
const t = loadPage(function () { calls += 1; return Promise.reject(new Error("down")); });
t.S.token = "x";
t.poll();                                              /* 落ちている板 = 失敗して、取り直しを待つ */
realSetTimeout(function () {
  const waiting = timers.filter(function (x) { return x.live && x.ms < 40000; }).length;
  t.poll();                                            /* 待っている間に、見張りを起こし直す */
  realSetTimeout(function () {
    const live = timers.filter(function (x) { return x.live && x.ms < 40000; }).length;
    console.log(JSON.stringify({ waiting: waiting, liveRetries: live, calls: calls }));
  }, 20);
}, 20);
""")
    assert out == {"waiting": 1, "liveRetries": 1, "calls": 2}   # 前の待ちは捨てられ、新しい待ちが 1 つだけ残る


def test_the_key_that_made_a_click_is_remembered_by_the_key_listeners(tmp_path, clock):
    """鍵が自分で起こした click (押したままの Enter の繰り返しなど) を数えない守りは、keydown / keyup の聞き手が
    「鍵が動いた時刻」を覚える事に懸かっている。聞き手から入れて確かめる (時刻を手で置かない)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) { sent.push(JSON.parse(opt.body).by); return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 })); });
show(t);
const handlers = {};
const btn = { dataset: { key: "allow_once" }, disabled: false, closest: function (s) { return s === "[data-key]" ? btn : null; } };
const doc = { hidden: true, activeElement: null, addEventListener: function (name, fn) { handlers[name] = handlers[name] || fn; }, documentElement: { addEventListener: function () {} } };
const win = { document: doc, addEventListener: function () {} };
t.selectWindow(win); t.bindInputs(win);
t.S.genAt = -1e9; t.S.keyAt = -1e9;
now = 5000; handlers.keydown({ key: "Enter", code: "Enter", repeat: true, preventDefault: function () {} });   /* 押したままの Enter の繰り返し */
now = 5100; handlers.click({ detail: 0, target: btn });        /* その鍵が起こした click */
const byRepeat = sent.length;
now = 6000; handlers.keyup({ key: "Enter", code: "Enter" });
now = 6100; handlers.click({ detail: 0, target: btn });        /* 鍵を離した直後の click も、鍵の物 */
const byKeyup = sent.length;
now = 7000; handlers.click({ detail: 0, target: btn });        /* 鍵が 0.5 秒より前 = 支援技術の押し */
setTimeout(function () { console.log(JSON.stringify({ byRepeat: byRepeat, byKeyup: byKeyup, sent: sent })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"byRepeat": 0, "byKeyup": 0, "sent": ["key"]}


def test_a_new_card_forgets_a_send_that_never_came_back(tmp_path, clock):
    """札が替わったら、前の札への送信の印を持ち越さない。板の写しを当てる所 (apply) から入れて確かめる
    (返らない送信が残っていても、新しい札は押せる)。新しい札は最後まで描けている (描画の途中で止まって後半を通らない形にしない)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + FAKE_CLOCK + r"""
const t = loadPage(function (path, opt) { sent.push(JSON.parse(opt.body).id); return new Promise(function () {}); });   /* 返らない送信 */
show(t);
const el = { hidden: true, style: {}, classList: { add: function () {}, remove: function () {}, toggle: function () {} }, dataset: {}, appendChild: function () {},
             insertBefore: function () {}, replaceChildren: function () {}, setAttribute: function () {}, querySelector: function () { return null; },
             querySelectorAll: function () { return []; }, getBoundingClientRect: function () { return { top: 0, left: 0, width: 0, height: 0 }; } };
el.parentNode = el;
t.selectWindow({ document: { hidden: false, body: el, documentElement: el, activeElement: el, elementFromPoint: function () { return null; },
                             getElementById: function () { return el; }, createElement: function () { return Object.assign({}, el, { dataset: {}, style: {} }); },
                             querySelector: function () { return null; }, querySelectorAll: function () { return []; }, contains: function () { return true; } },
                 requestAnimationFrame: function () { return 1; } });
t.S.scan = new core.Scan(0); t.S.scanMs = 0; t.S.lang = "ja"; t.S.fan = false; t.S.mode = "large"; t.S.genAt = -1e9;
now = 1000; t.press("allow_once", "key");              /* 1 枚目を押した = 送信は返らない */
const stuck = t.S.answering;
const next = Object.assign({}, card, { id: "card-2", view_seq: 9 });
now = 2000;
let drawn = "";
try { t.apply({ seq: 9, card: next, queue: 0, last: null, light: null, states: [], stats: {}, undo_ms: 3000 }); } catch (e) { drawn = "描けない: " + e.message; }
const cleared = t.S.answering;
t.S.btns = { allow_once: { disabled: false } };
now = 3000; t.press("allow_once", "key");              /* 2 枚目も押せる */
setTimeout(function () { console.log(JSON.stringify({ stuck: stuck, cleared: cleared, sent: sent, drawn: drawn })); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out["stuck"] is True and out["cleared"] is False, out
    assert out["sent"] == [card["id"], "card-2"], out
    assert out["drawn"] == "", out


def test_omitted_optional_fields_are_announced_on_the_card(tmp_path):
    """MCP の問いに、板で描けない任意の欄がある時 (hook が payload の omitted に題を入れる) は、札に知らせを出す
    = 人が見ていない欄を空のまま送らせない。無ければ何も足さない。"""
    out = node(tmp_path, r"""
const field = { name: "ok", title: "進めますか", multi: false, required: true,
                options: [{ label: "はい", value: "y" }, { label: "いいえ", value: "n" }] };
function texts(payload, lang) {
  const card = { id: "e1", kind: "elicitation", state: "shown", payload: payload };
  return core.buildScreen(card, core.newUi(card.id), lang).blocks.map(function (b) { return b.text; });
}
const base = { head: "srv", text: "確認", fields: [field] };
console.log(JSON.stringify({
  ja: texts(Object.assign({ omitted: ["題", "理由"] }, base), "ja"),
  en: texts(Object.assign({ omitted: ["title", "reason"] }, base), "en"),
  none: texts(base, "ja"),
  junk: texts(Object.assign({ omitted: [3, "", null] }, base), "ja")
}));
""")
    assert len(out["ja"]) == 1 and "2 個" in out["ja"][0] and "題・理由" in out["ja"][0] and "端末で答える" in out["ja"][0]
    assert len(out["en"]) == 1 and out["en"][0].startswith("2 optional") and "title, reason" in out["en"][0]
    assert out["none"] == [] and out["junk"] == []


def test_fan_script_never_splits_a_surrogate_pair(tmp_path):
    """書の帯の切れ目が、対の字 (絵文字・一部の漢字) の真ん中に来ない。"""
    out = node(tmp_path, r"""
const lone = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/;
const bad = [];
for (let k = 0; k <= 8; k++) {
  const text = "あ".repeat(k) + "😀".repeat(12);
  const r = core.fanScript(text, [100, 100]);
  if (r.lines.some(function (line) { return lone.test(line); })) bad.push(k);
}
console.log(JSON.stringify(bad));
""")
    assert out == []


def test_window_shape_is_dropped_while_the_page_is_zoomed(tmp_path):
    """頁を拡大・縮小している間は、内の寸法だけが倍率で変わって形が扇からずれる = 切り抜きをやめて四角へ戻す。
    大きさを変えた直後の一瞬 (0.8 秒未満) は、今までどおり何も送らずに待つ。"""
    out = node(tmp_path, FAKE_CLOCK + r"""
const reqs = [];
const t = loadPage(function (path, opt) {
  reqs.push(JSON.parse(opt.body));
  return Promise.resolve({ status: 200, json: function () { return Promise.resolve({ found: true, ok: true, pin: false }); } });
});
const svg = { getBoundingClientRect: function () { return { left: 10, top: 10, width: 300 }; } };
const els = { closed: { querySelector: function () { return svg; } }, "pip-btn": {} };
const w = t.window;
w.document = { getElementById: function (id) { return els[id] || null; } };
t.selectWindow(w);
t.S.mode = "small"; t.S.token = "x"; t.S.options = core.parseOptions("clear=on", {}); t.S.shapeSig = "null";
w.devicePixelRatio = 1.5;
w.outerWidth = 320; w.outerHeight = 120; w.innerWidth = 306; w.innerHeight = 83;      /* 倍率 100% = 枠 7・題の帯 30 */
now = 0; t.pushShape();
setTimeout(function () {
  const cut = reqs.length;
  w.devicePixelRatio = 1.65; w.innerWidth = 278; w.innerHeight = 75;                 /* 頁を 110% に拡大 = 枠 21 に見える */
  now = 1000; t.pushShape();
  now = 1700; t.pushShape();
  const waiting = reqs.length;
  now = 1800; t.pushShape();
  setTimeout(function () {
    console.log(JSON.stringify({ cut: cut, first: reqs[0].shape === null, waiting: waiting, after: reqs.length,
                                 last: reqs[reqs.length - 1].shape }));
  }, 20);
}, 20);
""")
    assert out == {"cut": 1, "first": False, "waiting": 1, "after": 2, "last": None}


# ---- 外部のレビューの所見: 滞留中の押下・固まった送信・欄の説明 ----

def test_dwell_never_fires_while_a_button_is_held(tmp_path, clock):
    """見つめて押す設定でも、釦を押したまま (文字の選択・ドラッグ) 羽根の上で止まっただけでは答えが出ない。
    離した後も、羽根へ入り直すまで数えない。押していなければ、今までどおり 1 秒で押す。
    入り直したと見るのは、釦の無い所に 150 ms (揺れの許し) より長く居てから戻った時。11/7 に期待を安全の向きへ書き換えた =
    前は釦なしの 3 こま (32 ms) で「外へ出た」と見ていた。縁の揺れで、見ていない羽根を押さないため (2 巡目 i19)。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
let now = 0;
Object.defineProperty(globalThis, "performance", { value: { now: function () { return now; } },
                                                   configurable: true, writable: true });
const t = loadPage(function (path, opt) {
  sent.push({ path: path, body: JSON.parse(opt.body) });
  return Promise.resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 }));
});
show(t);
t.S.btns = { allow_once: { disabled: false, style: { setProperty: function () {} } } };
t.S.dwellMs = 1000;
t.S.sideAt = Infinity;                                 /* 脇の表示の更新 (DOM) は回さない */
t.selectWindow({ document: { hidden: false }, requestAnimationFrame: function () { return 1; } });
function frames(from, to) { for (now = from; now <= to; now += 16) t.frame(now); return sent.length; }
const counts = {};
t.S.over = "allow_once";
t.S.down = true;                                       /* 押したまま羽根の上で 1.5 秒 */
counts.held = frames(0, 1500);
t.S.down = false;                                      /* 離して、そのまま留まる = 入り直していない */
counts.released = frames(1516, 3000);
t.S.over = null; frames(3016, 3200);                   /* 一度外へ出る (150 ms より長く) */
t.S.over = "allow_once";
counts.reentered = frames(3216, 4400);                 /* 入り直して 1 秒 = 押す */
setTimeout(function () { console.log(JSON.stringify(Object.assign(counts, { by: sent.map(function (s) { return s.body.by; }) }))); }, 20);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"held": 0, "released": 0, "reentered": 1, "by": ["dwell"]}


def test_pointer_events_report_the_held_button(tmp_path):
    """押している事は、動きの知らせに載る釦の状態から拾う (窓の外で押し始めたドラッグも分かる)。"""
    out = node(tmp_path, r"""
const t = loadPage(function () { throw new Error("通信しない"); });
t.S.dwell = new core.Dwell(1000, 150);
t.S.options = core.parseOptions("", {});
const target = { closest: function () { return null; } };
const move = function (buttons) { t.onPointer({ buttons: buttons, pointerType: "mouse", clientX: 5, clientY: 5, target: target }); return t.S.down; };
const seen = [move(1), move(0), move(4), move(0)];
t.S.down = true;
t.letGo();                                             /* 焦点を失ったら、押している印も手放す */
seen.push(t.S.down);
console.log(JSON.stringify(seen));
""")
    assert out == [True, False, True, False, False]


def test_a_stuck_answer_does_not_block_the_next_card(tmp_path, clock):
    """/answer が返らないまま次の札が来ても、新しい札は押せる。遅れて返った古い送信が、新しい送信の印を消さない。
    返らない送信そのものも、期限で失敗として扱う。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
const realSetTimeout = setTimeout;
const waits = [];
globalThis.setTimeout = function (fn, ms) { waits.push(ms); return realSetTimeout(fn, ms >= 8000 ? 60 : ms); };   /* 送信の期限 8 秒を縮める */
let releaseFirst = null, releaseSecond = null, aborted = 0;
function held(setter) { return new Promise(function (resolve) { setter(function () { resolve(reply(200, { undo_ms: 3000, undo_remaining: 3 })); }); }); }
const t = loadPage(function (path, opt) {
  sent.push({ path: path, id: JSON.parse(opt.body).id });
  if (sent.length === 1) return held(function (f) { releaseFirst = f; });
  if (sent.length === 2) return held(function (f) { releaseSecond = f; });
  return new Promise(function (_, reject) { opt.signal.addEventListener("abort", function () { aborted += 1; reject(new Error("aborted")); }); });
});
show(t);
t.press("allow_once", "click");                        /* 1 枚目: 返らない送信 */
const stuck = t.S.answering;
t.forgetSends();                                       /* 札が替わった (頁は新しい札を受けた時にこれを呼ぶ) */
t.S.card = Object.assign({}, card, { id: "next-card" });
t.S.key = "next";
t.press("allow_once", "click");                        /* 2 枚目: 押せる */
const second = sent.length;
const during = t.S.answering;
releaseFirst();                                        /* 1 枚目の返事が遅れて届く (2 枚目はまだ返っていない) */
realSetTimeout(function () {
  const afterLate = t.S.answering;                     /* 古い返事は、2 枚目の送信中の印を消さない */
  releaseSecond();
  realSetTimeout(function () {
    const afterSecond = t.S.answering;                 /* 2 枚目の返事で、印が消える */
    t.forgetSends();
    t.S.card = Object.assign({}, card, { id: "third-card" });
    t.S.key = "third";
    t.press("allow_once", "click");                    /* 3 枚目: 返らない → 期限で失敗 */
    realSetTimeout(function () {
      console.log(JSON.stringify({ stuck: stuck, second: second, during: during, afterLate: afterLate, afterSecond: afterSecond,
                                   ids: sent.map(function (s) { return s.id; }), aborted: aborted,
                                   answering: t.S.answering, offline: t.S.offline, deadline: waits.indexOf(8000) >= 0 }));
    }, 200);
  }, 20);
}, 30);
""").replace("__CARD__", json.dumps(card)))
    assert out["stuck"] is True and out["second"] == 2 and out["during"] is True
    assert out["afterLate"] is True and out["afterSecond"] is False
    assert out["ids"][1:] == ["next-card", "third-card"]
    assert out["aborted"] == 1 and out["answering"] is False and out["offline"] is True and out["deadline"] is True


def test_elicitation_field_description_is_shown_with_the_question_and_before_sending(tmp_path):
    """MCP の問いの欄に題と別の説明がある時、選ぶ画面と、送る前の確かめの両方に出す。"""
    out = node(tmp_path, r"""
const card = { id: "c", kind: "elicitation", state: "shown", payload: { head: "srv", text: "Please confirm", fields: [
  { name: "ok", title: "Confirm", description: "Delete all records permanently?", multi: false, required: true,
    options: [{ label: "Yes", value: true }, { label: "No", value: false }] },
  { name: "mode", title: "Mode", multi: false, required: true,
    options: [{ label: "fast", value: "fast" }, { label: "safe", value: "safe" }] }] } };
let ui = core.newUi(card.id);
const first = core.buildScreen(card, ui, "ja");
ui = core.pressKey(card, ui, "opt:0").ui;
const second = core.buildScreen(card, ui, "ja");
ui = core.pressKey(card, ui, "opt:1").ui;
const last = core.buildScreen(card, ui, "ja");
console.log(JSON.stringify({ first: first.blocks, second: second.blocks, last: last.blocks,
                             summary: last.summary, keys: last.options.map(function (o) { return o.key; }) }));
""")
    assert out["first"] == [{"label": "", "text": "Delete all records permanently?", "mono": False}]
    assert out["second"] == []
    assert out["last"] == [{"label": "Confirm", "text": "Delete all records permanently?", "mono": False}]
    assert out["summary"] == ["Confirm: Yes", "Mode: safe"] and "send" in out["keys"]


# ---- 5 巡目 (3・4 巡目の差分の反証): 頁を init() ごと DOM の代用品の中で回し、入口 (板の写し・鍵・click・pointer) から入れる ----

PAGE_DOM = Path(__file__).resolve().parent / "page_dom.cjs"
PERM_PAYLOAD = {"head": "Bash", "text": "ls", "blocks": [{"label": "command", "text": "ls", "mono": True}]}
TWO_QUESTIONS = {"questions": [
    {"header": "一", "question": "最初の問い", "options": [{"label": "a"}, {"label": "b"}]},
    {"header": "二", "question": "次の問い", "options": [{"label": "c"}, {"label": "d"}]}]}

PAGE_HELPERS = r"""
function deciding(card, choice, left) {          /* 板が答えを受けた写し = 猶予の内 */
  return Object.assign({}, card, { state: "deciding", choice: choice || { type: "allow_once" },
                                   undo_remaining: left === undefined ? 3 : left });
}
/* 次の札の写しに板が添える「直前に終わった札」。by = 渡った答えを送った頁の名札 (c.me() = この頁・答えが渡って終わった時だけ) */
function ended(card, by, end) {
  return { last: { id: card.id, kind: card.kind, end: end || "answered", from_deciding: true, ago: 0, answered_by: by || null } };
}
function reshown(card) {                         /* 取り消せた写し = 選ぶ画面へ戻る (表示の seq が進む) */
  return Object.assign({}, card, { state: "shown", view_seq: card.view_seq + 1, choice: null, undo_remaining: null });
}
function choices(c) { return c.answers().map(function (s) { return s.body.choice; }); }
"""


def _rule(command: str) -> list:
    return [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": command}],
             "behavior": "allow", "destination": "localSettings"}]


def _card(clock, kind: str = "permission", payload=None) -> dict:
    """本物の板が頁へ渡す形の札 (1 枚ごとに新しい板 = id は札ごとに別)。"""
    lim = replace(board_server.Limits(), wait_hold=0.0, pending_hold=0.0, viewer=None)
    board = board_server.Board(lim, clock=clock)
    assert board.ask(kind, {"cwd": "repo"}, payload or dict(PERM_PAYLOAD))[0] == 200
    return board.pending(-1)["card"]


def page(tmp_path: Path, body: str, **cards):
    """頁を init() ごと DOM の代用品 (page_dom.cjs) の中で回す筋書き。body は async の中身 (P = 代用品の道具)。
    cards = 筋書きの中の名前 → 札。"""
    script = "const P = require(" + json.dumps(str(PAGE_DOM)) + ");\n" + PAGE_HELPERS
    script += "".join(f"const {name} = {json.dumps(card, ensure_ascii=False)};\n" for name, card in cards.items())
    script += ("(async () => {\n" + body +
               "\n})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });\n")
    return node(tmp_path, script)


def test_a_double_press_on_back_does_not_send_the_allow_of_the_screen_it_returns_to(tmp_path, clock):
    """「前の画面へ」の上で Enter / Space が 2 回入っても (ばたつき・押し直し・間 30 ms と 150 ms)、2 打目は戻った画面の
    「許可」に当たらない (反証役の再現 = 扇でも大きな板でも allow_once が送られた)。位置や焦点で行き先が決まる押しで札の中を
    進めた時も 0.4 秒は押しを数えず、戻った後の鍵の焦点は来た元の「拒否 …」に置く = 0.6 秒後の Enter は理由の画面を
    もう一度開くだけ。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) for (const key of ["Enter", " "]) for (const gap of [30, 150]) {
  const code = key === " " ? "Space" : "Enter";
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(PERM);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("deny").focus();
  await c.key(key, code);                          /* 拒否 … → 理由の画面 */
  await c.run(500);
  c.btn("back").focus();                           /* Tab で「前の画面へ」へ */
  await c.key(key, code);                          /* 1 打目 = 前の画面へ */
  await c.run(gap);
  await c.key(key, code);                          /* 2 打目 (ばたつき・押し直し) */
  await c.run(300);
  const after = { sent: c.answers().length, focus: c.active(), reasons: !!c.btn("back") };
  await c.run(300);                                /* 1 打目から 0.6 秒より後 */
  await c.key(key, code);
  out[mode + ":" + code + ":" + gap] = Object.assign(after, { later: { sent: c.answers().length, reasons: !!c.btn("back") } });
}
console.log(JSON.stringify(out));
""", PERM=perm)
    want = {"sent": 0, "focus": "deny", "reasons": False, "later": {"sent": 0, "reasons": True}}
    assert out == {f"{m}:{k}:{g}": want for m in ("small", "large") for k in ("Enter", "Space") for g in (30, 150)}, out


def test_a_double_enter_on_the_last_question_does_not_send_an_unseen_confirmation(tmp_path, clock):
    """2 問の札の最後の設問で Enter が 2 回入っても、2 打目が確かめの画面の「送る」を押さない (反証役の再現)。
    0.4 秒より後なら、確かめの画面を見て押した Enter として送る。"""
    q = _card(clock, "question", TWO_QUESTIONS)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(Q);
await c.run(500);
await c.key("Tab", "Tab");
c.btn("opt:0").focus();
await c.key("Enter", "Enter");                     /* 1 問目 → 2 問目 */
await c.run(500);
c.btn("opt:1").focus();
await c.key("Enter", "Enter");                     /* 2 問目の最後の選択肢 → 確かめの画面 */
await c.run(30);
await c.key("Enter", "Enter");                     /* 2 打目 */
await c.run(300);
const early = { sent: c.answers().length, confirm: !!c.btn("send"), focus: c.active() };
await c.run(300);
await c.key("Enter", "Enter");                     /* 確かめの画面を見て押す */
console.log(JSON.stringify({ early: early, later: choices(c) }));
""", Q=q)
    assert out["early"] == {"sent": 0, "confirm": True, "focus": "send"}
    assert out["later"] == [{"type": "answer", "picks": [[0], [1]]}]


def test_a_double_click_on_back_in_the_large_board_sends_nothing(tmp_path, clock):
    """大きな板で「前の画面へ」をダブルクリックすると、2 回目は同じ所に来た戻った画面の釦に当たる。0.4 秒の内の 2 回目は
    数えない (位置で行き先が決まる押し)。0.4 秒より後の click は、今までどおり 1 回で送る。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(PERM);
await c.run(500);
await c.click(c.btn("deny"));                      /* 拒否 … → 理由の画面 */
await c.run(500);
await c.click(c.btn("back"));                      /* 前の画面へ */
await c.run(150);
await c.click(c.btn("allow_once"));                /* ダブルクリックの 2 回目 = 戻った画面の「許可」 */
await c.run(100);
const second = c.answers().length;
await c.run(300);
await c.click(c.btn("allow_once"));                /* 戻った画面を見て押す */
console.log(JSON.stringify({ second: second, later: choices(c) }));
""", PERM=perm)
    assert out == {"second": 0, "later": [{"type": "allow_once"}]}


def test_named_presses_still_follow_each_other_inside_a_card(tmp_path, clock):
    """逆向き: 行き先を名指しする数字の鍵は、札の中を進めても続けて打てる (2 → 1 = 理由 1 で拒否・2 → 4 → 1 = 戻って許可)。
    滞留で札の中を進めた直後の数字の鍵も捨てない。焦点の上の Enter でも、0.4 秒より後の押しは今までどおり数える。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const out = {};
let c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(PERM); await c.run(500);
await c.key("2", "Digit2"); await c.key("1", "Digit1");          /* 拒否 … → すぐ理由 1 */
out.reason = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(PERM); await c.run(500);
await c.key("2", "Digit2"); await c.key("4", "Digit4"); await c.key("1", "Digit1");   /* 拒否 … → 前の画面へ → 許可 */
out.back = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja&dwell=1" });
c.doc().layout = function (e) { return e.dataset.key === "deny" ? { left: 0, top: 0, width: 100, height: 100, z: 1 } : null; };
c.show(PERM);
await c.run(600, function () { c.pointer(300, 300); });        /* 釦の外 */
await c.run(1200, function () { c.pointer(50, 50); });         /* 滞留で拒否 … → 理由の画面 */
await c.key("1", "Digit1");                                     /* すぐ数字の 1 */
out.afterDwell = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(PERM); await c.run(500);
await c.key("Tab", "Tab"); c.btn("deny").focus();
await c.key("Enter", "Enter");                                  /* 拒否 … → 理由の画面 (焦点は先頭の理由) */
await c.run(450);
await c.key("Enter", "Enter");                                  /* 0.4 秒より後 */
out.enterLater = choices(c);
for (const named of [["Escape", "Escape"], ["0", "Digit0"]]) {  /* Esc (止める側) と 0 (端末で答える) も名指しの鍵 */
  c = await P.boot({ query: "?mode=small&lang=ja" });
  c.show(PERM); await c.run(500);
  await c.key("2", "Digit2"); await c.key(named[0], named[1]);  /* 拒否 … → すぐ Esc / 0 */
  out[named[0]] = choices(c).map(function (x) { return x.type; });
}
console.log(JSON.stringify(out));
""", PERM=perm)
    deny = [{"type": "deny", "reason": 0}]
    assert out == {"reason": deny, "back": [{"type": "allow_once"}], "afterDwell": deny, "enterLater": deny,
                   "Escape": ["stop"], "0": ["terminal"]}, out


SWAP_CARDS = {
    "permission": (dict(PERM_PAYLOAD, suggestions=_rule("git status")), dict(PERM_PAYLOAD, suggestions=_rule("rm -rf build")),
                   ["allow_once", "sugg:0", "deny", "fixed", "terminal"]),
    "question": ({"questions": [{"header": "一", "question": "どれにしますか", "options": [{"label": "a"}, {"label": "b"}, {"label": "c"}]}]},
                 {"questions": [{"header": "二", "question": "消してよいですか", "options": [{"label": "消す"}, {"label": "残す"}]}]},
                 ["opt:0", "opt:2", "fixed", "terminal"]),
    "elicitation": ({"head": "blemma", "text": "どれにしますか", "fields": [
                        {"name": "choice", "title": "どれにしますか", "multi": False, "required": True,
                         "options": [{"label": "x0"}, {"label": "x1"}, {"label": "x2"}]}]},
                    {"head": "srv", "text": "本番へ配りますか", "fields": [
                        {"name": "go", "title": "本番へ配りますか", "multi": False, "required": True,
                         "options": [{"label": "配る"}, {"label": "配らない"}]}]},
                    ["opt:0", "opt:2", "decline", "fixed", "terminal"]),
}


def test_a_card_replaced_under_the_key_focus_leaves_the_focus_nowhere(tmp_path, clock):
    """札がこの頁の答え無しで次の札に替わった時、鍵の焦点が前の札の釦に在れば、次の札には焦点をどこにも置かない (反証役の
    再現 = 焦点が次の札の先頭へ移り、前の札の「拒否 …」「止」「戻」「断る」へ向けた 0.6 秒遅れの Enter が、次の札の許可・
    1 番目の答え・MCP の受け入れを送った。その前の形は、同じ位置の「次から訊かない」へ持ち越して恒久の許可を送った)。
    起点は、権限の確認・質問・MCP の問いの、許可を含むどの釦でも同じ。扇でも大きな板でも同じ。人が自分で焦点を動かすまで続く。"""
    cards = {}
    for kind, (first, second, _keys) in SWAP_CARDS.items():
        cards[kind] = [_card(clock, kind, first), _card(clock, kind, second)]
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) for (const kind of Object.keys(CARDS)) for (const key of KEYS[kind]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(CARDS[kind][0]);
  await c.run(500);
  await c.key("Tab", "Tab");
  const from = c.btn(key);
  if (!from) { out[mode + ":" + kind + ":" + key] = "釦が無い"; continue; }
  from.focus();                                    /* 鍵で、前の札の釦へ焦点を置く (押さない) */
  c.show(CARDS[kind][1]);                          /* 答えずに、板から次の札へ直に替わる */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 前の札の釦へ向けた、遅れた Enter */
  await c.run(600);
  await c.key(" ", "Space");                       /* Space も同じ = 焦点任せの鍵では、印は解けない */
  out[mode + ":" + kind + ":" + key] = { focus: focus, sent: c.answers().length, after: c.active() };
}
console.log(JSON.stringify(out));
""", CARDS=cards, KEYS={kind: keys for kind, (_a, _b, keys) in SWAP_CARDS.items()})
    assert len(out) == 2 * sum(len(keys) for _a, _b, keys in SWAP_CARDS.values()), out
    assert all(v == {"focus": "body", "sent": 0, "after": "body"} for v in out.values()), out


def test_the_page_puts_the_key_focus_again_once_the_person_answers_or_moves_on(tmp_path, clock):
    """消えた焦点の後に来た札には、先頭へ焦点を置かない。人が自分でその札に答えると (数字・click・触る・扇の矢印や Tab で
    焦点を置いてからの Enter)、その次の札には今までどおり先頭へ置く。何も起こさない鍵 (焦点の無い Enter・Tab だけ・大きな板の
    矢印・釦の無い番号)・数えない間の内の数字 (前の札へ向けた遅れた 1 押しかも知れない) の後は、その次の札にも置かない。"""
    a, b, c3 = (_card(clock, payload=dict(PERM_PAYLOAD)) for _ in range(3))
    out = page(tmp_path, r"""
const out = {};
const HOWS = { none: "large", Enter: "large", Tab: "large", ArrowDown: "large", early1: "large", badNumber: "large",
               "1": "large", TabEnter: "large", click: "large", touch: "large", ArrowRight: "small" };
for (const how of Object.keys(HOWS)) {
  const c = await P.boot({ query: "?mode=" + HOWS[how] + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("deny").focus();
  c.show(B);                                       /* 前の札の「拒否 …」に焦点が在るまま、次の札へ替わる (焦点が消える) */
  await c.run(how === "early1" ? 200 : 600);
  if (how === "Enter") await c.key("Enter", "Enter");            /* 焦点が無い = 何も起こさない */
  if (how === "Tab") await c.key("Tab", "Tab");                  /* Tab だけ (この代用品では、Tab で焦点は動かない) */
  if (how === "ArrowDown") await c.key("ArrowDown", "ArrowDown");   /* 大きな板の矢印は焦点を動かさない */
  if (how === "badNumber") await c.key("6", "Digit6");           /* 6 番の釦は無い */
  if (how === "early1" || how === "1") await c.key("1", "Digit1");  /* 数字 = 0.2 秒では数えない・0.6 秒では B を許可する */
  if (how === "TabEnter") { await c.key("Tab", "Tab"); c.btn("allow_once").focus(); await c.key("Enter", "Enter"); }   /* Tab で焦点を置いて Enter */
  if (how === "click") await c.click(c.btn("allow_once"));       /* B の「許可」を click */
  if (how === "touch") {
    c.pointer(1, 1, { type: "pointerdown", pointerType: "touch", buttons: 1 });
    c.pointer(1, 1, { type: "pointerup", pointerType: "touch", buttons: 0 });
    c.event("click", { target: c.btn("allow_once"), detail: 1 });   /* B の「許可」を触る */
  }
  if (how === "ArrowRight") { await c.key("ArrowRight", "ArrowRight"); await c.key("Enter", "Enter"); }   /* 扇の矢印で羽根へ → Enter */
  const answered = choices(c).length;
  if (answered) {                                  /* B に自分で答えた = 猶予の後に次の札 */
    c.show(deciding(B, choices(c)[0]));
    await c.run(3100);
    await c.key("Shift", "ShiftLeft");             /* (click・触るの後) 鍵へ戻る。Shift は何も押さない */
  }
  c.show(C, answered ? ended(B, c.me()) : undefined);   /* その次の札 (答えた時は、その答えが渡って終わった) */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");
  out[how] = { answered: answered, focus: focus, sent: choices(c).length - answered };
}
console.log(JSON.stringify(out));
""", A=a, B=b, C=c3)
    nowhere = {"answered": 0, "focus": "body", "sent": 0}
    acted = {"answered": 1, "focus": "allow_once", "sent": 1}
    assert out == {"none": nowhere, "Enter": nowhere, "Tab": nowhere, "ArrowDown": nowhere, "early1": nowhere,
                   "badNumber": nowhere, "1": acted, "TabEnter": acted, "click": acted, "touch": acted,
                   "ArrowRight": acted}, out


def test_a_click_that_only_picks_a_blade_then_enter_moves_on_with_the_key_focus(tmp_path, clock):
    """消えた焦点の後でも、人が自分で札の中を進めれば、進んだ先の先頭へ焦点を置く。扇の羽根を 1 回 click して選び (click は
    羽根へ焦点を置く)、Enter で進めた時と、読み上げソフトの「押す」(pointer の無い click) で進めた時 (外部のレビューの所見 =
    前の形では印が残り続けて、進んだ先で Enter が効かなかった)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["click+Enter", "assist"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("allow_once").focus();
  c.show(B);                                       /* 焦点が在るまま札が替わる = 焦点が消える */
  await c.run(600);
  const gone = c.active();
  if (how === "click+Enter") {
    await c.click(c.btn("deny"));                  /* 扇の 1 回目の click = 選ぶだけ (羽根に焦点が来る) */
    await c.run(100);
    await c.key("Enter", "Enter");                 /* Enter で「拒否 …」→ 理由の画面 */
  } else {
    await c.run(600);                              /* 鍵から 0.5 秒より後 */
    c.event("click", { target: c.btn("deny"), detail: 0 });   /* 読み上げソフトの「押す」 */
  }
  await c.run(50);
  const reasons = c.active();                      /* 進んだ先の先頭 (理由の 1 番目) */
  await c.run(450);
  await c.key("Enter", "Enter");
  await c.run(50);
  out[how] = { gone: gone, reasons: reasons, sent: choices(c) };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"gone": "body", "reasons": "reason:0", "sent": [{"type": "deny", "reason": 0}]}
    assert out == {"click+Enter": want, "assist": want}, out


def test_an_undo_this_page_did_not_watch_keeps_the_next_card_unfocused(tmp_path, clock):
    """ほかの頁が答えて取り消し、この頁は途中の写しを受けないまま同じ札の選ぶ画面へ戻った時 = 描き直しが、人の置いた焦点を
    消す。その札が後で答え無しで替わっても、次の札の先頭 (許可) へ焦点を置かない (外部のレビューの所見 = 前の形は戻った直後
    だけを守っていて、その後に来た札の先頭へ焦点を置いた)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("deny").focus();                           /* 鍵で「拒否 …」へ焦点を置く (押さない) */
  c.show(reshown(A));                              /* ほかの頁の「答える → 取り消す」を、まとめて受けた */
  await c.run(600);
  const back = c.active();
  c.show(B);                                       /* その札が、答え無しで次の札へ替わる */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");
  out[mode] = { back: back, focus: focus, sent: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"back": "body", "focus": "body", "sent": 0}
    assert out == {"small": want, "large": want}, out


def test_an_undo_and_a_new_answer_seen_at_once_do_not_free_the_focus_on_undo(tmp_path, clock):
    """「取り消す」に焦点を置いている間に、ほかの頁が取り消して答え直し、この頁がそれをまとめて受けた時 (同じ札・猶予の内の
    まま・表示の seq だけが進む) = 扇では、描き直しが取り消しの枠を付け替えて焦点を外す。その後に来た札の先頭 (許可) へは
    置かない (外部のレビューの所見)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("1", "Digit1");                      /* この頁で許可 */
  c.show(deciding(A, { type: "allow_once" }));
  await c.run(500);
  await c.key("Tab", "Tab");
  c.$("undo-btn").focus();                         /* 取り消しに焦点を置く (押さない) */
  c.show(Object.assign(deciding(A, { type: "deny", reason: 0 }), { view_seq: A.view_seq + 2 }));   /* ほかの頁: 取り消す → 答え直す */
  await c.run(3100);                               /* 猶予が過ぎる */
  c.show(B);
  await c.run(20);
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");
  out[mode] = { focus: focus, sent: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "body", "sent": 1}
    assert out == {"small": want, "large": want}, out


MULTI_SELECT = {"questions": [{"header": "一", "question": "どれですか", "multiSelect": True,
                               "options": [{"label": "a"}, {"label": "b"}]}]}


def test_a_button_the_page_turns_off_under_the_key_focus_keeps_the_next_card_unfocused(tmp_path, clock):
    """複数選択で、焦点を「次へ」に置いたまま、数字で最後の選択を外す = 頁が「次へ」を押せなくして、焦点を消す (印を付けた
    だけの描き直しで、札の中は進んでいない)。その札が後で答え無しで替わっても、次の札の先頭 (許可) へ焦点を置かない
    (外部のレビューの所見)。押せない「次へ」の番号を押しても、何も変わらない。"""
    q, b = _card(clock, "question", MULTI_SELECT), _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(Q);
await c.run(500);
await c.key("1", "Digit1");                        /* 1 番を選ぶ = 「次へ」が押せるようになる */
await c.run(50);
const n = String(c.S.optionKeys.indexOf("next") + 1);
const on = !c.btn("next").disabled;
await c.key("Tab", "Tab");
c.btn("next").focus();                             /* 「次へ」に焦点を置く (押さない) */
await c.key("1", "Digit1");                        /* 1 番を外す = 「次へ」が押せなくなる */
await c.run(50);
const off = { focus: c.active(), disabled: c.btn("next").disabled };
await c.run(500);
await c.key(n, "Digit" + n);                       /* 押せない「次へ」の番号 */
await c.run(50);
c.show(B);                                         /* 答え無しで、次の札へ替わる */
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ on: on, off: off, focus: focus, sent: c.answers().length }));
""", Q=q, B=b)
    assert out == {"on": True, "off": {"focus": "body", "disabled": True}, "focus": "body", "sent": 0}, out


def test_the_key_focus_left_on_the_card_behind_the_settings_is_not_used_up_by_closing_them(tmp_path, clock):
    """設定の板を開いたまま、焦点を板の外の札の釦へ移して閉じた時 = 閉じる操作が使ったのは、板の中の焦点だけ。札の釦に在る
    焦点は生きている = その札が後で答え無しで替わったら、次の札の先頭 (許可) へ焦点を置かない。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(A);
await c.run(500);
await c.key("Tab", "Tab");
c.$("gear-btn").focus();
await c.key("Enter", "Enter");                     /* 設定の板が開く (焦点は「閉じる」) */
await c.run(600);
c.btn("deny").focus();                             /* Tab で板の外へ出て、札の「拒否 …」へ */
await c.key("Escape", "Escape");                   /* 板を閉じる */
const held = c.active();
c.show(B);                                         /* 答え無しで、次の札へ替わる */
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ closed: c.$("overlay").hidden, held: held, focus: focus, sent: c.answers().length }));
""", A=a, B=b)
    assert out == {"closed": True, "held": "deny", "focus": "body", "sent": 0}, out


def test_answering_by_enter_card_after_card_still_finds_the_first_button(tmp_path, clock):
    """ふだんの流れは変えない = 鍵の人が札を Enter で答えると、答えた釦は押せなくなって焦点が外れる。猶予の後に次の札が来た時、
    焦点はどこにも無いので、今までどおり先頭へ置き、次の Enter がその札に答える (焦点を置いたまま答えずに替えられた時だけ、
    置かない)。扇でも大きな板でも同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("allow_once").focus();
  await c.key("Enter", "Enter");                   /* 1 枚目に答える */
  c.show(deciding(A, { type: "allow_once" }));
  await c.run(3100);                               /* 猶予が過ぎ、答えが渡る */
  c.show(B, ended(A, c.me()));                     /* 自分の答えが渡り、次の札 */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 2 枚目にも Enter で答える */
  out[mode] = { focus: focus, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "allow_once", "sent": ["allow_once", "allow_once"]}
    assert out == {"small": want, "large": want}, out


def test_answering_finds_the_first_button_even_when_the_grace_was_never_shown(tmp_path, clock):
    """猶予が 0 の板 (--undo-ms 0) や、猶予の写しを受け損ねた頁では、自分で答えた札から次の札へ直に替わる (焦点は前の札の釦に
    在るまま)。これは人が自分の押しで進めた物 = 頁が焦点を消した事に数えず、今までどおり次の札の先頭へ置く。焦点の上の Enter で
    答えても、焦点を別の釦に置いたまま数字で答えても同じ。扇でも大きな板でも同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) for (const how of ["Enter", "1"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja", undoMs: 0 });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn(how === "Enter" ? "allow_once" : "deny").focus();
  await c.key(how, how === "Enter" ? "Enter" : "Digit1");   /* 1 枚目に答える */
  await c.run(20);
  /* 猶予の写しを挟まず、次の札へ直に替わる。板は、直前に終わった札と、受けた答えの名札を添える */
  c.show(B, { last: { id: A.id, kind: "permission", end: "answered", from_deciding: false, ago: 0, answered_by: c.me() } });
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 2 枚目にも Enter で答える */
  out[mode + ":" + how] = { focus: focus, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "allow_once", "sent": ["allow_once", "allow_once"]}
    assert out == {"small:Enter": want, "small:1": want, "large:Enter": want, "large:1": want}, out


def test_a_card_another_page_answered_under_the_key_focus_leaves_the_focus_nowhere(tmp_path, clock):
    """ほかの頁 (もう 1 枚の窓) が答えた札は、この頁の釦が押せなくなる所で、頁が人の焦点を消す = 短い猶予の後に次の札が来ても、
    先頭 (許可) へ焦点を置かない (この頁の人は答えていない = 前の札の「拒否 …」へ向けた遅れた Enter が、次の札の許可に
    当たらない)。自分で答えた札とは逆。扇でも大きな板でも同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja", undoMs: 300 });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("deny").focus();                           /* 鍵で「拒否 …」へ焦点を置く (押さない) */
  c.show(deciding(A, { type: "allow_once" }, 0.3));   /* ほかの頁が答えた (この頁は何も送っていない) */
  await c.run(350);
  c.show(B);                                       /* 短い猶予が過ぎ、次の札が来た */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 前の札の「拒否 …」へ向けた、遅れた Enter */
  out[mode] = { focus: focus, sent: c.answers().length, after: c.active() };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "body", "sent": 0, "after": "body"}
    assert out == {"small": want, "large": want}, out


def test_an_answer_taken_back_or_refused_is_not_counted_as_the_persons_own(tmp_path, clock):
    """自分で答えた札でも、取り消して選ぶ画面へ戻った後・板が答えを受けなかった後 (409)・届いたか分からない後 (送信の失敗) は、
    答えていない札と同じ = その札に焦点を置いたまま、答え無しで次の札へ替えられた時は、次の札の先頭 (許可) へ焦点を置かない。
    ほかの頁に取り消された時 (この頁では何も押していない・焦点は答えた時に使った) も同じ = 取り下げられた答えは、自分で
    進めた事に数えない。取り消しの写しを受け損ねて、ほかの頁の答え直し・次の札 (ほかの頁の答えが渡った・時間切れ) を
    先に受けた時も同じ (外部のレビューの所見 = 選ぶ画面の写しを受けた時しか、戻していなかった)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
const refuse = { undone: null, undone_elsewhere: null, reanswered_elsewhere: null, ended_elsewhere: null, expired_after: null,
                 refused: function (p) { return p === "/answer" ? { status: 409, data: { error: "stale" } } : null; },
                 lost: function (p) { if (p === "/answer") throw new Error("lost"); return null; } };
for (const how of Object.keys(refuse)) {
  const c = await P.boot({ query: "?mode=large&lang=ja", reply: refuse[how] });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("allow_once").focus();
  await c.key("Enter", "Enter");                   /* 1 枚目に答える */
  await c.run(50);
  if (how === "undone") {
    c.show(deciding(A, { type: "allow_once" }));
    await c.run(600);
    await c.key("Escape", "Escape");               /* 取り消す */
    c.show(reshown(A));
    await c.run(500);
    await c.key("Tab", "Tab");
    c.btn("deny").focus();                         /* 戻った選ぶ画面で、「拒否 …」へ焦点を置く (押さない) */
  }
  if (how === "undone_elsewhere") {
    c.show(deciding(A, { type: "allow_once" }));
    await c.run(600);
    c.show(reshown(A));                            /* ほかの頁が取り消した (この頁では何も押していない) */
    await c.run(500);
  }
  if (how === "reanswered_elsewhere") {             /* ほかの頁が取り消して答え直した。途中の選ぶ画面の写しは受けていない */
    c.show(deciding(A, { type: "allow_once" }));
    await c.run(600);
    c.show(Object.assign(deciding(A, { type: "deny", reason: 0 }), { view_seq: A.view_seq + 2 }));
    await c.run(3100);
  }
  if (how === "ended_elsewhere" || how === "expired_after") {   /* 取り消しの後の写しを全部受け損ねて、次の札を受けた */
    c.show(deciding(A, { type: "allow_once" }));
    await c.run(600);
  }
  const held = c.active();
  /* 答え無しで、次の札へ替わる。板が添える「直前に終わった札」= ほかの頁の答えが渡った・時間切れ・(ほかは) 読めない */
  c.show(B, how === "ended_elsewhere" || how === "reanswered_elsewhere" ? ended(A, "another-page")
            : how === "expired_after" ? ended(A, null, "expired") : undefined);
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 前の札の釦へ向けた、遅れた Enter */
  out[how] = { held: held, focus: focus, answers: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    assert out == {"undone": {"held": "deny", "focus": "body", "answers": 1},
                   "undone_elsewhere": {"held": "body", "focus": "body", "answers": 1},
                   "reanswered_elsewhere": {"held": "body", "focus": "body", "answers": 1},
                   "ended_elsewhere": {"held": "body", "focus": "body", "answers": 1},
                   "expired_after": {"held": "body", "focus": "body", "answers": 1},
                   "refused": {"held": "allow_once", "focus": "body", "answers": 1},
                   "lost": {"held": "allow_once", "focus": "body", "answers": 1}}, out


def test_only_the_boards_word_makes_an_answer_the_persons_own(tmp_path, clock):
    """「この頁の人の答えで札が進んだ」は、板が写しに添える名札 (受けた答えを送った頁) で読む。頁の側で推し量らない =
    答えを送った直後 (板の返りの前) に札が終わって次の札が来ても、返りと写しの順に左右されない (外部のレビューの所見 =
    前の形は、送った時点や、板の終わり方だけで「自分で答えた」と数え、ほかの頁の答えが先に通った時に、次の札の許可へ焦点を
    置いた)。時間切れ・ほかの頁の答え・ほかの札の終わり方しか読めない時は、次の札の先頭へ置かない。自分の答えが渡って
    終わった時 (「端末で答える」も) は、ふだんの流れ。断りの返りが、次の札を見て打った Enter の後から届いても同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["expired", "other_card", "other_page", "mine", "released"]) {
  let sendA = null;
  const c = await P.boot({ query: "?mode=large&lang=ja", undoMs: 0,
                           reply: function (p, body) { return p === "/answer" && body.id === A.id ? { later: function (s) { sendA = s; } } : null; } });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("allow_once").focus();
  if (how === "released") await c.key("0", "Digit0");   /* 「端末で答える」を送る (返りはまだ) */
  else await c.key("Enter", "Enter");                   /* 「許可」を送る (返りはまだ) */
  await c.run(20);
  const last = { id: how === "other_card" ? "another-card" : A.id, kind: "permission", from_deciding: false, ago: 0,
                 end: how === "expired" ? "expired" : how === "released" ? "released" : "answered",
                 answered_by: how === "expired" ? null : how === "other_page" ? "another-page" : c.me() };
  c.show(B, { last: last });                       /* 返りより先に、次の札が来た */
  const first = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 次の札を見て (0.6 秒後に) 打つ Enter。A の返りはまだ */
  await c.run(20);
  const sent = c.answers().length;
  if (how === "mine" || how === "released") sendA(200, { undo_ms: 0, undo_remaining: 0 });
  else sendA(409, how === "expired" ? { error: "expired" } : { error: "ended", end: "answered" });   /* 遅れて届いた A の返り */
  await c.run(20);
  out[how] = { first: first, sent: sent, after: c.active(),
               tagged: typeof c.answers()[0].body.tag === "string" && c.answers()[0].body.tag.indexOf(c.S.pressLedger.source + ":") === 0 };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    gone = {"first": "body", "sent": 1, "after": "body", "tagged": True}    # tagged = 頁は答えに自分の名札を添えている
    own = {"first": "allow_once", "sent": 2, "after": "allow_once", "tagged": True}
    assert out == {"expired": gone, "other_card": gone, "other_page": gone, "mine": own, "released": own}, out


def test_a_focus_the_page_puts_while_the_window_is_in_the_back_is_remembered_too(tmp_path, clock):
    """窓が背面に居る間は、頁が焦点を置いても、ブラウザは焦点の知らせを送らない (前面へ戻った時に送る)。頁が自分で置いた
    焦点は、知らせを待たずに覚える = 背面で置いた先頭の焦点が、その札の時間切れで消えた後、次の札の先頭へまた置かない
    (外部のレビューの所見・推測)。"""
    a, b, c3 = (_card(clock) for _ in range(3))
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(A);
await c.run(500);
await c.key("1", "Digit1");                        /* 鍵で使う人が、1 枚目に答える */
c.show(deciding(A, { type: "allow_once" }));
await c.run(3100);
c.doc().silentFocus = true;                        /* 窓が背面へ (焦点の知らせが来なくなる) */
c.show(B, ended(A, c.me()));                       /* 背面で次の札 = 頁は先頭へ焦点を置く */
const onB = c.active();
await c.run(600);
c.show(C);                                         /* その札が答え無しで替わる */
const onC = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ onB: onB, onC: onC, sent: c.answers().length }));
""", A=a, B=b, C=c3)
    assert out == {"onB": "allow_once", "onC": "body", "sent": 1}, out


def test_closing_the_settings_does_not_use_up_a_focus_lost_behind_them(tmp_path, clock):
    """設定の板を開いたまま、焦点を板の外の札の釦へ移し、その札がほかの頁の答えで押せなくなって焦点が消えた後に、板を
    閉じた時 = 閉じる操作が使うのは、板の中に在る焦点だけ。板の外で消えた焦点の記録は残る = 次の札の先頭 (許可) へ焦点を
    置かない (外部のレビューの所見 = 前の形は、焦点がどこにも無ければ、閉じる操作で済んだ事にした)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(A);
await c.run(500);
await c.key("Tab", "Tab");
c.$("gear-btn").focus();
await c.key("Enter", "Enter");                     /* 設定の板が開く (焦点は「閉じる」) */
await c.run(600);
c.btn("deny").focus();                             /* Tab で板の外へ出て、札の「拒否 …」へ */
c.show(deciding(A, { type: "allow_once" }, 0.3));  /* ほかの頁が答えた = 「拒否 …」が押せなくなり、焦点が消える */
await c.run(50);
const lost = c.active();
await c.key("Escape", "Escape");                   /* 板を閉じる */
await c.run(400);
c.show(B);
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ closed: c.$("overlay").hidden, lost: lost, focus: focus, sent: c.answers().length }));
""", A=a, B=b)
    assert out == {"closed": True, "lost": "body", "focus": "body", "sent": 0}, out


def test_an_undo_of_another_pages_answer_costs_this_page_nothing(tmp_path, clock):
    """ほかの頁が答えて取り消した札は、この頁の焦点とは関わりが無い = この頁に消えた焦点が無ければ、その後に来た札には
    今までどおり先頭へ焦点を置く (取り消しで「使われていない事に戻す」のは、この頁の人の答えが取り消された時だけ)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
c.show(A);
await c.run(500);
await c.key("Shift", "ShiftLeft");                 /* 鍵で使う人 (まだ焦点はどこにも置いていない) */
c.show(deciding(A, { type: "allow_once" }));       /* ほかの頁が答えた */
await c.run(600);
c.show(reshown(A));                                /* ほかの頁が取り消した */
await c.run(600);
const back = c.active();
c.show(B);                                         /* その札が終わり、次の札が来た */
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ back: back, focus: focus, sent: choices(c).map(function (x) { return x.type; }) }));
""", A=a, B=b)
    assert out == {"back": "body", "focus": "allow_once", "sent": ["allow_once"]}, out


def test_a_focus_placed_after_the_press_is_not_used_up_by_the_answer(tmp_path, clock):
    """数字で答えを送った後、板の写しが届く前に、Tab で「拒否 …」へ焦点を置き直した時 = その焦点は、送った答えでは使われて
    いない (使われたのは、押した時の焦点だけ)。描き直しで消えた後、次の札の先頭 (許可) へ焦点を置かない (外部のレビューの
    所見 = 写しを受けた時点の焦点を「使われた」と数え、置き直した焦点まで済んだ事にした)。猶予の写しを受けた時も、受けない
    まま次の札が来た時も同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["grace", "direct"]) {
  let send = null;
  const c = await P.boot({ query: "?mode=large&lang=ja", undoMs: how === "grace" ? 300 : 0,
                           reply: function (p, body) { return p === "/answer" && body.id === A.id ? { later: function (s) { send = s; } } : null; } });
  c.show(A);
  await c.run(500);
  await c.key("1", "Digit1");                      /* 数字で「許可」を送る (板の返りと写しは、まだ) */
  await c.key("Tab", "Tab");
  c.btn("deny").focus();                           /* その後で、「拒否 …」へ焦点を置き直す (押さない) */
  if (how === "grace") {
    c.show(deciding(A, { type: "allow_once" }, 0.3));   /* 遅れて届いた、自分の答えの猶予の写し */
    await c.run(400);
  }
  c.show(B, ended(A, c.me()));                     /* 自分の答えが渡り、次の札 */
  const focus = c.active();
  send(200, { undo_ms: 0, undo_remaining: 0 });
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 「拒否 …」へ向けた、遅れた Enter */
  out[how] = { focus: focus, sent: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "body", "sent": 1}
    assert out == {"grace": want, "direct": want}, out


def test_a_resend_is_not_mistaken_for_the_answer_that_went_through(tmp_path, clock):
    """最初の答えは板に通ったが、返りを失った (頁は失敗と見た・写しもまだ)。人が「止」へ焦点を置き直して Enter で送り直す
    (板は 2 回目を断る)。その後に、最初の答えが渡って次の札が来た時 = 使われた事にできるのは、最初の答えを押した時の焦点だけ。
    置き直した「止」の焦点は使われていない = 次の札の先頭 (許可) へ置かない (外部のレビューの所見 = 送信の控えが 1 つだと、
    2 回目の控えと照合して、「止」へ向けた遅れた Enter が次の札の許可を送った)。名札は送信ごと。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
let calls = 0;
const c = await P.boot({ query: "?mode=large&lang=ja", undoMs: 0,
                         reply: function (p) {
                           if (p !== "/answer") return null;
                           calls += 1;
                           if (calls === 1) throw new Error("lost");               /* 1 回目 = 板には通ったが、返りを失った */
                           return { status: 409, data: { error: "not_shown", state: "deciding" } };   /* 2 回目 = 板が断る */
                         } });
c.show(A);
await c.run(500);
await c.key("Tab", "Tab");
c.btn("allow_once").focus();
await c.key("Enter", "Enter");                     /* 1 回目: 「許可」を送る */
await c.run(500);
c.btn("fixed").focus();                            /* 「止」へ焦点を置き直す */
await c.key("Enter", "Enter");                     /* 2 回目: 「止」を送り直す (断られる) */
await c.run(100);
const tags = c.answers().map(function (x) { return x.body.tag; });
c.show(B, ended(A, tags[0]));                      /* 渡ったのは 1 回目の答え = 板は 1 回目の名札を添える */
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");                     /* 「止」へ向けた、遅れた Enter */
console.log(JSON.stringify({ distinct: tags[0] !== tags[1], focus: focus, sent: c.answers().length }));
""", A=a, B=b)
    assert out == {"distinct": True, "focus": "body", "sent": 2}, out


def test_putting_the_same_button_back_does_not_count_as_a_new_focus(tmp_path, clock):
    """答えを送った後、板の写しが届く前に、頁やブラウザが同じ釦へ焦点を付け直しても (窓へ戻った時の再通知・「常に手前」の
    PiP の窓へ移って描き直した時)、それは押した時の焦点のまま = 答えが渡ったら、今までどおり次の札の先頭へ焦点を置く
    (外部のレビューの所見 = 焦点が来るたびに数を進めると、置き直していない人の Enter の流れが切れた)。別の釦へ置き直した
    焦点は、今までどおり押した時の焦点とは別。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["renotify", "pip", "moved"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja", undoMs: 0, pip: how === "pip" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("allow_once").focus();
  await c.key("Enter", "Enter");                   /* 許可を送る (板の写しは、まだ) */
  const btn = c.btn("allow_once");
  if (how === "renotify") c.event("focusin", { target: btn });     /* 窓へ戻った時の、同じ釦への再通知 */
  if (how === "pip") c.t.press("pip", "key");                      /* 待っていた PiP の窓が開いて、頁が移る */
  if (how === "moved") { c.btn("deny").focus(); c.btn("allow_once").focus(); }   /* 人が別の釦へ移って、戻した */
  await c.run(50);
  const moved = { pip: c.vwin() !== c.win, focus: c.active() };
  c.show(B, ended(A, c.me()));                     /* 自分の答えが渡り、次の札 */
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");
  out[how] = { moved: moved, focus: focus, sent: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    kept = {"focus": "allow_once", "sent": 2}
    assert out == {"renotify": dict(kept, moved={"pip": False, "focus": "allow_once"}),
                   "pip": dict(kept, moved={"pip": True, "focus": "allow_once"}),
                   "moved": {"moved": {"pip": False, "focus": "allow_once"}, "focus": "body", "sent": 1}}, out


def test_a_number_right_behind_a_step_made_by_enter_or_click_is_not_counted(tmp_path, clock):
    """焦点の上の Enter や click で札の中を進めた直後 (「前の画面へ」) の 0.4 秒は、数字の鍵も数えない = 続けて入った数字が、
    戻った画面の 1 番 (許可) を送らない (外部のレビューの所見 = この守りは試験が見張っていなかった)。0.4 秒より後の数字は
    数える。数字で進めた直後に続けて打つ数字は、今までどおり数える (別の試験)。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["Enter", "click"]) {
  const c = await P.boot({ query: "?mode=large&lang=ja" });
  c.show(PERM);
  await c.run(500);
  await c.key("2", "Digit2");                      /* 拒否 … → 理由の画面 */
  await c.run(500);
  if (how === "Enter") { await c.key("Tab", "Tab"); c.btn("back").focus(); await c.key("Enter", "Enter"); }
  else await c.click(c.btn("back"));               /* 「前の画面へ」を Enter / click で */
  await c.run(50);
  await c.key("1", "Digit1");                      /* 0.05 秒後の数字 (戻った画面の 1 番 = 許可) */
  await c.run(20);
  const early = c.answers().length;
  await c.run(450);
  await c.key("1", "Digit1");                      /* 0.5 秒後の数字 = 数える */
  await c.run(20);
  out[how] = { early: early, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify(out));
""", PERM=perm)
    want = {"early": 0, "sent": ["allow_once"]}
    assert out == {"Enter": want, "click": want}, out


def test_an_undo_left_unpressed_does_not_turn_into_the_next_allow(tmp_path, clock):
    """「取り消す」に鍵の焦点を置いたまま押しそびれ、猶予が切れて頁が釦を消した後に次の札が来ても、その札の先頭 (許可) へ
    焦点を置かない (反証役の再現 = 取り消しのつもりの 0.6 秒遅れの Enter が、次の札の許可を送った)。扇でも大きな板でも同じ。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) for (const late of ["", "Escape", "Backspace"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("1", "Digit1");                      /* 1 枚目を許可 */
  c.show(deciding(A, { type: "allow_once" }));
  await c.run(500);
  c.$("undo-btn").focus();                         /* 取り消しに焦点を置いたまま、押さない */
  await c.run(3000);                               /* 猶予が切れ、頁が取り消しの釦を消す */
  const gone = c.$("undo-btn").hidden;
  if (late) await c.key(late, late);               /* 間に合わなかった取り消しの鍵 (何も起こさない) */
  /* 答えが渡り、次の札が来た。板は、直前に終わった札に「この頁の答えが渡った」の名札を添える。使われた事にできるのは、
     答えを押した時に在った焦点だけ = 取り消しに置いた焦点は、その後に来た焦点なので使われていない */
  c.show(B, { last: { id: A.id, kind: "permission", end: "answered", from_deciding: true, ago: 0, answered_by: c.me() } });
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 取り消しのつもりの、遅れた Enter */
  out[mode + ":" + late] = { gone: gone, focus: focus, posts: c.posts() };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"gone": True, "focus": "body", "posts": ["/answer"]}
    assert out == {mode + ":" + late: want for mode in ("small", "large") for late in ("", "Escape", "Backspace")}, out


def test_the_key_focus_on_more_goes_nowhere_when_the_next_card_has_no_more(tmp_path, clock):
    """「▼ 続き」に鍵の焦点を置いたまま、数字で自分で答えた時 = 猶予の間は頁が「▼ 続き」を隠すので、頁が焦点を消す。次の札の
    先頭 (許可) へは置かない (本文を送るつもりの Enter が、次の札の許可に当たらない)。次の札に続きが在っても無くても同じ
    (隠した「▼ 続き」へ焦点を戻しもしない = Enter は何も送らない)。"""
    a, b = _card(clock), _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const next of ["short", "long", "step"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja" });
  c.$("copy").scrollHeight = 900; c.$("copy").clientHeight = 180;   /* 長い本文 = 「▼ 続き」が出る */
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.$("more").focus();
  if (next === "step") {
    await c.key("2", "Digit2");                    /* 焦点は「▼ 続き」のまま、数字で札の中を進める (拒否 … → 理由) */
    await c.run(600);
    c.$("copy").scrollHeight = 100;
    c.show(B);                                     /* 答えないまま、続きの無い次の札へ替わる */
  } else {
    await c.key("1", "Digit1");                    /* 焦点は「▼ 続き」のまま、数字で許可 */
    c.show(deciding(A, { type: "allow_once" }));
    await c.run(3100);
    if (next === "short") c.$("copy").scrollHeight = 100;
    c.show(B, ended(A, c.me()));
  }
  await c.run(20);
  const focus = c.active();
  await c.run(600);
  await c.key("Enter", "Enter");                   /* 本文を送るつもりの Enter */
  out[next] = { focus: focus, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    want = {"focus": "body", "sent": ["allow_once"]}
    assert out == {"short": want, "long": want, "step": {"focus": "body", "sent": []}}, out


def test_a_habit_enter_right_behind_a_number_does_not_pick_the_unseen_question(tmp_path, clock):
    """数字の鍵 (名指し) で次の設問へ進めた直後は、続く数字の押しは数えるが、焦点任せの Enter は 0.4 秒のあいだ数えない
    (反証役の再現 = 数字の直後の癖の Enter が、見ていない次の設問の先頭を選んで確かめの画面へ進んだ)。"""
    q = _card(clock, "question", TWO_QUESTIONS)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(Q);
await c.run(500);
await c.key("1", "Digit1");                        /* 1 問目を数字で選ぶ → 2 問目へ */
await c.run(50);
await c.key("Enter", "Enter");                     /* 癖の Enter (2 問目はまだ見ていない) */
await c.run(100);
const early = { confirm: !!c.btn("send"), focus: c.active() };
await c.run(400);
await c.key("Enter", "Enter");                     /* 2 問目を見て押す */
await c.run(50);
console.log(JSON.stringify({ early: early, confirm: !!c.btn("send"), sent: c.answers().length }));
""", Q=q)
    assert out == {"early": {"confirm": False, "focus": "opt:0"}, "confirm": True, "sent": 0}, out


def test_clicks_right_behind_a_number_do_not_pick_a_blade_of_the_unseen_screen(tmp_path, clock):
    """扇の 2 回押し: 数字の鍵で札の中を進めた直後 (拒否 … → 理由) の 0.4 秒の内の click は、選ぶ 1 回目にも数えない (数えると、
    0.4 秒をまたぐ 2 回の click が、見ていない画面の羽根を決めてしまう = 「替わった直後の click を 1 回目に数えない」と同じ筋)。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(PERM);
await c.run(500);
await c.key("2", "Digit2");                        /* 「拒否 …」を数字で → 理由の画面 (扇のまま) */
const fan = c.S.fan, key = c.S.optionKeys[0];      /* 理由の 1 番目の羽根 */
await c.run(300);
await c.click(c.btn(key));                         /* 0.3 秒後の click (理由の画面はまだ見ていない) */
await c.run(150);
await c.click(c.btn(key));                         /* 0.45 秒後の click = これが選ぶ 1 回目 */
await c.run(50);
const two = { sent: c.answers().length, armed: c.S.armKey || null };
await c.click(c.btn(key));                         /* もう 1 回 = 決まる */
await c.run(50);
console.log(JSON.stringify({ fan: fan, key: key, two: two, sent: choices(c) }));
""", PERM=perm)
    assert out == {"fan": True, "key": "reason:0", "two": {"sent": 0, "armed": "reason:0"},
                   "sent": [{"type": "deny", "reason": 0}]}, out


def test_the_mark_of_uncounted_presses_covers_a_step_made_by_a_named_key(tmp_path, clock):
    """数字の鍵で札の中を進めた直後も、頁の印 (body.settling) を 0.4 秒付ける = 外の道具や試験が「もう押せる」と読んで押した
    焦点任せの押し (Enter・click) が、黙って捨てられない (実ブラウザの筋書きで見つけた食い違い)。"""
    q = _card(clock, "question", TWO_QUESTIONS)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(Q);
await c.run(500);
const before = c.doc().body.classList.contains("settling");
await c.key("1", "Digit1");                        /* 数字で次の設問へ */
await c.run(20);
const right = c.doc().body.classList.contains("settling");
await c.run(450);
console.log(JSON.stringify({ before: before, right: right, later: c.doc().body.classList.contains("settling") }));
""", Q=q)
    assert out == {"before": False, "right": True, "later": False}, out


def test_undo_right_behind_a_named_step_is_not_held_back(tmp_path, clock):
    """数字で札の中を進めて (拒否 … → 理由)、すぐ数字で答えた後の取り消しは、札の中を進めた直後の間 (0.4 秒) に巻き込まない
    (巻き込むと、猶予の短い板では取り消しの押せる間がその分だけ削られる)。取り消しの間は、猶予の写しから測る物だけ。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const key of ["Backspace", "Enter"]) {
  const c = await P.boot({ query: "?mode=large&lang=ja", undoMs: 400 });
  c.show(PERM);
  await c.run(500);
  await c.key("2", "Digit2");                      /* 拒否 … → 理由の画面 (札の中を進めた) */
  await c.key("1", "Digit1");                      /* すぐ理由 1 で答える */
  c.show(deciding(PERM, { type: "deny", reason: 0 }, 0.4));
  await c.run(250);                                /* 猶予 0.4 秒の板 = 取り消しは 0.2 秒から押せる */
  if (key === "Enter") c.$("undo-btn").focus();
  await c.key(key, key);
  await c.run(20);
  out[key] = c.posts();
}
console.log(JSON.stringify(out));
""", PERM=perm)
    assert out == {"Backspace": ["/answer", "/undo"], "Enter": ["/answer", "/undo"]}, out


def test_moving_on_inside_a_card_puts_the_key_focus_on_the_first_of_the_next_screen(tmp_path, clock):
    """札の中を自分の押しで進めた時は、進んだ先の先頭へ焦点を置く (2 問目の同じ番号へ持ち越さない)。同じ画面の描き直し
    (複数選択の印を付けただけ) では、焦点を押した釦のまま残す。"""
    q = _card(clock, "question", TWO_QUESTIONS)
    multi = _card(clock, "question", {"questions": [{"header": "一", "question": "選んでください", "multiSelect": True,
                                                     "options": [{"label": "a"}, {"label": "b"}, {"label": "c"}]}]})
    out = page(tmp_path, r"""
let c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(Q); await c.run(500);
await c.key("Tab", "Tab"); c.btn("opt:1").focus();
await c.key("Enter", "Enter");                     /* 1 問目の 2 番 → 2 問目 */
const next = c.active();
c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(M); await c.run(500);
await c.key("Tab", "Tab"); c.btn("opt:1").focus();
await c.key("Enter", "Enter");                     /* 印を付けるだけ */
console.log(JSON.stringify({ next: next, marked: c.active(), pressed: c.btn("opt:1").getAttribute("aria-pressed") }));
""", Q=q, M=multi)
    assert out == {"next": "opt:0", "marked": "opt:1", "pressed": "true"}


def test_undo_leaves_the_key_focus_nowhere(tmp_path, clock):
    """取り消して選ぶ画面へ戻った時は、鍵の焦点をどこにも置かない (反証役の再現 = 拒否を送って取り消すと、焦点が先頭の
    「許可」へ移り、次の Enter が許可を送った)。取り消しの釦でも Backspace / Esc でも、扇でも大きな板でも同じ。数字だけで
    使う人が取り消した時も同じ (数字 1 つで答えた人 = 焦点が一度も来ていない = 消えた焦点の決まりでは守れない筋)。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const out = {};
const pre = {};
for (const [mode, how] of [["small", "button"], ["small", "Backspace"], ["small", "Escape"], ["large", "button"],
                           ["small", "digit"], ["large", "digit"], ["small", "digit1"], ["large", "digit1"]]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(PERM);
  await c.run(500);
  if (how === "digit") {                           /* 数字で進めて答える (理由の画面では、頁が先頭へ焦点を置く) */
    await c.key("2", "Digit2");                    /* 拒否 … → 理由の画面 */
    await c.key("1", "Digit1");                    /* 理由 1 = 拒否を送る */
  } else if (how === "digit1") {                   /* 数字 1 つで答える = 焦点は一度も来ない (消えた焦点も無い) */
    pre[mode] = { focus: c.active(), seen: !!c.S.focusSeen };
    await c.key("1", "Digit1");                    /* 許可を送る */
  } else {
    await c.key("Tab", "Tab");
    c.btn("deny").focus();
    await c.key("Enter", "Enter");                 /* 拒否 … → 理由の画面 */
    await c.run(500);
    await c.key("Enter", "Enter");                 /* 先頭の理由 = 拒否を送る */
  }
  c.show(deciding(PERM, how === "digit1" ? { type: "allow_once" } : { type: "deny", reason: 0 }));
  await c.run(500);
  if (how === "button") { c.$("undo-btn").focus(); await c.key("Enter", "Enter"); }
  else { const k = how.indexOf("digit") === 0 ? "Escape" : how; await c.key(k, k); }
  c.show(reshown(PERM));                           /* 取り消せた = 選ぶ画面へ戻る */
  await c.run(20);                                 /* 隠れた取り消しの釦から焦点が外れる (次のこま) */
  const focus = c.active();
  await c.run(580);
  await c.key("Enter", "Enter");                   /* 焦点はどこにも無い = 何も押さない */
  out[mode + ":" + how] = { focus: focus, posts: c.posts(), sent: choices(c) };
}
out.pre = pre;
console.log(JSON.stringify(out));
""", PERM=perm)
    assert out.pop("pre") == {"small": {"focus": "body", "seen": False}, "large": {"focus": "body", "seen": False}}, out
    want = {"focus": "body", "posts": ["/answer", "/undo"], "sent": [{"type": "deny", "reason": 0}]}
    allow = dict(want, sent=[{"type": "allow_once"}])
    assert out == dict({k: want for k in ("small:button", "small:Backspace", "small:Escape", "large:button",
                                          "small:digit", "large:digit")},
                       **{"small:digit1": allow, "large:digit1": allow}), out


def test_an_undo_this_page_did_not_watch_leaves_the_key_focus_nowhere(tmp_path, clock):
    """ほかの頁が取り消した時、この頁は「決めている途中」の写しを受けないまま、同じ札の選ぶ画面 (表示の seq が進んだ写し) へ
    戻る事がある (外部のレビューの再現 = 「次から訊かない」に焦点を置いたまま Esc で止め、ほかの頁から取り消されると、焦点が
    同じ釦に付け直され、次の Enter が恒久の許可を送った)。同じ札で表示の seq だけが進んだ写しも取り消しとして扱い、鍵の焦点を
    どこにも置かない。扇でも大きな板でも同じ。"""
    a = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("git status")))
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["small", "large"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.btn("sugg:0").focus();                         /* 鍵で「次から訊かない」へ */
  await c.key("Escape", "Escape");                 /* 止める側を送る */
  c.show(reshown(A));                              /* ほかの頁が取り消した = 途中の写しを受けないまま、選ぶ画面へ戻る */
  await c.run(20);
  const focus = c.active();
  await c.run(580);
  await c.key("Enter", "Enter");                   /* 焦点はどこにも無い = 何も押さない */
  out[mode] = { focus: focus, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify(out));
""", A=a)
    want = {"focus": "body", "sent": ["stop"]}
    assert out == {"small": want, "large": want}, out


def test_moving_to_the_pip_window_and_back_keeps_the_key_focus(tmp_path, clock):
    """「常に手前」で別の窓 (Document Picture-in-Picture) へ移る・「元の窓へ」で戻る・窓を閉じて戻る時は、付け替える前に
    焦点の在った釦へ焦点を戻す (反証役の再現 = 焦点が先頭の「許可」へ移り、次の Enter が許可を送った)。戻す釦が無い時は、
    どこにも置かない。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja", pip: true });
c.show(PERM);
await c.run(500);
await c.key("Tab", "Tab");
c.$("pip-btn").focus();
await c.key("Enter", "Enter");                     /* 窓が見つからない = PiP の窓へ移る */
await c.run(20);
const inPip = { pip: c.vwin() !== c.win, focus: c.active() };
await c.run(600);
await c.key("Enter", "Enter");                     /* 「元の窓へ」 */
await c.run(20);
const back = { home: c.vwin() === c.win, focus: c.active() };
await c.run(600);
await c.key("Enter", "Enter");                     /* もう 1 回 PiP へ */
await c.run(600);
c.btn("deny").focus();                             /* PiP の中で「拒否 …」に焦点を置いて、窓の × で閉じる */
c.vwin().close();
await c.run(20);
const closed = { home: c.vwin() === c.win, focus: c.active() };
const lost = await P.boot({ query: "?mode=small&lang=ja", pip: true });
lost.show(PERM);
await lost.run(500);
await lost.key("Tab", "Tab");
lost.$("pip-btn").focus();
lost.event("keydown", { key: "Enter", code: "Enter", repeat: false, target: lost.doc().activeElement });
lost.doc().activeElement.blur();                   /* 窓が開く前に焦点が外れた = 戻す釦が無い */
await lost.run(20);
lost.event("keyup", { key: "Enter", code: "Enter" });
const nowhere = { pip: lost.vwin() !== lost.win, focus: lost.active() };
lost.vwin().close();                               /* 焦点の無いまま閉じて戻る */
await lost.run(20);
console.log(JSON.stringify({ inPip: inPip, back: back, closed: closed, nowhere: nowhere, nowhereBack: lost.active(),
                             sent: c.answers().length + lost.answers().length }));
""", PERM=perm)
    assert out == {"inPip": {"pip": True, "focus": "pip"}, "back": {"home": True, "focus": "pip"},
                   "closed": {"home": True, "focus": "deny"}, "nowhere": {"pip": True, "focus": "body"},
                   "nowhereBack": "body", "sent": 0}


def test_coming_back_from_the_pip_window_keeps_the_key_focus_on_undo(tmp_path, clock):
    """扇の PiP の窓で、猶予の内の「取り消す」に鍵の焦点を置いたまま窓を閉じて元へ戻っても、焦点は「取り消す」に残り、Enter で
    取り消せる (外部のレビューの再現 = 戻った後の描き直しが取り消しの枠を付け替えて焦点が外れ、Enter では取り消せなかった)。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja", pip: true });
c.show(PERM);
await c.run(500);
await c.key("Tab", "Tab");
c.$("pip-btn").focus();
await c.key("Enter", "Enter");                     /* PiP の窓へ移る */
await c.run(600);
c.btn("allow_once").focus();
await c.key("Enter", "Enter");                     /* 許可を送る */
c.show(deciding(PERM, { type: "allow_once" }));
await c.run(500);
c.$("undo-btn").focus();                           /* 猶予の内の「取り消す」へ */
c.vwin().close();                                  /* 窓の × で閉じて、元の窓へ戻る */
await c.run(20);
const focus = c.active();
await c.run(500);                                  /* 戻った直後の、押しを数えない間が過ぎてから */
await c.key("Enter", "Enter");
console.log(JSON.stringify({ home: c.vwin() === c.win, focus: focus, posts: c.posts() }));
""", PERM=perm)
    assert out == {"home": True, "focus": "undo", "posts": ["/answer", "/undo"]}, out


def test_moving_to_the_pip_window_by_mouse_leaves_no_key_focus(tmp_path, clock):
    """マウスで「常に手前」を押して別の窓へ移る・戻る時は、焦点を釦へ戻さない (戻すと、焦点の在る間、上の釦の帯が出たままに
    なる)。焦点を元の釦へ戻すのは、鍵で使っている時だけ。どちらの時も、先頭の「許可」へは置かない。"""
    perm = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja", pip: true });
c.show(PERM);
await c.run(500);
await c.click(c.$("pip-btn"));                     /* マウスで「常に手前」= 窓が見つからず PiP の窓へ移る */
await c.run(20);
const inPip = { pip: c.vwin() !== c.win, focus: c.active() };
await c.run(600);
await c.click(c.$("pip-btn"));                     /* マウスで「元の窓へ」 */
await c.run(20);
const back = { home: c.vwin() === c.win, focus: c.active() };
await c.run(600);
await c.key("Enter", "Enter");                     /* 焦点はどこにも無い = Enter は何も送らない */
console.log(JSON.stringify({ inPip: inPip, back: back, sent: c.answers().length }));
""", PERM=perm)
    assert out == {"inPip": {"pip": True, "focus": "body"}, "back": {"home": True, "focus": "body"}, "sent": 0}


def test_the_key_focus_on_a_button_the_page_takes_away_leaves_the_focus_nowhere(tmp_path, clock):
    """鍵の焦点が、札の替わりと一緒に消える釦 (「▼ 続き」・取り消しの釦) に在った時も、次の札の先頭 (許可) へ焦点を置かない
    (最初の直しは先頭へ置く形で、反証役が、遅れた Enter が次の札の許可を送る事を再現した)。次の Enter は何も起こさない
    (Tab・矢印・数字は効く)。取り消しは、扇でも大きな板でも同じ (扇では、描き直しが取り消しの枠を付け替えて焦点を外すので、
    頁は描く前に見る)。ほかの頁が取り消して選ぶ画面へ戻った後に、その札が替わった時も同じ。"""
    a = _card(clock)
    b = _card(clock)
    out = page(tmp_path, r"""
let c = await P.boot({ query: "?mode=small&lang=ja" });
c.$("copy").scrollHeight = 900; c.$("copy").clientHeight = 180;   /* 長い本文 = 「▼ 続き」が出る */
c.show(A);
await c.run(500);
const shown = !c.$("more").hidden;
await c.key("Tab", "Tab");
c.$("more").focus();
await c.key("Enter", "Enter");                     /* 1 画面送る */
c.$("copy").scrollHeight = 100;                    /* 次の札は短い = 「▼ 続き」は消える */
c.show(B);
const more = c.active();
const undo = {};
for (const mode of ["small", "large"]) for (const end of ["next", "undone"]) {
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("1", "Digit1");
  c.show(deciding(A, undefined));
  await c.run(500);
  await c.key("Tab", "Tab");
  c.$("undo-btn").focus();                         /* 取り消しに焦点を置いたまま、押さない */
  if (end === "undone") { c.show(reshown(A)); await c.run(500); }   /* ほかの頁が取り消した = 選ぶ画面へ戻る */
  c.show(B);                                       /* 次の札が来た (猶予の内に札が終わった・戻った札が時間切れになった) */
  await c.run(20);                                 /* 隠れた取り消しの釦から焦点が外れる (次のこま) */
  const focus = c.active();
  await c.run(580);
  await c.key("Enter", "Enter");
  undo[mode + ":" + end] = { focus: focus, sent: choices(c).map(function (x) { return x.type; }) };
}
console.log(JSON.stringify({ shown: shown, more: more, undo: undo }));
""", A=a, B=b)
    left = {"focus": "body", "sent": ["allow_once"]}
    assert out == {"shown": True, "more": "body",
                   "undo": {"small:next": left, "small:undone": left, "large:next": left, "large:undone": left}}, out


def test_the_undo_band_coming_or_going_does_not_unguard_the_button_under_the_pointer(tmp_path, clock):
    """取り消しの枠が釦に重なる配置 (横長・縦に伸ばした小窓・低い大きな板) でも、枠の出入りで pointer の下に来た物は、
    入り直すまで滞留で押さない (反証役の再現 = 枠の下に出た次の札の釦が約 1 秒で送られ、取り消し → 送り直しが繰り返した)。
    取り消しの枠と「▼ 続き」は、pointer の下を確かめる前に出し入れする。"""
    a = _card(clock)
    b = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja&dwell=1" });
c.doc().layout = function (e) {                    /* 取り消しの枠が「許可」の上の半分に重なる */
  if (e.id === "undo-btn") return { left: 0, top: 0, width: 600, height: 120, z: 31 };
  if (e.id === "undo-zone") return { left: 0, top: 0, width: 600, height: 120, z: 30 };
  if (e.dataset.key === "allow_once") return { left: 0, top: 60, width: 300, height: 100, z: 1 };
  return null;
};
const at = function () { c.pointer(50, 80); };     /* 枠と「許可」が重なる所 (視線の道具と同じ 10 ms の流れ) */
c.show(A);
await c.run(600, function () { c.pointer(400, 400); });
await c.run(1300, at);                             /* 入って 1 秒 = 滞留で「許可」を送る */
const answered = c.posts();
c.show(deciding(A));                               /* 枠が pointer の上に出た */
await c.run(2000, at);                             /* 入り直していない = 取り消しを押さない */
const undoAfterAnswer = c.posts();
c.show(B);                                         /* 答えが渡り、次の札が来た = 枠が消えて、下に次の「許可」 */
await c.run(3000, at);
const restingOnNext = c.posts();
await c.run(300, function () { c.pointer(400, 400); });
await c.run(1300, at);                             /* 入り直す */
console.log(JSON.stringify({ answered: answered, undoAfterAnswer: undoAfterAnswer, restingOnNext: restingOnNext,
                             reentered: c.answers().map(function (s) { return [s.body.id === B.id, s.body.by]; }) }));
""", A=a, B=b)
    assert out["answered"] == ["/answer"]
    assert out["undoAfterAnswer"] == ["/answer"]
    assert out["restingOnNext"] == ["/answer"]
    assert out["reentered"] == [[False, "dwell"], [True, "dwell"]]


def test_closing_the_settings_does_not_press_what_waits_under_the_pointer(tmp_path, clock):
    """設定の板を閉じた直後、板の裏で置いたままの pointer の下に居た釦は、入り直すまで滞留で押さない (反証役の再現 =
    閉じた後のこまが pointer の知らせより先に来ると守りが解け、止まったマウスが 1 px 動いた後に約 1 秒で押された)。
    Esc でも「閉じる」でも、板を開いている間に札が替わっていても、閉じた後に pointer が一度も動かなくても (止まったマウスは
    知らせを出さない) 同じ。閉じた後に最初に届いた pointer の下の釦も、入り直すまで数えない (板が開いていた間の位置と、
    その下の物は信じない)。"""
    a = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("git status")))
    b = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("npm test")))
    out = page(tmp_path, r"""
async function scene(how, swap, first) {
  const c = await P.boot({ query: "?mode=large&lang=ja&dwell=1" });
  c.doc().layout = function (e) {
    if (e.id === "overlay") return { left: 0, top: 0, width: 640, height: 700, z: 50 };
    if (e.dataset.key === "allow_once") return { left: 0, top: 0, width: 100, height: 100, z: 1 };
    if (e.dataset.key === "sugg:0") return { left: 200, top: 0, width: 100, height: 100, z: 1 };
    return null;
  };
  c.show(A);
  await c.run(600, function () { c.pointer(400, 400); });   /* 釦の外 */
  await c.key("Tab", "Tab");
  c.$("gear-btn").focus();
  await c.key("Enter", "Enter");                   /* 設定の板を開く */
  await c.run(300, function () { c.pointer(40, 40); });     /* 板の上 (裏に「許可」) */
  if (swap) c.show(B);                             /* 板を開いている間に、板から札が替わった */
  await c.run(300);                                /* pointer は止まった */
  if (how === "esc") await c.key("Escape", "Escape");
  else await c.click(c.$("panel-close"));
  await c.run(500);                                /* 閉じた後のこまが先 (pointer は止まったまま) */
  if (first) c.pointer(first[0], first[1]);        /* 0.5 秒後に最初の知らせ (無し = 止まったマウスは知らせを出さない) */
  await c.run(2500);
  const resting = c.answers().length;
  const back = first || [40, 40];
  await c.run(300, function () { c.pointer(400, 400); });
  await c.run(1300, function () { c.pointer(back[0] + 1, back[1]); });     /* 入り直す */
  return { resting: resting, open: !c.$("overlay").hidden, reentered: c.answers().length };
}
console.log(JSON.stringify({ esc: await scene("esc", false, [41, 40]), close: await scene("close", false, [41, 40]),
                             swapped: await scene("esc", true, [41, 40]), movedAway: await scene("esc", false, [240, 40]),
                             still: await scene("esc", false, null) }));
""", A=a, B=b)
    want = {"resting": 0, "open": False, "reentered": 1}
    assert out == {"esc": want, "close": want, "swapped": want, "movedAway": want, "still": want}


def test_scrolling_only_the_text_does_not_hold_back_the_next_dwell(tmp_path, clock):
    """本文の枠・和紙だけが送られた時 (押せる物は動いていない) は、次に見た釦を入り直さずに滞留で押せる (反証役の再現 =
    本文から「許可」へ視線を移す途中で本文が数 px 送られると、見続けても押せなかった・扇で「▼ 続き」の 0.3 秒後に羽根へ
    着くと押せなかった)。逆向き: 押せる釦を含む列が送られた時は、今までどおり pointer の下に来た釦を入り直すまで押さない
    (要素の送りは泡立たない = capture の聞き手だけが受ける)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const out = {};
let c = await P.boot({ query: "?mode=large&lang=ja&dwell=1" });
c.$("card").scrollHeight = 3000; c.$("card").clientHeight = 300;
c.doc().layout = function (e) {
  if (e.id === "card") return { left: 0, top: 0, width: 600, height: 300, z: 0 };
  if (e.dataset.key === "allow_once") return { left: 0, top: 320, width: 300, height: 100, z: 1 };
  return null;
};
c.show(A);
await c.run(1000, function () { c.pointer(100, 150); });        /* 本文の真ん中で読む */
await c.run(200, function () { c.pointer(100, 285); });         /* 下寄りの帯を通る = 本文が送られる */
const textMoved = c.$("card").scrollTop > 0;
let arrived = c.clock.now;
await c.run(1500, function () { c.pointer(100, 370); });        /* 「許可」を見続ける */
out.text = { moved: textMoved, after: c.answers().map(function (s) { return Math.round(s.at - arrived); }) };
c = await P.boot({ query: "?mode=small&lang=ja&dwell=1" });
c.$("copy").scrollHeight = 900; c.$("copy").clientHeight = 180;
c.doc().layout = function (e) {
  if (e.id === "more") return { left: 0, top: 600, width: 200, height: 40, z: 1 };
  if (e.dataset.key === "allow_once") return { left: 0, top: 0, width: 100, height: 100, z: 1 };
  return null;
};
c.show(A);
await c.run(600, function () { c.pointer(400, 400); });
await c.run(450, function () { c.pointer(50, 610); });          /* 「▼ 続き」に載せる = 0.35 秒で 1 画面送る */
const paged = c.$("copy").scrollTop > 0;
await c.run(300, function () { c.pointer(400, 400); });         /* 和紙を 0.3 秒読む */
arrived = c.clock.now;
await c.run(1500, function () { c.pointer(50, 50); });          /* 羽根へ */
out.fan = { paged: paged, after: c.answers().map(function (s) { return Math.round(s.at - arrived); }) };
c = await P.boot({ query: "?mode=large&lang=ja&dwell=1" });
c.$("opts").scrollHeight = 2000; c.$("opts").clientHeight = 400;
let shift = 0;
c.doc().layout = function (e) {                                 /* 「許可」は置いたままの pointer の少し下 */
  return e.dataset.key === "allow_once" ? { left: 0, top: 200 - shift, width: 300, height: 90, z: 1 } : null;
};
c.show(A);
await c.run(600, function () { c.pointer(400, 400); });
await c.run(1000, function () { c.pointer(50, 195); });         /* 釦の上の隙間に置いたまま */
c.$("opts").scrollTop = 50; shift = 50;                         /* ホイールで列が送られた = pointer の下に「許可」が来た */
await c.run(3000, function () { c.pointer(50, 195); });         /* ブラウザが配る、下の物が替わった知らせ */
out.list = { resting: c.answers().length };
await c.run(300, function () { c.pointer(400, 400); });
await c.run(1300, function () { c.pointer(50, 195); });         /* 入り直す */
out.list.reentered = choices(c);
console.log(JSON.stringify(out));
""", A=a)
    for name in ("text", "fan"):
        after = out[name]["after"]
        assert len(after) == 1 and 1000 <= after[0] <= 1040, out          # 着いてから 1 秒 = 入り直さずに押せる
    assert out["text"]["moved"] is True and out["fan"]["paged"] is True
    assert out["list"] == {"resting": 0, "reentered": [{"type": "allow_once"}]}


def test_a_scan_step_that_scrolls_nothing_keeps_the_dwell(tmp_path, clock):
    """滞留と走査を両方入れた列で、走査の光が進んでも列が送られなかった時 (列が窓に収まる) は、見に来た釦の滞留を捨てない
    (反証役の再現 = 光が進むたびに送りの守りが掛かり、止まった pointer で釦を見続けても押せなかった)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja&dwell=1&scan=1.5" });
c.doc().layout = function (e) {
  if (e.dataset.key === "allow_once") return { left: 0, top: 0, width: 300, height: 100, z: 1 };
  if (e.dataset.key === "deny") return { left: 0, top: 120, width: 300, height: 100, z: 1 };
  return null;
};
c.show(A);
await c.run(100);
c.pointer(400, 400);                               /* 窓の中の釦の外に、止まったマウス */
await c.run(3100);                                 /* 止まって 1.5 秒で走査が回る (光は 1.5 秒ごとに次へ) */
const lit = c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; });
c.pointer(50, 50);                                 /* 光が進んだ直後に「許可」へ動かして置く (以後は動かさない) */
const arrived = c.clock.now;
await c.run(2000);
console.log(JSON.stringify({ lit: lit, after: c.answers().map(function (s) { return [Math.round(s.at - arrived), s.body.by]; }) }));
""", A=a)
    assert out["lit"] == ["deny"], out
    assert len(out["after"]) == 1 and 1000 <= out["after"][0][0] <= 1040 and out["after"][0][1] == "dwell", out


def test_the_undo_light_comes_on_when_undo_can_be_pressed(tmp_path, clock):
    """走査の光は、取り消しが押せるようになった時から取り消しに当たる (光っていない物は押せない)。猶予の短い板 (--undo-ms 300)
    では猶予の半分の 0.15 秒から、既定の猶予では 0.4 秒から (反証役の再現 = 猶予 300 ms の間、光は 1 度も出ないのに、
    スイッチの押しは 0.15 秒から取り消しになった)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const ms of [300, 3000]) {
  const c = await P.boot({ query: "?mode=small&lang=ja&scan=0.5", undoMs: ms });
  c.show(A);
  await c.run(500);
  await c.key("1", "Digit1");
  c.show(deciding(A, null, ms / 1000));            /* 板が受けた = 猶予の内 */
  const from = c.clock.now;
  let first = null;
  for (let i = 0; i < 60 && first === null; i++) {
    await c.run(8);
    if (c.$("undo-btn").classList.contains("scan")) first = Math.round(c.clock.now - from);
  }
  out[ms] = first;
}
console.log(JSON.stringify(out));
""", A=a)
    assert out["300"] is not None and 150 <= out["300"] <= 175, out
    assert out["3000"] is not None and 400 <= out["3000"] <= 425, out


def test_a_number_key_takes_two_presses_only_for_dont_ask_again(tmp_path, clock):
    """数字の鍵で「次から訊かない」(settings に恒久で書く許可) を押す時だけ、同じ数字を 1.5 秒の内にもう 1 回押して決める
    (札 #216 B)。1 回目は選ぶだけ (釦に選んだ印・大きな板は上の帯に案内)。扇に鍵の焦点が在るまま端末を見て打った数字が、
    扇の番号で恒久の規則を書かない (頁の点検 F2 の再現 = 選択肢 2 件の札で「3」が 1 回で allow_always を送った)。
    1.5 秒を過ぎた 2 回目と、別の数字を挟んだ後は選び直し。今回の許可は 1 回のまま。札が出た直後・窓が焦点を得た直後の
    0.4 秒の数字は、選ぶ 1 回目にも数えない。答えが決まった後 (同じ数字の 2 打目・別の数字の名指し) は「同じ数字を
    もう 1 回」の案内を残さない (2 巡目 i20 = 猶予の帯の上に最長 1.5 秒残った)。"""
    two = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("git status") + _rule("npm test")))
    out = page(tmp_path, r"""
function armed(c) { return c.doc().querySelectorAll(".armed").map(function (b) { return b.dataset.key; }); }
const out = {};
for (const mode of ["small", "large"]) {
  const r = {};
  let c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(500);
  r.keys = c.S.optionKeys.slice();
  await c.key("3", "Digit3");                      /* 2 つ目の「次から訊かない」= 選ぶだけ */
  r.first = { sent: c.answers().length, armed: armed(c), notice: c.$("status").textContent.indexOf("同じ数字") >= 0 };
  await c.run(300);
  await c.key("3", "Digit3");                      /* 0.3 秒後の同じ数字 = 決まる */
  r.second = choices(c);
  c.show(deciding(TWO, { type: "allow_always", suggestion: 1 })); await c.run(300);
  r.secondStatus = c.$("status").textContent;      /* 決まった後に案内を残さない */
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(500);
  await c.key("3", "Digit3");                      /* 選ぶだけ = 案内が出る */
  await c.key("1", "Digit1");                      /* 許可 (今回) を名指し = 送られる */
  r.named = choices(c);
  c.show(deciding(TWO, { type: "allow_once" })); await c.run(300);
  r.afterDecide = c.$("status").textContent;       /* 別の数字で決まった後も案内を残さない */
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(500);
  await c.key("2", "Digit2");
  await c.run(1600);                               /* 1.5 秒を過ぎた = 選び直し */
  await c.key("2", "Digit2");
  r.lapsed = { sent: c.answers().length, armed: armed(c) };
  await c.key("3", "Digit3");                      /* 別の数字 = 選び替え */
  r.switched = { sent: c.answers().length, armed: armed(c) };
  await c.key("3", "Digit3");
  r.switchedThen = choices(c);
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(500);
  await c.key("1", "Digit1");                      /* 今回の許可は 1 回のまま */
  r.once = choices(c);
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(100);
  await c.key("2", "Digit2");                      /* 札が出て 0.1 秒 = 選ぶ 1 回目にも数えない */
  await c.run(500);
  await c.key("2", "Digit2");                      /* これが 1 回目 */
  r.fresh = { sent: c.answers().length, armed: armed(c) };
  await c.key("2", "Digit2");
  r.freshThen = choices(c);
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(TWO); await c.run(2000);
  c.win.listeners.fire("focus", {});
  await c.run(100);
  await c.key("2", "Digit2");                      /* 窓が焦点を得て 0.1 秒 = 選ぶ 1 回目にも数えない */
  await c.run(500);
  await c.key("2", "Digit2");                      /* これが 1 回目 */
  r.focused = { sent: c.answers().length, armed: armed(c) };
  await c.key("2", "Digit2");
  r.focusedThen = choices(c);
  out[mode] = r;
}
console.log(JSON.stringify(out));
""", TWO=two)
    always0 = [{"type": "allow_always", "suggestion": 0}]
    always1 = [{"type": "allow_always", "suggestion": 1}]
    want = {"keys": ["allow_once", "sugg:0", "sugg:1", "deny"],
            "first": {"sent": 0, "armed": ["sugg:1"], "notice": True}, "second": always1, "secondStatus": "",
            "named": [{"type": "allow_once"}], "afterDecide": "",
            "lapsed": {"sent": 0, "armed": ["sugg:0"]}, "switched": {"sent": 0, "armed": ["sugg:1"]}, "switchedThen": always1,
            "once": [{"type": "allow_once"}],
            "fresh": {"sent": 0, "armed": ["sugg:0"]}, "freshThen": always0,
            "focused": {"sent": 0, "armed": ["sugg:0"]}, "focusedThen": always0}
    assert out == {"small": want, "large": want}, out


def test_a_click_and_a_number_do_not_make_one_double_press(tmp_path, clock):
    """扇の 2 回押しの 1 回目と 2 回目は、同じ入り方 (click 同士・同じ数字同士) の時だけ決める。click で選んだ
    「次から訊かない」を、迷い込んだ数字 1 つで決めない。数字で選んだ物を click 1 回でも決めない (外の目の 6 巡目の再現 =
    click と数字が同じ「選んだ」の控えを使い、click の後の数字 1 つで allow_always を送った)。"""
    two = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("git status") + _rule("npm test")))
    out = page(tmp_path, r"""
function armed(c) { return c.doc().querySelectorAll(".armed").map(function (b) { return b.dataset.key; }); }
const out = {};
let c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(TWO); await c.run(500);
await c.click(c.btn("sugg:0"));                    /* click で選ぶ (1 回目) */
await c.run(200);
await c.key("2", "Digit2");                        /* 端末へ向けたつもりの数字 = 決めない (数字の 1 回目として選び直す) */
out.clickThenDigit = { sent: c.answers().length, armed: armed(c) };
await c.key("2", "Digit2");
out.clickThenDigitThen = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(TWO); await c.run(500);
await c.key("2", "Digit2");                        /* 数字で選ぶ (1 回目) */
await c.run(200);
await c.click(c.btn("sugg:0"));                    /* click 1 回 = 決めない (click の 1 回目として選び直す) */
out.digitThenClick = { sent: c.answers().length, armed: armed(c) };
await c.run(200);
await c.click(c.btn("sugg:0"));
out.digitThenClickThen = choices(c);
console.log(JSON.stringify(out));
""", TWO=two)
    always0 = [{"type": "allow_always", "suggestion": 0}]
    assert out == {"clickThenDigit": {"sent": 0, "armed": ["sugg:0"]}, "clickThenDigitThen": always0,
                   "digitThenClick": {"sent": 0, "armed": ["sugg:0"]}, "digitThenClickThen": always0}, out


def test_enter_or_space_on_the_key_focus_takes_two_presses_only_for_dont_ask_again(tmp_path, clock):
    """焦点の上の Enter / Space で「次から訊かない」(settings に恒久で書く許可) を押す時も、数字と同じく 1.5 秒の内に
    もう 1 回押して決める (最終デバッグ 1 巡目 #19 の再現 = 扇に焦点を持たせた後の、端末の「No」の癖の ↓↓Enter が、
    扇では「次から訊かない」に当たり、1 押しで送った)。1 回目は選ぶだけ (選んだ印と案内)・1.5 秒を過ぎた 2 回目は
    選び直し・決まった後は案内を残さない。2 回目は同じ入り方 (焦点の上の鍵) の時だけ決める = click で選んだ羽根を
    Enter 1 回で、鍵で選んだ羽根を数字や click 1 回で決めない。今回の許可は焦点の Enter 1 回のまま。大きな板で Tab から
    置いた焦点の Enter も同じ。"""
    one = _card(clock, payload=dict(PERM_PAYLOAD, suggestions=_rule("git status")))
    out = page(tmp_path, r"""
function armed(c) { return c.doc().querySelectorAll(".armed").map(function (b) { return b.dataset.key; }); }
function told(c) { return c.$("status").textContent.indexOf("同じキー") >= 0; }
async function reach(c, nav) {                     /* 鍵の焦点を 3 番目の羽根 (次から訊かない) へ */
  if (nav === "Tab") { await c.key("Tab", "Tab"); c.btn("sugg:0").focus(); }
  else { await c.key(nav, nav); await c.key(nav, nav); }
}
async function fresh(mode) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(ONE); await c.run(500);
  return c;
}
const out = {};
for (const [name, mode, nav, key, code] of [["rightEnter", "small", "ArrowRight", "Enter", "Enter"],
    ["downEnter", "small", "ArrowDown", "Enter", "Enter"], ["rightSpace", "small", "ArrowRight", " ", "Space"],
    ["tabEnter", "large", "Tab", "Enter", "Enter"]]) {
  const r = {};
  let c = await fresh(mode);
  await reach(c, nav);
  r.focus = c.active();
  await c.key(key, code);                          /* 1 回目 = 選ぶだけ */
  r.first = { sent: c.answers().length, armed: armed(c), told: told(c) };
  await c.run(500);
  await c.key(key, code);                          /* 0.5 秒後の 2 回目 = 決まる */
  r.second = choices(c);
  c.show(deciding(ONE, { type: "allow_always", suggestion: 0 })); await c.run(300);
  r.after = c.$("status").textContent;
  c = await fresh(mode);
  await reach(c, nav);
  await c.key(key, code);
  await c.run(1600);                               /* 1.5 秒を過ぎた 2 回目 = 選び直し */
  await c.key(key, code);
  r.lapsed = { sent: c.answers().length, armed: armed(c) };
  out[name] = r;
}
for (const gap of [100, 600]) {
  const c = await fresh("small");
  await c.click(c.btn("sugg:0"));                  /* click で選ぶ (羽根に焦点も来る) */
  await c.run(gap);
  await c.key("Enter", "Enter");                   /* click の 2 回目にしない = 鍵の 1 回目として選び直す */
  out["click" + gap] = { sent: c.answers().length, armed: armed(c), by: c.S.armBy };
}
let c = await fresh("small");
await c.key("ArrowRight", "ArrowRight");           /* 焦点は 2 番目の羽根 (許可 今回) */
await c.key("Enter", "Enter");
out.once = choices(c);
c = await fresh("small");
await c.key("2", "Digit2");                        /* 数字の 1 回目 (前からの形) */
out.digit = { sent: c.answers().length, armed: armed(c), by: c.S.armBy };
c = await fresh("small");
await reach(c, "ArrowRight");
await c.key("Enter", "Enter");                     /* 鍵で選ぶ */
await c.key("2", "Digit2");                        /* 数字 1 つでは決めない (数字の 1 回目として選び直す) */
out.keyThenDigit = { sent: c.answers().length, armed: armed(c), by: c.S.armBy };
c = await fresh("small");
await reach(c, "ArrowRight");
await c.key("Enter", "Enter");
await c.run(200);
await c.click(c.btn("sugg:0"));                    /* click 1 回でも決めない (click の 1 回目として選び直す) */
out.keyThenClick = { sent: c.answers().length, armed: armed(c), by: c.S.armBy };
console.log(JSON.stringify(out));
""", ONE=one)
    always = [{"type": "allow_always", "suggestion": 0}]
    want = {"focus": "sugg:0", "first": {"sent": 0, "armed": ["sugg:0"], "told": True}, "second": always, "after": "",
            "lapsed": {"sent": 0, "armed": ["sugg:0"]}}
    picked = {"sent": 0, "armed": ["sugg:0"]}
    assert out == {"rightEnter": want, "downEnter": want, "rightSpace": want, "tabEnter": want,
                   "click100": dict(picked, by="key"), "click600": dict(picked, by="key"),
                   "once": [{"type": "allow_once"}], "digit": dict(picked, by="digit"),
                   "keyThenDigit": dict(picked, by="digit"), "keyThenClick": dict(picked, by="click")}, out


def test_a_resuming_scan_keeps_the_quiet_after_the_window_got_the_focus(tmp_path, clock):
    """pointer が止まって走査が戻る時も、窓が焦点を得た後の静かな 1 こまは短くしない (外の目の 6 巡目の再現 = 焦点の
    0.5 秒後に pointer の止まりで走査が戻り、0.4 秒の鍵の間が終わった後に許可が光った)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
function lit(c) { return c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; })[0] || null; }
const c = await P.boot({ query: "?mode=small&lang=ja&scan=1.5" });
c.show(A); await c.run(3000);
c.pointer(5, 5);                                   /* 窓の中で pointer が動いた = 走査は 1.5 秒止まる */
await c.run(1000);
c.win.listeners.fire("focus", {});                 /* 動きの 1 秒後に窓が焦点を得た = 静かな間は焦点から 1.5 秒 */
await c.run(700);                                  /* 焦点の 0.7 秒後 (pointer の止まりで走査が戻るのは 0.5 秒後) */
const early = lit(c);
await c.run(900);                                  /* 焦点の 1.6 秒後 */
console.log(JSON.stringify({ early: early, later: lit(c) }));
""", A=a)
    assert out == {"early": None, "later": "allow_once"}, out


def test_the_window_getting_the_focus_does_not_relight_the_allow_or_count_keys_at_once(tmp_path, clock):
    """窓が鍵の焦点を得た直後 (別の窓を閉じた時に OS が扇へ焦点を移す・人が扇を click する) は、走査を頭 (許可) からすぐには
    光らせず、静かな 1 こまを置いてから回す。鍵とスイッチの押しは 0.4 秒数えず、その間は頁に印 (body.settling) を付ける
    = 光っていた「止」へ向けたスイッチの 1 押しや、別の窓へ向けて打った数字が、許可に当たらない (頁の点検 F3 の再現 =
    焦点の 20 ms 後に「許可」が光り、Space で allow_once を送った)。マウスの click は数える (焦点の無い窓を click した
    最初の押しを捨てない)。猶予の取り消しも数える (安全の側)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
function lit(c) { return c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; })[0] || null; }
function focusWindow(c) { c.win.listeners.fire("focus", {}); }
const out = {};
for (const mode of ["small", "large"]) {
  /* スイッチ: 光が「許可」から離れた所で、窓に焦点が来る */
  let c = await P.boot({ query: "?mode=" + mode + "&lang=ja&scan=1.5" });
  c.show(A);
  await c.run(5000);
  const before = lit(c);
  focusWindow(c);
  await c.run(20);
  const sw = { moved: before !== null && before !== "allow_once", lit: lit(c), mark: c.doc().body.classList.contains("settling") };
  await c.key(" ", "Space");
  sw.sent = c.answers().length;
  await c.run(450);
  sw.markAfter = c.doc().body.classList.contains("settling");
  await c.run(1300);                               /* 焦点から 1.77 秒 = 静かな 1 こま (1.5 秒) の後 */
  sw.later = lit(c);
  await c.key(" ", "Space");
  sw.laterSent = choices(c);
  out[mode + ":switch"] = sw;
  /* 数字 (行き先を名指しする鍵): 焦点の 0.1 秒後は数えない・0.6 秒後は数える */
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(2000);
  focusWindow(c);
  await c.run(100);
  await c.key("1", "Digit1");
  const early = c.answers().length;
  await c.run(500);
  await c.key("1", "Digit1");
  out[mode + ":digit"] = { early: early, later: choices(c) };
  /* 取り消し: 猶予の内に窓へ焦点が来ても、直後の Backspace は取り消す */
  c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.show(A);
  await c.run(2000);
  await c.key("1", "Digit1");
  c.show(deciding(A));
  await c.run(500);
  focusWindow(c);
  await c.run(20);
  await c.key("Backspace", "Backspace");
  out[mode + ":undo"] = c.posts();
}
/* 札の来る前 (待ちの頁を開いた直後) に焦点が来ても、印は 0.4 秒で外れる (実ブラウザの試験の再現 = 世代の時刻が未定義で、
   印が外れずに次の click が待ち続けた) */
const w = await P.boot({ query: "?mode=small&lang=ja" });
await w.run(100);
focusWindow(w);
await w.run(20);
const waitMark = w.doc().body.classList.contains("settling");
await w.run(450);
out["waiting"] = { mark: waitMark, markAfter: w.doc().body.classList.contains("settling") };
/* マウス: 大きな板の釦は 1 回の click で決まる。焦点を得た直後の click も数える */
const m = await P.boot({ query: "?mode=large&lang=ja" });
m.show(A);
await m.run(2000);
focusWindow(m);
await m.run(20);
await m.click(m.btn("allow_once"));
out["large:click"] = choices(m);
console.log(JSON.stringify(out));
""", A=a)
    allow = [{"type": "allow_once"}]
    switch = {"moved": True, "lit": None, "mark": True, "sent": 0, "markAfter": False, "later": "allow_once", "laterSent": allow}
    want = {}
    for mode in ("small", "large"):
        want[mode + ":switch"] = switch
        want[mode + ":digit"] = {"early": 0, "later": allow}
        want[mode + ":undo"] = ["/answer", "/undo"]
    want["large:click"] = allow
    want["waiting"] = {"mark": True, "markAfter": False}
    assert out == want, out


def test_a_key_held_when_the_window_lost_the_focus_is_let_go_when_it_comes_back(tmp_path, clock):
    """押したままの鍵の印 (S.held) は、窓が焦点を取り戻した時に捨てる (最終デバッグ 1 巡目 #10・#33 の再現 = 鍵を押したまま
    窓が焦点を失うと、離した知らせ (keyup) は別の窓へ行き、戻った後の最初の 1 押し (取り消しを含む) が黙って捨てられた)。
    mac の ⌘ と組んだ鍵 (⌘ を押している間は離した知らせが来ない) には、初めから押したままの印を立てない。対照 = 押したまま
    繰り返す鍵 (repeat) は焦点が戻った後も数えない・焦点を失わない間の、離していない鍵の 2 打目は今までどおり数えない。"""
    a = _card(clock)
    out = page(tmp_path, r"""
function down(c, key, code, more) {               /* keydown だけ (離した知らせは届かない) */
  return c.event("keydown", Object.assign({ key: key, code: code, repeat: false, ctrlKey: false, altKey: false, metaKey: false,
                                            target: c.doc().activeElement }, more || {}));
}
function lit(c) { return c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; })[0] || null; }
async function untilLit(c, key) { for (let i = 0; i < 400 && lit(c) !== key; i++) await c.run(16); return lit(c); }
function away(c) { c.win.listeners.fire("blur", {}); }
function back(c) { c.win.listeners.fire("focus", {}); }
const out = {};
let c = await P.boot({ query: "?mode=small&lang=ja&scan=1" });
await c.run(500);
down(c, " ", "Space");                             /* 待ちの扇で押したまま、窓が焦点を失う */
away(c); await c.run(200); back(c); await c.run(500);
c.show(A);
out.waitingLit = await untilLit(c, "allow_once");
await c.key(" ", "Space");                         /* 戻った後の 1 押し = 光った許可を押す */
out.waiting = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja&scan=1" });
c.show(A);
out.answerLit = await untilLit(c, "allow_once");
down(c, " ", "Space");                             /* 答えて、離さないまま窓が焦点を失う */
out.answered = choices(c);
c.show(deciding(A, { type: "allow_once" }));
away(c); await c.run(100); back(c);
out.undoLit = await untilLit(c, "undo");
await c.key(" ", "Space");                         /* 猶予の内の取り消しの 1 押し */
out.undo = c.posts();
c = await P.boot({ query: "?mode=small&lang=ja" });
c.show(A); await c.run(500);
down(c, "1", "Digit1", { metaKey: true });         /* ⌘+1 (離した知らせは来ない) */
await c.run(300);
await c.key("1", "Digit1");                        /* 素の 1 = 1 押し目で押せる */
out.meta = choices(c);
c = await P.boot({ query: "?mode=small&lang=ja&scan=1" });
c.show(A);
await untilLit(c, "allow_once");
away(c); await c.run(100); back(c);
out.repeatLit = await untilLit(c, "allow_once");
down(c, " ", "Space", { repeat: true });           /* 押したまま繰り返す鍵 = 焦点が戻った後も数えない */
out.repeat = c.answers().length;
c = await P.boot({ query: "?mode=small&lang=ja&scan=1" });
c.show(A);
await untilLit(c, "allow_once");
down(c, " ", "Space");
c.show(deciding(A, { type: "allow_once" }));
out.heldLit = await untilLit(c, "undo");
down(c, " ", "Space");                             /* 焦点を失っていない = 離していない鍵の 2 打目は数えない */
out.held = c.posts();
console.log(JSON.stringify(out));
""", A=a)
    once = [{"type": "allow_once"}]
    assert out == {"waitingLit": "allow_once", "waiting": once,
                   "answerLit": "allow_once", "answered": once, "undoLit": "undo", "undo": ["/answer", "/undo"],
                   "meta": once, "repeatLit": "allow_once", "repeat": 0,
                   "heldLit": "undo", "held": ["/answer"]}, out


def test_the_close_button_of_the_settings_answers_enter_and_space(tmp_path, clock):
    """設定の板の「閉じる」に焦点が在る時は、Enter / Space で閉じる (反証役の再現 = Esc とマウスでしか閉じなかった)。
    板の中の選択の上の Enter には触らない (板は開いたまま)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const key of ["Enter", " "]) {
  const c = await P.boot({ query: "?mode=small&lang=ja" });
  c.show(A);
  await c.run(500);
  await c.key("Tab", "Tab");
  c.$("gear-btn").focus();
  await c.key("Enter", "Enter");                   /* 設定の板が開き、焦点は「閉じる」 */
  const opened = { open: !c.$("overlay").hidden, focus: c.active() };
  await c.run(600);
  await c.key(key, key === " " ? "Space" : "Enter");
  out[key === " " ? "space" : "enter"] = { opened: opened, closed: c.$("overlay").hidden, sent: c.answers().length };
}
const d = await P.boot({ query: "?mode=small&lang=ja" });
d.show(A);
await d.run(500);
await d.key("Tab", "Tab");
d.$("gear-btn").focus();
await d.key("Enter", "Enter");
d.$("panel-body").querySelector("select").focus();
await d.key("Enter", "Enter");
out.select = { open: !d.$("overlay").hidden, focus: d.active() };
console.log(JSON.stringify(out));
""", A=a)
    want = {"opened": {"open": True, "focus": "close"}, "closed": True, "sent": 0}
    assert out == {"enter": want, "space": want, "select": {"open": True, "focus": "select"}}


def test_a_doubled_space_on_the_settings_close_does_not_reach_the_scan(tmp_path, clock):
    """走査 (1 鍵のスイッチ = Space) の板で、設定の板を「閉じる」の Space で閉じ、次のこまの直後にばたつきでもう 1 度 Space を
    押しても、答えは送られない (外の目の 8 巡目 = 閉じた直後に走査の光が許可へ戻り、2 打目が allow_once を送った)。閉じた直後は
    「表示が替わった直後」と同じ静かな間 (押しを数えない 0.4 秒・走査は間を置いて頭から) = 光は消え、頁に印 (settling) が付く。
    静かな間の後は、スイッチで光っている釦 (頭 = 許可) を押せる (スイッチは生きている)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
function lit(c) { return c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; })[0] || null; }
const out = {};
for (const mode of ["large", "small"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja&scan=0.5" });
  c.show(A);
  await c.run(1300);                                /* 走査が回り、光は許可から離れた所 */
  c.$("gear-btn").focus();
  await c.key("Enter", "Enter");                   /* 設定の板が開き、焦点は「閉じる」 */
  await c.run(600);
  await c.key(" ", "Space");                       /* 1 打目 = 閉じる */
  const r = { closed: c.$("overlay").hidden, mark: c.doc().body.classList.contains("settling"), lit: lit(c) };
  await c.run(16);                                  /* 次のこま */
  await c.run(50);
  await c.key(" ", "Space");                       /* 2 打目 = ばたつき */
  r.early = c.answers().length;
  await c.run(550);                                 /* 閉じてから 0.62 秒 = 静かな間 (0.5 秒) の後、光は頭 (許可) に戻っている */
  r.later = lit(c);
  await c.key(" ", "Space");
  r.laterSent = choices(c);
  out[mode] = r;
}
console.log(JSON.stringify(out));
""", A=a)
    want = {"closed": True, "mark": True, "lit": None, "early": 0, "later": "allow_once", "laterSent": [{"type": "allow_once"}]}
    assert out == {"large": want, "small": want}, out


def test_a_card_arriving_right_after_the_settings_close_finds_the_first_button(tmp_path, clock):
    """設定の板を「閉じる」の Enter で閉じた同じこま (隠れた「閉じる」に、ブラウザが焦点を外すまで焦点が残っている) に札が来た時 =
    焦点はどこにも無いのと同じ → 今までどおり先頭へ置く (隠れた釦に残る焦点を「人が置いた焦点」に数えない)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=large&lang=ja" });
await c.run(100);
await c.key("Tab", "Tab");
c.$("gear-btn").focus();
await c.key("Enter", "Enter");                     /* 設定の板が開き、焦点は「閉じる」 */
await c.run(600);
await c.key("Enter", "Enter");                     /* 「閉じる」の Enter で閉じる */
const stale = c.active();
c.show(A);                                         /* 同じこまに札が来た */
const focus = c.active();
await c.run(600);
await c.key("Enter", "Enter");
console.log(JSON.stringify({ closed: c.$("overlay").hidden, stale: stale, focus: focus,
                             sent: choices(c).map(function (x) { return x.type; }) }));
""", A=a)
    assert out == {"closed": True, "stale": "close", "focus": "allow_once", "sent": ["allow_once"]}, out


def test_a_drag_into_a_blade_released_within_one_frame_is_not_pressed(tmp_path, clock):
    """押したまま (羽根の外で押し始めて) 羽根へ来て、同じこまの内に離した時も、入り直すまで滞留で押さない (外したら押された =
    離したその場の守りだけが、この筋を見張る)。押しが途中で取り消された時 (pointercancel) も同じ。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const end of ["pointerup", "pointercancel"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja&dwell=1" });
  c.doc().layout = function (e) { return e.dataset.key === "allow_once" ? { left: 0, top: 0, width: 100, height: 100, z: 1 } : null; };
  c.show(A);
  await c.run(800, function () { c.pointer(300, 300); });          /* 羽根の外 */
  c.pointer(300, 300, { type: "pointerdown", buttons: 1 });         /* 外で押し始める */
  await c.run(200, function () { c.pointer(300, 300, { buttons: 1 }); });
  c.pointer(50, 50, { buttons: 1 });                                /* 押したまま羽根へ */
  c.pointer(50, 50, { type: end, buttons: 0 });                     /* 同じこまの内に離す */
  await c.run(3000, function () { c.pointer(50, 50); });           /* 羽根の上で止まる */
  const resting = c.answers().length;
  await c.run(300, function () { c.pointer(300, 300); });
  await c.run(1300, function () { c.pointer(50, 50); });           /* 入り直す */
  out[end] = { resting: resting, reentered: c.answers().length };
}
console.log(JSON.stringify(out));
""", A=a)
    assert out == {"pointerup": {"resting": 0, "reentered": 1}, "pointercancel": {"resting": 0, "reentered": 1}}


def test_letting_go_of_a_window_drag_on_a_blade_does_not_press_it_by_dwell(tmp_path, clock):
    """扇の背景を掴んで運び (窓のドラッグ)、羽根の上で離しても、その羽根は入り直すまで滞留で押さない (最終デバッグ 1 巡目の
    追加の 1 件の再現 = 運んでいる間の pointer の知らせは窓を運ぶだけで、頁は pointer の下の釦を数えていない (押し始めの
    背景のまま)。離した時の守りが下の羽根に掛からず、次の 1 動き (捕まえが解けた後の羽根への pointerover・離した後の
    1 px の揺れ) から 0.3 秒で押された)。離した知らせは捕まえた背景へ届く (target は背景) = 位置から引き直す。羽根の縁の
    1 px 外で離し、揺れで 1 px 入った時も、離した後に最初に届いた pointer の下の羽根は守る。一度外へ出て入り直すと押せる。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const how of ["over", "move", "edge"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja&dwell=0.3" });
  const back = c.$("fan-scroll");
  const at = how === "edge" ? 199 : 250;                      /* edge = 羽根の 1 px 外 (背景) で離す */
  c.doc().layout = function (e) {
    if (e === back) return { left: 0, top: 0, width: 640, height: 330, z: 0 };
    if (e.dataset.key === "allow_once" && e.parentNode && e.parentNode.id === "fan") return { left: 200, top: 100, width: 100, height: 100, z: 1 };
    return null;
  };
  c.show(A);
  await c.run(600);
  c.pointer(50, 300);                                         /* 扇の背景 */
  await c.run(200);
  c.pointer(50, 300, { type: "pointerdown", buttons: 1 });    /* 掴む = 窓のドラッグ */
  await c.run(50);
  c.pointer(at, 150, { buttons: 1, target: back });           /* 運ぶ (知らせは捕まえた背景へ) */
  await c.run(50);
  c.pointer(at, 150, { type: "pointerup", target: back });    /* 羽根の上 (edge は 1 px 外) で離す */
  c.event("lostpointercapture", { target: back });
  out[how + "Drag"] = !!c.S.drag;
  if (how === "over") c.pointer(250, 150, { type: "pointerover" });   /* 捕まえが解けた後の、羽根への知らせ */
  else { await c.run(20); c.pointer(at + (how === "edge" ? 2 : 1), 150); }   /* 離した後の揺れ (edge は 1 px 羽根の中へ) */
  await c.run(1000);
  out[how] = c.answers().length;
  c.pointer(50, 300); await c.run(300);                       /* 一度外へ出て */
  c.pointer(250, 150); await c.run(500);                      /* 入り直すと押せる */
  out[how + "Again"] = choices(c);
}
console.log(JSON.stringify(out));
""", A=a)
    once = [{"type": "allow_once"}]
    assert out == {"overDrag": False, "over": 0, "overAgain": once, "moveDrag": False, "move": 0, "moveAgain": once,
                   "edgeDrag": False, "edge": 0, "edgeAgain": once}, out


def test_moving_to_pip_while_presses_settle_clears_the_mark_on_the_first_page(tmp_path, clock):
    """押しを数えない間の印 (body.settling) を付けた後、その間に PiP の窓へ移っても、間が終われば元の頁の印も消す
    (残ると、外の道具や試験が「まだ押せない」と読み続ける)。移った先の文書にも、その間は印が付く (外部のレビューの所見 =
    移った先には印が無いのに、押しは捨てていた)。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja", pip: true });
c.show(A);                                         /* 替わった = 数えない間の印が付く */
const marked = c.win.document.body.classList.contains("settling");
await c.key("Tab", "Tab");
c.$("pip-btn").focus();
await c.key("Enter", "Enter");                     /* 数えない間の内に PiP へ移る */
await c.run(20);
const inPip = c.vwin() !== c.win;
const pipMarked = c.doc().body.classList.contains("settling");   /* 移った先の文書にも印 */
await c.run(600);                                  /* 数えない間が終わる */
console.log(JSON.stringify({ marked: marked, inPip: inPip, pipMarked: pipMarked,
                             home: c.win.document.body.classList.contains("settling"),
                             pip: c.doc().body.classList.contains("settling") }));
""", A=a)
    assert out == {"marked": True, "inPip": True, "pipMarked": True, "home": False, "pip": False}, out


def test_a_window_reply_that_breaks_still_lets_the_next_shape_go(tmp_path):
    """窓の形の頼みの返りを扱う所が例外で終わっても (固定の釦がまだ無い頁など)、待ちの印を残さない = 次の形を送れる。"""
    out = node(tmp_path, r"""
const reqs = [];
const t = loadPage(function (path, opt) {
  reqs.push(JSON.parse(opt.body));
  return Promise.resolve({ status: 200, json: function () { return Promise.resolve({ found: true, ok: true, pin: false }); } });
});
const svg = { getBoundingClientRect: function () { return { left: 10, top: 10, width: 300 }; } };
let pipButton = null;                                  /* 最初の返りの時は固定の釦が無い = 返りの扱いが例外で終わる */
const els = { closed: { querySelector: function () { return svg; } } };
const w = t.window;
w.document = { getElementById: function (id) { return id === "pip-btn" ? pipButton : els[id] || null; } };
t.selectWindow(w);
t.S.mode = "small"; t.S.token = "x"; t.S.options = core.parseOptions("clear=on", {}); t.S.shapeSig = "null";
w.devicePixelRatio = 1.5; w.outerWidth = 320; w.outerHeight = 120; w.innerWidth = 306; w.innerHeight = 83;
t.pushShape();
setTimeout(function () {
  const busy = t.S.shapeBusy;
  pipButton = {};
  svg.getBoundingClientRect = function () { return { left: 20, top: 10, width: 300 }; };
  t.pushShape();                                       /* 次の形 */
  setTimeout(function () { console.log(JSON.stringify({ busy: busy, sent: reqs.length })); }, 20);
}, 20);
""")
    assert out == {"busy": False, "sent": 2}


def test_scan_mark_on_more_does_not_survive_a_card_change(tmp_path, clock):
    """長い札 A で走査の光が「▼ 続き」(常設の釦・走査の列の末尾) に来た瞬間に札 B が来る (A の時間切れ・端末や別の頁の
    答え) と、描き直しは光の印 (.scan) を外さずに手放していた = 「▼ 続き」は光ったまま残り、静かな間の後に本物の光が
    先頭 (許可) から回る (2 巡目の反証の再現 = 700 ms 後の .scan は ["more", "allow_once"])。「▼ 続き」を待っていた人の
    1 押しは本物の光 = 許可に当たる。描き直しは印を外してから手放す = 静かな間は光が無く、その後は allow_once だけ。"""
    a = _card(clock)
    b = _card(clock)
    out = page(tmp_path, r"""
function lit(c) { return c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; }); }
const c = await P.boot({ query: "?mode=small&lang=ja&scan=0.5" });
c.$("copy").scrollHeight = 900; c.$("copy").clientHeight = 180;   /* 長い本文 = 「▼ 続き」が走査の列の末尾に入る */
c.show(A);
await c.run(600);
let waited = 0;
while (waited < 10000 && c.S.scanEl !== c.$("more")) { await c.run(16); waited += 16; }
const r = { ids: A.id !== B.id, onMore: c.S.scanEl === c.$("more"), before: lit(c) };
c.show(B);                                           /* 光が「▼ 続き」に居る瞬間に、別の長い札 */
r.moreShown = !c.$("more").hidden;
await c.run(100);
r.at100 = lit(c);                                    /* 静かな間 (0.5 秒) の内 */
await c.run(600);
r.at700 = lit(c);
let most = r.at700.length;
for (let t = 700; t < 3000; t += 16) { await c.run(16); most = Math.max(most, lit(c).length); }
r.most = most;                                       /* 走査が列を 1 周する間に、同時に点いた光の数 */
console.log(JSON.stringify(r));
""", A=a, B=b)
    assert out["ids"] and out["onMore"] and out["before"] == ["more"] and out["moreShown"], out
    assert out["at100"] == [] and out["at700"] == ["allow_once"], out
    assert out["most"] == 1, out


def test_undo_fill_does_not_carry_to_the_next_grace(tmp_path, clock):
    """取り消しを途中まで見つめた (1 秒の滞留の半分) まま猶予が終わり次の札へ替わると、「取り消す」(常設の釦) の縁の満ち
    (--p) が残り、次の猶予の「取り消す」が最初から半分満ちて見えた (2 巡目の反証の再現 = 0.48 のまま)。描き直しは縁を 0 へ
    戻してから手放す (大きな板・扇の両方)。"""
    a = _card(clock)
    b = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const mode of ["large", "small"]) {
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja&dwell=1" });
  c.doc().layout = function (e) {
    if (e.id === "undo-btn") return { left: 0, top: 0, width: 600, height: 120, z: 31 };
    if (e.id === "undo-zone") return { left: 0, top: 0, width: 600, height: 120, z: 30 };
    return null;
  };
  const away = function () { c.pointer(400, 400); };
  const onUndo = function () { c.pointer(50, 50); };
  c.show(A);
  await c.run(600, away);
  await c.key("1", "Digit1");                        /* 許可 (今回) を送る */
  c.show(deciding(A));                               /* 猶予の内 = 取り消しが出る */
  await c.run(600, away);
  await c.run(500, onUndo);                          /* 取り消しを 0.5 秒見つめる (1 秒の滞留の半分) */
  const r = { pMid: c.$("undo-btn").style["--p"] };
  c.show(B, ended(A, c.me()));                       /* 猶予が終わり、次の札 B */
  await c.run(600, away);
  r.pHidden = c.$("undo-btn").style["--p"];
  await c.key("1", "Digit1");                        /* B に答える */
  c.show(deciding(B));                               /* 次の猶予 */
  await c.run(20, away);
  r.pNext = c.$("undo-btn").style["--p"];
  r.zoneShown = !c.$("undo-zone").hidden;
  r.sent = choices(c).map(function (x) { return x.type; });
  out[mode] = r;
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    for mode in ("large", "small"):
        r = out[mode]
        assert 0.3 < float(r["pMid"]) < 1, out                  # 前提 = 取り消しの縁が途中まで満ちた (押してはいない)
        assert r["pHidden"] == "0" and r["pNext"] == "0", out
        assert r["zoneShown"] and r["sent"] == ["allow_once", "allow_once"], out


def test_undo_scan_mark_does_not_survive_a_screen_change(tmp_path, clock):
    """猶予の内に走査の光が「取り消す」(常設の釦) に点いた後、別の頁が取り消して選ぶ画面へ戻ると、隠れた「取り消す」に光の
    印が残り、次の猶予では押せる (0.4 秒) より前から光って見えた (2 巡目の反証の再現 = 戻った画面の .scan は
    ["allow_once", "undo"]・次の猶予の 20 ms 後に光る)。押しは間で落ちるので安全側だが、表示と状態が食い違う。
    描き直しは印を外してから手放す。"""
    a = _card(clock)
    out = page(tmp_path, r"""
const c = await P.boot({ query: "?mode=small&lang=ja&scan=0.5" });
c.show(A);
await c.run(600);
await c.key("1", "Digit1");                          /* 許可 (今回) を送る */
c.show(deciding(A));
let w = 0;
while (w < 3000 && !c.$("undo-btn").classList.contains("scan")) { await c.run(8); w += 8; }
const r = { undoLit: c.$("undo-btn").classList.contains("scan") };
c.show(reshown(A));                                  /* 別の頁が取り消した = 選ぶ画面へ戻る */
await c.run(600);
r.shownLit = c.doc().querySelectorAll(".scan").map(function (b) { return b.dataset.key; });
r.undoMarkWhileHidden = c.$("undo-btn").classList.contains("scan");
await c.key("1", "Digit1");                          /* もう一度答える */
c.show(deciding(Object.assign({}, A, { view_seq: A.view_seq + 1 })));
await c.run(20);
r.undoLitAt20 = c.$("undo-btn").classList.contains("scan");   /* 押せる (0.4 秒) より前に光って見えるか */
await c.key(" ", "Space");                           /* その間のスイッチ = 取り消しにならない (安全側) */
r.posts = c.posts();
console.log(JSON.stringify(r));
""", A=a)
    assert out["undoLit"], out                                     # 前提 = 光が「取り消す」に来た
    assert out["shownLit"] == ["allow_once"] and out["undoMarkWhileHidden"] is False, out
    assert out["undoLitAt20"] is False and out["posts"] == ["/answer", "/answer"], out


def test_scroll_position_resets_for_a_new_card_but_not_for_undo(tmp_path, clock):
    """長い札 A を末尾まで読んだ後に画面が替わる (次の札・札なしを挟んだ次の札・2 問の札の次の設問) と、送りの枠は A の送り
    位置のまま描かれ、替わった札の頭 (何の確認か) が隠れたまま羽根が押せた・「▲ 先頭へ」が出たまま (2 巡目の反証)。
    画面が替わった時だけ頭へ戻す = 小型の和紙 (#copy)・大きな板の札の枠 (#card)。答えた (猶予)・取り消して同じ画面へ戻った・
    印を付けただけの描き直しは、読んでいた位置を保つ。"""
    a = _card(clock)
    b = _card(clock)
    multi = _card(clock, "question", MULTI_SELECT)
    q = _card(clock, "question", TWO_QUESTIONS)
    out = page(tmp_path, r"""
async function long(mode, box) {                     /* 長い本文の頁 (送りの枠 = box・末尾 = 720) */
  const c = await P.boot({ query: "?mode=" + mode + "&lang=ja" });
  c.$(box).scrollHeight = 900; c.$(box).clientHeight = 180;
  return c;
}
const out = {};
let c = await long("small", "copy");
c.show(A); await c.run(500);
c.$("copy").scrollTop = 720;                         /* A を末尾まで読んだ */
await c.key("1", "Digit1");                          /* 許可 (今回) = 猶予 (同じ画面の描き直し) */
c.show(deciding(A)); await c.run(100);
out.deciding = c.$("copy").scrollTop;
c.show(reshown(A)); await c.run(500);                /* 取り消した = 同じ画面へ戻る */
out.undone = c.$("copy").scrollTop;
c.show(B); await c.run(100);                         /* 次の札 */
out.next = { top: c.$("copy").scrollTop, more: c.$("more").textContent };
c = await long("small", "copy");
c.show(A); await c.run(500);
c.$("copy").scrollTop = 720;
c.show(null); await c.run(100);                      /* 札なし (空きを挟む) */
c.show(B); await c.run(100);
out.afterIdle = c.$("copy").scrollTop;
c = await long("small", "copy");
c.show(MULTI); await c.run(500);
c.$("copy").scrollTop = 720;
await c.key("1", "Digit1");                          /* 印を付けるだけ = 同じ画面の描き直し */
out.marked = { top: c.$("copy").scrollTop, pressed: c.btn("opt:0").getAttribute("aria-pressed") };
c = await long("small", "copy");
c.show(Q); await c.run(500);
c.$("copy").scrollTop = 720;
await c.key("1", "Digit1");                          /* 1 問目に答えた = 次の設問 */
out.nextQuestion = { top: c.$("copy").scrollTop, question: c.$("question").textContent.indexOf("次の問い") >= 0 };
c = await long("large", "card");
c.show(A); await c.run(500);
c.$("card").scrollTop = 720;
c.show(B); await c.run(100);
out.large = c.$("card").scrollTop;
console.log(JSON.stringify(out));
""", A=a, B=b, MULTI=multi, Q=q)
    assert out["deciding"] == 720 and out["undone"] == 720 and out["marked"] == {"top": 720, "pressed": "true"}, out
    assert out["next"] == {"top": 0, "more": "▼ 続き (↓)"}, out
    assert out["afterIdle"] == 0 and out["large"] == 0, out
    assert out["nextQuestion"] == {"top": 0, "question": True}, out


def test_answer_409_other_than_stale_does_not_say_choose_again(tmp_path, clock):
    """/answer の 409 を全部「画面が古くなっていました。もう一度選んでください」で出していた = 期限と同時の押し (expired)・
    終わった札 (ended)・頭に居ない札 (not_current)・ほかの頁が先に答えた札 (not_shown) でも「選び直せ」と出て、終わりの文
    (時間切れ) を 5 秒隠し、次の札の上にも重なった (2 巡目 i21)。選び直せば通る時 (stale) だけ今の文を出し、ほかは黙って
    写しを取り直す (取り直した表示と終わりの文に任せる・取り消しの 409 と同じ形)。"""
    a = _card(clock)
    b = _card(clock)
    out = page(tmp_path, r"""
const out = {};
for (const error of ["expired", "ended", "not_current", "not_shown", "stale"]) {
  const c = await P.boot({ query: "?mode=small&lang=ja", reply: function (p) {
    return p === "/answer" ? { status: 409, data: { error: error } } : null; } });
  c.show(A); await c.run(500);
  await c.key("1", "Digit1");                        /* 許可 (今回) = 板が 409 で断る */
  const r = { sent: c.answers().length, kicked: c.S.seq === -1 };
  c.show(null, { last: { id: A.id, kind: "permission", end: "expired", from_deciding: false, ago: 0, answered_by: null } });
  await c.run(100);
  r.idle = c.$("status").textContent;                /* 札が終わった後の行 */
  c.show(B); await c.run(100);
  r.next = c.$("status").textContent;                /* 次の札の上の行 */
  out[error] = r;
}
console.log(JSON.stringify(out));
""", A=a, B=b)
    for error in ("expired", "ended", "not_current", "not_shown"):
        assert out[error] == {"sent": 1, "kicked": True, "idle": "時間切れ。端末で答えてください", "next": ""}, out
    assert out["stale"]["sent"] == 1 and out["stale"]["kicked"] is True, out
    assert out["stale"]["idle"] == "画面が古くなっていました。もう一度選んでください", out
