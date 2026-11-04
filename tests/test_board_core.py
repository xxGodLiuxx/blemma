# -*- coding: utf-8 -*-
"""板の状態の確定 (§3.4〜§3.6) を、時計を差し替えて直に確かめる (HTTP なし)。"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

import server as S

# 設計の数そのまま + 抱える秒だけ 0 (偽の時計では待てないので)
CORE = replace(S.Limits(), wait_hold=0.0, pending_hold=0.0, viewer=None)

PERM = {"head": "Bash", "text": "list files", "blocks": [{"label": "command", "text": "ls -la", "mono": True}]}


def new_board(clock, tmp_path=None, **kw):
    lim = replace(CORE, **kw) if kw else CORE
    return S.Board(lim, log_dir=tmp_path, clock=clock)


def ask(board, kind="permission", payload=None):
    code, body = board.ask(kind, {"cwd": "repo", "session": "abc123"}, payload or dict(PERM))
    assert code == 200, body
    return body["id"]


def keepalive(board, *ids):
    """hook が /wait を呼び続けている事にする (抱える秒 0 = すぐ返る)。"""
    for cid in ids:
        board.wait(cid)


def head(board):
    return board.live[0] if board.live else None


def card_of(board, cid):
    return board._find(cid) or board.done.get(cid)


def test_defaults_match_design_table():
    lim = S.Limits()
    assert S.HOOK_TIMEOUT_SEC == 600
    assert (lim.wait, lim.create_cap, lim.min_show) == (300, 540, 30)
    assert lim.perm_wait is None and lim.wait_for("permission") == 300 and lim.wait_for("question") == 300
    assert replace(lim, wait=120).wait_for("permission") == 120          # 権限の札の待ちの既定 = --wait
    assert (lim.undo_ms, lim.undo_max_ms) == (3000, 5000)
    assert lim.hard_deadline == 555
    assert (lim.ask_giveup, lim.wait_giveup, lim.wait_hold, lim.pending_hold) == (2, 20, 15, 25)
    assert (lim.disconnect, lim.queue_max, lim.light, lim.viewer) == (5, 20, 10, 30)
    # 不等式 = --wait ≤ 上限 < 上限 + 15 < timeout
    assert lim.wait <= lim.create_cap < lim.create_cap + 15 <= lim.hard_deadline < S.HOOK_TIMEOUT_SEC
    S.check_limits(lim)


def test_press_batches_survive_reset_and_are_scoped_to_each_card(clock):
    b = new_board(clock)
    cid = ask(b)
    batch = {"id": "page:1", "presses": {"dwell": 2}}
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(cid, seq, {"type": "allow_once"}, "dwell", 2, [batch, batch])[0] == 200
    assert b.pending(-1)["stats"]["total"] == 2
    b.reset_stats()
    assert b.undo(cid, "key", 2, [batch])[0] == 200
    assert b.pending(-1)["stats"]["total"] == 0
    assert card_of(b, cid).presses["dwell"] == 2
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(cid, seq, {"type": "allow_once"}, "dwell", 2, [batch])[0] == 200
    assert b.pending(-1)["stats"]["total"] == 0
    clock.advance(3.0)
    _, _, card = b.wait(cid)
    b.delivered(card, True)
    other = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(other, seq, {"type": "allow_once"}, "dwell", 2, [batch])[0] == 200
    assert b.pending(-1)["stats"]["total"] == 2


@pytest.mark.parametrize("invalid", [False, {}, [{"id": [], "presses": {"dwell": 1}}],
                                   [{"id": "", "presses": {"dwell": 1}}],
                                   [{"id": "page:2", "presses": 1}]])
def test_invalid_press_batches_do_not_change_state_or_counts(clock, invalid):
    b = new_board(clock)
    cid = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    first = {"id": "page:1", "presses": {"dwell": 1}}
    batches = [first] + invalid if isinstance(invalid, list) else invalid
    assert b.answer(cid, seq, {"type": "allow_once"}, "dwell", 1, batches) == (
        400, {"error": "bad_press_batches"},
    )
    assert b.pending(-1)["stats"]["total"] == 0 and head(b).state == "shown"
    assert b.answer(cid, seq, {"type": "allow_once"}, "dwell", 1, [first])[0] == 200
    assert b.undo(cid, "switch", 1, batches) == (400, {"error": "bad_press_batches"})
    assert b.pending(-1)["stats"]["total"] == 1 and head(b).state == "deciding"


def test_rejected_press_batch_can_be_counted_by_a_later_request(clock):
    b = new_board(clock)
    cid = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    batch = {"id": "page:1", "presses": {"key": 1}}
    assert b.answer(cid, seq - 1, {"type": "allow_once"}, "key", 1, [batch])[0] == 409
    assert b.undo(cid, "key", 1, [batch])[0] == 409
    assert b.answer(cid, seq, {"type": "allow_once"}, "key", 1, [batch])[0] == 200
    assert b.pending(-1)["stats"]["total"] == 1


@pytest.mark.parametrize("kw", [{"undo_ms": 5001}, {"undo_ms": -1}, {"wait": 541}, {"wait": 0},
                                {"perm_wait": 600}])
def test_check_limits_refuses(kw):
    with pytest.raises(ValueError):
        S.check_limits(replace(S.Limits(), **kw))


def test_first_card_shown_second_queued(clock):
    b = new_board(clock)
    a = ask(b)
    c = ask(b, "question", {"questions": []})
    assert card_of(b, a).state == "shown"
    assert card_of(b, a).deadline == clock.t + 300
    assert card_of(b, c).state == "queued"
    snap = b.pending(-1)
    assert snap["card"]["id"] == a and snap["queue"] == 1
    assert snap["card"]["from"] == {"cwd": "repo", "session": "abc123", "agent": None}


def test_second_card_deadline_counts_from_show_and_is_capped(clock):
    b = new_board(clock, wait=500, perm_wait=500)
    t0 = clock.t
    a = ask(b)
    c = ask(b)
    for _ in range(100):                       # 400 秒 = a の hook も c の hook も生きている
        clock.advance(4)
        keepalive(b, a, c)
    assert card_of(b, a).state == "shown"
    # a を答えて渡す → c が表示される (t0 + 400 で表示・作成からの上限 540 で抑えられる)
    snap = b.pending(-1)
    assert b.answer(a, snap["card"]["view_seq"], {"type": "allow_once"}, "dwell", 1)[0] == 200
    clock.advance(3.0)
    b.tick()
    code, body, card = b.wait(a)
    assert body["state"] == "answered"
    b.delivered(card, True)
    cc = card_of(b, c)
    assert cc.state == "shown"
    assert cc.deadline == pytest.approx(t0 + 540)       # min(表示 + 500, 作成 + 540)


def test_queued_card_with_less_than_30s_is_expired_without_showing(clock):
    b = new_board(clock, wait=520, perm_wait=520)
    a = ask(b)
    c = ask(b)
    for _ in range(127):                       # 508 秒まで
        clock.advance(4)
        keepalive(b, a, c)
    clock.advance(3)                           # 511 秒 = 作成からの上限まで 29 秒
    keepalive(b, a, c)
    assert card_of(b, c).state == "expired"
    assert card_of(b, c).first_shown is None   # 一度も表示していない
    assert card_of(b, a).state == "shown"


def test_answer_grace_then_delivery_is_answered(clock, tmp_path):
    b = new_board(clock, tmp_path)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    code, body = b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    assert code == 200 and body["undo_ms"] == 3000
    assert card_of(b, a).state == "deciding"
    clock.advance(2.9)
    assert b.wait(a)[1]["state"] == "waiting"        # 猶予のうちは hook に返さない
    clock.advance(0.2)
    code, body, card = b.wait(a)
    assert body == {"state": "answered", "answer": {"type": "allow_once"}}
    assert card_of(b, a).state == "deciding"         # 書き終えるまでは answered でない
    b.delivered(card, True)
    assert card_of(b, a).state == "answered"
    assert card_of(b, a).payload is None             # 本文は閉じたら捨てる
    snap = b.pending(-1)
    assert snap["card"] is None and snap["last"]["end"] == "answered"
    assert snap["stats"]["answers"] == 1 and snap["stats"]["presses"]["dwell"] == 1
    # 遅れた出来事は捨てる
    assert b.undo(a, "key", 1)[0] == 409
    assert b.answer(a, seq, {"type": "allow_once"}, "key", 1) == (409, {"error": "ended", "end": "answered"})
    # 答えは渡す時の 1 回だけ = 終わった札への /wait は closed
    assert b.wait(a)[1] == {"state": "closed"}


def test_terminal_is_released(clock):
    b = new_board(clock)
    a = ask(b, "question", {"questions": [{"question": "q", "options": [{"label": "x"}, {"label": "y"}]}]})
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "terminal"}, "key", 1)[0] == 200
    clock.advance(3.0)
    code, body, card = b.wait(a)
    assert body == {"state": "released"}
    b.delivered(card, True)
    assert card_of(b, a).state == "released"


def test_undo_in_grace_returns_to_shown_with_new_view_seq(clock):
    b = new_board(clock)
    a = ask(b)
    seq1 = b.pending(-1)["card"]["view_seq"]
    deadline = card_of(b, a).deadline
    assert b.answer(a, seq1, {"type": "deny", "reason": 0}, "dwell", 1)[0] == 200
    clock.advance(1.0)
    assert b.undo(a, "switch", 1) == (200, {"state": "shown"})
    c = card_of(b, a)
    assert c.state == "shown" and c.deadline == deadline     # 残りの時間はそのまま
    assert c.view_seq != seq1
    # 古い画面 (seq1) への押しは効かない
    assert b.answer(a, seq1, {"type": "allow_once"}, "dwell", 1) == (409, {"error": "stale"})
    assert b.answer(a, c.view_seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    assert c.undos == 1 and c.presses["switch"] == 1 and c.presses["dwell"] == 2


def test_undo_after_grace_is_refused(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    clock.advance(3.01)
    assert b.undo(a, "key", 1)[0] == 409


def test_answer_at_deadline_is_expired_and_409(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    clock.advance(300.0)                             # 期限と同時 = expired が勝つ
    assert b.answer(a, seq, {"type": "allow_once"}, "dwell", 1) == (409, {"error": "expired"})
    assert card_of(b, a).state == "expired"


def test_deciding_card_runs_past_deadline_then_undo_expires(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    clock.advance(299.5)
    keepalive(b, a)
    assert b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    clock.advance(1.0)                               # 期限 (300) を越えた・猶予のうち
    b.tick()
    assert card_of(b, a).state == "deciding"         # 期限の前に受けた答えは猶予を完走する
    assert b.undo(a, "key", 1) == (200, {"state": "expired"})   # 期限の後の取り消し = expired
    assert card_of(b, a).state == "expired"


def test_deciding_card_past_deadline_is_delivered(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    clock.advance(299.5)
    keepalive(b, a)
    b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    clock.advance(3.0)                               # 302.5 = 期限の 2.5 秒後
    code, body, card = b.wait(a)
    assert body["state"] == "answered"
    b.delivered(card, True)
    assert card_of(b, a).state == "answered"


def test_two_pages_second_answer_409(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    code, body = b.answer(a, seq, {"type": "stop"}, "touch", 1)
    assert code == 409 and body["error"] == "not_shown"
    assert card_of(b, a).choice == {"type": "allow_once"}


def test_answer_to_not_current_card_409(clock):
    b = new_board(clock)
    ask(b)
    c = ask(b)
    assert b.answer(c, 1, {"type": "allow_once"}, "dwell", 1) == (409, {"error": "not_current"})
    assert b.answer("nope", 1, {"type": "allow_once"}, "dwell", 1) == (409, {"error": "not_current"})


def test_disconnect_when_waits_stop(clock):
    b = new_board(clock)
    a = ask(b)
    clock.advance(5.1)                               # /ask から 5 秒、/wait が来ない
    b.tick()
    assert card_of(b, a).state == "disconnected"
    assert b.pending(-1)["last"]["from_deciding"] is False


def test_disconnect_during_grace_says_not_delivered(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    keepalive(b, a)
    b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    clock.advance(5.1)
    b.tick()
    assert card_of(b, a).state == "disconnected"
    last = b.pending(-1)["last"]
    assert last["end"] == "disconnected" and last["from_deciding"] is True


def test_failed_delivery_is_disconnected(clock):
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    clock.advance(3.0)
    code, body, card = b.wait(a)
    b.delivered(card, False)
    assert card_of(b, a).state == "disconnected"


def test_waiting_hook_is_not_disconnected(clock):
    b = new_board(clock)
    a = ask(b)
    c = b._find(a)
    c.wait_inflight = 1                              # /wait を抱えている間
    clock.advance(60)
    b.tick()
    assert c.state == "shown"


def test_queue_full_is_503(clock):
    b = new_board(clock)
    for _ in range(20):
        ask(b)
    code, body = b.ask("permission", {}, dict(PERM))
    assert code == 503


@pytest.mark.parametrize("kind,choice", [
    ("permission", {"type": "answer", "picks": [[0]]}),
    ("permission", {"type": "deny"}),
    ("permission", {"type": "allow_always", "suggestion": -1}),
    ("permission", {"type": "allow_always", "suggestion": True}),
    ("question", {"type": "answer", "picks": [["0"]]}),
    ("question", {"type": "answer", "picks": []}),
    ("question", {"type": "stop"}),
    ("elicitation", {"type": "allow_once"}),
    ("elicitation", "accept"),
])
def test_bad_choice_is_400(clock, kind, choice):
    b = new_board(clock)
    payload = {"questions": []} if kind == "question" else ({"fields": []} if kind == "elicitation" else dict(PERM))
    a = ask(b, kind, payload)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, choice, "dwell", 1)[0] == 400
    assert card_of(b, a).state == "shown"


def test_bad_ask_is_400(clock):
    b = new_board(clock)
    assert b.ask("other", {}, {})[0] == 400
    assert b.ask("permission", {}, "text")[0] == 400


def test_log_keeps_only_choice_time_and_counts(clock, tmp_path):
    b = new_board(clock, tmp_path)
    secret = "TOP-SECRET-COMMAND-TEXT"
    a = ask(b, "permission", {"head": "Bash", "blocks": [{"text": secret}]})
    seq = b.pending(-1)["card"]["view_seq"]
    b.answer(a, seq, {"type": "allow_once"}, "dwell", {"dwell": 1, "key": 1})
    clock.advance(3.0)
    _, _, card = b.wait(a)
    b.delivered(card, True)
    files = list(tmp_path.glob("log-*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert secret not in text and "Bash" not in text
    rec = json.loads(text.strip().splitlines()[-1])
    assert set(rec) == {"t", "kind", "end", "choice", "sec", "by", "presses", "undo"}
    assert rec["kind"] == "permission" and rec["end"] == "answered" and rec["choice"] == "allow_once"
    assert rec["presses"] == 2 and rec["undo"] == 0 and rec["by"] == "dwell"


def test_no_log_dir_writes_nothing(clock, tmp_path):
    b = new_board(clock, None)
    a = ask(b)
    clock.advance(301)
    keepalive(b, a)
    assert list(tmp_path.iterdir()) == []


def test_light_and_stats_reset(clock):
    b = new_board(clock)
    b.notify({"type": "idle_prompt", "message": "Claude is waiting", "from": {"cwd": "repo"}})
    snap = b.pending(-1)
    assert snap["light"]["type"] == "idle_prompt" and snap["light"]["remaining"] == 10
    clock.advance(10.1)
    b.tick()
    assert b.pending(-1)["light"] is None
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    b.answer(a, seq, {"type": "allow_once"}, "touch", 2)
    assert b.pending(-1)["stats"]["presses"]["touch"] == 2
    b.reset_stats()
    st = b.pending(-1)["stats"]
    assert st["total"] == 0 and st["answers"] == 0 and st["elapsed"] == 0


def test_pending_returns_new_seq(clock):
    b = new_board(clock)
    s1 = b.pending(-1)["seq"]
    assert b.pending(s1)["seq"] == s1                # 変わらなければ同じ (抱える秒 0)
    ask(b)
    assert b.pending(s1)["seq"] > s1


def test_undo_keeps_the_first_deadline(clock):
    """取り消しで shown へ戻しても期限は最初の表示のまま (延びない・§3.6 の 2)。"""
    b = new_board(clock)
    t0 = clock.t
    a = ask(b)
    for _ in range(62):                               # 248 秒
        clock.advance(4)
        keepalive(b, a)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    clock.advance(1)
    assert b.undo(a, "key", 1) == (200, {"state": "shown"})
    assert card_of(b, a).deadline == pytest.approx(t0 + 300)
    for _ in range(12):                               # 297 秒
        clock.advance(4)
        keepalive(b, a)
    assert card_of(b, a).state == "shown"
    clock.advance(3.5)
    keepalive(b, a)
    assert card_of(b, a).state == "expired"           # 最初の表示から 300 秒で切れる


def test_finish_twice_counts_and_logs_once(clock, tmp_path):
    b = new_board(clock, tmp_path)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)
    clock.advance(3.0)
    _, _, card = b.wait(a)
    b.delivered(card, True)
    with b.cond:
        b._finish(card, "expired", clock())          # 後から来た終わりは捨てる
    b._flush_logs()
    assert card.end == "answered"
    assert b.pending(-1)["stats"]["answers"] == 1
    lines = next(tmp_path.glob("log-*.jsonl")).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_answer_still_ok_after_other_ask_and_notify(clock):
    """全体の seq が進んでも (別の札・待ちの合図)、表示が同じなら押しは通る。"""
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    s0 = b.seq
    ask(b)
    b.notify({"type": "idle_prompt", "message": "m"})
    assert b.seq > s0 and b.pending(-1)["card"]["view_seq"] == seq
    assert b.answer(a, seq, {"type": "allow_once"}, "dwell", 1)[0] == 200


# ---- 見る人の判定 (頁を閉じている時は札を受けない = 端末が最長 5 分止まって見えない) ----

def test_ask_ok_within_startup_grace(clock):
    b = new_board(clock, viewer=30.0)
    clock.advance(29.9)                               # 起動も「見た」と数える
    assert b.ask("permission", {}, dict(PERM))[0] == 200


def test_ask_refused_after_viewer_seconds_then_ok_once_a_page_looks(clock):
    b = new_board(clock, viewer=30.0)
    clock.advance(30.1)
    assert b.ask("permission", {}, dict(PERM)) == (503, {"error": "no_viewer"})
    b.pending(-1)                                     # 頁が 1 回見た (抱える秒 0 = すぐ返る)
    assert b.ask("permission", {}, dict(PERM))[0] == 200


def test_viewer_gone_expires_queued_but_deciding_completes(clock):
    b = new_board(clock, viewer=30.0)
    a = ask(b)
    c = ask(b)
    for _ in range(7):                                # 28 秒 (hook は居る・頁は見ていない)
        clock.advance(4)
        keepalive(b, a, c)
    assert b.answer(a, card_of(b, a).view_seq, {"type": "allow_once"}, "dwell", 1)[0] == 200
    clock.advance(2.5)                                # 30.5 秒 = 見る人なし
    keepalive(b, a, c)
    assert card_of(b, c).state == "expired"           # 待ちの札は切れる
    assert card_of(b, c).first_shown is None
    assert card_of(b, a).state == "deciding"          # 決めた札は猶予を完走する
    clock.advance(0.6)
    _, body, card = b.wait(a)
    assert body == {"state": "answered", "answer": {"type": "allow_once"}}
    b.delivered(card, True)
    assert card_of(b, a).state == "answered"


def test_viewer_gone_expires_the_shown_card(clock):
    b = new_board(clock, viewer=30.0)
    a = ask(b)
    for _ in range(7):
        clock.advance(4)
        keepalive(b, a)
    assert card_of(b, a).state == "shown"
    clock.advance(3)                                  # 31 秒
    keepalive(b, a)
    assert card_of(b, a).state == "expired"
