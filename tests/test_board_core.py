# -*- coding: utf-8 -*-
"""板の状態の確定 (§3.4〜§3.6) を、時計を差し替えて直に確かめる (HTTP なし)。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

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


def test_page_open_counts_real_pages_not_the_startup_grace(clock):
    """起こし方が訊く「見る頁が在るか」: 起動の猶予 (見る人の判定) は数えず、頁の見張りが在る時と直後だけ True。"""
    board = S.Board(replace(S.Limits(), pending_hold=0.0, wait_hold=0.0), clock=clock)
    assert board.page_open() is False            # 起きたばかりの板 = 見る人の猶予の内でも、頁は無い
    board.pending(-1)
    assert board.page_open() is True             # 頁の見張りが、いま張り直しの間
    clock.advance(S.PAGE_GAP + 0.1)
    assert board.page_open() is False            # 頁が閉じた
    board.close()


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
    assert b.undo(a, "key", 1) == (409, {"error": "not_undoable", "state": "deciding"})   # 答えが渡る所


def test_refused_undo_tells_whether_the_card_is_back(clock):
    """断った取り消しは、同じ札がまだ頭に居る時だけ今の状態を添える = 頁が「ほかの頁が先に取り消した (shown = 答えは
    渡っていない)」と「答えが渡る」を見分けられる。札が替わった後・無い札には添えない。"""
    b = new_board(clock)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "allow_once"}, "click", 1)[0] == 200
    assert b.undo(a, "click", 1) == (200, {"state": "shown"})                # 1 枚目の頁の取り消し
    assert b.undo(a, "click", 1) == (409, {"error": "not_undoable", "state": "shown"})   # 2 枚目の頁 = もう戻っている
    assert card_of(b, a).state == "shown" and card_of(b, a).undos == 1
    assert b.undo("no-such-card", "click", 1) == (409, {"error": "not_undoable"})


def test_refused_undo_says_how_an_ended_card_ended(clock):
    """もう終わった札への取り消しの 409 には、/answer と同じく終わり方を添える = 頁は「答えは渡りました」を、答えが実際に
    渡った時 (answered・released) だけ出せる (反証役の再現 = 時間切れ・切断の後の 409 に何も添えず、頁が「渡りました」と出した)。
    判定の前に時間で進む物を確かめる = 接続が終わったはずの札を生きているとは答えず、取り消しも受けない。"""
    b = new_board(clock)                             # 答えを渡し終えた札
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "allow_once"}, "click", 1)[0] == 200
    clock.advance(3.01)
    _, _, card = b.wait(a)
    b.delivered(card, True)
    assert b.undo(a, "click", 1) == (409, {"error": "not_undoable", "end": "answered"})
    b = new_board(clock)                             # 期限の直前に答え、1 枚目の頁が期限の後に取り消した (expired)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    clock.advance(299.0)
    keepalive(b, a)
    assert b.answer(a, seq, {"type": "allow_once"}, "click", 1)[0] == 200
    clock.advance(1.5)
    assert b.undo(a, "click", 1) == (200, {"state": "expired"})
    assert b.undo(a, "click", 1) == (409, {"error": "not_undoable", "end": "expired"})   # 2 枚目の頁
    b = new_board(clock)                             # hook が居なくなった後に答えた札 (最後の /wait から 4 秒)
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    keepalive(b, a)
    clock.advance(4.0)
    assert b.answer(a, seq, {"type": "allow_once"}, "click", 1)[0] == 200
    clock.advance(1.5)                               # 最後の /wait から 5.5 秒 (接続の終了は 5 秒)・猶予の内
    assert b.undo(a, "click", 1) == (409, {"error": "not_undoable", "end": "disconnected"})
    assert card_of(b, a).state == "disconnected"


def test_the_board_says_which_answer_it_delivered(clock, tmp_path):
    """板は、渡った答えの名札 (tag = 頁ごとの乱数 + 送信の番号) を、「直前に終わった札」(last.answered_by) に添える = 頁は
    「自分のどの答えが渡って札が終わった」を、板の返りと写しの順に左右されずに読める (外部のレビューの所見 = 頁の側の
    推し量りでは、ほかの頁の答えが先に通った時と、同じ頁の送り直しを見分けられなかった)。取り消して答え直した時は、渡った
    答えの名札。答えが渡らずに終わった札 (時間切れ・渡す前に hook が居なくなった) には添えない。形の違う名札 (長すぎる・
    字が違う・文字列でない) は、名札なしで受ける。名札は、札の写し・hook への返り・記録の file には載せない。"""
    def deliver(board, cid):
        clock.advance(3.01)
        _, body, taken = board.wait(cid)
        board.delivered(taken, True)
        return body

    b = new_board(clock, tmp_path)
    a = ask(b)
    card = b.pending(-1)["card"]
    assert b.answer(a, card["view_seq"], {"type": "allow_once"}, "key", 1, None, "page-1:1")[0] == 200
    assert "page-1:1" not in json.dumps(b.pending(-1)["card"])             # 猶予の札の写しには載せない
    assert b.undo(a, "key", 1)[0] == 200
    card = b.pending(-1)["card"]
    assert b.answer(a, card["view_seq"], {"type": "deny", "reason": 0}, "click", 1, None, "page-2:1")[0] == 200   # ほかの頁が答え直す
    body = deliver(b, a)
    last = b.pending(-1)["last"]
    assert (last["id"], last["end"], last["answered_by"]) == (a, "answered", "page-2:1")   # 渡ったのは、答え直した頁の答え
    assert "page-" not in json.dumps(body)                                # hook へ渡す返りに、名札は載らない
    a = ask(b)                                                            # 「端末で答える」が渡って終わった札にも添える
    seq = b.pending(-1)["card"]["view_seq"]
    assert b.answer(a, seq, {"type": "terminal"}, "key", 1, None, "page-3:1")[0] == 200
    deliver(b, a)
    last = b.pending(-1)["last"]
    assert (last["id"], last["end"], last["answered_by"]) == (a, "released", "page-3:1")
    logs = "".join(f.read_text(encoding="utf-8") for f in tmp_path.glob("log-*.jsonl"))
    assert logs and "page-" not in logs                                   # 記録の file にも載らない
    for bad in ("x" * 81, "page 1", "頁", "", 7, None, ["page-1:1"]):       # 形の違う名札 = 名札なしで受ける
        b = new_board(clock)
        a = ask(b)
        seq = b.pending(-1)["card"]["view_seq"]
        assert b.answer(a, seq, {"type": "allow_once"}, "key", 1, None, bad)[0] == 200
        deliver(b, a)
        last = b.pending(-1)["last"]
        assert (last["id"], last["end"], last["answered_by"]) == (a, "answered", None), bad
    b = new_board(clock)                                                  # 時間切れで終わった札には添えない
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    clock.advance(301.0)
    assert b.answer(a, seq, {"type": "allow_once"}, "key", 1, None, "page-1:1")[0] == 409
    last = b.pending(-1)["last"]
    assert (last["id"], last["end"], last["answered_by"]) == (a, "expired", None)
    b = new_board(clock)                                                  # 答えを受けた後、渡す前に hook が居なくなった札にも添えない
    a = ask(b)
    seq = b.pending(-1)["card"]["view_seq"]
    keepalive(b, a)
    clock.advance(4.0)
    assert b.answer(a, seq, {"type": "allow_once"}, "key", 1, None, "page-1:1")[0] == 200
    clock.advance(1.5)                                                    # 最後の /wait から 5.5 秒 (接続の終了は 5 秒)
    last = b.pending(-1)["last"]
    assert (last["id"], last["end"], last["answered_by"]) == (a, "disconnected", None)


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


def test_log_day_and_time_come_from_one_clock_reading(clock, tmp_path, monkeypatch):
    """記録の行の時刻 (t) と file の日付は、時計を 1 回だけ読んで作る (1 巡目 #12 = 2 回読んでいたので、日付の変わり目に
    終わった札は 11/7 の時刻の行が log-2026-11-08.jsonl に入った)。時計は naive の現地時刻 = 機械の時間帯に依らない。"""
    from datetime import datetime as real
    readings = [real(2026, 11, 7, 23, 59, 59, 999000), real(2026, 11, 8, 0, 0, 0)]
    calls = []

    class FakeDT:
        @staticmethod
        def now(tz=None):
            calls.append(tz)
            return readings[min(len(calls), len(readings)) - 1]

    b = new_board(clock, tmp_path)
    a = ask(b)
    monkeypatch.setattr(S, "datetime", FakeDT)        # server.py は from datetime import datetime
    clock.advance(301)                                # 期限 (300 秒) を過ぎる
    keepalive(b, a)                                   # 板の時が進み、expired で終わって 1 行
    assert card_of(b, a).state == "expired"
    files = sorted(p.name for p in tmp_path.glob("log-*.jsonl"))
    assert files == ["log-2026-11-07.jsonl"]
    rec = json.loads((tmp_path / files[0]).read_text(encoding="utf-8").strip())
    assert rec["t"][:10] == "2026-11-07" and rec["end"] == "expired"
    assert calls == [None]                            # 時計を読むのは 1 回


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


def test_pending_returns_at_once_when_the_viewer_closed(clock):
    """閉じた頁の long-poll を抱え続けない = 見る人の数が残って端末へ戻るのが遅れない (実機の検収 11/6)。"""
    b = new_board(clock)
    b.lim = replace(b.lim, pending_hold=60)
    calls = []
    def closed():
        calls.append(1)
        return False
    b.pending(b.seq, alive=closed)
    assert calls and b.viewers_open == 0


# ---- 頁の計算 (board/static/board_core.js) を node の require() で = 札の字 (DOM なし) ----

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node が無い (頁の計算の試験は node で走らせる)")
CORE_JS = Path(__file__).resolve().parent.parent / "board" / "static" / "board_core.js"
ZW, RLO = "​", "‮"


def core_js(tmp_path, body: str, data) -> object:
    """board_core.js を読み、body (DATA = data の JSON) が console.log で出す JSON を返す。data は \\u の形で渡す
    (JS の source に見えない字を書かない)。"""
    script = tmp_path / "core.js"
    script.write_text(f"const core = require({json.dumps(str(CORE_JS))});\nconst DATA = {json.dumps(data)};\n" + body,
                      encoding="utf-8")
    p = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def no_raw_hidden(screen) -> bool:
    text = json.dumps(screen, ensure_ascii=False)
    return ZW not in text and RLO not in text


@needs_node
def test_question_card_shows_hidden_characters(tmp_path):
    """Claude の質問の札は、見えない字 (幅ゼロ・書字方向) を ⟨U+XXXX⟩ にして描く (1 巡目 #23 = 'Yes' と 'Ye'+U+200B+'s' の
    釦が見分けられなかった)。直すのは表示だけ = 板へ返すのは番号 (picks) で、hook が組む answers は逐語 (test_hooks)。
    1 問の札 (頭・問い・選択肢の字と説明) と、2 問の札の確かめの画面 (要約の名と選んだ字)・猶予の間の答えの字。"""
    one = {"question": "Which?" + RLO, "header": "h" + ZW, "multiSelect": False,
           "options": [{"label": "Yes"}, {"label": "Ye" + ZW + "s", "description": "d" + ZW + "x"}]}
    out = core_js(tmp_path, r"""
const one = {kind: 'question', payload: {questions: [DATA.one]}};
const two = {kind: 'question', payload: {questions: [DATA.one, DATA.two]}};
const ui = core.newUi(); ui.step = 2; ui.picks = [[1], [1]];
console.log(JSON.stringify({one: core.buildScreen(one, core.newUi(), 'ja'), confirm: core.buildScreen(two, ui, 'ja'),
  answer: core.choiceLabel(two, {type: 'answer', picks: [[1], [0]]}, 'ja'), send: core.pressKey(one, core.newUi(), 'opt:1')}));
""", {"one": one, "two": dict(one, header="k" + RLO)})
    s = out["one"]
    assert (s["head"], s["question"]) == ("h⟨U+200B⟩", "Which?⟨U+202E⟩")
    assert [(o["label"], o["desc"]) for o in s["options"]] == [("Yes", ""), ("Ye⟨U+200B⟩s", "d⟨U+200B⟩x")]
    assert out["confirm"]["summary"] == ["h⟨U+200B⟩: Ye⟨U+200B⟩s", "k⟨U+202E⟩: Ye⟨U+200B⟩s"]
    assert out["answer"] == "Ye⟨U+200B⟩s / Yes"
    assert out["send"] == {"send": {"type": "answer", "picks": [[1]]}}          # 答えは番号だけ (字は hook が逐語で引く)
    assert no_raw_hidden(out)


@needs_node
def test_mcp_card_shows_hidden_characters(tmp_path):
    """MCP の問いの札も、頭 (server の名)・本文 (message)・欄の題と説明・選択肢の字と説明・板で描けない欄の名・確かめの
    画面の要約と説明の、見えない字を ⟨U+XXXX⟩ にして描く (1 巡目 #23 = 'invoice_'+U+202E+'fdp.exe' が 'invoice_exe.pdf'
    に見えた)。題が本文と同じ 1 欄の札は、直した後の字で比べて問いを重ねて出さない。"""
    field = {"name": "ok", "title": "Open invoice_" + RLO + "fdp.exe ?", "description": "attach " + RLO + "fdp.exe",
             "required": True, "multi": False,
             "options": [{"label": "send invoice_" + RLO + "fdp.exe", "description": "d" + ZW + "x"}, {"label": "no"}]}
    payload = {"head": "srv" + RLO + "xe", "text": "Send invoice_" + RLO + "fdp.exe", "fields": [field],
               "omitted": ["note" + RLO + "txt.exe"]}
    out = core_js(tmp_path, r"""
const one = {kind: 'elicitation', payload: DATA.payload};
const two = {kind: 'elicitation', payload: Object.assign({}, DATA.payload, {fields: [DATA.field, DATA.field]})};
const same = {kind: 'elicitation', payload: Object.assign({}, DATA.payload, {text: DATA.field.title, fields: [DATA.field]})};
const ui = core.newUi(); ui.step = 2; ui.picks = [[0], [1]];
console.log(JSON.stringify({one: core.buildScreen(one, core.newUi(), 'ja'), confirm: core.buildScreen(two, ui, 'ja'),
  same: core.buildScreen(same, core.newUi(), 'ja')}));
""", {"payload": payload, "field": field})
    s = out["one"]
    assert (s["head"], s["text"]) == ("srv⟨U+202E⟩xe", "Send invoice_⟨U+202E⟩fdp.exe")
    assert s["question"] == "Open invoice_⟨U+202E⟩fdp.exe ?"
    assert "note⟨U+202E⟩txt.exe" in s["blocks"][0]["text"] and s["blocks"][1]["text"] == "attach ⟨U+202E⟩fdp.exe"
    assert [(o["label"], o["desc"]) for o in s["options"] if o["key"].startswith("opt:")] == [
        ("send invoice_⟨U+202E⟩fdp.exe", "d⟨U+200B⟩x"), ("no", "")]
    c = out["confirm"]
    assert c["summary"] == ["Open invoice_⟨U+202E⟩fdp.exe ?: send invoice_⟨U+202E⟩fdp.exe",
                            "Open invoice_⟨U+202E⟩fdp.exe ?: no"]
    assert [(b["label"], b["text"]) for b in c["blocks"][1:]] == [("Open invoice_⟨U+202E⟩fdp.exe ?", "attach ⟨U+202E⟩fdp.exe")] * 2
    assert out["same"]["question"] == "" and out["same"]["text"] == "Open invoice_⟨U+202E⟩fdp.exe ?"
    assert no_raw_hidden(out)


# hook の visible と同じ答えになるべき 17 本 = 種では拾えない 6 字・文字の後の異体字セレクタ (と組み合わせ)・正当な異体字セレクタ・
# 改行とタブ・どちらの網でも拾う字。字は古くからの物だけ (3.10 の unicodedata と node の Unicode の版の差を避ける)。
HIDDEN_CASES = [
    "a͏b", "aᅟb", "aᅠb", "aㅤb", "aﾠb", "rm⠀-rf", "r️m -rf", "x\U000e0100y",
    "⠀️", "​️", "x︎",
    "❤️", "葛\U000e0100", "\U0001f44d️", "a\tb\nc 日本語", "ok‮; rm", "a​b\r",
]


@needs_node
def test_page_and_hook_mark_the_same_hidden_characters(tmp_path):
    """頁の visibleText (board_core.js) と hook の visible (hooks/permission.py) は、同じ字に印を付ける (1 巡目 #25 = hook の網を
    広げた後も、頁は種 5 つのままで、点字の空白・ハングルの埋め字・文字の後の異体字セレクタを素通しにした)。"""
    import permission as PERM

    got = core_js(tmp_path, "console.log(JSON.stringify(DATA.map(function (s) { return core.visibleText(s); })));",
                  HIDDEN_CASES)
    want = [PERM.visible(s) for s in HIDDEN_CASES]
    assert [(case, g, w) for case, g, w in zip(HIDDEN_CASES, got, want) if g != w] == []
    assert len(got) == len(want) == 17


@needs_node
def test_visible_suggestions_drop_bypass_and_auto(tmp_path):
    """頁も「次から訊かない」に bypassPermissions と auto へ移す物を出さない (hook の offered と同じ・1 巡目 #26)。
    先頭から 2 件まで・番号は元の列のまま。"""
    sugg = [{"type": "setMode", "mode": "bypassPermissions", "destination": "session"},
            {"type": "setMode", "mode": "auto", "destination": "session"},
            {"type": "setMode", "mode": "acceptEdits", "destination": "session"},
            {"type": "addDirectories", "directories": ["/home/u/demo-repo"], "destination": "session"},
            {"type": "addRules", "rules": [{"toolName": "Bash"}], "behavior": "allow", "destination": "session"}]
    out = core_js(tmp_path, "console.log(JSON.stringify(core.visibleSuggestions(DATA).map(function (v) { return v.index; })));",
                  sugg)
    assert out == [2, 3]

