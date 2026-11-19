"""Blueprint lookups shared by the analyzer and exporter.

The game's blueprint names and aoe4world's don't always match:
  unit_knight_hospitaller_tem_2 -> unit_knight_hospitaller_2_tem   (tier digit elsewhere)
  unit_ram_fire_3_byz           -> unit_workshop_fire_ram_3_byz    (order, extra word)
  building_aqueduct_byz         -> building_aqueduct_bastion_byz   (extra word)
resolve() tries: exact; same name at the nearest other tier; then the same name parts in any
order with at most one part more or less, preferring the same tier (never a "free" variant).
"""
import re

# units the game spawns for free (no purchase): cost 0, not "unknown"
FREE = ("unit_pilgrim",)
# elephant crew (owner 2026-11-13: Delhi / Tughlaq elephants are one unit with several weapons): the rider / spearman, tower
# archers, handcannoneers, monks ... are their own entities in the elephant's squad. resolve() matched them to the elephant
# (unit_war_elephant_tower_archer_4_sul -> the 1,000-resource Tower Elephant), so every crew member counted the elephant's cost
# again. They resolve to nothing and cost 0; the elephant carries the unit's value.
CREW_RE = re.compile(r"^unit_war_elephant_(?:tower_)?(?:spearman|archer|handcannoneer|crossbow\w*|monk|rider|crew|mahout)_")

_index = {}


def is_crew(bp):
    return bool(bp) and bool(CREW_RE.match(bp))


def is_free(bp):
    return bool(bp) and (bp.startswith(FREE) or is_crew(bp))


def _parts(name):
    toks = name.split("_")
    tier = next((int(t) for t in toks if t.isdigit() and len(t) == 1), None)
    words = frozenset(t for t in toks[1:] if not (t.isdigit() and len(t) == 1))
    return toks[0], words, tier


def _build(table):
    idx = {}
    for k in table:
        pre, words, tier = _parts(k)
        idx.setdefault(pre, []).append((words, tier, k))
    return idx


def resolve(bp, table):
    if not bp or is_crew(bp):
        return None
    if bp in table:
        return bp
    m = re.search(r"_(\d)(_|$)", bp)
    if m:
        n = int(m.group(1))
        for k in sorted(range(1, 5), key=lambda k: (abs(k - n), -k)):
            alt = bp[:m.start(1)] + str(k) + bp[m.end(1):]
            if alt in table:
                return alt
    idx = _index.get(id(table))
    if idx is None:
        idx = _index[id(table)] = _build(table)
    pre, words, tier = _parts(bp)
    best, bkey = None, None
    for kw, kt, k in idx.get(pre, ()):
        extra = (kw - words) | (words - kw)
        # same parts, or one part more/less on either side; never a "free" variant
        if len(extra) > 1 or "free" in extra or not (words <= kw or kw <= words):
            continue
        key = (len(extra), 0 if kt == tier else abs((kt or 0) - (tier or 0)) or 9, k)
        if bkey is None or key < bkey:
            best, bkey = k, key
    return best


def class_match(words, classes):
    """aoe4world bonus targets are word lists (["light", "melee", "infantry"]); the unit's classes are the joined names
    ("light_melee_infantry"). Strict: the joined name must be one of the classes (every joined target name in the data
    exists as a class; matching loose tokens gave false hits: "siege" inside "find_non_siege_land_military")"""
    return bool(words) and "_".join(words) in classes


def canon_attrib(at, table):
    """the upgrades.json key for a game upgrade attrib (owner 2026-11-11, Tughlaq: attribs carry a civ suffix such as
    _sul_ha_tug that upgrades.json often lacks - upgrade_econ_resource_wood_harvest_rate_2_sul_ha_tug): the attrib itself,
    else the attrib with up to three trailing _segments dropped (never below three segments); None if nothing matches"""
    if at in table:
        return at
    # building emplacements (owner 2026-11-12): the game's bupgrade_outpost_springald / _barbican_springald_chi ... are listed by
    # aoe4world under one name per weapon
    m = re.search(r"(springald|handcannon|cannon|arrowslit)", at) if re.search(r"outpost|keep|tower|barbican|fort|castle", at) else None
    if m:
        k = {"springald": "upgrade_keep_springald", "cannon": "upgrade_keep_cannon", "arrowslit": "upgrade_outpost_arrowslits",
             "handcannon": "upgrade_outpost_handcannonslits_chi"}[m.group(1)]
        if k in table and "_".join(at.split("_")[:2]) != "upgrade_naval":
            return k
    parts = at.split("_")
    for k in range(1, 4):
        if len(parts) - k < 3:
            break
        cand = "_".join(parts[:-k])
        if cand in table:
            return cand
    return None
