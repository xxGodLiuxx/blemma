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
    abort: null, kicked: false, retry: 0, stopped: false, overlay: null, sideAt: 0, ac: null,
    health: new C.Health(3), stoppedAt: null, fontFit: 1
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
    if (S.shapeSig === undefined) S.shapeSig = "null";     /* 切っていない窓に元へ戻す知らせを送らない */
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
      if (S.abort === ctl) S.abort = null;        /* 終わった要求は kick の的にしない */
      if (r.status === 401) { S.stopped = true; S.problem = L().bad_token; return; }
      if (r.status !== 200 || !r.data) throw new Error("status " + r.status);
      S.retry = 0;
      S.offline = false;
      S.kicked = false;                 /* 通った = 古い kick の印を持ち越さない (後の 1 回の失敗を数え落とさない) */
      S.health.ok();
      apply(r.data);
      poll();                         /* 直に呼ぶ = 隠れた頁で timer が間引かれても見る人の数が途切れない */
    }).catch(function () {
      clearTimeout(timer);
      if (S.abort === ctl) S.abort = null;
      if (S.kicked) { S.kicked = false; poll(); return; }
      S.offline = true;
      S.health.fail(performance.now());
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
      if (S.ui.cardId !== null) forgetSends();
      S.ui = C.newUi(null);
    } else if (card.id !== S.ui.cardId) {
      S.ui = C.newUi(card.id);
      S.delta = C.zeroPresses();
      S.pressLedger = C.newPressLedger(S.pressLedger.source);
      forgetSends();
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
      bumpGen(true);
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
    fitWindow();                      /* 先に窓の大きさ。形 (透過) は寸法が揃ってから送る */
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
    disarm();
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
    S.fanOutline = layout.outline;
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

  /* 窓の大きさに扇と字を合わせる = ドラッグで窓を変えると、扇も和紙も字も一緒に追従する */
  function fitFan() {
    var root = viewDocument.documentElement, fit = 1;
    if (S.fan) {
      var fan = $("fan"), box = $("fan-scroll");
      var w = parseFloat(fan.style.width), h = parseFloat(fan.style.height);
      var wide = viewWindow.innerWidth / viewWindow.innerHeight >= 1.5;      /* 横向き = 左に問い・右に扇 */
      var roomW = root.clientWidth - (wide ? 300 : 20);
      var roomH = wide ? viewWindow.innerHeight - 20 : viewWindow.innerHeight * 0.45;  /* 縦向きの残りは和紙 */
      var k = Math.max(0.45, Math.min(1.8, roomW / w, roomH / h));
      fan.style.transform = "scale(" + k.toFixed(4) + ")";
      box.style.height = Math.ceil(h * k) + "px";
      box.style.width = wide ? Math.ceil(w * k) + "px" : "";
      root.style.setProperty("--fan-w", Math.ceil(w * k) + "px");
      fit = Math.max(0.85, Math.min(1.4, k));
    }
    S.fontFit = fit;
    setFont();
    pushShape();
  }

  /* 字の大きさを書くのはここだけ = 設定の倍率 × 窓に合わせた補正 (補正は fitFan が測る)。
   * ほかの所が設定の倍率だけで書くと、窓に合わせた字が元の大きさへ戻ってしまう */
  function setFont() {
    viewDocument.documentElement.style.setProperty("--font", String(S.options.font * (S.fontFit || 1)));
  }

  /* 最前面と透過 = Windows の小窓は server が窓に当てる。当たらない時は何も変わらない。
   * 返り = 頼んだ事が窓に当たったか (窓が見つからない・API が失敗した時は false)。応答で直すのは固定のボタンだけ */
  function windowCall(body) {
    return send("/window", body, 5000).then(function (r) {
      var found = !!(r.status === 200 && r.data && r.data.found);
      S.windowOk = found;
      if (found) S.pinned = !!r.data.pin;
      setPinButton();
      return found && r.data.ok !== false;
    }, function () { return false; });
  }

  function togglePin() {
    if (viewWindow !== window) { viewWindow.close(); return; }
    var want = !S.pinned;
    /* 固定できない時は別の窓 (PiP) を手前に出す。外す側が当たらなかった時は、手前の窓を増やさない */
    windowCall({ pin: want }).then(function (done) { if (!done && want) openPip(); });
  }

  function isApp() {
    return !!window.matchMedia && window.matchMedia("(display-mode: standalone)").matches;
  }

  /* 待機中は閉じた扇の小さな窓にして、札が来たら元の大きさへ開く (app の窓だけ。普通のタブでは大きさは変わらない) */
  var WIDGET = [320, 120], FULL = [640, 720];
  var CLOSED = [[4, 14], [0, 45], [4, 76], [290, 63], [298, 45], [290, 27]];     /* 閉じた扇は横に寝かせて控える */

  /* 札を出す時の元の大きさ。待機の小さな窓のまま読み直しても失わないよう、この窓の間だけ覚えておく */
  function rememberFull(size) {
    S.fullSize = size;
    try { window.sessionStorage.setItem("blemma.full", size.join(",")); }
    catch (e) { /* 覚えられない環境でも、この頁の間は S.fullSize で動く */ }
  }

  function recallFull() {
    if (S.fullSize) return S.fullSize;
    try {
      var m = /^(\d{3,5}),(\d{3,5})$/.exec(window.sessionStorage.getItem("blemma.full") || "");
      if (m) return [parseInt(m[1], 10), parseInt(m[2], 10)];
    } catch (e) { /* 同上 */ }
    return null;
  }

  function fitWindow() {
    if (S.mode !== "small" || viewWindow !== window || !isApp()) return;
    var idle = !S.card && !S.overlay;
    if (idle === S.widget) return;
    var w = window.outerWidth, h = window.outerHeight, s = window.screen, pos = S.options.pos;
    if (!(w > 0 && h > 0)) return;    /* 読み込みの頭は窓の寸法がまだ 0 = 次のこまで見直す (窓を画面の左上へ飛ばさない) */
    S.widget = idle;
    var tiny = w <= WIDGET[0] + 40 && h <= WIDGET[1] + 40;      /* いま待機の大きさ = これを「元の大きさ」と覚えない */
    if (idle && !tiny) rememberFull([w, h]);
    /* 札つきで始まった時 (起動の直後・札の途中で頁を読み直した時) は、今の窓のまま = 利用者が広げた窓を、
       前に覚えた大きさへ縮めない。待機の大きさの窓に札が来た時だけ、覚えた大きさ (無ければ既定) へ開く */
    var to = idle ? WIDGET : tiny ? recallFull() || FULL : null;
    if (!to) return;
    S.drag = null;                    /* 掴んで運んでいる最中に窓の大きさが替わる = 掴み直してもらう (掴んだ時の大きさへ戻さない) */
    windowMoved();
    var x = window.screenX + w - to[0], y = window.screenY + h - to[1];        /* 右下の角を保つ */
    if (pos !== "keep") {
      x = pos.charAt(1) === "r" ? s.availLeft + s.availWidth - to[0] : s.availLeft;
      y = pos.charAt(0) === "b" ? s.availTop + s.availHeight - to[1] : s.availTop;
    }
    x = Math.max(s.availLeft, Math.min(x, s.availLeft + s.availWidth - to[0]));
    y = Math.max(s.availTop, Math.min(y, s.availTop + s.availHeight - to[1]));
    /* 縮める時は先に小さくしてから動かす = 大きいまま隅へ動かすと、画面からはみ出す分だけ押し戻されて角がずれる。
       広げる時は先に動かしてから大きくする (逆の順だと、広げた窓がはみ出して押し戻される) */
    if (to[0] * to[1] < w * h) { window.resizeTo(to[0], to[1]); window.moveTo(x, y); }
    else { window.moveTo(x, y); window.resizeTo(to[0], to[1]); }
  }

  /* 窓の大きさや位置が変わると、画面の同じ所に居る pointer の下の物が入れ替わる (待機の小窓が札で開くと、置いたままの
     pointer の下に羽根が来る)。落ち着くまで滞留を数えず (frame)、落ち着いた後に最初に届いた pointer の下の釦は、
     入り直すまで数えない = 見ないまま押されない (線 3)。前の窓の座標 (lastX/lastY) と、その下に居た釦は捨てる */
  var WINDOW_SETTLE_MS = 600;
  function windowMoved() {
    S.windowAt = performance.now();
    S.lastX = -1;
    S.over = null;
    S.firstPointer = true;
    releaseDwell();
  }

  /* 扇の周りを透かす = 題の帯と和紙は四角のまま、扇の外の角だけを窓から切る */
  function pushShape() {
    if (S.mode !== "small" || viewWindow !== window || S.shapeBusy) return;   /* 前の頼みの返事を待つ = 順が入れ替わらない */
    var shape = null;
    var side = (window.outerWidth - window.innerWidth) / 2, top = window.outerHeight - window.innerHeight - side;
    /* 窓の大きさを変えた直後は、外の寸法だけが先に新しくなる。枠の幅と題の帯の高さがあり得ない値の間は、
       形を作らず次のこまを待つ (崩れた形を送ると、板は窓を四角へ戻してしまう) */
    var odd = S.options.clear === "on" && !(side >= 0 && side <= 14 && top >= 0 && top <= 56);
    if (odd) {
      /* 続く時は、頁を拡大・縮小している (内の寸法だけが倍率で変わり、形が扇からずれて羽根が切れる) = 切り抜きをやめて四角へ戻す */
      var since = performance.now();
      if (!S.shapeOddAt) S.shapeOddAt = since;
      if (since - S.shapeOddAt < 800) return;
    } else {
      S.shapeOddAt = 0;
    }
    if (!odd && S.options.clear === "on" && !S.card && !S.overlay && S.options.scale === 1) {
      var c = $("closed").querySelector("svg").getBoundingClientRect(), z = c.width / 300;   /* 待機中 = 閉じた扇だけ */
      shape = { dpr: window.devicePixelRatio, left: side, top: top, keep: 0, bare: true, rects: [],
                polygon: CLOSED.map(function (p) { return [c.left + p[0] * z, c.top + p[1] * z]; }) };
    } else if (!odd && S.options.clear === "on" && S.fan && !S.overlay && S.options.scale === 1 && S.fanOutline) {
      var fan = $("fan"), r = fan.getBoundingClientRect(), k = r.width / parseFloat(fan.style.width);
      var wide = window.innerWidth / window.innerHeight >= 1.5;
      var below = $("fan-scroll").getBoundingClientRect().bottom;       /* 縦向き = 扇の下は和紙 */
      var rects = wide ? [[0, 0, r.left - 6, window.innerHeight]] : [[0, below, window.innerWidth, window.innerHeight - below]];
      Array.prototype.forEach.call(fan.querySelectorAll(".fan-aux"), function (e) {
        var b = e.getBoundingClientRect();
        rects.push([b.left - 2, b.top - 2, b.width + 4, b.height + 4]);
      });
      shape = { dpr: window.devicePixelRatio, left: side, top: top, keep: 0, rects: rects,
                polygon: S.fanOutline.map(function (p) { return [r.left + p[0] * k, r.top + p[1] * k]; }) };
    }
    var sig = JSON.stringify(shape);
    if (sig === S.shapeSig) return;
    S.shapeSig = sig;
    S.shapeBusy = true;
    windowCall({ shape: shape }).then(function (done) {
      S.shapeBusy = false;
      /* 開いた直後は窓の名がまだ付いていない = 当たるまで少し繰り返す (API が失敗した時も同じ) */
      S.shapeTries = done ? 0 : (S.shapeTries || 0) + 1;
      if (!done && S.shapeTries < 20 && S.shapeSig === sig) S.shapeSig = "";
    });
  }

  /* 窓の位置 = 画面の 4 隅へ動かす (app の窓だけ動く。普通のタブでは何も起きない) */
  function placeWindow() {
    var pos = S.options.pos, s = window.screen;
    if (pos === "keep" || viewWindow !== window) return;
    var x = pos.charAt(1) === "r" ? s.availLeft + s.availWidth - window.outerWidth : s.availLeft;
    var y = pos.charAt(0) === "b" ? s.availTop + s.availHeight - window.outerHeight : s.availTop;
    window.moveTo(x, y);
  }

  function releaseDwell() {
    S.dwell.reset();
    S.dwell.block(S.over);
    setFill(null, 0);
  }

  /* 焦点を失った・頁が隠れた = 滞留のほかに、和紙の自動送りと窓のドラッグも手放す */
  function letGo() {
    releaseDwell();
    S.overMore = false;
    S.down = false;
    endDrag();
  }

  /* 表示の世代を進める = 滞留を止めて選択を解き、pointer の下の釦は入り直すまで数えない・走査は頭から (§4.2) */
  /* fromBoard = 板から来た替わり (新しい札・状態の変化・取り消しで戻った)。この時だけ、押しを数えない間を置く (press の SETTLE_MS)。
     札の中で人が画面を進めた時 (拒否 → 理由・次の設問) は置かない = 鍵で続けて打つ人の 2 打目を捨てない */
  function bumpGen(fromBoard) {
    var now = performance.now();
    S.gen += 1;
    if (fromBoard) {
      S.genAt = now;
      setSettling(true);
    }
    S.over = keyAtPointer();
    if (S.lastX < 0) S.firstPointer = true;
    S.overMore = false;               /* 「▼ 続き」も同じ = 動かさないままの pointer で、新しい札の和紙を送らない */
    releaseDwell();
    S.scan.restart(fromBoard ? now + scanQuiet() : now);   /* 板から替わった後は、1 こまぶん何も光らせない */
    if (S.scanEl) { S.scanEl.classList.remove("scan"); S.scanEl = null; }
    if (S.card && S.card.state === "shown" && S.lastInput === "key" && !S.overlay && S.scanMs <= 0) {
      var first = S.fan ? S.scanList[0] : viewDocument.querySelector("#opts .btn:not(:disabled)");
      if (first) first.focus({ preventScroll: true });
    }
  }

  /* 板から札が替わった後、走査が最初の光を出すまでの間 = 走査の 1 こまぶん (0.4〜1.5 秒)。押すのが遅い人の、前の札へ向けた
     1 押しが、新しい札の先頭 (許可) に当たらない (光っていない物は押せない) */
  function scanQuiet() {
    return Math.max(SETTLE_MS, Math.min(S.scanMs || 0, 1500));
  }

  /* 押しを数えない間は、頁に印を付ける (body.settling)。見た目は変えない = 試験と外の道具が「もう押せる」を読める */
  function setSettling(on) {
    var b = viewDocument.body;
    if (S.settling === on) return;
    S.settling = on;
    if (b && b.classList) b.classList.toggle("settling", on);
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
    if (key === "more") return $("more");
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
    setText($("closed-state"), label);
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
    updateMore();
    fitWindow();
    pushShape();
    /* 板が止まったら app の窓を閉じる (題の帯が隠れた窓も残らない)。止まったと見てから 10 秒 */
    var gone = goneSince(now);
    if (S.mode === "small" && viewWindow === window && gone !== null && now - gone > 10000 && isApp()) window.close();
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

  /* 板が止まったと見る時刻 (止まっていなければ null)。1 回の通信の失敗では決めない =
   * 板の見張り (/pending) が続けて 3 回落ちた時か、鍵が違って見張りをやめた時だけ。
   * 答えの送信が 1 回こけただけで、動いている板の窓を閉じない */
  function goneSince(now) {
    if (!S.stopped) { S.stoppedAt = null; return S.health.goneSince(); }
    if (S.stoppedAt === null) S.stoppedAt = now;
    return S.stoppedAt;
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
      btn.setAttribute("aria-label", T.undo + ": " + label);   /* 扇では釦の字を出さない = 読み上げ用の名 */
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

  /* 人の操作より前に作った AudioContext は止まったまま始まる = 合図の時と、鍵・click の時に起こす */
  function wakeSound() {
    try { if (S.ac && S.ac.state === "suspended" && S.ac.resume) S.ac.resume(); } catch (e) { /* 音が出せない環境では光だけ */ }
  }

  function beep() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      S.ac = S.ac || new AC();
      wakeSound();
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
  var SETTLE_MS = 400;                /* 表示が替わってから、押しを数え始めるまで */
  /* 取り消しは、猶予の短い板 (--undo-ms が 0.8 秒より短い) では猶予の半分まで = 許された猶予なら、その間に必ず押せる時間が残る
     (0.4 秒のままだと、猶予 0.4 秒以下の板では取り消しが 1 度も押せない) */
  function settleFor(key) {
    var undoMs = key === "undo" && S.snap ? S.snap.undo_ms : 0;
    return undoMs > 0 ? Math.min(SETTLE_MS, undoMs / 2) : SETTLE_MS;
  }
  function press(key, by) {
    if (key === "reset" || key === "phone" || key === "gear" || key === "pip" || key === "theme" || key === "copy") {
      if (by !== "key" && by !== "click") return;          /* 視線では押さない (§4.5) */
      if (key === "reset") api("POST", "/stats/reset", {}).catch(lostCall);
      if (key === "phone") openPhone();
      if (key === "gear") openGear();
      if (key === "pip") togglePin();
      if (key === "copy") copyCard();
      if (key === "theme") toggleTheme();
      return;
    }
    if (key === "close") { closeOverlay(); return; }
    /* 表示が替わった直後の押しは数えない (線 3) = 前の表示へ向けた遅れた 1 押しや、スイッチ・鍵のばたつきが、
       新しい札の先頭 (許可) や出たばかりの「取り消す」に当たらない。人が新しい表示を見て押すには、これより長く掛かる。
       滞留は「入り直すまで数えない」(bumpGen の releaseDwell) が別に守る */
    if (by !== "dwell" && performance.now() - S.genAt < settleFor(key)) return;
    if (key === "more") {                                  /* 和紙の続きを 1 画面分送る。最後まで読んだら先頭へ */
      copyPage(1);
      S.moreNext = performance.now() + 1500;
      S.dwell.reset();
      S.dwell.block(S.over);                               /* 見つめ直すまで次へ送らない */
      setFill(null, 0);
      return;
    }
    var card = S.card;
    if (!card || S.overlay) return;
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

  /* 期限つきの送信 = ms のうちに返らなければ中断して、失敗として扱う (返らない送信で頁が固まらない)。
   * 板は同じ機械に居る = 正常なら一瞬で返る。時計は返った時に止める */
  var SEND_MS = 8000;
  function send(path, body, ms) {
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, ms);
    return api("POST", path, body, ctl.signal).then(
      function (r) { clearTimeout(timer); return r; },
      function (e) { clearTimeout(timer); throw e; });
  }

  /* 札が替わった = 前の札への送信の印を持ち越さない (返らない送信が残っていても、新しい札は押せる)。
   * 番号を進めておけば、遅れて返った古い送信が、新しい送信の印を消す事も無い */
  function forgetSends() {
    S.answering = false;
    S.undoing = false;
    S.answerId = (S.answerId || 0) + 1;
    S.undoId = (S.undoId || 0) + 1;
  }

  function sendAnswer(choice, by) {
    var card = S.card;
    var mine = S.answerId = (S.answerId || 0) + 1;
    function settle() { if (S.answerId === mine) S.answering = false; }
    S.answering = true;
    var sentKey = S.key;
    var batches = takePressBatches(), sent = C.sumPressBatches(batches);
    send("/answer", { id: card.id, seq: card.view_seq, choice: choice, by: by,
                      presses: sent, press_batches: batches }, SEND_MS)
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
        lostCall();
      })
      .then(settle, settle);
  }

  /* 送信が 1 回届かなかった = 「つながらない」と出して、板の見張りをすぐ取り直す。
   * 板が生きていれば次の見張りで表示は戻る (板が止まったかどうかは見張りの側が続けて落ちた数で決める) */
  function lostCall() {
    S.offline = true;
    kick();
  }

  function doUndo(by) {
    var card = S.card;
    if (!card || S.undoing) return;
    var mine = S.undoId = (S.undoId || 0) + 1;
    function settle() { if (S.undoId === mine) S.undoing = false; }
    S.undoing = true;
    S.delta[by] = (S.delta[by] || 0) + 1;
    var batches = takePressBatches(), sent = C.sumPressBatches(batches);
    send("/undo", { id: card.id, by: by, presses: sent, press_batches: batches }, SEND_MS)
      .then(function (r) {
        if (r.status === 200) return;
        giveBack(card.id, sent, batches);
        /* 黙って答えが渡ると、取り消せたと取り違える。ほかの頁が先に取り消した時 (札は選ぶ所へ戻っている) は、
           答えは渡っていない = 「間に合わなかった」とは言わず、取り直した表示に任せる */
        if (r.status === 409 && !(r.data && r.data.state === "shown")) showNotice(L().undo_late);
        kick();
      }, function () {
        giveBack(card.id, sent, batches);
        lostCall();
      })
      .then(settle, settle);
  }

  /* ---- 入力 ---- */
  function onPointer(e) {
    S.down = !!e.buttons;             /* 窓の外で押し始めたドラッグも、動きの知らせに載る釦の状態で分かる */
    if (S.drag) {
      /* 釦を離した知らせを取りこぼしても、押していない pointer に窓を貼り付かせない */
      if (e.buttons & 1) { dragTo(e); return; }
      endDrag();
    }
    if (e.pointerType === "touch") { S.pointerType = "touch"; return; }
    S.pointerType = e.pointerType || "mouse";
    S.lastX = e.clientX;
    S.lastY = e.clientY;
    S.pointerAt = performance.now();
    S.over = dwellKeyOf(e.target);
    var onMore = !!(e.target && e.target.closest && e.target.closest("#more"));
    if (onMore !== !!S.overMore) { S.overMore = onMore; S.moreFresh = true; S.moreNext = S.pointerAt + 350; }
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
    if (e.ctrlKey || e.altKey || e.metaKey) return false;   /* Ctrl+Space (IME の切り替え) などで、光っている釦を押さない */
    var k = S.switchKey;
    if (k === "Space" || k === " ") return e.code === "Space" || e.key === " ";
    return e.code === k || e.key === k || (k.length === 1 && typeof e.key === "string" && e.key.toLowerCase() === k.toLowerCase());
  }

  function onKeyDown(e) {
    S.keyAt = performance.now();
    wakeSound();
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
      return;
    }
    var active = viewDocument.activeElement && viewDocument.activeElement.closest
      ? viewDocument.activeElement.closest("[data-key]") : null;
    if (!sw && active && (e.key === "Enter" || e.key === " ") &&
        ["reset", "phone", "gear", "pip", "theme", "copy"].indexOf(active.dataset.key) >= 0) {
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
    if (e.key === "c" || e.key === "C") { e.preventDefault(); press("copy", "key"); return; }
    if (/^(ArrowDown|ArrowUp|PageDown|PageUp)$/.test(e.key) && !$("more").hidden) {
      e.preventDefault();
      copyPage(e.key === "ArrowDown" || e.key === "PageDown" ? 1 : -1);
      return;
    }
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
    /* detail 0 の click = 鍵で起きた物か、支援技術 (読み上げの「押す」・音声操作) が起こした物。鍵の分は keydown で扱った
       ので、直前に鍵が動いていない時だけ受ける。受けた時は鍵と同じ扱い = 1 回で決まる (猶予の取り消しは残る) */
    var assist = e.detail === 0;
    if (assist && performance.now() - S.keyAt < 500) return;
    wakeSound();
    var b = e.target && e.target.closest ? e.target.closest("[data-key]") : null;
    if (!b || b.disabled) return;
    var how = assist ? "key" : S.pointerType === "touch" ? "touch" : "click";
    S.lastInput = how;
    if (!assist && S.fan && S.options.click !== "single" && (b.parentNode === $("fan") || b.closest(".fan-aux"))) {
      var at = performance.now();
      /* 表示が替わった直後の click は、選ぶ 1 回目にも数えない (press の SETTLE_MS と同じ線 3)。数えると、前の札へ向けた
         2 回押しの 2 回目が新しい札の羽根を選び、人が見てから押す click は 1 回で決まってしまう */
      if (at - S.genAt < SETTLE_MS) return;
      var step = C.armStep(S.armKey ? { key: S.armKey, at: S.armAt } : null, b.dataset.key, at, ARM_MS);
      if (!step.confirm) { armChoice(b, at); return; }
      disarm();
    }
    press(b.dataset.key, how);
  }

  /* 毎こま = 滞留・走査・表示の秒 */
  function frame(now) {
    now = performance.now();  // Use one clock even after adopting the DOM into PiP.
    var dwelling = false;
    if (S.dwellMs > 0 && S.pointerType !== "touch" && !S.overlay && inputActive()) {
      if (S.down) {
        /* 釦を押している間 (文字の選択・ドラッグ・窓の移動) は滞留を数えない。離した後も、羽根へ入り直すまで数えない
           = 押したまま羽根の上で止まっただけで答えが出ない (線 3) */
        releaseDwell();
      } else if (now - S.windowAt < WINDOW_SETTLE_MS) {
        S.firstPointer = true;        /* 窓が落ち着くまで (windowMoved)。この間に届いた pointer は、最初の 1 つに数えない */
        releaseDwell();
      } else {
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
    }
    if (S.settling && now - S.genAt >= SETTLE_MS) setSettling(false);
    if (S.armKey && now - S.armAt > ARM_MS) { disarm(); if (S.spotBtn) spotlight(S.spotBtn); }
    if (S.overMore) hoverMore(now);
    if (S.scanMs > 0) {
      var card = S.card;
      var target = null;
      /* 窓の中で pointer が動いている間は光を回さない = 視線で読み押す人の邪魔をしない。
       * pointer が止まっているか窓の外なら回る (スイッチの人・OS の鍵盤を見ている時)。 */
      var moving = dwelling || now - (S.pointerAt || -1e9) < 1500;
      if (moving) S.scanPaused = true;
      else if (S.scanPaused) { S.scanPaused = false; S.scan.restart(Math.max(now, S.genAt + scanQuiet() || 0)); }
      if (card && card.state === "deciding") {
        var u = $("undo-btn");                               /* 猶予のうち = 走査を止め、次の押下 = 取り消す */
        target = u.hidden || now - S.genAt < SETTLE_MS ? null : u;   /* 出たばかりの間は光らせない (press の SETTLE_MS) */
      } else if (card && card.state === "shown" && !S.overlay && !S.answering && inputActive() && !moving) {
        var i = S.scan.index(now, S.scanList.length);
        target = i >= 0 ? S.scanList[i] : null;
      }
      if (S.scanEl !== target) {
        if (S.scanEl) S.scanEl.classList.remove("scan");
        if (target) {
          target.classList.add("scan");
          if (!S.fan && target.scrollIntoView) target.scrollIntoView({ block: "nearest" });   /* 列が窓より長い札 */
        }
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
    if (S.fan || !(S.dwellMs > 0)) return null;            /* 視線の機能が切の時と和紙の文章は動かさない。続きは「▼ 続き」で送る */
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
    d.addEventListener("pointerdown", active(function (e) { S.pointerType = e.pointerType || "mouse"; S.down = true; }), { passive: true, capture: true });
    d.addEventListener("pointerup", active(function () { S.down = false; }), { passive: true, capture: true });
    d.addEventListener("pointercancel", active(function () { S.down = false; }), { passive: true, capture: true });
    d.documentElement.addEventListener("pointerleave", active(function () { S.over = null; S.overMore = false; S.lastX = -1; S.scrollRest = 0; }));
    d.addEventListener("pointerdown", active(startDrag));
    d.addEventListener("pointerup", active(endDrag));
    d.addEventListener("pointercancel", active(endDrag));
    d.addEventListener("lostpointercapture", active(endDrag));
    w.addEventListener("blur", active(letGo));
    w.addEventListener("focus", active(function () { releaseDwell(); S.scan.restart(Math.max(performance.now(), S.genAt + scanQuiet() || 0)); }));
    d.addEventListener("visibilitychange", active(letGo));
    w.addEventListener("resize", active(function () { windowMoved(); fitFan(); }));
    d.addEventListener("keydown", active(onKeyDown));
    d.addEventListener("keyup", active(function (e) { S.keyAt = performance.now(); delete S.held[e.code || e.key]; }));
    d.addEventListener("click", active(onClick));
    d.addEventListener("focusin", active(function (e) { spotlight(e.target); }));
  }

  function openPip() {
    if (viewWindow !== window) { viewWindow.close(); return; }
    if (!window.documentPictureInPicture || S.pipOpening) return;
    S.pipOpening = true;
    /* 前の位置を引きずると画面からはみ出す = 毎回 既定の位置に、画面に収まる大きさで開く */
    var width = Math.min(640, window.screen.availWidth - 40), height = Math.min(720, window.screen.availHeight - 60);
    window.documentPictureInPicture.requestWindow({ width: width, height: height, preferInitialWindowPlacement: true }).then(function (w) {
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
    fitWindow();
  }

  function closeOverlay() {
    S.overlay = null;
    $("overlay").hidden = true;
    S.dwell.reset();
    S.dwell.block(keyAtPointer());
    fitWindow();
  }

  /* 扇の選択肢 = 1 回目の click は選ぶだけ。同じ羽根をもう 1 回押すと決まる (ダブルクリックもこの形) */
  var ARM_MS = 1500;
  function armChoice(b, now) {
    disarm();
    S.armKey = b.dataset.key;
    S.armBtn = b;
    S.armAt = now;
    b.classList.add("armed");
    spotlight(b);
    var t = $("fan-script-1");
    if (t && !t.firstChild.textContent) {
      t.style.fontSize = "18px";
      setText(t.firstChild, L().double_hint);
    }
  }

  function disarm() {
    if (S.armBtn) S.armBtn.classList.remove("armed");
    S.armKey = null;
    S.armBtn = null;
  }

  function copyPage(dir) {
    var c = $("copy"), end = c.scrollHeight - c.clientHeight, step = Math.max(40, c.clientHeight - 36);
    c.scrollTop = dir > 0 && c.scrollTop >= end - 2 ? 0 : c.scrollTop + dir * step;
  }

  /* 和紙の文章をそのままコピーする。「変更」の行は本文の写しなので入れない */
  function copyCard() {
    if (!S.card || S.mode !== "small") return;
    var m = C.buildScreen(S.card, S.ui, S.lang), T = L(), btn = $("copy-btn");
    var lines = [m.head, m.text].filter(Boolean);
    m.blocks.forEach(function (b) { if (!b.change) lines.push((b.label ? b.label + ": " : "") + b.text); });
    if (m.question) lines.push(m.question);
    var text = lines.join("\n");
    function done(ok) {
      setText(btn, ok ? T.copied : T.copy_failed);
      setTimeout(function () { setText(btn, L().copy); }, 1500);
    }
    function byHand() {
      var area = el("textarea");
      area.value = text;
      $("surface").appendChild(area);
      area.select();
      var ok = false;
      try { ok = viewDocument.execCommand("copy"); } catch (e) { ok = false; }
      area.remove();
      done(ok);
    }
    var board = viewWindow.navigator.clipboard;
    if (board && board.writeText) board.writeText(text).then(function () { done(true); }, byHand);
    else byHand();
  }

  /* 「▼ 続き」にポインタを載せている間は 1 画面ずつ送る。最後まで来たら止まり、載せ直すと先頭へ戻る */
  function hoverMore(now) {
    if ($("more").hidden || now < S.moreNext) return;
    var c = $("copy");
    if (S.moreFresh || c.scrollTop < c.scrollHeight - c.clientHeight - 2) copyPage(1);
    S.moreFresh = false;
    S.moreNext = now + 1500;
  }

  /* 扇の背景をドラッグすると窓が動く。羽根と取り消しは押す所なので動かさない */
  function startDrag(e) {
    var t = e.target;
    if (e.button !== 0 || e.pointerType === "touch" || viewWindow !== window) return;
    if (!t || !t.closest || !t.closest("#fan-scroll, #closed") || t.closest("[data-key]")) return;
    S.drag = { x: e.screenX - window.screenX, y: e.screenY - window.screenY,
               w: window.outerWidth, h: window.outerHeight, moved: false };
    t.setPointerCapture(e.pointerId);
  }

  /* 掴んだ窓を pointer に付いて行かせる。位置は物理の画素で割り切れる所だけ (C.gridStep) = 表示倍率が 125%・150% などの
     画面で、動かすたびに窓が 1 画素ずつ大きくなるのを防ぐ。それでも育った時 (頁を拡大している時など) は、
     掴んだ時の大きさへ戻す */
  function dragTo(e) {
    var d = S.drag, step = C.gridStep(window.devicePixelRatio);
    d.moved = true;
    window.moveTo(C.snap(e.screenX - d.x, step), C.snap(e.screenY - d.y, step));
    keepSize(d, 4);
  }

  function keepSize(d, slack) {
    var w = window.outerWidth, h = window.outerHeight;
    if (!(d.w > 0 && d.h > 0 && w > 0 && h > 0)) return;      /* 寸法が読めない間は触らない */
    if (Math.abs(w - d.w) > slack || Math.abs(h - d.h) > slack) window.resizeTo(d.w, d.h);
  }

  function endDrag() {
    var d = S.drag;
    S.drag = null;
    if (d && d.moved) keepSize(d, 0);                         /* 離す時に、掴んだ時の大きさへ揃える */
  }

  /* 和紙の文章が切れている時だけ「▼ 続き」を見せる */
  function updateMore() {
    var more = $("more"), c = $("copy");
    var show = S.mode === "small" && !!S.card && S.card.state === "shown" && c.scrollHeight > c.clientHeight + 2;
    if (more.hidden === show) more.hidden = !show;
    if (show) setText(more, c.scrollTop >= c.scrollHeight - c.clientHeight - 2 ? L().more_top : L().more);
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
      addSelect(body, T.set_click, "click", [["double", T.click_double], ["single", T.click_single]], o.click);
      addSelect(body, T.set_font, "font", [["0.85", T.size_s], ["1", T.size_m], ["1.15", T.size_l], ["1.3", T.size_xl], ["1.5", T.size_xxl]], o.font);
      addSelect(body, T.set_face, "face", [["yuji", T.face_yuji], ["mincho", T.face_mincho], ["gothic", T.face_gothic]], o.face);
      addSelect(body, T.set_pos, "pos", [["keep", T.pos_keep], ["br", T.pos_br], ["bl", T.pos_bl], ["tr", T.pos_tr], ["tl", T.pos_tl]], o.pos);
      addSelect(body, T.set_clear, "clear", [["off", T.off], ["on", T.on]], o.clear);
      addSelect(body, T.set_theme, "theme", [["auto", T.auto], ["light", T.light], ["dark", T.dark], ["contrast", T.contrast]], o.theme);
      addSelect(body, T.set_lang, "lang", [["auto", T.auto], ["ja", "日本語"], ["en", "English"]], o.lang);
      addSelect(body, T.set_sound, "sound", [["off", T.off], ["on", T.on]], S.sound ? "on" : "off");
      addSelect(body, T.set_mode, "mode", [["small", T.small], ["large", T.large]], o.mode);
      addSelect(body, T.set_desc, "desc", [["on", T.on], ["off", T.off]], o.desc);
      addInput(body, T.set_scale, "scale", o.scale, .75, 2);
      addSelect(body, T.set_dwell, "dwell",
                [["0", T.off], ["0.8", "0.8"], ["1", "1.0"], ["1.2", "1.2"], ["1.5", "1.5"], ["2", "2.0"]],
                String(S.dwellMs / 1000));
      addSelect(body, T.set_trail, "trail", [["off", T.off], ["on", T.on]], o.trail);
      addSelect(body, T.set_scan, "scan",
                [["off", T.off], ["1", "1.0"], ["1.5", "1.5"], ["2", "2.0"], ["3", "3.0"]],
                S.scanMs ? String(S.scanMs / 1000) : "off");
      addInput(body, T.set_key, "key", o.key);
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
    if (name === "pos") placeWindow();
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
    viewDocument.documentElement.dataset.face = S.options.face;
    viewDocument.documentElement.style.zoom = S.options.scale === 1 ? "" : String(S.options.scale);
    setFont();
    viewDocument.title = C.windowTitle(S.mode, location.port);
    $("stats-reset").textContent = T.reset;
    $("phone-btn").textContent = T.phone;
    $("gear-btn").textContent = T.settings;
    $("panel-close").textContent = T.close;
    setText($("copy-btn"), T.copy);
    $("gear-btn").textContent = S.mode === "small" ? "⚙" : T.settings;
    $("gear-btn").setAttribute("aria-label", T.settings);
    $("theme-btn").textContent = isDark() ? "☀" : "☾";
    $("theme-btn").setAttribute("aria-label", isDark() ? T.to_light : T.to_dark);
    $("theme-btn").title = isDark() ? T.to_light : T.to_dark;
    setPinButton();
    $("trail").hidden = S.options.trail !== "on";
  }

  /* 固定のボタン = 窓の応答 (windowCall) が来るたびに直すのはここだけ */
  function setPinButton() {
    var T = L();
    $("pip-btn").hidden = S.mode !== "small" || !(window.documentPictureInPicture || S.windowOk);
    $("pip-btn").textContent = viewWindow !== window ? T.pip_back : S.pinned ? T.pip_off : T.pip;
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
    if (S.mode === "small") { windowCall({}); placeWindow(); }
  }

  init();
})();
