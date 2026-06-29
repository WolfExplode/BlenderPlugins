bl_info = {
    "name": "Open Console on Startup",
    "author": "WXP",
    "version": (1, 0, 0),
    "blender": (3, 2, 0),
    "location": "",
    "description": "When Blender starts, open the system console (Windows) on the second monitor top-left",
    "category": "System",
}

import os
import sys

import bpy

_TOGGLE_TRIED = False
_RETRY_COUNT = 0
_MAX_RETRIES = 80
_FIRST_DELAY_S = 0.25

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    _MONITORINFOF_PRIMARY = 1

    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.c_void_p,
        wintypes.LPARAM,
    )

    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, _MONITORENUMPROC, wintypes.LPARAM]
    _user32.EnumDisplayMonitors.restype = wintypes.BOOL

    def _work_area_top_left_second_monitor_win32():
        """Top-left of the work area on the first non-primary monitor; else primary."""
        rows = []

        def _enum_monitor(hmon, _hdc, _prc, _lp):
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                primary = bool(mi.dwFlags & _MONITORINFOF_PRIMARY)
                rows.append((mi.rcWork.left, mi.rcWork.top, primary))
            return True

        cb = _MONITORENUMPROC(_enum_monitor)
        _user32.EnumDisplayMonitors(None, None, cb, 0)
        if not rows:
            return 0, 0
        non_primary = [r for r in rows if not r[2]]
        if non_primary:
            non_primary.sort(key=lambda r: (r[0], r[1]))
            return non_primary[0][0], non_primary[0][1]
        rows.sort(key=lambda r: (r[0], r[1]))
        return rows[0][0], rows[0][1]

    def _find_console_hwnd_win32():
        target_pid = os.getpid()
        found = []

        def _enum(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != target_pid:
                return True
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == "ConsoleWindowClass":
                found.append(hwnd)
                return False
            return True

        cb = _WNDENUMPROC(_enum)
        _user32.EnumWindows(cb, 0)
        return found[0] if found else None

    def _place_console_top_left_win32(hwnd):
        x, y = _work_area_top_left_second_monitor_win32()
        _user32.SetWindowPos(
            hwnd,
            None,
            int(x),
            int(y),
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW,
        )
else:

    def _find_console_hwnd_win32():
        return None

    def _place_console_top_left_win32(_hwnd):
        pass


def _console_toggle():
    wm = bpy.context.window_manager
    if not wm.windows:
        raise RuntimeError("no Blender windows yet")
    win = wm.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.wm.console_toggle()


def _startup_once():
    global _TOGGLE_TRIED, _RETRY_COUNT

    if sys.platform != "win32":
        return None

    wm = bpy.context.window_manager
    if not wm.windows:
        _RETRY_COUNT += 1
        return None if _RETRY_COUNT > _MAX_RETRIES else 0.1

    hwnd = _find_console_hwnd_win32()
    if hwnd:
        _place_console_top_left_win32(hwnd)
        return None

    if not _TOGGLE_TRIED:
        _TOGGLE_TRIED = True
        try:
            _console_toggle()
        except Exception:
            pass

    _RETRY_COUNT += 1
    if _RETRY_COUNT > _MAX_RETRIES:
        return None

    hwnd = _find_console_hwnd_win32()
    if hwnd:
        _place_console_top_left_win32(hwnd)
        return None

    return 0.15


def _begin_console_timer():
    """Reset state and (re)start the polling timer. Safe to call multiple times."""
    global _TOGGLE_TRIED, _RETRY_COUNT
    _TOGGLE_TRIED = False
    _RETRY_COUNT = 0
    try:
        bpy.app.timers.unregister(_startup_once)
    except ValueError:
        pass
    bpy.app.timers.register(_startup_once, first_interval=_FIRST_DELAY_S)


@bpy.app.handlers.persistent
def _on_load_post(_dummy):
    """After a .blend finishes loading (including default startup)."""
    if sys.platform != "win32":
        return
    _begin_console_timer()


def register():
    if sys.platform != "win32":
        return
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    _begin_console_timer()


def unregister():
    try:
        bpy.app.handlers.load_post.remove(_on_load_post)
    except ValueError:
        pass
    try:
        bpy.app.timers.unregister(_startup_once)
    except ValueError:
        pass
