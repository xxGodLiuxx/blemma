"""扇の窓の最前面と透過: 頁から来た形の確かめ・この板の 1 枚だけに当てる事・当たらない時に何もしない事。"""
import ctypes
from ctypes import wintypes

import pytest

import window_win as W


def good_shape(**change):
    shape = {"dpr": 1.5, "left": 7, "top": 30, "keep": 380, "polygon": [[0, 0], [10, 0], [10, 10]], "rects": [[1, 2, 3, 4]]}
    shape.update(change)
    return shape


def test_clean_shape_keeps_a_good_shape():
    got = W.clean_shape(good_shape())
    assert got["dpr"] == 1.5 and got["polygon"] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)] and got["rects"] == [[1.0, 2.0, 3.0, 4.0]]


def test_clean_shape_refuses_a_broken_shape():
    for broken in (None, "x", [], good_shape(dpr=0), good_shape(dpr=True), good_shape(dpr="1"), good_shape(left=-1),
                   good_shape(keep=float("nan")), good_shape(polygon=[[0, 0], [1, 1]]), good_shape(polygon=[[0, 0]] * (W.MAX_POINTS + 1)),
                   good_shape(polygon=[[0, 0], [1, 1], ["a", 2]]), good_shape(polygon=[[0, 0], [1, 1], [W.LIMIT * 2, 2]]),
                   good_shape(rects=[[1, 2, 3]]), good_shape(rects=[[0, 0, 1, 1]] * (W.MAX_RECTS + 1)), good_shape(rects="x")):
        assert W.clean_shape(broken) is None, broken


def test_clean_shape_refuses_numbers_too_big_for_a_float():
    """JSON の整数は桁に限りが無い。float に収まらない数でも例外を漏らさず、壊れた形として断る。"""
    huge = 10 ** 400
    for broken in (good_shape(dpr=huge), good_shape(left=huge), good_shape(top=-huge), good_shape(keep=huge),
                   good_shape(polygon=[[0, 0], [1, 1], [huge, 2]]), good_shape(rects=[[0, 0, huge, 1]])):
        assert W.clean_shape(broken) is None


def test_device_shape_uses_real_pixels_and_keeps_the_title_bar():
    got = W.device_shape(W.clean_shape(good_shape(polygon=[[0, 0], [100, 0], [100, 100]], rects=[[10, 20, 30, 40]])), 960)
    assert got["band"] == (10, 0, 950, 615)                       # 題の帯 + 和紙の下端まで・見えない枠は除く
    assert got["polygon"][1] == (160, 45)
    assert got["rects"] == [(26, 75, 70, 135)]


def test_closed_fan_hides_the_title_bar():
    got = W.device_shape(W.clean_shape(good_shape(bare=True)), 960)
    assert got["band"] is None and len(got["polygon"]) == 3
    assert W.clean_shape(good_shape(bare="yes"))["bare"] is False


def test_window_name_carries_the_port_only_when_it_is_not_the_default():
    assert W.title_for(W.DEFAULT_PORT) == W.TITLE == "BLEMMA · 扇 (OhGi)"
    assert W.title_for(9123) == "BLEMMA · 扇 (OhGi) · 9123"


class FakeWin:
    """窓の代用品 = 呼ばれた事を覚え、決めた成否を返す (実の窓には一切触らない)。"""

    def __init__(self, windows, fail=()):
        self.windows, self.fail, self.calls, self.top = list(windows), set(fail), [], set()

    def enter(self):
        return 1

    def leave(self, previous):
        self.calls.append(("leave", previous))

    def find(self, title):
        self.calls.append(("find", title))
        return list(self.windows)

    def pin(self, hwnd, on):
        self.calls.append(("pin", hwnd, on))
        if "pin" in self.fail:
            return False
        (self.top.add if on else self.top.discard)(hwnd)
        return True

    def pinned(self, hwnd):
        return hwnd in self.top

    def width(self, hwnd):
        return None if "width" in self.fail else 960

    def cut(self, hwnd, shape):
        self.calls.append(("cut", hwnd))
        return "cut" not in self.fail

    def uncut(self, hwnd):
        self.calls.append(("uncut", hwnd))
        return "uncut" not in self.fail


def test_only_the_single_window_of_this_board_is_touched():
    win = FakeWin([11])
    assert W._drive(win, {"pin": True, "shape": good_shape()}, "name") == {"found": True, "ok": True, "pin": True}
    assert win.calls == [("find", "name"), ("pin", 11, True), ("cut", 11)]


def test_no_window_means_nothing_is_touched():
    win = FakeWin([])
    assert W._drive(win, {"pin": True, "shape": good_shape()}, "name") == {"found": False}
    assert win.calls == [("find", "name")]


def test_two_windows_with_the_same_name_are_never_cut():
    """同じ名の窓が 2 枚 = どちらが頼んだ頁か決められない。片方の形でもう片方を切らず、前の形も残さない。"""
    win = FakeWin([11, 12])
    assert W._drive(win, {"pin": True, "shape": good_shape()}, "name") == {"found": False}
    assert win.calls == [("find", "name"), ("uncut", 11), ("uncut", 12)]
    only_pin = FakeWin([11, 12])
    assert W._drive(only_pin, {"pin": True}, "name") == {"found": False}
    assert only_pin.calls == [("find", "name")]


@pytest.mark.parametrize("fail, calls", [
    ("cut", [("cut", 11), ("uncut", 11)]),          # 切れなかった = 四角い窓へ戻す
    ("width", [("uncut", 11)]),                     # 窓の幅が読めない = 切らない
])
def test_a_failed_cut_is_reported_and_leaves_a_plain_window(fail, calls):
    win = FakeWin([11], fail={fail})
    assert W._drive(win, {"shape": good_shape()}, "name") == {"found": True, "ok": False, "pin": False}
    assert win.calls == [("find", "name")] + calls


def test_a_failed_pin_is_reported_with_the_real_state():
    win = FakeWin([11], fail={"pin"})
    assert W._drive(win, {"pin": True}, "name") == {"found": True, "ok": False, "pin": False}


def test_a_broken_or_empty_shape_returns_the_window_to_a_rectangle():
    for shape in (None, good_shape(dpr=10 ** 400)):
        win = FakeWin([11])
        assert W._drive(win, {"shape": shape}, "name") == {"found": True, "ok": True, "pin": False}
        assert win.calls == [("find", "name"), ("uncut", 11)]


class FakeGdi:
    """gdi32 の代用品。region を番号で配り、解放された番号を覚える。"""

    def __init__(self, polygon=100, combine=1):
        self.polygon, self.combine, self.next, self.freed = polygon, combine, 200, []

    def CreatePolygonRgn(self, points, count, mode):
        return self.polygon

    def CreateRectRgn(self, *box):
        self.next += 1
        return self.next

    def CombineRgn(self, target, a, b, mode):
        return self.combine

    def DeleteObject(self, handle):
        self.freed.append(handle)
        return 1


class FakeUser:
    def __init__(self, set_region=1):
        self.set_region, self.regions = set_region, []

    def SetWindowRgn(self, hwnd, region, redraw):
        self.regions.append(region)
        return self.set_region


class FakeDwm:
    def DwmSetWindowAttribute(self, *args):
        return 0


def real_cut(gdi, user):
    win = object.__new__(W._Win)                    # DLL を読まずに、切る手順だけを代用品で通す
    win.c, win.w, win.g, win.u, win.d = ctypes, wintypes, gdi, user, FakeDwm()
    shape = W.device_shape(W.clean_shape(good_shape()), 960)        # 四角 1 つ + 題の帯 = 部品 2 つ
    return win.cut(11, shape)


def test_cut_gives_the_region_to_windows_only_on_success():
    gdi, user = FakeGdi(), FakeUser()
    assert real_cut(gdi, user) is True
    assert user.regions == [100] and gdi.freed == [201, 202]        # 部品は解放・本体は Windows の持ち物


def test_cut_frees_the_region_when_windows_refuses_it():
    gdi, user = FakeGdi(), FakeUser(set_region=0)
    assert real_cut(gdi, user) is False
    assert gdi.freed == [201, 202, 100]                             # 断られた本体は、こちらで解放する


def test_cut_stops_and_frees_everything_when_a_part_cannot_be_joined():
    gdi, user = FakeGdi(combine=0), FakeUser()
    assert real_cut(gdi, user) is False
    assert gdi.freed == [201, 100] and user.regions == []


def test_cut_does_nothing_when_the_region_cannot_be_made():
    gdi, user = FakeGdi(polygon=0), FakeUser()
    assert real_cut(gdi, user) is False
    assert gdi.freed == [] and user.regions == []


def test_apply_does_nothing_without_a_request_body(monkeypatch):
    assert W.apply("x") == {"found": False}
    monkeypatch.setattr(W.sys, "platform", "linux")
    assert W.apply({"pin": True}) == {"found": False}


def test_apply_looks_for_the_window_of_its_own_port(monkeypatch):
    made = []

    def make():
        made.append(FakeWin([7]))
        return made[-1]

    monkeypatch.setattr(W.sys, "platform", "win32")
    monkeypatch.setattr(W, "_Win", make)
    assert W.apply({"pin": True}, 9123) == {"found": True, "ok": True, "pin": True}
    assert made[0].calls == [("find", "BLEMMA · 扇 (OhGi) · 9123"), ("pin", 7, True), ("leave", 1)]
    assert W.apply({"pin": False}) == {"found": True, "ok": True, "pin": False}
    assert made[1].calls[0] == ("find", "BLEMMA · 扇 (OhGi)")


@pytest.mark.parametrize("error", [OSError("no window system"), OverflowError("too big"), RuntimeError("anything")])
def test_apply_is_quiet_when_the_system_call_fails(monkeypatch, error):
    def fail(*_):
        raise error
    monkeypatch.setattr(W.sys, "platform", "win32")
    monkeypatch.setattr(W, "_apply", fail)
    assert W.apply({"pin": True}) == {"found": False}
