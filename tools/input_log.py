"""Record your own key and mouse-button presses during a test game, to line them up with the replay's commands
(owner 2026-11-18: which keys led to which command, e.g. control groups vs 0x92 / 0x94). Windows only, standard library.

    python tools/input_log.py                  # -> logs/input_<date>_<time>.tsv, stop with Ctrl+C in this window
    python tools/cmd_probe.py <replay> --keys logs/input_....tsv [--offset 12.3] [--bindings <profile.rkp>]

Only presses made while the Age of Empires IV window is in front are written (nothing typed elsewhere), and nothing
leaves this PC. Rows: seconds since start, down / up, key name (the .rkp spelling). The mouse wheel and the mouse
position are not recorded. Polls every 5 ms, so a
tap shorter than that can be missed. The replay knows game time only: cmd_probe matches the right-clicks to the unit
orders to find the offset (or take --offset); game speed must be 1x and the game never paused.
"""
import ctypes
import os
import sys
import time
from datetime import datetime

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TITLE = "Age of Empires IV"
POLL_S = 0.005

# key names as the game's key binding profiles (.rkp) write them, so cmd_probe can look the binding up
NAMES = {1: "MouseLeft", 2: "MouseRight", 4: "MouseMiddle", 5: "MouseX1", 6: "MouseX2", 8: "Backspace", 9: "Tab",
         13: "Enter", 16: "Shift", 17: "Control", 18: "Alt", 19: "Pause", 20: "CapsLock", 27: "Escape", 32: "Space",
         33: "PageUp", 34: "PageDown", 35: "End", 36: "Home", 37: "Left", 38: "Up", 39: "Right", 40: "Down", 45: "Insert",
         46: "Delete", 91: "Win", 186: "Semicolon", 187: "Equal", 188: "Comma", 189: "Minus", 190: "Period", 191: "Slash",
         192: "Grave", 219: "LBracket", 220: "Backslash", 221: "RBracket", 222: "Apostrophe"}
NAMES.update({c: chr(c) for c in range(0x30, 0x3A)})
NAMES.update({c: chr(c) for c in range(0x41, 0x5B)})
NAMES.update({0x60 + i: f"Numpad{i}" for i in range(10)})
NAMES.update({0x70 + i: f"F{i + 1}" for i in range(12)})
# the left / right variants (160-165) duplicate Shift / Ctrl / Alt; skipped
SKIP = set(range(160, 166))


def main():
    if os.name != "nt":
        sys.exit("Windows only")
    u32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(256)

    def in_game():
        u32.GetWindowTextW(u32.GetForegroundWindow(), buf, 256)
        return TITLE in buf.value

    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    path = os.path.join(os.path.normpath(ROOT), "logs", f"input_{datetime.now():%Y%m%d_%H%M%S}.tsv")
    keys = [k for k in range(1, 255) if k not in SKIP]
    down = set()
    t0 = time.perf_counter()
    n = 0
    print(f"recording to {path}\nonly while '{TITLE}' is in front; Ctrl+C here to stop", flush=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# started {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.flush()
        try:
            while True:
                ok = in_game()
                for k in keys:
                    on = ok and bool(u32.GetAsyncKeyState(k) & 0x8000)
                    if on != (k in down):
                        (down.add if on else down.discard)(k)
                        fh.write(f"{time.perf_counter() - t0:.3f}\t{'down' if on else 'up'}\t{NAMES.get(k, f'VK{k}')}\n")
                        fh.flush()      # closing the window instead of Ctrl+C keeps what was written
                        n += 1
                time.sleep(POLL_S)
        except KeyboardInterrupt:
            pass
    print(f"{n} events -> {path}")


if __name__ == "__main__":
    main()
