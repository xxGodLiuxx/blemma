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
  src = src.replace(re, "\n  window.__t = { S: S, press: press, releaseDwell: releaseDwell, bindInputs: bindInputs, inputActive: inputActive, selectWindow: function(w) { viewWindow=w; viewDocument=w.document; }, onClick: onClick, disarm: disarm, fitFan: fitFan, windowCall: windowCall, poll: poll, goneSince: goneSince, bumpGen: bumpGen, onPointer: onPointer, letGo: letGo, pushShape: pushShape, window: window, frame: frame, forgetSends: forgetSends, startDrag: startDrag, endDrag: endDrag, fitWindow: fitWindow, windowMoved: windowMoved, onKeyDown: onKeyDown, togglePin: togglePin };$1");
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


def test_quiet_moment_is_only_for_changes_from_the_board(tmp_path):
    """板から来た替わり (新しい札・取り消しで戻った) の時だけ、押しを数えない間と、走査の静かな 1 こまを置く。
    札の中で人が画面を進めた時 (拒否 → 理由) は置かない = 続けて打つ 2 打目を捨てない。"""
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
    """取り消しが間に合わなかった (409) 時は、黙って答えを渡さずに知らせる。"""
    _, card = _board(clock)
    out = node(tmp_path, (PAGE_SETUP + r"""
const t = loadPage(function (path, opt) {
  sent.push(path);
  return Promise.resolve(reply(409, { error: "too_late" }));
});
show(t);
t.S.lang = "ja";
t.S.card = Object.assign({}, card, { state: "deciding" });
t.S.undoAt = performance.now() + 3000;
t.press("undo", "key");
setTimeout(function () { console.log(JSON.stringify({ sent: sent, notice: t.S.notice || "" })); }, 30);
""").replace("__CARD__", json.dumps(card)))
    assert out == {"sent": ["/undo"], "notice": "取り消しは間に合いませんでした (答えは渡りました)"}


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
function item() { return { classList: { add: function () {}, remove: function () {} }, scrollIntoView: function () { brought += 1; } }; }
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
    離した後も、羽根へ入り直すまで数えない。押していなければ、今までどおり 1 秒で押す。"""
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
t.S.over = null; frames(3016, 3048);                   /* 一度外へ出る */
t.S.over = "allow_once";
counts.reentered = frames(3064, 4200);                 /* 入り直して 1 秒 = 押す */
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
