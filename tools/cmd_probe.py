"""Print a replay's command stream for a time window, to name undecoded command types from a test game (owner
2026-11-18: what are 0x92 / 0x94?). Camera (0x99) and heartbeat (0x9a) are left out unless --all.

    python tools/cmd_probe.py <replay> [--from 60] [--to 120] [--slot 1] [--all]
    python tools/cmd_probe.py <replay> --slot 1 --keys logs/input_....tsv [--offset 12.3] [--bindings <profile.rkp>]

Each line: game time, slot, type, sequence number (u32 @4), shift flag, receivers (u = squad, b = entity, p = player
only), data type and length. A 0x92 ... 0x94 run is indented. The summary at the end answers the test protocol:
pairs, orders per pair, squad orders outside a pair, and 0x92 / 0x94 that were not part of a 0x92-order-0x94 run.

--keys interleaves the presses recorded by tools/input_log.py during the test ("key" lines with the commands the
profile binds to that combo; x2 = double-tap). The offset (game time - recorder time) is found by matching right-clicks
to 0x92 pairs unless --offset is given; the match rate is printed so a wrong offset shows. --bindings defaults to the
newest .rkp in Documents/My Games/Age of Empires IV/keyBindingProfiles.

Test game (owner 2026-11-18): a custom game against an AI, as English (the civ of the reference replay). Replays of games
against the AI may not be saved: check the playback folder after a short first try. Run tools/input_log.py during it.
Launch the game normally, NOT with -dev: -dev replaces the key profile in the game with a debugging one (owner
2026-11-18), so the keys would no longer mean what --bindings says. The .rkp files on disk are not changed by it.

Part A, one step per game minute: do it in the first 20 s of minute k and then touch nothing, so
`--from 60*k --to 60*k+59` shows step k alone. Steps 1-6 give NO order: the expectation is no command at all besides
camera / heartbeat (selections and control groups stay on the player's PC). Any command there is a selection command.
  1  click-select one villager, then another; box-select four; double-click a villager (all on screen)
  2  control group set: select two villagers, Ctrl+1; select the scout, Ctrl+2; select the TC, Ctrl+3
  3  control group recall: 1, 2, 3, 1, 2 (single presses)
  4  control group add / remove: select a villager, Shift+1 (add), Ctrl+Shift+2 (add exclusively), Alt+1 (remove)
  5  double-tap 1 (select and centre the camera on the group), then double-tap 3
  6  unit type selection: Ctrl+click a villager (all villagers on screen), double-click a scout; the pick-all-of-type
     hotkeys (infantry / archers / cavalry / workers on screen)
  6b (minute 6 too, after 30 s) selection hotkeys: idle villagers, all military, next scout, all town centers, subselect
  7  one villager, one right-click on the ground                                        -> 0x92, 0x3e, 0x94
  8  recall group 1 (two villagers), one right-click on the ground                       -> one pair, 1 or 2 moves?
  9  one villager, three Shift+right-clicks                                              -> 3 pairs, shift flag S
 10  villagers + scout selected, one right-click on a sheep                              -> 1 pair, 2+ orders
 11  one unit: Stop hotkey, then Hold position hotkey                                    -> order first, then pair
 12  attack-move: A + click on the ground                                                -> 0x47 first, then pair
 13  TC + a villager selected together, one right-click on the ground                    -> rally + move: pair or not?
 14  TC only: set its rally point, queue one villager                                    -> 0xc, 0x3, no pair
 15  one villager, right-click on the minimap                                            -> pair?
 16  place a house with one villager, then one with three villagers                      -> 0x7b each, +4 bytes per builder

Part B, anything not seen in m260952857 or not named yet. Any order, at least 20 s apart (the key log shows when).
  - delete (Delete key): an unfinished foundation, a finished house, one villager         (0x38 = delete building?)
  - palisade wall -> build a gate on it; lock / unlock the gate                          (0x0e on a palisade = gate)
  - Town Center: ring the town bell, release it; garrison villagers, ungarrison all      (0x14: one of these?)
  - unload one unit from a building (0x4c is decoded but never seen)
  - cancel a queued villager, cancel a research                                          (0x5 data = queue slot?)
  - stances: aggressive / defensive / stand ground; formation change                     (seen as noise in the recorder)
  - repair a damaged building with a villager; build a farm on a mill
  - market: buy and sell once each
  - monk: heal, pick up a relic, put it into a monastery; trebuchet / springald pack and unpack
  - map ping / flare (Alt+click), a chat message, a taunt
  - production building auto-queue toggle, if the civ has one
  - last: resign                                                                         (0x8f = resign?)
Anything that breaks an expectation names what the command really is.
"""
import argparse
import collections
import glob
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analyzer"))
import replay as R  # noqa: E402

NAMES = {**R.ORDER_TYPES, 0x0e: "ability", 0x48: "ability", 0x72: "ability stop", 0x03: "queue", 0x05: "cancel",
         0x0c: "rally", 0x10: "research", 0x7b: "place building", 0x92: "<<< 0x92", 0x94: ">>> 0x94",
         0x99: "camera", 0x9a: "heartbeat"}
MODS = ("Control", "Shift", "Alt")
DOUBLE_S = 0.4      # a second press of the same combo within this = double-tap (repeatCount 1 in the profile)


def describe(c):
    try:
        rec, o = R.receivers(c)
        dt, d = R.data_of(c, o)
    except Exception:  # noqa: BLE001
        return "?", None, 0, []
    kinds = {k for k, _ in rec}
    who = "u" if 2 in kinds else "b" if 1 in kinds else "p"
    return who, dt, len(d), rec


def bindings(path):
    """{(combo, double-tap): [command, ...]} from a key binding profile (.rkp)"""
    out = collections.defaultdict(list)
    if not path or not os.path.exists(path):
        return out
    cmd = combo = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.search(r'(command|combo) = "([^"]*)"', line)
            if m:
                if m.group(1) == "command":
                    cmd = m.group(2)
                else:
                    combo = m.group(2)
                continue
            m = re.search(r"repeatCount = (-?\d+)", line)
            if m and combo:
                key = (combo, m.group(1) == "1")
                if cmd not in out[key]:
                    out[key].append(cmd)
                combo = None
    return out


def presses(path, binds):
    """[(recorder time, combo, bound commands)], one per key-down, with the modifiers held"""
    held, last, out = set(), {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            t, ev, k = line.rstrip("\n").split("\t")
            t = float(t)
            if ev == "up":
                held.discard(k)
                continue
            held.add(k)
            if k in MODS:
                continue
            combo = "+".join([m for m in MODS if m in held] + [k])
            dbl = combo in last and t - last[combo] <= DOUBLE_S
            last[combo] = t
            cmds = binds.get((combo, dbl)) or (binds.get((combo, False), []) if dbl else [])
            out.append((t, combo + (" x2" if dbl else ""), cmds))
    return out


def find_offset(keys, pair_times):
    """game time - recorder time: the most common gap between a right-click and a 0x92 pair, in 1/8 s bins"""
    clicks = [t for t, combo, _ in keys if combo.split(" ")[0].split("+")[-1] == "MouseRight"]
    gaps = collections.Counter(round((g - c) * 8) for c in clicks for g in pair_times)
    if not gaps:
        return None, 0, 0
    off = gaps.most_common(1)[0][0] / 8
    hit = sum(1 for c in clicks if any(abs(g - c - off) <= 0.25 for g in pair_times))
    return off, hit, len(clicks)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay")
    ap.add_argument("--from", dest="t0", type=float, default=0.0, help="start, game seconds")
    ap.add_argument("--to", dest="t1", type=float, default=1e9, help="end, game seconds")
    ap.add_argument("--slot", type=int, help="only this replay slot (needed with --keys: yours)")
    ap.add_argument("--all", action="store_true", help="also camera and heartbeat")
    ap.add_argument("--keys", help="a tools/input_log.py recording of the same game")
    ap.add_argument("--offset", type=float, help="game time - recorder time, seconds (default: found from right-clicks)")
    prof = sorted(glob.glob(os.path.join(os.path.expanduser("~"), "Documents", "My Games", "Age of Empires IV",
                                         "keyBindingProfiles", "*.rkp")), key=os.path.getmtime)
    ap.add_argument("--bindings", default=prof[-1] if prof else None, help="key binding profile (.rkp)")
    a = ap.parse_args()

    events = []     # (game time, order, command (slot, typ, c) or key text)
    for n, (tick, slot, typ, c) in enumerate(R.commands(a.replay)):
        if a.slot is None or slot == a.slot:
            events.append((tick / R.TICKS_PER_S, n, (slot, typ, c)))
    if a.keys:
        if a.slot is None:
            sys.exit("--keys needs --slot (your slot in the replay)")
        keys = presses(a.keys, bindings(a.bindings))
        if a.offset is not None:
            off, note = a.offset, "given"
        else:
            off, hit, nclick = find_offset(keys, [t for t, _, (_, typ, _) in events if typ == 0x92])
            if off is None:
                sys.exit("no right-clicks / 0x92 pairs to line up: give --offset")
            note = f"right-clicks matched to a 0x92 pair: {hit} of {nclick}"
        print(f"offset {off:+.3f} s ({note}); bindings {a.bindings}")
        for t, combo, cmds in keys:
            events.append((t + off, -1, f"key {combo:<22} " + ", ".join(cmds[:4]) + (" ..." if len(cmds) > 4 else "")))
    events.sort(key=lambda e: (e[0], e[1]))

    inside, pairs, stray, outside = {}, collections.Counter(), collections.Counter(), collections.Counter()
    for t, _, ev in events:
        if t < a.t0 or t > a.t1:
            continue
        stamp = f"{int(t // 60):2d}:{t % 60:05.2f}"
        if isinstance(ev, str):
            print(f"{stamp}     {ev}")
            continue
        slot, typ, c = ev
        if typ in (0x99, 0x9a) and not a.all:
            continue
        who, dt, dl, rec = describe(c)
        seq = struct.unpack_from("<I", c, 4)[0] if len(c) >= 8 else -1
        shift = "S" if c[3] & 0x80 else " "
        if typ == 0x92:
            if inside.get(slot) is not None:
                stray[(slot, "0x92 inside a run")] += 1
            inside[slot] = 0
        ind = "    " if inside.get(slot) is not None and typ not in (0x92, 0x94) else ""
        ids = ",".join(hex(i) for _, i in rec[:4]) + ("..." if len(rec) > 4 else "")
        print(f"{stamp} s{slot} {ind}0x{typ:02x} {NAMES.get(typ, ''):<16} seq {seq:<6} {shift} "
              f"{who}{len(rec)} [{ids}] data {dt} len {dl}")
        if typ == 0x94:
            if inside.get(slot) is None:
                stray[(slot, "0x94 without 0x92")] += 1
            else:
                pairs[(slot, inside[slot])] += 1
            inside[slot] = None
        elif typ != 0x92:
            if inside.get(slot) is not None:
                inside[slot] += 1
            elif who == "u":
                outside[(slot, hex(typ))] += 1

    print("\nsummary")
    for (slot, n), v in sorted(pairs.items()):
        print(f"  s{slot}: {v} pair(s) wrapping {n} command(s)")
    for (slot, ty), v in sorted(outside.items()):
        print(f"  s{slot}: {v} squad command(s) {ty} outside a pair")
    for (slot, what), v in sorted(stray.items()):
        print(f"  s{slot}: {v} x {what}")
    if not (pairs or outside or stray):
        print("  no 0x92 / 0x94 and no squad commands in this window")


if __name__ == "__main__":
    main()
