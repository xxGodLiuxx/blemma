#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA の MCP の問いの口 = `Elicitation` の hook (Python 3.10+・標準ライブラリだけ)。設計 = docs/design.md §2.3。

MCP server が form で人に訊く時 (同梱の `ask_board` を含む)、`requested_schema` の欄を板の釦にし、選ばれた
答えを公式の形で返す。**出力の `hookEventName` は必須** (省くと出力ごと捨てられる = §10.3)。

- 板で描く欄 (提出版): 単一選択 (`enum`・`oneOf` の [{const, title}]) = 選択肢ごとに釦 / `boolean` = はい・いいえ /
  複数選択 (`type: array` + `items` の `enum` か `anyOf`・数の縛りが板で守れる物だけ) = 印の付く釦 + 「送る」。
  必須の複数選択は `minItems` が 0 の時だけ印 0 個でも送れる (= 値は `[]`)・`minItems` が無ければ 1 個以上。
- `ask_board` の「ほかの答え」(const `"other"` + 書く欄 `other_text` = §2.5) = 押すと端末で答える
  (板で文字は書かない)。
- 板で描けない欄 (文字・数の入力など): 必須なら札ごと端末へ (無出力)・任意でも既定の値 (`default`) が在れば札ごと端末へ
  (板で答えると、その値が抜ける)・既定の値の無い任意の欄は板では空のまま (content に入れない)。
  空のままにした任意の欄は、題を札の `omitted` に載せる (頁が「板に出ない欄がある」と知らせる・ask_board の
  `other_text` は「ほかの答え」の釦と対なので載せない)。欄が 7 つ以上・描く欄が 0・URL 形式 (`mode: url`) も
  無出力で端末へ。
- 送る = `action: "accept"` + `content` (欄の名 → 値・client が自分の payload の写しから組む) / 断る = `decline` /
  この問い合わせを閉じる (固定の位置の釦) = `cancel`。
- 判断なし (端末で答える・時限・板なし・壊れた返り・例外) は全部、何も書かず exit 0 = 端末に form が出る。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -P / PYTHONSAFEPATH でも _client を読む
try:
    import _client
except Exception:            # 置き方が壊れていても exit 0 (§2.0)
    sys.exit(0)

EVENT = "Elicitation"
FREE_CONST = "other"         # ask_board の「ほかの答え」の値 (§2.5)
FREE_FIELD = "other_text"    # ask_board の書く欄の名 (§2.5)
MAX_FIELDS = 6               # 欄が 7 つ以上の form は板に出さない (§2.3)
MAX_FIELD_OPTIONS = 12       # 1 欄の釦の数の上限 (超える欄は描けない欄の扱い)
MAX_OMITTED = 8              # 札の omitted (板に出ない任意の欄の題) の数の上限
OMITTED_CLIP = 80            # omitted の 1 個の字の上限
YES = {"ja": "はい", "en": "Yes"}
NO = {"ja": "いいえ", "en": "No"}


def _text(v: Any) -> Optional[str]:
    return v if isinstance(v, str) and v else None


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _primitive(v: Any) -> bool:
    """選択肢の値になれる物 = 文・数 (有限)・真偽。"""
    if isinstance(v, float):
        return math.isfinite(v)
    return isinstance(v, (str, int))      # bool は int の仲間


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b  # True と 1 を同じにしない


def _label(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def choices_of(spec: Any) -> Optional[List[Tuple[Any, str]]]:
    """`enum` (+ 旧い `enumNames`) か `oneOf` / `anyOf` の [{const, title}] → [(値, 釦の字)]。無ければ None。"""
    if not isinstance(spec, dict):
        return None
    vals = spec.get("enum")
    if isinstance(vals, list):
        names = spec.get("enumNames")
        if not (isinstance(names, list) and len(names) == len(vals) and all(_text(n) for n in names)):
            names = None
        out = []
        for i, v in enumerate(vals):
            if not _primitive(v):
                return None
            out.append((v, names[i] if names else _label(v)))
        return out or None
    for key in ("oneOf", "anyOf"):
        items = spec.get(key)
        if isinstance(items, list):
            out = []
            for it in items:
                if not isinstance(it, dict) or "const" not in it or not _primitive(it["const"]):
                    return None
                out.append((it["const"], _text(it.get("title")) or _label(it["const"])))
            return out or None
    return None


def field_of(name: str, spec: Any, required: bool, free: bool) -> Optional[dict]:
    """1 欄 → 板の 1 画面 (client の docstring の fields の形)。板で描けなければ None。"""
    if not isinstance(spec, dict):
        return None
    title = _text(spec.get("title")) or _text(spec.get("description")) or name
    # 題と説明の両方がある欄は、説明も札に載せる。題が「Confirm」だけの問いで、
    # 何を確かめるのか (消す対象・元に戻せるか) が説明にしか無い事がある
    note = _text(spec.get("description")) if _text(spec.get("title")) else None
    typ = spec.get("type")
    default = spec.get("default")
    least: Optional[int] = None                  # 複数選択で送れる最小の印の数 (下の min_picks)
    if typ == "boolean":
        options: List[dict] = [{"label": YES, "value": True}, {"label": NO, "value": False}]
        marks = [0] if default is True else [1] if default is False else []
        multi = False
    elif typ == "array":
        ch = choices_of(spec.get("items"))
        if ch is None:
            return None
        lo, hi = spec.get("minItems"), spec.get("maxItems")
        if lo is not None and not (_int(lo) and lo <= 1):          # 2 つ以上の下限は板で守れない
            return None
        if hi is not None and not (_int(hi) and hi >= len(ch)):    # 上限は板で守れない
            return None
        options = [{"label": t, "value": v} for v, t in ch]
        dv = default if isinstance(default, list) else []
        marks = [i for i, (v, _) in enumerate(ch) if any(_same(v, d) for d in dv)]
        multi = True
        # 欄の必須と最小の選択の数は別: 必須でも minItems が 0 なら 0 個 (= [] を値に) で送れる。
        # minItems が無い必須の欄は 1 個以上 (今までどおり)。任意の欄は 0 個 = 空のまま (content に入れない)
        least = (0 if lo is not None and lo <= 0 else 1) if required else 0
    elif typ in (None, "string", "number", "integer"):
        ch = choices_of(spec)
        if ch is None:
            return None
        options = [{"label": t, "terminal": True} if free and _same(v, FREE_CONST) else {"label": t, "value": v}
                   for v, t in ch]
        marks = [i for i, (v, _) in enumerate(ch) if "value" in options[i] and _same(v, default)]
        multi = False
    else:
        return None
    if not 1 <= len(options) <= MAX_FIELD_OPTIONS:
        return None
    # Description is an optional JSON Schema annotation. Its loss must never
    # change option indices, labels, values, or the validity of the card.
    source = spec.get("items", {}) if typ == "array" else spec
    if isinstance(source, dict) and not isinstance(source.get("enum"), list):
        entries = source.get("oneOf", source.get("anyOf"))
        if isinstance(entries, list) and len(entries) == len(options):
            for option, entry in zip(options, entries):
                if isinstance(entry, dict) and isinstance(entry.get("description"), str):
                    option["description"] = entry["description"]
    field = {"name": name, "title": title, "multi": multi, "required": required, "options": options}
    if note and note != title:
        field["description"] = note
    if least is not None:
        field["min_picks"] = least
    if marks:
        field["default"] = marks
    return field


def fields_of(schema: Any, omitted: Optional[List[str]] = None) -> Optional[List[dict]]:
    """`requested_schema` → 板の欄の列。札にできなければ None (= 端末へ)。

    omitted に list を渡すと、板で描けずに空のままにした任意の欄の題 (`title`・無ければ欄の名) を足す
    (札にできた時だけ・MAX_OMITTED 個・各 OMITTED_CLIP 字まで)。ask_board の書く欄 `other_text` は、
    「ほかの答え」の釦 (端末で答える) と対の時は足さない (その釦が端末へ導く)。
    """
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        return None
    props = schema.get("properties")
    if not isinstance(props, dict) or not 1 <= len(props) <= MAX_FIELDS:
        return None
    req = schema.get("required", [])
    if not isinstance(req, list):
        return None
    required = {r for r in req if isinstance(r, str)}
    spec = props.get(FREE_FIELD)
    free = (isinstance(spec, dict) and spec.get("type") == "string" and choices_of(spec) is None
            and FREE_FIELD not in required)
    fields = []
    dropped = []
    for name, spec in props.items():
        f = field_of(name, spec, name in required, free)
        if f is None:
            if name in required:
                return None        # 要る欄を板で描けない = 札ごと端末へ
            if isinstance(spec, dict) and "default" in spec and not (free and name == FREE_FIELD):
                # 既定の値つきの欄 = 端末の form なら、その値ごと送られる。板では見せも埋めもできず、
                # 答えからその欄が抜けて結果が変わる = 札ごと端末へ
                return None
            dropped.append((name, spec))   # 任意の欄 = 板では空のまま (書きたい時は「端末で答える」)
            continue
        fields.append(f)
    if not fields:
        return None
    if omitted is not None:
        paired = free and any(o.get("terminal") for f in fields for o in f["options"])
        for name, spec in dropped:
            if paired and name == FREE_FIELD:
                continue           # 「ほかの答え」の釦で端末へ行く書く欄 = 板に出ない欄に数えない
            title = (_text(spec.get("title")) if isinstance(spec, dict) else None) or name
            if len(omitted) < MAX_OMITTED:
                omitted.append(title[:OMITTED_CLIP])
    return fields


def decide(choice: dict) -> Optional[dict]:
    """板の答え (client が payload と照らした物) → 公式の JSON。合わなければ None (= 無出力)。"""
    t = choice.get("type")
    if t == "accept":
        values = choice.get("values")
        if not isinstance(values, dict):
            return None
        body = {"hookEventName": EVENT, "action": "accept", "content": values}
    elif t in ("decline", "cancel"):
        body = {"hookEventName": EVENT, "action": t}
    else:
        return None
    return {"hookSpecificOutput": body}


def main() -> None:
    data = _client.read_input()
    if data is None:
        return
    event = data.get("hook_event_name")
    if event is not None and event != EVENT:
        _client.debug(f"別の口の入力 ({event})")
        return
    if data.get("mode") not in (None, "form") or data.get("url"):
        _client.debug("URL 形式 = 端末へ")      # accept を返すと URL が開かなくなる (§2.3)
        return
    server = _text(data.get("mcp_server_name"))
    if server is None:
        _client.debug("問うている server の名が無い = 端末へ")
        return
    omitted: List[str] = []
    fields = fields_of(data.get("requested_schema"), omitted)
    if fields is None:
        _client.debug("板で描けない form = 端末へ")
        return
    payload = {"head": server, "text": _text(data.get("message")) or "", "fields": fields}
    if omitted:                  # 板に出ない任意の欄がある = 頁が知らせる (無ければ鍵ごと付けない)
        payload["omitted"] = omitted
    if not _client.payload_fits(payload):
        _client.debug("札が大きすぎる = 端末へ")
        return
    end, choice = _client.ask_detail(data, "elicitation", payload)
    if choice is None:
        _client.debug(f"判断なし: {end}")
        return
    out = decide(choice)
    if out is not None:
        _client.emit(out)


if __name__ == "__main__":
    _client.run_hook(main)       # 何があっても無出力のまま exit 0 (§2.0)
