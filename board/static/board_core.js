/* BLEMMA の板の頁 = 純粋な計算だけ (DOM・通信なし)。設計 = docs/design.md §4。
 * ブラウザでは window.BlemmaCore、node では require() で読める (手で確かめる時に使う)。 */
(function (root) {
  "use strict";

  var I18N = {
    ja: {
      kind_permission: "権限の確認", kind_question: "Claude の質問", kind_elicitation: "MCP の問い",
      allow_once: "許可 (今回)", deny: "拒否", deny_title: "拒否の理由を選んでください", back: "前の画面へ",
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
      more: "▼ 続き (↓)", more_top: "▲ 先頭へ (↓)", copy: "コピー", copied: "コピーしました", copy_failed: "コピーできません", change: "変更", double_hint: "もう 1 回で決まります", digit_again: "同じ数字をもう 1 回押すと決まります (次から訊かない)", key_again: "同じキーをもう 1 回押すと決まります (次から訊かない)",
      set_click: "押し方", click_double: "2 回で決まる", click_single: "1 回で決まる",
      phone_help: "携帯は利用者の転送で 127.0.0.1 へ届けます (例: USB の Android = adb reverse tcp:{port} tcp:{port})。" +
        "127.0.0.1 / localhost 以外の名で開く時は、server を --allow-host <名> で起こしてください。" +
        "転送の先へ札の本文と token が渡ります。token は起動ごとに替わります。",
      settings: "設定", set_dwell: "視線で押す (見つめる秒)", set_scan: "走査 (秒・切 = なし)",
      set_lang: "言葉", set_sound: "音", off: "切", on: "入", auto: "自動",
      set_mode: "表示", set_scale: "全体の倍率", set_font: "文字の大きさ", set_theme: "配色", set_desc: "解説",
      set_key: "スイッチのキー", set_trail: "視線の点", set_face: "字体", face_yuji: "佑字 粛", face_mincho: "明朝", face_gothic: "ゴシック",
      size_s: "小", size_m: "標準", size_l: "やや大", size_xl: "大", size_xxl: "特大",
      set_pos: "窓の位置", pos_keep: "そのまま", pos_br: "右下", pos_bl: "左下", pos_tr: "右上", pos_tl: "左上",
      set_clear: "扇の周りを透かす (Windows)", pip_off: "固定を外す", small: "扇 (OhGi)", large: "大きな板",
      to_light: "明るい配色へ", to_dark: "暗い配色へ", light: "明るい", dark: "暗い", contrast: "高コントラスト", pip: "常に手前", pip_back: "元の窓へ",
      pip_error: "常に手前を開けませんでした", idle_line: "Claude が訊くと、ここに表示します",
      no_token: "token がありません。server.py の端末に出た URL (#t= つき) で開いてください",
      bad_token: "token が違います。server を起こし直した時は、新しい URL で開いてください",
      offline: "板の server に繋がりません (繋ぎ直しています)",
      stale: "画面が古くなっていました。もう一度選んでください",
      undo_late: "取り消しは間に合いませんでした (答えは渡りました)",
      undo_going: "取り消しは間に合いませんでした (答えを渡している所です)",
      omitted: "この問いには、ここに出せない任意の欄が {n} 個あります ({names})。書く時は「端末で答える」を選んでください",
      light_permission_prompt: "権限の確認が届いています",
      light_elicitation_dialog: "問いが届いています",
      light_agent_needs_input: "Claude があなたの入力を待っています",
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
      more: "▼ More (↓)", more_top: "▲ Back to top (↓)", copy: "Copy", copied: "Copied", copy_failed: "Could not copy", change: "Change", double_hint: "Click again to confirm", digit_again: "Press the same number again to confirm (Don't ask again)", key_again: "Press the same key again to confirm (Don't ask again)",
      set_click: "Confirm with", click_double: "Two clicks", click_single: "One click",
      phone_help: "Reach 127.0.0.1 from the phone through your own forwarding (e.g. USB Android: adb reverse tcp:{port} tcp:{port}). " +
        "If you open it under a name other than 127.0.0.1 / localhost, start the server with --allow-host <name>. " +
        "The card text and the token travel to wherever you forward. The token changes on every launch.",
      settings: "Settings", set_dwell: "Press by gaze (seconds)", set_scan: "Scan (s, off = none)",
      set_lang: "Language", set_sound: "Sound", off: "off", on: "on", auto: "auto",
      set_mode: "View", set_scale: "Overall scale", set_font: "Text size", set_theme: "Theme", set_desc: "Descriptions",
      set_key: "Switch key", set_trail: "Pointer trail", set_face: "Typeface", face_yuji: "Yuji Syuku", face_mincho: "Serif", face_gothic: "Sans serif",
      size_s: "Small", size_m: "Normal", size_l: "Large", size_xl: "Larger", size_xxl: "Largest",
      set_pos: "Window position", pos_keep: "Keep", pos_br: "Bottom right", pos_bl: "Bottom left", pos_tr: "Top right", pos_tl: "Top left",
      set_clear: "See through around the fan (Windows)", pip_off: "Unpin", small: "OhGi", large: "Large board",
      to_light: "Switch to light", to_dark: "Switch to dark", light: "Light", dark: "Dark", contrast: "High contrast", pip: "Always on top", pip_back: "Return to window",
      pip_error: "Could not open always on top", idle_line: "Questions from Claude appear here",
      no_token: "No token. Open the URL (with #t=) printed by server.py",
      bad_token: "Wrong token. If the server was restarted, open the new URL",
      offline: "Cannot reach the board server (reconnecting)",
      stale: "The screen was out of date. Please choose again",
      undo_late: "Too late to undo: the answer was handed over",
      undo_going: "Too late to undo: the answer is being handed over",
      omitted: "{n} optional field(s) cannot be shown here ({names}). Choose the terminal to fill them in",
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

  var OPTION_DEFAULTS = { dwell: "0", scan: "off", key: "Space", lang: "auto", sound: "off",
    mode: "large", scale: 1, font: 1, theme: "auto", desc: "on", trail: "off", click: "double", face: "yuji", pos: "keep", clear: "off" };

  function parseOptions(query, saved) {
    var q = new URLSearchParams(query), out = {};
    saved = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    Object.keys(OPTION_DEFAULTS).forEach(function (key) {
      var fallback = OPTION_DEFAULTS[key];
      var v = q.has(key) ? q.get(key) : Object.prototype.hasOwnProperty.call(saved, key) ? saved[key] : fallback;
      var s = typeof v === "string" || typeof v === "number" ? String(v) : "!invalid";
      var enums = {pos: ["keep", "br", "bl", "tr", "tl"], click: ["double", "single"], face: ["yuji", "mincho", "gothic"], mode: ["small", "large"], lang: ["auto", "ja", "en"], theme: ["auto", "light", "dark", "contrast"]};
      if (enums[key]) out[key] = enums[key].indexOf(s) >= 0 ? s : fallback;
      else if (["sound", "desc", "trail", "clear"].indexOf(key) >= 0) {
        out[key] = ["on", "true", "1", ""].indexOf(s) >= 0 ? "on" :
          ["off", "false", "0"].indexOf(s) >= 0 ? "off" : fallback;
      } else if (key === "key") {
        out[key] = s === " " ? "Space" : /^(?:[A-Za-z0-9]|Space|Enter|NumpadEnter|Tab|Escape|Backspace|Arrow(?:Left|Right|Up|Down)|F(?:[1-9]|1[0-9]|2[0-4])|Key[A-Z]|Digit[0-9]|Numpad[0-9])$/.test(s) ? s : fallback;
      } else {
        var x = /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(s) ? Number(s) : NaN;
        if (key === "scan" && ["", "on", "true"].indexOf(s) >= 0) x = 1.5;
        if (key === "scan" && ["off", "false"].indexOf(s) >= 0) x = 0;
        if ((key === "dwell" && x > 10) || (key === "scan" && x > 20)) x /= 1000;
        var lo = {scale: .75, font: .8, dwell: .3, scan: .5}[key];
        var hi = {scale: 2, font: 2, dwell: 5, scan: 10}[key];
        out[key] = Number.isFinite(x) && (x >= lo && x <= hi || x === 0 && (key === "scan" || key === "dwell")) ?
          (key === "scale" || key === "font" ? x : key === "scan" && x === 0 ? "off" : String(x)) : fallback;
      }
    });
    return out;
  }

  /* 窓の名。小窓は「BLEMMA · 扇 (OhGi)」で、既定でない port の板は名に port を足す
   * (板の側の window_win.title_for と同じ決まり = 別の port で起こした板の窓を取り違えない)。 */
  var WINDOW_TITLE = "BLEMMA · 扇 (OhGi)", DEFAULT_PORT = "8765";
  function windowTitle(mode, port) {
    if (mode !== "small") return "BLEMMA";
    port = String(port || "80");
    return port === DEFAULT_PORT ? WINDOW_TITLE : WINDOW_TITLE + " · " + port;
  }

  /* 板の見張り (/pending) の調子。1 回の失敗では「板が止まった」と言わない =
   * 続けて limit 回落ちた時だけ、最初に落ちた時刻を返す (それまでは null)。1 回でも通れば頭に戻る。 */
  function Health(limit) {
    this.limit = limit || 3;
    this.ok();
  }
  Health.prototype.ok = function () { this.fails = 0; this.since = null; };
  Health.prototype.fail = function (now) {
    if (!this.fails) this.since = now;
    this.fails += 1;
  };
  Health.prototype.goneSince = function () { return this.fails >= this.limit ? this.since : null; };

  /* 扇の 2 回押し。1 回目は選ぶだけ = 同じ羽根を ms のうちにもう 1 回押した時だけ決まる。
   * arm = 選んである羽根 {key, at} か null (札が替わった・描き直した・時間が切れた時は null に戻っている)。 */
  function armStep(arm, key, now, ms) {
    if (arm && arm.key === key && now - arm.at <= ms) return { confirm: true, arm: null };
    return { confirm: false, arm: { key: key, at: now } };
  }

  /* 窓を動かす位置の刻み (CSS の画素)。表示倍率が 125%・150%・175% の画面では、物理の画素で割り切れない位置へ
   * 窓を動かすたびに、ブラウザが窓の矩形を外側へ丸めて 1 画素ずつ大きくする。割り切れる位置だけへ動かせば育たない。
   * ratio = devicePixelRatio。整数倍は 1、1.5・2.5 倍は 2、それ以外 (1.25・1.75 倍や、頁を拡大している時) は 4。 */
  function gridStep(ratio) {
    var r = Number(ratio);
    if (!(r > 0) || !isFinite(r)) return 1;
    if (Math.abs(r - Math.round(r)) < 0.01) return 1;
    if (Math.abs(r * 2 - Math.round(r * 2)) < 0.01) return 2;
    return 4;
  }

  /* 位置を刻みの倍数へ寄せる (負の座標 = 左や上の画面でも同じ)。 */
  function snap(value, step) {
    var v = Math.round(Number(value) / step) * step;
    return v === 0 ? 0 : v;           /* -0 を渡さない */
  }

  function mmss(sec) {
    var s = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(s / 60);
    var r = s % 60;
    return m + ":" + (r < 10 ? "0" : "") + r;
  }

  /* 滞留 = 同じ釦の上に ms 留まると押す。外れても grace のうちに戻れば数え続ける。
   * 外れた長さは戻った時にも見る (grace を超えていれば頭から数え直す)。こま (update の呼び) の間が grace より
   * 長く空いた時も (頁が隠れた・描画が止まった) その間 留まっていたか分からない = 頭から数え直す (§4.2)。
   * block(key) = その釦は pointer が一度外へ出るまで数えない (押した直後・表示の世代が変わった時)。外へ出たと見るのは、
   * 釦の無い所に grace より長く居た時か、別の釦に入った時 = 数える側と同じ揺れの許し (羽根の縁に休む視線が 1 こまだけ
   * 帯へ揺れても、見ていない (入り直していない) 羽根を 1 秒後に押さない)。 */
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
    this.blockedOut = null;                   /* 守りの釦の外 (釦なし) に出た時刻 */
    this.last = null;
  };
  Dwell.prototype.block = function (key) {
    this.target = null;
    this.outSince = null;
    this.blocked = key || null;
    this.blockedOut = null;
  };
  /* key = いま pointer の下の釦 (無ければ null)。返り = {target, progress (0〜1), fire} */
  Dwell.prototype.update = function (key, now) {
    var none = { target: null, progress: 0, fire: false };
    if (!(this.ms > 0)) return none;
    var gap = this.last === null ? 0 : now - this.last;
    this.last = now;
    if (gap > this.grace) {                   /* こまが途切れた = その間は数えない */
      this.target = null;
      this.outSince = null;
    }
    if (this.blocked !== null) {
      if (key === this.blocked) { this.blockedOut = null; return none; }
      if (key === null || key === undefined) {  /* 釦なし = grace の内は守りを保つ (縁の揺れ)・grace を超えて続いたら解く */
        if (this.blockedOut === null) this.blockedOut = now;
        if (now - this.blockedOut <= this.grace) return none;
      }
      this.blocked = null;                    /* 別の釦に入った時は、すぐ解く */
      this.blockedOut = null;
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
    if (key !== this.target || (this.outSince !== null && now - this.outSince > this.grace)) {
      this.target = key;                      /* 入った・grace より長く外れてから戻った = 頭から数える */
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

  /* 1 鍵の走査 = ms ごとに次へ。restart で頭から。restart に先の時刻を渡すと、その時刻までは何も光らせない
   * (-1 を返す) = 表示が替わった直後の間 (頁の SETTLE_MS) は、光が無く押しても何も起きない。 */
  function Scan(ms) {
    this.ms = ms;
    this.t0 = 0;
  }
  Scan.prototype.restart = function (now) { this.t0 = now; };
  Scan.prototype.index = function (now, n) {
    if (!(this.ms > 0) || !(n > 0) || now < this.t0) return -1;
    return Math.floor((now - this.t0) / this.ms) % n;
  };

  function reasonsOf(payload, lang) {
    var r = payload && payload.reasons;
    if (Array.isArray(r) && r.length) return r.map(function (x) { return tx(x, lang); });
    return I18N[lang].reasons.slice();
  }

  /* 「次から訊かない」に出す suggestion = 先頭から 2 件まで・bypassPermissions・auto へ移す物は出さない (§2.1) */
  function visibleSuggestions(list) {
    var out = [];
    if (!Array.isArray(list)) return out;
    for (var i = 0; i < list.length && out.length < 2; i++) {
      var s = list[i];
      if (!s || typeof s !== "object") continue;
      if (s.type === "setMode" && (s.mode === "bypassPermissions" || s.mode === "auto")) continue;
      out.push({ index: i, s: s });
    }
    return out;
  }

  /* 異体字セレクタが正当になる前の字の表 = 番号の範囲 [始, 終] の昇順 (hooks/permission.py の _EMOJI_BASES・_IDEOGRAPH_BASES と
     同じ物 = 試験で照合)。性質の名でなく表で持つ = 処理系と Python の Unicode の版で網が変わらない。EMOJI_BASES = node 22
     (Unicode 17.0) の \p{Emoji} から生成・IDEOGRAPH_BASES = CJK 統合漢字 (Unified_Ideograph) の block */
  var EMOJI_BASES = [
    [0x23, 0x23], [0x2A, 0x2A], [0x30, 0x39], [0xA9, 0xA9], [0xAE, 0xAE], [0x203C, 0x203C], [0x2049, 0x2049],
    [0x2122, 0x2122], [0x2139, 0x2139], [0x2194, 0x2199], [0x21A9, 0x21AA], [0x231A, 0x231B], [0x2328, 0x2328],
    [0x23CF, 0x23CF], [0x23E9, 0x23F3], [0x23F8, 0x23FA], [0x24C2, 0x24C2], [0x25AA, 0x25AB], [0x25B6, 0x25B6],
    [0x25C0, 0x25C0], [0x25FB, 0x25FE], [0x2600, 0x2604], [0x260E, 0x260E], [0x2611, 0x2611], [0x2614, 0x2615],
    [0x2618, 0x2618], [0x261D, 0x261D], [0x2620, 0x2620], [0x2622, 0x2623], [0x2626, 0x2626], [0x262A, 0x262A],
    [0x262E, 0x262F], [0x2638, 0x263A], [0x2640, 0x2640], [0x2642, 0x2642], [0x2648, 0x2653], [0x265F, 0x2660],
    [0x2663, 0x2663], [0x2665, 0x2666], [0x2668, 0x2668], [0x267B, 0x267B], [0x267E, 0x267F], [0x2692, 0x2697],
    [0x2699, 0x2699], [0x269B, 0x269C], [0x26A0, 0x26A1], [0x26A7, 0x26A7], [0x26AA, 0x26AB], [0x26B0, 0x26B1],
    [0x26BD, 0x26BE], [0x26C4, 0x26C5], [0x26C8, 0x26C8], [0x26CE, 0x26CF], [0x26D1, 0x26D1], [0x26D3, 0x26D4],
    [0x26E9, 0x26EA], [0x26F0, 0x26F5], [0x26F7, 0x26FA], [0x26FD, 0x26FD], [0x2702, 0x2702], [0x2705, 0x2705],
    [0x2708, 0x270D], [0x270F, 0x270F], [0x2712, 0x2712], [0x2714, 0x2714], [0x2716, 0x2716], [0x271D, 0x271D],
    [0x2721, 0x2721], [0x2728, 0x2728], [0x2733, 0x2734], [0x2744, 0x2744], [0x2747, 0x2747], [0x274C, 0x274C],
    [0x274E, 0x274E], [0x2753, 0x2755], [0x2757, 0x2757], [0x2763, 0x2764], [0x2795, 0x2797], [0x27A1, 0x27A1],
    [0x27B0, 0x27B0], [0x27BF, 0x27BF], [0x2934, 0x2935], [0x2B05, 0x2B07], [0x2B1B, 0x2B1C], [0x2B50, 0x2B50],
    [0x2B55, 0x2B55], [0x3030, 0x3030], [0x303D, 0x303D], [0x3297, 0x3297], [0x3299, 0x3299], [0x1F004, 0x1F004],
    [0x1F0CF, 0x1F0CF], [0x1F170, 0x1F171], [0x1F17E, 0x1F17F], [0x1F18E, 0x1F18E], [0x1F191, 0x1F19A],
    [0x1F1E6, 0x1F1FF], [0x1F201, 0x1F202], [0x1F21A, 0x1F21A], [0x1F22F, 0x1F22F], [0x1F232, 0x1F23A],
    [0x1F250, 0x1F251], [0x1F300, 0x1F321], [0x1F324, 0x1F393], [0x1F396, 0x1F397], [0x1F399, 0x1F39B],
    [0x1F39E, 0x1F3F0], [0x1F3F3, 0x1F3F5], [0x1F3F7, 0x1F4FD], [0x1F4FF, 0x1F53D], [0x1F549, 0x1F54E],
    [0x1F550, 0x1F567], [0x1F56F, 0x1F570], [0x1F573, 0x1F57A], [0x1F587, 0x1F587], [0x1F58A, 0x1F58D],
    [0x1F590, 0x1F590], [0x1F595, 0x1F596], [0x1F5A4, 0x1F5A5], [0x1F5A8, 0x1F5A8], [0x1F5B1, 0x1F5B2],
    [0x1F5BC, 0x1F5BC], [0x1F5C2, 0x1F5C4], [0x1F5D1, 0x1F5D3], [0x1F5DC, 0x1F5DE], [0x1F5E1, 0x1F5E1],
    [0x1F5E3, 0x1F5E3], [0x1F5E8, 0x1F5E8], [0x1F5EF, 0x1F5EF], [0x1F5F3, 0x1F5F3], [0x1F5FA, 0x1F64F],
    [0x1F680, 0x1F6C5], [0x1F6CB, 0x1F6D2], [0x1F6D5, 0x1F6D8], [0x1F6DC, 0x1F6E5], [0x1F6E9, 0x1F6E9],
    [0x1F6EB, 0x1F6EC], [0x1F6F0, 0x1F6F0], [0x1F6F3, 0x1F6FC], [0x1F7E0, 0x1F7EB], [0x1F7F0, 0x1F7F0],
    [0x1F90C, 0x1F93A], [0x1F93C, 0x1F945], [0x1F947, 0x1F9FF], [0x1FA70, 0x1FA7C], [0x1FA80, 0x1FA8A],
    [0x1FA8E, 0x1FAC6], [0x1FAC8, 0x1FAC8], [0x1FACD, 0x1FADC], [0x1FADF, 0x1FAEA], [0x1FAEF, 0x1FAF8]
  ];
  var IDEOGRAPH_BASES = [
    [0x3400, 0x4DBF], [0x4E00, 0x9FFF], [0xFA0E, 0xFA0F], [0xFA11, 0xFA11], [0xFA13, 0xFA14], [0xFA1F, 0xFA1F],
    [0xFA21, 0xFA21], [0xFA23, 0xFA24], [0xFA27, 0xFA29], [0x20000, 0x2A6DF], [0x2A700, 0x2B73F], [0x2B740, 0x2B81F],
    [0x2B820, 0x2CEAF], [0x2CEB0, 0x2EBEF], [0x2EBF0, 0x2EE5F], [0x30000, 0x3134F], [0x31350, 0x323AF]
  ];
  /* キーキャップの土台 (# * 0〜9) = EMOJI_BASES に入るが、この字の後の U+FE0E / FE0F は次がキーキャップの印 U+20E3 の時だけ正当
     (2 + U+FE0F + >f が札で 2>f に見えないように・hooks/permission.py の _KEYCAP_BASES と同じ字) */
  var KEYCAP_BASES = [[0x23, 0x23], [0x2A, 0x2A], [0x30, 0x39]];

  /* 見えない字 (制御の字・書字方向の字・幅ゼロの字など) を ⟨U+XXXX⟩ にして見せる。hooks/permission.py の visible と同じ網
     (種 Cc・Cf・Cs・Zl・Zp + 種では拾えない 6 字 (U+034F・U+115F・U+1160・U+3164・U+FFA0・U+2800) + 異体字セレクタ = U+FE00〜FE0D
     は常に・U+FE0E と FE0F は EMOJI_BASES の字の後でない時と、KEYCAP_BASES の字の後で次が U+20E3 でない時・U+E0100〜E01EF は
     IDEOGRAPH_BASES の字の後でない時・改行とタブは残す)。権限の札の本文は hook で、質問と MCP の札の字と「次から訊かない」の文は
     頁がここで直す (表示だけ = 返す答えは番号のまま) */
  var HIDDEN_RE = (function () {
    var cls = function (ranges) {      /* 表 → 後ろ読みの字の類 (\u{...} の逃がしで組む = source に字を書かない・u 旗) */
      return "[" + ranges.map(function (r) {
        return "\\u{" + r[0].toString(16) + "}-\\u{" + r[1].toString(16) + "}";
      }).join("") + "]";
    };
    try {
      return new RegExp("[\\p{Cc}\\p{Cf}\\p{Cs}\\p{Zl}\\p{Zp}\\u034F\\u115F\\u1160\\u3164\\uFFA0\\u2800\\uFE00-\\uFE0D]|" +
                        "(?<!" + cls(EMOJI_BASES) + ")[\\uFE0E\\uFE0F]|(?<=" + cls(KEYCAP_BASES) + ")[\\uFE0E\\uFE0F](?!\\u20E3)|" +
                        "(?<!" + cls(IDEOGRAPH_BASES) + ")[\\u{E0100}-\\u{E01EF}]", "gu");
    } catch (e) {            /* 古い JS の処理系 = 主な見えない字の範囲だけ (番号で組む = source に見えない字を書かない)。
                                U+FE00〜FE0D は前の字に依らず印なので拾う。U+FE0E / FE0F と U+E0100〜 は前の字を見られない
                                (後ろ読みが無い) ので、この予備では拾わない */
      var ranges = [[0x0, 0x1f], [0x7f, 0x9f], [0xad, 0xad], [0x34f, 0x34f], [0x61c, 0x61c], [0x115f, 0x1160],
                    [0x180e, 0x180e], [0x200b, 0x200f], [0x2028, 0x202e], [0x2060, 0x2064], [0x2066, 0x206f],
                    [0x2800, 0x2800], [0x3164, 0x3164], [0xfe00, 0xfe0d], [0xfeff, 0xfeff], [0xffa0, 0xffa0],
                    [0xfff9, 0xfffb], [0xd800, 0xdfff]];
      var esc = function (n) { var h = n.toString(16); while (h.length < 4) h = "0" + h; return "\\" + "u" + h; };
      return new RegExp("[" + ranges.map(function (r) { return esc(r[0]) + "-" + esc(r[1]); }).join("") + "]", "g");
    }
  })();
  function visibleText(s) {
    return String(s).replace(HIDDEN_RE, function (ch) {
      if (ch === "\n" || ch === "\t") return ch;
      var hex = ch.codePointAt(0).toString(16).toUpperCase();
      while (hex.length < 4) hex = "0" + hex;
      return "⟨U+" + hex + "⟩";
    });
  }

  function suggestionLabel(s, lang) {
    return visibleText(suggestionText(s, lang));
  }

  function suggestionText(s, lang) {
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

  /* 1 欄で送れる最小の選択の数 (欄の必須と最小の選択の数は別・§2.3) = 質問は 1・MCP の問いの任意の欄は 0
   * (空のまま)・必須の複数選択は min_picks (0 か 1・無ければ 1。0 = 印 0 個で「次へ」= 値は [])・必須の単一は 1 */
  function minPicks(card, st) {
    if (card.kind === "question") return 1;
    if (!st || !st.required) return 0;
    if (isMulti(card, st) && (st.min_picks === 0 || st.min_picks === 1)) return st.min_picks;
    return 1;
  }

  /* 1 押しで送れない札 = 複数の問い・複数選択 → 最後に確かめの画面と「送る」 */
  function needConfirm(card) {
    var st = steps(card);
    if (st.length > 1) return true;
    return st.some(function (s) { return isMulti(card, s); });
  }

  /* Small mode reuses the very same actions, including auxiliary choices. */
  function fanEligible(card, ui, screen) {
    if (!card || !ui || !screen || screen.summary) return false;
    if (card.kind !== "permission" && (steps(card).length !== 1 || needConfirm(card) || ui.step !== 0)) return false;
    var blades = screen.options.filter(function (o) { return !o.aux; }).length;   /* 断るなどの補助は羽根の外 */
    return blades >= 2 && blades <= 6;
  }

  /* 折り扇 = 要 (かなめ) を下に置き、骨が左から右へ開く。左端 = 止める・右端 = 端末で答える (どの n でも動かない)。
   * 地紙は内外 2 段。外の帯 = 押す羽根 (一文字)・内の帯 = 押せない書の帯 (見つめた羽根の全文が弧に沿って出る)。
   * 全文を押せる所に書くと、読む視線が他の羽根を押す = 読む所と押す所を分ける。
   * 羽根の字の位置で幅 84 CSS px 以上を保つ (足りない時は小さくせず扇を大きくする)。 */
  /* 透かす時に残す扇の形 = 外の弧と、親骨の先から要の下まで */
  function outlineOf(point, r, first, spread, cx, cy) {
    var out = [];
    for (var i = 0; i <= 40; i++) out.push(point(r, first - 2 + (spread + 4) * i / 40));
    out.push([cx, cy + 16]);
    return out;
  }

  function fanLayout(n) {
    if (!Number.isInteger(n) || n < 2 || n > 6) return null;
    var total = n + 2, spread = 168, step = spread / total, first = -spread / 2;
    var band = 100, script = 90;
    var middle = Math.max(210, Math.ceil(84 / (2 * Math.sin(step * Math.PI / 360))));
    var outer = middle + band / 2, press = outer - band, inner = press - script, depth = band;
    var width = 2 * (outer + 10), height = outer + 40, cx = width / 2, cy = height - 28;
    function point(r, a) {
      return [cx + r * Math.sin(a * Math.PI / 180), cy - r * Math.cos(a * Math.PI / 180)];
    }
    function ring(r, a0, a1) {
      var p0 = point(r, a0), p1 = point(r, a1);
      return "M " + p0.join(" ") + " A " + r + " " + r + " 0 0 1 " + p1.join(" ");
    }
    function band2(r0, r1, a0, a1) {
      var points = [], count = Math.ceil((a1 - a0) / 3);
      for (var j = 0; j <= count; j++) points.push(point(r1, a0 + (a1 - a0) * j / count));
      for (var k = count; k >= 0; k--) points.push(point(r0, a0 + (a1 - a0) * k / count));
      return "polygon(" + points.map(function (v) {
        return (v[0] / width * 100).toFixed(4) + "% " + (v[1] / height * 100).toFixed(4) + "%";
      }).join(",") + ")";
    }
    var parts = [];
    for (var i = 0; i < total; i++) {
      var start = first + i * step;
      var part = { key: i === 0 ? "fixed" : i === total - 1 ? "terminal" : "option",
                   start: start, end: start + step, angle: start + step / 2 };
      if (part.key === "option") part.index = i - 1;
      parts.push(part);
    }
    parts.forEach(function (p) {
      p.polygon = band2(press, outer, p.start, p.end);
      p.label = point(middle, p.angle);
      p.width = 2 * middle * Math.sin(step * Math.PI / 360);
      p.arc = ring(outer - 7, p.start + 0.8, p.end - 0.8);
    });
    var ribs = [];
    for (var r = 0; r <= total; r++) {
      var a = first + r * step, main = r === 0 || r === total;
      ribs.push({ main: main, from: point(main ? 8 : 12, a), to: point(main ? outer + 8 : inner, a) });
    }
    var folds = [];
    for (var f = 0; f < total + 1; f++) {
      folds.push({ from: point(press, first + f * step), to: point(outer, first + f * step) });
    }
    var radii = [press - 28, press - 60];
    /* 左から右の順は visual で持つ。走査の順は option → 止める → 端末 (今の板と同じ) */
    var visual = parts.slice();
    parts.sort(function (x, y) {
      var rank = function (q) { return q.key === "option" ? q.index : q.key === "fixed" ? 100 : 101; };
      return rank(x) - rank(y);
    });
    return { width: width, height: height, cx: cx, cy: cy, inner: inner, press: press, outer: outer, middle: middle,
             depth: depth, step: step, first: first, spread: spread, parts: parts, visual: visual, ribs: ribs, folds: folds,
             paper: band2(inner, outer, first, first + spread),
             scriptBand: band2(inner, press, first, first + spread),
             edges: [ring(outer, first, first + spread), ring(inner, first, first + spread)],
             seam: ring(press, first, first + spread),
             outline: outlineOf(point, outer + 4, first, spread, cx, cy),
             arcs: radii.map(function (q) { return ring(q, -78, 78); }),
             arcLengths: radii.map(function (q) { return q * 156 * Math.PI / 180; }) };
  }

  /* 書の帯に入れる字 = 短い字は大きく 1 行・長い字は 2 行・入らない分は「…」(全文は上に出す) */
  function fanScript(text, lengths) {
    var t = String(text || "");
    function units(c) { return c.charCodeAt(0) < 128 ? 0.56 : 1; }
    function width(str) { var w = 0; for (var i = 0; i < str.length; i++) w += units(str.charAt(i)); return w; }
    function fit(str, room) {
      var w = 0;
      for (var i = 0; i < str.length; i++) { w += units(str.charAt(i)); if (w > room) return i; }
      return str.length;
    }
    if (width(t) * 28 <= lengths[0]) return { size: 28, lines: [t, ""], clipped: false };
    if (width(t) * 22 <= lengths[0]) return { size: 22, lines: [t, ""], clipped: false };
    /* 切れ目が対の字 (絵文字・一部の漢字) の真ん中に来たら、1 つ手前で切る */
    function whole(str, i) { var c = i > 0 ? str.charCodeAt(i - 1) : 0; return c >= 0xD800 && c <= 0xDBFF ? i - 1 : i; }
    var size = 20, n = whole(t, fit(t, lengths[0] / size)), rest = t.slice(n), m = fit(rest, lengths[1] / size);
    var clipped = m < rest.length;
    return { size: size, lines: [t.slice(0, n), clipped ? rest.slice(0, whole(rest, Math.max(0, m - 1))) + "…" : rest], clipped: clipped };
  }

  /* 羽根の印 = 一文字だけ。全文は見つめた時に上へ大きく出す (扇に字を詰めない) */
  function fanMark(index, key, lang) {
    if (lang === "ja") {
      if (key === "fixed") return "止";
      if (key === "terminal") return "戻";
      return "一二三四五六".charAt(index);
    }
    if (key === "fixed") return "Esc";
    if (key === "terminal") return "0";
    return String(index + 1);
  }

  /* 見つめて本文を送る向き = 枠の下寄りで下へ・上寄りで上へ・真ん中は止まる (視線の人は巻物を回せない) */
  function scrollDirection(ratio) {
    if (!(ratio >= 0 && ratio <= 1)) return 0;
    return ratio > 0.68 ? 1 : ratio < 0.32 ? -1 : 0;
  }

  function actionDescription(card, key, lang) {
    var ja = lang === "ja";
    if (key === "terminal") return I18N[lang].terminal_sub;
    if (!card || card.kind !== "permission") return "";
    if (key === "allow_once") return ja ? "この1回だけ許可します" : "Allow this one request";
    if (key === "deny") return ja ? "拒否する理由を選びます" : "Choose a reason to deny";
    if (key === "fixed") return ja ? "この作業を止めます" : "Stop this work";
    return "";
  }

  function priorityState(states, card) {
    if (card) return { state: "waiting on you", reason: "card", stale: false };
    /* あなたの番が最優先。作業中と完了は新しい方 (古い別の会話の「完了」が今の作業を隠さない) */
    var ranks = { "waiting on you": 2, done: 1, working: 1 };
    return (Array.isArray(states) ? states : []).filter(function (s) { return s && ranks[s.state]; })
      .slice().sort(function (a, b) {
        return ranks[b.state] - ranks[a.state] || Number(a.stale) - Number(b.stale) || (a.ago || 0) - (b.ago || 0) ||
          Number(b.state === "done") - Number(a.state === "done");
      })[0] || null;
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

  /* Edit の old と new の違い = 前後の共通部を除いた真ん中。大きく違う時は印を付けない */
  function diffRange(a, b) {
    var max = Math.min(a.length, b.length), p = 0, s = 0;
    while (p < max && a.charAt(p) === b.charAt(p)) p++;
    while (s < max - p && a.charAt(a.length - 1 - s) === b.charAt(b.length - 1 - s)) s++;
    if (p > 0 && /[\uD800-\uDBFF]/.test(a.charAt(p - 1))) p--;        /* サロゲートの対を割らない */
    if (s > 0 && /[\uDC00-\uDFFF]/.test(a.charAt(a.length - s))) s--;
    var longest = Math.max(a.length, b.length), changed = longest - p - s;
    if (changed <= 0 || changed > longest * 0.6) return null;
    return { start: p, oldEnd: a.length - s, newEnd: b.length - s };
  }

  /* 権限の札 = old_string と new_string の違う所に印を付け、短い違いは「変更」の 1 行で先に見せる */
  function markChange(blocks, label) {
    var named = function (name) { return blocks.filter(function (b) { return b.label === name; })[0]; };
    var o = named("old_string"), n = named("new_string");
    if (!o || !n) return;
    var r = diffRange(o.text, n.text);
    if (!r) return;
    o.mark = [r.start, r.oldEnd]; o.markKind = "del";
    n.mark = [r.start, r.newEnd]; n.markKind = "ins";
    var from = Math.max(0, r.start - 3), tail = r.oldEnd > r.start && r.newEnd > r.start ? 1 : 0;  /* 語の途中で切らない */
    var before = o.text.slice(from, r.oldEnd + tail), after = n.text.slice(from, r.newEnd + tail);
    if (before.length > 40 || after.length > 40 || /\n/.test(before + after)) return;
    blocks.unshift({ label: label, text: before + " → " + after, mono: false, change: true });
  }

  function optionLabels(opts, picks, lang, emptyText) {
    var labels = (picks || []).map(function (i) { return visibleText(tx(((opts || [])[i] || {}).label, lang)); });
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
      markChange(out.blocks, L.change);
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
      out.head = visibleText(tx(p.head, lang));
      out.text = visibleText(tx(p.text, lang));
      /* 板で描けない任意の欄 (hook が札から落とした物) は、黙って落とさず知らせる = 人が見ていない欄を空のまま送らせない */
      var omitted = (Array.isArray(p.omitted) ? p.omitted : []).filter(function (x) { return typeof x === "string" && x; });
      if (omitted.length) {
        out.blocks.push({ label: "", text: fmt(L.omitted, { n: omitted.length, names: omitted.map(function (x) { return visibleText(x); }).join(lang === "ja" ? "・" : ", ") }), mono: false });
      }
    }
    if (ui.step < n) {
      var cur = st[ui.step] || {};
      var multi = isMulti(card, cur);
      var defs = Array.isArray(cur.default) ? cur.default : [];
      if (card.kind === "question") {
        out.head = visibleText(tx(cur.header, lang));
        out.question = visibleText(tx(cur.question, lang));
      } else {
        out.question = visibleText(tx(cur.title, lang));
      }
      if (card.kind === "elicitation" && n === 1 && out.question === out.text) out.question = "";
      /* 欄に題と別の説明がある時は、問いの上に出す = 題が「Confirm」だけでも、何を確かめる問いかが見える */
      if (card.kind === "elicitation" && tx(cur.description, lang)) {
        out.blocks.push({ label: "", text: visibleText(tx(cur.description, lang)), mono: false });
      }
      if (n > 1) out.question = (out.question ? out.question + "  " : "") + "(" + (ui.step + 1) + " / " + n + ")";
      (Array.isArray(cur.options) ? cur.options : []).forEach(function (o, i) {
        o = o || {};
        out.options.push({ key: "opt:" + i, label: visibleText(tx(o.label, lang)), desc: visibleText(tx(o.description, lang)),
                           def: defs.indexOf(i) >= 0, marked: multi ? ui.marks.indexOf(i) >= 0 : null });
      });
      if (card.kind === "elicitation" && !cur.required && !multi) {
        out.options.push({ key: "skipf", label: L.skip_field, aux: true });
      }
      if (multi) {
        out.options.push({ key: "next", label: L.next, aux: true, disabled: ui.marks.length < minPicks(card, cur) });
      }
    } else {
      out.question = L.confirm;
      out.summary = st.map(function (s, k) {
        var name = visibleText(card.kind === "question" ? tx(s.header || s.question, lang) : tx(s.title || s.name, lang));
        /* 送る前の確かめでも、欄ごとの説明をもう一度見せる (何に答えたのかを題だけで判断させない) */
        if (card.kind === "elicitation" && tx(s.description, lang)) {
          out.blocks.push({ label: name, text: visibleText(tx(s.description, lang)), mono: false });
        }
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
        return { ui: u, gen: false };          /* 印を付けるだけ = 世代は進めない。走査の列は「次へ」の分だけ伸び縮みする = 光は keepLight で保つ */
      }
      return advance([i]);
    }
    if (key === "next" && multi) {
      if (u.marks.length < minPicks(card, cur)) return null;
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
    /* Claude Code の合図の文は英語で来る = 日本語の板では定型の字だけにする */
    if (fixed) return msg && !(lang === "ja" && /^[\x00-\x7f]*$/.test(msg)) ? fixed + " — " + msg : fixed;
    return msg || L.light_default;
  }

  function zeroPresses() {
    var o = {};
    INPUTS.forEach(function (k) { o[k] = 0; });
    return o;
  }

  /* 押しの数の和 (入力ごと)。 */
  function addPresses(a, b) {
    var o = zeroPresses();
    INPUTS.forEach(function (k) { o[k] = ((a && a[k]) || 0) + ((b && b[k]) || 0); });
    return o;
  }

  function newPressLedger(source) {
    return { source: source, next: 1, pending: [] };
  }

  /* 新しい押しだけに ID を付ける。返された古い束は、ID と数を変えずに次の要求へ乗せる。 */
  function takePressBatches(ledger, presses) {
    var batches = ledger.pending.slice(), next = ledger.next;
    if (INPUTS.some(function (k) { return presses[k] > 0; })) {
      batches.push({ id: ledger.source + ":" + next++, presses: addPresses(null, presses) });
    }
    return { ledger: { source: ledger.source, next: next, pending: [] }, batches: batches };
  }

  function returnPressBatches(ledger, batches) {
    var pending = ledger.pending.slice();
    batches.forEach(function (batch) {
      if (!pending.some(function (p) { return p.id === batch.id; })) pending.push(batch);
    });
    return { source: ledger.source, next: ledger.next, pending: pending };
  }

  function sumPressBatches(batches) {
    return batches.reduce(function (sum, batch) { return addPresses(sum, batch.presses); }, zeroPresses());
  }

  var api = {
    I18N: I18N, INPUTS: INPUTS, FIXED: FIXED, fmt: fmt, tx: tx, pickLang: pickLang,
    parseDwell: parseDwell, parseScan: parseScan, mmss: mmss, Dwell: Dwell, Scan: Scan,
    reasonsOf: reasonsOf, visibleSuggestions: visibleSuggestions, suggestionLabel: suggestionLabel, visibleText: visibleText,
    EMOJI_BASES: EMOJI_BASES, IDEOGRAPH_BASES: IDEOGRAPH_BASES,
    steps: steps, needConfirm: needConfirm, newUi: newUi, uiAfterUndo: uiAfterUndo,
    fanEligible: fanEligible, fanLayout: fanLayout, fanMark: fanMark, fanScript: fanScript, scrollDirection: scrollDirection, actionDescription: actionDescription,
    priorityState: priorityState, diffRange: diffRange,
    parseOptions: parseOptions, OPTION_DEFAULTS: OPTION_DEFAULTS,
    windowTitle: windowTitle, Health: Health, armStep: armStep, gridStep: gridStep, snap: snap,
    buildScreen: buildScreen, pressKey: pressKey, choiceLabel: choiceLabel, viewKey: viewKey,
    statsText: statsText, endText: endText, lightText: lightText, zeroPresses: zeroPresses,
    addPresses: addPresses, newPressLedger: newPressLedger, takePressBatches: takePressBatches,
    returnPressBatches: returnPressBatches, sumPressBatches: sumPressBatches
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BlemmaCore = api;
})(typeof self !== "undefined" ? self : this);
