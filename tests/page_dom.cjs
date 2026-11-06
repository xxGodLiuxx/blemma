/* 板の頁 (board/static/board.js) を、index.html から作った小さな DOM の代用品の中で init() ごと走らせる
 * (node の vm・実ブラウザも port も使わない)。試験は関数を直に呼ばず、板の写し (apply)・鍵・click・pointer の
 * 入口から入れて、描き直し・取り消しの枠・焦点の付け直しまで通す。配置 (CSS) は持たない = 当たり判定は試験が
 * doc.layout で決める。時計と timer は偽物 (試験が run で進める)。見張り (/pending) は返さない = 板の写しは試験が入れる。
 *
 * ブラウザの順として置いた前提 (実の Chromium 156 の headless で測った):
 *  - 焦点の在る要素を木から外す・別の所へ付け替える・その要素自身に hidden を立てる = 焦点はその場で body へ移る。
 *  - 入れ物を隠す・要素を disabled にする = その処理の間は焦点が残り、次のこまの頭で body へ移る。
 *  - 要素の送りの知らせ (scroll) は泡立たない = 次のこまの頭 (rAF の前) に、文書の capture の聞き手へだけ配る。
 *  - Enter の keydown と Space の keyup は、keydown が preventDefault されなければ、焦点の釦に click (detail 0) を起こす。
 */
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");

const STATIC = path.join(__dirname, "..", "board", "static");

function settle() { return new Promise(function (resolve) { setImmediate(function () { setImmediate(resolve); }); }); }

/* ---- 時計と timer (偽物) ---- */
function makeClock(start) {
  const c = { now: start === undefined ? 1000 : start, timers: [], seq: 0 };
  c.setTimeout = function (fn, ms) { const id = ++c.seq; c.timers.push({ id: id, at: c.now + Math.max(0, Number(ms) || 0), fn: fn }); return id; };
  c.clearTimeout = function (id) { c.timers = c.timers.filter(function (t) { return t.id !== id; }); };
  c.nextAt = function () { return c.timers.reduce(function (a, t) { return Math.min(a, t.at); }, Infinity); };
  c.due = function () {
    for (;;) {
      let next = null;
      c.timers.forEach(function (t) { if (t.at <= c.now && (!next || t.at < next.at || (t.at === next.at && t.id < next.id))) next = t; });
      if (!next) return;
      c.timers = c.timers.filter(function (t) { return t !== next; });
      next.fn();
    }
  };
  return c;
}

/* ---- DOM の代用品 ---- */
class Style {
  setProperty(k, v) { this[k] = String(v); }
  getPropertyValue(k) { return this[k] === undefined ? "" : this[k]; }
  removeProperty(k) { delete this[k]; }
}

class ClassList {
  constructor() { this.set = new Set(); }
  add() { for (const c of arguments) this.set.add(c); }
  remove() { for (const c of arguments) this.set.delete(c); }
  toggle(c, force) { const on = force === undefined ? !this.set.has(c) : !!force; if (on) this.set.add(c); else this.set.delete(c); return on; }
  contains(c) { return this.set.has(c); }
}

class Listeners {
  constructor() { this.list = []; }
  add(type, fn, opt) { this.list.push({ type: type, fn: fn, capture: opt === true || !!(opt && opt.capture), once: !!(opt && opt.once), opt: opt }); }
  remove(type, fn) { this.list = this.list.filter(function (l) { return !(l.type === type && l.fn === fn); }); }
  /* capture の聞き手が先・泡立たない知らせ (要素の scroll) は capture の聞き手にだけ届く */
  fire(type, ev, captureOnly) {
    const hit = this.list.filter(function (l) { return l.type === type && (!captureOnly || l.capture); });
    const order = hit.filter(function (l) { return l.capture; }).concat(hit.filter(function (l) { return !l.capture; }));
    order.forEach(function (l) { if (l.once) this.remove(type, l.fn); l.fn(ev); }, this);
    return order.length;
  }
}

class Text {
  constructor(doc, text) { this.nodeType = 3; this.ownerDocument = doc; this.parentNode = null; this.data = String(text); }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}

function inside(node, root) {
  for (let n = node; n; n = n.parentNode) if (n === root) return true;
  return false;
}

function walk(root, fn) {
  (root.childNodes || []).forEach(function (n) { if (n.nodeType === 1) { fn(n); walk(n, fn); } });
}

function adopt(node, doc) {
  node.ownerDocument = doc;
  (node.childNodes || []).forEach(function (n) { adopt(n, doc); });
}

/* 選ぶ式 = 「,」の並び・空白 (子孫)・#id・.class・tag・[属性]・:disabled・:not(:disabled) だけ */
function camel(s) { return s.replace(/-([a-z])/g, function (m, c) { return c.toUpperCase(); }); }
function hasAttr(e, a) {
  if (a.indexOf("data-") === 0) return Object.prototype.hasOwnProperty.call(e.dataset, camel(a.slice(5)));
  if (a === "hidden") return !!e.hidden;
  if (a === "disabled") return !!e.disabled;
  return Object.prototype.hasOwnProperty.call(e.attrs, a);
}
function compound(text) {
  const tests = [];
  const re = /#([\w-]+)|\.([\w-]+)|\[([\w-]+)\]|(:not\(:disabled\))|(:disabled)|([a-zA-Z][\w-]*)/g;
  let m, used = 0;
  while ((m = re.exec(text))) {
    used += m[0].length;
    if (m[1]) { const id = m[1]; tests.push(function (e) { return e.id === id; }); }
    else if (m[2]) { const c = m[2]; tests.push(function (e) { return e.classList.contains(c); }); }
    else if (m[3]) { const a = m[3]; tests.push(function (e) { return hasAttr(e, a); }); }
    else if (m[4]) tests.push(function (e) { return !e.disabled; });
    else if (m[5]) tests.push(function (e) { return !!e.disabled; });
    else if (m[6]) { const t = m[6].toLowerCase(); tests.push(function (e) { return e.localName === t; }); }
  }
  if (used !== text.length) throw new Error("代用品が読めない選ぶ式: " + text);
  return tests;
}
function matches(e, sel) {
  return sel.split(",").some(function (part) {
    const chain = part.trim().split(/\s+/).map(compound);
    if (!chain[chain.length - 1].every(function (t) { return t(e); })) return false;
    let i = chain.length - 2;
    for (let p = e.parentElement; p && i >= 0; p = p.parentElement) if (chain[i].every(function (t) { return t(p); })) i -= 1;
    return i < 0;
  });
}

const FOCUSABLE = { BUTTON: 1, SELECT: 1, INPUT: 1, TEXTAREA: 1 };

class Element {
  constructor(doc, tag) {
    this.nodeType = 1; this.ownerDocument = doc; this.parentNode = null;
    this.tagName = String(tag).toUpperCase(); this.localName = String(tag).toLowerCase();
    this.childNodes = []; this.attrs = {}; this.dataset = {}; this.style = new Style(); this.classList = new ClassList();
    this.listeners = new Listeners(); this._hidden = false; this.disabled = false; this.id = "";
    this.scrollHeight = 0; this.clientHeight = 0; this.clientWidth = 0; this._scrollTop = 0; this.offsetWidth = 0;
    this.value = "";
  }
  get hidden() { return this._hidden; }
  set hidden(v) {
    v = !!v;
    if (v === this._hidden) return;
    this._hidden = v;
    const doc = this.ownerDocument;                    /* その要素自身に hidden = 焦点はその場で外れる (前提の 1) */
    if (v && doc && doc.activeElement === this) doc.activeElement = doc.body;
  }
  get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
  get children() { return this.childNodes.filter(function (n) { return n.nodeType === 1; }); }
  get firstChild() { return this.childNodes[0] || null; }
  get className() { return Array.from(this.classList.set).join(" "); }
  set className(v) { this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get textContent() { return this.childNodes.map(function (n) { return n.textContent; }).join(""); }
  set textContent(v) {
    this.replaceChildren();
    if (v !== "" && v !== null && v !== undefined) this.appendChild(new Text(this.ownerDocument, v));
  }
  get scrollTop() { return this._scrollTop; }
  set scrollTop(v) {
    const max = Math.max(0, this.scrollHeight - this.clientHeight);
    const to = Math.max(0, Math.min(max, Math.round(Number(v) || 0)));
    if (to === this._scrollTop) return;
    this._scrollTop = to;
    this.ownerDocument.pendingScroll.push(this);       /* 送りの知らせは次のこまの頭 (前提の 3) */
  }
  setAttribute(k, v) {
    v = String(v);
    this.attrs[k] = v;
    if (k === "id") this.id = v;
    else if (k === "class") this.className = v;
    else if (k === "hidden") this.hidden = true;
    else if (k === "disabled") this.disabled = true;
    else if (k.indexOf("data-") === 0) this.dataset[camel(k.slice(5))] = v;
  }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; if (k === "hidden") this.hidden = false; if (k === "disabled") this.disabled = false; }
  detach(child) {
    const i = this.childNodes.indexOf(child);
    if (i < 0) return;
    this.childNodes.splice(i, 1);
    child.parentNode = null;
    const doc = child.ownerDocument;                   /* 焦点の在る物を外した・付け替えた = その場で body へ (前提の 1) */
    if (doc && doc.activeElement && inside(doc.activeElement, child)) doc.activeElement = doc.body;
  }
  appendChild(child) { return this.insertBefore(child, null); }
  insertBefore(child, ref) {
    if (child.parentNode) child.parentNode.detach(child);
    if (child.ownerDocument !== this.ownerDocument) adopt(child, this.ownerDocument);
    const i = ref ? this.childNodes.indexOf(ref) : -1;
    if (i < 0) this.childNodes.push(child); else this.childNodes.splice(i, 0, child);
    child.parentNode = this;
    return child;
  }
  replaceChildren() {
    this.childNodes.slice().forEach(function (c) { this.detach(c); }, this);
    for (const n of arguments) this.appendChild(n);
  }
  remove() { if (this.parentNode) this.parentNode.detach(this); }
  contains(n) { return inside(n, this); }
  matches(sel) { return matches(this, sel); }
  closest(sel) { for (let e = this; e && e.nodeType === 1; e = e.parentElement) if (matches(e, sel)) return e; return null; }
  querySelectorAll(sel) { const out = []; walk(this, function (e) { if (matches(e, sel)) out.push(e); }); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  addEventListener(type, fn, opt) { this.listeners.add(type, fn, opt); }
  removeEventListener(type, fn) { this.listeners.remove(type, fn); }
  getBoundingClientRect() {
    const r = (this.ownerDocument.layout && this.ownerDocument.layout(this)) || { left: 0, top: 0, width: 0, height: 0 };
    return { left: r.left, top: r.top, width: r.width, height: r.height, x: r.left, y: r.top, right: r.left + r.width, bottom: r.top + r.height };
  }
  scrollIntoView(opt) { if (this.ownerDocument.onScrollIntoView) this.ownerDocument.onScrollIntoView(this, opt); }
  setPointerCapture() {}
  select() {}
  shown() {                                            /* hidden の祖先が無く、文書に繋がっている */
    for (let e = this; e && e.nodeType === 1; e = e.parentElement) if (e.hidden) return false;
    return this.ownerDocument.contains(this);
  }
  focusable() { return !!FOCUSABLE[this.tagName] && !this.disabled && this.shown(); }
  focus() {
    const doc = this.ownerDocument;
    if (!this.focusable() || doc.activeElement === this) return;
    doc.activeElement = this;
    /* silentFocus = 窓が背面に居る (実のブラウザは、背面の窓へは焦点の知らせを送らない・前面へ戻った時に送る) */
    if (!doc.silentFocus) doc.listeners.fire("focusin", { target: this });
  }
  blur() { if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body; }
}

class Document {
  constructor(win) {
    this.nodeType = 9; this.defaultView = win; this.listeners = new Listeners(); this.pendingScroll = [];
    this.hidden = false; this.title = "";
    this.documentElement = new Element(this, "html"); this.head = new Element(this, "head"); this.body = new Element(this, "body");
    this.documentElement.appendChild(this.head);
    this.documentElement.appendChild(this.body);
    this.activeElement = this.body;
    this.layout = null;                                /* 試験が置く (要素 → {left, top, width, height, z}) */
    this.onScrollIntoView = null;
  }
  createElement(tag) { return new Element(this, tag); }
  createElementNS(ns, tag) { return new Element(this, tag); }
  createTextNode(t) { return new Text(this, t); }
  getElementById(id) { let hit = null; walk(this.documentElement, function (e) { if (!hit && e.id === id) hit = e; }); return hit; }
  contains(n) { return inside(n, this.documentElement); }
  querySelectorAll(sel) { return this.documentElement.querySelectorAll(sel); }
  querySelector(sel) { return this.documentElement.querySelector(sel); }
  addEventListener(type, fn, opt) { this.listeners.add(type, fn, opt); }
  removeEventListener(type, fn) { this.listeners.remove(type, fn); }
  execCommand() { return false; }
  /* 点の下の物 = 見えていて、配置が点を含む物。z が大きい物・同じ z なら文書の後ろの物が勝つ */
  elementFromPoint(x, y) {
    let best = null, bestZ = -Infinity;
    const self = this;
    if (!this.layout) return this.body;
    walk(this.documentElement, function (e) {
      if (!e.shown()) return;
      const r = self.layout(e);
      if (!r || !(x >= r.left && x < r.left + r.width && y >= r.top && y < r.top + r.height)) return;
      const z = r.z || 0;
      if (z >= bestZ) { best = e; bestZ = z; }
    });
    return best || this.body;
  }
  /* こまの頭 = 送りの知らせ (capture の聞き手だけ) と、焦点の付け直し (入れ物が隠れた・押せなくなった釦から body へ) */
  beforeFrame() {
    const moved = this.pendingScroll.filter(function (e, i, all) { return all.indexOf(e) === i; });
    this.pendingScroll = [];
    moved.forEach(function (e) { this.listeners.fire("scroll", { target: e }, true); }, this);
    const a = this.activeElement;
    if (a && a !== this.body && !a.focusable()) this.activeElement = this.body;
    return moved.length;
  }
}

class Win {
  constructor(name) {
    this.name = name; this.listeners = new Listeners(); this.document = new Document(this);
    this.innerWidth = 640; this.innerHeight = 700; this.outerWidth = 656; this.outerHeight = 739; this.screenX = 100; this.screenY = 100;
    this.screen = { availLeft: 0, availTop: 0, availWidth: 2560, availHeight: 1392 };
    this.devicePixelRatio = 1; this.navigator = { language: "ja" };
    this.raf = null; this.rafId = 0; this.closed = false;
    this.document.documentElement.clientWidth = 640;
  }
  requestAnimationFrame(fn) { this.raf = fn; this.rafId += 1; return this.rafId; }
  cancelAnimationFrame(id) { if (id === this.rafId) this.raf = null; }
  matchMedia() { return { matches: false }; }
  addEventListener(type, fn, opt) { this.listeners.add(type, fn, opt); }
  removeEventListener(type, fn) { this.listeners.remove(type, fn); }
  moveTo() {}
  resizeTo() {}
  focus() {}
  close() { if (this.closed) return; this.closed = true; this.listeners.fire("pagehide", {}); }
}

/* index.html を木にする (script は走らせない) */
function buildFromHtml(doc, html) {
  const re = /<!--[\s\S]*?-->|<!doctype[^>]*>|<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)((?:\s+[^\s=>\/]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/gi;
  const VOID = { meta: 1, link: 1, br: 1, img: 1, input: 1, path: 1, circle: 1 };
  let cur = null, m;
  while ((m = re.exec(html))) {
    if (m[1]) {
      const t = m[1].toLowerCase();
      if (t !== "html" && t !== "head" && t !== "body" && cur && cur.parentNode) cur = cur.parentNode;
      continue;
    }
    if (m[2]) {
      const tag = m[2].toLowerCase();
      let e;
      if (tag === "html") e = doc.documentElement;
      else if (tag === "head") e = doc.head;
      else if (tag === "body") e = doc.body;
      else { e = doc.createElement(tag); cur.appendChild(e); }
      const are = /([^\s=]+)(?:="([^"]*)")?/g;
      let a;
      while ((a = are.exec(m[3] || ""))) e.setAttribute(a[1], a[2] === undefined ? "" : a[2]);
      if (!(VOID[tag] || m[4])) cur = e;
      continue;
    }
    if (m[5] && cur && m[5].trim()) cur.appendChild(doc.createTextNode(m[5]));
  }
}

const EXPORT = "\n  window.__t = { S: S, apply: apply, press: press, bumpGen: bumpGen," +
  " view: function () { return { doc: viewDocument, win: viewWindow }; } };\n  init();$1";

/* 頁を起こす。opt = { query: "?mode=small&…", undoMs: 3000, pip: true (PiP の窓を開ける),
   reply: (path, body) → {status, data} か {later: fn(send)} (返りを後で送る) } */
async function boot(opt) {
  opt = opt || {};
  const clock = makeClock(opt.start);
  const win = new Win("home");
  buildFromHtml(win.document, fs.readFileSync(path.join(STATIC, "index.html"), "utf8"));
  const core = require(path.join(STATIC, "board_core.js"));
  win.BlemmaCore = core;
  win.crypto = require("crypto").webcrypto;
  const store = {}, session = {};
  win.localStorage = { getItem: function (k) { return k in store ? store[k] : null; }, setItem: function (k, v) { store[k] = String(v); } };
  win.sessionStorage = { getItem: function (k) { return k in session ? session[k] : null; }, setItem: function (k, v) { session[k] = String(v); } };
  const location = { search: opt.query || "", hash: "#t=tok", origin: "http://127.0.0.1:8765", port: "8765", pathname: "/" };
  const history = { replaceState: function (a, b, url) { const q = String(url).split("#")[0].split("?")[1]; location.search = q ? "?" + q : ""; } };
  const c = { clock: clock, win: win, core: core, sent: [], pips: [], windowFound: false, undoMs: opt.undoMs === undefined ? 3000 : opt.undoMs,
              reply: opt.reply || null, nextFrame: clock.now, seq: 0 };
  if (opt.pip) {
    win.documentPictureInPicture = { requestWindow: function () { const w = new Win("pip"); c.pips.push(w); return Promise.resolve(w); } };
  }
  function respond(status, data) { return { status: status, json: function () { return Promise.resolve(data); } }; }
  function fetchImpl(url, o) {
    o = o || {};
    const p = String(url).split("?")[0];
    return new Promise(function (resolve, reject) {
      if (o.signal) o.signal.addEventListener("abort", function () { reject(new Error("aborted")); });
      if (p === "/pending") return;                      /* 見張りは返さない = 板の写しは試験が c.show で入れる */
      const body = o.body ? JSON.parse(o.body) : {};
      c.sent.push({ path: p, body: body, at: clock.now });
      const r = c.reply && c.reply(p, body);
      /* later = 返りを後で送る (写しが返りより先に届く順を作る)。later(send) の send(status, data) を、筋書きが好きな時に呼ぶ */
      if (r && typeof r.later === "function") return r.later(function (status, data) { resolve(respond(status, data)); });
      if (r) return resolve(respond(r.status, r.data));
      if (p === "/answer") return resolve(respond(200, { undo_ms: c.undoMs, undo_remaining: c.undoMs / 1000 }));
      if (p === "/undo") return resolve(respond(200, { state: "shown" }));
      if (p === "/window") return resolve(respond(200, { found: c.windowFound, ok: true, pin: !!body.pin }));
      resolve(respond(204, null));
    });
  }
  let src = fs.readFileSync(path.join(STATIC, "board.js"), "utf8");
  const re = /\n  init\(\);(\r?\n)/;
  if (!re.test(src)) throw new Error("board.js の init(); の行が見つからない");
  vm.runInNewContext(src.replace(re, EXPORT), {
    window: win, document: win.document, location: location, navigator: win.navigator, history: history,
    performance: { now: function () { return clock.now; } }, fetch: fetchImpl,
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, URLSearchParams: URLSearchParams,
    AbortController: AbortController, console: console });
  const t = win.__t;
  c.t = t; c.S = t.S;
  c.doc = function () { return t.view().doc; };
  c.vwin = function () { return t.view().win; };
  c.$ = function (id) { return c.doc().getElementById(id); };
  /* 見えている釦 (data-key) */
  c.btn = function (key) { return c.doc().querySelectorAll("[data-key]").filter(function (b) { return b.dataset.key === key && b.shown(); })[0] || null; };
  c.active = function () { const d = c.doc(), a = d.activeElement; return !a || a === d.body ? "body" : (a.dataset.key || a.id || a.localName); };
  /* この頁の名札 (頁が /answer に添える viewer)。実の板は、受けた答えの名札を写しに添える = 筋書きは、猶予の写しと
     「直前に終わった札」に、誰の答えかを自分で書く (deciding(…, by)・ended(card, by)) */
  c.me = function () { return c.S.pressLedger.source; };
  c.answers = function () { return c.sent.filter(function (s) { return s.path === "/answer"; }); };
  c.posts = function () { return c.sent.filter(function (s) { return s.path === "/answer" || s.path === "/undo"; }).map(function (s) { return s.path; }); };
  /* 板の写しを当てる (= 見張りが返った時と同じ入口) */
  c.show = function (card, more) {
    c.seq += 1;
    t.apply(Object.assign({ seq: c.seq, card: card || null, queue: 0, last: null, light: null, states: [],
                            stats: { presses: {}, total: 0, answers: 0, elapsed: 0, cards: [] }, undo_ms: c.undoMs }, more || {}));
  };
  /* こまの 1 歩 = 窓ごとに 送りの知らせ → 焦点の付け直し → rAF */
  c.step = function () {
    const all = [win].concat(c.pips);
    all.forEach(function (w) { if (!w.closed) w.document.beforeFrame(); });
    all.forEach(function (w) { const fn = w.raf; w.raf = null; if (fn && !w.closed) fn(clock.now); });
  };
  /* ms だけ進める。こまは 16 ms ごと。pointerFn(now) があれば every ms ごとに呼ぶ (視線の道具は 10 ms ごと) */
  c.run = async function (ms, pointerFn, every) {
    const end = clock.now + ms;
    let nextPointer = clock.now;
    every = every || 10;
    while (clock.now < end) {
      const at = Math.min(pointerFn ? nextPointer : Infinity, c.nextFrame, clock.nextAt(), end);
      clock.now = Math.max(clock.now, at);
      clock.due();
      if (pointerFn && clock.now >= nextPointer) { pointerFn(clock.now); nextPointer = clock.now + every; }
      if (clock.now >= c.nextFrame) { c.step(); c.nextFrame = clock.now + 16; }
      await settle();
    }
    await settle();
  };
  c.event = function (type, ev) {
    ev.defaultPrevented = false;
    ev.preventDefault = function () { this.defaultPrevented = true; };
    c.doc().listeners.fire(type, ev);
    return ev;
  };
  /* pointer の動き (既定 pointermove)。当たり判定は doc.layout */
  c.pointer = function (x, y, more) {
    const ev = Object.assign({ target: c.doc().elementFromPoint(x, y), clientX: x, clientY: y, screenX: x, screenY: y,
                               buttons: 0, button: 0, pointerType: "mouse", pointerId: 1 }, more || {});
    c.event((more && more.type) || "pointermove", ev);
    return ev.target;
  };
  /* 鍵の 1 打 = keydown → (Enter の既定 = 焦点の釦の click) → hold ms → keyup → (Space の既定 = 焦点の釦の click) */
  c.key = async function (key, code, hold) {
    const d = c.doc();
    const down = c.event("keydown", { key: key, code: code || key, repeat: false, ctrlKey: false, altKey: false, metaKey: false, target: d.activeElement });
    const a = c.doc().activeElement;
    if (!down.defaultPrevented && key === "Enter" && a && a.localName === "button" && a.focusable()) c.event("click", { target: a, detail: 0 });
    await settle();
    if (hold) await c.run(hold);
    c.event("keyup", { key: key, code: code || key, target: c.doc().activeElement });
    const b = c.doc().activeElement;
    if (!down.defaultPrevented && key === " " && b && b.localName === "button" && b.focusable()) c.event("click", { target: b, detail: 0 });
    await settle();
    return down;
  };
  /* マウスの 1 回の click = 押す → (釦なら焦点) → 離す → click。target は要素 (配置を問わない) */
  c.click = async function (target) {
    const base = { target: target, clientX: 1, clientY: 1, screenX: 1, screenY: 1, button: 0, pointerType: "mouse", pointerId: 1 };
    c.event("pointerdown", Object.assign({}, base, { buttons: 1 }));
    const b = target.closest ? target.closest("button") : null;
    if (b) b.focus();
    c.event("pointerup", Object.assign({}, base, { buttons: 0 }));
    c.event("click", { target: target, detail: 1 });
    await settle();
  };
  await settle();
  return c;
}

module.exports = { boot: boot, settle: settle };
