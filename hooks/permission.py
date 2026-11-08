#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA の権限の口 = `PermissionRequest` の hook (Python 3.10+・標準ライブラリだけ)。設計 = docs/design.md §2.1。

stdin の問い (道具と入力・`permission_suggestions`) を板の札にし、人が板で選んだ答えを公式の JSON に
組んで stdout へ 1 個だけ書く。

- 釦 = 許可 (今回) / 次から訊かない (suggestion ごと・2 件まで・bypassPermissions・auto へ移す物は出さない) /
  拒否 (定型 3 つ) / 作業を止める (固定の位置) / 端末で答える。
- 返す JSON = `hookSpecificOutput.decision` に `allow` / `allow` + `updatedPermissions` (選んだ suggestion を
  入力から逐語で写す) / `deny` + `message` / `deny` + `message` + `interrupt: true`。
- 板に出さない物 (無出力) = `ExitPlanMode`・`AskUserQuestion` (質問の口は PreToolUse = ask.py が答える。
  PreToolUse が決めない時は PermissionRequest も AskUserQuestion で呼ばれる = §10.3)・`permission_mode` が
  `plan`・環境変数 `BLEMMA_TERMINAL_ONLY` の道具・板に載らない大きさの札。
- 判断なし (板なし・時限・端末で答える・壊れた返り・例外) は全部、何も書かず exit 0 (§2.0)。

札の本文 (§2.1): Bash などの `command` は省かず全部 (長ければ札を出さず端末へ)・Edit は file と old → new・
Write は file と頭の 40 行・MCP の道具は server と道具の名と入力の JSON・他の道具は入力の JSON (どちらも
2,000 字まで・超えたら「続きは端末で」)。
見えない字 (制御の字・書字方向の字など) は `⟨U+XXXX⟩` に置き換えて見せる (表示だけ・返す JSON は変えない)。
"""

from __future__ import annotations

import bisect
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
# 異体字セレクタは前の字で決める: U+FE0E / U+FE0F (文字と絵文字の見せ方) は Emoji の性質を持つ字 (©・‼・❤ など) の後だけ
# 正当 (# * 数字の後は、次がキーキャップの印 U+20E3 の時だけ = 2 + U+FE0F + >f が札で 2>f に見えないように)・
# U+E0100〜U+E01EF (漢字の異体字) は CJK 統合漢字の後だけ正当・U+FE00〜U+FE0D (異体字セレクタ 1〜14) は常に印
_HIDDEN_CHARS = frozenset({"͏", "ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"})
_VS_ALWAYS = frozenset(chr(c) for c in range(0xFE00, 0xFE0E))
_VS_EMOJI = frozenset(chr(c) for c in (0xFE0E, 0xFE0F))
_VS_IDEOGRAPH = frozenset(chr(c) for c in range(0xE0100, 0xE01F0))
_KEYCAP_BASES = frozenset("#*0123456789")   # キーキャップの土台 (頁の KEYCAP_BASES と同じ字)
_KEYCAP = chr(0x20E3)                       # キーキャップの印 (囲みの結合文字)
# 前の字の表 = 番号の範囲 (始, 終) の昇順・頁 (board_core.js) の EMOJI_BASES・IDEOGRAPH_BASES と同じ物 (試験で照合)。性質の名で
# なく表で持つ = Python と頁の処理系の Unicode の版で網が変わらない。Emoji = node 22 (Unicode 17.0) の \p{Emoji} から生成・
# 漢字 = CJK 統合漢字 (Unified_Ideograph) の block
_EMOJI_BASES: tuple[tuple[int, int], ...] = (
    (0x23, 0x23), (0x2A, 0x2A), (0x30, 0x39), (0xA9, 0xA9), (0xAE, 0xAE), (0x203C, 0x203C), (0x2049, 0x2049),
    (0x2122, 0x2122), (0x2139, 0x2139), (0x2194, 0x2199), (0x21A9, 0x21AA), (0x231A, 0x231B), (0x2328, 0x2328),
    (0x23CF, 0x23CF), (0x23E9, 0x23F3), (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25AB), (0x25B6, 0x25B6),
    (0x25C0, 0x25C0), (0x25FB, 0x25FE), (0x2600, 0x2604), (0x260E, 0x260E), (0x2611, 0x2611), (0x2614, 0x2615),
    (0x2618, 0x2618), (0x261D, 0x261D), (0x2620, 0x2620), (0x2622, 0x2623), (0x2626, 0x2626), (0x262A, 0x262A),
    (0x262E, 0x262F), (0x2638, 0x263A), (0x2640, 0x2640), (0x2642, 0x2642), (0x2648, 0x2653), (0x265F, 0x2660),
    (0x2663, 0x2663), (0x2665, 0x2666), (0x2668, 0x2668), (0x267B, 0x267B), (0x267E, 0x267F), (0x2692, 0x2697),
    (0x2699, 0x2699), (0x269B, 0x269C), (0x26A0, 0x26A1), (0x26A7, 0x26A7), (0x26AA, 0x26AB), (0x26B0, 0x26B1),
    (0x26BD, 0x26BE), (0x26C4, 0x26C5), (0x26C8, 0x26C8), (0x26CE, 0x26CF), (0x26D1, 0x26D1), (0x26D3, 0x26D4),
    (0x26E9, 0x26EA), (0x26F0, 0x26F5), (0x26F7, 0x26FA), (0x26FD, 0x26FD), (0x2702, 0x2702), (0x2705, 0x2705),
    (0x2708, 0x270D), (0x270F, 0x270F), (0x2712, 0x2712), (0x2714, 0x2714), (0x2716, 0x2716), (0x271D, 0x271D),
    (0x2721, 0x2721), (0x2728, 0x2728), (0x2733, 0x2734), (0x2744, 0x2744), (0x2747, 0x2747), (0x274C, 0x274C),
    (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757), (0x2763, 0x2764), (0x2795, 0x2797), (0x27A1, 0x27A1),
    (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B07), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55), (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299), (0x1F004, 0x1F004),
    (0x1F0CF, 0x1F0CF), (0x1F170, 0x1F171), (0x1F17E, 0x1F17F), (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A),
    (0x1F1E6, 0x1F1FF), (0x1F201, 0x1F202), (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F), (0x1F232, 0x1F23A),
    (0x1F250, 0x1F251), (0x1F300, 0x1F321), (0x1F324, 0x1F393), (0x1F396, 0x1F397), (0x1F399, 0x1F39B),
    (0x1F39E, 0x1F3F0), (0x1F3F3, 0x1F3F5), (0x1F3F7, 0x1F4FD), (0x1F4FF, 0x1F53D), (0x1F549, 0x1F54E),
    (0x1F550, 0x1F567), (0x1F56F, 0x1F570), (0x1F573, 0x1F57A), (0x1F587, 0x1F587), (0x1F58A, 0x1F58D),
    (0x1F590, 0x1F590), (0x1F595, 0x1F596), (0x1F5A4, 0x1F5A5), (0x1F5A8, 0x1F5A8), (0x1F5B1, 0x1F5B2),
    (0x1F5BC, 0x1F5BC), (0x1F5C2, 0x1F5C4), (0x1F5D1, 0x1F5D3), (0x1F5DC, 0x1F5DE), (0x1F5E1, 0x1F5E1),
    (0x1F5E3, 0x1F5E3), (0x1F5E8, 0x1F5E8), (0x1F5EF, 0x1F5EF), (0x1F5F3, 0x1F5F3), (0x1F5FA, 0x1F64F),
    (0x1F680, 0x1F6C5), (0x1F6CB, 0x1F6D2), (0x1F6D5, 0x1F6D8), (0x1F6DC, 0x1F6E5), (0x1F6E9, 0x1F6E9),
    (0x1F6EB, 0x1F6EC), (0x1F6F0, 0x1F6F0), (0x1F6F3, 0x1F6FC), (0x1F7E0, 0x1F7EB), (0x1F7F0, 0x1F7F0),
    (0x1F90C, 0x1F93A), (0x1F93C, 0x1F945), (0x1F947, 0x1F9FF), (0x1FA70, 0x1FA7C), (0x1FA80, 0x1FA8A),
    (0x1FA8E, 0x1FAC6), (0x1FAC8, 0x1FAC8), (0x1FACD, 0x1FADC), (0x1FADF, 0x1FAEA), (0x1FAEF, 0x1FAF8),
)
_IDEOGRAPH_BASES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFA0E, 0xFA0F), (0xFA11, 0xFA11), (0xFA13, 0xFA14), (0xFA1F, 0xFA1F),
    (0xFA21, 0xFA21), (0xFA23, 0xFA24), (0xFA27, 0xFA29), (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x2EBF0, 0x2EE5F), (0x30000, 0x3134F), (0x31350, 0x323AF),
)


def _within(table: tuple[tuple[int, int], ...], ch: str) -> bool:
    """ch の番号が表の範囲のどれかに入るか (bisect = 長い本文に異体字セレクタが並んでも速い)。"""
    cp = ord(ch)
    i = bisect.bisect_right(table, (cp, 0x10FFFF)) - 1      # 始が cp 以下の最後の範囲
    return i >= 0 and cp <= table[i][1]


def _hidden(ch: str, prev: str, nxt: str) -> bool:
    if ch in "\n\t":
        return False
    if ch in _VS_EMOJI:
        if prev in _KEYCAP_BASES:
            return nxt != _KEYCAP                                  # # * 数字の後は、キーキャップの印が続く時だけ正当
        return not (prev and _within(_EMOJI_BASES, prev))         # ほかの Emoji の字 (❤・‼ など) の後は正当
    if ch in _VS_IDEOGRAPH:
        return not (prev and _within(_IDEOGRAPH_BASES, prev))     # CJK 統合漢字の後は正当
    return ch in _HIDDEN_CHARS or ch in _VS_ALWAYS or unicodedata.category(ch) in _HIDDEN


def visible(s: str) -> str:
    """見えない字を ⟨U+XXXX⟩ にして見せる (尾や途中に隠れた物を札で見落とさない)。"""
    out = []
    prev = ""
    for i, ch in enumerate(s):
        out.append(f"⟨U+{ord(ch):04X}⟩" if _hidden(ch, prev, s[i + 1:i + 2]) else ch)     # 次の字 (尾では "")
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


def _cut(s: str, limit: int = SUMMARY_CLIP) -> str:
    """1 行の要約を limit 字で切る。切った時は「…」を足す (表示だけ = 切れた url や名を、別の物に見せない)。"""
    return s if len(s) <= limit else s[:limit] + "…"


def _summary(tool_input: dict) -> str:
    for key in ("file_path", "notebook_path", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return visible(_cut(v.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]))
    v = tool_input.get("url")
    if isinstance(v, str) and v:
        return visible(_cut(v))
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
        text = visible(_cut(desc)) if isinstance(desc, str) else ""
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
            ja, en = f"頭の {WRITE_HEAD_LINES} 行", f"first {WRITE_HEAD_LINES} of {len(lines)} lines"
            if len(head) > TEXT_CLIP:                  # 40 行が 6,000 字を超える = 字でも切った事を見出しに書く
                ja, en = f"{ja}の先頭 {TEXT_CLIP} 字", f"first {TEXT_CLIP} chars of the {en}"
            label: Any = {"ja": f"content ({ja}・全 {len(lines)} 行・続きは端末で)",
                          "en": f"content ({en}; the rest in the terminal)"}
            content_block = _block(label, head[:TEXT_CLIP] + "\n…", mono=True)
        else:
            content_block = _clip_block("content", head, TEXT_CLIP)
        return _summary(ti), ([_block("file", path), content_block]
                              + _rest(ti, ("file_path", "content")))
    return _summary(ti), [_clip_block("input", _json_text(ti), JSON_CLIP)]


def _to_bypass(s: Any) -> bool:
    """一押しで以後の確認が消える (bypassPermissions)・分類器に任される (auto) モードへ移す物 = 板で出さない (§2.1)。"""
    return isinstance(s, dict) and s.get("type") == "setMode" and s.get("mode") in ("bypassPermissions", "auto")


def offered(suggestions: Any) -> List[dict]:
    """板に出す suggestion = 公式の 6 種だけ・bypassPermissions・auto へ移す物は除く・先頭から 2 件まで。

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
