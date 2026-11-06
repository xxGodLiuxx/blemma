"""扇の窓の最前面と透過: 頁から来た形の確かめと、当たらない時に何もしない事。"""
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


def test_device_shape_uses_real_pixels_and_keeps_the_title_bar():
    got = W.device_shape(W.clean_shape(good_shape(polygon=[[0, 0], [100, 0], [100, 100]], rects=[[10, 20, 30, 40]])), 960)
    assert got["band"] == (10, 0, 950, 615)                       # 題の帯 + 和紙の下端まで・見えない枠は除く
    assert got["polygon"][1] == (160, 45)
    assert got["rects"] == [(26, 75, 70, 135)]


def test_closed_fan_hides_the_title_bar():
    got = W.device_shape(W.clean_shape(good_shape(bare=True)), 960)
    assert got["band"] is None and len(got["polygon"]) == 3
    assert W.clean_shape(good_shape(bare="yes"))["bare"] is False


def test_apply_does_nothing_without_a_request_body(monkeypatch):
    assert W.apply("x") == {"found": False}
    monkeypatch.setattr(W.sys, "platform", "linux")
    assert W.apply({"pin": True}) == {"found": False}


def test_apply_is_quiet_when_the_system_call_fails(monkeypatch):
    def fail(_):
        raise OSError("no window system")
    monkeypatch.setattr(W.sys, "platform", "win32")
    monkeypatch.setattr(W, "_apply", fail)
    assert W.apply({"pin": True}) == {"found": False}
