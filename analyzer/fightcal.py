"""Calibrated fight engine (owner 2026-11-10: "we need to predict real results") and its check against the scripted test
fights (logs/fighttests). Every rule below is a measured value from the owner's test batches (CLAUDE.md "Batch 1 results",
"Splash re-runs"); data/units.json supplies the rest (HP, armour, damage, bonus, range, move speed, attack phases).

    python analyzer/fightcal.py <fighttests folder> [--runs 3]     # sim vs game for every test, + the totals

Engine (0.125 s steps = one game tick):
- move: data speed x 4 units per tile; melee units with a target charge (x CHARGE by base: spear 1.25, knight 1.19,
  horseman 1.07, other infantry 1.25, other cavalry 1.1); a spearman whose target is cavalry coming at it braces (stops) within BRACE (the others close in: m03);
  cavalry reaching a braced spear lands its first hit STUN s later (measured 2.25-2.5).
- reach: centre distance <= weapon range x 4 + both radii (RADIUS by class; spear pair 3.98 vs measured 3.92, knight on
  spear 4.95 vs 4.84); ranged: within range (+ target radius), not inside the minimum range.
- attack: a swing starts when in reach and ready; it lands after aim + windup + attack (spear 0.375 measured); the next
  swing PERIOD later (data speed; knight measured 1.625, override). Projectiles fly distance / PROJ_SPEED (arrow 35 u/s,
  bolt 80; siege stones FLIGHT 1.25 s) and land on the target where it is then.
- damage = max(1, damage + bonus vs classes - armour of the weapon type); siege ignores armour.
- splash / pierce (per projectile, the burst split into projectiles): mangonel 3 stones per volley, each landing with
  SCATTER around the target, hitting every enemy within 1.25 (57 % at 1.5, 5 % at 2-2.5); nest of bees 7 rockets, full
  within 2.0, 40 % damage to 2.5; springald / bed crossbow bolts pierce along the line to maximum range (springald:
  units the line passes through; bed crossbow: chance by distance from the line 55 % / 20 % / 5 %); ribauldequin volley
  = up to 3 enemies nearest the target, the bolts split among them; cannon / bombard single target.
- orders as the tests gave them: attack-move (nearest enemy, kept until it dies), hold (no movement, attacks in reach),
  move (walk to the far side); invulnerable sides take no damage.
"""
import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gamedata import class_match, resolve  # noqa: E402

DT = 0.125
TILE = 4.0
RADIUS = (("elephant", 1.0), ("siege", 0.9), ("cavalry", 0.6), ("camel", 0.6), ("infantry", 0.35), ("worker", 0.35))
CHARGE = {"spearman": 1.25, "knight": 1.19, "horseman": 1.07}
CHARGE_INF, CHARGE_CAV = 1.25, 1.1
BRACE = 12.0          # map units: a spear facing cavalry stops when it is this close
STUN = 2.25           # s: cavalry's first hit on a braced spear after contact
PERIOD = {"knight": 1.625}
CHARGE_DMG = {"knight": 12.0}   # batch 2: a knight's first hit +12 (32 on a knight, 36 on an archer / horseman, 32 on
                                # men-at-arms), not on a bracing spear (t06: 24); horseman: none (c03)
CHARGE_NEXT = 1.25              # s: the knight's swing after the charge hit (then 1.625)
# measured where the data's weapon is not the one that fights (batch 2): villagers fight with 6 per hit every 3.875 s
# (the data lists the torch: 10 fire every 2.125); the war elephant hits 50 every 3.0 s and cleaves ~35 % to enemies
# around the target (27 / 25 / 15 / 13 / 5 seen), and its rider (a second entity) hits 25 every 3.75 s
SPECIAL = {"villager": {"type": "melee", "dmg": 6.0, "period": 3.875, "mods": [], "range": 1.2, "lead": 0.875},
           "war-elephant": {"period": 3.0, "cleave": 0.35, "extra": (25.0, 3.75)}}
CLEAVE_R = 3.5        # map units around the target
PROJ_SPEED = {"archer": 35.0, "crossbowman": 80.0, "springald": 80.0, "bed-crossbow": 80.0, "longbowman": 35.0}
FLIGHT = 1.25         # s: siege stones / rockets
SCATTER = 1.0         # map units: siege landing spread around the aimed point
T_MAX = 240.0
MELEE_CAP = 1.2       # map units
PREF = 0.5            # target choice: distance factor for targets the unit has a big bonus against
# splash re-measured over 0.6 s after each landing (owner's re-runs t11s / t12s / t16s; 18 spears at spacing 1.8): hit
# chance per enemy by distance from the landing point (0.5-unit bins) / from the bolt's line
# the measured rates undercount (several impacts at once: a hit goes to the nearest one), so they are scaled to the
# measured totals (t11s 837, t12s 1278 dealt in 40 s): mangonel x 1.6, rockets x 1.45, capped at 1
MANG_P = [min(1.0, 1.6 * p) for p in (1.0, 0.65, 0.59, 0.47, 0.52, 0.41, 0.25, 0.0)]                 # 0 .. 3.5
ROCK_P = [min(1.0, 1.45 * p) for p in (1.0, 1.0, 0.85, 0.78, 0.70, 0.60, 0.46, 0.50, 0.35, 0.33, 0.10, 0.0)]   # 0 .. 5.5
BED_P = [0.7, 0.7, 0.45, 0.36, 0.22, 0.18, 0.09, 0.0]                  # perp 0 .. 3.5
PIERCE_W = 1.2        # springald: units within this of the line (2 per shot on knights 2 rows deep)


def _load(name, key):
    with open(os.path.join(HERE, "..", "data", name), encoding="utf-8") as fh:
        return json.load(fh)[key]


UNITS = None


UPGRADES = None
GW = None
AOE_EDGE = float(os.environ.get("A4D_EDGE", "0.5"))   # share of the body radius taken off the distance (fitted on t11s/t12s/us01: 1.0 = +20 %, 0 = -40 %; replace with the game's own radius)
AOE_SCAT = os.environ.get("A4D_SCAT", "area")         # landing spread: uniform over the disk area / radius
GAME_AOE = True       # area / scatter / falloff from the game's own weapon files (data/game_weapons.json)


def game_weapon(bp, upgrades=()):
    """the game's weapon values for a unit blueprint: area radius, falloff bands, landing scatter (map units).
    data/game_weapons.json (tools/game_assets.py weapons, from the owner's installation): file name weapon_<bp minus
    unit_>, civ / tier suffixes dropped until one exists; Adjustable Crossbars -> weapon_mangonel_4_adjustable_crossbars"""
    global GW
    if GW is None:
        f = os.path.join(HERE, "..", "data", "game_weapons.json")
        raw = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        GW = {}
        for k, v in raw.items():
            if "campaign" in k or "rogue" in k:
                continue
            GW.setdefault(os.path.basename(k.replace("\\", "/")).rsplit(".", 1)[0], v)
    name = bp[5:] if bp.startswith("unit_") else bp
    if "upgrade_siege_adjustable_crossbar" in upgrades and "mangonel" in name:
        name = "mangonel_4_adjustable_crossbars"
    parts = name.split("_")
    d = None
    while parts and d is None:
        d = GW.get("weapon_" + "_".join(parts))
        parts = parts[:-1]
    if d is None:
        return None
    P = "/data/default/weapon_bag/"
    g = lambda k, dflt=0.0: d.get(P + k) if d.get(P + k) is not None else dflt
    return {"R": g("area_effect/area_info/outer_radius"), "Dn": g("area_effect/distance/near"),
            "Dm": g("area_effect/distance/mid"), "Df": g("area_effect/distance/far"),
            "Kn": g("area_effect/damage/near", 1.0), "Km": g("area_effect/damage/mid", 1.0),
            "Kf": g("area_effect/damage/far", 1.0), "scatter": g("scatter/area_scatter_option/area_info/outer_radius"),
            "angle": g("scatter/angle_scatter"), "range": g("range/max")}


def aoe_factor(G, d):
    """damage factor at distance d from the impact (bands: near <= Dn, mid <= Df, far <= R; 0 outside)"""
    if d > G["R"]:
        return 0.0
    if d <= G["Dn"]:
        return G["Kn"]
    if d <= max(G["Df"], G["Dm"]):
        return G["Km"]
    return G["Kf"]


# owner's corrections where aoe4world's effect lists are incomplete (2026-11-12: Teardrop Shields "buffs both melee and
# ranged armor" of Cataphracts; aoe4world lists the melee +1 only - 259818624: knights took 1 less from mansa javelins from 15:25)
EFFECT_FIX = {"upgrade_teardrop_shields_byz": [{"property": "rangedArmor", "effect": "change", "value": 1,
                                                "select": {"id": ["cataphract"]}}]}


def effects_of(names, code=None):
    """aoe4world effects of upgrades (attribNames), the civ's entry when there are several, + EFFECT_FIX"""
    global UPGRADES
    if UPGRADES is None:
        UPGRADES = _load("upgrades.json", "upgrades")
    out = []
    for a in names:
        es = UPGRADES.get(a) or []
        e = next((x for x in es if code in (x.get("civs") or [])), es[0] if es else None)
        if e:
            out += e.get("effects") or []
        out += EFFECT_FIX.get(a, [])
    return out


# units an upgrade reaches through the unit they were upgraded from, where aoe4world's effect lists name only the older one
# (259818624: Malian Ranged Damage I done 13:52 -> Mansa Javelineer hits 16 -> 17 / 4 -> 5; the list names javelin-thrower)
SELECT_ALIAS = {"mansa-javelineer": ("javelin-thrower",)}


def _selects(sel, base, classes):
    if not sel:
        return False
    ids = sel.get("id") or []
    if base in ids or any(a in ids for a in SELECT_ALIAS.get(base, ())):
        return True
    return any(class_match(g, classes) for g in (sel.get("class") or []))


def stats(bp, effects=()):
    global UNITS
    if UNITS is None:
        UNITS = _load("units.json", "units")
    u = UNITS.get(bp) or UNITS.get(resolve(bp, UNITS) or "")
    if not u:
        return None
    cls = set(u.get("classes") or [])
    w = u.get("w") or {}
    d = w.get("dur") or {}
    base = u.get("base") or ""
    typ = w.get("type") or "melee"
    st = {"bp": bp, "base": base, "classes": cls, "hp": float(u.get("hp") or 1), "cost": float(u.get("cost") or 0),
          "marmor": float((u.get("armor") or {}).get("melee") or 0), "rarmor": float((u.get("armor") or {}).get("ranged") or 0),
          "type": typ, "dmg": float(w.get("dmg") or 0), "mods": w.get("mods") or [],
          "period": PERIOD.get(base, float(w.get("speed") or 1.5)),
          "lead": float((d.get("aim") or 0) + (d.get("windup") or 0) + (d.get("attack") or 0)),
          "range": float(w.get("range") or 0) * TILE, "minr": float(w.get("min") or 0) * TILE,
          "burst": int(w.get("burst") or 1), "spd": float(u.get("move") or 1.0) * TILE,
          "cav": "cavalry" in cls, "melee": typ == "melee"}
    atk = {"melee": "meleeAttack", "ranged": "rangedAttack", "siege": "siegeAttack"}.get(typ)
    for e in effects:
        if not _selects(e.get("select"), base, cls):
            continue
        prop, v, mul = e.get("property"), float(e.get("value") or 0), e.get("effect") == "multiply"
        key = {atk: "dmg", "meleeArmor": "marmor", "rangedArmor": "rarmor", "hitpoints": "hp", "moveSpeed": "spd",
               "maxRange": "range", "attackSpeed": "period"}.get(prop)
        if key:
            if key == "range" and not mul:
                v *= TILE
            st[key] = st[key] * v if mul else st[key] + v
    sp = SPECIAL.get(base)
    if sp:
        st.update(sp)
        st["melee"] = st["type"] == "melee"
    st["r"] = next((rad for k, rad in RADIUS if k in cls), 0.4) * TILE
    st["gw"] = game_weapon(bp) if GAME_AOE else None
    if st["melee"]:
        st["charge"] = CHARGE.get(base, CHARGE_CAV if st["cav"] else CHARGE_INF)
    else:
        st["charge"] = 1.0
    st["splash"] = ("mangonel" if "mangonel" in base else "rockets" if "nest-of-bees" in base
                    else "pierce" if base in ("springald",) else "pierce_fuzzy" if "bed-crossbow" in base
                    else "ribauld" if "ribauldequin" in base else None)
    return st


def hit(a, t, per_projectile=False):
    d = a["dmg"]
    for groups, val in a["mods"]:
        for g in groups:
            alts = g if g and isinstance(g[0], list) else [g]
            if any(class_match(al, t["classes"]) for al in alts):
                d += val
                break
    if a["type"] == "melee":
        d -= t["marmor"]
    elif a["type"] == "ranged":
        d -= t["rarmor"]
    d = max(1.0, d)
    return d if per_projectile else d * a["burst"]


class U:
    __slots__ = ("i", "side", "st", "x", "z", "hp", "ready", "tgt", "dead", "order", "inv", "braced", "met", "dealt",
                 "swung", "ready2")

    def __init__(self, i, side, st, x, z, hp, order="am", inv=False):
        self.i, self.side, self.st, self.x, self.z = i, side, st, x, z
        self.hp = hp if hp else st["hp"]
        self.ready, self.tgt, self.dead, self.order, self.inv = 0.0, None, None, order, inv
        self.braced, self.met, self.dealt, self.swung, self.ready2 = False, set(), 0.0, set(), 0.0


def dist(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def in_reach(a, b):
    d = dist(a, b)
    if a.st["melee"]:
        # melee closes to body contact + its reach, at most MELEE_CAP (a horseman's 1.5-tile... 6-unit reach would leave a
        # bracing spear out of its own reach; measured contacts: spear pair 3.92, cavalry on spear 4.67-4.84)
        return d <= min(a.st["range"], MELEE_CAP) + a.st["r"] + b.st["r"] + 0.05
    return d <= a.st["range"] + b.st["r"] and d >= a.st["minr"]


def simulate(units, rng, t_max=T_MAX, axis=None, until_one_side=True):
    """units: [U]; returns (end time, reason)"""
    t = 0.0
    pending = []          # (t_land, attacker, target or None, x, z, kind)
    sides = sorted({u.side for u in units})
    while t < t_max:
        alive = [u for u in units if u.dead is None]
        by = {s: [u for u in alive if u.side == s] for s in sides}
        if until_one_side and len(sides) == 2 and any(not by[s] for s in sides):
            return t, "side gone"
        # projectiles landing now
        keep = []
        for p in pending:
            if p[0] <= t + 1e-9:
                land(p, units, rng, t)
            else:
                keep.append(p)
        pending = keep
        moves = []
        for u in alive:
            if u.dead is not None:
                continue
            foes = [f for s in sides if s != u.side for f in by[s] if f.dead is None]
            if u.order == "move":
                if axis:
                    moves.append((u, axis[u.side], u.st["spd"]))
                continue
            if not foes:
                continue
            if u.order == "hold":
                if u.tgt is None or u.tgt.dead is not None or not in_reach(u, u.tgt):
                    inr = [f for f in foes if in_reach(u, f)]
                    u.tgt = min(inr, key=lambda f: pick_score(u, f)) if inr else None
            elif u.tgt is None or u.tgt.dead is not None or not in_reach(u, u.tgt):
                # attack-move: nearest, counters preferred (owner's batch t17: spears went for the horsemen, not the
                # nearer men-at-arms); kept while in reach
                u.tgt = min(foes, key=lambda f: pick_score(u, f))
            tg = u.tgt
            if tg is None:
                continue
            if in_reach(u, tg):
                if tg.i not in u.met:
                    u.met.add(tg.i)
                    stun = STUN if (u.st["cav"] and u.st["melee"] and tg.braced) else 0.0
                    u.ready = max(u.ready, t + stun)
                ex = u.st.get("extra")
                if ex and t + 1e-9 >= getattr(u, "ready2", 0.0):
                    u.ready2 = t + ex[1]
                    pending.append((t + 0.5, u, tg, ex[0], None, "fixed"))
                if t + 1e-9 >= u.ready:
                    first = tg.i not in u.swung
                    u.swung.add(tg.i)
                    u.ready = t + (u.st["period"] if not (first and CHARGE_DMG.get(u.st["base"])) else CHARGE_NEXT)
                    tl = t + u.st["lead"]
                    if u.st["melee"]:
                        bonus = CHARGE_DMG.get(u.st["base"], 0) if first and not tg.braced else 0
                        pending.append((tl, u, tg, bonus, None, "melee"))
                    else:
                        fl = FLIGHT if u.st["type"] == "siege" or u.st["splash"] in ("mangonel", "rockets") else \
                            dist(u, tg) / PROJ_SPEED.get(u.st["base"], 50.0)
                        pending.append((tl + fl, u, tg, tg.x, tg.z, u.st["splash"] or "single"))
                continue
            if u.order == "hold":
                continue
            # brace: a spearman facing cavalry waits for it
            if u.st["base"] == "spearman" and tg.st["cav"] and tg.tgt is u and dist(u, tg) <= BRACE:
                u.braced = True
                continue
            spd = u.st["spd"] * (u.st["charge"] if u.st["melee"] else 1.0)
            if not u.st["melee"] and dist(u, tg) < u.st["minr"]:
                moves.append((u, (2 * u.x - tg.x, 2 * u.z - tg.z), u.st["spd"]))
            else:
                moves.append((u, (tg.x, tg.z), spd))
        for u, (gx, gz), spd in moves:
            dx, dz = gx - u.x, gz - u.z
            L = math.hypot(dx, dz)
            if L > 1e-6:
                s = min(L, spd * DT)
                u.x += dx / L * s
                u.z += dz / L * s
        separate([u for u in units if u.dead is None])
        t += DT
    return t, "time"


def pick_score(u, f):
    """distance, halved when u has a bonus against f at least as large as its base damage"""
    d = dist(u, f)
    b = hit(u.st, f.st, True) - (u.st["dmg"] - (f.st["marmor"] if u.st["melee"] else f.st["rarmor"] if u.st["type"] == "ranged" else 0))
    return d * (PREF if b >= u.st["dmg"] else 1.0)


def damage(a, v, amount, t):
    if v.dead is not None:
        return
    if not v.inv:
        dealt = min(amount, v.hp)
        v.hp -= amount
        a.dealt += dealt
        if v.hp <= 1e-9:
            v.dead = t
    else:
        a.dealt += amount


def land(p, units, rng, t):
    tl, a, tg, x, z, kind = p
    foes = [u for u in units if u.dead is None and u.side != a.side]
    if kind == "fixed":
        if tg.dead is None:
            damage(a, tg, x, t)
        return
    if kind in ("melee", "single"):
        if tg.dead is None and (kind == "single" or in_reach(a, tg) or dist(a, tg) <= a.st["range"] + a.st["r"] + tg.st["r"] + 1.0):
            damage(a, tg, hit(a.st, tg.st) + (x or 0 if kind == "melee" else 0), t)
            if kind == "melee" and a.st.get("cleave"):
                for v in foes:
                    if v is not tg and v.dead is None and dist(v, tg) <= CLEAVE_R:
                        damage(a, v, a.st["cleave"] * hit(a.st, v.st), t)
        return
    G = a.st.get("gw")
    if kind in ("mangonel", "rockets") and G and G["R"] > 0.2:
        # the game's own area: each projectile lands uniformly within the scatter disk around the aimed point and hits
        # every enemy whose body edge is within the area radius, at the band's damage factor
        n = a.st.get("stones", 3) if kind == "mangonel" else a.st["burst"]
        for _ in range(n):
            u_ = rng.random()
            ang, rr = rng.uniform(0, 2 * math.pi), G["scatter"] * (math.sqrt(u_) if AOE_SCAT == "area" else u_)
            cx, cz = x + rr * math.cos(ang), z + rr * math.sin(ang)
            for v in foes:
                d = max(0.0, math.hypot(v.x - cx, v.z - cz) - AOE_EDGE * v.st["r"])
                f = aoe_factor(G, d)
                if f > 0:
                    damage(a, v, f * hit(a.st, v.st, True), t)
        return
    if kind == "mangonel":
        for _ in range(a.st.get("stones", 3)):
            ang, rr = rng.uniform(0, 2 * math.pi), rng.uniform(0, SCATTER)
            cx, cz = x + rr * math.cos(ang), z + rr * math.sin(ang)
            for v in foes:
                d = math.hypot(v.x - cx, v.z - cz)
                pr = MANG_P[min(int(d * 2), len(MANG_P) - 1)]
                if pr and rng.random() < pr:
                    damage(a, v, hit(a.st, v.st, True), t)
    elif kind == "rockets":
        for _ in range(a.st["burst"]):
            ang, rr = rng.uniform(0, 2 * math.pi), rng.uniform(0, SCATTER)
            cx, cz = x + rr * math.cos(ang), z + rr * math.sin(ang)
            for v in foes:
                d = math.hypot(v.x - cx, v.z - cz)
                pr = ROCK_P[min(int(d * 2), len(ROCK_P) - 1)]
                if pr and rng.random() < pr:
                    f = 1.0 if d <= 1.0 else max(0.4, 1.0 - 0.6 * (d - 1.0) / 1.5)
                    damage(a, v, f * hit(a.st, v.st, True), t)
    elif kind in ("pierce", "pierce_fuzzy"):
        L = math.hypot(x - a.x, z - a.z) or 1.0
        ux, uz = (x - a.x) / L, (z - a.z) / L
        for v in foes:
            along = (v.x - a.x) * ux + (v.z - a.z) * uz
            if along < 0 or along > a.st["range"] + v.st["r"]:
                continue
            perp = abs(-(v.x - a.x) * uz + (v.z - a.z) * ux)
            if kind == "pierce":
                ok = perp <= PIERCE_W
            else:
                pr = BED_P[min(int(perp * 2), len(BED_P) - 1)]
                ok = rng.random() < pr
            if ok:
                damage(a, v, hit(a.st, v.st, True), t)
    elif kind == "ribauld":
        near = sorted(foes, key=lambda v: math.hypot(v.x - x, v.z - z))[:3]
        if near:
            per = a.st["burst"] / len(near)
            for v in near:
                damage(a, v, hit(a.st, v.st, True) * per, t)


def separate(units):
    grid = {}
    for u in units:
        grid.setdefault((int(u.x // 4), int(u.z // 4)), []).append(u)
    for (cx, cz), us in grid.items():
        near = [v for ox in (-1, 0, 1) for oz in (-1, 0, 1) for v in grid.get((cx + ox, cz + oz), [])]
        for a in us:
            for b in near:
                if b.i <= a.i:
                    continue
                d = dist(a, b)
                m = a.st["r"] + b.st["r"]
                if d < m:
                    if d < 1e-6:
                        a.x += 0.01
                        d = 0.01
                    push = (m - d) / 2
                    ux, uz = (b.x - a.x) / d, (b.z - a.z) / d
                    wa = 0.0 if a.order == "hold" else 1.0
                    wb = 0.0 if b.order == "hold" else 1.0
                    if wa + wb == 0:
                        continue
                    a.x -= ux * push * 2 * wa / (wa + wb)
                    a.z -= uz * push * 2 * wa / (wa + wb)
                    b.x += ux * push * 2 * wb / (wa + wb)
                    b.z += uz * push * 2 * wb / (wa + wb)


# ---------------------------------------------------------------- the tests, replayed
def from_test(R):
    """units at the test's first frame, with the orders / invulnerability the test gave"""
    t0, fr = R["frames"][0]
    inv = set(R.get("inv") or [])
    orders = {s: (R["cmd"].get(s) or ("am",))[0] for s in (1, 2)}
    us = []
    ups = {s: [n for side, n, ok in R.get("up") or [] if side == s and ok == "ok"] for s in (1, 2)}
    for q, u in sorted(R["units"].items()):
        v = fr.get(q)
        if not v or not v.get("n"):
            continue
        st = stats(u["bp"], effects_of(ups[u["side"]]))
        if st is None:
            continue
        # full health at the start reads as the upgraded maximum (u08: the first frame still showed 230 of Biology's 287.5)
        hp = st["hp"] if (v.get("hp") or 0) >= (v.get("hpmax") or 0) - 0.01 else v.get("hp")
        if ups[u["side"]] and "upgrade_siege_adjustable_crossbar" in ups[u["side"]]:
            st["stones"] = 4          # measured: one more stone per volley (data: attack speed x0.99)
            st["gw"] = game_weapon(u["bp"], ups[u["side"]]) if GAME_AOE else None
        us.append(U(len(us), u["side"], st, v["x"], v["z"], hp, orders[u["side"]], u["side"] in inv))
    axis = None
    s = R.get("start") or {}
    if s:
        far = 60
        axis = {1: (s["cx"] + s["dx"] * far, s["cz"] + s["dz"] * far), 2: (s["cx"] - s["dx"] * far, s["cz"] - s["dz"] * far)}
    return us, axis


def game_result(R):
    last = R["frames"][-1][1] if R["frames"] else {}
    side_ents = {s: {u["entity"] for u in R["units"].values() if u["side"] == s} for s in (1, 2)}
    out = {}
    for s in (1, 2):
        sq = [q for q, u in R["units"].items() if u["side"] == s]
        alive = [q for q in sq if (last.get(q) or {}).get("n")]
        out[s] = {"n": len(sq), "alive": len(alive), "hp": sum((last.get(q) or {}).get("hp") or 0 for q in alive),
                  "dealt": sum(h[3] or 0 for h in R["hits"] if h[1] in side_ents[s])}
    out["t"] = (R["end"] or (None,))[0]
    return out


def sim_result(us, t):
    out = {}
    for s in (1, 2):
        mine = [u for u in us if u.side == s]
        out[s] = {"n": len(mine), "alive": sum(1 for u in mine if u.dead is None),
                  "hp": sum(max(u.hp, 0) for u in mine if u.dead is None), "dealt": sum(u.dealt for u in mine)}
    out["t"] = t
    return out


def main():
    import fighttests as FT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", help="write the comparison here")
    a = ap.parse_args()
    files = sorted(f for f in os.listdir(a.folder) if f.endswith(".txt"))
    tests = {}
    for f in files:
        tid = f.rsplit("_r", 1)[0]
        if a.only and tid not in a.only:
            continue
        tests.setdefault(tid, []).append(os.path.join(a.folder, f))
    rows = []
    for tid, fs in tests.items():
        G, S, name = [], [], ""
        for k, f in enumerate(fs):
            R = FT.load(f)
            name = R["meta"].get("name", "")
            if not R["frames"] or not R["units"] or R.get("kite"):
                continue          # scripted micro (orb-walking tests): the engine has no kiting yet
            G.append(game_result(R))
            us, axis = from_test(R)
            secs = R["meta"].get("secs") or 90
            two = sum(1 for s in (1, 2) if any(u.side == s for u in us)) == 2
            t, why = simulate(us, random.Random(1000 + k), t_max=secs, axis=axis,
                              until_one_side=two and not any(u.inv for u in us))
            S.append(sim_result(us, t))
        if not G:
            continue

        def mean(L, s, k):
            v = [x[s][k] for x in L]
            return sum(v) / len(v)
        row = {"id": tid, "name": name, "runs": len(G)}
        for src, L in (("game", G), ("sim", S)):
            row[src] = {str(s): {k: round(mean(L, s, k), 1) for k in ("alive", "hp", "dealt")} for s in (1, 2)}
            row[src]["t"] = round(sum(x["t"] or 0 for x in L) / len(L), 2)
            row[src]["range_dealt"] = {str(s): [round(min(x[s]["dealt"] for x in L)), round(max(x[s]["dealt"] for x in L))]
                                       for s in (1, 2)}
        gw = [1 if x[1]["alive"] > x[2]["alive"] else 2 if x[2]["alive"] > x[1]["alive"] else 0 for x in G]
        sw = [1 if x[1]["alive"] > x[2]["alive"] else 2 if x[2]["alive"] > x[1]["alive"] else 0 for x in S]
        row["winner_game"], row["winner_sim"] = gw, sw
        rows.append(row)
    # print
    print(f"{'test':6s} {'name':34s} {'winner g/s':12s} {'S1 dealt game | sim':24s} {'S2 dealt game | sim':24s} {'time g | s':12s}")
    ok_w = n_w = 0
    errs = []
    for r in rows:
        g, s = r["game"], r["sim"]
        gw = max(set(r["winner_game"]), key=r["winner_game"].count)
        sw = max(set(r["winner_sim"]), key=r["winner_sim"].count)
        fighting = g["1"]["dealt"] + g["2"]["dealt"] > 0
        if fighting and gw:
            n_w += 1
            ok_w += gw == sw
        for side in ("1", "2"):
            if g[side]["dealt"] > 50:
                errs.append(abs(s[side]["dealt"] - g[side]["dealt"]) / g[side]["dealt"])
        print(f"{r['id']:6s} {r['name'][:34]:34s} {str(gw) + ' / ' + str(sw):12s} "
              f"{g['1']['dealt']:8.0f} | {s['1']['dealt']:<8.0f}      {g['2']['dealt']:8.0f} | {s['2']['dealt']:<8.0f}      "
              f"{g['t']:5.1f} | {s['t']:<5.1f}")
    errs.sort()
    med = errs[len(errs) // 2] if errs else None
    print(f"\nwinner right {ok_w}/{n_w}; damage dealt per side: median error "
          f"{'-' if med is None else f'{med:.0%}'}, within 15 %: {sum(1 for e in errs if e <= 0.15)}/{len(errs)}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)


if __name__ == "__main__":
    main()
