"""扇の窓の最前面と透過 (Windows だけ・標準ライブラリの ctypes)。

頁が開いている Chrome / Edge の app の窓だけを、窓の名で探して触る。
他の OS・窓が見つからない・API が失敗した時は何もしない = 窓はそのまま (退化)。
"""
from __future__ import annotations

import math
import sys
from typing import Any, Optional

TITLE = "BLEMMA · 扇 (OhGi)"
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
PER_MONITOR_AWARE_V2 = -4


def _number(value: Any, low: float, high: float) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
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


def _find(u: Any, wintypes: Any, ctypes: Any) -> list:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd: int, _: int) -> bool:
        if not u.IsWindowVisible(hwnd):
            return True
        name, kind = ctypes.create_unicode_buffer(128), ctypes.create_unicode_buffer(64)
        u.GetWindowTextW(hwnd, name, 128)
        u.GetClassNameW(hwnd, kind, 64)
        if name.value == TITLE and kind.value == WINDOW_CLASS:
            found.append(hwnd)
        return True

    u.EnumWindows(visit, 0)
    return found


def _apply(data: dict) -> dict:
    import ctypes
    from ctypes import wintypes

    u, g, d = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("dwmapi")
    u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    g.CreateRectRgn.restype = wintypes.HRGN
    g.CreatePolygonRgn.restype = wintypes.HRGN
    g.CreatePolygonRgn.argtypes = [ctypes.POINTER(wintypes.POINT), ctypes.c_int, ctypes.c_int]
    g.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    def attribute(hwnd: int, name: int, value: int) -> None:
        number = ctypes.c_int(value)
        d.DwmSetWindowAttribute(wintypes.HWND(hwnd), name, ctypes.byref(number), 4)

    def region(shape: dict) -> Any:
        points = (wintypes.POINT * len(shape["polygon"]))(*[wintypes.POINT(x, y) for x, y in shape["polygon"]])
        target = g.CreatePolygonRgn(points, len(shape["polygon"]), WINDING)
        parts = [g.CreateRectRgn(*box) for box in shape["rects"]]
        if shape["band"]:
            parts.append(g.CreateRectRgn(*shape["band"]))
        for part in parts:
            g.CombineRgn(target, target, part, RGN_OR)
            g.DeleteObject(part)
        return target                    # 窓に渡した region は Windows が持つ

    previous = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(PER_MONITOR_AWARE_V2))
    try:
        windows = _find(u, wintypes, ctypes)
        if not windows:
            return {"found": False}
        pin = data.get("pin")
        wants_shape = "shape" in data
        shape = clean_shape(data.get("shape")) if wants_shape else None
        for hwnd in windows:
            if isinstance(pin, bool):
                u.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST if pin else HWND_NOTOPMOST), 0, 0, 0, 0,
                               SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
            if not wants_shape:
                continue
            if shape is None:
                u.SetWindowRgn(hwnd, None, True)
                attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_USEWINDOWSTYLE)
                attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_AUTO)
                continue
            box = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(box))
            attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED)
            attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
            u.SetWindowRgn(hwnd, region(device_shape(shape, box.right - box.left)), True)
        return {"found": True, "pin": bool(u.GetWindowLongPtrW(windows[0], GWL_EXSTYLE) & WS_EX_TOPMOST)}
    finally:
        u.SetThreadDpiAwarenessContext(previous)


def apply(data: Any) -> dict:
    """{"pin": bool?, "shape": 形 | None?} を窓に当てる。当たらない時は {"found": False}。"""
    if sys.platform != "win32" or not isinstance(data, dict):
        return {"found": False}
    try:
        return _apply(data)
    except (OSError, ValueError, TypeError, AttributeError):
        return {"found": False}
