"""扇の窓の最前面と透過 (Windows だけ・標準ライブラリの ctypes)。

頁が開いている Chrome / Edge の app の窓のうち、この板の 1 枚だけを窓の名で探して触る。
他の OS・窓が見つからない・同じ名の窓が 2 枚以上ある・API が失敗した時は窓を切らない (退化)。
同じ名の窓が 2 枚以上の時も、戻す向きの頼み (固定を外す・四角へ戻す) だけは、その全部に当てる。
"""
from __future__ import annotations

import math
import sys
import threading
from typing import Any, Optional

TITLE = "BLEMMA · 扇 (OhGi)"
DEFAULT_PORT = 8765
WINDOW_CLASS = "Chrome_WidgetWin_1"
MAX_RECTS = 8
MAX_POINTS = 256
LIMIT = 32768

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
DWMWA_NCRENDERING_POLICY, DWMWA_SYSTEMBACKDROP_TYPE = 2, 38
DWMNCRP_USEWINDOWSTYLE, DWMNCRP_DISABLED = 0, 1
DWMSBT_AUTO, DWMSBT_NONE = 0, 1
WINDING, RGN_OR = 2, 2
RGN_ERROR, NULLREGION = 0, 1          # GetRgnBox の返り (2・3 = 面積のある形)
PER_MONITOR_AWARE_V2 = -4

_ONE_AT_A_TIME = threading.Lock()     # 頁からの頼みが重なっても、窓へは 1 つずつ順に当てる


def title_for(port: Any) -> str:
    """この板の窓の名。既定の port の板は名だけ、ほかの port の板は名に port を足す
    (頁の BlemmaCore.windowTitle と同じ決まり)。別の port で起こした板の窓を、こちらの形で切らないための印。"""
    return TITLE if port == DEFAULT_PORT else f"{TITLE} · {port}"


def _number(value: Any, low: float, high: float) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):      # JSON の整数は桁に限りが無い = float に収まらない数は壊れた形として断る
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def _pair(item: Any) -> Optional[tuple]:
    if not isinstance(item, (list, tuple)) or len(item) != 2:
        return None
    x, y = _number(item[0], -LIMIT, LIMIT), _number(item[1], -LIMIT, LIMIT)
    return None if x is None or y is None else (x, y)


def clean_shape(shape: Any) -> Optional[dict]:
    """頁から来た形を確かめる。壊れている時は None = 窓を切らない。"""
    if not isinstance(shape, dict):
        return None
    dpr = _number(shape.get("dpr"), 0.5, 5)
    left = _number(shape.get("left"), 0, 200)
    top = _number(shape.get("top"), 0, 400)
    keep = _number(shape.get("keep"), 0, LIMIT)
    polygon, rects = shape.get("polygon"), shape.get("rects")
    if None in (dpr, left, top, keep) or not isinstance(polygon, list) or not isinstance(rects, list):
        return None
    if not 3 <= len(polygon) <= MAX_POINTS or len(rects) > MAX_RECTS:
        return None
    points = [_pair(p) for p in polygon]
    boxes = []
    for r in rects:
        if not isinstance(r, (list, tuple)) or len(r) != 4:
            return None
        box = [_number(v, -LIMIT, LIMIT) for v in r]
        if None in box:
            return None
        boxes.append(box)
    if None in points:
        return None
    return {"dpr": dpr, "left": left, "top": top, "keep": keep, "polygon": points, "rects": boxes, "bare": shape.get("bare") is True}


def device_shape(shape: dict, width: int) -> dict:
    """CSS の座標を窓の中の実の画素へ直す。題の帯は残す (bare = 閉じた扇の時だけ隠す)。"""
    dpr, left, top = shape["dpr"], shape["left"], shape["top"]

    def point(x: float, y: float) -> tuple:
        return round((left + x) * dpr), round((top + y) * dpr)

    edge = round(left * dpr)
    band = None if shape["bare"] else (edge, 0, width - edge, round((top + shape["keep"]) * dpr))
    rects = []
    for x, y, w, h in shape["rects"]:
        x0, y0 = point(x, y)
        x1, y1 = point(x + w, y + h)
        rects.append((x0, y0, x1, y1))
    return {"band": band, "rects": rects, "polygon": [point(x, y) for x, y in shape["polygon"]]}


class _Win:
    """窓に触る Win32 の呼び出し。どれも戻り値を見て、成否を bool で返す (試験では偽物に差し替える)。"""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.c, self.w = ctypes, wintypes
        u, g, d = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("dwmapi")
        self.u, self.g, self.d = u, g, d
        u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        # 32bit の Python の user32 には GetWindowLongPtrW が無い = 窓に触る前に、在る方を選んでおく
        self.style = getattr(u, "GetWindowLongPtrW", None) or u.GetWindowLongW
        self.style.restype = ctypes.c_ssize_t
        self.style.argtypes = [wintypes.HWND, ctypes.c_int]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowRect.restype = wintypes.BOOL
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.SetWindowPos.restype = wintypes.BOOL
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.SetWindowRgn.restype = ctypes.c_int
        u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        g.CreateRectRgn.restype = wintypes.HRGN
        g.CreateRectRgn.argtypes = [ctypes.c_int] * 4
        g.CreatePolygonRgn.restype = wintypes.HRGN
        g.CreatePolygonRgn.argtypes = [ctypes.POINTER(wintypes.POINT), ctypes.c_int, ctypes.c_int]
        g.CombineRgn.restype = ctypes.c_int
        g.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
        g.GetRgnBox.restype = ctypes.c_int
        g.GetRgnBox.argtypes = [wintypes.HRGN, ctypes.POINTER(wintypes.RECT)]
        g.DeleteObject.restype = wintypes.BOOL
        g.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    def enter(self) -> Any:
        return self.u.SetThreadDpiAwarenessContext(self.c.c_void_p(PER_MONITOR_AWARE_V2))

    def leave(self, previous: Any) -> None:
        self.u.SetThreadDpiAwarenessContext(previous)

    def find(self, title: str) -> list:
        """見えている窓のうち、名が title と同じ Chrome / Edge の窓。"""
        c, w, u, found = self.c, self.w, self.u, []

        @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def visit(hwnd: int, _: int) -> bool:
            if u.IsWindowVisible(hwnd):
                name, kind = c.create_unicode_buffer(128), c.create_unicode_buffer(64)
                u.GetWindowTextW(hwnd, name, 128)
                u.GetClassNameW(hwnd, kind, 64)
                if name.value == title and kind.value == WINDOW_CLASS:
                    found.append(hwnd)
            return True

        u.EnumWindows(visit, 0)
        return found

    def pin(self, hwnd: int, on: bool) -> bool:
        return bool(self.u.SetWindowPos(hwnd, self.w.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST), 0, 0, 0, 0,
                                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE))

    def pinned(self, hwnd: int) -> bool:
        return bool(self.style(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    def width(self, hwnd: int) -> Optional[int]:
        box = self.w.RECT()
        return box.right - box.left if self.u.GetWindowRect(hwnd, self.c.byref(box)) else None

    def _attribute(self, hwnd: int, name: int, value: int) -> None:
        number = self.c.c_int(value)            # 見た目だけの属性 = 失敗しても窓は使える
        self.d.DwmSetWindowAttribute(self.w.HWND(hwnd), name, self.c.byref(number), 4)

    def cut(self, hwnd: int, shape: dict) -> bool:
        """窓を形に切る。途中で失敗したら、作った region を解放して False を返す。"""
        g, w = self.g, self.w
        count = len(shape["polygon"])
        points = (w.POINT * count)(*[w.POINT(x, y) for x, y in shape["polygon"]])
        target = g.CreatePolygonRgn(points, count, WINDING)
        if not target:
            return False
        for box in list(shape["rects"]) + ([shape["band"]] if shape["band"] else []):
            part = g.CreateRectRgn(*box)
            joined = bool(part) and g.CombineRgn(target, target, part, RGN_OR) != 0     # 0 = ERROR
            if part:
                g.DeleteObject(part)
            if not joined:
                g.DeleteObject(target)
                return False
        box = w.RECT()
        if g.GetRgnBox(target, self.c.byref(box)) in (RGN_ERROR, NULLREGION):
            g.DeleteObject(target)              # 面積 0 の形を当てると、窓が丸ごと見えず押せなくなる = 当てない
            return False
        self._attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED)
        self._attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
        if self.u.SetWindowRgn(hwnd, target, True):
            return True                         # 成功した時だけ、region は Windows の持ち物になる
        g.DeleteObject(target)                  # 失敗 = まだこちらの持ち物 → 解放する
        return False

    def uncut(self, hwnd: int) -> bool:
        """切る前の四角い窓へ戻す。"""
        done = bool(self.u.SetWindowRgn(hwnd, None, True))
        self._attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_USEWINDOWSTYLE)
        self._attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_AUTO)
        return done


def _drive(win: Any, data: dict, title: str) -> dict:
    """この板の窓 1 枚にだけ当てる。0 枚 = 何もしない。2 枚以上 = どの窓が頼んだ頁か決められないので、
    切らず固定もしない (戻す向きの「固定を外す」「四角へ戻す」だけは、同じ名の窓の全部に当てる)。"""
    windows = win.find(title)
    wants_shape = "shape" in data
    pin = data.get("pin")
    if len(windows) != 1:
        if pin is False:                        # 前に固定した窓が、外せないまま手前に残らないよう、全部から外す
            for hwnd in windows:
                win.pin(hwnd, False)
        if wants_shape:
            for hwnd in windows:                # 前に切った形が残らないよう、同じ名の窓は四角へ戻す
                win.uncut(hwnd)
        return {"found": False}
    hwnd, ok = windows[0], True
    if isinstance(pin, bool):
        ok = win.pin(hwnd, pin) and ok
    if wants_shape:
        raw = data.get("shape")
        shape = clean_shape(raw)
        if shape is None:
            ok = win.uncut(hwnd) and ok
            if raw is not None:                 # null でないのに読めない形 = 四角へ戻した上で失敗を返す
                ok = False                      # (頁が当たったと思って送り直さない、を作らない)
        else:
            width = win.width(hwnd)
            if width is None or not win.cut(hwnd, device_shape(shape, width)):
                win.uncut(hwnd)                 # 切れなかった = 古い形を残さず、四角い窓へ
                ok = False
    return {"found": True, "ok": ok, "pin": win.pinned(hwnd)}


def _apply(data: dict, title: str) -> dict:
    win = _Win()
    previous = win.enter()
    try:
        return _drive(win, data, title)
    finally:
        win.leave(previous)


def apply(data: Any, port: Any = DEFAULT_PORT) -> dict:
    """{"pin": bool?, "shape": 形 | None?} を、port の板の窓に当てる。当たらない時は {"found": False}。
    窓は見つかったが API が失敗した・形が読めない・面積 0 の形の時は {"found": True, "ok": False}
    (窓は四角へ戻す・頁が送り直すか、別の手段へ切り替える)。"""
    if sys.platform != "win32" or not isinstance(data, dict):
        return {"found": False}
    try:
        with _ONE_AT_A_TIME:
            return _apply(data, title_for(port))
    except Exception:                           # 窓の操作は飾り = 何が起きても板は止めない (勝手に答えもしない)
        return {"found": False}
