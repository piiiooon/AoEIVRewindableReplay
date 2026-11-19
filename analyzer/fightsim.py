"""Fight simulator (owner 2026-11-10; review only): place each recorded fight between plain attack-move and perfect
micro, on open ground.

    python analyzer/fightsim.py <name>            # work/<name>.analyzed.json + .fights.json -> work/<name>.fightsim.json
    python analyzer/fightsim.py <name> --fight 4  # one fight, with a step log every 5 s
    python analyzer/fightsim.py <name> --html     # + views/<name>.fightsim.html: the fights as moving circles

Owner's definitions:
- Units: those in the fight area when it starts (reinforcements: arrivals list, not used yet - "room to explore").
- Open ground only: no terrain, buildings or TC / tower fire (tree-line positioning is a later calibrated part).
- The fight runs until one side is wiped out (cap T_MAX).
- Four runs: attack-move vs attack-move, micro vs attack-move, attack-move vs micro, micro vs micro.
- Attack-move: each unit hits the nearest enemy, walks to it if out of reach, keeps that target until it dies.
- Perfect micro, in the owner's order survive > priority > focus (spread against splash comes with splash data):
  1. survive: ranged units step away from melee threats while reloading (kiting), only when every threat is slower;
     a unit under 35 % HP that is threatened pulls back toward its own side while healthier allies remain and the
     threats are slower (running from equal or faster units only loses attacks);
  2. priority: the enemy worth the most per second of the unit's time: (its cost + 20 x its damage per second
     against my side) / (time to walk into reach + time to kill it), among the 6 nearest and those within reach +
     PRIO_LOOK - counters and cheap-to-kill valuable units go first, far ones lose to near ones;
  3. focus: no overkill - damage already committed by allies this second counts against a target's HP; a target
     already covered is skipped while another is available.
Per unit: HP, armour, weapon (damage, bonus damage by class, attack period, range, min range, burst) and move speed
from data/units.json (aoe4world), upgrades researched by the fight's start from the U events (aoe4world effects:
melee / ranged / siege attack, melee / ranged armour, hitpoints, attack speed, move speed, max range). Hits land
instantly; siege ignores armour; burst weapons deal damage x burst per volley. No splash or cleave yet (needs the v9 hit
events to measure), no projectile travel or misses, no abilities, charges or auras.

Micro score per side: share = enemy value lost / (both sides' value lost). Floor = my share when I attack-move and
they micro; ceiling = my share when I micro and they attack-move; score = (real share - floor) / (ceiling - floor),
clamped 0..1 (shown unclamped too). The real fight usually ends before a wipe-out (retreat), the sims don't: the share
compares the trade, not the size.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from basics import _is_army  # noqa: E402
from gamedata import class_match, resolve  # noqa: E402
from techs_bought import civ_code, techs_bought  # noqa: E402

FORMAT = "a4d-fightsim/1"
TILE = 4.0            # map units per tile (aoe4world ranges / speeds are in tiles)
DT = 0.1              # s
T_MAX = 240.0         # s: a run longer than this stops (kiting stalemates)
FIGHT_PAD = 25.0      # map units around the fight circle: units counted as in it at the start
HURT = 0.35           # HP share: a hurt unit pulls back when threatened
KITE_PAD = 1.0        # tiles: melee threat this much beyond its reach makes a reloading ranged unit step away
PRIO_LOOK = 2.0       # tiles beyond reach the micro target choice looks
FRAME_EVERY = 2       # steps between recorded frames for the page (0.2 s)
RETARGET = 1.3        # micro: switch target only for a score this much better (no dithering)
CELL = 4.0            # map units: grid for unit separation
RADIUS = (("elephant", 1.0), ("siege", 0.9), ("ship", 1.2), ("cavalry", 0.6), ("camel", 0.6), ("infantry", 0.35))
SKIP = ("monk", "scholar", "imam", "prelate", "priest", "shaman", "dervish", "trader")
MODES = (("am", "am"), ("micro", "am"), ("am", "micro"), ("micro", "micro"))


def _load(name, key):
    with open(os.path.join(HERE, "..", "data", name), encoding="utf-8") as fh:
        return json.load(fh)[key]


def mmss(t):
    t = int(round(t or 0))
    return f"{t // 60}:{t % 60:02d}"


# ---------------------------------------------------------------- unit stats with upgrades
def _selects(sel, base, classes):
    if not sel:
        return False
    if base in (sel.get("id") or []):
        return True
    return any(g and set(g) <= classes for g in (sel.get("class") or []))


def _effects(done, code, upgrades):
    """[effect] of the upgrades a player had finished (attribNames), the entry for their civ"""
    out = []
    for a in done:
        es = upgrades.get(a) or []
        e = next((x for x in es if code in (x.get("civs") or [])), es[0] if es else None)
        if e:
            out += e.get("effects") or []
    return out


def stats(bp, units, effects):
    u = units.get(bp) or units.get(resolve(bp, units) or "")
    if not u or not u.get("w") or not u.get("hp"):
        return None
    w = u["w"]
    cls = set(u.get("classes") or [])
    st = {"name": u.get("name") or bp, "base": u.get("base"), "classes": cls, "cost": float(u.get("cost") or 0),
          "hp": float(u["hp"]), "marmor": float((u.get("armor") or {}).get("melee") or 0),
          "rarmor": float((u.get("armor") or {}).get("ranged") or 0), "type": w.get("type") or "melee",
          "dmg": float(w.get("dmg") or 0), "period": float(w.get("speed") or 1.5), "range": float(w.get("range") or 0),
          "min": float(w.get("min") or 0), "burst": int(w.get("burst") or 1), "mods": w.get("mods") or [],
          "move": float(u.get("move") or 1.0)}
    atk = {"melee": "meleeAttack", "ranged": "rangedAttack", "siege": "siegeAttack"}.get(st["type"])
    for e in effects:
        if not _selects(e.get("select"), st["base"], cls):
            continue
        p, v, mul = e.get("property"), float(e.get("value") or 0), e.get("effect") == "multiply"
        key = {atk: "dmg", "meleeArmor": "marmor", "rangedArmor": "rarmor", "hitpoints": "hp", "moveSpeed": "move",
               "maxRange": "range", "attackSpeed": "period"}.get(p)
        if key:
            st[key] = st[key] * v if mul else st[key] + v
    st["r"] = next((rad for w_, rad in RADIUS if w_ in cls), 0.4) * TILE
    st["reach"] = st["range"] * TILE
    st["minr"] = st["min"] * TILE
    st["spd"] = st["move"] * TILE
    return st


def hit(a, t):
    """damage of one attack (volley) of stats a on stats t"""
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
    return max(1.0, d) * a["burst"]


# ---------------------------------------------------------------- the simulation
class U:
    __slots__ = ("i", "side", "st", "x", "z", "hp", "cool", "tgt", "dead_t", "fired")

    def __init__(self, i, side, st, x, z, hp):
        self.i, self.side, self.st, self.x, self.z = i, side, st, x, z
        self.hp = min(hp, st["hp"]) if hp else st["hp"]
        self.cool, self.tgt, self.dead_t, self.fired = 0.0, None, None, False


def _d(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def _in_reach(a, b, d=None):
    d = _d(a, b) if d is None else d
    gap = d - a.st["r"] - b.st["r"]
    if a.st["type"] == "melee":
        return gap <= max(a.st["reach"], 0.5)
    return gap <= a.st["reach"] and d >= a.st["minr"]


def _threat(t, foes):
    """t's damage per second against the other side's average unit"""
    if not foes:
        return 0.0
    return sum(hit(t.st, f.st) for f in foes) / len(foes) / t.st["period"]


def run(units, modes, t_max=T_MAX, log=None, frames=None):
    """units: [U]; modes: {side: "am" / "micro"}. Returns per side: lost value, left value / count, time."""
    U_ = [u for u in units]
    sides = sorted({u.side for u in U_})
    t = 0.0
    while t < t_max:
        alive = {s: [u for u in U_ if u.dead_t is None and u.side == s] for s in sides}
        if any(not v for v in alive.values()):
            break
        cen = {s: (sum(u.x for u in v) / len(v), sum(u.z for u in v) / len(v)) for s, v in alive.items()}
        threat = {}
        for s in sides:
            foes = [f for q in sides if q != s for f in alive[q]]
            for u in alive[s]:
                threat[u.i] = _threat(u, foes)
        committed = {}
        order = sorted((u for v in alive.values() for u in v), key=lambda u: u.cool)
        moves = []
        for u in order:
            foes = [f for q in sides if q != u.side for f in alive[q]]
            mode = modes[u.side]
            u.cool = max(0.0, u.cool - DT)
            u.fired = False
            if mode == "am":
                if u.tgt is None or u.tgt.dead_t is not None:
                    u.tgt = min(foes, key=lambda f: _d(u, f))
                tg = u.tgt
            else:
                tg = _micro_target(u, foes, threat, committed)
                # survive: kite / pull back
                melee_threats = [f for f in foes if f.st["type"] == "melee"
                                 and _d(u, f) - u.st["r"] - f.st["r"] <= max(f.st["reach"], 0.5) + KITE_PAD * TILE]
                # stepping away only pays against slower threats (equal speed: they keep up, the shot is lost)
                slower = [f for f in melee_threats if f.st["spd"] < u.st["spd"]]
                if slower and len(slower) == len(melee_threats) and u.st["type"] != "melee" and u.cool > DT:
                    moves.append((u, _away(u, melee_threats, cen[u.side]), u.st["spd"]))
                    continue
                if u.hp < HURT * u.st["hp"] and melee_threats and all(f.st["spd"] < u.st["spd"] for f in melee_threats) \
                        and len(alive[u.side]) > 1 and any(a.hp > u.hp for a in alive[u.side] if a is not u):
                    moves.append((u, _away(u, melee_threats, cen[u.side]), u.st["spd"]))
                    continue
                u.tgt = tg
            if tg is None:
                continue
            d = _d(u, tg)
            if _in_reach(u, tg, d):
                if u.cool <= 0:
                    dmg = hit(u.st, tg.st)
                    tg.hp -= dmg
                    u.cool = u.st["period"]
                    u.fired = True
                    if tg.hp <= 0 and tg.dead_t is None:
                        tg.dead_t = t
                if mode == "micro":
                    committed[tg.i] = committed.get(tg.i, 0.0) + hit(u.st, tg.st) * (1.0 / max(u.st["period"], 1.0))
            else:
                if u.st["type"] != "melee" and d < u.st["minr"]:
                    moves.append((u, _away(u, [tg], cen[u.side]), u.st["spd"]))
                else:
                    moves.append((u, (tg.x, tg.z), u.st["spd"]))
        for u, (gx, gz), spd in moves:
            if u.dead_t is not None:
                continue
            dx, dz = gx - u.x, gz - u.z
            L = math.hypot(dx, dz)
            if L > 1e-6:
                s = min(L, spd * DT)
                u.x += dx / L * s
                u.z += dz / L * s
        _separate([u for u in U_ if u.dead_t is None])
        if frames is not None and int(round(t / DT)) % FRAME_EVERY == 0:
            frames.append([round(t, 2), [[u.i, round(u.x, 1), round(u.z, 1), round(max(u.hp, 0)),
                                          u.tgt.i if u.tgt is not None and u.tgt.dead_t is None else -1,
                                          1 if u.fired else 0] for u in U_ if u.dead_t is None or u.dead_t >= t - DT]])
        t += DT
        if log is not None and abs(t / 5 - round(t / 5)) < DT / 10:
            log.append({"t": round(t, 1), **{str(s): len([u for u in U_ if u.dead_t is None and u.side == s])
                                             for s in sides}})
    out = {}
    for s in sides:
        mine = [u for u in U_ if u.side == s]
        out[s] = {"lost": round(sum(u.st["cost"] for u in mine if u.dead_t is not None)),
                  "left": round(sum(u.st["cost"] * max(u.hp, 0) / u.st["hp"] for u in mine if u.dead_t is None)),
                  "n_left": sum(1 for u in mine if u.dead_t is None), "n": len(mine)}
    out["t"] = round(t, 1)
    out["winner"] = next((s for s in sides if out[s]["n_left"] and all(not out[q]["n_left"] for q in sides if q != s)),
                         None)
    return out


def _micro_target(u, foes, threat, committed):
    """the enemy worth the most per second of this unit's time: (its cost + its threat) / (time to reach it + time to
    kill it); already covered by allies' committed damage (focus, no overkill) counts 5 %"""
    reach = u.st["reach"] + u.st["r"] + PRIO_LOOK * TILE + (0.5 if u.st["type"] == "melee" else 0)
    near = {f.i: f for f in sorted(foes, key=lambda f: _d(u, f))[:6]}
    for f in foes:
        if _d(u, f) - f.st["r"] <= reach:
            near[f.i] = f
    near = list(near.values())

    def score(f):
        d = _d(u, f)
        gap = d - u.st["r"] - f.st["r"] - (max(u.st["reach"], 0.5) if u.st["type"] == "melee" else u.st["reach"])
        walk = max(0.0, gap) / max(u.st["spd"], 0.1)
        kill = max(f.hp, 1.0) / (hit(u.st, f.st) / u.st["period"])
        s = (f.st["cost"] + 20.0 * threat.get(f.i, 0.0)) / (walk + kill)
        if committed.get(f.i, 0.0) >= f.hp:          # focus: already covered by allies
            s *= 0.05
        return s
    best = max(near, key=score)
    cur = u.tgt if u.tgt is not None and u.tgt.dead_t is None and u.tgt in near else None
    if cur is not None and score(best) < RETARGET * score(cur):
        return cur
    return best


def _away(u, threats, home):
    tx = sum(f.x for f in threats) / len(threats)
    tz = sum(f.z for f in threats) / len(threats)
    dx, dz = u.x - tx, u.z - tz
    L = math.hypot(dx, dz) or 1.0
    hx, hz = home[0] - u.x, home[1] - u.z
    H = math.hypot(hx, hz) or 1.0
    vx, vz = dx / L + 0.3 * hx / H, dz / L + 0.3 * hz / H     # away from them, a little toward my side
    return u.x + vx * 10, u.z + vz * 10


def _separate(units):
    grid = {}
    for u in units:
        grid.setdefault((int(u.x // CELL), int(u.z // CELL)), []).append(u)
    for (cx, cz), us in grid.items():
        near = [v for ox in (-1, 0, 1) for oz in (-1, 0, 1) for v in grid.get((cx + ox, cz + oz), [])]
        for a in us:
            for b in near:
                if b.i <= a.i:
                    continue
                d = _d(a, b)
                m = a.st["r"] + b.st["r"]
                if d < m:
                    if d < 1e-6:
                        a.x += 0.01
                        d = 0.01
                    push = (m - d) / 2
                    ux, uz = (b.x - a.x) / d, (b.z - a.z) / d
                    a.x -= ux * push
                    a.z -= uz * push
                    b.x += ux * push
                    b.z += uz * push


# ---------------------------------------------------------------- recorded fights
def fight_units(tl, f, units, effects_of):
    """[U] in the fight area at its start; also the skipped blueprints"""
    fr = min(tl["frames"], key=lambda x: abs(x["t"] - f["start"]))
    pids = [p["idx"] for p in tl["players"]]
    out, skipped, i = [], {}, 0
    rad = (f.get("r") or 15.0) + FIGHT_PAD
    for e in fr["entities"]:
        if e["owner"] not in pids or e["x"] is None or not _is_army(e) or any(w in (e["bp"] or "") for w in SKIP):
            continue
        if math.hypot(e["x"] - f["x"], e["z"] - f["z"]) > rad:
            continue
        st = stats(e["bp"], units, effects_of[e["owner"]](fr["t"]))
        if not st:
            skipped[e["bp"]] = skipped.get(e["bp"], 0) + 1
            continue
        out.append(U(i, e["owner"], st, e["x"], e["z"], e.get("hp")))
        i += 1
    return out, skipped


def _clone(us):
    return [U(u.i, u.side, u.st, u.x, u.z, u.hp) for u in us]


def _share(res, s, o):
    a, b = res[s]["lost"], res[o]["lost"]
    return b / (a + b) if a + b > 0 else None


def real_anim(tl, f, units, costs, pad=5.0):
    """the recorded fight as circles: 4/s fight samples (dump v6+) or the 1 s frames, from the start to its end + pad;
    every player unit (army and villagers) within the fight circle + FIGHT_PAD at some point"""
    meta = {}
    for fr in tl["frames"]:
        if f["start"] - 2 <= fr["t"] <= f["end"] + pad:
            for e in fr["entities"]:
                if e["owner"] in (1, 2) and e["kind"] in ("m", "w") and e["id"] not in meta:
                    meta[e["id"]] = (e["owner"], e["bp"] or "", e["kind"])
    rad = (f.get("r") or 15.0) + FIGHT_PAD
    fast = [x for x in tl.get("fast") or [] if f["start"] <= x["t"] <= f["end"] + pad]
    if fast:
        src = [(x["t"], [(i, v[0], v[1], v[2], v[3]) for i, v in x["u"].items() if v[0] is not None]) for x in fast]
    else:
        src = [(fr["t"], [(e["id"], e["x"], e["z"], e.get("hp"), e.get("target")) for e in fr["entities"]
                          if e["id"] in meta and e["x"] is not None])
               for fr in tl["frames"] if f["start"] <= fr["t"] <= f["end"] + pad]
    ids = set()
    for _, us in src:
        for i, x, z, *_ in us:
            if int(i) in meta and math.hypot(x - f["x"], z - f["z"]) <= rad:
                ids.add(int(i))
    table, idx = [], {}
    for i in sorted(ids):
        side, bp, kind = meta[i]
        u = units.get(bp) or units.get(resolve(bp, units) or "") or {}
        cls = set(u.get("classes") or [])
        r = next((rad_ for w_, rad_ in RADIUS if w_ in cls), 0.4) * TILE
        typ = "villager" if kind == "w" else ((u.get("w") or {}).get("type") or "melee")
        cost = (costs.get(resolve(bp, costs) or "") or {})
        val = sum(float(cost.get(k) or 0) for k in ("food", "wood", "gold", "stone"))
        idx[i] = len(table)
        table.append([len(table), side, u.get("name") or bp, round(r, 2), u.get("hp") or 0, typ, round(val)])
    frames = []
    seen_hp = {}
    for t, us in src:
        row = []
        for i, x, z, hp, tg in us:
            i = int(i)
            if i not in idx:
                continue
            seen_hp[i] = max(seen_hp.get(i, 0), hp or 0)
            row.append([idx[i], round(x, 1), round(z, 1), round(hp or 0), idx.get(int(tg), -1) if tg else -1, 0])
        frames.append([round(t - f["start"], 2), row])
    for i, j in idx.items():                     # max HP: the data's, else the most seen
        if not table[j][4]:
            table[j][4] = seen_hp.get(i) or 1
    return {"units": table, "frames": frames}


def analyze(tl, fights, only=None, verbose=False, record=False):
    units = _load("units.json", "units")
    upgrades = _load("upgrades.json", "upgrades")
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        bought = {}
    pids = [p["idx"] for p in tl["players"]]
    code = {p: civ_code(tl, p) for p in pids}

    def eff(p):
        return lambda t: _effects([x["attrib"] for x in bought.get(p, []) if x.get("done", 1e9) <= t], code[p], upgrades)
    effects_of = {p: eff(p) for p in pids}
    out = {"format": FORMAT, "players": tl["players"], "fights": [], "params": {
        "DT": DT, "T_MAX": T_MAX, "FIGHT_PAD": FIGHT_PAD, "HURT": HURT, "KITE_PAD": KITE_PAD, "PRIO_LOOK": PRIO_LOOK}}
    for f in fights.get("fights") or []:
        if only is not None and f["n"] != only:
            continue
        us, skipped = fight_units(tl, f, units, effects_of)
        sides = sorted({u.side for u in us})
        rec = {"n": f["n"], "start": f["start"], "end": f["end"], "units": {str(s): sum(1 for u in us if u.side == s)
                                                                          for s in pids}, "skipped": skipped}
        real = {str(p): (f.get("lost") or {}).get(str(p)) or 0 for p in pids}
        rec["real"] = real
        if len(sides) < 2:
            rec["note"] = "one side only (no enemy army in the area at the start)"
            out["fights"].append(rec)
            continue
        a, b = pids
        runs = {}
        anim = {}
        for ma, mb in MODES:
            log = [] if verbose else None
            frs = [] if record else None
            r = run(_clone(us), {a: ma, b: mb}, log=log, frames=frs)
            runs[f"{ma}-{mb}"] = {"t": r["t"], "winner": r["winner"],
                                  **{str(s): r[s] for s in (a, b)}, **({"log": log} if verbose else {})}
            if record:
                anim[f"{ma}-{mb}"] = frs
        if record:
            rec["anim"] = {"units": [[u.i, u.side, u.st["name"], round(u.st["r"], 2), round(u.st["hp"]), u.st["type"],
                                      round(u.st["cost"])] for u in us],
                           "runs": anim, "real": real_anim(tl, f, units, _load("costs.json", "costs"))}
        rec["runs"] = runs
        rec["score"] = {}
        for s, o, flo, cei in ((a, b, "am-micro", "micro-am"), (b, a, "micro-am", "am-micro")):
            ra, rb = real[str(s)], real[str(o)]
            real_share = rb / (ra + rb) if ra + rb > 0 else None
            fl = _share({s: runs[flo][str(s)], o: runs[flo][str(o)]}, s, o)
            ce = _share({s: runs[cei][str(s)], o: runs[cei][str(o)]}, s, o)
            sc = None
            if None not in (real_share, fl, ce) and abs(ce - fl) > 0.02:
                sc = (real_share - fl) / (ce - fl)
            rec["score"][str(s)] = {"real_share": None if real_share is None else round(real_share, 2),
                                    "floor": None if fl is None else round(fl, 2),
                                    "ceiling": None if ce is None else round(ce, 2),
                                    "score": None if sc is None else round(max(0.0, min(1.0, sc)), 2),
                                    "raw": None if sc is None else round(sc, 2)}
        out["fights"].append(rec)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--work", default=os.path.join(HERE, "..", "work"))
    ap.add_argument("--fight", type=int)
    ap.add_argument("--html", nargs="?", const="", help="also write the circles page (default views/<name>.fightsim.html)")
    a = ap.parse_args()

    def rd(k):
        with open(os.path.join(a.work, f"{a.name}.{k}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    out = analyze(rd("analyzed"), rd("fights"), a.fight, verbose=a.fight is not None, record=a.html is not None)
    if a.html is not None:
        sys.path.insert(0, os.path.join(HERE, "..", "viewer"))
        import build_fightsim
        page = a.html or os.path.join(HERE, "..", "views", f"{a.name}.fightsim.html")
        build_fightsim.build(out, page)
        print("page:", page)
    if a.fight is None:
        with open(os.path.join(a.work, f"{a.name}.fightsim.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, separators=(",", ":"))
    for f in out["fights"]:
        head = f"fight {f['n']} {mmss(f['start'])}-{mmss(f['end'])} units {f['units']} real lost {f['real']}"
        if "note" in f:
            print(head, "-", f["note"])
            continue
        print(head + (f" skipped {f['skipped']}" if f["skipped"] else ""))
        for k, r in f["runs"].items():
            print(f"   {k:12s} {r['t']:6.1f}s winner P{r['winner']} " + "  ".join(
                f"P{s}: lost {r[s]['lost']} left {r[s]['n_left']}/{r[s]['n']}" for s in r if s.isdigit()))
            if "log" in r:
                print("      " + " ".join(f"{x['t']}:{'/'.join(str(v) for k_, v in x.items() if k_ != 't')}" for x in r["log"]))
        for s, sc in f["score"].items():
            print(f"   P{s} micro score {sc}")


if __name__ == "__main__":
    main()
