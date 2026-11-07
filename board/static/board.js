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
    genAt: -1e9,                      /* 表示の世代が進んだ時刻。札の来る前に窓の焦点で押せない間の印が付いても、印を外せるように初めから数にする */
    btns: {}, optionKeys: [], scanList: [], scanEl: null, fillEl: null,
    delta: C.zeroPresses(), answering: false, undoing: false, sentKey: null,
    pressLedger: C.newPressLedger(window.crypto.getRandomValues(new Uint32Array(4)).join("-")),
    lastX: -1, lastY: -1, over: null, pointerType: "mouse", lastInput: "",
    held: {}, deadlineAt: null, undoAt: null,
    lightUntil: 0, lightKey: "", lastSeen: "", endText: "", endUntil: 0,
    notice: "", noticeUntil: 0, noticeKind: null, problem: "", offline: false,
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
    if (S.retryTimer) { clearTimeout(S.retryTimer); S.retryTimer = null; }   /* 待っている取り直しと並走しない (見張りは常に 1 本) */
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
      S.retryTimer = setTimeout(poll, S.retry);
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
    var undone = false;
    /* 鍵の焦点の決まり (§4.2): 焦点がどこかに来た事を覚えておき (S.focusSeen)、その焦点が、人の自分の押し (答える・札の中を
       進める・設定を閉じる) で使われないまま消えた後は、次の札の先頭 (許可) へ焦点を置かない (bumpGen) = 前の札へ向けた
       Enter が、次の札の許可に当たらない (線 3)。
       ここで数えるのは「この頁の人の答えが渡って、札が終わった」時だけ = その答えを送った時に在った焦点 (S.sends) は、
       その答えで使われた。どの答えが渡ったかは、板が「直前に終わった札」に添える名札 (answered_by = 送信ごとの名札) で
       読む = 頁の側で推し量らない (送った答えが通るとは限らない・板の返りと写しの順は決まっていない・同じ札へ送り直した
       2 回目と、先に通っていた 1 回目を取り違えない)。猶予に入っただけでは数えない = 取り消された答え・ほかの頁が答え直した
       札は、最初から数に入らない。押した後に来た焦点 (置き直した焦点・取り消しへ置いた焦点) は、使われていない
       (focusGen が進んでいる) */
    var gone = snap.last, sent = prev && gone && gone.id === prev.id && S.sends ? S.sends[gone.answered_by] : null;
    if (sent && sent.usable && sent.gen === S.focusGen) S.focusSeen = false;
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
    } else if (prev && prev.id === card.id && card.state === "shown" &&
               (prev.state === "deciding" || prev.view_seq !== card.view_seq)) {
      /* 取り消した = 確かめの画面か頭へ。ほかの頁が取り消した時は、途中 (deciding) の写しを受けないまま、同じ札の選ぶ画面へ
         戻る事がある (表示の seq だけが進む) = それも取り消しとして扱う。この描き直しでは、鍵の焦点を同じ釦へ付け直さない
         (止める・拒否を送って取り消された人の次の Enter が、前に焦点を置いていた「次から訊かない」に当たらない・線 3) */
      S.ui = C.uiAfterUndo(card, S.ui);
      S.drawnScreen = null;
      undone = true;
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
    refreshView(undone);                         /* 取り消して選ぶ画面へ戻った = 焦点を先頭 (許可) へ置かない */
  }

  /* leaveFocus = 替わった後に、鍵の焦点を先頭へ置かない (取り消して戻った時・窓を移った時) */
  function refreshView(leaveFocus) {
    var k = C.viewKey(S.card, S.ui, S.lang);
    if (k !== S.key) {
      S.ui.marks = [];
      S.key = k;
      render();
      /* 取り消しの枠と「▼ 続き」を先に出し入れする = この後に消える物を pointer の下 (滞留の守り) と焦点の在処に数えない */
      updateSide(performance.now());
      bumpGen(true, leaveFocus);
      return;
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
    /* 鍵の焦点を同じ釦へ付け直すのは、同じ画面の描き直し (印を付けただけ・配色や設定・言葉の変更・窓の移り) だけ。
       札が替わった・札の中で次の画面へ進んだ時は付け直さない = 前の画面と同じ位置の釦 (次の札の「次から訊かない」・
       次の設問の同じ番号) へ焦点を持ち越さない。付け直さなかった焦点は bumpGen の決まりに任せる */
    var screen = card ? [card.id, S.ui.step, S.ui.sub || ""].join("|") : "";
    var sameScreen = screen === S.drawnScreen;
    S.drawnScreen = screen;
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
    /* 札が替わった・札の中で次の画面へ進んだ = 送りの枠 (小型の和紙 #copy・大きな板の #card・幅の狭い大きな板では頁そのもの) を
       頭へ戻す = 前の札の送り位置のまま描かない (替わった札の頭 = 何の確認かが隠れたまま羽根が押せる)。取り消しで同じ画面へ
       戻った時と、印を付けただけ・配色や設定の描き直しは位置を保つ (読んでいた所へ戻る) = 鍵は S.drawnScreen と別に持つ
       (取り消しの枝は S.drawnScreen を消すので、それを使うと取り消しでも頭へ戻る)。中身を書き込んだ後に戻す */
    if (screen !== S.scrollScreen) {
      S.scrollScreen = screen;
      $("copy").scrollTop = 0;
      $("card").scrollTop = 0;
      var se = viewDocument.scrollingElement;
      if (se) se.scrollTop = 0;
    }
    renderFan(m);
    /* 光の印と滞留の縁を外してから手放す = 作り直す釦は木ごと消えるが、常設の釦 (「▼ 続き」・取り消す) は残る。null にする
       だけだと、外す側 (bumpGen・frame) が空振りし、次の札で動かない偽の光と本物の光が 2 つ点く (光が「▼ 続き」に居る時に
       札が替わると、それを待っていた人の 1 押しが、本物の光 = 先頭の許可に当たる)・次の猶予の「取り消す」が満ちかけて見える */
    if (S.scanEl) S.scanEl.classList.remove("scan");
    S.scanEl = null;
    setFill(null, 0);
    if (sameScreen && focusedKey && S.btns[focusedKey] && !S.btns[focusedKey].disabled) {
      focusOn(S.btns[focusedKey]);
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

  /* 頁や列が送られた時も同じ = 置いたままの pointer の下の物が入れ替わる (走査の光が窓の外の釦を見える所へ送る・ホイール・
     見つめて本文を送る)。落ち着くまで滞留を数えず、その後に pointer の下に居た釦は入り直すまで数えない (線 3)。
     pointer の位置は捨てない (見つめて送る動きは、止まった pointer の位置で続く) */
  function scrolled() {
    S.windowAt = performance.now();
    S.over = null;
    S.firstPointer = true;
    releaseDwell();
  }

  /* scroll の知らせ (capture = 要素の送りは泡立たない)。守るのは、文書そのものの送りと、押せる的 (滞留の釦) を含む列の送りだけ。
     押せる的を含まない枠 (本文・和紙) の送りは素通し = 本文から釦へ視線を移す途中で本文が少し送られても、次に見た釦は
     入り直さずに押せる (押せる物は動いていない) */
  function onScroll(e) {
    var box = e && e.target;
    if (box && box.nodeType === 1 && box.querySelectorAll) {
      var pressable = Array.prototype.some.call(box.querySelectorAll("[data-dwell]"), function (b) { return !b.hidden && !b.disabled; });
      if (!pressable) return;
    }
    scrolled();
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
    }, function () {
      S.shapeBusy = false;            /* 頼みが例外で終わっても、次の形を送れる (待ちの印を残さない) */
    });
  }

  /* 窓の位置 = 画面の 4 隅へ動かす (app の窓だけ動く。普通のタブでは何も起きない) */
  function placeWindow() {
    var pos = S.options.pos, s = window.screen;
    if (pos === "keep" || viewWindow !== window) return;
    var x = pos.charAt(1) === "r" ? s.availLeft + s.availWidth - window.outerWidth : s.availLeft;
    var y = pos.charAt(0) === "b" ? s.availTop + s.availHeight - window.outerHeight : s.availTop;
    window.moveTo(x, y);
    windowMoved();                    /* 位置が変わった = 置いたままの pointer の下の物が入れ替わる (大きさの変化と同じ扱い) */
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
  /* settle = 押しを数えない間 (press の SETTLE_MS) と走査の静かな 1 こまを置く。置くのは、板から来た替わり (新しい札・状態の
     変化・取り消しで戻った・設定の変更) と、位置や焦点で行き先が決まる押し (焦点の上の Enter / Space・click・触る・支援技術の
     押し・スイッチ) で札の中を進めた時 = ばたつきや押し直しの 2 打目が、進んだ先 (戻った画面の「許可」・見ていない次の設問・
     確かめの画面の「送る」) に当たらない (線 3)。数字の鍵 (行き先を名指しする押し) と滞留で進めた時は置かない。
     leaveFocus = 鍵の焦点を先頭へ置かない (取り消して戻った時・窓を移った時) */
  function bumpGen(settle, leaveFocus) {
    var now = performance.now();
    S.gen += 1;
    if (settle) {
      S.genAt = now;
      setSettling(true);
    }
    S.over = keyAtPointer();
    if (S.lastX < 0) S.firstPointer = true;
    S.overMore = false;               /* 「▼ 続き」も同じ = 動かさないままの pointer で、新しい札の和紙を送らない */
    releaseDwell();
    S.scan.restart(settle ? now + scanQuiet() : now);   /* 間を置いた後は、1 こまぶん何も光らせない */
    if (S.scanEl) { S.scanEl.classList.remove("scan"); S.scanEl = null; }
    if (!leaveFocus && keyFocusWanted()) {
      /* 鍵で使う人のために先頭の釦へ焦点を置く = 焦点がどこにも無い所へ札 (画面) が出た時と、人が自分の押しで札に答えた・
         札の中を進めた時。人が自分で置いた焦点 (配色・設定・コピーなどの釦) は奪わない = 配色の釦を鍵で 2 回押した
         2 回目が、焦点の移った先頭の羽根 (許可) に当たらない (線 3)。
         前に来た焦点が、人の押しで使われないまま消えている時 (S.focusSeen) は置かない = 頁が消した焦点 (札が替わった・
         取り消しや「▼ 続き」や上の釦が隠れた・釦が押せなくなった) の行き先を、頁が許可へ変えない。人が自分で答えるか
         札の中を進めると (focusUsed)、また置く */
      var first = S.fan ? S.scanList[0] : viewDocument.querySelector("#opts .btn:not(:disabled)");
      if (first && focusNowhere() && !S.focusSeen) focusOn(first);
    }
  }

  /* 鍵の焦点を頁が置く場面 = 押せる札があり、鍵で使っていて (走査は切)、設定の板が閉じている */
  function keyFocusWanted() {
    return !!S.card && S.card.state === "shown" && S.lastInput === "key" && !S.overlay && S.scanMs <= 0;
  }

  /* 頁が自分で焦点を置く所は、全部ここを通す。窓が背面に居る間は、置いても焦点の知らせ (focusin) が来ない (窓が前面に
     戻った時に来る) = 置いた事を、知らせを待たずに覚える */
  function focusOn(el) {
    el.focus({ preventScroll: true });
    if (viewDocument.activeElement === el) focusCame(el);
  }

  /* 鍵の焦点がどこかに来た。focusGen = 焦点の行き先 (釦) が替わった数 = 答えを押した後に、別の釦へ置き直した焦点を、押した
     時の焦点と見分ける。同じ釦への付け直し (描き直しで作り直した同じ鍵の釦・PiP の窓への移し・窓へ戻った時のブラウザの
     再通知) では進めない = 押した時の焦点のまま */
  function focusCame(el) {
    S.focusSeen = true;
    var k = el && el.dataset && el.dataset.key ? "k:" + el.dataset.key : el && el.id ? "i:" + el.id : null;
    if (k === null || k !== S.focusKey) S.focusGen = (S.focusGen || 0) + 1;
    S.focusKey = k;
  }

  /* 鍵の焦点がどこにも無いか。入れ物を隠した釦と押せなくした釦は、ブラウザが焦点を外すまで activeElement に残るので、
     在るとは数えない */
  function focusNowhere() {
    var a = viewDocument.activeElement;
    return !a || a === viewDocument.body || a === viewDocument.documentElement ||
      !!(viewDocument.contains && !viewDocument.contains(a)) || !!a.disabled || !!(a.closest && a.closest("[hidden]"));
  }

  /* 鍵の焦点が、札の釦の区域 (選択肢・止・戻・扇) の中に在るか */
  function heldOnCard() {
    var a = viewDocument.activeElement;
    return !!(a && a !== viewDocument.body && a.closest && a.closest("#opts, #fixed-zone, #term-zone, #fan"));
  }

  /* 人が自分の押しで札に答えた・札の中を進めた = 札の釦に在った焦点は、その押しで使われた (この後に釦が消えるのは、人が
     進めた結果)。焦点がどこにも無い時も同じ (消えた焦点の事は、この押しで済んだ)。「▼ 続き」や上の釦に在る生きた焦点は
     使われていない = それが後で隠れたら、次の札の先頭へは置かない */
  function focusUsed() {
    if (focusNowhere() || heldOnCard()) S.focusSeen = false;
  }

  /* 板から札が替わった後、走査が最初の光を出すまでの間 = 走査の 1 こまぶん (0.4〜1.5 秒)。押すのが遅い人の、前の札へ向けた
     1 押しが、新しい札の先頭 (許可) に当たらない (光っていない物は押せない) */
  function scanQuiet() {
    return Math.max(SETTLE_MS, Math.min(S.scanMs || 0, 1500));
  }

  /* 押しを数えない間は、頁に印を付ける (body.settling)。見た目は変えない = 試験と外の道具が「もう押せる」を読める。
     印が付く間 = 表示が替わった直後 (どの押しも数えない) と、札の中を進めた直後 (焦点や位置で行き先が決まる押しを数えない。
     名指しの鍵は数える) */
  function setSettling(on) {
    var b = viewDocument.body;
    /* 値が同じでも、今の文書の印は揃える (印を付けた後に PiP の窓へ移ると、移った先の文書には印が無い) */
    if (b && b.classList) b.classList.toggle("settling", on);
    S.settling = on;
    /* 印を付けた後に頁が PiP の窓へ移った (戻った) 時 = 元の文書の印も消す (残ると、外の道具が「まだ押せない」と読み続ける) */
    var home = homeDocument && homeDocument.body;
    if (!on && home && home !== b && home.classList) home.classList.remove("settling");
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
    S.noticeKind = null;              /* 別の知らせ = 数字の案内の印を外す (disarm では消さない) */
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
  /* 取り消しは、猶予の短い板 (--undo-ms が 0.8 秒より短い) では、数えない間を板の猶予の半分までにする (0.4 秒のままだと、
     猶予 0.4 秒以下の板では取り消しが 1 度も押せない)。数えない間は板の猶予 (undo_ms) から、猶予の終わりは写しを受けた時の
     残りから測る = 猶予の半分を過ぎてから写しが届いた時は、押せる間が残らない事がある */
  function settleFor(key) {
    var undoMs = key === "undo" && S.snap ? S.snap.undo_ms : 0;
    return undoMs > 0 ? Math.min(SETTLE_MS, undoMs / 2) : SETTLE_MS;
  }
  /* named = 行き先を名指しする押し (数字の鍵)。札の中を進めても、続けて打つ次の押しを捨てない */
  function press(key, by, named) {
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
       滞留は「入り直すまで数えない」(bumpGen の releaseDwell) と、短い滞留の数え始めを遅らせる frame の枝が別に守る
       (ここで滞留の押しを捨てると、捨てた釦は入り直すまで数えなくなり、見続けている人が押せなくなる) */
    if (by !== "dwell" && performance.now() - S.genAt < settleFor(key)) return;
    /* 名指しの押し (数字の鍵) で札の中を進めた直後 = 続く名指しの押しは数えるが、焦点や位置で行き先が決まる押し (癖の Enter・
       ダブルクリック) は数えない (見ていない次の設問の先頭に当たらない)。取り消しは別 (猶予の内の、自分の間を持つ) */
    if (by !== "dwell" && !named && key !== "undo" && performance.now() - (S.stepAt || -1e9) < SETTLE_MS) return;
    /* 窓が鍵の焦点を得た直後の鍵とスイッチの押しは数えない (線 3) = 別の窓へ向けて打った鍵や、焦点を得た瞬間のスイッチが、
       許可に当たらない。ここは名指しの鍵 (数字) も数えない (数字が届いた先が、打った人の見ていた窓とは限らない)。
       click と触る押しは数える (焦点の無い窓を click した最初の押しを捨てない)。取り消しも数える (安全の側) */
    if ((by === "key" || by === "switch") && key !== "undo" && performance.now() - (S.focusAt || -1e9) < SETTLE_MS) return;
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
    var moved = r.gen || k !== S.key;                      /* 印を付けただけ = 世代は進めない */
    S.key = k;
    if (moved) focusUsed();                                /* 自分の押しで札の中を進めた = 札の釦に在った焦点は使われた */
    render();
    updateSide(performance.now());
    if (!moved) return;
    S.stepAt = performance.now();                          /* 札の中を進めた時刻 (名指しで進めた直後の、焦点任せの押しを数えない) */
    setSettling(true);                                     /* その間も頁の印を付ける (外の道具が「もう押せる」を読み違えない) */
    /* 「前の画面へ」で戻った = 鍵の焦点は先頭 (許可) でなく、来た元の「拒否 …」へ (押し直しが許可に当たらない) */
    if (key === "back" && keyFocusWanted() && S.btns.deny && !S.btns.deny.disabled) focusOn(S.btns.deny);
    /* 札の中で人が画面を進めた (拒否 → 理由・前の画面へ・次の設問・確かめの画面)。位置や焦点で行き先が決まる押しの時は、
       板から替わった時と同じ間を置く = ばたつき・押し直し・ダブルクリックの 2 打目が、進んだ先に当たらない (線 3)。
       数字の鍵 (名指し) と滞留 (入り直すまで数えない守りが別に在る) の時は置かない */
    bumpGen(by !== "dwell" && !named);
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
    S.sends = {};                                /* 前の札への送信の控え (焦点の照合用) も捨てる */
    S.undoing = false;
    S.answerId = (S.answerId || 0) + 1;
    S.undoId = (S.undoId || 0) + 1;
  }

  function sendAnswer(choice, by) {
    var card = S.card;
    var mine = S.answerId = (S.answerId || 0) + 1;
    function settle() { if (S.answerId === mine) S.answering = false; }
    S.answering = true;
    /* 答えの名札 (頁ごとの乱数 + 送信の番号) と、押した時の焦点 = この答えが渡った時に「使われた」事にできる焦点 (札の釦の
       上か、どこにも無い時だけ)。gen = その時までに来た焦点の数 (この後に焦点が来たら、それは別の焦点 = この答えでは使われて
       いない)。送信ごとに覚える = 返りを失った 1 回目が板に通っていて、2 回目を送り直した時も、渡った方の控えで照合する */
    var tag = S.pressLedger.source + ":" + (S.sendSeq = (S.sendSeq || 0) + 1);
    S.sends = S.sends || {};
    S.sends[tag] = { gen: S.focusGen, usable: focusNowhere() || heldOnCard() };
    var sentKey = S.key;
    var batches = takePressBatches(), sent = C.sumPressBatches(batches);
    /* tag = この答えの名札。板は、渡った答えの名札を「直前に終わった札」に添える = 頁は「自分のどの答えが渡った」を、
       推し量らずに読める (apply) */
    send("/answer", { id: card.id, seq: card.view_seq, choice: choice, by: by,
                      presses: sent, press_batches: batches, tag: tag }, SEND_MS)
      .then(function (r) {
        if (r.status === 200) {
          S.sentKey = sentKey;
          return;
        }
        giveBack(card.id, sent, batches);
        if (r.status === 401) {
          S.problem = L().bad_token;
        } else {
          /* 「画面が古くなっていました。もう一度選んでください」は、選び直せば通る時だけ (409 の stale・400・分からない返り)。
             期限と同時の押し (expired)・終わった札 (ended)・頭に居ない札 (not_current)・ほかの頁が先に答えた札 (not_shown) では
             言わず、取り直した表示と終わりの文に任せる (doUndo と同じ形・次の札の上に前の札への文を重ねない) */
          var err = r.status === 409 && r.data ? r.data.error : null;
          if (!(r.status === 409 && err && err !== "stale")) showNotice(L().stale);
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
        /* 「間に合わなかった」と知らせるのは 2 つの時だけ (言い方は分ける)。答えが実際に渡った (板が添える終わり方が answered か
           released) =「答えは渡りました」。同じ札がまだ頭に居て、猶予が切れて渡している途中 (deciding) =「答えを渡している所です」
           (まだ渡っていない答えを「渡りました」と読ませない・黙ったまま、取り消せたと取り違えさせない)。ほかの頁が先に取り消した
           (shown)・時間切れ・接続の終了・終わり方が分からない時は言わず、取り直した表示と終わりの文に任せる */
        var end = r.data && r.data.end, state = r.data && r.data.state;
        if (r.status === 409 && (end === "answered" || end === "released")) showNotice(L().undo_late);
        else if (r.status === 409 && state === "deciding") showNotice(L().undo_going);
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
      /* 板の中の選択や入力の Enter / Space には触らない。焦点が「閉じる」に在る時だけ、Enter / Space で閉じる
         (ブラウザが鍵から起こす click は、直前に鍵が動いたので onClick が数えない) */
      var onClose = (e.key === "Enter" || e.key === " ") && viewDocument.activeElement === $("panel-close");
      if (e.key === "Escape" || onClose) { e.preventDefault(); closeOverlay(); }
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
    if (e.key === "Escape") { e.preventDefault(); press("fixed", "key", true); return; }   /* Esc = 止める側を名指しする鍵 */
    if (e.key === "c" || e.key === "C") { e.preventDefault(); press("copy", "key"); return; }
    if (/^(ArrowDown|ArrowUp|PageDown|PageUp)$/.test(e.key) && !$("more").hidden) {
      e.preventDefault();
      copyPage(e.key === "ArrowDown" || e.key === "PageDown" ? 1 : -1);
      return;
    }
    if (e.key === "0") { e.preventDefault(); press("terminal", "key", true); return; }     /* 0 = 「端末で答える」を名指しする鍵 */
    if (S.fan && /^Arrow(Left|Right|Up|Down)$/.test(e.key)) {
      e.preventDefault();
      var at = S.fanVisual.indexOf(active), n = S.fanVisual.length;
      var dir = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
      if (n) focusOn(S.fanVisual[at < 0 ? 1 : (at + dir + n) % n]);
      return;
    }
    if (/^[1-6]$/.test(e.key)) {
      var k = S.optionKeys[parseInt(e.key, 10) - 1];
      /* 数字 = 行き先を名指しする押し。「次から訊かない」(恒久の許可) だけは、同じ数字を 1.5 秒の内にもう 1 回押して決める
         (1 回目は選ぶだけ・札 #216 B) = 扇に鍵の焦点が在るまま端末を見て打った数字が、扇の番号で恒久の規則を書かない
         (端末の選択肢の番号と扇の番号は揃わない)。今回の許可・拒否・止める・端末で答えるは 1 回のまま */
      if (k) { e.preventDefault(); if (k.indexOf("sugg:") !== 0 || armTwice(k, "digit")) press(k, "key", true); }
      return;
    }
    if ((e.key === "Enter" || e.key === " ") && active && active.dataset.dwell) {
      e.preventDefault();
      /* 焦点の上の Enter / Space も、「次から訊かない」だけは同じ入り方の 2 回で決める (数字と同じ・1 回目は選ぶだけ) =
         扇に鍵の焦点を持たせたまま、端末の癖で打った ↓↓Enter (端末では「No」・扇では「次から訊かない」に当たる) が、恒久の
         規則を書かない (最終デバッグ 1 巡目 #19)。大きな板で Tab から置いた焦点も同じ。今回の許可・拒否・止・戻は 1 回のまま */
      var fk = active.dataset.key;
      if (fk.indexOf("sugg:") !== 0 || armTwice(fk, "key")) press(fk, "key");
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
         2 回押しの 2 回目が新しい札の羽根を選び、人が見てから押す click は 1 回で決まってしまう。名指しの鍵や滞留で
         札の中を進めた直後も同じ (0.4 秒をまたぐ 2 回の click が、見ていない画面の羽根を決めない) */
      if (at - S.genAt < SETTLE_MS || at - (S.stepAt || -1e9) < SETTLE_MS) return;
      /* 1 回目と 2 回目は同じ入り方 (click 同士) の時だけ決める = 数字で選んだ羽根を click 1 回で、click で選んだ
         羽根を迷い込んだ数字 1 つで決めない (外の目の 6 巡目・恒久の許可の 2 回押しの穴) */
      var step = C.armStep(S.armKey && S.armBy === "click" ? { key: S.armKey, at: S.armAt } : null, b.dataset.key, at, ARM_MS);
      if (!step.confirm) { armChoice(b, at, "click"); return; }
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
      } else if (now - S.genAt < SETTLE_MS - S.dwellMs) {
        /* 0.4 秒より短い滞留 (URL や --set で入れた時) = 板から表示が替わった直後は、数え始めを遅らせる。pointer の揺れが
           入り直しに数えられても、滞留の押しは替わって 0.4 秒より後になる (鍵・スイッチ・click と同じ線 3)。
           数えないだけで、守り (入り直すまで数えない釦) は消さない。0.4 秒以上の滞留では、この枝は通らない */
        setFill(null, 0);
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
    if (S.settling && now - S.genAt >= SETTLE_MS && now - (S.stepAt || -1e9) >= SETTLE_MS &&
        now - (S.focusAt || -1e9) >= SETTLE_MS) setSettling(false);
    if (S.armKey && now - S.armAt > ARM_MS) { disarm(); if (S.spotBtn) spotlight(S.spotBtn); }
    if (S.overMore) hoverMore(now);
    if (S.scanMs > 0) {
      var card = S.card;
      var target = null;
      /* 窓の中で pointer が動いている間は光を回さない = 視線で読み押す人の邪魔をしない。
       * pointer が止まっているか窓の外なら回る (スイッチの人・OS の鍵盤を見ている時)。 */
      var moving = dwelling || now - (S.pointerAt || -1e9) < 1500;
      if (moving) S.scanPaused = true;
      /* 止まっていた走査が戻る時も、替わった後と焦点を得た後の静かな間は短くしない (外の目の 6 巡目 = 焦点の 0.5 秒後に
         pointer の止まりで戻り、許可が早く光った) */
      else if (S.scanPaused) { S.scanPaused = false; S.scan.restart(Math.max(now, S.genAt + scanQuiet(), (S.focusAt || -1e9) + scanQuiet())); }
      if (card && card.state === "deciding") {
        var u = $("undo-btn");                               /* 猶予のうち = 走査を止め、次の押下 = 取り消す */
        target = u.hidden || now - S.genAt < settleFor("undo") ? null : u;   /* 出たばかりの間は光らせない = 押せる時から光る (press と同じ間) */
      } else if (card && card.state === "shown" && !S.overlay && !S.answering && inputActive() && !moving) {
        var i = S.scan.index(now, S.scanList.length);
        target = i >= 0 ? S.scanList[i] : null;
      }
      if (S.scanEl !== target) {
        if (S.scanEl) S.scanEl.classList.remove("scan");
        if (target) {
          target.classList.add("scan");
          if (!S.fan && target.scrollIntoView) {            /* 列が窓より長い札 = 光を見える所へ送る */
            var was = target.getBoundingClientRect();
            target.scrollIntoView({ block: "nearest" });
            var to = target.getBoundingClientRect();
            /* 実際に送った時だけ (知らせを待たずに) 守る = 送られて pointer の下に来た釦を、滞留で押さない。
               窓に収まる列で光が進むだけの時は守らない (見ている釦の滞留を光のたびに捨てない) */
            if (to.top !== was.top || to.left !== was.left) scrolled();
          }
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

  /* 窓が鍵の焦点を得た (別の窓を閉じた時に OS が扇へ焦点を移す・人が扇を click する) = 表示が替わった時と同じ守りを置く。
     走査は頭 (許可) からすぐには光らせず、静かな 1 こまの後に回す (光っていた「止」へ向けたスイッチの 1 押しが、跳んだ先の
     許可に当たらない)。鍵とスイッチの押しは press が 0.4 秒数えない (別の窓へ向けて打った鍵が扇に届いても、許可に当たら
     ない)。その間は頁に印を付ける (外の道具と試験が「もう押せる」を読み違えない)。焦点の出入りの瞬間の古い滞留は捨てる */
  function windowFocused() {
    var now = performance.now();
    releaseDwell();
    S.focusAt = now;
    S.scan.restart(now + scanQuiet());
    setSettling(true);
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
    /* 押した・離したその場で滞留を解く (こま単位の見張りだけだと、1 こまの内に押して離す速い click や、押したまま羽根へ来て
       同じこまで離した時に「入り直すまで数えない」が掛からない) */
    d.addEventListener("pointerdown", active(function (e) { S.pointerType = e.pointerType || "mouse"; S.down = true; releaseDwell(); }), { passive: true, capture: true });
    d.addEventListener("pointerup", active(function () { S.down = false; releaseDwell(); }), { passive: true, capture: true });
    d.addEventListener("pointercancel", active(function () { S.down = false; releaseDwell(); }), { passive: true, capture: true });
    d.addEventListener("scroll", active(onScroll), { passive: true, capture: true });
    d.documentElement.addEventListener("pointerleave", active(function () { S.over = null; S.overMore = false; S.lastX = -1; S.scrollRest = 0; }));
    d.addEventListener("pointerdown", active(startDrag));
    d.addEventListener("pointerup", active(endDrag));
    d.addEventListener("pointercancel", active(endDrag));
    d.addEventListener("lostpointercapture", active(endDrag));
    w.addEventListener("blur", active(letGo));
    w.addEventListener("focus", active(windowFocused));
    d.addEventListener("visibilitychange", active(letGo));
    w.addEventListener("resize", active(function () { windowMoved(); fitFan(); }));
    d.addEventListener("keydown", active(onKeyDown));
    d.addEventListener("keyup", active(function (e) { S.keyAt = performance.now(); delete S.held[e.code || e.key]; }));
    d.addEventListener("click", active(onClick));
    /* 鍵の焦点がどこかに来た (人が置いても、頁が置いても) = 覚えておく。使われないまま消えたら、次の札の先頭へ置かない (bumpGen) */
    d.addEventListener("focusin", active(function (e) { focusCame(e.target); spotlight(e.target); }));
  }

  /* 頁を別の窓へ付け替えると、焦点は外れる。付け替える前に焦点の在った釦を覚え、付け替えた後に同じ釦へ戻す (鍵の焦点を
     先頭の「許可」へ移さない)。戻せない時は、どこにも置かない (refreshView(true))。
     戻すのは鍵で使っている時だけ = マウスで「常に手前」を押した時は戻さない (焦点が釦に残ると、上の釦の帯が出たままになる) */
  function heldIn(surface) {
    if (S.lastInput !== "key") return null;
    var a = viewDocument.activeElement;
    return a && a !== viewDocument.body && surface.contains(a) ? a : null;
  }

  /* 描き直しの前と後の 2 回呼ぶ。前 = 描き直しが同じ画面の同じ釦へ付け直せるように。後 = 描き直しが付け替えた物 (扇の
     取り消しの枠) に在った焦点を戻す (作り直された釦は、もう文書に無いので何もしない) */
  function keepFocus(held) {
    if (held && viewDocument.contains(held) && !held.disabled && !(held.closest && held.closest("[hidden]"))) {
      focusOn(held);
    }
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
        var held = heldIn(surface);
        homeDocument.body.appendChild(surface);
        viewWindow = window; viewDocument = homeDocument;
        S.lastX = -1; S.over = null;
        setChrome(); keepFocus(held); S.key = ""; refreshView(true); keepFocus(held); restartFrames();
      }, { once: true });
      var link = w.document.createElement("link");
      link.rel = "stylesheet"; link.href = location.origin + "/static/board.css";
      w.document.head.appendChild(link);
      var held = heldIn(surface);
      w.document.body.appendChild(surface);
      viewWindow = w; viewDocument = w.document;
      bindInputs(w);
      S.lastX = -1; S.over = null;
      setChrome(); keepFocus(held); S.key = ""; refreshView(true); keepFocus(held); restartFrames();
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
    focusOn($("panel-close"));
    S.dwell.reset();
    setFill(null, 0);
    fitWindow();
  }

  function closeOverlay() {
    /* 設定の板を閉じるのは人の操作 = 板の中に在る焦点 (「閉じる」・選択) は、その操作で使われた (次の札の先頭へ置いてよい)。
       焦点がどこにも無い時は何もしない (板の外で消えた焦点の記録まで、閉じる操作で済ませない) */
    var a = viewDocument.activeElement;
    if (a && a.closest && a.closest("#overlay")) S.focusSeen = false;
    S.overlay = null;
    $("overlay").hidden = true;
    /* 板の裏で置いたままの pointer の下に居た釦は、入り直すまで数えない (板を開いている間に札が替わっていても同じ)。
       守る釦と S.over を揃える (揃えないと、次のこまの滞留の見張りが守りを解いてしまう)。閉じた後に最初に届いた pointer の
       下の釦も同じ = 板が開いていた間の位置と、その下の物は信じない */
    S.over = keyAtPointer();
    S.firstPointer = true;
    releaseDwell();
    /* 閉じた直後は「表示が替わった直後」と同じ静かな間を置く (押しを数えない 0.4 秒 + 走査は間を置いて頭から) = 「閉じる」の
       Space / Enter の 2 打目 (ばたつき) が、戻った走査の光や焦点の羽根 (許可) に届かない (外の目の 8 巡目 = 走査の板で、閉じた
       次のこまの 2 打目が allow_once を送った)。焦点は動かさない (人が置いた焦点を奪わない) */
    bumpGen(true, true);
    fitWindow();
  }

  /* 扇の選択肢 = 1 回目の click は選ぶだけ。同じ羽根をもう 1 回押すと決まる (ダブルクリックもこの形) */
  var ARM_MS = 1500;
  function armChoice(b, now, by) {
    disarm();
    S.armKey = b.dataset.key;
    S.armBtn = b;
    S.armAt = now;
    S.armBy = by;                     /* 選んだ入り方 (click / digit / key) = 2 回目は同じ入り方の時だけ決める */
    b.classList.add("armed");
    spotlight(b);
    var t = $("fan-script-1");
    if (t && !t.firstChild.textContent) {
      t.style.fontSize = "18px";
      setText(t.firstChild, L().double_hint);
    }
  }

  /* 数字か、焦点の上の Enter / Space で「次から訊かない」を押した = 1 回目は選ぶだけ (羽根・釦に選んだ印・案内の文)、
     同じ入り方の 2 回目 (1.5 秒の内) で決める (how = "digit" は同じ数字・"key" は焦点の上の鍵 = 数字で選んだ物を Enter で、
     Enter で選んだ物を数字や click で決めない)。間に描き直し (新しい札・状態の変化・設定) が入ると選び直し (renderFan の
     disarm)。押しを数えない間 (表示が替わった直後・窓が焦点を得た直後) の押しは、選ぶ 1 回目にも数えない (press と同じ間・
     扇の 1 回目の click と同じ考え)。焦点の上の鍵は、名指しで札の中を進めた直後の間も数えない (press と同じ・名指しの数字は
     数える)。戻り値 = 決める押しか (true の時だけ press へ渡す) */
  function armTwice(key, how) {
    var at = performance.now(), card = S.card, b = S.btns[key];
    if (!card || S.overlay || S.answering || card.state !== "shown" || !b || b.disabled) return false;
    if (at - S.genAt < SETTLE_MS || at - (S.focusAt || -1e9) < SETTLE_MS) return false;
    if (how === "key" && at - (S.stepAt || -1e9) < SETTLE_MS) return false;
    var step = C.armStep(S.armKey && S.armBy === how ? { key: S.armKey, at: S.armAt } : null, key, at, ARM_MS);
    if (step.confirm) { disarm(); return true; }
    armChoice(b, at, how);
    var kind = how === "digit" ? "digit_again" : "key_again";
    S.notice = L()[kind];
    S.noticeUntil = at + ARM_MS;
    S.noticeKind = kind;              /* 選んだ物と一緒に消す印 (disarm)・言葉を替えた後も効く */
    updateSide(at);
    return false;
  }

  /* 選んだ印を解く = 決まった (2 回目)・選び直し・描き直し (猶予の写し・新しい札・設定)。数字と鍵の案内も一緒に消す = 答えが
     決まった後の猶予の帯の上に「同じ数字 (キー) をもう 1 回」を残さない */
  function disarm() {
    if (S.noticeKind === "digit_again" || S.noticeKind === "key_again") { S.notice = ""; S.noticeUntil = 0; S.noticeKind = null; }
    if (S.armBtn) S.armBtn.classList.remove("armed");
    S.armKey = null;
    S.armBtn = null;
    S.armBy = null;
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
