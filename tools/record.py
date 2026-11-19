"""Record a replay with ingame/dump.lua and analyse it (Windows only; Fogline's own code, 2026-11-06).

    python tools/record.py                         # newest readable replay in the game's playback folder
    python tools/record.py path/to/replay --name my_game
    python tools/record.py replay --speed 32 --keep-open --no-run

1. The replay: checked (readable, made on the installed game build - other builds don't play), then put in the
   game's playback folder (gzip downloads unpacked, other files copied).
2. The game: refused if already running; launched through Steam in dev mode straight into the replay.
3. When warnings.log shows the match, the SCAR console is opened (tools/gamelink.py: in the background if the game
   takes it, else once you click into the game) and the dump is started with one console line. The console stops
   taking input once the dump runs, so a temporary copy of dump.lua carries the sim rate (--speed) and the replay's
   end: it speeds up after loading and stops itself at the end.
4. Progress follows the dump's A4D|P lines until the end (or no progress for 90 s).
5. The game is closed (unless --keep-open), warnings.log saved as logs/<name>.recorded.log ("Log saved: ..."), and
   run.py run on it with the replay (cameras, orders) unless --no-run.

Exit codes (fogline-profile batch.py): 0 done; 3 the game closed mid-run (crash); 4 incomplete recording (playback
stopped advancing). On any failure warnings.log is kept as logs/<name>.failed.log.
What reaches the game: key messages to its window (console chord, the console lines, Enter, Backspace).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "analyzer"))
if sys.platform != "win32":
    sys.exit("tools/record.py drives the Windows game client; run it on Windows")

import gamelink as gl  # noqa: E402
from replay import info as replay_info  # noqa: E402

DUMP = ROOT / "ingame" / "dump.lua"
LOGS = ROOT / "logs"
LOAD_LIMIT = 900         # s from launch to the match (long replays on slow disks load for minutes)
STALL_LIMIT = 90         # s without dump progress before stopping early
DUMP_HOOK = "A4D_AUTO_SPEED = nil\nA4D_AUTO_END = nil\n"     # the line pair dump.lua offers for the settings


class GameClosed(RuntimeError):
    """the game process went away mid-run"""


def mmss(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def readable(path: Path) -> dict | None:
    """the replay's header info, or None for an empty or unreadable file (the game leaves 0-byte files around)"""
    try:
        if path.stat().st_size < 64:
            return None
        return replay_info(path)
    except Exception:          # noqa: BLE001 - whatever fails to parse is not a replay
        return None


def pick_replay(arg: Path | None) -> tuple[Path, dict]:
    if arg is None:
        files = sorted((p for p in gl.PLAYBACK.glob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            meta = readable(p)
            if meta:
                return p, meta
            print(f"  skipping {p.name} ({p.stat().st_size} bytes, not a readable replay)")
        sys.exit(f"no readable replay in {gl.PLAYBACK}")
    path = arg if arg.exists() else gl.PLAYBACK / arg.name
    if not path.exists():
        sys.exit(f"replay not found: {arg}")
    meta = readable(path)
    if meta is None:
        sys.exit(f"{path} is empty or not a replay ({path.stat().st_size} bytes)")
    return path, meta


class Watch:
    """the game process: closed = missing for longer than gl.GONE_FOR s (after it was seen at least once)"""

    def __init__(self):
        self.seen, self.missing_since = False, None

    def check(self, what: str) -> None:
        if gl.game_pid() is not None:
            self.seen, self.missing_since = True, None
            return
        self.missing_since = self.missing_since or time.time()
        if self.seen and time.time() - self.missing_since > gl.GONE_FOR:
            raise GameClosed(what)


def wait_for_match(log: gl.LogTail, launched: float, watch: Watch) -> None:
    until = time.time() + 180                   # the game writes a fresh warnings.log at launch
    while time.time() < until:
        try:
            if gl.WARNINGS.stat().st_mtime >= launched - 1:
                break
        except OSError:
            pass
        time.sleep(1)
    until = time.time() + LOAD_LIMIT
    while not log.wait_for(r"Starting mission|ClassicStart_PostInit", timeout=3):
        watch.check("the game closed while loading the replay")
        if time.time() > until:
            sys.exit(f"the replay never reached the match in {LOAD_LIMIT // 60} min (see warnings.log)")


def start_dump(con: gl.Console, log: gl.LogTail, speed: float, end: float, light: bool = True,
               unit_sm: bool = True, full_read: bool = False) -> None:
    try:                                        # half speed while the dump loads, so it starts near 0:00
        con.run(gl.scar("Game_SetSimRate(4)"))
    except gl.ConsoleError as e:
        print(f"  could not slow the game while loading: {e}")
    text = DUMP.read_text(encoding="utf-8")
    if DUMP_HOOK not in text:
        sys.exit("ingame/dump.lua has no A4D_AUTO_SPEED / A4D_AUTO_END lines; update it with this record.py")
    run_copy = gl.TEMP / "fogline_dump_run.lua"
    hook = f"A4D_AUTO_SPEED = {speed:g}\nA4D_AUTO_END = {end:.1f}\n" + ("A4D_LIGHT_VIEW = true\n" if light else "") + \
        ("" if unit_sm else "A4D_SM_UNITS = false\n") + ("A4D_STATIC_EVERY = 1\n" if full_read else "")
    run_copy.write_text(text.replace(DUMP_HOOK, hook, 1),
                        encoding="utf-8")
    # dofile where the console has it, else loadfile + call
    con.run("local load_and_run = dofile or (loadfile and function(p) local c, e = loadfile(p) "
            "if not c then error(e) end return c() end) "
            "if not load_and_run then error('no dofile or loadfile in the console') end "
            f'load_and_run("{run_copy.as_posix()}")', timeout=20)
    if not (log.wait_for(r"A4D\|SPEED", timeout=30) or any("A4D|SPEED" in x for x in log.lines)):
        print(f"  speed-up not seen; to speed up by hand: console, A4D_Speed({speed:g})")


def follow(log: gl.LogTail, duration: float, watch: Watch) -> tuple[bool, float]:
    """(reached the end, last game time seen)"""
    t, moved = 0.0, time.time()
    progress = re.compile(r"A4D\|P\|([\d.]+)\|")
    perf = re.compile(r"A4D\|PERF\|([\d.]+)\|(\d+)")
    pf = []                                     # (wall time, game time, rendered frames) per A4D|PERF line
    while True:
        for line in log.poll():
            m = progress.search(line)
            if m and float(m.group(1)) > t:
                t, moved = float(m.group(1)), time.time()
            m2 = perf.search(line)
            if m2:
                pf.append((time.time(), float(m2.group(1)), int(m2.group(2))))
        if t >= duration - 2.5:
            return True, t
        if any("A4D|STOP" in x for x in log.lines[-50:]):
            return False, t
        watch.check(f"the game closed during playback at {mmss(t)} of {mmss(duration)}")
        if time.time() - moved > STALL_LIMIT:
            print("\n  playback stopped advancing; stopping early")
            return False, t
        rate = ""
        if len(pf) >= 2:                        # over the last ~minute of game time: speed and frames per second
            a, b = pf[max(0, len(pf) - 7)], pf[-1]
            if b[0] > a[0] and b[1] > a[1]:
                rate = f" {(b[1] - a[1]) / (b[0] - a[0]):.1f}x real time, {(b[2] - a[2]) / (b[0] - a[0]):.0f} fps"
        print(f"\r  {mmss(t)} / {mmss(duration)}{rate}   ", end="", flush=True)
        time.sleep(2)


def keep_failed_log(log: gl.LogTail, name: str) -> None:
    log.poll()
    shown = [x for x in log.lines if "A4D|" in x and "A4D|API|" not in x and "A4D|HM|" not in x][-15:]
    print("\nLast dump / console lines in warnings.log:")
    for x in shown:
        print("  " + x[x.find("A4D|"):][:160])
    if gl.WARNINGS.exists():
        LOGS.mkdir(exist_ok=True)
        shutil.copyfile(gl.WARNINGS, LOGS / f"{name}.failed.log")
        print(f"warnings.log copied to logs/{name}.failed.log")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay", nargs="?", type=Path, help="replay file (default: newest in the playback folder)")
    ap.add_argument("--name", help="name for logs/ and views/ (default: the replay's file name)")
    ap.add_argument("--speed", type=float, default=64, help="sim rate (8 = 1x; 64 = 8x, the default)")
    ap.add_argument("--keep-open", action="store_true", help="leave the game running afterwards")
    ap.add_argument("--no-unit-sm", action="store_true",
                    help="dump v18: skip unit state models (buffs, charges, veterancy); buildings and players stay")
    ap.add_argument("--full-read", action="store_true",
                    help="re-read blueprint / kind / squad id / building position every second (default since 2026-11-15: "
                         "cached, re-read after upgrades, packing, construction and every 30 s; decision 0007)")
    ap.add_argument("--full-view",action="store_true",
                    help="leave the game's view alone (default: sound off, camera parked over a map corner, looking down - cheaper frames)")
    ap.add_argument("--no-run", action="store_true", help="only record; don't run the analysis")
    ap.add_argument("--icons", action="store_true", help="pass --icons to run.py")
    ap.add_argument("--player", help="pass --player to run.py (basics page from that side)")
    ap.add_argument("--detail", help="pass --detail to run.py (3d page: light / medium / heavy)")
    ap.add_argument("--out", help="pass --out to run.py: pages to write, e.g. viewer,fights,3d (default viewer,fights)")
    a = ap.parse_args()

    src, meta = pick_replay(a.replay)
    duration = meta["duration"]
    print(f"Replay {src.name}: build {meta['build']}, {mmss(duration)}")
    exe = gl.game_exe()
    if exe is None:
        sys.exit("Age of Empires IV not found through Steam")
    build = gl.game_build(exe)
    if build is not None and build != meta["build"]:
        sys.exit(f"replay is from build {meta['build']}, installed game is build {build}: it will not play")
    if gl.game_pid() is not None:
        sys.exit("Age of Empires IV is already running; close it first")
    staged = gl.stage_replay(src)
    if staged != src:
        print(f"  {src.name} -> playback/{staged.name}")
    name = a.name or Path(staged.name).stem

    launched = time.time()
    gl.launch(staged.name)
    print("Launching the game (it pops up once; you can switch away)...")
    log, watch, finished, last = gl.LogTail(gl.WARNINGS), Watch(), False, 0.0
    try:
        wait_for_match(log, launched, watch)
        time.sleep(2)
        hwnd = gl.game_window()
        if hwnd is None:
            sys.exit("game window not found")
        con = gl.Console(log, hwnd)
        con.open()
        start_dump(con, log, a.speed, duration - 1, light=not a.full_view, unit_sm=not a.no_unit_sm,
                   full_read=a.full_read)
        print(f"Recording at sim rate {a.speed:g} ({a.speed / 8:g}x); the dump stops itself at {mmss(duration - 1)}...")
        finished, last = follow(log, duration, watch)
        print()
        if not (log.wait_for(r"A4D\|STOP", timeout=20) or any("A4D|STOP" in x for x in log.lines)):
            print(f"  no A4D|STOP line; the log is complete up to {mmss(last)}")
    except BaseException:
        keep_failed_log(log, name)
        raise
    finally:
        if not a.keep_open:
            gl.close_game()
    LOGS.mkdir(exist_ok=True)
    saved = LOGS / f"{name}.recorded.log"
    shutil.copyfile(gl.WARNINGS, saved)
    print(f"Log saved: {saved}" + ("" if finished else " (incomplete)"))
    if not a.no_run:
        cmd = [sys.executable, str(ROOT / "run.py"), str(saved), "--name", name, "--replay", str(staged)]
        if a.icons:
            cmd.append("--icons")
        if a.player:
            cmd += ["--player", a.player]
        if a.out:
            cmd += ["--out", a.out]
        if a.detail:
            cmd += ["--detail", a.detail]
        subprocess.run(cmd, check=True)
    if not finished:
        sys.exit(4)


if __name__ == "__main__":
    try:
        main()
    except GameClosed as e:
        print(f"\n{e}")
        sys.exit(3)
