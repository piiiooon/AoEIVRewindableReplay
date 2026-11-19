"""Check a recorded game for building buffs and Tughlaq governors (owner 2026-11-12: "how should I test ...").

    python tools/buff_check.py NAME [--replay path/to/replay]

Reads work/NAME.timeline.json (and work/NAME.fights.json for the 3D unit table). Prints:
  1. governors: every upgrade event whose name has "govern" (the attrib names the HUD's city tags need), plus Tughlaq
     upgrades (_tug) that data/upgrades.json does not know - those are the candidates if "govern" finds nothing;
  2. ability events from the recorder (dump v12+): how many, and those aimed at a building;
  3. ability commands in the replay file aimed at a building (needs the replay: --replay, or found next to the log);
  4. the building buff rings the 3D page would draw (build_3d.buff_spans on buildings);
  5. dump v18 state models: every key that was ever non-zero, on how many entities / which blueprints, and the
     player keys (tl["esm"] / tl["psm"]); the probe's key counts per blueprint (tl["smk"]).
Nothing is written.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analyzer"))
sys.path.insert(0, os.path.join(ROOT, "viewer"))


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--replay")
    a = ap.parse_args()
    tl = json.load(open(os.path.join(ROOT, "work", f"{a.name}.timeline.json"), encoding="utf-8"))
    bp_of, owner = {}, {}
    for fr in tl.get("frames") or []:
        for e in fr["entities"]:
            if e.get("id") is not None:
                bp_of.setdefault(e["id"], e.get("bp") or "")
                owner.setdefault(e["id"], e.get("owner"))
    is_b = lambda i: str(bp_of.get(i, "")).lower().startswith("building")

    print("== 1. governors (upgrade events) ==")
    try:
        ups = json.load(open(os.path.join(ROOT, "data", "upgrades.json"), encoding="utf-8"))["upgrades"]
    except (OSError, ValueError, KeyError):
        ups = {}
    from gamedata import canon_attrib
    ev = [e for e in tl.get("events") or [] if e.get("type") == "upgrade"]
    gov = [e for e in ev if "govern" in str(e.get("upgrade", "")).lower()]
    for e in gov:
        print(f"  {mmss(e['t'])}  {e['upgrade'][1:]}  executer {e.get('executer')}")
    if not gov:
        print("  none named *govern*")
    unk = sorted({e["upgrade"][1:] for e in ev if "_tug" in str(e.get("upgrade", "")).lower()
                  and not canon_attrib(e["upgrade"][1:], ups)})
    if unk:
        print("  Tughlaq upgrades not in upgrades.json (governor candidates):")
        for u in unk:
            print("   ", u, "at", ", ".join(mmss(e["t"]) for e in ev if e["upgrade"][1:] == u))
    print(f"  ({len(ev)} upgrade events in all)")

    print("\n== 2. recorder ability events (dump v12+) ==")
    ab = tl.get("abilities") or []
    print(f"  {len(ab)} events; events seen: {', '.join(sorted({str(r[1]) for r in ab})) or '-'}")
    if not ab:
        print("  none: the log is older than dump v12, or the game fired no ability events")
    hit = [r for r in ab if len(r) > 4 and str(r[4]).isdigit() and is_b(int(r[4]))]
    for r in hit[:40]:
        print(f"  {mmss(r[0])}  {r[1]}  {r[3]}  caster {r[2]} -> {bp_of.get(int(r[4]))} ({r[4]})")
    print(f"  aimed at a building: {len(hit)}")
    if ab and not hit:
        tg = sorted({str(r[4])[:12] for r in ab if len(r) > 4})[:10]
        print(f"  target field values seen: {', '.join(tg) or 'none'} (empty = the event carries no target)")

    print("\n== 3. replay ability commands aimed at a building ==")
    rp = a.replay
    if not rp:
        for d in ("logs", "replays", "playback"):
            for ext in ("", ".rec"):
                c = os.path.join(ROOT, d, a.name + ext)
                if os.path.isfile(c):
                    rp = c
    if not rp or not os.path.isfile(rp):
        print("  no replay (pass --replay)")
        casts = []
    else:
        from replay import abilities
        casts = abilities(rp)
        names = {}
        try:
            names = json.load(open(os.path.join(ROOT, "data", "abilities.json"), encoding="utf-8"))["abilities"]
        except (OSError, ValueError, KeyError):
            pass
        try:
            names.update(json.load(open(os.path.join(ROOT, "models", "ability_info.json"), encoding="utf-8")))
        except (OSError, ValueError):
            pass
        n = 0
        for c in casts:
            tg = c.get("target")
            if tg and tg[0] == "entity" and is_b(tg[1]):
                n += 1
                nm = (names.get(str(c["pbg"])) or {}).get("name") or (names.get(str(c["pbg"])) or {}).get("attrib") or "?"
                if n <= 40:
                    print(f"  {mmss(c['t'])}  pbg {c['pbg']} {nm} -> {bp_of.get(tg[1])} ({tg[1]})")
        sq = sum(1 for c in casts if c.get("target") and c["target"][0] == "squad")
        print(f"  {len(casts)} ability commands; at a building entity: {n}; at a squad: {sq}")

    print("\n== 5. state models (dump v18) ==")
    esm, psm = tl.get("esm") or {}, tl.get("psm") or {}
    keys = {}
    for i, rows in esm.items():
        for _, d in rows:
            for k, v in d.items():
                if v:
                    keys.setdefault(k, {}).setdefault(i, bp_of.get(int(i), "?"))
    for k in sorted(keys, key=lambda k: -len(keys[k])):
        bps = sorted({str(b) for b in keys[k].values()})
        print(f"  {k}: {len(keys[k])} entities  ({', '.join(bps[:4])}{' ...' if len(bps) > 4 else ''})")
    if not keys:
        print("  no entity keys (the log is older than v18, or nothing was ever non-zero)")
    for p, rows in sorted(psm.items()):
        seen = sorted({k for _, d in rows for k, v in d.items() if v})
        print(f"  player {p}: {len(rows)} changes; keys {', '.join(seen[:30])}{' ...' if len(seen) > 30 else ''}")
    smk = tl.get("smk") or {}
    if smk:
        top = sorted(smk.items(), key=lambda kv: -int(kv[1]) if str(kv[1]).isdigit() else 0)[:8]
        print("  probe keys per blueprint (most):", ", ".join(f"{b}={n}" for b, n in top))

    print("\n== 4. building buff rings the 3D page would draw ==")
    fp = os.path.join(ROOT, "work", f"{a.name}.fights.json")
    if not os.path.exists(fp):
        print("  no fights.json (run run.py first)")
        return
    F = json.load(open(fp, encoding="utf-8"))
    ui_of = {u[0]: i for i, u in enumerate(F["units"])}
    import build_3d
    spans, bnames = build_3d.buff_spans(tl, rp if rp and os.path.isfile(rp) else None, ui_of)
    bspans = [s for s in spans or [] if str(F["bps"][F["units"][s[0]][2]]).lower().startswith("building")]
    for s in bspans[:40]:
        print(f"  {mmss(s[1])}-{mmss(s[2])}  {bnames[s[3]]} ({s[4]}) on {F['bps'][F['units'][s[0]][2]]}")
    print(f"  {len(bspans)} building spans of {len(spans or [])}")


if __name__ == "__main__":
    main()
