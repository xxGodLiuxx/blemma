/* BLEMMA の板の頁 = 純粋な計算だけ (DOM・通信なし)。設計 = docs/design.md §4。
 * ブラウザでは window.BlemmaCore、node では require() で読める (手で確かめる時に使う)。 */
(function (root) {
  "use strict";

  var I18N = {
    ja: {
      kind_permission: "権限の確認", kind_question: "Claude の質問", kind_elicitation: "MCP の問い",
      allow_once: "許可 (今回)", deny: "拒否", deny_title: "拒否の理由を選んでください", back: "戻る",
      fixed_permission: "作業を止める", fixed_question: "この質問に答えない",
      fixed_elicitation: "この問い合わせを閉じる",
      terminal: "端末で答える", terminal_sub: "端末で答えた時も、これで閉じる",
      decline: "断る", skip_field: "空のまま", next: "次へ", send: "送る", restart: "やり直す",
      confirm: "これで送りますか", default_mark: "既定", empty_field: "(空のまま)",
      undo: "取り消す", decided: "決まりました", delivering: "Claude Code へ渡しています…",
      end_answered: "板の答えを Claude Code へ渡しました (端末の確認が続くことがあります)",
      end_released: "端末で答えてください",
      end_expired: "時間切れ。端末で答えてください",
      end_disconnected: "接続が終了しました。端末を確認してください",
      end_resolved: "端末の側で終わりました",
      not_delivered: "板の答えは届いていません",
      empty: "札はありません。Claude Code が訊くと、ここに出ます",
      queue: "待ち {n} 件", remain: "残り {t}",
      stats_line: "押し {n} ({parts})・送った答え {m}・経過 {t}",
      in_dwell: "視線", in_key: "キー", in_switch: "スイッチ", in_touch: "触る", in_click: "クリック",
      per_card: "札ごとの秒", reset: "計を 0 に",
      phone: "携帯で開く", close: "閉じる",
      phone_help: "携帯は利用者の転送で 127.0.0.1 へ届けます (例: USB の Android = adb reverse tcp:{port} tcp:{port})。" +
        "127.0.0.1 / localhost 以外の名で開く時は、server を --allow-host <名> で起こしてください。" +
        "転送の先へ札の本文と token が渡ります。token は起動ごとに替わります。",
      settings: "設定", set_dwell: "滞留 (秒・0 = click だけ)", set_scan: "走査 (秒・切 = なし)",
      set_lang: "言葉", set_sound: "音", off: "切", on: "入", auto: "自動",
      no_token: "token がありません。server.py の端末に出た URL (#t= つき) で開いてください",
      bad_token: "token が違います。server を起こし直した時は、新しい URL で開いてください",
      offline: "板の server に繋がりません (繋ぎ直しています)",
      stale: "画面が古くなっていました。もう一度選んでください",
      light_idle_prompt: "Claude が次の指示を待っています (端末へ)",
      light_elicitation_url_dialog: "端末でリンクを開くか決めてください",
      light_default: "Claude Code からの合図",
      dest_session: "このセッションの間", dest_localSettings: "この project・この機械で恒久",
      dest_projectSettings: "この project の共有の設定で恒久 (commit されうる)",
      dest_userSettings: "全部の project で恒久",
      sugg_allow: "次から訊かない", sugg_deny: "次から拒否", sugg_ask: "次から必ず訊く",
      sugg_mode: "モードを替える", sugg_dirs: "このフォルダも許す",
      mode_acceptEdits: "編集を訊かない (acceptEdits)", mode_default: "既定 (default)",
      mode_plan: "計画 (plan)", mode_dontAsk: "訊かずに断る (dontAsk)", mode_auto: "自動 (auto)",
      reasons: ["別のやり方でお願いします", "いまは要りません", "先に説明してください"]
    },
    en: {
      kind_permission: "Permission", kind_question: "Claude asks", kind_elicitation: "MCP request",
      allow_once: "Allow (this time)", deny: "Deny", deny_title: "Choose a reason to deny", back: "Back",
      fixed_permission: "Stop the work", fixed_question: "Don't answer this question",
      fixed_elicitation: "Close this request",
      terminal: "Answer in the terminal", terminal_sub: "Also closes it if you already answered there",
      decline: "Decline", skip_field: "Leave empty", next: "Next", send: "Send", restart: "Start over",
      confirm: "Send these answers?", default_mark: "default", empty_field: "(empty)",
      undo: "Undo", decided: "Decided", delivering: "Handing it to Claude Code…",
      end_answered: "The board's answer was handed to Claude Code (the terminal may still ask)",
      end_released: "Please answer in the terminal",
      end_expired: "Timed out. Please answer in the terminal",
      end_disconnected: "The connection ended. Please check the terminal",
      end_resolved: "It was finished on the terminal side",
      not_delivered: "The board's answer did not arrive",
      empty: "No cards. When Claude Code asks, it appears here",
      queue: "{n} waiting", remain: "{t} left",
      stats_line: "Presses {n} ({parts}) · answers sent {m} · elapsed {t}",
      in_dwell: "gaze", in_key: "key", in_switch: "switch", in_touch: "touch", in_click: "click",
      per_card: "seconds per card", reset: "Reset counts",
      phone: "Open on a phone", close: "Close",
      phone_help: "Reach 127.0.0.1 from the phone through your own forwarding (e.g. USB Android: adb reverse tcp:{port} tcp:{port}). " +
        "If you open it under a name other than 127.0.0.1 / localhost, start the server with --allow-host <name>. " +
        "The card text and the token travel to wherever you forward. The token changes on every launch.",
      settings: "Settings", set_dwell: "Dwell (s, 0 = click only)", set_scan: "Scan (s, off = none)",
      set_lang: "Language", set_sound: "Sound", off: "off", on: "on", auto: "auto",
      no_token: "No token. Open the URL (with #t=) printed by server.py",
      bad_token: "Wrong token. If the server was restarted, open the new URL",
      offline: "Cannot reach the board server (reconnecting)",
      stale: "The screen was out of date. Please choose again",
      light_idle_prompt: "Claude is waiting for your next instruction (terminal)",
      light_elicitation_url_dialog: "Decide in the terminal whether to open the link",
      light_default: "A signal from Claude Code",
      dest_session: "for this session", dest_localSettings: "this project, this machine, permanently",
      dest_projectSettings: "this project's shared settings, permanently (may be committed)",
      dest_userSettings: "all projects, permanently",
      sugg_allow: "Don't ask again", sugg_deny: "Deny from now on", sugg_ask: "Always ask",
      sugg_mode: "Change mode", sugg_dirs: "Also allow this folder",
      mode_acceptEdits: "don't ask for edits (acceptEdits)", mode_default: "default",
      mode_plan: "plan", mode_dontAsk: "deny without asking (dontAsk)", mode_auto: "auto",
      reasons: ["Please do it another way.", "Not needed right now.", "Please explain first."]
    }
  };

  var INPUTS = ["dwell", "key", "switch", "touch", "click"];
  var FIXED = { permission: "stop", question: "skip", elicitation: "cancel" };

  function fmt(s, vars) {
    return String(s).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m;
    });
  }

  /* 頁に出す字 = 文字列か {"ja": …, "en": …} */
  function tx(v, lang) {
    if (v === null || v === undefined) return "";
    if (typeof v === "string") return v;
    if (typeof v === "object") {
      if (typeof v[lang] === "string") return v[lang];
      if (typeof v.en === "string") return v.en;
      if (typeof v.ja === "string") return v.ja;
      return "";
    }
    return String(v);
  }

  function pickLang(param, navLang) {
    if (param === "ja" || param === "en") return param;
    return String(navLang || "").toLowerCase().indexOf("ja") === 0 ? "ja" : "en";
  }

  /* ?dwell= (秒) → ms。0 = 頁の滞留を止める。既定 1.0 秒・0.3〜5 秒に収める。 */
  function parseDwell(v) {
    if (v === null || v === undefined || v === "") return 1000;
    var x = parseFloat(v);
    if (!isFinite(x)) return 1000;
    if (x <= 0) return 0;
    if (x > 10) x = x / 1000;               /* ms で書かれた時 */
    return Math.round(Math.min(5, Math.max(0.3, x)) * 1000);
  }

  /* ?scan= (秒) → ms。無い・0・off = 走査なし。値なし・on = 1.5 秒。0.5〜10 秒に収める。 */
  function parseScan(v) {
    if (v === null || v === undefined) return 0;
    if (v === "" || v === "on" || v === "true") return 1500;
    if (v === "off" || v === "false") return 0;
    var x = parseFloat(v);
    if (!isFinite(x) || x <= 0) return 0;
    if (x > 20) x = x / 1000;
    return Math.round(Math.min(10, Math.max(0.5, x)) * 1000);
  }

  function mmss(sec) {
    var s = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(s / 60);
    var r = s % 60;
    return m + ":" + (r < 10 ? "0" : "") + r;
  }

  /* 滞留 = 同じ釦の上に ms 留まると押す。外れても grace のうちに戻れば数え続ける。
   * block(key) = その釦は pointer が一度外へ出るまで数えない (押した直後・表示の世代が変わった時)。 */
  function Dwell(ms, graceMs) {
    this.ms = ms;
    this.grace = graceMs === undefined ? 150 : graceMs;
    this.reset();
  }
  Dwell.prototype.reset = function () {
    this.target = null;
    this.start = 0;
    this.outSince = null;
    this.blocked = null;
  };
  Dwell.prototype.block = function (key) {
    this.target = null;
    this.outSince = null;
    this.blocked = key || null;
  };
  /* key = いま pointer の下の釦 (無ければ null)。返り = {target, progress (0〜1), fire} */
  Dwell.prototype.update = function (key, now) {
    var none = { target: null, progress: 0, fire: false };
    if (!(this.ms > 0)) return none;
    if (this.blocked !== null) {
      if (key === this.blocked) return none;
      this.blocked = null;
    }
    if (key === null || key === undefined) {
      if (this.target === null) return none;
      if (this.outSince === null) this.outSince = now;
      if (now - this.outSince > this.grace) {
        this.target = null;
        this.outSince = null;
        return none;
      }
      return { target: this.target, progress: Math.min(1, (now - this.start) / this.ms), fire: false };
    }
    if (key !== this.target) {
      this.target = key;
      this.start = now;
      this.outSince = null;
      return { target: key, progress: 0, fire: false };
    }
    this.outSince = null;
    var p = (now - this.start) / this.ms;
    if (p >= 1) {
      this.target = null;
      this.blocked = key;                     /* 見続けても 2 回押さない */
      return { target: key, progress: 1, fire: true };
    }
    return { target: key, progress: p, fire: false };
  };

  /* 1 鍵の走査 = ms ごとに次へ。restart で頭から。 */
  function Scan(ms) {
    this.ms = ms;
    this.t0 = 0;
  }
  Scan.prototype.restart = function (now) { this.t0 = now; };
  Scan.prototype.index = function (now, n) {
    if (!(this.ms > 0) || !(n > 0)) return -1;
    return Math.floor(Math.max(0, now - this.t0) / this.ms) % n;
  };

  function reasonsOf(payload, lang) {
    var r = payload && payload.reasons;
    if (Array.isArray(r) && r.length) return r.map(function (x) { return tx(x, lang); });
    return I18N[lang].reasons.slice();
  }

  /* 「次から訊かない」に出す suggestion = 先頭から 2 件まで・bypassPermissions へ移す物は出さない (§2.1) */
  function visibleSuggestions(list) {
    var out = [];
    if (!Array.isArray(list)) return out;
    for (var i = 0; i < list.length && out.length < 2; i++) {
      var s = list[i];
      if (!s || typeof s !== "object") continue;
      if (s.type === "setMode" && s.mode === "bypassPermissions") continue;
      out.push({ index: i, s: s });
    }
    return out;
  }

  function suggestionLabel(s, lang) {
    var L = I18N[lang];
    if (s && s.label !== undefined) return tx(s.label, lang);
    var dest = s.destination ? (L["dest_" + s.destination] || s.destination) : "";
    var tail = dest ? " — " + dest : "";
    if (s.type === "addRules") {
      var rules = (Array.isArray(s.rules) ? s.rules : []).map(function (r) {
        if (r && typeof r.toolName === "string") {
          return r.ruleContent ? r.toolName + "(" + r.ruleContent + ")" : r.toolName;
        }
        return JSON.stringify(r);
      }).join(", ");
      var verb = s.behavior === "deny" ? L.sugg_deny : (s.behavior === "ask" ? L.sugg_ask : L.sugg_allow);
      return verb + ": " + rules + tail;
    }
    if (s.type === "setMode") return L.sugg_mode + ": " + (L["mode_" + s.mode] || String(s.mode)) + tail;
    if (s.type === "addDirectories" && Array.isArray(s.directories)) {
      return L.sugg_dirs + ": " + s.directories.join(", ") + tail;
    }
    var rest = {};
    Object.keys(s || {}).forEach(function (k) { if (k !== "type" && k !== "destination") rest[k] = s[k]; });
    return String(s.type) + ": " + JSON.stringify(rest) + tail;
  }

  function steps(card) {
    var p = card.payload || {};
    if (card.kind === "question") return Array.isArray(p.questions) ? p.questions : [];
    if (card.kind === "elicitation") return Array.isArray(p.fields) ? p.fields : [];
    return [];
  }

  function isMulti(card, st) {
    return card.kind === "question" ? !!(st && st.multiSelect) : !!(st && st.multi);
  }

  /* 1 押しで送れない札 = 複数の問い・複数選択 → 最後に確かめの画面と「送る」 */
  function needConfirm(card) {
    var st = steps(card);
    if (st.length > 1) return true;
    return st.some(function (s) { return isMulti(card, s); });
  }

  function newUi(cardId) {
    return { cardId: cardId || null, step: 0, sub: null, picks: [], marks: [] };
  }

  function copyUi(ui) {
    return { cardId: ui.cardId, step: ui.step, sub: ui.sub, picks: ui.picks.slice(), marks: ui.marks.slice() };
  }

  /* 取り消しで shown へ戻った時の画面 = 確かめの画面がある札はそこへ・無ければ頭 */
  function uiAfterUndo(card, ui) {
    var u = newUi(ui.cardId);
    if (needConfirm(card) && ui.picks.length >= steps(card).length) {
      u.picks = ui.picks.slice();
      u.step = steps(card).length;
    }
    return u;
  }

  function blocksOf(list, lang) {
    if (!Array.isArray(list)) return [];
    return list.filter(function (b) { return b && typeof b === "object"; }).map(function (b) {
      return { label: tx(b.label, lang), text: tx(b.text, lang), mono: !!b.mono };
    });
  }

  function optionLabels(opts, picks, lang, emptyText) {
    var labels = (picks || []).map(function (i) { return tx(((opts || [])[i] || {}).label, lang); });
    return labels.length ? labels.join(", ") : emptyText;
  }

  /* 画面の形 = 頭・本文・問い・釦の並び (固定の位置の釦と「端末で答える」は別に頁が置く) */
  function buildScreen(card, ui, lang) {
    var L = I18N[lang];
    var p = card.payload || {};
    var out = { head: "", text: "", blocks: [], question: null, summary: null, options: [],
                fixedLabel: L["fixed_" + card.kind] || "" };
    if (card.kind === "permission") {
      out.head = tx(p.head, lang);
      out.text = tx(p.text, lang);
      out.blocks = blocksOf(p.blocks, lang);
      if (ui.sub === "deny") {
        out.question = L.deny_title;
        reasonsOf(p, lang).forEach(function (r, j) { out.options.push({ key: "reason:" + j, label: r }); });
        out.options.push({ key: "back", label: L.back, aux: true });
      } else {
        out.options.push({ key: "allow_once", label: L.allow_once });
        visibleSuggestions(p.suggestions).forEach(function (v) {
          out.options.push({ key: "sugg:" + v.index, label: suggestionLabel(v.s, lang) });
        });
        out.options.push({ key: "deny", label: L.deny + " …" });
      }
      return out;
    }
    var st = steps(card);
    var n = st.length;
    if (card.kind === "elicitation") {
      out.head = tx(p.head, lang);
      out.text = tx(p.text, lang);
    }
    if (ui.step < n) {
      var cur = st[ui.step] || {};
      var multi = isMulti(card, cur);
      var defs = Array.isArray(cur.default) ? cur.default : [];
      if (card.kind === "question") {
        out.head = tx(cur.header, lang);
        out.question = tx(cur.question, lang);
      } else {
        out.question = tx(cur.title, lang);
      }
      if (card.kind === "elicitation" && n === 1 && out.question === out.text) out.question = "";
      if (n > 1) out.question = (out.question ? out.question + "  " : "") + "(" + (ui.step + 1) + " / " + n + ")";
      (Array.isArray(cur.options) ? cur.options : []).forEach(function (o, i) {
        o = o || {};
        out.options.push({ key: "opt:" + i, label: tx(o.label, lang), desc: tx(o.description, lang),
                           def: defs.indexOf(i) >= 0, marked: multi ? ui.marks.indexOf(i) >= 0 : null });
      });
      if (card.kind === "elicitation" && !cur.required && !multi) {
        out.options.push({ key: "skipf", label: L.skip_field, aux: true });
      }
      if (multi) {
        var need = card.kind === "question" || !!cur.required;
        out.options.push({ key: "next", label: L.next, aux: true, disabled: need && ui.marks.length === 0 });
      }
    } else {
      out.question = L.confirm;
      out.summary = st.map(function (s, k) {
        var name = card.kind === "question" ? tx(s.header || s.question, lang) : tx(s.title || s.name, lang);
        return name + ": " + optionLabels(s.options, ui.picks[k], lang, L.empty_field);
      });
      out.options.push({ key: "send", label: L.send });
      out.options.push({ key: "restart", label: L.restart, aux: true });
    }
    if (card.kind === "elicitation") out.options.push({ key: "decline", label: L.decline, aux: true });
    return out;
  }

  /* 釦を押した結果 = {send: choice} (板へ送る) か {ui, gen} (頁の中で画面を進める) か null */
  function pressKey(card, ui, key) {
    if (key === "fixed") return { send: { type: FIXED[card.kind] } };
    if (key === "terminal") return { send: { type: "terminal" } };
    var u = copyUi(ui);
    if (card.kind === "permission") {
      if (key === "allow_once") return { send: { type: "allow_once" } };
      if (key.indexOf("sugg:") === 0) return { send: { type: "allow_always", suggestion: parseInt(key.slice(5), 10) } };
      if (key === "deny") { u.sub = "deny"; return { ui: u, gen: true }; }
      if (key === "back") { u.sub = null; return { ui: u, gen: true }; }
      if (key.indexOf("reason:") === 0) return { send: { type: "deny", reason: parseInt(key.slice(7), 10) } };
      return null;
    }
    var st = steps(card);
    var n = st.length;
    var type = card.kind === "question" ? "answer" : "accept";
    if (key === "decline" && card.kind === "elicitation") return { send: { type: "decline" } };
    if (key === "send") return { send: { type: type, picks: u.picks.slice(0, n).map(function (x) { return (x || []).slice(); }) } };
    if (key === "restart") { u.step = 0; u.picks = []; u.marks = []; return { ui: u, gen: true }; }
    if (u.step >= n) return null;
    var cur = st[u.step] || {};
    var multi = isMulti(card, cur);
    var advance = function (pick) {
      u.picks[u.step] = pick;
      u.marks = [];
      if (!needConfirm(card)) return { send: { type: type, picks: [pick] } };
      u.step += 1;
      return { ui: u, gen: true };
    };
    if (key.indexOf("opt:") === 0) {
      var i = parseInt(key.slice(4), 10);
      var opt = (Array.isArray(cur.options) ? cur.options : [])[i];
      if (!opt) return null;
      if (opt.terminal) return { send: { type: "terminal" } };
      if (multi) {
        var m = u.marks.slice();
        var at = m.indexOf(i);
        if (at >= 0) m.splice(at, 1); else m.push(i);
        m.sort(function (a, b) { return a - b; });
        u.marks = m;
        return { ui: u, gen: false };          /* 印を付けるだけ = 並びは変わらない */
      }
      return advance([i]);
    }
    if (key === "next" && multi) {
      if (u.marks.length === 0 && (card.kind === "question" || cur.required)) return null;
      return advance(u.marks.slice());
    }
    if (key === "skipf" && card.kind === "elicitation" && !cur.required) return advance([]);
    return null;
  }

  function choiceLabel(card, choice, lang) {
    var L = I18N[lang];
    var p = card.payload || {};
    if (!choice) return "";
    switch (choice.type) {
      case "allow_once": return L.allow_once;
      case "allow_always": {
        var s = (Array.isArray(p.suggestions) ? p.suggestions : [])[choice.suggestion];
        return s ? suggestionLabel(s, lang) : L.sugg_allow;
      }
      case "deny": return L.deny + ": " + (reasonsOf(p, lang)[choice.reason] || "");
      case "stop": case "skip": case "cancel": return L["fixed_" + card.kind] || "";
      case "terminal": return L.terminal;
      case "decline": return L.decline;
      case "answer": case "accept": {
        var st = steps(card);
        return (choice.picks || []).map(function (pk, k) {
          return optionLabels((st[k] || {}).options, pk, lang, L.empty_field);
        }).join(" / ");
      }
      default: return "";
    }
  }

  /* 表示の世代の鍵 = 札の id・状態・表示の seq・設問の番号・釦の並び・言葉 (§4.2) */
  function viewKey(card, ui, lang) {
    if (!card) return "none|" + lang;
    return [card.id, card.state, card.view_seq, ui.step, ui.sub || "", lang].join("|");
  }

  function statsText(stats, lang, elapsedSec) {
    var L = I18N[lang];
    var P = (stats && stats.presses) || {};
    var parts = [L.in_dwell + " " + (P.dwell || 0), L.in_key + " " + (P.key || 0),
                 L.in_switch + " " + (P.switch || 0), L.in_touch + " " + (P.touch || 0)];
    if (P.click) parts.push(L.in_click + " " + P.click);
    var line = fmt(L.stats_line, { n: (stats && stats.total) || 0, parts: parts.join(lang === "ja" ? "・" : " · "),
                                   m: (stats && stats.answers) || 0, t: mmss(elapsedSec) });
    var cards = (stats && stats.cards) || [];
    if (cards.length) {
      line += (lang === "ja" ? "・" : " · ") + L.per_card + " " +
        cards.slice(-5).map(function (c) { return String(c.sec); }).join(lang === "ja" ? "・" : ", ");
    }
    return line;
  }

  function endText(last, lang) {
    var L = I18N[lang];
    if (!last) return "";
    var t = L["end_" + last.end] || "";
    if (last.end === "disconnected" && last.from_deciding) t += " — " + L.not_delivered;
    return t;
  }

  function lightText(light, lang) {
    var L = I18N[lang];
    if (!light) return "";
    var fixed = L["light_" + light.type];
    var msg = light.message || light.title || "";
    if (fixed) return msg ? fixed + " — " + msg : fixed;
    return msg || L.light_default;
  }

  function zeroPresses() {
    var o = {};
    INPUTS.forEach(function (k) { o[k] = 0; });
    return o;
  }

  var api = {
    I18N: I18N, INPUTS: INPUTS, FIXED: FIXED, fmt: fmt, tx: tx, pickLang: pickLang,
    parseDwell: parseDwell, parseScan: parseScan, mmss: mmss, Dwell: Dwell, Scan: Scan,
    reasonsOf: reasonsOf, visibleSuggestions: visibleSuggestions, suggestionLabel: suggestionLabel,
    steps: steps, needConfirm: needConfirm, newUi: newUi, uiAfterUndo: uiAfterUndo,
    buildScreen: buildScreen, pressKey: pressKey, choiceLabel: choiceLabel, viewKey: viewKey,
    statsText: statsText, endText: endText, lightText: lightText, zeroPresses: zeroPresses
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BlemmaCore = api;
})(typeof self !== "undefined" ? self : this);
