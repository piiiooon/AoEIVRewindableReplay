"""Unit -> model parts for the 3D viewer (owner 2026-11-10), from models/artmap.json (tools/game_assets.py artmap). Stays on
this PC under models/ (game art is never shipped).

    python tools/unit_models.py            # -> models/unit_models.json, + the parts to export
    python tools/unit_models.py --show spearman

Rules (read off artmap.json, English units checked by hand):
- body: the unit's tier list for its own tier (unit_spearman_2_eng -> tier2_spearman_eng). Tier lists are cumulative
  (archer tier3 = age02 + age03 bodies), so the body is the humans / animals / team_weapons path ending in ageNN of the
  unit's tier, else the last one. Other paths in that list ride along (knight shield heater).
- weapon: the first weapon list that is not the torch, a charge or a spear wall; its first path.
- villagers / siege crew: body only (their tier list carries every work tool and resource).
- buildings (owner 2026-11-10: static, so the game's models): art paths under structures from every list; most buildings
  name stamps instead (owner 2026-11-11): the first tier list's civ stamp -> its structure models (models/stamps.json);
  exported from DX12Geo<civ> (Gen7 has few structures).
- no tier list with civ art (villagers: archetypes only, siege: art on the unit itself): the direct art path, else the
  civ's own villager body by name (eng_villager_female_age01) from models/model_list.txt.
Model names = the last path part (= the .rrgeom stem; Gen7AssetsGeometry has every civ).
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "models"
BODY_DIRS = ("\\humans\\", "\\animals\\", "\\team_weapons\\", "\\ships\\", "\\naval\\")


def stem(path):
    return path.replace("/", "\\").rstrip("\\").split("\\")[-1].lower()


def tier_of(unit):
    m = re.search(r"_(\d)(?:_|$)", unit)
    return int(m.group(1)) if m else None


def parts(unit, rec, villagers):
    t = tier_of(unit)
    tiers = rec["lists"].get("tier", {})
    tl = None
    if t is not None:
        tl = next((v for k, v in tiers.items() if k.lower().startswith(f"tier{t}_")), None)
    if tl is None and tiers:
        tl = list(tiers.values())[0]
    civ_art = [p for p in (tl or []) if "\\archetypes\\" not in p.lower()]
    bodies = [p for p in civ_art if any(d in p.lower() for d in BODY_DIRS)]
    body = None
    if bodies:
        want = [p for p in bodies if t is not None and stem(p).endswith(f"age0{t}")]
        body = (want or bodies)[-1]
    elif rec["direct"]:
        body = rec["direct"][0]
    extra = [p for p in civ_art if p is not body and not any(d in p.lower() for d in BODY_DIRS)]
    weapon = None
    for k, v in rec["lists"].get("weapon", {}).items():
        lk = k.lower()
        if v and not any(w in lk for w in ("torch", "charge", "spearwall", "template")) and not stem(v[0]).startswith("fx_"):
            weapon = v[0]
            break
    # owner 2026-11-12: knights hold the lance when charging - the charge weapon list's art (the 3D page swaps it in)
    charge = None
    for k, v in rec["lists"].get("weapon", {}).items():
        if "charge" in k.lower() and v and not stem(v[0]).startswith("fx_"):
            charge = v[0]
            break
    out = {"body": stem(body) if body else None, "weapon": stem(weapon) if weapon else None,
           "charge": stem(charge) if charge and stem(charge) != (stem(weapon) if weapon else None) else None,
           "extra": [stem(p) for p in extra if stem(p) != (stem(weapon) if weapon else None)]}
    if "villager" in unit or "siege_crew" in unit:   # tier list = every work tool / carried resource: body only
        out["extra"] = []
    if out["body"] is None and "villager" in unit:
        civ = unit.rsplit("_", 1)[-1]
        out["body"] = next((v for v in villagers if v.startswith(f"{civ}_villager") and v.endswith("age01")), None)
        out["extra"] = []
        out["weapon"] = None
    return out


SKIP_ART = ("\\stamps\\", "\\archetypes\\", "scaffold", "\\fx\\", "_destroyed", "_damaged", "_rubble", "_construction", "_unfinished")


STAMPS = None


def stamp_structures(ref):
    """a building's stamp (art\\stamps\\civ_scots\\sco_house_a_age_01) -> its structure models (models/stamps.json,
    tools/game_assets.py stamps)"""
    global STAMPS
    if STAMPS is None:
        f = MD / "stamps.json"
        STAMPS = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    out = []
    for r in STAMPS.get(ref.lower(), []):
        path, xf = (r, None) if isinstance(r, str) else r
        if "\\structures\\" in path.lower():
            out.append((path, xf))
    return out


WORDS = {"wood": ("lumber", "wood"), "food": ("mill", "food", "farm"), "mining": ("mining", "mine"), "dock": ("dock",),
         "market": ("market",), "house": ("house",), "town_center": ("town_center", "towncenter", "tc"),
         "blacksmith": ("blacksmith", "smith"), "monastery": ("monastery", "church"), "religious": ("monastery", "church", "temple")}


DEBRIS = re.compile(r"debris|rubble|destroy|ruin|broken|chunk|break|_dest(?![a-z])|_damage")


def stamp_pieces(st):
    """owner 2026-11-11: Viking landmarks still broken - a landmark stamp places many pieces, often the same model several
    times; all of them are kept (each with its own placement, up to 48), damage / debris pieces dropped, and pieces with
    no readable placement dropped when others have one (they all sat at the centre)"""
    st = [x for x in dict.fromkeys((p, tuple(xf) if xf else None) for p, xf in st)
          if not DEBRIS.search(x[0].lower().split("\\")[-1])]
    if any(xf for _, xf in st):
        st = [x for x in st if x[1]]
    return [(p, list(xf) if xf else None) for p, xf in st[:48]]


# owner 2026-11-11 (building_report): drop-off points are mostly props around a small structure - the lumber camp stamp has
# only a crane as a structure, the shed look is its logs / saw; the mill and mining camp structures are shared ("com_")
# models. For these the stamp's props are kept too, minus construction / scaffolding / outskirt markers / the relic slot.
DROPOFF = re.compile(r"econ_(wood|food|mining|gold|stone)|mining_camp|lumber|mill|granary")
PROP_SKIP = re.compile(r"construction|buildpile|scaffold|outskirt|sacred_object|marker|splat_")


def stamp_entries(ref):
    """every placed object of a stamp (structures and props) with its placement"""
    global STAMPS
    if STAMPS is None:
        f = MD / "stamps.json"
        STAMPS = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return [((r, None) if isinstance(r, str) else (r[0], r[1])) for r in STAMPS.get(ref.lower(), [])]


def best_structures(bp, st):
    """owner 2026-11-11: mining camp / mill / lumber camp got the wrong model - a stamp can name several structures;
    prefer the ones whose name shares a word with the blueprint (econ_wood -> lumber, econ_food -> mill, ...)"""
    want = [w for k, ws in WORDS.items() if k in bp.lower() for w in ws]
    if not want:
        return st
    good = [x for x in st if any(w in x[0].lower().split("\\")[-1] for w in want)]
    return good or st


def building_parts(rec, bp=""):
    """a building's model: the art paths under structures (not scaffolding / stamps / damage states), every list kind;
    the one the most names agree on first - several pieces (walls, gates) are kept, up to 4"""
    refs = list(rec["direct"])
    for kind in ("unit", "tier", "other", "weapon"):
        for v in rec["lists"].get(kind, {}).values():
            refs += v
    direct = [p for p in dict.fromkeys(refs) if "\\structures\\" in p.lower() and not any(s in p.lower() for s in SKIP_ART)]
    if direct:
        return [(p, None) for p in direct[:4]]
    # owner 2026-11-11: buildings name stamps per age / variant; the first tier list's civ stamps (not construction /
    # destroyed / scaffolding / outskirt dressing), variant a, its structure models
    tiers = rec["lists"].get("tier", {})
    order = [tiers[k] for k in sorted(tiers, key=lambda k: (not k.lower().startswith("tier"), k))]
    order += [v for kind in ("unit", "other", "weapon") for v in rec["lists"].get(kind, {}).values()]
    order.append(rec["direct"])
    # pass 1: civ stamps; pass 2 (farmsteads, fish ponds, totems, outposts had none): any stamp but construction /
    # destroyed / scaffolding, outskirt dressing last
    for allow in ((), ("outskirt",)):
        for refs_ in order:
            for r in refs_:
                lr = r.lower()
                if "\\stamps\\" in lr and not any(w in lr for w in ("const_dest", "scaffold", "outskirt") if w not in allow):
                    st = stamp_pieces(best_structures(bp, stamp_structures(r)))
                    if st and DROPOFF.search(bp):
                        props = [(p, xf) for p, xf in stamp_entries(r) if "\\structures\\" not in p.lower()
                                 and not PROP_SKIP.search(p.lower().split("\\")[-1])]
                        st = stamp_pieces(st + props)
                    if st:
                        return st
    return []


DROP_RE = re.compile(r"landmark|wonder|econ_|mining|mill|lumber|dock|granary|farmstead|longhouse|outpost")


def report(spec, A):
    """owner 2026-11-11: "the biggest misrender are the landmarks and any of the drop-off points". For each blueprint (comma
    list, or a views/<name>.3d.models.txt: its landmark / drop-off blueprints): the stamp references in its artmap entry
    (per list), every entry of each stamp in models/stamps.json (structures, props, nested stamps, with placement) and the
    pieces unit_models chose -> logs/building_report.txt (send it with a screenshot)"""
    if spec.endswith(".txt") and Path(spec).exists():
        # lines are "   N x <blueprint>: <what it uses>"
        bps = sorted({m.group(1).lower() for l in Path(spec).read_text(encoding="utf-8").splitlines()
                      for m in [re.search(r"(building_[a-z0-9_]+)\s*:", l)] if m and DROP_RE.search(m.group(1))})
    else:
        bps = [x.strip().lower() for x in spec.split(",") if x.strip()]
    global STAMPS
    if STAMPS is None:
        f = MD / "stamps.json"
        STAMPS = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    by_unit = {stem(k).removesuffix(".json").lower(): rec for k, rec in A.items()
               if "\\campaign\\" not in k and "/campaign/" not in k}
    lines = []
    for bp in bps:
        rec = by_unit.get(bp)
        lines.append(f"## {bp}")
        if not rec:
            lines.append("  not in artmap.json")
            continue
        refs = [("direct", r) for r in rec["direct"]]
        for kind, d in rec["lists"].items():
            for ln, v in d.items():
                refs += [(f"{kind}:{ln}", r) for r in v]
        stamps = [(where, r) for where, r in refs if "\\stamps\\" in r.lower()]
        lines.append(f"  {len(refs)} art refs, {len(stamps)} stamps; structures named directly: "
                     + ", ".join(stem(r) for _, r in refs if "\\structures\\" in r.lower())[:600])
        for where, r in stamps[:12]:
            ent = STAMPS.get(r.lower(), [])
            lines.append(f"  stamp {stem(r)} ({where}): {len(ent)} entries")
            for e in ent[:60]:
                path, xf = (e, None) if isinstance(e, str) else e
                kind = "STRUCT" if "\\structures\\" in path.lower() else "STAMP " if "\\stamps\\" in path.lower() else "prop  "
                lines.append(f"    {kind} {stem(path):48s} {[round(v, 3) for v in xf] if xf else '-'}")
        chosen = building_parts(rec, bp)
        lines.append("  chosen pieces: " + "; ".join(f"{stem(p)} {[round(v, 2) for v in xf] if xf else '-'}" for p, xf in chosen))
    dst = ROOT / "logs" / "building_report.txt"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {len(bps)} blueprints -> {dst}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show")
    ap.add_argument("--report", help="building blueprints (comma list) or views/<name>.3d.models.txt -> logs/building_report.txt")
    a = ap.parse_args()
    A = json.loads((MD / "artmap.json").read_text(encoding="utf-8"))
    if a.report:
        report(a.report, A)
        return
    names = set()   # Gen7 names (units); buildings come from DX12Geo<civ> (Gen7 has few structures)
    ml = MD / "model_list.txt"
    if ml.exists():
        for line in ml.read_text(encoding="utf-8").splitlines():
            if line.startswith("Gen7AssetsGeometry"):   # owner: Gen7 models only
                names.add(stem(line.split("\t")[0]).removesuffix(".rrgeom"))
    villagers = sorted(n for n in names if "_villager" in n)
    out, paths = {}, {}
    for k, rec in A.items():
        if "\\campaign\\" in k or "/campaign/" in k:
            continue
        unit = stem(k).removesuffix(".json")
        if unit.startswith("building_"):
            refs = building_parts(rec, unit)
            if refs:
                names_ = list(dict.fromkeys(stem(r[0]) for r in refs))
                out[unit] = {"body": names_[0], "weapon": None, "extra": names_[1:], "building": True,
                             "xf": {stem(r[0]): r[1] for r in refs if r[1]},
                             "pieces": [[stem(r[0]), r[1]] for r in refs]}
                for r in refs:
                    paths[stem(r[0])] = r[0]
            continue
        if not unit.startswith("unit_"):
            # map objects (owner 2026-11-10: mines at their real size, trees, animals): the first art path that is not
            # scaffolding / fx / a damage state, Gen7 copy
            refs = [r[0] for r in building_parts({"direct": rec["direct"], "lists": rec["lists"]})] or \
                [r for r in list(rec["direct"]) + [x for v in rec["lists"].get("unit", {}).values() for x in v]
                 if not any(sk in r.lower() for sk in SKIP_ART)]
            if refs and ("\\races\\" not in k.lower() and "/races/" not in k.lower()):
                out[unit] = {"body": stem(refs[0]), "weapon": None, "extra": [], "prop": True}
            continue
        p = parts(unit, rec, villagers)
        if p["body"]:
            out[unit] = p
    need = sorted({x for p in out.values() for x in [p["body"], p["weapon"], p.get("charge"), *p["extra"]] if x})
    missing = [n for n in need if names and n not in names and n not in paths]
    (MD / "unit_models.json").write_text(json.dumps({"units": out, "parts": need, "missing": missing, "paths": paths}, indent=1),
                                         encoding="utf-8")
    if a.show:
        for u, p in out.items():
            if a.show in u:
                print(f"  {u:34s} {p}")
    nb = sum(1 for v in out.values() if v.get("building"))
    nprop = sum(1 for v in out.values() if v.get("prop"))
    nb += nprop
    print(f"  {len(out) - nb} units, {nb - nprop} buildings, {nprop} map objects, {len(need)} parts ({len(missing)} not in model_list.txt) -> {MD / 'unit_models.json'}")


if __name__ == "__main__":
    main()
