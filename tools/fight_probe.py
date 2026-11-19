"""Fight probe (owner 2026-11-10): before scripted test fights, check that the game's spawn / attack-move / formation
calls work from our console.

    python tools/fight_probe.py                          # 3 spearmen a side, 24 apart, watched 30 s
    python tools/fight_probe.py --bp unit_knight_2_fre --n 5 --gap 30 --secs 40
    python tools/fight_probe.py --hits                   # also print the game's hit events (A4D|FP|H)

Before: the game in dev mode in a skirmish (fogline-spawns: python launch.py --replay <file>, quit the replay, start a
skirmish: you + 1 AI on an open map such as Dry Arabia; the probe switches the AI off). The probe spawns the units
halfway between the two starting positions, orders both groups to attack-move at each other, prints the unit
positions / HP every tick (--every), and saves everything to logs/fight_probe.txt. Watch the middle of the map while it runs.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "ingame" / "fight_probe.lua"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bp", help="squad blueprint (default: try a spearman list)")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--gap", type=float, default=24)
    ap.add_argument("--secs", type=float, default=30)
    ap.add_argument("--every", type=float, default=0.125, help="sampling interval, s (0.125 = every sim tick)")
    ap.add_argument("--hits", action="store_true", help="also listen to the game's hit event (second run)")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "tools"))
    import gamelink as gl                       # Windows only
    if gl.game_pid() is None:
        sys.exit("the game isn't running (dev mode skirmish needed)")
    log = gl.LogTail(gl.WARNINGS)
    try:
        log.offset = gl.WARNINGS.stat().st_size
    except OSError:
        pass
    start = len(log.lines)
    pre = (f'A4D_FP_BP={chr(34) + a.bp + chr(34) if a.bp else "nil"} A4D_FP_N={a.n} A4D_FP_GAP={a.gap} '
           f'A4D_FP_SECS={a.secs} A4D_FP_HITS={"true" if a.hits else "false"} '
           f'A4D_FP_EVERY={a.every} ')
    con = gl.Console(log, gl.game_window())
    con.open_front(say=print)
    try:
        con.run(pre + f'local f,e=loadfile("{PROBE.as_posix()}") if not f then error(e) end f()', timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"console: {e}")
    con.close()
    print("probe running - watch the middle of the map")
    end = time.time() + a.secs + 60
    while time.time() < end and not any("A4D|FP|END" in l for l in log.lines[start:]):
        log.poll()
        time.sleep(0.3)
    block = [l[l.find("A4D|FP|"):] for l in log.lines[start:] if "A4D|FP|" in l]
    out = ROOT / "logs" / "fight_probe.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(block) + "\n", encoding="utf-8")
    for l in block:
        if not l.startswith("A4D|FP|S|"):
            print(" ", l[:200])
    print(f"{sum(1 for l in block if l.startswith('A4D|FP|S|'))} samples -> {out}  (send this file)")


if __name__ == "__main__":
    main()
