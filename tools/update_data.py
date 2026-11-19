"""Rebuild data/*.json from a local copy of github.com/aoe4world/data (owner 2026-11-01: the analyzer did not
recognise the new civs' buildings and units after a patch).

    python tools/update_data.py                       # data-main next to aoe4-analyzer (C:\\aoe4\\data-main)
    python tools/update_data.py --data C:/aoe4/data-main
    python tools/update_data.py --check               # only compare with the current files, write nothing

Writes costs.json, icons.json, sight.json, units.json (units), upgrades.json, production.json, keeping each file's
format. Entries the old files had and data-main no longer has are kept (old replays may use them) and listed.
techs.json (11 base eco techs) and econ.json (wiki gather rates) are not from data-main and are left alone.
Prints what was added / changed / kept per file.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RES = ("food", "wood", "gold", "stone", "oliveoil", "silver")


def rows(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in d["data"] if isinstance(d, dict) else d:
        for v in r.get("variations") or [r]:
            out.append((r, v))
    return out


def icon_path(url):
    return url.split("/images/", 1)[1] if url and "/images/" in url else url


WONDER_AGE = {"wonder_dark_age": 1, "wonder_feudal_age": 2, "wonder_castle_age": 3, "wonder_imperial_age": 4}


def landmark_age(v):
    """the age a landmark is built in (wonder_*_age class; the attribName's ageN is not reliable: Mongols)"""
    for c in v.get("classes", []):
        if c in WONDER_AGE:
            return WONDER_AGE[c]
    for c in v.get("classes", []):
        if c.startswith("age") and "_landmark" in c and c[3:4].isdigit():
            return int(c[3])
    return None


def build(dm):
    U = rows(dm / "units" / "all.json")
    B = rows(dm / "buildings" / "all.json")
    T = rows(dm / "technologies" / "all.json")
    UP = rows(dm / "upgrades" / "all.json")
    costs, icons, sight, units = {}, {}, {}, {}
    prod_units, bbase, base_cost, landmarks, ltime = {}, {}, {}, {}, {}
    for kind, R in (("unit", U), ("building", B)):
        for r, v in R:
            a = v.get("attribName")
            if not a:
                continue
            c = v.get("costs") or {}
            cl = v.get("classes") or []
            e = {"name": v.get("name"), "type": kind}
            for x in ("food", "wood", "gold", "stone", "oliveoil"):
                e[x] = c.get(x, 0) or 0
            e["military"] = "military" in cl
            e["worker"] = "villager" in cl              # villagers (not trade carts / fishing boats)
            e["silver"] = c.get("silver", 0) or 0
            if kind == "building":
                e["landmark_age"] = landmark_age(v)
            e["age"] = v.get("age")
            costs[a] = e
            if v.get("icon"):
                icons[a] = icon_path(v["icon"])
            sl = (v.get("sight") or {}).get("line")
            if sl is not None:
                sight[a] = sl
            if kind == "unit":
                w = (v.get("weapons") or [None])[0]
                arm = {x["type"]: x["value"] for x in v.get("armor") or [] if x.get("value")}
                units[a] = {"name": v.get("name"), "base": v.get("baseId"), "age": v.get("age"), "civs": v.get("civs"),
                            "unique": bool(v.get("unique")),     # aoe4world's flag (spikes.py: unique units)
                            "hp": v.get("hitpoints"), "armor": arm, "classes": cl, "cost": c.get("total", 0),
                            "time": c.get("time"),      # production time s (3D: building production progress)
                            "move": (v.get("movement") or {}).get("speed"),      # tiles / s (fight simulator)
                            "w": ({"type": w.get("type"), "dmg": w.get("damage"), "speed": w.get("speed"),
                                   "range": (w.get("range") or {}).get("max"),
                                   "min": (w.get("range") or {}).get("min"),
                                   "burst": (w.get("burst") or {}).get("count"),
                                   # attack animation phases (s): aim, windup, attack, winddown, reload, setup,
                                   # teardown - orb walking = moving between the winddown and the next shot
                                   "dur": w.get("durations"),
                                   "mods": [[m["target"].get("class", []), m["value"]] for m in w.get("modifiers") or []
                                            if m.get("effect") == "change" and m.get("target")]}
                                  if w else None)}
                if v.get("producedBy"):
                    prod_units[a] = v["producedBy"]
            else:
                base = v.get("baseId") or r.get("baseId")
                bbase[a] = base
                for civ in v.get("civs") or [] if base != "town-center" else []:   # TCs: not a producer to imply
                    base_cost.setdefault(base, {})
                    if civ not in base_cost[base]:
                        base_cost[base][civ] = [a, c.get("total", 0)]
                la = landmark_age(v)
                if la:
                    for civ in v.get("civs") or []:
                        landmarks.setdefault(civ, {}).setdefault(str(la), [])
                        if base not in landmarks[civ][str(la)]:
                            landmarks[civ][str(la)].append(base)
                        if c.get("time"):
                            ltime.setdefault(civ, {})[str(la)] = c["time"]
    # age-up landmarks only: built in ages 1-3 (age 4 = wonders), civs with landmarks in all three ages (Abbasid,
    # Ayyubids, Golden Horde, Knights Templar age up differently - as in the old file)
    landmarks = {c: {k: v for k, v in d.items() if k in ("1", "2", "3")} for c, d in landmarks.items()}
    landmarks = {c: d for c, d in landmarks.items() if len(d) == 3}
    ltime = {c: {k: v for k, v in d.items() if k in ("1", "2", "3")} for c, d in ltime.items() if c in landmarks}
    upgrades = {}
    for r, v in T + UP:
        a = v.get("attribName")
        if not a:
            continue
        c = v.get("costs") or {}
        upgrades.setdefault(a, []).append({"civs": v.get("civs"), "name": v.get("name"),
                                           "food": c.get("food", 0) or 0, "wood": c.get("wood", 0) or 0,
                                           "stone": c.get("stone", 0) or 0, "gold": c.get("gold", 0) or 0,
                                           "time": c.get("time"), "icon": icon_path(v.get("icon")),
                                           "unique": bool(v.get("unique")),     # spikes.py: unique techs
                                           # fight simulator: stat changes (property, select classes / ids, change /
                                           # multiply, value) as aoe4world lists them
                                           "effects": [{"property": e.get("property"), "select": e.get("select"),
                                                        "effect": e.get("effect"), "value": e.get("value")}
                                                       for e in v.get("effects") or []
                                                       if e.get("type") in (None, "passive")]})
    civs = build_civs(dm, U, B, T + UP)
    # abilities by the game's PBG id (owner 2026-11-11: decode the ability commands in the replay file): name, attrib,
    # active / toggle / always, icon
    abilities = {}
    ap_ = dm / "abilities" / "all.json"
    if ap_.exists():
        for r, v in rows(ap_):
            if v.get("pbgid"):
                abilities[str(v["pbgid"])] = {"name": v.get("name"), "attrib": v.get("attribName"), "active": v.get("active"),
                                              "civs": v.get("civs"), "icon": icon_path(v.get("icon")),
                                              # owner 2026-11-12, aura buffs from positions (analyzer/auras.py): radius in
                                              # tiles (0 = no radius), the units / buildings it sits on, stat effects
                                              "auraRange": v.get("auraRange"), "activatedOn": v.get("activatedOn"),
                                              "effects": [{"property": e.get("property"), "effect": e.get("effect"),
                                                           "value": e.get("value"), "select": e.get("select"),
                                                           "duration": e.get("duration")}
                                                          for e in v.get("effects") or []]}
    # units / buildings / technologies by PBG id (owner 2026-11-12: the replay's queue commands name what was queued by
    # its PBG id; analyzer/replay.py queues()): [kind, attribName]
    pbgids = {}
    for kind, R in (("unit", U), ("building", B), ("tech", T + UP)):
        for r, v in R:
            if v.get("pbgid") and v.get("attribName"):
                pbgids.setdefault(str(v["pbgid"]), [kind, v["attribName"]])
    return {"pbgids.json": ("pbgids", pbgids), "abilities.json": ("abilities", abilities), "civs.json": ("civs", civs), "costs.json": ("costs", costs), "icons.json": ("icons", icons), "sight.json": ("sight", sight),
            "units.json": ("units", units), "upgrades.json": ("upgrades", upgrades),
            "production.json": (None, {"units": prod_units, "buildingBase": bbase, "baseCost": base_cost,
                                       "landmarks": landmarks, "landmarkTime": ltime})}


def build_civs(dm, U, B, TU):
    """civs.json (owner 2026-11-10: the package should know civs as civs): per civ code (aoe4world abbr) its name, game
    attribName, classes, description and overview text (bonuses, playstyle), the units it can make per age (base, name,
    first age, unique), its unique technologies and its landmarks per age with their descriptions. Pro games correct
    this on the civ pages (civ_notes.json: the owner's own notes, same keys)."""
    idx = json.loads((dm / "civilizations" / "civs-index.json").read_text(encoding="utf-8"))
    out = {}
    for code, ci in idx.items():
        f = dm / "civilizations" / f"{ci.get('slug')}.json"
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        units = {}
        for r, v in U:
            if code not in (v.get("civs") or []):
                continue
            base = v.get("baseId") or r.get("baseId")
            age = v.get("age") or 1
            cur = units.get(base)
            if cur is None or age < cur["age"]:
                units[base] = {"name": r.get("name") or v.get("name"), "age": age, "unique": bool(v.get("unique")),
                               "military": "military" in (v.get("classes") or []),
                               "description": (r.get("description") or v.get("description") or "")[:300]}
        techs = {}
        for r, v in TU:
            if code in (v.get("civs") or []) and v.get("unique"):
                techs.setdefault(r.get("baseId") or v.get("attribName"), {
                    "name": v.get("name"), "age": v.get("age"),
                    "description": (v.get("description") or r.get("description") or "")[:300]})
        lms = {}
        for r, v in B:
            if code not in (v.get("civs") or []):
                continue
            la = landmark_age(v)
            if la:
                lms.setdefault(str(la), {})[r.get("baseId") or v.get("attribName")] = {
                    "name": v.get("name"), "description": (v.get("description") or r.get("description") or "")[:400]}
        out[code] = {"name": ci.get("name") or d.get("name"), "attribName": ci.get("attribName"),
                     "classes": d.get("classes"), "description": d.get("description"),
                     "overview": [{"title": o.get("title"), "description": o.get("description"), "list": o.get("list")}
                                  for o in d.get("overview") or []],
                     "units": units, "uniqueTechs": techs, "landmarks": {k: lms[k] for k in sorted(lms)}}
    return out


def compare(old, new, label):
    """(added, changed, gone) keys"""
    add = sorted(set(new) - set(old))
    gone = sorted(set(old) - set(new))
    ch = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    print(f"  {label}: {len(new)} entries; {len(add)} new, {len(ch)} changed, {len(gone)} only in the old file (kept)")
    return add, ch, gone


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT.parent / "data-main")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not (a.data / "units" / "all.json").exists():
        sys.exit(f"aoe4world data not found at {a.data} (units/all.json); use --data")
    stamp = f"github.com/aoe4world/data, local copy {a.data.name} ({time.strftime('%Y-%m-%d', time.localtime((a.data / 'units' / 'all.json').stat().st_mtime))})"
    report = []
    for fname, (key, new) in build(a.data).items():
        p = DATA / fname
        old_d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        print(fname)
        if key:
            old = old_d.get(key, {})
            add, ch, gone = compare(old, new, key)
            merged = dict(old)
            merged.update(new)
            out = {"source": f"{stamp}; kept from before: {len(gone)}", key: merged}
            report.append((fname, add, gone))
        else:
            out = {"source": stamp}
            for k, v in new.items():
                old = old_d.get(k, {})
                add, ch, gone = compare(old, v, k)
                merged = dict(old)
                merged.update(v)
                out[k] = merged
                report.append((f"{fname} {k}", add, gone))
        if not a.check:
            p.write_text(json.dumps(out, ensure_ascii=True), encoding="ascii")   # plain ASCII: reads the same in any Windows codepage
    civs = sorted({k.rsplit("_", 1)[-1] for f, add, _ in report if f == "costs.json" for k in add})
    print(f"\nnew blueprint suffixes in costs: {', '.join(civs)}")
    for f, add, gone in report:
        if gone and f in ("costs.json", "units.json"):
            print(f"{f}: only in the old file: {', '.join(gone[:12])}{' ...' if len(gone) > 12 else ''}")
    print("checked only (nothing written)" if a.check else "written to " + str(DATA))


if __name__ == "__main__":
    main()
