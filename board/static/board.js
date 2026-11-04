/* BLEMMA の板の頁 = DOM と通信。純粋な計算は board_core.js (window.BlemmaCore)。設計 = docs/design.md §4。
 * 入力の 5 通り = 視線 (滞留)・キー・スイッチ 1 鍵の走査・携帯 (触る)・マウス (click)。
 * 札の本文は textContent だけで描く (innerHTML を使わない)。 */
(function () {
  "use strict";
  var C = window.BlemmaCore;
  var $ = function (id) { return document.getElementById(id); };
  var reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var S = {
    token: "", lang: "ja", dwellMs: 1000, scanMs: 0, switchKey: "Space", sound: false,
    seq: -1, snap: null, snapAt: 0, card: null, ui: C.newUi(null), key: "", gen: 0,
    btns: {}, optionKeys: [], scanList: [], scanEl: null, fillEl: null,
    delta: C.zeroPresses(), answering: false, undoing: false, sentKey: null,
    lastX: -1, lastY: -1, over: null, pointerType: "mouse", lastInput: "",
    held: {}, deadlineAt: null, undoAt: null,
    lightUntil: 0, lightKey: "", lastSeen: "", endText: "", endUntil: 0,
    notice: "", noticeUntil: 0, problem: "", offline: false,
    abort: null, kicked: false, retry: 0, stopped: false, overlay: null, sideAt: 0, ac: null
  };

  function L() { return C.I18N[S.lang]; }

  function readSettings() {
    var q = new URLSearchParams(location.search);
    S.lang = C.pickLang(q.get("lang"), navigator.language);
    S.dwellMs = C.parseDwell(q.get("dwell"));
    S.scanMs = C.parseScan(q.has("scan") ? q.get("scan") : null);
    S.switchKey = q.get("key") || "Space";
    S.sound = q.get("sound") === "1" || q.get("sound") === "on";
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
      setTimeout(poll, 0);
    }).catch(function () {
      clearTimeout(timer);
      if (S.kicked) { S.kicked = false; setTimeout(poll, 0); return; }
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
      S.key = k;
      render();
      bumpGen();
    }
    updateSide(performance.now());
  }

  /* ---- 描く ---- */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function makeButton(key, label, desc, cls) {
    var b = el("button", "btn" + (cls ? " " + cls : ""));
    b.type = "button";
    b.dataset.key = key;
    b.dataset.dwell = "1";
    b.appendChild(el("span", "fill"));
    b.appendChild(el("span", "label", label));
    if (desc) b.appendChild(el("span", "desc", desc));
    return b;
  }

  function fromText(f) {
    if (!f) return "";
    return [f.cwd, f.session, f.agent].filter(function (x) { return !!x; }).join(" · ");
  }

  function render() {
    var lang = S.lang;
    var T = L();
    var card = S.card;
    var focusedKey = document.activeElement && document.activeElement.dataset
      ? document.activeElement.dataset.key : null;
    document.documentElement.lang = lang;
    $("kind").textContent = card ? T["kind_" + card.kind] : "";
    $("from").textContent = card ? fromText(card.from) : "";
    var m = card ? C.buildScreen(card, S.ui, lang) : null;
    $("head").textContent = m ? m.head : "";
    $("text").textContent = m ? m.text : T.empty;
    var blocks = $("blocks");
    blocks.replaceChildren();
    (m ? m.blocks : []).forEach(function (b) {
      var sec = el("section");
      if (b.label) sec.appendChild(el("div", "label", b.label));
      sec.appendChild(el(b.mono ? "pre" : "div", b.mono ? "" : "plain", b.text));
      blocks.appendChild(sec);
    });
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
      document.querySelectorAll("#opts .btn, #fixed-zone .btn, #term-zone .btn"),
      function (b) { return !b.disabled; });
    S.scanEl = null;
    S.fillEl = null;
    if (focusedKey && S.btns[focusedKey] && !S.btns[focusedKey].disabled) {
      S.btns[focusedKey].focus({ preventScroll: true });
    }
  }

  /* 表示の世代を進める = 滞留を止めて選択を解き、pointer の下の釦は入り直すまで数えない・走査は頭から (§4.2) */
  function bumpGen() {
    S.gen += 1;
    S.over = keyAtPointer();
    S.dwell.reset();
    S.dwell.block(S.over);
    S.scan.restart(performance.now());
    if (S.scanEl) { S.scanEl.classList.remove("scan"); S.scanEl = null; }
    if (S.card && S.card.state === "shown" && S.lastInput === "key" && !S.overlay && S.scanMs <= 0) {
      var first = document.querySelector("#opts .btn:not(:disabled)");
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
    return dwellKeyOf(document.elementFromPoint(S.lastX, S.lastY));
  }

  function findBtn(key) {
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
    var rem = $("remain");
    if (card && card.state === "shown" && S.deadlineAt !== null) {
      var sec = Math.max(0, (S.deadlineAt - now) / 1000);
      setText(rem, C.fmt(T.remain, { t: C.mmss(Math.ceil(sec)) }));
      rem.classList.toggle("low", sec < 60);
    } else {
      setText(rem, "");
      rem.classList.remove("low");
    }
    var qn = S.snap ? S.snap.queue : 0;
    setText($("queue"), qn > 0 ? C.fmt(T.queue, { n: qn }) : "");
    if (S.snap && S.snap.stats) {
      setText($("stats"), C.statsText(S.snap.stats, S.lang, S.snap.stats.elapsed + (now - S.snapAt) / 1000));
    }
    var st = "";
    if (S.problem) st = S.problem;
    else if (S.offline) st = T.offline;
    else if (S.notice && now < S.noticeUntil) st = S.notice;
    else if (S.endText && now < S.endUntil) st = S.endText;
    setText($("status"), st);
    var band = $("band");
    var lightOn = !!(S.snap && S.snap.light) && now < S.lightUntil;
    if (lightOn) {
      setText(band, C.lightText(S.snap.light, S.lang));
      band.hidden = false;
      document.body.classList.add("glow");
    } else {
      band.hidden = true;
      document.body.classList.remove("glow");
      $("card").classList.remove("blink");
    }
    updateUndo(now);
  }

  /* 取り消す = 押した後の猶予のうちだけ、上の中央に大きく (押した釦の上には出さない・§4.3) */
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
    } else {
      setText($("undo-label"), T.delivering + " " + label);
      btn.hidden = true;
      btn.disabled = true;
    }
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
    if (!reduced && S.card) {
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
    if (key === "reset" || key === "phone" || key === "gear") {
      if (by !== "key" && by !== "click") return;          /* 視線では押さない (§4.5) */
      if (key === "reset") api("POST", "/stats/reset", {}).catch(function () { S.offline = true; });
      if (key === "phone") openPhone();
      if (key === "gear") openGear();
      return;
    }
    if (key === "close") { closeOverlay(); return; }
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

  function sendAnswer(choice, by) {
    var card = S.card;
    S.answering = true;
    var sentKey = S.key;
    api("POST", "/answer", { id: card.id, seq: card.view_seq, choice: choice, by: by, presses: S.delta })
      .then(function (r) {
        if (r.status === 200) {
          S.delta = C.zeroPresses();
          S.sentKey = sentKey;
        } else if (r.status === 401) {
          S.problem = L().bad_token;
        } else {
          showNotice(L().stale);
          kick();
        }
      })
      .catch(function () { S.offline = true; })
      .then(function () { S.answering = false; });
  }

  function doUndo(by) {
    var card = S.card;
    if (!card || S.undoing) return;
    S.undoing = true;
    S.delta[by] = (S.delta[by] || 0) + 1;
    api("POST", "/undo", { id: card.id, by: by, presses: S.delta })
      .then(function (r) {
        if (r.status === 200) S.delta = C.zeroPresses();
        else kick();
      })
      .catch(function () { S.offline = true; })
      .then(function () { S.undoing = false; });
  }

  /* ---- 入力 ---- */
  function onPointer(e) {
    if (e.pointerType === "touch") { S.pointerType = "touch"; return; }
    S.lastX = e.clientX;
    S.lastY = e.clientY;
    S.over = dwellKeyOf(e.target);
  }

  function isSwitch(e) {
    var k = S.switchKey;
    if (k === "Space" || k === " ") return e.code === "Space" || e.key === " ";
    return e.code === k || e.key === k || (k.length === 1 && typeof e.key === "string" && e.key.toLowerCase() === k.toLowerCase());
  }

  function onKeyDown(e) {
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
    var active = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest("[data-key]") : null;
    if (!sw && active && (e.key === "Enter" || e.key === " ") &&
        ["reset", "phone", "gear"].indexOf(active.dataset.key) >= 0) {
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
    if (!b || b.disabled) return;
    S.lastInput = S.pointerType === "touch" ? "touch" : "click";
    press(b.dataset.key, S.pointerType === "touch" ? "touch" : "click");
  }

  /* 毎こま = 滞留・走査・表示の秒 */
  function frame(now) {
    if (S.dwellMs > 0 && !S.overlay) {
      var r = S.dwell.update(S.over, now);
      setFill(r.target, r.progress);
      if (r.fire) {
        setFill(null, 0);
        S.lastInput = "dwell";
        press(r.target, "dwell");
      }
    }
    if (S.scanMs > 0) {
      var card = S.card;
      var target = null;
      if (card && card.state === "deciding") {
        var u = $("undo-btn");                               /* 猶予のうち = 走査を止め、次の押下 = 取り消す */
        target = u.hidden ? null : u;
      } else if (card && card.state === "shown" && !S.overlay && !S.answering) {
        var i = S.scan.index(now, S.scanList.length);
        target = i >= 0 ? S.scanList[i] : null;
      }
      if (S.scanEl !== target) {
        if (S.scanEl) S.scanEl.classList.remove("scan");
        if (target) target.classList.add("scan");
        S.scanEl = target;
      }
    }
    if (now - S.sideAt > 250) {
      S.sideAt = now;
      updateSide(now);
    }
    window.requestAnimationFrame(frame);
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
    S.dwell.reset();
    S.dwell.block(keyAtPointer());
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

  function openGear() {
    var T = L();
    var q = new URLSearchParams(location.search);
    showPanel(T.settings, function (body) {
      addSelect(body, T.set_dwell, "dwell",
                [["0", "0"], ["0.8", "0.8"], ["1", "1.0"], ["1.2", "1.2"], ["1.5", "1.5"], ["2", "2.0"]],
                String(S.dwellMs / 1000));
      addSelect(body, T.set_scan, "scan",
                [["off", T.off], ["1", "1.0"], ["1.5", "1.5"], ["2", "2.0"], ["3", "3.0"]],
                S.scanMs ? String(S.scanMs / 1000) : "off");
      addSelect(body, T.set_lang, "lang", [["", T.auto], ["ja", "日本語"], ["en", "English"]], q.get("lang") || "");
      addSelect(body, T.set_sound, "sound", [["off", T.off], ["on", T.on]], S.sound ? "on" : "off");
    });
  }

  function setParam(name, value) {
    var p = new URLSearchParams(location.search);
    if (value === "" || (name === "scan" && value === "off")) p.delete(name);
    else p.set(name, value);
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    readSettings();
    setChrome();
    S.key = "";
    refreshView();
    var title = $("panel-title");
    if (S.overlay) title.textContent = L().settings;
  }

  function setChrome() {
    var T = L();
    document.documentElement.lang = S.lang;
    $("stats-reset").textContent = T.reset;
    $("phone-btn").textContent = T.phone;
    $("gear-btn").textContent = T.settings;
    $("panel-close").textContent = T.close;
  }

  function init() {
    readSettings();
    readToken();
    setChrome();
    S.key = C.viewKey(null, S.ui, S.lang);
    render();
    document.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("pointerover", onPointer, { passive: true });
    document.addEventListener("pointerdown", function (e) {
      S.pointerType = e.pointerType || "mouse";
    }, { passive: true, capture: true });
    document.documentElement.addEventListener("pointerleave", function () { S.over = null; });
    window.addEventListener("blur", function () { S.over = null; S.held = {}; });
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("keyup", function (e) { delete S.held[e.code || e.key]; });
    document.addEventListener("click", onClick);
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
    window.requestAnimationFrame(frame);
    if (!S.token) { S.problem = L().no_token; updateSide(performance.now()); return; }
    poll();
  }

  init();
})();
