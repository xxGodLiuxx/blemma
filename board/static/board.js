/* BLEMMA の板の頁 = DOM と通信。純粋な計算は board_core.js (window.BlemmaCore)。設計 = docs/design.md §4。
 * 入力の 5 通り = 視線 (滞留)・キー・スイッチ 1 鍵の走査・携帯 (触る)・マウス (click)。
 * 札の本文は textContent だけで描く (innerHTML を使わない)。 */
(function () {
  "use strict";
  var homeDocument = document, viewDocument = document, viewWindow = window;
  var rafWindow = window, rafId = null;
  var C = window.BlemmaCore;
  var $ = function (id) { return viewDocument.getElementById(id); };
  var reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var S = {
    token: "", lang: "ja", dwellMs: 1000, scanMs: 0, switchKey: "Space", sound: false,
    mode: "large", desc: true, fan: false, fanVisual: [], firstPointer: true,
    seq: -1, snap: null, snapAt: 0, card: null, ui: C.newUi(null), key: "", gen: 0,
    btns: {}, optionKeys: [], scanList: [], scanEl: null, fillEl: null,
    delta: C.zeroPresses(), answering: false, undoing: false, sentKey: null,
    pressLedger: C.newPressLedger(window.crypto.getRandomValues(new Uint32Array(4)).join("-")),
    lastX: -1, lastY: -1, over: null, pointerType: "mouse", lastInput: "",
    held: {}, deadlineAt: null, undoAt: null,
    lightUntil: 0, lightKey: "", lastSeen: "", endText: "", endUntil: 0,
    notice: "", noticeUntil: 0, problem: "", offline: false,
    abort: null, kicked: false, retry: 0, stopped: false, overlay: null, sideAt: 0, ac: null
  };

  function L() { return C.I18N[S.lang]; }

  function savedOptions() {
    try { return JSON.parse(window.localStorage.getItem("blemma.options") || "{}"); }
    catch (e) { return {}; }
  }

  function readSettings() {
    var o = C.parseOptions(location.search, savedOptions());
    S.options = o;
    S.lang = C.pickLang(o.lang, navigator.language);
    S.dwellMs = C.parseDwell(o.dwell);
    S.scanMs = C.parseScan(o.scan);
    S.switchKey = o.key;
    S.sound = o.sound === "on";
    S.mode = o.mode;
    S.desc = o.desc === "on";
    S.dwell = new C.Dwell(S.dwellMs, 150);
    S.scan = new C.Scan(S.scanMs);
  }

  function readToken() {
    var h = location.hash.replace(/^#/, "");
    S.token = new URLSearchParams(h).get("t") || "";
  }

  /* ---- 通信 ---- */
  function api(method, path, body, signal) {
    var headers = { "X-Blemma-Token": S.token };
    var opt = { method: method, headers: headers, cache: "no-store", credentials: "omit", signal: signal };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    return fetch(path, opt).then(function (r) {
      if (r.status === 204) return { status: r.status, data: null };
      return r.json().then(function (d) { return { status: r.status, data: d }; },
                           function () { return { status: r.status, data: null }; });
    });
  }

  function poll() {
    if (S.stopped) return;
    if (!S.token) { S.problem = L().no_token; S.stopped = true; return; }
    var ctl = new AbortController();
    S.abort = ctl;
    var timer = setTimeout(function () { ctl.abort(); }, 40000);
    api("GET", "/pending?seq=" + S.seq, undefined, ctl.signal).then(function (r) {
      clearTimeout(timer);
      if (r.status === 401) { S.stopped = true; S.problem = L().bad_token; return; }
      if (r.status !== 200 || !r.data) throw new Error("status " + r.status);
      S.retry = 0;
      S.offline = false;
      apply(r.data);
      poll();                         /* 直に呼ぶ = 隠れた頁で timer が間引かれても見る人の数が途切れない */
    }).catch(function () {
      clearTimeout(timer);
      if (S.kicked) { S.kicked = false; poll(); return; }
      S.offline = true;
      S.retry = S.retry ? Math.min(5000, S.retry * 2) : 1000;
      setTimeout(poll, S.retry);
    });
  }

  /* 今の long-poll を捨てて、すぐ新しい写しを取る */
  function kick() {
    S.seq = -1;
    if (S.abort) { S.kicked = true; S.abort.abort(); }
  }

  /* ---- 受けた写しを当てる ---- */
  function apply(snap) {
    var now = performance.now();
    var prev = S.card;
    var card = snap.card;
    S.seq = snap.seq;
    S.snap = snap;
    S.snapAt = now;
    if (!card) {
      S.ui = C.newUi(null);
    } else if (card.id !== S.ui.cardId) {
      S.ui = C.newUi(card.id);
      S.delta = C.zeroPresses();
      S.pressLedger = C.newPressLedger(S.pressLedger.source);
    } else if (prev && prev.id === card.id && prev.state === "deciding" && card.state === "shown") {
      S.ui = C.uiAfterUndo(card, S.ui);          /* 取り消した = 確かめの画面か頭へ */
    }
    S.card = card;
    S.deadlineAt = card && typeof card.remaining === "number" ? now + card.remaining * 1000 : null;
    S.undoAt = card && card.state === "deciding" ? now + (card.undo_remaining || 0) * 1000 : null;
    var last = snap.last;
    if (last && S.lastSeen !== last.id + "|" + last.end) {
      S.lastSeen = last.id + "|" + last.end;
      if (last.ago < 10) {
        S.endText = C.endText(last, S.lang);
        S.endUntil = now + (10 - last.ago) * 1000;
      }
    }
    var light = snap.light;
    if (light) {
      var lk = [light.type, light.title, light.message].join("|");
      var fresh = S.lightKey !== lk || now >= S.lightUntil;
      S.lightUntil = now + (light.remaining || 0) * 1000;
      if (fresh) { S.lightKey = lk; onNewLight(); }
    } else {
      S.lightUntil = 0;
      S.lightKey = "";
    }
    refreshView();
  }

  function refreshView() {
    var k = C.viewKey(S.card, S.ui, S.lang);
    if (k !== S.key) {
      S.ui.marks = [];
      S.key = k;
      render();
      bumpGen();
    }
    updateSide(performance.now());
  }

  /* ---- 描く ---- */
  function el(tag, cls, text) {
    var e = viewDocument.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function makeButton(key, label, desc, cls) {
    var b = el("button", "btn" + (cls ? " " + cls : ""));
    b.type = "button";
    b.dataset.key = key;
    b.dataset.dwell = "1";
    b.dataset.label = label;
    b.dataset.description = key === "fixed" ? C.actionDescription(S.card, key, S.lang) : desc || C.actionDescription(S.card, key, S.lang);
    b.appendChild(el("span", "fill"));
    b.appendChild(el("span", "label", label));
    if (desc && S.desc) b.appendChild(el("span", "desc", desc));
    return b;
  }

  function fromText(f) {
    if (!f) return "";
    return [f.cwd, f.session, f.agent].filter(function (x) { return !!x; }).join(" · ");
  }

  /* 本文の 1 節。Edit の変わった所には印を付ける (色だけに頼らない = 消す所は打ち消し線・足す所は下線) */
  function blockEl(b) {
    var sec = el("section", b.change ? "change" : "");
    if (b.label) sec.appendChild(el("div", "label", b.label));
    var body = el(b.mono ? "pre" : "div", b.mono ? "" : "plain");
    if (b.mark && b.mark[1] > b.mark[0]) {
      body.appendChild(viewDocument.createTextNode(b.text.slice(0, b.mark[0])));
      body.appendChild(el("mark", b.markKind, b.text.slice(b.mark[0], b.mark[1])));
      body.appendChild(viewDocument.createTextNode(b.text.slice(b.mark[1])));
    } else {
      body.textContent = b.text;
    }
    sec.appendChild(body);
    return sec;
  }

  function render() {
    var lang = S.lang;
    var T = L();
    var card = S.card;
    var focusedKey = viewDocument.activeElement && viewDocument.activeElement.dataset
      ? viewDocument.activeElement.dataset.key : null;
    viewDocument.documentElement.lang = lang;
    $("kind").textContent = card ? T["kind_" + card.kind] : "";
    if (S.mode === "small" && card && card.kind === "elicitation" && card.payload.head === "blemma") {
      $("kind").textContent = lang === "ja" ? "次の一手 (Claude の先回り)" : "Next step (Claude's suggestion)";
    }
    $("from").textContent = card ? fromText(card.from) : "";
    if (S.mode === "small") $("copy").insertBefore($("from"), $("head"));
    else $("remain").parentNode.insertBefore($("from"), $("remain"));
    var m = card ? C.buildScreen(card, S.ui, lang) : null;
    S.fan = S.mode === "small" && C.fanEligible(card, S.ui, m);
    viewDocument.body.classList.toggle("small", S.mode === "small");
    viewDocument.body.classList.toggle("has-fan", S.fan);
    viewDocument.body.classList.toggle("idle", !card);
    $("head").textContent = m ? m.head : "";
    $("text").textContent = m ? m.text : S.mode === "small" ? T.idle_line : T.empty;
    var blocks = $("blocks");
    blocks.replaceChildren();
    (m ? m.blocks : []).forEach(function (b) { blocks.appendChild(blockEl(b)); });
    $("question").textContent = m && m.question ? m.question : "";
    var sum = $("summary");
    sum.replaceChildren();
    ((m && m.summary) || []).forEach(function (s) { sum.appendChild(el("li", "", s)); });

    var enabled = !!card && card.state === "shown";
    var opts = $("opts");
    opts.replaceChildren();
    S.btns = {};
    S.optionKeys = [];
    (m ? m.options : []).forEach(function (o, i) {
      var b = makeButton(o.key, o.label, o.desc, o.aux ? "aux" : "");
      if (i < 6) b.appendChild(el("span", "num", String(i + 1)));
      if (o.marked !== null && o.marked !== undefined) b.setAttribute("aria-pressed", o.marked ? "true" : "false");
      if (o.def) b.appendChild(el("span", "def", T.default_mark));
      b.disabled = !enabled || !!o.disabled;
      opts.appendChild(b);
      S.btns[o.key] = b;
      S.optionKeys.push(o.key);
    });
    var fz = $("fixed-zone");
    var tz = $("term-zone");
    fz.replaceChildren();
    tz.replaceChildren();
    if (card) {
      var fb = makeButton("fixed", m.fixedLabel, "Esc", "fixed");
      fb.disabled = !enabled;
      fz.appendChild(fb);
      S.btns.fixed = fb;
      var tb = makeButton("terminal", T.terminal, T.terminal_sub, "term");
      tb.disabled = !enabled;
      tz.appendChild(tb);
      S.btns.terminal = tb;
    }
    S.scanList = Array.prototype.filter.call(
      viewDocument.querySelectorAll("#opts .btn, #fixed-zone .btn, #term-zone .btn"),
      function (b) { return !b.disabled; });
    renderFan(m);
    S.scanEl = null;
    S.fillEl = null;
    if (focusedKey && S.btns[focusedKey] && !S.btns[focusedKey].disabled) {
      S.btns[focusedKey].focus({ preventScroll: true });
    }
  }

  /* 見つめた羽根の全文 = 押せない書の帯に出す。目を移しても消さない (読むために羽根を離れるので)。
   * 入らない長さの時だけ上にも全文。何も見ていない時は選択肢の静かな一覧 */
  function spotlight(b) {
    if (S.mode !== "small" || !S.fan || (S.card && S.card.state === "deciding")) return;
    var on = !!(b && b.dataset && b.dataset.label);
    S.spotKey = on ? b.dataset.key : null;
    S.spotBtn = on ? b : null;
    var fit = C.fanScript(on ? b.dataset.label : "", S.fanArcs || [1, 1]);
    var clipped = fit.clipped;
    [0, 1].forEach(function (i) {
      var t = $("fan-script-" + i);
      if (!t) return;
      t.style.fontSize = fit.size + "px";
      setText(t.firstChild, fit.lines[i]);
      /* 字の幅は字体ごとに違う = 実際の長さが弧を越えたら、上の欄に全文を残す */
      if (t.getComputedTextLength && t.getComputedTextLength() > S.fanArcs[i]) clipped = true;
    });
    var desc = on && S.desc ? b.dataset.description || "" : "";
    $("spot-list").hidden = on && (clipped || !!desc);
    $("spot-label").hidden = !(on && clipped);
    $("spot-desc").hidden = !desc;
    setText($("spot-label"), on ? b.dataset.label : "");
    setText($("spot-desc"), desc);
  }

  var SVG_NS = "http://www.w3.org/2000/svg";

  /* 扇の骨 = 竹の骨・折り目・地紙の縁・要。押す物ではない (pointer-events: none) */
  function fanBones(layout) {
    var svg = viewDocument.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + layout.width + " " + layout.height);
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("fan-bones");
    function line(from, to, cls) {
      var l = viewDocument.createElementNS(SVG_NS, "line");
      l.setAttribute("x1", from[0]); l.setAttribute("y1", from[1]);
      l.setAttribute("x2", to[0]); l.setAttribute("y2", to[1]);
      l.setAttribute("class", cls);
      svg.appendChild(l);
    }
    layout.folds.forEach(function (f) { line(f.from, f.to, "fold"); });
    layout.ribs.forEach(function (r) { line(r.from, r.to, r.main ? "rib main" : "rib"); });
    layout.edges.concat([layout.seam]).forEach(function (d, i) {
      var p = viewDocument.createElementNS(SVG_NS, "path");
      p.setAttribute("d", d);
      p.setAttribute("class", i < layout.edges.length ? "edge" : "seam");
      svg.appendChild(p);
    });
    layout.arcs.forEach(function (d, i) {
      var arc = viewDocument.createElementNS(SVG_NS, "path");
      arc.setAttribute("id", "fan-arc-" + i);
      arc.setAttribute("d", d);
      arc.setAttribute("fill", "none");
      svg.appendChild(arc);
      var t = viewDocument.createElementNS(SVG_NS, "text");
      t.setAttribute("id", "fan-script-" + i);
      t.setAttribute("class", "fan-script");
      var tp = viewDocument.createElementNS(SVG_NS, "textPath");
      tp.setAttribute("href", "#fan-arc-" + i);
      tp.setAttribute("startOffset", "50%");
      tp.setAttribute("text-anchor", "middle");
      t.appendChild(tp);
      svg.appendChild(t);
    });
    var c = viewDocument.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", layout.cx); c.setAttribute("cy", layout.cy); c.setAttribute("r", 9);
    c.setAttribute("class", "pivot");
    svg.appendChild(c);
    return svg;
  }

  function renderFan(m) {
    var fan = $("fan"), clock = $("fan-time"), undoZone = $("undo-zone");
    if (undoZone.parentNode !== $("surface")) $("surface").appendChild(undoZone);
    $("undo-btn").style.clipPath = "";
    fan.replaceChildren(clock);
    $("fan-scroll").hidden = !S.fan;
    $("spotlight").hidden = !S.fan;
    if (!S.fan) return;
    var blades = m.options.filter(function (o) { return !o.aux; });
    var layout = C.fanLayout(blades.length);
    function buttonOf(p) { return S.btns[p.key === "option" ? blades[p.index].key : p.key]; }
    fan.style.width = layout.width + "px";
    fan.style.height = layout.height + "px";
    fan.style.setProperty("--cx", layout.cx + "px");
    fan.style.setProperty("--cy", layout.cy + "px");
    fan.style.setProperty("--a0", layout.first + "deg");
    fan.style.setProperty("--fold", layout.step + "deg");
    S.fanArcs = layout.arcLengths;
    var paper = el("div", "fan-paper");
    paper.style.clipPath = layout.paper;
    fan.appendChild(paper);
    S.scanList = [];
    layout.parts.forEach(function (p) {
      var b = buttonOf(p);
      b.style.clipPath = p.polygon;
      b.style.setProperty("--lx", p.label[0] + "px");
      b.style.setProperty("--ly", p.label[1] + "px");
      b.style.setProperty("--rot", p.angle + "deg");
      b.style.setProperty("--a0", p.start + "deg");
      b.style.setProperty("--full", layout.step + "deg");
      b.setAttribute("aria-label", b.dataset.label);
      b.title = b.dataset.label;
      b.appendChild(el("span", "fan-text", C.fanMark(p.index, p.key, S.lang)));
      var svg = viewDocument.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 " + layout.width + " " + layout.height);
      svg.setAttribute("aria-hidden", "true");
      svg.classList.add("dwell-arc");
      var path = viewDocument.createElementNS(SVG_NS, "path");
      path.setAttribute("d", p.arc);
      path.setAttribute("pathLength", "1");
      svg.appendChild(path);
      b.appendChild(svg);
      fan.appendChild(b);
      if (!b.disabled) S.scanList.push(b);
    });
    S.fanVisual = layout.visual.map(buttonOf).filter(function (b) { return !b.disabled; });
    /* 取り消しは内の帯そのもの = 押した羽根の上ではなく、見つめて戻せる大きな的 */
    $("undo-btn").style.clipPath = layout.scriptBand;
    fan.appendChild(undoZone);
    fan.appendChild(fanBones(layout));
    fan.appendChild(el("span", "fan-seal", "扇"));
    var aux = m.options.filter(function (o) { return o.aux; });
    if (aux.length) {
      var box = el("div", "fan-aux");
      aux.forEach(function (o) {
        var b = S.btns[o.key];
        box.appendChild(b);
        if (!b.disabled) { S.scanList.push(b); S.fanVisual.push(b); }
      });
      fan.appendChild(box);
    }
    var list = $("spot-list");
    list.replaceChildren();
    layout.visual.forEach(function (p) {
      var item = el("span", "item");
      item.appendChild(el("b", "", C.fanMark(p.index, p.key, S.lang)));
      item.appendChild(viewDocument.createTextNode(" " + buttonOf(p).dataset.label));
      list.appendChild(item);
    });
    spotlight(null);
    fitFan();
    if (viewDocument.fonts && viewDocument.fonts.ready) {       /* 字体の読み込みの後に幅を測り直す */
      viewDocument.fonts.ready.then(function () { if (S.fan) spotlight(S.spotBtn); });
    }
    if (S.fanCard !== S.card.id) {                  /* 新しい札で扇を開く動き (CSS・動きを止める設定では動かない) */
      S.fanCard = S.card.id;
      fan.classList.remove("open-anim");
      void fan.offsetWidth;
      fan.classList.add("open-anim");
      fan.addEventListener("animationend", function done() {
        fan.classList.remove("open-anim");
        fan.removeEventListener("animationend", done);
      });
    }
  }

  /* 窓が扇より小さい時は、見切れないよう扇を窓に合わせて縮める (大きい窓では 1 倍のまま) */
  function fitFan() {
    if (!S.fan) return;
    var fan = $("fan"), box = $("fan-scroll");
    var w = parseFloat(fan.style.width), h = parseFloat(fan.style.height);
    var wide = viewWindow.innerWidth / viewWindow.innerHeight >= 1.5;   /* 横向き = 左に問い・右に扇 */
    var roomW = viewDocument.documentElement.clientWidth - (wide ? 300 : 20);
    var roomH = viewWindow.innerHeight - (wide ? 20 : 250);             /* 縦向きは上の札と全文の欄の分を残す */
    var k = Math.max(0.45, Math.min(1, roomW / w, roomH / h));
    fan.style.transform = k < 1 ? "scale(" + k.toFixed(4) + ")" : "";
    box.style.height = Math.ceil(h * k) + "px";
    box.style.width = wide ? Math.ceil(w * k) + "px" : "";
    viewDocument.documentElement.style.setProperty("--fan-w", Math.ceil(w * k) + "px");
  }

  /* 滞留を解く = 時計を止め、pointer の下の釦は一度外へ出て入り直すまで数えない (§4.2 の ①②)。
   * 世代が進んだ時・頁が隠れた時と見えた時・焦点を失った時 (戻った瞬間に古い滞留で押さない)。 */
  function releaseDwell() {
    S.dwell.reset();
    S.dwell.block(S.over);
    setFill(null, 0);
  }

  /* 表示の世代を進める = 滞留を止めて選択を解き、pointer の下の釦は入り直すまで数えない・走査は頭から (§4.2) */
  function bumpGen() {
    S.gen += 1;
    S.over = keyAtPointer();
    if (S.lastX < 0) S.firstPointer = true;
    releaseDwell();
    S.scan.restart(performance.now());
    if (S.scanEl) { S.scanEl.classList.remove("scan"); S.scanEl = null; }
    if (S.card && S.card.state === "shown" && S.lastInput === "key" && !S.overlay && S.scanMs <= 0) {
      var first = S.fan ? S.scanList[0] : viewDocument.querySelector("#opts .btn:not(:disabled)");
      if (first) first.focus({ preventScroll: true });
    }
  }

  function dwellKeyOf(target) {
    var b = target && target.closest ? target.closest("[data-dwell]") : null;
    if (!b || b.disabled || b.hidden) return null;
    return b.dataset.key || null;
  }

  function keyAtPointer() {
    if (S.lastX < 0) return null;
    return dwellKeyOf(viewDocument.elementFromPoint(S.lastX, S.lastY));
  }

  function findBtn(key) {
    if (key === "close" || key === "sheet-next") return $(key === "close" ? "panel-close" : "panel-next");
    if (key === "sheet") return $("more");
    if (key === "undo") {
      var u = $("undo-btn");
      return u.hidden || u.disabled ? null : u;
    }
    return S.btns[key] || null;
  }

  function setFill(key, p) {
    var b = key ? findBtn(key) : null;
    if (S.fillEl && S.fillEl !== b) S.fillEl.style.setProperty("--p", "0");
    S.fillEl = b;
    if (b) {
      var v = reduced ? Math.floor(p * 4) / 4 : p;
      b.style.setProperty("--p", String(Math.max(0, Math.min(1, v))));
    }
  }

  function setText(e, t) {
    if (e.textContent !== t) e.textContent = t;
  }

  function updateSide(now) {
    var T = L();
    var card = S.card;
    var state = C.priorityState(S.snap && S.snap.states, card), badge = $("work-state");
    badge.hidden = S.mode !== "small";
    var labels = S.lang === "ja" ? { working: "◐ 作業中", "waiting on you": "◆ あなたの番", done: "✓ 完了" } :
      { working: "◐ working", "waiting on you": "◆ waiting on you", done: "✓ done" };
    var label = state ? labels[state.state] : (S.lang === "ja" ? "○ 待機中" : "○ ready");
    if (state && state.reason === "disconnected") label = S.lang === "ja" ? "■ 止まった・端末を見てください" : "■ stopped · check the terminal";
    setText(badge, label);
    badge.classList.toggle("stale", !!state && (state.stale || state.state === "working" && state.ago + (now - S.snapAt) / 1000 >= 600));
    badge.dataset.state = state ? state.state : "idle";
    var rem = $("remain");
    if (card && card.state === "shown" && S.deadlineAt !== null) {
      var sec = Math.max(0, (S.deadlineAt - now) / 1000);
      setText(rem, C.fmt(T.remain, { t: C.mmss(Math.ceil(sec)) }));
      setText($("fan-time"), C.mmss(Math.ceil(sec)));
      rem.classList.toggle("low", sec < 60);
    } else {
      setText(rem, "");
      rem.classList.remove("low");
      setText($("fan-time"), "");
    }
    if (S.sheet) updateSheet();
    updateMore();
    var qn = S.snap ? S.snap.queue : 0;
    setText($("queue"), qn > 0 ? C.fmt(T.queue, { n: qn }) : "");
    if (S.snap && S.snap.stats) {
      setText($("stats"), C.statsText(S.snap.stats, S.lang, S.snap.stats.elapsed + (now - S.snapAt) / 1000));
    }
    var st = "";
    if (S.problem) st = S.problem;
    else if (S.offline) st = T.offline;
    else if (S.notice && now < S.noticeUntil) st = S.notice;
    else if (S.endText && now < S.endUntil && !S.card) st = S.endText;
    setText($("status"), st);
    var band = $("band");
    /* 小型の窓では札そのものが知らせ = 札の間は縁も帯も出さない。
       通知は札の約 6 秒後に来るので、帯が割り込むと見つめている羽根がずれる */
    if (S.card) S.cardAt = now;                 /* 札と札の間の短い隙にも割り込ませない */
    var lightOn = !!(S.snap && S.snap.light) && now < S.lightUntil &&
      !(S.mode === "small" && (S.card || now - (S.cardAt || -1e9) < 1500));
    if (lightOn) {
      setText(band, C.lightText(S.snap.light, S.lang));
      band.hidden = false;
      viewDocument.body.classList.add("glow");
    } else {
      band.hidden = true;
      viewDocument.body.classList.remove("glow");
      $("card").classList.remove("blink");
    }
    updateUndo(now);
  }

  /* 取り消す = 押した後の猶予のうちだけ、上の中央に大きく。扇では内の帯そのもの (押した羽根の上には出さない・§4.3) */
  function updateUndo(now) {
    var T = L();
    var z = $("undo-zone");
    var card = S.card;
    var btn = $("undo-btn");
    if (!card || card.state !== "deciding") {
      if (!z.hidden) z.hidden = true;
      btn.disabled = true;
      return;
    }
    z.hidden = false;
    var label = C.choiceLabel(card, card.choice, S.lang);
    var left = S.undoAt !== null ? (S.undoAt - now) / 1000 : 0;
    if (left > 0) {
      setText($("undo-label"), T.decided + ": " + label);
      setText($("undo-text"), T.undo + " (" + Math.ceil(left) + ")");
      btn.hidden = false;
      btn.disabled = false;
      if (S.fan) fanNote(T.undo + " (" + Math.ceil(left) + ")", label);
    } else {
      setText($("undo-label"), T.delivering + " " + label);
      btn.hidden = true;
      btn.disabled = true;
      if (S.fan) fanNote(label, "");
    }
  }

  /* 猶予のうちの書の帯 = 上の行に取り消す (残りの秒)・下の行に決めた答え */
  function fanNote(first, second) {
    [first, second].forEach(function (text, i) {
      var t = $("fan-script-" + i);
      if (!t) return;
      t.style.fontSize = (i ? 20 : 28) + "px";
      t.classList.add("note");
      setText(t.firstChild, text);
    });
  }

  function undoOpen() {
    return !!S.card && S.card.state === "deciding" && S.undoAt !== null && performance.now() < S.undoAt;
  }

  function showNotice(t) {
    S.notice = t;
    S.noticeUntil = performance.now() + 5000;
  }

  function onNewLight() {
    if (S.sound) beep();
    var c = $("card");
    if (!reduced && S.card && S.mode !== "small") {
      c.classList.remove("blink");
      void c.offsetWidth;
      c.classList.add("blink");
    }
  }

  function beep() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      S.ac = S.ac || new AC();
      var o = S.ac.createOscillator();
      var g = S.ac.createGain();
      o.frequency.value = 880;
      g.gain.value = 0.15;
      o.connect(g);
      g.connect(S.ac.destination);
      o.start();
      o.stop(S.ac.currentTime + 0.18);
    } catch (e) { /* 音が出せない環境では光だけ */ }
  }

  /* ---- 押す ---- */
  function press(key, by) {
    if (key === "reset" || key === "phone" || key === "gear" || key === "pip" || key === "theme") {
      if (by !== "key" && by !== "click") return;          /* 視線では押さない (§4.5) */
      if (key === "reset") api("POST", "/stats/reset", {}).catch(function () { S.offline = true; });
      if (key === "phone") openPhone();
      if (key === "gear") openGear();
      if (key === "pip") openPip();
      if (key === "theme") toggleTheme();
      return;
    }
    if (key === "close" || key === "sheet-next") {
      if (S.sheet && by !== "key" && by !== "switch" && performance.now() < S.sheetArmAt) return;  /* 開いた直後の視線の click は受けない */
      if (key === "close") { closeOverlay(); return; }
      sheetPage(1);
      S.dwell.reset();
      S.dwell.block(S.over);                               /* 見つめ直すまで次の頁へ送らない */
      setFill(null, 0);
      return;
    }
    if (key === "sheet") {
      if (performance.now() >= (S.guardUntil || 0)) openSheet();
      return;
    }
    var card = S.card;
    if (!card || S.overlay) return;
    if (by === "click" && performance.now() < (S.guardUntil || 0)) return;  /* 紙を閉じた直後の視線の click では答えない */
    if (key === "undo") {                                  /* 写しが deciding なら、/answer の返りを待たずに取り消せる */
      if (!S.undoing && undoOpen()) doUndo(by);
      return;
    }
    if (S.answering || card.state !== "shown" || S.sentKey === S.key) return;
    var b = S.btns[key];
    if (!b || b.disabled) return;
    S.delta[by] = (S.delta[by] || 0) + 1;
    S.dwell.reset();
    S.dwell.block(S.over);                                 /* 押した直後 = 入り直すまで数えない */
    setFill(null, 0);
    var r = C.pressKey(card, S.ui, key);
    if (!r) return;
    if (r.send) { sendAnswer(r.send, by); return; }
    S.ui = r.ui;
    var k = C.viewKey(card, S.ui, S.lang);
    if (r.gen || k !== S.key) {
      S.key = k;
      render();
      bumpGen();
    } else {
      render();                                            /* 印を付けただけ = 世代は進めない */
    }
    updateSide(performance.now());
  }

  /* 新しい押しは要求ごとに切り離す (§4.5)。応答の喪失では受理されたか分からないため、
   * 再送する束は元の ID と数を保つ。server は同じ札の受理済み ID を二度数えない。 */
  function takePresses() {
    var sent = S.delta;
    S.delta = C.zeroPresses();
    return sent;
  }

  function takePressBatches() {
    var taken = C.takePressBatches(S.pressLedger, takePresses());
    S.pressLedger = taken.ledger;
    return taken.batches;
  }

  function giveBack(cardId, sent, batches) {
    if (!S.card || S.card.id !== cardId) return;
    if (batches) S.pressLedger = C.returnPressBatches(S.pressLedger, batches);
    else S.delta = C.addPresses(S.delta, sent);
  }

  function sendAnswer(choice, by) {
    var card = S.card;
    S.answering = true;
    var sentKey = S.key;
    var batches = takePressBatches(), sent = C.sumPressBatches(batches);
    api("POST", "/answer", { id: card.id, seq: card.view_seq, choice: choice, by: by,
                             presses: sent, press_batches: batches })
      .then(function (r) {
        if (r.status === 200) {
          S.sentKey = sentKey;
          return;
        }
        giveBack(card.id, sent, batches);
        if (r.status === 401) {
          S.problem = L().bad_token;
        } else {
          showNotice(L().stale);
          kick();
        }
      }, function () {
        giveBack(card.id, sent, batches);
        S.offline = true;
      })
      .then(function () { S.answering = false; }, function () { S.answering = false; });
  }

  function doUndo(by) {
    var card = S.card;
    if (!card || S.undoing) return;
    S.undoing = true;
    S.delta[by] = (S.delta[by] || 0) + 1;
    var batches = takePressBatches(), sent = C.sumPressBatches(batches);
    api("POST", "/undo", { id: card.id, by: by, presses: sent, press_batches: batches })
      .then(function (r) {
        if (r.status === 200) return;
        giveBack(card.id, sent, batches);
        kick();
      }, function () {
        giveBack(card.id, sent, batches);
        S.offline = true;
      })
      .then(function () { S.undoing = false; }, function () { S.undoing = false; });
  }

  /* ---- 入力 ---- */
  function onPointer(e) {
    if (e.pointerType === "touch") { S.pointerType = "touch"; return; }
    S.pointerType = e.pointerType || "mouse";
    S.lastX = e.clientX;
    S.lastY = e.clientY;
    S.pointerAt = performance.now();
    S.over = dwellKeyOf(e.target);
    var inCopy = !!(e.target && e.target.closest && e.target.closest("#copy"));
    if (inCopy !== !!S.overCopy) { S.overCopy = inCopy; S.copyAt = S.pointerAt; }
    if (S.firstPointer) { S.dwell.block(S.over); S.firstPointer = false; }
    if (S.over) spotlight(S.btns[S.over]);
    if (S.options.trail === "on") {
      var dots = $("trail").children;
      for (var i = 0; i < dots.length; i++) {
        dots[i].style.left = (e.clientX / S.options.scale) + "px";
        dots[i].style.top = (e.clientY / S.options.scale) + "px";
      }
    }
  }

  function isSwitch(e) {
    var k = S.switchKey;
    if (k === "Space" || k === " ") return e.code === "Space" || e.key === " ";
    return e.code === k || e.key === k || (k.length === 1 && typeof e.key === "string" && e.key.toLowerCase() === k.toLowerCase());
  }

  function onKeyDown(e) {
    if (!inputActive()) return;
    var code = e.code || e.key;
    var sw = S.scanMs > 0 && isSwitch(e);
    if (e.repeat || S.held[code]) {                         /* 押したままの鍵は離すまで数えない */
      if (sw) e.preventDefault();
      return;
    }
    S.held[code] = true;
    S.lastInput = "key";
    if (S.overlay) {
      if (e.key === "Escape") { e.preventDefault(); closeOverlay(); }
      else if (S.sheet) sheetKey(e, sw);
      return;
    }
    var active = viewDocument.activeElement && viewDocument.activeElement.closest
      ? viewDocument.activeElement.closest("[data-key]") : null;
    if (!sw && active && (e.key === "Enter" || e.key === " ") &&
        ["reset", "phone", "gear", "pip", "theme"].indexOf(active.dataset.key) >= 0) {
      e.preventDefault();
      press(active.dataset.key, "key");
      return;
    }
    var card = S.card;
    if (!card) return;
    if (card.state === "deciding") {
      var onUndo = (e.key === "Enter" || e.key === " ") && active && active.dataset.key === "undo";
      if (sw || onUndo || e.key === "Backspace" || e.key === "Escape") {
        e.preventDefault();
        if (undoOpen()) press("undo", sw ? "switch" : "key");
      }
      return;
    }
    if (card.state !== "shown") return;
    if (sw) {
      e.preventDefault();
      if (S.scanEl && S.scanEl.dataset.key) press(S.scanEl.dataset.key, "switch");
      return;
    }
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === "Escape") { e.preventDefault(); press("fixed", "key"); return; }
    if (e.key === "0") { e.preventDefault(); press("terminal", "key"); return; }
    if (S.fan && /^Arrow(Left|Right|Up|Down)$/.test(e.key)) {
      e.preventDefault();
      var at = S.fanVisual.indexOf(active), n = S.fanVisual.length;
      var dir = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
      if (n) S.fanVisual[at < 0 ? 1 : (at + dir + n) % n].focus({ preventScroll: true });
      return;
    }
    if (/^[1-6]$/.test(e.key)) {
      var k = S.optionKeys[parseInt(e.key, 10) - 1];
      if (k) { e.preventDefault(); press(k, "key"); }
      return;
    }
    if ((e.key === "Enter" || e.key === " ") && active && active.dataset.dwell) {
      e.preventDefault();
      press(active.dataset.key, "key");
    }
  }

  function onClick(e) {
    if (e.detail === 0) return;                             /* キーで起きた click は keydown で扱った */
    var b = e.target && e.target.closest ? e.target.closest("[data-key]") : null;
    if (!b && e.target && e.target.closest && e.target.closest("#copy") && !$("more").hidden) {
      var picked = viewWindow.getSelection();              /* 字を選んだだけの時は開かない */
      if (!picked || picked.isCollapsed) press("sheet", "click");
      return;
    }
    if (!b || b.disabled) return;
    S.lastInput = S.pointerType === "touch" ? "touch" : "click";
    press(b.dataset.key, S.pointerType === "touch" ? "touch" : "click");
  }

  /* 毎こま = 滞留・走査・表示の秒 */
  function frame(now) {
    now = performance.now();  // Use one clock even after adopting the DOM into PiP.
    var dwelling = false;
    if (S.dwellMs > 0 && S.pointerType !== "touch" && (!S.overlay || S.sheet) && inputActive()) {
      var r = S.dwell.update(S.over, now);
      setFill(r.target, r.progress);
      dwelling = !!r.target;
      /* 滞留の間は、数えている羽根の全文を必ず出す = 読んだ字と違う羽根が押されない (線 3) */
      if (dwelling && S.spotKey !== r.target && S.btns[r.target]) spotlight(S.btns[r.target]);
      if (r.fire) {
        setFill(null, 0);
        S.lastInput = "dwell";
        press(r.target, "dwell");
      }
    }
    /* 切れている左の文章を見つめたら全文の紙を開く。1 度閉じた札では見つめただけでは開かない */
    if (S.overCopy && S.dwellMs > 0 && S.mode === "small" && !S.overlay && S.card && S.card.state === "shown" &&
        S.sheetSeen !== S.card.id && now - S.copyAt >= 800 && !$("more").hidden) openSheet();
    if (S.scanMs > 0) {
      var card = S.card;
      var target = null;
      /* 窓の中で pointer が動いている間は光を回さない = 視線で読み押す人の邪魔をしない。
       * pointer が止まっているか窓の外なら回る (スイッチの人・OS の鍵盤を見ている時)。 */
      var moving = dwelling || now - (S.pointerAt || -1e9) < 1500;
      if (moving) S.scanPaused = true;
      else if (S.scanPaused) { S.scanPaused = false; S.scan.restart(now); }
      if (card && card.state === "deciding") {
        var u = $("undo-btn");                               /* 猶予のうち = 走査を止め、次の押下 = 取り消す */
        target = u.hidden ? null : u;
      } else if (card && card.state === "shown" && !S.overlay && !S.answering && inputActive() && !moving) {
        var i = S.scan.index(now, S.scanList.length);
        target = i >= 0 ? S.scanList[i] : null;
      }
      if (S.scanEl !== target) {
        if (S.scanEl) S.scanEl.classList.remove("scan");
        if (target) target.classList.add("scan");
        S.scanEl = target;
        if (target) spotlight(target);
      }
    }
    gazeScroll(now);
    if (now - S.sideAt > 250) {
      S.sideAt = now;
      updateSide(now);
    }
    rafWindow = viewWindow;
    rafId = viewWindow.requestAnimationFrame(frame);
  }

  /* 見えている窓なら受ける。焦点は問わない = 端末で作業したまま隅の窓を見て押す (扇の芯)。
   * 焦点の出入りの瞬間に古い滞留で押さない守りは blur / focus の releaseDwell が持つ。 */
  function inputActive() { return !viewDocument.hidden; }

  /* 見つめて本文を送る = 視線だけの人は巻物を回せない (§4.1)。本文の枠の下寄りで下へ・上寄りで上へ */
  function scrollerAt(x, y) {
    var n = viewDocument.elementFromPoint(x, y);
    while (n && n !== viewDocument.body) {
      var named = n.id === "copy" || n.id === "card" || n.id === "spotlight" || n.tagName === "PRE" ||
        (n.classList && n.classList.contains("plain"));
      if (named && n.scrollHeight > n.clientHeight + 2) return n;
      n = n.parentElement;
    }
    return null;
  }

  function gazeScroll(now) {
    var dt = Math.min(0.1, Math.max(0, (now - (S.scrollAt || now)) / 1000));
    S.scrollAt = now;
    if (S.lastX < 0 || S.pointerType === "touch" || S.overlay || !inputActive()) return;
    var box = scrollerAt(S.lastX, S.lastY);
    if (!box) return;
    var r = box.getBoundingClientRect();
    var dir = C.scrollDirection((S.lastY - r.top) / r.height);
    if (!dir) return;
    S.scrollRest = (S.scrollRest || 0) + dir * 90 * dt;
    var whole = S.scrollRest > 0 ? Math.floor(S.scrollRest) : Math.ceil(S.scrollRest);
    if (whole) { box.scrollTop += whole; S.scrollRest -= whole; }
  }

  function restartFrames() {
    if (rafId !== null) rafWindow.cancelAnimationFrame(rafId);
    rafWindow = viewWindow;
    rafId = viewWindow.requestAnimationFrame(frame);
  }

  function bindInputs(w) {
    var d = w.document;
    function active(fn) { return function (e) { if (w === viewWindow) fn(e); }; }
    d.addEventListener("pointermove", active(onPointer), { passive: true });
    d.addEventListener("pointerover", active(onPointer), { passive: true });
    d.addEventListener("pointerdown", active(function (e) { S.pointerType = e.pointerType || "mouse"; }), { passive: true, capture: true });
    d.documentElement.addEventListener("pointerleave", active(function () { S.over = null; S.overCopy = false; S.lastX = -1; S.scrollRest = 0; }));
    w.addEventListener("blur", active(releaseDwell));
    w.addEventListener("focus", active(function () { releaseDwell(); S.scan.restart(performance.now()); }));
    d.addEventListener("visibilitychange", active(releaseDwell));
    w.addEventListener("resize", active(function () { fitFan(); if (S.sheet) fitSheet(); }));
    d.addEventListener("keydown", active(onKeyDown));
    d.addEventListener("keyup", active(function (e) { delete S.held[e.code || e.key]; }));
    d.addEventListener("click", active(onClick));
    d.addEventListener("focusin", active(function (e) { spotlight(e.target); }));
  }

  function openPip() {
    if (viewWindow !== window) { viewWindow.close(); return; }
    if (!window.documentPictureInPicture || S.pipOpening) return;
    S.pipOpening = true;
    var width = Math.max(940, S.fan ? parseFloat($("fan").style.width) * S.options.scale + 320 : 0);
    var height = Math.max(400, S.fan ? parseFloat($("fan").style.height) * S.options.scale + 40 : 0);
    window.documentPictureInPicture.requestWindow({ width: width, height: height }).then(function (w) {
      var surface = $("surface");
      w.addEventListener("pagehide", function () {
        if (viewWindow !== w) return;
        homeDocument.body.appendChild(surface);
        viewWindow = window; viewDocument = homeDocument;
        S.lastX = -1; S.over = null;
        setChrome(); S.key = ""; refreshView(); restartFrames();
      }, { once: true });
      var link = w.document.createElement("link");
      link.rel = "stylesheet"; link.href = location.origin + "/static/board.css";
      w.document.head.appendChild(link);
      w.document.body.appendChild(surface);
      viewWindow = w; viewDocument = w.document;
      bindInputs(w);
      S.lastX = -1; S.over = null;
      setChrome(); S.key = ""; refreshView(); restartFrames();
    }).catch(function () {
      if (viewWindow !== window) viewWindow.close();
      showNotice(L().pip_error);
    }).then(function () { S.pipOpening = false; });
  }

  /* ---- 携帯で開く・設定 (キーと click だけ) ---- */
  function showPanel(title, fill) {
    S.overlay = title;
    $("panel-title").textContent = title;
    var body = $("panel-body");
    body.replaceChildren();
    fill(body);
    $("overlay").hidden = false;
    $("panel-close").focus({ preventScroll: true });
    S.dwell.reset();
    setFill(null, 0);
  }

  function closeOverlay() {
    S.overlay = null;
    $("overlay").hidden = true;
    if (S.sheet) {                                         /* 閉じた直後の視線の click で羽根を押さない */
      S.sheet = null;
      S.guardUntil = performance.now() + 1200;
      $("overlay").classList.remove("sheet");
      delete $("panel-close").dataset.dwell;
      $("panel-next").hidden = true;
      $("panel-body").style.fontSize = "";
    }
    S.dwell.reset();
    S.dwell.block(keyAtPointer());
  }

  /* 全文の紙 = 左の文章を窓いっぱいの押せない紙に大きく出す。設定の面と同じ守りが効く (答え・走査は止まる)。
     閉じるボタンは羽根の無い左に置き、視線が外れても勝手に閉じない (閉じた視線の下に羽根を出さない) */
  function openSheet() {
    var card = S.card;
    if (!card || card.state !== "shown" || S.overlay || S.mode !== "small") return;
    var m = C.buildScreen(card, S.ui, S.lang);
    showPanel(L()["kind_" + card.kind], function (body) {
      if (m.head) body.appendChild(el("h3", "sheet-head", m.head));
      if (m.text) body.appendChild(el("p", "sheet-text", m.text));
      m.blocks.forEach(function (b) { body.appendChild(blockEl(b)); });
      if (m.question) body.appendChild(el("p", "sheet-question", m.question));
    });
    S.sheet = card.id;
    S.sheetSeen = card.id;
    S.sheetArmAt = performance.now() + 1200;
    $("overlay").classList.add("sheet");
    $("panel-close").dataset.dwell = "1";
    updateSheet();
    fitSheet();
    S.dwell.block(keyAtPointer());
  }

  /* 紙に全部が収まる一番大きな字。18px でも収まらなければ「次へ」で送る */
  function fitSheet() {
    var body = $("panel-body"), size = 26;
    do {
      body.style.fontSize = (size * S.options.font) + "px";
      size -= 2;
    } while (size >= 18 && body.scrollHeight > body.clientHeight);
    body.scrollTop = 0;
    $("panel-next").hidden = body.scrollHeight <= body.clientHeight + 2;
  }

  function sheetPage(dir) {
    var body = $("panel-body"), end = body.scrollHeight - body.clientHeight;
    var step = Math.max(40, body.clientHeight - 40);
    body.scrollTop = dir > 0 && body.scrollTop >= end - 2 ? 0 : body.scrollTop + dir * step;
  }

  function sheetKey(e, sw) {
    var body = $("panel-body");
    if (e.key === "PageDown" || e.key === "ArrowDown") { e.preventDefault(); sheetPage(1); }
    else if (e.key === "PageUp" || e.key === "ArrowUp") { e.preventDefault(); sheetPage(-1); }
    else if (sw || e.key === "Enter" || e.key === " ") {   /* 1 鍵の人 = 押すたびに次の頁・最後の頁で閉じる */
      e.preventDefault();
      if (body.scrollTop >= body.scrollHeight - body.clientHeight - 2) closeOverlay();
      else sheetPage(1);
    }
  }

  /* 紙の左上 = 残り時間。札が終わっても紙は勝手に閉じない (次の札の羽根を視線の下に出さない) */
  function updateSheet() {
    var live = S.card && S.card.id === S.sheet;
    setText($("panel-title"), live ? L()["kind_" + S.card.kind] + "\n" + $("remain").textContent : L().sheet_over);
  }

  /* 左の文章が切れている時だけ「▼ 全文」を見せる */
  function updateMore() {
    var more = $("more"), c = $("copy");
    var show = S.mode === "small" && !!S.card && S.card.state === "shown" && c.scrollHeight > c.clientHeight + 2;
    if (more.hidden === show) more.hidden = !show;
    var at = S.scanList.indexOf(more);
    if (show && at < 0) S.scanList.push(more);
    if (!show && at >= 0) S.scanList.splice(at, 1);
  }

  function openPhone() {
    var T = L();
    showPanel(T.phone, function (body) {
      body.appendChild(el("p", "url", location.origin + "/#t=" + S.token));
      body.appendChild(el("p", "", C.fmt(T.phone_help, { port: location.port || "80" })));
    });
  }

  function addSelect(body, label, name, opts, cur) {
    var lb = el("label");
    lb.appendChild(el("span", "", label));
    var sel = el("select");
    cur = String(cur);
    if (!opts.some(function (o) { return o[0] === cur; })) opts = opts.concat([[cur, cur]]);
    sel.name = name;
    opts.forEach(function (o) {
      var op = el("option", "", o[1]);
      op.value = o[0];
      if (o[0] === cur) op.selected = true;
      sel.appendChild(op);
    });
    sel.addEventListener("change", function () { setParam(name, sel.value); });
    lb.appendChild(sel);
    body.appendChild(lb);
  }

  function addInput(body, label, name, value, min, max) {
    var lb = el("label"), input = el("input");
    lb.appendChild(el("span", "", label));
    input.name = name; input.value = value;
    input.type = min === undefined ? "text" : "number";
    if (min !== undefined) { input.min = min; input.max = max; input.step = "any"; }
    else input.maxLength = 32;
    input.addEventListener("change", function () { setParam(name, input.value); input.value = S.options[name]; });
    lb.appendChild(input); body.appendChild(lb);
  }

  function openGear() {
    var T = L();
    var o = S.options;
    showPanel(T.settings, function (body) {
      addSelect(body, T.set_dwell, "dwell",
                [["0", "0"], ["0.8", "0.8"], ["1", "1.0"], ["1.2", "1.2"], ["1.5", "1.5"], ["2", "2.0"]],
                String(S.dwellMs / 1000));
      addSelect(body, T.set_scan, "scan",
                [["off", T.off], ["1", "1.0"], ["1.5", "1.5"], ["2", "2.0"], ["3", "3.0"]],
                S.scanMs ? String(S.scanMs / 1000) : "off");
      addInput(body, T.set_key, "key", o.key);
      addSelect(body, T.set_lang, "lang", [["auto", T.auto], ["ja", "日本語"], ["en", "English"]], o.lang);
      addSelect(body, T.set_sound, "sound", [["off", T.off], ["on", T.on]], S.sound ? "on" : "off");
      addSelect(body, T.set_mode, "mode", [["small", T.small], ["large", T.large]], o.mode);
      addInput(body, T.set_scale, "scale", o.scale, .75, 2);
      addInput(body, T.set_font, "font", o.font, .8, 2);
      addSelect(body, T.set_theme, "theme", [["auto", T.auto], ["light", T.light], ["dark", T.dark], ["contrast", T.contrast]], o.theme);
      addSelect(body, T.set_desc, "desc", [["on", T.on], ["off", T.off]], o.desc);
      addSelect(body, T.set_trail, "trail", [["off", T.off], ["on", T.on]], o.trail);
    });
  }

  function setParam(name, value) {
    var p = new URLSearchParams(location.search);
    p.set(name, value);
    try {
      var saved = C.parseOptions("", savedOptions());
      saved[name] = C.parseOptions(p.toString(), saved)[name];
      window.localStorage.setItem("blemma.options", JSON.stringify(saved));
    } catch (e) { /* URL still works when local storage is disabled. */ }
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    readSettings();
    setChrome();
    S.key = "";
    refreshView();
    var title = $("panel-title");
    if (S.overlay) title.textContent = L().settings;
  }

  /* 明るい / 暗いの切り替え = 歯車の「配色」と同じ鍵 (theme) を 1 回で替える */
  function isDark() {
    if (S.options.theme === "auto") return viewWindow.matchMedia("(prefers-color-scheme: dark)").matches;
    return S.options.theme !== "light";
  }

  function toggleTheme() { setParam("theme", isDark() ? "light" : "dark"); }

  function setChrome() {
    var T = L();
    viewDocument.documentElement.lang = S.lang;
    viewDocument.documentElement.dataset.theme = S.options.theme;
    viewDocument.documentElement.style.zoom = S.options.scale === 1 ? "" : String(S.options.scale);
    viewDocument.documentElement.style.setProperty("--font", String(S.options.font));
    viewDocument.title = S.mode === "small" ? "BLEMMA · 扇 (OhGi)" : "BLEMMA";
    $("stats-reset").textContent = T.reset;
    $("phone-btn").textContent = T.phone;
    $("gear-btn").textContent = T.settings;
    $("panel-close").textContent = T.close;
    $("panel-next").textContent = T.sheet_next;
    $("more").textContent = T.more;
    $("gear-btn").textContent = S.mode === "small" ? "⚙" : T.settings;
    $("gear-btn").setAttribute("aria-label", T.settings);
    $("theme-btn").textContent = isDark() ? "☀" : "☾";
    $("theme-btn").setAttribute("aria-label", isDark() ? T.to_light : T.to_dark);
    $("theme-btn").title = isDark() ? T.to_light : T.to_dark;
    $("pip-btn").hidden = S.mode !== "small" || !window.documentPictureInPicture;
    $("pip-btn").textContent = viewWindow === window ? T.pip : T.pip_back;
    $("trail").hidden = S.options.trail !== "on";
  }

  function init() {
    readSettings();
    readToken();
    setChrome();
    S.key = C.viewKey(null, S.ui, S.lang);
    render();
    bindInputs(window);
    window.addEventListener("hashchange", function () {
      var old = S.token;
      readToken();
      if (S.token && S.token !== old) {
        var wasStopped = S.stopped;
        S.problem = "";
        S.stopped = false;
        S.seq = -1;
        if (wasStopped || !S.abort) poll();
        else { S.kicked = true; S.abort.abort(); }
      }
    });
    restartFrames();
    if (!S.token) { S.problem = L().no_token; updateSide(performance.now()); return; }
    poll();
  }

  init();
})();
