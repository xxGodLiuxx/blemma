#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notification の待ちの合図を板へ 1 回だけ送る。判断は返さない (§2.4)。

何があっても (板なし・通信の失敗・壊れた入力・例外・`_client` を読めない置き方) 無出力で exit 0 (§2.0)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I / -P / PYTHONSAFEPATH でも _client を読む
try:
    import _client
except Exception:            # 置き方が壊れていても exit 0 (§2.0)
    sys.exit(0)

NOTIFICATION_TYPES = (
    "permission_prompt",
    "idle_prompt",
    "elicitation_dialog",
    "elicitation_url_dialog",
    "agent_needs_input",
)
NOTIFY_TIMEOUT_SEC = 2.0     # この短命な処理だけ、板へ送る通信の全体を 2 秒にする


def main() -> None:
    data = _client.read_input()
    if data is None or data.get("hook_event_name") != "Notification":
        return
    if data.get("notification_type") not in NOTIFICATION_TYPES:
        return
    _client.NOTIFY_GIVEUP_SEC = NOTIFY_TIMEOUT_SEC
    _client.notify(data)     # 転送 (3xx) は共通の通信が追わない = 1 回だけの通信


if __name__ == "__main__":
    _client.run_hook(main)   # 何があっても無出力のまま exit 0 (§2.0)
