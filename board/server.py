#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BLEMMA の板の server (Python 3.10+・標準ライブラリだけ)。設計 = docs/design.md §3。

    python board/server.py [--port 8765] [--wait 300] [--perm-wait SEC] [--undo-ms 3000]
                           [--allow-host NAME] [--no-browser] [--no-log]

- 127.0.0.1 だけで待ち受ける (LAN・外には bind しない)。起動ごとに token を作り、
  `board/state/run.json` (`{"port","token","pid","started"}`) に書く。止まる時に消す。
- hook は `POST /ask` → `GET /wait` (long-poll)、頁は `GET /pending` (long-poll) → `POST /answer`
  / `POST /undo`。札は 1 件ずつ・期限は表示から数えて作成からの上限で抑える・終わりは 4 つ
  (resolved は作らない・§3.5) のどれか 1 つに排他で決まる・取り消しの猶予は server が持つ (§3.4〜§3.6)。
- 板から返すのは choice (種と番号) だけ。公式の JSON は hook が組む (§3.3)。
- 記録は選択と時刻と数だけ (問いの本文・道具の入力・答えの文字は書かない・§3.8)。
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    # 手で起こした時も、板を起こす前に止める (blemma.py と同じ文)。古い python でもこの行まで届くよう、
    # file 全体を 3.9 の文法で書く。
    _VERSION = "%d.%d" % tuple(sys.version_info[:2])
    sys.stderr.write("BLEMMA: Python 3.10 以上で実行してください (今の版は %s)\n"
                     "BLEMMA: Python 3.10 or later is required (this is %s)\n" % (_VERSION, _VERSION))
    sys.exit(1)

import argparse
import atexit
import collections
import errno
import functools
import hmac
import json
import os
import re
import secrets
import select
import signal
import socket
import socketserver
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:                # python -I で起こされても隣の file を読む
    sys.path.insert(0, _HERE)

try:
    import window_win  # noqa: E402
except ImportError:                      # 窓の最前面と透過が無くても板は動く
    window_win = None  # type: ignore[assignment]
from urllib.parse import parse_qs, urlsplit

# ---------------------------------------------------------------------------
# §3.4 の数 = この 1 か所で決める。settings の hook の timeout を変える時は
# HOOK_TIMEOUT_SEC だけを直せば、作成からの上限・hook の自前の期限・--wait の上限が揃って動く
# (不等式 = --wait ≤ 上限 < 上限 + 15 < timeout)。
# ---------------------------------------------------------------------------
HOOK_TIMEOUT_SEC = 600          # settings の hook の timeout (examples の雛形と揃える)


@dataclass(frozen=True)
class Limits:
    wait: float = 300.0                          # 待ち (--wait・表示から)
    perm_wait: Optional[float] = None            # 権限の札の待ち (--perm-wait・None = wait と同じ)
    create_cap: float = HOOK_TIMEOUT_SEC - 60    # 作成からの上限 = 540
    min_show: float = 30.0                       # 表示の最小の残り (切っていれば表示しない)
    undo_ms: int = 3000                          # 取り消しの猶予 (--undo-ms・0〜undo_max_ms)
    undo_max_ms: int = 5000                      # 取り消しの猶予の上限
    hard_margin: float = 10.0                    # hook の自前の期限 = 上限 + 猶予の上限 + これ
    ask_giveup: float = 2.0                      # hook が POST /ask を諦める秒 (hooks/_client.py)
    wait_giveup: float = 20.0                    # hook が 1 回の GET /wait を諦める秒
    wait_hold: float = 15.0                      # server が /wait を抱える最長
    pending_hold: float = 25.0                   # server が /pending を抱える最長
    disconnect: float = 5.0                      # 最後の /wait が返ってから、これで接続の終了
    queue_max: int = 20                          # 生きている札の上限 (超えたら /ask は 503)
    light: float = 10.0                          # Notification の帯を出す秒
    viewer: Optional[float] = 30.0               # 見る人の判定 = 開いている /pending が無く、最後の返りから
                                                 # この秒を過ぎたら見る人なし (None = 判定しない)
    tick: float = 0.1                            # 状態を進める刻み
    keep_done: int = 200                         # 終わった札の控え (本文なし) を持つ数

    @property
    def hard_deadline(self) -> float:
        """hook の自前の期限 (作った時から) = 540 + 5 + 10 = 555 秒。"""
        return self.create_cap + self.undo_max_ms / 1000.0 + self.hard_margin

    def wait_for(self, kind: str) -> float:
        """札の種ごとの待ち (表示から)。権限の札だけ perm_wait (無ければ wait)。"""
        if kind == "permission" and self.perm_wait is not None:
            return self.perm_wait
        return self.wait


def check_limits(lim: Limits) -> None:
    """起動を断る値なら ValueError (§3.4 の決まり)。"""
    if not 0 < lim.wait <= lim.create_cap:
        raise ValueError(f"--wait は 0 より大きく {lim.create_cap:g} 秒 (作成からの上限) 以下")
    if not 0 < lim.wait_for("permission") <= lim.create_cap:
        raise ValueError(f"--perm-wait は 0 より大きく {lim.create_cap:g} 秒 (作成からの上限) 以下")
    if not 0 <= lim.undo_ms <= lim.undo_max_ms:
        raise ValueError(f"--undo-ms は 0〜{lim.undo_max_ms} ms")
    if lim.create_cap + lim.undo_max_ms / 1000.0 >= lim.hard_deadline:
        raise ValueError("hook の自前の期限は 作成からの上限 + 猶予の上限 より後")
    if lim.hard_deadline >= HOOK_TIMEOUT_SEC:
        raise ValueError("hook の自前の期限は settings の hook の timeout より前")
    if lim.viewer is not None and not lim.viewer > 0:
        raise ValueError("見る人の判定の秒は 0 より大きく")


KINDS = ("permission", "question", "elicitation")
INPUTS = ("dwell", "key", "switch", "touch", "click")   # §4.2 の入力 (by)
FINAL = ("answered", "released", "expired", "disconnected")   # resolved (/resolve) は作らない (§10.2)
CHOICES = {
    "permission": ("allow_once", "allow_always", "deny", "stop", "terminal"),
    "question": ("answer", "skip", "terminal"),
    "elicitation": ("accept", "decline", "cancel", "terminal"),
}
MAX_BODY = 512 * 1024
STATIC_NAME = re.compile(r"^[A-Za-z0-9_-]+\.(html|css|js|svg|png|ico|woff2)$")
CONTENT_TYPES = {
    "html": "text/html; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "woff2": "font/woff2",
    "js": "text/javascript; charset=utf-8",
    "svg": "image/svg+xml",
    "png": "image/png",
    "ico": "image/x-icon",
}
PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
DEBUG = os.environ.get("BLEMMA_DEBUG") == "1"


def _debug(msg: str) -> None:
    """`BLEMMA_DEBUG=1` の時だけ stderr に 1 行。書けない時 (stderr の無い起こし方) も、板の仕事を落とさない。"""
    if not DEBUG:
        return
    try:
        sys.stderr.write("BLEMMA server: " + msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _is_index(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 1000


def check_choice(kind: str, choice: Any) -> Optional[dict]:
    """choice の形だけを確かめて整える (番号の範囲は hook が自分の入力と照らす・§3.3)。"""
    if not isinstance(choice, dict):
        return None
    t = choice.get("type")
    if t not in CHOICES.get(kind, ()):
        return None
    if t == "allow_always":
        return {"type": t, "suggestion": choice.get("suggestion")} \
            if _is_index(choice.get("suggestion")) else None
    if t == "deny":
        return {"type": t, "reason": choice.get("reason")} if _is_index(choice.get("reason")) else None
    if t in ("answer", "accept"):
        picks = choice.get("picks")
        if not isinstance(picks, list) or not 0 < len(picks) <= 32:
            return None
        for p in picks:
            if not isinstance(p, list) or len(p) > 64 or not all(_is_index(i) for i in p):
                return None
        return {"type": t, "picks": [list(p) for p in picks]}
    return {"type": t}


def _clean_from(v: Any) -> dict:
    d = v if isinstance(v, dict) else {}

    def s(key: str) -> Optional[str]:
        x = d.get(key)
        return x[:80] if isinstance(x, str) and x else None

    return {"cwd": s("cwd") or "", "session": (s("session") or "")[:6], "agent": s("agent")}


def _presses_of(by: str, presses: Any) -> Dict[str, int]:
    """頁が送る押した数 = 数 (by に数える) か {入力: 数}。外れた値は 0。"""
    out = {k: 0 for k in INPUTS}
    if isinstance(presses, dict):
        for k, v in presses.items():
            if k in out and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000:
                out[k] = v
    elif isinstance(presses, int) and not isinstance(presses, bool) and 0 <= presses <= 1000:
        out[by if by in out else "click"] = presses
    return out


def _tag_of(value: Any) -> Optional[str]:
    """答えの名札 (頁ごとの乱数 + 送信の番号)。英数字と - _ : の 80 字までだけを通す。それ以外は名札なし。"""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", value):
        return value
    return None


def _press_batches_of(by: str, presses: Any, batches: Any) -> Optional[List[tuple]]:
    """ID 付きの束を先に全件確かめる。古い呼び手の presses だけの形も受ける。"""
    if batches is None:
        return [(None, _presses_of(by, presses))]
    if not isinstance(batches, list):
        return None
    out = []
    for batch in batches:
        if (not isinstance(batch, dict) or not isinstance(batch.get("id"), str) or
                not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", batch["id"]) or
                not isinstance(batch.get("presses"), dict)):
            return None
        out.append((batch["id"], _presses_of(by, batch["presses"])))
    return out


def _flushing(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Board の外側の口 = 錠を離した後に、溜まった記録を file へ書く。"""
    @functools.wraps(fn)
    def inner(self: "Board", *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        finally:
            self._flush_logs()
    return inner


class Card:
    """札 1 枚。状態 = queued / shown / deciding / 終わり 4 つ (resolved は作らない・§3.5)。"""

    def __init__(self, cid: str, kind: str, frm: dict, payload: dict, now: float) -> None:
        self.id = cid
        self.kind = kind
        self.frm = frm
        self.payload: Optional[dict] = payload
        self.created = now
        self.state = "queued"
        self.first_shown: Optional[float] = None
        self.deadline: Optional[float] = None
        self.view_seq = 0
        self.choice: Optional[dict] = None
        self.by: Optional[str] = None
        self.tag: Optional[str] = None      # 最後に受けた答えの名札 (頁ごとの乱数 + 送信の番号。記録にも hook への返りにも書かない)
        self.decided_at: Optional[float] = None
        self.undo_until: Optional[float] = None
        self.ready = False          # 猶予が過ぎ、hook の /wait へ渡すのを待っている
        self.delivering = False     # /wait へ書いている最中
        self.wait_inflight = 0
        self.last_wait_end = now
        self.presses = {k: 0 for k in INPUTS}
        self.press_batch_ids: set[str] = set()  # 札の間だけ保持し、記録には書かない
        self.undos = 0
        self.end: Optional[str] = None
        self.from_deciding = False


PAGE_GAP = 2.0                        # 頁の見張りの張り直しの間 (ふつう数 ms) を「頁が在る」と見る幅


class Board:
    """待ち行列と札の状態の確定。HTTP を知らない (試験は clock を差し替えて直に叩ける)。"""

    def __init__(self, limits: Limits, log_dir: Optional[Path] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.lim = limits
        self.clock = clock
        self.log_dir = log_dir
        self.cond = threading.Condition(threading.Lock())
        self.seq = 1
        self.live: List[Card] = []
        self.done: "collections.OrderedDict[str, Card]" = collections.OrderedDict()
        self.last: Optional[dict] = None
        self.light: Optional[dict] = None
        self.light_until = 0.0
        self.sessions: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
        self.closed = False
        self.viewers_open = 0                 # 開いている GET /pending の数 (見る人)
        self.viewer_seen = clock()            # 最後に見た時 = 起動も「見た」と数える
        self.page_seen: Optional[float] = None    # 頁の見張りが最後に在った時 (1 度も来ていなければ None = 起動の猶予は数えない)
        self._logq: "collections.deque[Tuple[str, dict]]" = collections.deque()
        self._log_lock = threading.Lock()
        self._reset_stats_locked(clock())

    # ---- 内側 (錠の下で呼ぶ) ----
    def _bump(self) -> None:
        self.seq += 1
        self.cond.notify_all()

    def _reset_stats_locked(self, now: float) -> None:
        self.stats_presses = {k: 0 for k in INPUTS}
        self.stats_answers = 0
        self.stats_since = now
        self.stats_cards: "collections.deque[dict]" = collections.deque(maxlen=20)

    def _find(self, cid: str) -> Optional[Card]:
        for c in self.live:
            if c.id == cid:
                return c
        return None

    def _head(self) -> Optional[Card]:
        return self.live[0] if self.live else None

    def _viewer_present(self, now: float) -> bool:
        """見る人が居るか = /pending が開いている・最後の返りから viewer 秒のうち (どの見え方も同じに数える)。"""
        if self.lim.viewer is None or self.viewers_open > 0:
            return True
        return now - self.viewer_seen <= self.lim.viewer

    def _show(self, c: Card, now: float) -> None:
        c.state = "shown"
        if c.first_shown is None:
            c.first_shown = now
        if c.deadline is None:              # 期限は最初の表示で 1 回だけ決める (取り消しで延ばさない・§3.6 の 2)
            c.deadline = min(now + self.lim.wait_for(c.kind), c.created + self.lim.create_cap)
        self._bump()
        c.view_seq = self.seq

    def _finish(self, c: Card, end: str, now: float) -> None:
        assert end in FINAL, end            # 終わりは FINAL の 4 つだけ (注釈と code をずらさない)
        if c.end is not None:               # 終わりは 1 回だけ (排他・§3.5)
            return
        c.from_deciding = c.state == "deciding"
        c.end = end
        c.state = end
        if c in self.live:
            self.live.remove(c)
        self._set_state(c.frm.get("session", ""),
                        "working" if end == "answered" else "waiting on you", now,
                        "" if end == "answered" else end)
        c.payload = None                      # 本文は札が生きている間だけ (§3.3)
        self.done[c.id] = c
        while len(self.done) > self.lim.keep_done:
            self.done.popitem(last=False)
        sec = None
        if end in ("answered", "released"):
            self.stats_answers += 1
            if c.decided_at is not None and c.first_shown is not None:
                sec = round(c.decided_at - c.first_shown, 1)
                self.stats_cards.append({"kind": c.kind, "end": end, "sec": sec})
        if c.first_shown is not None:
            self.last = {"id": c.id, "kind": c.kind, "end": end,
                         "from_deciding": c.from_deciding, "at": now,
                         "answered_by": c.tag if end in ("answered", "released") else None}
        self._log(c, sec)

    def _log(self, c: Card, sec: Optional[float]) -> None:
        """1 札 1 行 = 種・終わり・選択の種・秒・手段・押した数・取り消しの数だけ (§3.8)。"""
        if self.log_dir is None:
            return
        now = datetime.now().astimezone()    # 1 回だけ読む = 日付の変わり目でも、行の時刻と file の日付が揃う
        rec = {
            "t": now.isoformat(timespec="seconds"),
            "kind": c.kind,
            "end": c.end,
            "choice": c.choice.get("type") if (c.choice and c.end in ("answered", "released")) else None,
            "sec": sec,
            "by": c.by if c.end in ("answered", "released") else None,
            "presses": sum(c.presses.values()),
            "undo": c.undos,
        }
        self._logq.append((now.strftime("%Y-%m-%d"), rec))   # 書くのは錠の外 (_flush_logs)

    def _flush_logs(self) -> None:
        """溜まった記録を file へ書く。板の錠を持たずに呼ぶ (file の待ちで板を止めない)。"""
        if self.log_dir is None or not self._logq:
            return
        with self._log_lock:
            items = []
            while self._logq:
                items.append(self._logq.popleft())
            if not items:
                return
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                for day, rec in items:
                    with open(self.log_dir / f"log-{day}.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as e:
                _debug(f"記録を書けない: {type(e).__name__}")

    def _advance(self, now: float) -> None:
        """時間で進む物 (接続の終了・期限・表示・猶予の終わり・帯) を進める。"""
        changed = False
        for session, state in list(self.sessions.items()):
            if now - state["at"] >= 86400:
                del self.sessions[session]
                changed = True
            elif state["state"] == "working" and not state["stale"] and now - state["at"] >= 600:
                state["stale"] = True
                changed = True
        for c in list(self.live):
            if c.delivering or c.wait_inflight > 0:
                continue
            if now - c.last_wait_end > self.lim.disconnect:
                self._finish(c, "disconnected", now)
                changed = True
        if not self._viewer_present(now):
            for c in list(self.live):         # 見る人が居ない = 待ちと表示の札は切る・決めた札 (deciding) は完走
                if c.state in ("queued", "shown"):
                    self._finish(c, "expired", now)
                    changed = True
        head = self._head()
        if head is not None and head.state == "shown" and head.deadline is not None \
                and now >= head.deadline:
            self._finish(head, "expired", now)
            changed = True
        for c in list(self.live):
            if c.state == "queued" and c.created + self.lim.create_cap - now < self.lim.min_show:
                self._finish(c, "expired", now)            # 表示の直後の期限切れを作らない
                changed = True
        head = self._head()
        if head is not None and head.state == "queued" and self._viewer_present(now):
            self._show(head, now)
        if head is not None and head.state == "deciding" and not head.ready \
                and head.undo_until is not None and now >= head.undo_until:
            head.ready = True
            changed = True
        if self.light is not None and now >= self.light_until:
            self.light = None
            changed = True
        if changed:
            self._bump()

    def _final_body(self, c: Card) -> dict:
        """/wait を抱えている間に終わった札の返り。答えは渡す時の 1 回だけ = 渡し終えた札は closed。"""
        if c.end in ("expired", "disconnected"):
            return {"state": c.end}
        return {"state": "closed"}

    # ---- 外側 (錠を取る・終わった札の記録は錠を離してから書く) ----
    @_flushing
    def tick(self) -> None:
        with self.cond:
            self._advance(self.clock())

    def close(self) -> None:
        with self.cond:
            self.closed = True
            self.cond.notify_all()

    @_flushing
    def ask(self, kind: Any, frm: Any, payload: Any) -> Tuple[int, dict]:
        if kind not in KINDS or not isinstance(payload, dict):
            return 400, {"error": "bad_request"}
        with self.cond:
            now = self.clock()
            self._advance(now)
            if not self._viewer_present(now):
                return 503, {"error": "no_viewer"}           # 頁を閉じている = hook は判断なしで端末へ
            if len(self.live) >= self.lim.queue_max:
                return 503, {"error": "queue_full"}
            c = Card(secrets.token_hex(8), kind, _clean_from(frm), payload, now)
            self.live.append(c)
            self._set_state(c.frm.get("session", ""), "waiting on you", now)
            self._bump()
            self._advance(now)
            hard = self.lim.hard_deadline
            return 200, {
                "id": c.id,
                "hard_deadline": round(time.time() + hard, 3),
                "hard_deadline_in": hard,
                "wait_giveup": self.lim.wait_giveup,
                "wait_hold": self.lim.wait_hold,
            }

    @_flushing
    def wait(self, cid: Any, alive: Callable[[], bool] = lambda: True) -> Tuple[int, dict, Optional[Card]]:
        """hook の long-poll。答えを渡す時は第 3 の値に札を返す (書けたら delivered を呼ぶ)。"""
        if not isinstance(cid, str):
            return 400, {"error": "bad_request"}, None
        with self.cond:
            c = self._find(cid)
            if c is None:
                if cid not in self.done:
                    return 404, {"error": "unknown"}, None
                return 200, {"state": "closed"}, None      # 終わった札への /wait は closed だけ
            c.wait_inflight += 1
            try:
                until = self.clock() + self.lim.wait_hold
                while True:
                    now = self.clock()
                    self._advance(now)
                    if c.end is not None:
                        return 200, self._final_body(c), None
                    if c.state == "deciding" and c.ready and not c.delivering:
                        if not alive():
                            # 渡す直前に hook が閉じていた = 渡さず切断で閉じる (受け取り手の居ない答えを
                            # 頁に「渡しました」と出さない)。次の札もすぐ出す
                            self._finish(c, "disconnected", now)
                            self._bump()
                            self._advance(now)
                            return 0, {}, None
                        c.delivering = True
                        st = "released" if c.choice and c.choice.get("type") == "terminal" else "answered"
                        body = {"state": st}
                        if st == "answered":
                            body["answer"] = c.choice
                        return 200, body, c
                    if now >= until or self.closed:
                        rem = (c.deadline - now) if c.deadline is not None else None
                        return 200, {"state": "waiting", "card": c.state, "remaining": rem}, None
                    if not alive():
                        return 0, {}, None                 # hook は居ない = 返さない
                    self.cond.wait(min(0.25, max(0.0, until - now)))
            finally:
                c.wait_inflight -= 1
                c.last_wait_end = self.clock()

    @_flushing
    def delivered(self, c: Card, ok: bool) -> None:
        """答えを /wait へ書き終えた (ok) か、書けなかった。終わりを確定する。"""
        with self.cond:
            if c.end is not None:
                return
            now = self.clock()
            if ok:
                self._finish(c, "released" if c.choice and c.choice.get("type") == "terminal"
                             else "answered", now)
            else:
                self._finish(c, "disconnected", now)
            self._bump()
            self._advance(now)                     # 次の札をすぐ出す

    @_flushing
    def answer(self, cid: Any, seq: Any, choice: Any, by: Any, presses: Any,
               press_batches: Any = None, tag: Any = None) -> Tuple[int, dict]:
        with self.cond:
            now = self.clock()
            head = self._head()
            if head is None or head.id != cid:
                d = self.done.get(cid) if isinstance(cid, str) else None
                return 409, ({"error": "ended", "end": d.end} if d else {"error": "not_current"})
            if head.state == "shown" and head.deadline is not None and now >= head.deadline:
                self._finish(head, "expired", now)        # 期限と同時 = expired が勝つ (§3.6 の 4)
                self._bump()
                self._advance(now)
                return 409, {"error": "expired"}
            if head.state != "shown":
                return 409, {"error": "not_shown", "state": head.state}
            if isinstance(seq, bool) or not isinstance(seq, int) or seq != head.view_seq:
                return 409, {"error": "stale"}
            norm = check_choice(head.kind, choice)
            if norm is None:
                return 400, {"error": "bad_choice"}
            by_s = by if by in INPUTS else "click"
            batches = _press_batches_of(by_s, presses, press_batches)
            if batches is None:
                return 400, {"error": "bad_press_batches"}
            self._add_press_batches(head, batches)
            head.state = "deciding"
            head.choice = norm
            head.by = by_s
            head.tag = _tag_of(tag)               # どの送信の答えか (渡って終わった時に、last へ添える)
            head.decided_at = now
            head.undo_until = now + self.lim.undo_ms / 1000.0
            head.ready = self.lim.undo_ms == 0
            self._bump()
            return 200, {"undo_ms": self.lim.undo_ms, "undo_remaining": self.lim.undo_ms / 1000.0}

    @_flushing
    def undo(self, cid: Any, by: Any, presses: Any, press_batches: Any = None) -> Tuple[int, dict]:
        with self.cond:
            now = self.clock()
            self._advance(now)                          # 接続の終了・期限を先に確かめる (終わったはずの札を生きていると答えない)
            head = self._head()
            if head is None or head.id != cid or head.state != "deciding" or head.delivering \
                    or head.ready or head.undo_until is None or now >= head.undo_until:
                # 同じ札がまだ頭に居る時は今の状態を、もう終わった札には終わり方を添える = 頁が「ほかの頁が先に取り消した
                # (shown)」「答えが渡る途中 (deciding)」「渡った (answered・released)」「渡っていない (expired・disconnected)」を
                # 見分けられる (/answer の 409 と同じ形)。知らない札には添えない。
                if head is not None and head.id == cid:
                    return 409, {"error": "not_undoable", "state": head.state}
                d = self.done.get(cid) if isinstance(cid, str) else None
                if d is not None:
                    return 409, {"error": "not_undoable", "end": d.end}
                return 409, {"error": "not_undoable"}
            by_s = by if by in INPUTS else "click"
            batches = _press_batches_of(by_s, presses, press_batches)
            if batches is None:
                return 400, {"error": "bad_press_batches"}
            self._add_press_batches(head, batches)
            head.undos += 1
            head.choice = None
            head.by = None
            head.decided_at = None
            head.undo_until = None
            if head.deadline is not None and now < head.deadline:
                head.state = "shown"                       # 残りの時間はそのまま (§3.6 の 2)
                self._bump()
                head.view_seq = self.seq
                return 200, {"state": "shown"}
            head.state = "shown"
            self._finish(head, "expired", now)
            self._bump()
            self._advance(now)
            return 200, {"state": "expired"}

    def _add_press_batches(self, c: Card, batches: List[tuple]) -> None:
        # answer/undo の錠の内側で、受理した束だけを覚える (409/400 は覚えない)。
        for bid, p in batches:
            if bid is not None:
                if bid in c.press_batch_ids:
                    continue
                c.press_batch_ids.add(bid)
            self._add_presses(c, p)

    def _add_presses(self, c: Card, p: Dict[str, int]) -> None:
        for k, v in p.items():
            c.presses[k] += v
            self.stats_presses[k] += v

    def notify(self, body: Any) -> None:
        d = body if isinstance(body, dict) else {}

        def s(key: str, n: int) -> str:
            v = d.get(key)
            return v[:n] if isinstance(v, str) else ""

        with self.cond:
            now = self.clock()
            self.light = {"type": s("type", 60), "title": s("title", 200),
                          "message": s("message", 500), "from": _clean_from(d.get("from"))}
            self.light_until = now + self.lim.light
            if s("type", 60) in ("permission_prompt", "idle_prompt", "elicitation_dialog",
                                 "elicitation_url_dialog", "agent_needs_input"):
                self._set_state(self.light["from"]["session"], "waiting on you", now, "notification")
            self._bump()

    def _set_state(self, session: str, state: str, now: float, reason: str = "") -> None:
        # Only a short session ID and status survive; no prompt, tool input or cwd.
        session = session[:6]
        self.sessions[session] = {"session": session, "state": state, "at": now,
                                  "reason": reason, "stale": False}
        self.sessions.move_to_end(session)
        while len(self.sessions) > 128:
            self.sessions.popitem(last=False)

    def set_state(self, body: Any) -> Tuple[int, Optional[dict]]:
        if (not isinstance(body, dict) or set(body) != {"session", "state"}
                or body.get("state") not in ("working", "done")
                or not isinstance(body.get("session"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,6}", body["session"])):
            return 400, {"error": "bad_state"}
        with self.cond:
            self._set_state(body["session"], body["state"], self.clock())
            self._bump()
        return 204, None

    def _states(self, now: float) -> List[dict]:
        states = {sid: {**s, "ago": round(max(0, now - s["at"]), 1)}
                  for sid, s in self.sessions.items()}
        for c in self.live:
            sid = c.frm.get("session", "")
            states[sid] = {"session": sid, "state": "waiting on you", "stale": False,
                           "reason": "card", "ago": 0}
        for state in states.values():
            state.pop("at", None)
        return list(states.values())

    def reset_stats(self) -> None:
        with self.cond:
            self._reset_stats_locked(self.clock())
            self._bump()

    def _snapshot(self, now: float) -> dict:
        head = self._head()
        card = None
        if head is not None and head.state in ("shown", "deciding"):
            card = {
                "id": head.id, "kind": head.kind, "from": head.frm, "payload": head.payload,
                "state": head.state, "view_seq": head.view_seq,
                "remaining": max(0.0, round(head.deadline - now, 2)) if head.deadline else None,
                "choice": head.choice if head.state == "deciding" else None,
                "undo_remaining": (max(0.0, round(head.undo_until - now, 2))
                                   if head.state == "deciding" and head.undo_until and not head.ready
                                   else (0.0 if head.state == "deciding" else None)),
            }
        last = None
        if self.last is not None:
            last = dict(self.last)
            last["ago"] = round(now - last.pop("at"), 1)
        light = None
        if self.light is not None:
            light = dict(self.light)
            light["remaining"] = round(max(0.0, self.light_until - now), 1)
        return {
            "seq": self.seq,
            "card": card,
            "queue": sum(1 for c in self.live if c.state == "queued"),
            "last": last,
            "light": light,
            "states": self._states(now),
            "stats": {
                "presses": dict(self.stats_presses),
                "total": sum(self.stats_presses.values()),
                "answers": self.stats_answers,
                "elapsed": round(now - self.stats_since, 1),
                "cards": list(self.stats_cards),
            },
            "undo_ms": self.lim.undo_ms,
        }

    @_flushing
    def pending(self, seen: Any, alive: Callable[[], bool] = lambda: True) -> dict:
        """頁の long-poll。seq が seen と違えばすぐ、同じなら変わるまで (最長 pending_hold) 待つ。
        相手が閉じたらすぐ返す = 閉じた頁を見る人に数え続けない (端末へ戻るのが遅れる)。"""
        with self.cond:
            self.viewers_open += 1
            self.viewer_seen = self.page_seen = self.clock()
            try:
                until = self.clock() + self.lim.pending_hold
                while True:
                    now = self.clock()
                    self._advance(now)
                    if seen != self.seq or now >= until or self.closed or not alive():
                        return self._snapshot(now)
                    self.cond.wait(max(0.0, min(1.0, until - now)))
            finally:
                self.viewers_open -= 1
                self.viewer_seen = self.page_seen = self.clock()

    def page_open(self) -> bool:
        """いま板を見ている頁が在るか = 頁の見張り (GET /pending) が開いている・または直前 (PAGE_GAP 秒のうち) に在った。
        起こし方が「窓をもう 1 枚開くか」を決めるのに使う。見る人の判定と違い、起動の猶予は数えない
        (起きたばかりの板は、まだ誰にも見られていない)。"""
        with self.cond:
            if self.viewers_open > 0:
                return True
            return self.page_seen is not None and self.clock() - self.page_seen <= PAGE_GAP


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class App:
    def __init__(self, limits: Limits, token: str, allow_hosts: Optional[List[str]] = None,
                 log_dir: Optional[Path] = None, static_dir: Optional[Path] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.board = Board(limits, log_dir=log_dir, clock=clock)
        self.token = token
        self.hosts = {"127.0.0.1", "localhost"} | {h.lower() for h in (allow_hosts or []) if h}
        self.static_dir = static_dir or (Path(__file__).resolve().parent / "static")
        # token の要らない静的の口が開くのは、起動の時にこの置き場に在った file だけ
        # (Windows の装置名 CON.js・COM1.js などを、file の名として開きに行かない)
        self.static_names = _file_names(self.static_dir)


def _file_names(folder: Path) -> frozenset:
    """folder に今ある普通の file の名の集合。読めない時は空 (= 静的の口は全部 404)。"""
    names = set()
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        names.add(entry.name)
                except OSError:
                    continue
    except OSError:
        pass
    return frozenset(names)


def _peer_alive(sock: socket.socket) -> bool:
    """相手が接続を閉じていなければ True (読める + 0 byte = 閉じた)。"""
    try:
        r, _, _ = select.select([sock], [], [], 0)
        if not r:
            return True
        return sock.recv(1, socket.MSG_PEEK) != b""
    except (OSError, ValueError):
        return False


READ_TIMEOUT = 10.0          # 要求の行・ヘッダー・本文を読む時の待ち (秒)。正しい相手は同じ機械から一瞬で送る
MAX_CONNECTIONS = 64         # 同時に抱える接続の上限 (頁の long-poll と hook を合わせても普段は 10 未満)


class Handler(BaseHTTPRequestHandler):
    server_version = "BLEMMA"
    sys_version = ""
    # 鍵を確かめる前の読み取りで、遅い相手を時間の限りなく待たない。long-poll は返事を抱えるだけで
    # 読まないので、この待ちには掛からない
    timeout = READ_TIMEOUT
    protocol_version = "HTTP/1.0"
    default_request_version = "HTTP/1.0"   # 壊れた要求の行にも状態行つきで返す (Python 3.10 の既定は HTTP/0.9 扱いで状態行を省く)

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # 口の名と状態だけ (§3.3)
        return

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        if DEBUG:                         # 壊れた要求の行では path がまだ無い = getattr で読む
            _debug(f"{getattr(self, 'command', None)} {urlsplit(getattr(self, 'path', '') or '').path} {code}")

    def version_string(self) -> str:
        return self.server_version

    # ---- 返す ----
    def _send(self, code: int, body: bytes, ctype: Optional[str], extra: Optional[dict] = None) -> bool:
        try:
            self.send_response(code)
            if ctype:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Connection", "close")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)
            self.wfile.flush()
            return True
        except OSError:
            return False

    def _json(self, code: int, obj: Any) -> bool:
        if code == 204:
            return self._send(204, b"", None)
        # ASCII だけで返す (日本語は \uXXXX)。札の文に対のないサロゲートなど UTF-8 に直せない字が
        # 混じっても、その札が出ている間じゅう板の取得が落ち続ける、という形にしない
        return self._send(code, json.dumps(obj, ensure_ascii=True).encode("ascii"),
                          "application/json; charset=utf-8")

    def _read_body(self) -> Tuple[Optional[bytes], int]:
        """本文の bytes を読み切るだけ (解かない)。鍵の確かめの前に読む = 読み残すと Windows は RST を返す。
        解くのは鍵が通った後 (_parse_json) = 鍵の無い相手の深い入れ子や巨大な数で、板の thread を落とさず止めない。"""
        n = self.headers.get("Content-Length")
        try:
            size = int(n) if n is not None else -1
        except ValueError:
            size = -1
        if size < 0:
            return None, 411
        if size > MAX_BODY:
            return None, 413
        try:
            return self.rfile.read(size), 200
        except OSError:
            return None, 400

    @staticmethod
    def _parse_json(raw: Optional[bytes]) -> Tuple[Optional[dict], int]:
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except (ValueError, RecursionError):   # 深い入れ子も、壊れた本文として断る (捕まえないと handler の thread が落ちる)
            return None, 400
        if not isinstance(data, dict):
            return None, 400
        return data, 200

    # ---- 門 ----
    def _host_ok(self) -> bool:
        host = self.headers.get("Host")
        if not host:
            return False
        name = host.strip()
        if name.startswith("["):
            name = name.split("]", 1)[0] + "]"
        elif ":" in name:
            name = name.rsplit(":", 1)[0]
        return name.lower().rstrip(".") in self.app.hosts

    def _token_ok(self) -> bool:
        given = self.headers.get("X-Blemma-Token") or ""
        return hmac.compare_digest(given.encode("utf-8"), self.app.token.encode("utf-8"))

    # ---- 口 ----
    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def _route(self, method: str) -> None:
        if not self._host_ok():
            self._json(403, {"error": "host"})
            return
        parts = urlsplit(self.path)
        path = parts.path
        if method == "GET" and path in ("/", "/index.html"):
            self._static("index.html")
            return
        if method == "GET" and path.startswith("/static/"):
            self._static(path[len("/static/"):])
            return
        raw, st = (self._read_body() if method == "POST" else (None, 200))
        if not self._token_ok():          # 本文を読み切ってから断る (読み残すと Windows は RST を返す)
            self._json(401, {"error": "token"})
            return
        data = None
        if method == "POST" and st == 200:
            data, st = self._parse_json(raw)          # 解くのは鍵の後
        board = self.app.board
        q = parse_qs(parts.query)
        if method == "GET" and path == "/page":      # 起こし方の照会 = 札を作らず、見る人にも数えない
            self._json(200, {"open": board.page_open()})
            return
        if method == "GET" and path == "/wait":
            cid = (q.get("id") or [None])[0]
            code, body, card = board.wait(cid, alive=lambda: _peer_alive(self.connection))
            ok = False                    # 書き終えたと確かめられた時だけ True
            try:
                if code != 0:
                    ok = self._json(code, body)
            finally:
                # 書く所が OSError の外の例外で落ちても、渡しの途中の札は必ず閉じる
                # (閉じないと delivering のまま先頭に残り、以後の札が出ない)
                if card is not None:
                    board.delivered(card, ok)
            return
        if method == "GET" and path == "/pending":
            try:
                seen = int((q.get("seq") or ["-1"])[0])
            except ValueError:
                seen = -1
            self._json(200, board.pending(seen, alive=lambda: _peer_alive(self.connection)))
            return
        if method != "POST":
            self._json(404, {"error": "not_found"})
            return
        if data is None:
            self._json(st, {"error": "bad_body"})
            return
        if path == "/ask":
            code, body = board.ask(data.get("kind"), data.get("from"), data.get("payload"))
            self._json(code, body)
        elif path == "/answer":
            code, body = board.answer(data.get("id"), data.get("seq"), data.get("choice"),
                                      data.get("by"), data.get("presses"), data.get("press_batches"),
                                      data.get("tag"))
            self._json(code, body)
        elif path == "/undo":
            code, body = board.undo(data.get("id"), data.get("by"), data.get("presses"),
                                   data.get("press_batches"))
            self._json(code, body)
        elif path == "/notify":
            board.notify(data)
            self._json(204, None)
        elif path == "/state":
            code, body = board.set_state(data)
            self._json(code, body)
        elif path == "/stats/reset":
            board.reset_stats()
            self._json(204, None)
        elif path == "/window":
            # 触るのはこの板 (この port) の窓だけ = 別の port の板の窓を取り違えない
            port = self.connection.getsockname()[1]
            self._json(200, window_win.apply(data, port) if window_win else {"found": False})
        else:
            # /resolve は提出版では作らない (1 対 1 の照合の鍵が見つかった時だけ・§3.7)
            self._json(404, {"error": "not_found"})

    def _static(self, name: str) -> None:
        if not STATIC_NAME.match(name) or name not in self.app.static_names:
            self._json(404, {"error": "not_found"})
            return
        path = self.app.static_dir / name
        try:
            body = path.read_bytes()
        except OSError:
            self._json(404, {"error": "not_found"})
            return
        ext = name.rsplit(".", 1)[1]
        extra = {"X-Frame-Options": "DENY"}
        if ext == "html":
            extra["Content-Security-Policy"] = PAGE_CSP
        self._send(200, body, CONTENT_TYPES[ext], extra)


class BoardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False      # 抱えた long-poll の終わりを待たずに閉じる
    # Windows の SO_REUSEADDR は使用中の port にも bind できてしまう = 使わず、排他の旗を立てる。
    # wildcard (0.0.0.0・:: の二重) で待つ相手には排他の旗でも bind が通る = make_server が connect の試しで断る
    allow_reuse_address = os.name != "nt"
    max_connections = MAX_CONNECTIONS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(self.max_connections)

    def process_request(self, request: Any, client_address: Any) -> None:
        """接続ごとに thread を 1 本。上限を超えた接続は受けずに閉じる (thread を増やし続けない)。"""
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)      # getfqdn (遅い逆引き) を避ける
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port


def _refuse_if_answered(port: int) -> None:
    """127.0.0.1:port に繋がる相手が居れば OSError (EADDRINUSE)。0.0.0.0 や :: (二重) で待つ相手が居ても、Windows と mac
    では 127.0.0.1 の bind が通り、その相手の 127.0.0.1 の客を奪う = bind の前に繋いでみる (人の上に起きないための
    確かめ・確かめと bind の間の隙は許す)。繋がらない (断られた・時間切れ) 時は空きと見て bind へ進む。"""
    try:
        probe = socket.create_connection(("127.0.0.1", port), timeout=0.2)
    except OSError:
        return
    probe.close()
    raise OSError(errno.EADDRINUSE, "この port で接続を受ける相手が居ます (0.0.0.0・:: で待つ物を含む)")


def make_server(app: App, port: int) -> BoardHTTPServer:
    """127.0.0.1 だけに bind する。使用中なら OSError (黙って別の port に移らない)。"""
    if port:                                  # 0 = OS が空きを選ぶ (試験の板)
        _refuse_if_answered(port)
    httpd = BoardHTTPServer(("127.0.0.1", port), Handler)
    httpd.app = app  # type: ignore[attr-defined]
    return httpd


def start_ticker(board: Board) -> threading.Thread:
    def loop() -> None:
        while not board.closed:
            board.tick()
            time.sleep(board.lim.tick)

    t = threading.Thread(target=loop, name="blemma-ticker", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# run.json (在処と token)
# ---------------------------------------------------------------------------
def write_run_file(path: Path, info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f)
    for _ in range(20):
        try:
            os.replace(str(tmp), str(path))
            break
        except PermissionError:          # Windows で読み手が開いている間
            time.sleep(0.05)
    else:
        os.replace(str(tmp), str(path))
    if os.name != "nt":
        os.chmod(str(path), 0o600)


def restrict_to_user(folder: Path, run: Callable[..., Any] = subprocess.run) -> bool:
    """置き場を、今のユーザーだけが読めるようにする (run.json には板の port と鍵が入る)。

    Windows の file は親の folder の許可を継ぐ。置いた場所によっては、同じ PC の他のユーザーにも読めて
    しまい、鍵を読んだ人は代わりに答えを送れる。できなかった時は False を返す (板は動かす・許可は元のまま)。
    """
    if os.name != "nt":
        try:
            os.chmod(str(folder), 0o700)
            return True
        except OSError:
            return False
    return _restrict_windows(folder, run)


def _restrict_windows(folder: Path, run: Callable[..., Any]) -> bool:
    system = Path(os.environ.get("SystemRoot") or "C:/Windows") / "System32"    # PATH の同名の物を拾わない
    quiet = {"capture_output": True, "timeout": 10, "stdin": subprocess.DEVNULL,
             "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        who = run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **quiet)
        sid = re.search(rb"S-1-[0-9-]+", who.stdout or b"")
        if who.returncode != 0 or not sid:
            return False
        # 先に自分の許可を足し、それが通った時だけ親からの継ぎを外す
        # (逆の順で途中で失敗すると、自分も読めない folder が残る)
        grant = run([str(system / "icacls.exe"), str(folder), "/grant:r",
                     "*" + sid.group(0).decode("ascii") + ":(OI)(CI)F"], **quiet)
        if grant.returncode != 0:
            return False
        return run([str(system / "icacls.exe"), str(folder), "/inheritance:r"], **quiet).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def remove_run_file(path: Path, token: str) -> None:
    """自分の token の run.json だけを消す (後から起きた別の server の物は消さない)。"""
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        if info.get("token") == token:
            path.unlink()
    except (OSError, ValueError):
        pass


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="board/server.py",
        description="BLEMMA の板 (127.0.0.1 だけ)。起動ごとの token を board/state/run.json に書く。")
    ap.add_argument("--port", type=int, default=8765, help="待ち受ける port (既定 8765・使用中なら起動を断る)")
    ap.add_argument("--wait", type=float, default=Limits.wait,
                    help=f"札の待ち・表示から (既定 {Limits.wait:g} 秒・{Limits.create_cap:g} まで)")
    ap.add_argument("--perm-wait", type=float, default=None, help="権限の札の待ち (既定 = --wait)")
    ap.add_argument("--undo-ms", type=int, default=Limits.undo_ms,
                    help=f"取り消しの猶予 (既定 {Limits.undo_ms} ms・0〜{Limits.undo_max_ms})")
    ap.add_argument("--allow-host", action="append", default=[], metavar="NAME",
                    help="Host の照合に足す名 (携帯の転送で 127.0.0.1 / localhost 以外の名を使う時・複数可)")
    ap.add_argument("--no-browser", action="store_true", help="頁を既定のブラウザで開かない")
    ap.add_argument("--no-log", action="store_true", help="board/state/log-*.jsonl を書かない")
    return ap.parse_args(argv)


def harden_streams(*streams: Any) -> None:
    """案内の行 (日本語を含む) を、console の文字コードが書けない時 (英語の Windows の cp1252 など) も落とさない = 書けない字は
    ? に替える。文字コードは変えない (日本語の console はそのまま読める)。付け替えられない stream (差し替えの物) は放っておく。
    Replace unencodable characters instead of raising, so a non-Japanese console cannot kill the board at startup."""
    for stream in streams or (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    harden_streams()
    args = parse_args(argv)
    lim = Limits(wait=args.wait,
                 perm_wait=args.perm_wait,
                 undo_ms=args.undo_ms)
    try:
        check_limits(lim)
    except ValueError as e:
        print(f"BLEMMA: 起動を断りました: {e}", file=sys.stderr)
        return 2
    if not 0 < args.port < 65536:
        print("BLEMMA: --port は 1〜65535", file=sys.stderr)
        return 2
    here = Path(__file__).resolve().parent
    state = here / "state"
    token = secrets.token_urlsafe(32)
    app = App(lim, token, allow_hosts=args.allow_host, log_dir=None if args.no_log else state)
    try:
        httpd = make_server(app, args.port)
    except OSError as e:
        print(f"BLEMMA: 127.0.0.1:{args.port} を開けません (使用中か権限なし): {e}", file=sys.stderr)
        return 1
    port = httpd.server_address[1]
    run = state / "run.json"
    state.mkdir(parents=True, exist_ok=True)
    if not restrict_to_user(state):       # 鍵を書く前に絞る (後から絞ると、その間は読める)
        print("BLEMMA: 置き場の許可を今のユーザーだけに絞れませんでした。共有の PC では、他のユーザーが読めない"
              "場所に置いてください / Could not restrict board/state to the current user.", file=sys.stderr)
    write_run_file(run, {"port": port, "token": token, "pid": os.getpid(),
                         "started": datetime.now().astimezone().isoformat(timespec="seconds")})
    atexit.register(remove_run_file, run, token)
    if hasattr(signal, "SIGTERM"):
        def _term(signum: int, frame: Any) -> None:
            raise KeyboardInterrupt
        try:
            signal.signal(signal.SIGTERM, _term)
        except (OSError, ValueError):
            pass
    start_ticker(app.board)
    url = f"http://127.0.0.1:{port}/#t={token}"
    print(f"BLEMMA: 板を開きました = {url}", flush=True)
    print("BLEMMA: 止める = Ctrl+C (止めると hook は判断を返さず、Claude Code のいつもの確認に戻ります)", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        app.board.close()
        httpd.server_close()
        remove_run_file(run, token)
        print("BLEMMA: 板を止めました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
