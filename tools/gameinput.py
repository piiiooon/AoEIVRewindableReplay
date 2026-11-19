"""Keyboard input to the Age of Empires IV window, and finding the game (Windows only; Fogline's own code, 2026-11-06).

Two ways in:
  - posted: window messages put straight into the game window's queue (WM_CHAR for text, WM_KEYDOWN / WM_KEYUP for
    keys). Works while the game is in the background; used to type console lines.
  - pressed: real key presses through SendInput (scan codes). Windows delivers them to whatever window is in front,
    so this module presses keys only after checking that the game window is the foreground window, and never
    brings the game window forward itself.

The SCAR console opens with a modifier + Shift + ` chord (CONSOLE_CHORDS). In the background the chord is posted
while this thread shares the game thread's input state with the modifier keys marked as held (the game reads the
key state, not only the messages); in front it is pressed for real.

Public: GAME_EXE, game_pid(), game_window(pid=None), in_front(hwnd), post_text(hwnd, text), post_key(hwnd, key,
times=1), Chord, CONSOLE_CHORDS, post_chord(hwnd, chord), press_chord(hwnd, chord) -> bool, press_key(hwnd, key)
-> bool, held(key) -> bool (is that key down on the keyboard now). Keys by name: KEYS.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes as W
from typing import NamedTuple

if sys.platform != "win32":
    raise ImportError("gameinput drives the Windows game client")

GAME_EXE = "RelicCardinal.exe"

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class Key(NamedTuple):
    vk: int          # virtual-key code (window messages)
    scan: int        # set-1 scan code (SendInput, lParam bits 16-23)
    char: int = 0    # WM_CHAR that the key also produces when posted (0 = none)
    ext: bool = False   # extended key (E0 prefix): the arrow keys - without it their scan codes are the numpad's


KEYS = {
    "enter": Key(0x0D, 0x1C, 0x0D), "backspace": Key(0x08, 0x0E, 0x08), "tab": Key(0x09, 0x0F),
    "esc": Key(0x1B, 0x01), "space": Key(0x20, 0x39), "shift": Key(0x10, 0x2A), "ctrl": Key(0x11, 0x1D),
    "alt": Key(0x12, 0x38), "grave": Key(0xC0, 0x29),
    "up": Key(0x26, 0x48, ext=True), "down": Key(0x28, 0x50, ext=True),
}
_LEFT = {"shift": 0xA0, "ctrl": 0xA2, "alt": 0xA4}     # left-hand vk of a modifier (also marked in the key state)


class Chord(NamedTuple):
    name: str
    modifier: str            # "alt" or "ctrl" (+ shift + `)
    system: bool             # post as WM_SYSKEY* (how Windows sends Alt combinations)


CONSOLE_CHORDS = [Chord("Alt+Shift+`", "alt", True), Chord("Alt+Shift+` (plain messages)", "alt", False),
                  Chord("Ctrl+Shift+`", "ctrl", False)]

# ---------------------------------------------------------------------------------------------- the game process


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", W.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


_k32.CreateToolhelp32Snapshot.restype = W.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = (W.DWORD, W.DWORD)
_k32.Process32FirstW.argtypes = (W.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
_k32.Process32NextW.argtypes = (W.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
_k32.CloseHandle.argtypes = (W.HANDLE,)
_INVALID = W.HANDLE(-1).value


def game_pid() -> int | None:
    """process id of the running game, or None (a Toolhelp snapshot of the process list)"""
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)            # TH32CS_SNAPPROCESS
    if not snap or snap == _INVALID:
        return None
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == GAME_EXE.lower():
                return int(e.th32ProcessID)
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
        return None
    finally:
        _k32.CloseHandle(snap)


_ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
_u32.EnumWindows.argtypes = (_ENUM, W.LPARAM)
_u32.GetWindowThreadProcessId.argtypes = (W.HWND, ctypes.POINTER(W.DWORD))
_u32.GetWindowThreadProcessId.restype = W.DWORD
_u32.IsWindowVisible.argtypes = (W.HWND,)
_u32.GetClientRect.argtypes = (W.HWND, ctypes.POINTER(W.RECT))
_u32.GetForegroundWindow.restype = W.HWND


def game_window(pid: int | None = None) -> int | None:
    """the game's main window: of the process's visible top-level windows, the one with the largest client area"""
    pid = pid if pid is not None else game_pid()
    if pid is None:
        return None
    best = [None, -1]

    def visit(hwnd, _):
        owner = W.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and _u32.IsWindowVisible(hwnd):
            r = W.RECT()
            if _u32.GetClientRect(hwnd, ctypes.byref(r)):
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > best[1]:
                    best[0], best[1] = hwnd, area
        return True
    _u32.EnumWindows(_ENUM(visit), 0)
    return best[0]


def in_front(hwnd: int) -> bool:
    return bool(hwnd) and _u32.GetForegroundWindow() == hwnd

# ---------------------------------------------------------------------------------------------- posted messages


WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0102, 0x0104, 0x0105
_u32.PostMessageW.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM)
_u32.PostMessageW.restype = W.BOOL


def _lp(scan: int, release: bool = False, alt_down: bool = False, ext: bool = False) -> int:
    """lParam of a key message: repeat 1, scan code, extended-key bit, context (Alt held) bit, previous-state +
    transition bits"""
    v = 1 | (scan & 0xFF) << 16
    if ext:
        v |= 1 << 24
    if alt_down:
        v |= 1 << 29
    if release:
        v |= 3 << 30
    return v


def _post(hwnd: int, msg: int, wp: int, lp: int) -> None:
    if not _u32.PostMessageW(hwnd, msg, wp, lp):
        raise OSError(ctypes.get_last_error(), "could not post to the game window (closed?)")


def post_text(hwnd: int, text: str) -> None:
    """type text as characters (no key presses); a short pause every 64 characters keeps the queue from flooding"""
    for i, ch in enumerate(text, 1):
        _post(hwnd, WM_CHAR, ord(ch), 1)
        if i % 64 == 0:
            time.sleep(0.05)


def post_key(hwnd: int, key: str, times: int = 1) -> None:
    k = KEYS[key]
    for _ in range(times):
        _post(hwnd, WM_KEYDOWN, k.vk, _lp(k.scan, ext=k.ext))
        if k.char:
            _post(hwnd, WM_CHAR, k.char, _lp(k.scan))
        _post(hwnd, WM_KEYUP, k.vk, _lp(k.scan, release=True, ext=k.ext))


_u32.AttachThreadInput.argtypes = (W.DWORD, W.DWORD, W.BOOL)
_u32.GetKeyboardState.argtypes = (ctypes.POINTER(ctypes.c_ubyte),)
_u32.SetKeyboardState.argtypes = (ctypes.POINTER(ctypes.c_ubyte),)
_k32.GetCurrentThreadId.restype = W.DWORD


def post_chord(hwnd: int, chord: Chord) -> None:
    """post <modifier>+Shift+` to the game in the background: for the duration, this thread shares the game thread's
    input state and marks the modifier and Shift as held there, then puts the old state back"""
    mod, shift, grave = KEYS[chord.modifier], KEYS["shift"], KEYS["grave"]
    alt = chord.modifier == "alt"
    down, up = (WM_SYSKEYDOWN, WM_SYSKEYUP) if chord.system else (WM_KEYDOWN, WM_KEYUP)
    theirs = _u32.GetWindowThreadProcessId(hwnd, None)
    mine = _k32.GetCurrentThreadId()
    joined = bool(_u32.AttachThreadInput(mine, theirs, True))
    before = (ctypes.c_ubyte * 256)()
    _u32.GetKeyboardState(before)
    held = (ctypes.c_ubyte * 256)(*before)
    for vk in (mod.vk, _LEFT[chord.modifier], shift.vk, _LEFT["shift"]):
        held[vk] |= 0x80
    try:
        _u32.SetKeyboardState(held)
        for k in (mod, shift, grave):
            _post(hwnd, down, k.vk, _lp(k.scan, alt_down=alt))
        time.sleep(0.15)
        for k in (grave, shift, mod):
            _post(hwnd, up, k.vk, _lp(k.scan, release=True, alt_down=alt and k is not mod))
        time.sleep(0.3)
    finally:
        _u32.SetKeyboardState(before)
        if joined:
            _u32.AttachThreadInput(mine, theirs, False)

# ---------------------------------------------------------------------------------------------- real key presses


class _KI(ctypes.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _ANY(ctypes.Union):
    _fields_ = [("ki", _KI), ("_room", ctypes.c_byte * 32)]      # INPUT's union is as large as MOUSEINPUT


class _INPUT(ctypes.Structure):
    _fields_ = [("type", W.DWORD), ("u", _ANY)]


_u32.SendInput.argtypes = (W.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
_u32.SendInput.restype = W.UINT
_SCAN, _UP, _EXT = 0x0008, 0x0002, 0x0001


def _scan(code: int, release: bool, ext: bool = False) -> None:
    e = _INPUT(type=1)                                  # INPUT_KEYBOARD
    e.u.ki = _KI(0, code, _SCAN | (_UP if release else 0) | (_EXT if ext else 0), 0, 0)
    if _u32.SendInput(1, ctypes.byref(e), ctypes.sizeof(e)) != 1:
        raise OSError(ctypes.get_last_error(), "SendInput refused the key")


def press_key(hwnd: int, key: str, hold: float = 0.06) -> bool:
    """one real key press, only if the game is in front; False (nothing sent) otherwise. A combination is written
    with + ("shift+tab"): the modifiers go down first and come up last. hold: s the key stays down (2026-11-07:
    the menus sometimes missed short presses)."""
    if not in_front(hwnd):
        return False
    parts = [KEYS[k] for k in key.split("+")]
    down = []
    try:
        for k in parts:
            _scan(k.scan, False, k.ext)
            down.append(k)
            time.sleep(0.03)
        time.sleep(max(0.0, hold - 0.03))
    finally:
        for k in reversed(down):
            _scan(k.scan, True, k.ext)
            time.sleep(0.02)
    return True


def press_chord(hwnd: int, chord: Chord) -> bool:
    """the chord as real key presses, only if the game is in front; if the game loses the front mid-chord, the keys
    already down are released and False is returned"""
    if not in_front(hwnd):
        return False
    codes = [KEYS[chord.modifier].scan, KEYS["shift"].scan, KEYS["grave"].scan]
    down = []
    try:
        for c in codes:
            if not in_front(hwnd):
                return False
            _scan(c, False)
            down.append(c)
            time.sleep(0.02)
        time.sleep(0.05)
        return True
    finally:
        for c in reversed(down):
            _scan(c, True)
            time.sleep(0.02)


_u32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_u32.GetAsyncKeyState.restype = ctypes.c_short


def held(key: str) -> bool:
    """is the key down right now (physical keyboard state; used to learn the menu keys the user presses)"""
    return bool(_u32.GetAsyncKeyState(KEYS[key].vk) & 0x8000)
