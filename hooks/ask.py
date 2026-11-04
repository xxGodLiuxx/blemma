#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA の質問の口 = `PreToolUse` (matcher `AskUserQuestion`) の hook (Python 3.10+・標準ライブラリだけ)。

設計 = docs/design.md §2.2。Claude 自身の質問 (`tool_input.questions` = 1〜4 問・各 2〜4 択) を 1 枚の札で
板に出し (1 問 = 1 画面・複数の問いと multiSelect は確かめの画面と「送る」)、選ばれた答えを公式の形で返す。

- 答えた = `permissionDecision: "allow"` + `updatedInput` (元の `tool_input` を丸ごと写して `answers` を足す)。
  `answers` = {問いの文: 選んだ label}。multiSelect は label を ", " で繋いだ 1 本の文 (実機では配列も通り、
  Claude にはどちらも ", " で繋いだ文に見える = §10.3)。鍵と文は hook が自分の stdin の写しから組む
  (板からは番号だけ)。
- この質問に答えない (固定の位置の釦) = `permissionDecision: "deny"` + `permissionDecisionReason`
  (Claude には hook の error として届き、作業は続く = §10.3)。
- 判断なし (端末で答える・時限・板なし・壊れた返り・板で描けない形・例外) は全部、何も書かず exit 0 =
  端末に AskUserQuestion の dialog が出る。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -P / PYTHONSAFEPATH でも _client を読む
try:
    import _client
except Exception:            # 置き方が壊れていても exit 0 (§2.0)
    sys.exit(0)

EVENT = "PreToolUse"
TOOL = "AskUserQuestion"
SKIP_REASON = "BLEMMA: the user did not answer this question"
MAX_QUESTIONS = 4            # 公式の数 = 1〜4 問・各 2〜4 択 (外れた形は端末へ)
MIN_OPTIONS = 2
MAX_OPTIONS = 4


def questions_of(tool_input: Any) -> Optional[List[dict]]:
    """板で描けて答えを組める形の questions。外れていれば None (= 端末へ)。

    - 問いの文 (`question`) は空でない文・問いどうしで重ならない (`answers` の鍵になる)。
    - 選択肢は 2〜4 個・各 `label` は空でない文 (答えの文になる)。`multiSelect` は真偽か無し。
    """
    if not isinstance(tool_input, dict):
        return None
    qs = tool_input.get("questions")
    if not isinstance(qs, list) or not 1 <= len(qs) <= MAX_QUESTIONS:
        return None
    seen = set()
    for q in qs:
        if not isinstance(q, dict):
            return None
        text = q.get("question")
        if not isinstance(text, str) or not text or text in seen:
            return None
        seen.add(text)
        opts = q.get("options")
        if not isinstance(opts, list) or not MIN_OPTIONS <= len(opts) <= MAX_OPTIONS:
            return None
        for o in opts:
            if not isinstance(o, dict) or not isinstance(o.get("label"), str) or not o["label"]:
                return None
        if not isinstance(q.get("multiSelect", False), bool):
            return None
    return qs


def answers_of(qs: List[dict], picks: List[List[int]]) -> dict:
    """問いごとの選んだ番号 → {問いの文: label (multiSelect は ", " で繋ぐ)}。"""
    out = {}
    for q, p in zip(qs, picks):
        labels = [q["options"][i]["label"] for i in p]
        out[q["question"]] = ", ".join(labels) if q.get("multiSelect") else labels[0]
    return out


def decide(choice: dict, tool_input: dict, qs: List[dict]) -> Optional[dict]:
    """板の答え (client が payload と照らした物) → 公式の JSON。合わなければ None (= 無出力)。"""
    t = choice.get("type")
    if t == "answer":
        picks = choice.get("picks")
        if not isinstance(picks, list) or len(picks) != len(qs):
            return None
        updated = dict(tool_input)
        updated["answers"] = answers_of(qs, picks)
        return {"hookSpecificOutput": {"hookEventName": EVENT, "permissionDecision": "allow",
                                       "updatedInput": updated}}
    if t == "skip":
        return {"hookSpecificOutput": {"hookEventName": EVENT, "permissionDecision": "deny",
                                       "permissionDecisionReason": SKIP_REASON}}
    return None


def main() -> None:
    data = _client.read_input()
    if data is None:
        return
    event = data.get("hook_event_name")
    if (event is not None and event != EVENT) or data.get("tool_name") != TOOL:
        _client.debug("AskUserQuestion の PreToolUse でない = 何もしない")
        return
    if _client.terminal_only(TOOL):
        _client.debug(f"板に出さない: {_client.TERMINAL_ONLY_ENV}")
        return
    tool_input = data.get("tool_input")
    qs = questions_of(tool_input)
    if qs is None:
        _client.debug("板で描けない questions = 端末へ")
        return
    payload = {"questions": qs}
    if not _client.payload_fits(payload):
        _client.debug("札が大きすぎる = 端末へ")
        return
    end, choice = _client.ask_detail(data, "question", payload)
    if choice is None:
        _client.debug(f"判断なし: {end}")
        return
    out = decide(choice, tool_input, qs)
    if out is not None:
        _client.emit(out)


if __name__ == "__main__":
    _client.run_hook(main)       # 何があっても無出力のまま exit 0 (§2.0)
