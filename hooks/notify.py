#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notification の待ちの合図を板へ 1 回だけ送る。判断は返さない (§2.4)。"""

import urllib.request

import _client


NOTIFICATION_TYPES = (
    "permission_prompt",
    "idle_prompt",
    "elicitation_dialog",
    "elicitation_url_dialog",
    "agent_needs_input",
)
NOTIFY_TIMEOUT_SEC = 2.0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 共通 client の宛先は 127.0.0.1。転送でも外へ出さず、再送もしない。
        return None


def main():
    try:
        data = _client.read_input()
        if data is None or data.get("hook_event_name") != "Notification":
            return
        if data.get("notification_type") not in NOTIFICATION_TYPES:
            return
        # この短命な処理だけ 2 秒にする。共通 client の file は変更しない。
        _client.NOTIFY_GIVEUP_SEC = NOTIFY_TIMEOUT_SEC
        _client._OPENER = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        _client.notify(data)
    except Exception as exc:
        _client.debug(f"notify failed: {type(exc).__name__}")


if __name__ == "__main__":
    main()
