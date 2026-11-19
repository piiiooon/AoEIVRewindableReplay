"""Talking to a running Age of Empires IV (Windows only; Fogline's own code, 2026-11-06): where its files are, reading
warnings.log as it grows, running Lua in the SCAR console, finding the game through Steam, putting a replay where
the game plays it from.

Used by tools/record.py (replays), fogline-spawns spawns.py, bo-maker calib.py / record.py (dev skirmishes).

Console commands: the code goes into a small file (CMD_FILE); the console only gets one short line that loads it
(long typed lines were cut off in the console: game3, "unfinished long string"). The file reports back in
warnings.log: A4D|ACK|<n> when the code ran, A4D|NAK|<n>|<error> when it failed - printed in the console's Lua state
and again through Scar_DoString, in case only one of them reaches the log.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if sys.platform != "win32":
    raise ImportError("gamelink drives the Windows game client")

import winreg  # noqa: E402

import gameinput as gi  # noqa: E402

APP_ID = "1466860"
GONE_FOR = 15            # s the game process must be missing before it counts as closed (short gaps happen)


def _shell_folder(name: str, fallback: Path) -> Path:
    """a user shell folder from the registry (follows OneDrive / moved / localized folders)"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            return Path(os.path.expandvars(winreg.QueryValueEx(k, name)[0]))
    except OSError:
        return fallback


DOCUMENTS = _shell_folder("Personal", Path.home() / "Documents")
GAME_USER_DIR = DOCUMENTS / "My Games" / "Age of Empires IV"
PLAYBACK = GAME_USER_DIR / "playback"
WARNINGS = GAME_USER_DIR / "warnings.log"
TEMP = Path(os.environ.get("TEMP") or Path.home())
CMD_FILE = TEMP / "fogline_cmd.lua"          # no spaces in TEMP's usual path: the typed line stays short

game_pid = gi.game_pid
game_window = gi.game_window

# ---------------------------------------------------------------------------------------------- warnings.log


class LogTail:
    """warnings.log as it grows: poll() returns the complete new lines (and keeps them all in .lines); .offset is the
    byte position read so far (set it to the file size to skip what is already there)."""

    def __init__(self, path: Path = WARNINGS, from_end: bool = False):
        self.path, self.lines, self.offset = Path(path), [], 0
        if from_end:
            self.skip_existing()

    def skip_existing(self) -> None:
        try:
            self.offset = self.path.stat().st_size
        except OSError:
            self.offset = 0

    def poll(self) -> list[str]:
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:                 # the game recreated the log (a new launch): start over
            self.offset = 0
        if size == self.offset:
            return []
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read(size - self.offset)
        end = chunk.rfind(b"\n")
        if end < 0:                            # a line still being written
            return []
        self.offset += end + 1
        new = chunk[:end].decode("utf-8", errors="replace").split("\n")
        new = [x.rstrip("\r") for x in new]
        self.lines.extend(new)
        return new

    def wait_for(self, pattern: str, timeout: float, every: float = 0.2) -> str | None:
        """the first new line matching pattern within timeout s, else None"""
        rx = re.compile(pattern)
        until = time.time() + timeout
        while True:
            for line in self.poll():
                if rx.search(line):
                    return line
            if time.time() >= until:
                return None
            time.sleep(every)

# ---------------------------------------------------------------------------------------------- the SCAR console


class ConsoleError(RuntimeError):
    """the game ran the command and reported an error"""


class Console:
    def __init__(self, log: LogTail, hwnd: int):
        self.log, self.hwnd, self.count, self.chord = log, hwnd, 0, None

    def _write_command(self, n: int, code: str) -> None:
        CMD_FILE.write_text(
            "local A4D_ok, A4D_err = pcall(function()\n" + code + "\nend)\n"
            f"local A4D_msg = 'A4D|' .. (A4D_ok and 'ACK|{n}' or ('NAK|{n}|' .. tostring(A4D_err)))\n"
            "print(A4D_msg)\n"
            "if Scar_DoString then pcall(Scar_DoString, 'print(' .. string.format('%q', A4D_msg) .. ')') end\n",
            encoding="utf-8")

    def run(self, code: str, timeout: float = 6.0, retries: int = 2) -> None:
        """run Lua code in the console; ConsoleError if the game reports an error, TimeoutError if no answer"""
        self.count += 1
        n = self.count
        self._write_command(n, code)
        # the console's own environment (_ENV) has functions the plain global table lacks; the NAK text is split
        # so the typed line (echoed into the log) can't match the reply pattern itself
        line = (f'local c,e=loadfile("{CMD_FILE.as_posix()}","t",_ENV) '
                f'if c then c() else print("A4D|".."NAK|{n}|"..tostring(e)) end')
        reply = re.compile(rf"A4D\|(ACK|NAK)\|{n}(\||$)")
        for _ in range(max(1, retries)):
            gi.post_key(self.hwnd, "backspace", 250)        # whatever is left on the input line
            gi.post_text(self.hwnd, line)
            gi.post_key(self.hwnd, "enter")
            hit = self.log.wait_for(reply.pattern, timeout)
            if hit:
                if "|NAK|" in hit:
                    raise ConsoleError(hit.split(f"NAK|{n}|", 1)[-1])
                return
        raise TimeoutError(f"the console did not answer command {n}")

    def ping(self, timeout: float = 2.5) -> bool:
        try:
            self.run("", timeout=timeout, retries=1)
            return True
        except TimeoutError:
            return False

    def open(self, say=print, front_wait: float = 600) -> gi.Chord:
        """open the console: first by posting each chord in the background; if the game ignores those, by pressing
        it for real once the user clicks into the game (up to front_wait s)"""
        for chord in gi.CONSOLE_CHORDS:
            gi.post_chord(self.hwnd, chord)
            if self.ping():
                self.chord = chord
                say(f"  console open ({chord.name})")
                return chord
        say("  The game ignores background console hotkeys. Click into the game window once;\n"
            "  the console opens by itself and you can switch away again.")
        return self.open_front(say=say, limit=front_wait, quiet=True)

    def open_front(self, say=print, limit: float | None = None, quiet: bool = False) -> gi.Chord:
        """open the console with real key presses, only while the game is in front (waits for the user to click into
        it; never brings it forward). A chord that took effect is kept for close(). limit: s, None = no limit."""
        until = None if limit is None else time.time() + limit
        asked = quiet
        while until is None or time.time() < until:
            if not gi.in_front(self.hwnd):
                if not asked:
                    say("  waiting for the game window to be in front (click into the game)...")
                    asked = True
                time.sleep(0.5)
                continue
            for chord in gi.CONSOLE_CHORDS:
                if gi.press_chord(self.hwnd, chord):
                    time.sleep(1.5)                  # a toggle that lands mid-typing would split the line
                    if self.ping():
                        self.chord = chord
                        say(f"  console open ({chord.name})")
                        return chord
                    time.sleep(1.0)
            say("  the console did not answer; trying again (keep the game in front)")
            time.sleep(2.0)
        raise TimeoutError("could not open the SCAR console")

    def close(self) -> bool:
        """toggle the console shut with the chord that opened it; only possible while the game is in front"""
        return bool(self.chord) and gi.press_chord(self.hwnd, self.chord)


def scar(call: str) -> str:
    """a call for the SCAR state: run directly if the console sees the function, else through Scar_DoString"""
    fn = call.split("(", 1)[0]
    return f'if {fn} then {call} else Scar_DoString("{call}") end'

# ---------------------------------------------------------------------------------------------- Steam, the game


def steam_exe() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamExe")[0])
    except OSError:
        return None


def game_exe() -> Path | None:
    """RelicCardinal.exe in whichever Steam library holds the game (libraryfolders.vdf, appmanifest installdir)"""
    steam = steam_exe()
    if steam is None:
        return None
    root = steam.parent
    libraries = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        libraries += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s*"([^"]+)"', text)]
    for lib in libraries:
        manifest = lib / "steamapps" / f"appmanifest_{APP_ID}.acf"
        if not manifest.exists():
            continue
        m = re.search(r'"installdir"\s*"([^"]+)"', manifest.read_text(encoding="utf-8", errors="replace"))
        if m:
            exe = lib / "steamapps" / "common" / m.group(1) / gi.GAME_EXE
            if exe.exists():
                return exe
    return None


def game_build(exe: Path) -> int | None:
    """the build number of the installed game (the third part of the exe's file version)"""
    q = f"(Get-Item -LiteralPath '{exe}').VersionInfo.FileBuildPart"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", q], capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None


def launch(replay_name: str | None = None) -> None:
    """start the game through Steam in dev mode, optionally straight into a replay in the playback folder"""
    steam = steam_exe()
    if steam is None:
        raise RuntimeError("Steam not found in the registry")
    args = [str(steam), "-applaunch", APP_ID, "-dev"]
    if replay_name:
        args += ["-replay", f"playback:{replay_name}"]
    subprocess.Popen(args)


def close_game(wait: float = 60) -> None:
    subprocess.run(["taskkill", "/F", "/IM", gi.GAME_EXE], capture_output=True)
    until = time.time() + wait
    while game_pid() is not None and time.time() < until:
        time.sleep(1)


def stage_replay(src: Path) -> Path:
    """put a replay where the game plays it from: gzip downloads (aoe4world, aoe4replays.gg) unpacked into the
    playback folder, other files copied there unless already in it. Returns the file in the playback folder."""
    PLAYBACK.mkdir(parents=True, exist_ok=True)
    name = src.name[:-3] if src.name.lower().endswith(".gz") else src.name
    dest = PLAYBACK / name
    with open(src, "rb") as fh:
        packed = fh.read(2) == b"\x1f\x8b"
    if packed:
        import gzip
        with gzip.open(src, "rb") as fh:
            data = fh.read()                 # whole file first: src and dest may be the same path
        dest.write_bytes(data)
    elif src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    return dest
