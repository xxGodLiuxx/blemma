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
  src = src.replace(re, "\n  window.__t = { S: S, press: press, releaseDwell: releaseDwell, bindInputs: bindInputs, inputActive: inputActive, selectWindow: function(w) { viewWindow=w; viewDocument=w.document; } };$1");
  const win = { BlemmaCore: core, crypto: require("crypto").webcrypto };
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
    assert out == {"ja": ["一", "二", "六"], "fixed": ["止", "端"], "en": ["1", "Esc", "0"]}


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
