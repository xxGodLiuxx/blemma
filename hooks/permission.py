#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA の権限の口 = `PermissionRequest` の hook (Python 3.10+・標準ライブラリだけ)。設計 = docs/design.md §2.1。

stdin の問い (道具と入力・`permission_suggestions`) を板の札にし、人が板で選んだ答えを公式の JSON に
組んで stdout へ 1 個だけ書く。

- 釦 = 許可 (今回) / 次から訊かない (suggestion ごと・2 件まで・bypassPermissions へ移す物は出さない) /
  拒否 (定型 3 つ) / 作業を止める (固定の位置) / 端末で答える。
- 返す JSON = `hookSpecificOutput.decision` に `allow` / `allow` + `updatedPermissions` (選んだ suggestion を
  入力から逐語で写す) / `deny` + `message` / `deny` + `message` + `interrupt: true`。
- 板に出さない物 (無出力) = `ExitPlanMode`・`AskUserQuestion` (質問の口は PreToolUse = ask.py が答える。
  PreToolUse が決めない時は PermissionRequest も AskUserQuestion で呼ばれる = §10.3)・`permission_mode` が
  `plan`・環境変数 `BLEMMA_TERMINAL_ONLY` の道具・板に載らない大きさの札。
- 判断なし (板なし・時限・端末で答える・壊れた返り・例外) は全部、何も書かず exit 0 (§2.0)。

札の本文 (§2.1): Bash などの `command` は省かず全部 (長ければ札を出さず端末へ)・Edit は file と old → new・
Write は file と頭の 40 行・MCP の道具は server と道具の名と入力の JSON (2,000 字まで)・他の道具は入力の JSON。
見えない字 (制御の字・書字方向の字など) は `⟨U+XXXX⟩` に置き換えて見せる (表示だけ・返す JSON は変えない)。
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -P / PYTHONSAFEPATH でも _client を読む
try:
    import _client
except Exception:            # 置き方が壊れていても exit 0 (§2.0)
    sys.exit(0)

EVENT = "PermissionRequest"
EXCLUDED_TOOLS = ("ExitPlanMode", "AskUserQuestion")
STOP_MESSAGE = "BLEMMA: the user stopped the work"
DENY_PREFIX = "BLEMMA: the user denied this on the board: "
SUGGESTION_TYPES = ("addRules", "replaceRules", "removeRules", "setMode", "addDirectories",
                    "removeDirectories")
MAX_SUGGESTIONS = 2          # 「次から訊かない」の釦は 2 件まで (3 件目からは端末で・§2.1)
JSON_CLIP = 2000             # MCP の道具・他の道具の入力の JSON (字・§2.1)
TEXT_CLIP = 6000             # Edit の old / new・Write の頭 (字)
SUMMARY_CLIP = 300           # 1 行の要約 (Bash の description など)
WRITE_HEAD_LINES = 40
_HIDDEN = ("Cc", "Cf", "Cs", "Zl", "Zp")   # 見えない字の種 (改行とタブは残す)
# 種では拾えない見えない字 (外の目の走査 F3): 結合文字の接着 U+034F・ハングルの埋め字・点字の空白・異体字セレクタ。
# 異体字セレクタは、絵文字の見せ方 (❤️ = U+2764 U+FE0F) と漢字の異体字 (漢字の後の U+E0100〜) では正当 = その 2 つだけ残す
_HIDDEN_CHARS = frozenset({"͏", "ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"})
_VS_EMOJI = frozenset(chr(c) for c in range(0xFE00, 0xFE10))
_VS_IDEOGRAPH = frozenset(chr(c) for c in range(0xE0100, 0xE01F0))


def _hidden(ch: str, prev: str) -> bool:
    if ch in "\n\t":
        return False
    if ch in _VS_EMOJI:
        return not (prev and unicodedata.category(prev)[0] == "S")   # 記号 (絵文字) の後は正当
    if ch in _VS_IDEOGRAPH:
        return not (prev and unicodedata.category(prev) == "Lo")      # 漢字 (文字) の後は正当
    return ch in _HIDDEN_CHARS or unicodedata.category(ch) in _HIDDEN


def visible(s: str) -> str:
    """見えない字を ⟨U+XXXX⟩ にして見せる (尾や途中に隠れた物を札で見落とさない)。"""
    out = []
    prev = ""
    for ch in s:
        out.append(f"⟨U+{ord(ch):04X}⟩" if _hidden(ch, prev) else ch)
        prev = ch
    return "".join(out)


def _block(label: Any, text: str, mono: bool = False) -> dict:
    b: dict = {"label": label, "text": visible(text)}
    if mono:
        b["mono"] = True
    return b


def _clip_block(name: str, text: str, limit: int, mono: bool = True) -> dict:
    """長い本文は先頭だけ (字の上限)。切った時は見出しに「先頭 n 字・全 m 字・続きは端末で」。"""
    if len(text) <= limit:
        return _block(name, text, mono)
    label = {"ja": f"{name} (先頭 {limit} 字・全 {len(text)} 字・続きは端末で)",
             "en": f"{name} (first {limit} of {len(text)} chars; the rest in the terminal)"}
    return _block(label, text[:limit] + "\n…", mono)


def _json_text(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _rest(tool_input: dict, shown: Tuple[str, ...]) -> List[dict]:
    """札に別に出した鍵の外の入力 (timeout・sandbox の旗など) = 隠さず JSON で。空・偽・None は省く。"""
    rest = {k: v for k, v in tool_input.items()
            if k not in shown and v is not None and v is not False and v != ""}
    if not rest:
        return []
    return [_clip_block("other input", _json_text(rest), JSON_CLIP)]


def _summary(tool_input: dict) -> str:
    for key in ("file_path", "notebook_path", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return visible(v.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1][:SUMMARY_CLIP])
    v = tool_input.get("url")
    if isinstance(v, str) and v:
        return visible(v[:SUMMARY_CLIP])
    return ""


def _mcp_parts(tool_name: str, data: dict) -> Tuple[str, str]:
    """`mcp__<server>__<tool>` → (server, tool)。server は stdin の `mcp_server.name` を先に使う。"""
    rest = tool_name[len("mcp__"):]
    srv = data.get("mcp_server")
    name = srv.get("name") if isinstance(srv, dict) else None
    if isinstance(name, str) and name and rest.startswith(name + "__"):
        return name, rest[len(name) + 2:]
    server, _, tool = rest.partition("__")
    return (name if isinstance(name, str) and name else server), tool


def body_of(tool_name: str, ti: dict, data: dict) -> Tuple[str, List[dict]]:
    """札の 1 行の要約と本文 (blocks)。"""
    if tool_name.startswith("mcp__"):
        server, tool = _mcp_parts(tool_name, data)
        return "", [_block("server", server), _block("tool", tool),
                    _clip_block("input", _json_text(ti), JSON_CLIP)]
    cmd = ti.get("command")
    if isinstance(cmd, str):                       # Bash・PowerShell など = command は省かない
        desc = ti.get("description")
        text = visible(desc[:SUMMARY_CLIP]) if isinstance(desc, str) else ""
        return text, [_block("command", cmd, mono=True)] + _rest(ti, ("command", "description"))
    path = ti.get("file_path")
    old, new = ti.get("old_string"), ti.get("new_string")
    if tool_name == "Edit" and isinstance(path, str) and isinstance(old, str) and isinstance(new, str):
        return _summary(ti), ([_block("file", path), _clip_block("old_string", old, TEXT_CLIP),
                               _clip_block("new_string", new, TEXT_CLIP)]
                              + _rest(ti, ("file_path", "old_string", "new_string")))
    content = ti.get("content")
    if tool_name == "Write" and isinstance(path, str) and isinstance(content, str):
        lines = content.splitlines(keepends=True)
        head = "".join(lines[:WRITE_HEAD_LINES])
        if len(lines) > WRITE_HEAD_LINES:
            label: Any = {"ja": f"content (頭の {WRITE_HEAD_LINES} 行・全 {len(lines)} 行・続きは端末で)",
                          "en": f"content (first {WRITE_HEAD_LINES} of {len(lines)} lines; "
                                "the rest in the terminal)"}
            content_block = _block(label, head[:TEXT_CLIP] + "\n…", mono=True)
        else:
            content_block = _clip_block("content", head, TEXT_CLIP)
        return _summary(ti), ([_block("file", path), content_block]
                              + _rest(ti, ("file_path", "content")))
    return _summary(ti), [_clip_block("input", _json_text(ti), JSON_CLIP)]


def _to_bypass(s: Any) -> bool:
    return isinstance(s, dict) and s.get("type") == "setMode" and s.get("mode") == "bypassPermissions"


def offered(suggestions: Any) -> List[dict]:
    """板に出す suggestion = 公式の 6 種だけ・bypassPermissions へ移す物は除く・先頭から 2 件まで。

    要素は入力のまま (逐語)。板の答えの番号はこの列の番号 = この列から `updatedPermissions` へ写す。
    """
    out: List[dict] = []
    if not isinstance(suggestions, list):
        return out
    for s in suggestions:
        if len(out) >= MAX_SUGGESTIONS:
            break
        if isinstance(s, dict) and s.get("type") in SUGGESTION_TYPES and not _to_bypass(s):
            out.append(s)
    return out


def excluded(data: dict) -> Optional[str]:
    """板に出さない理由 (無ければ None)。"""
    event = data.get("hook_event_name")
    if event is not None and event != EVENT:
        return f"別の口の入力 ({event})"
    name = data.get("tool_name")
    if not isinstance(name, str) or not name:
        return "tool_name が無い"
    if name in EXCLUDED_TOOLS:
        return name
    if data.get("permission_mode") == "plan":
        return "plan mode"
    if _client.terminal_only(name):
        return _client.TERMINAL_ONLY_ENV
    if not isinstance(data.get("tool_input"), dict):
        return "tool_input が無い"
    return None


def build(data: dict) -> Tuple[dict, List[dict]]:
    """板へ送る payload と、その suggestions の列 (答えの番号を引く元)。"""
    name = data["tool_name"]
    text, blocks = body_of(name, data["tool_input"], data)
    sugg = offered(data.get("permission_suggestions"))
    payload: dict = {"head": visible(name), "text": text, "blocks": blocks}
    if sugg:
        payload["suggestions"] = sugg
    return payload, sugg


def decide(choice: dict, sugg: List[dict]) -> Optional[dict]:
    """板の答え (client が payload と照らした物) → 公式の JSON。合わなければ None (= 無出力)。"""
    t = choice.get("type")
    if t == "allow_once":
        dec: dict = {"behavior": "allow"}
    elif t == "allow_always":
        i = choice.get("suggestion")
        if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(sugg) or _to_bypass(sugg[i]):
            return None
        dec = {"behavior": "allow", "updatedPermissions": [sugg[i]]}
    elif t == "deny":
        j = choice.get("reason")
        if not isinstance(j, int) or isinstance(j, bool) or not 0 <= j < len(_client.DENY_REASONS):
            return None
        ja, en = _client.DENY_REASONS[j]
        dec = {"behavior": "deny", "message": f"{DENY_PREFIX}{ja} / {en}", "interrupt": False}
    elif t == "stop":
        dec = {"behavior": "deny", "message": STOP_MESSAGE, "interrupt": True}
    else:
        return None
    return {"hookSpecificOutput": {"hookEventName": EVENT, "decision": dec}}


def main() -> None:
    data = _client.read_input()
    if data is None:
        return
    why = excluded(data)
    if why is not None:
        _client.debug(f"板に出さない: {why}")
        return
    payload, sugg = build(data)
    if not _client.payload_fits(payload):
        _client.debug("札が大きすぎる = 端末へ")
        return
    end, choice = _client.ask_detail(data, "permission", payload)
    if choice is None:
        _client.debug(f"判断なし: {end}")
        return
    out = decide(choice, sugg)
    if out is not None:
        _client.emit(out)


if __name__ == "__main__":
    _client.run_hook(main)       # 何があっても無出力のまま exit 0 (§2.0)
