"""Upgrades / buffs with no game-data entry or icon (owner 2026-11-12: "some landmarks seem to give buffs ... that do not have
an assigned icon ... list them and I can manually input their appropriate descriptions").

    python tools/tech_notes.py            # scan work/*.hud.json, add new ones to data/tech_notes.json, print the list
    python tools/tech_notes.py --list     # print only (nothing written)

data/tech_notes.json is yours to edit: {attrib: {"name": "...", "short": "...", "desc": "...", "from": "..."}}
  name   shown name (default: the attrib made readable)
  short  the tile label, up to ~10 letters (default: the start of the name)
  desc   what it does, one or more lines (\\n) - shown on hover
  from   what grants it (landmark, civ bonus, ...) - shown on hover
Empty fields fall back to the defaults. Existing entries are never overwritten. Re-run run.py for a game to use the notes.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analyzer"))
NOTES = os.path.join(ROOT, "data", "tech_notes.json")


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print only, do not add to data/tech_notes.json")
    a = ap.parse_args()
    from gamedata import canon_attrib
    ups = json.load(open(os.path.join(ROOT, "data", "upgrades.json"), encoding="utf-8"))["upgrades"]
    try:
        notes = json.load(open(NOTES, encoding="utf-8"))
    except (OSError, ValueError):
        notes = {}
    found = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "work", "*.hud.json"))):
        game = os.path.basename(f).split(".")[0]
        H = json.load(open(f, encoding="utf-8"))
        civ = {str(p.get("idx")): p.get("civ") for p in H.get("players") or [] if isinstance(p, dict)}
        for p, rows in (H.get("tech") or {}).items():
            for r in rows:
                at = r[1]
                ca = canon_attrib(at, ups) or at
                if any(e.get("icon") for e in ups.get(ca, [])):
                    continue
                g = found.setdefault(at, {"games": {}, "in_data": ca in ups})
                g["games"].setdefault(game, (r[0], civ.get(str(p)) or f"player {p}"))
    added = 0
    for at in sorted(found):
        if at not in notes:
            notes[at] = {"name": "", "short": "", "desc": "", "from": ""}
            added += 1
    print(f"{len(found)} upgrades without an icon in work/*.hud.json:")
    for at in sorted(found):
        n = notes.get(at) or {}
        state = "described" if n.get("desc") else "TO DESCRIBE"
        seen = "; ".join(f"{g} {mmss(t)} {c}" for g, (t, c) in sorted(found[at]["games"].items()))
        print(f"  [{state}] {at}{'' if found[at]['in_data'] else '  (not in upgrades.json)'}  -  {seen}")
    if not a.list and added:
        with open(NOTES, "w", encoding="utf-8") as fh:
            json.dump(dict(sorted(notes.items())), fh, indent=1, ensure_ascii=False)
        print(f"{added} added to data/tech_notes.json - fill in desc / from (and name / short if you like)")


if __name__ == "__main__":
    main()
