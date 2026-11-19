"""Villager economy per player (review: full information) - owner, 2026-10-25.

The idea: an aggressor who can take food outside his base (deer, boar) gathers faster than farms or berries
and opens a resource gap; forward mills and outposts / walls are what that costs.

Per player, sampled every STEP s:
- what each villager is on: the game's gather flag gives the resource; food villagers are placed on farm /
  berry / deer / boar / sheep / fish by position (same reach rules as food.py); "map hunt" = deer or boar
  further than BASE_R from the player's starting TC
- nominal income: villagers on each source x base gather rate (data/econ.json: Age of Empires wiki base
  rates; civ overrides) x the gather multipliers of the technologies researched so far (U events;
  aoe4world effects: food / hunt / berry / farm / wood / gold / stone)
- measured income: bank change + everything spent, per resource (true banks; costs of everything made
  and researched). efficiency = measured / nominal: walking, drop-off distance, idle time, civ bonuses
  the data doesn't model
- hunt premium: food gathered on deer / boar above what the same villager-time would give on farms
  (farm rate x the player's farm multipliers); map-hunt premium: the same, only outside the base
- food sources: natural (econ.natural_food), farms (farm villager-time x farm rate), other = gathered food
  minus both (passive / non-villager food: Malian cattle, Mongol pastures, fishing boats, ...)
- investments: forward drop sites (mill / hunting cabin further than BASE_R from the starting TC) and
  defence (outposts, towers, walls, gates, forts); net = hunt premium - those
"""
import json
import math
import os

from gamedata import resolve, is_free
from techs_bought import techs_bought, civ_code

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = 2              # s between samples
BASE_R = 50.0         # map units from the starting TC: inside = their base
REACH, FARM_R, SHEEP_R = 8.0, 9.0, 5.0
WINDOWS = ((0, 300), (300, 600), (600, 900), (900, 1200))
RES = ("food", "wood", "gold", "stone")
SOURCES = ("farm", "berry", "deer", "boar", "sheep", "fish", "other")
DROP_FWD = ("food_control", "hunting_cabin", "mill")
DEFENCE = ("outpost", "tower", "palisade", "_wall", "wall_", "gate", "wooden_fort", "keep", "bastion")


def load_econ():
    with open(os.path.join(HERE, "..", "data", "econ.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _snap_index(snaps, t):
    lo, hi = 0, len(snaps) - 1
    if hi < 0 or snaps[0]["t"] > t:
        return -1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if snaps[mid]["t"] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _grid(points, cell=16.0):
    g = {}
    for p in points:
        g.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    return g


def _near(g, x, z, r, cell=16.0):
    best, bd = None, r
    cx, cz = int(x // cell), int(z // cell)
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for p in g.get((cx + dx, cz + dz), ()):
                d = math.hypot(p[0] - x, p[1] - z)
                if d <= bd:
                    best, bd = p, d
    return best


def _food_kind(n):
    t, bp = n["type"], n.get("bp") or ""
    if t == "carcass":
        return "boar" if "boar" in bp else "sheep" if "sheep" in bp else "deer"
    return {"berry": "berry", "deer": "deer", "boar": "boar", "sheep": "sheep", "fish": "fish"}.get(t)


# food nodes whose remaining amount drops as they're eaten. Recorded: deer and boar are eaten in place (same
# entity, amount 350 -> 0); sheep become a separate *_corpse entity (carcass), so a live sheep never drops
NATURAL_TAKE = ("berry", "carcass", "deer", "boar", "sheep", "fish")
REGIONS = ("base", "own side", "enemy side", "enemy base")


def _region(x, z, mine, theirs):
    dm, dt_ = math.dist((x, z), mine), math.dist((x, z), theirs)
    if dm <= BASE_R:
        return "base"
    if dt_ <= BASE_R:
        return "enemy base"
    return "own side" if dm <= dt_ else "enemy side"


def natural_food(tl, tc0, region=None, regions=REGIONS):
    """Natural food each player took (owner: how much outside food you take vs your opponent; the farm
    transition is costly). Every drop in a berry bush / carcass / fish amount between two node snapshots is
    split over the players by their food villager-time within REACH of it in that interval; nothing near
    = unattributed (decay, animals killed by armies). Region: by the node's position from each player's
    starting TC. Also the natural food on the map at the start, per region, from each player's side."""
    frames, snaps = tl["frames"], [s for s in (tl.get("nodes") or [])]
    pids = [p["idx"] for p in tl["players"]]
    if len(snaps) < 2 or any(tc0[o] is None for o in pids) or len(pids) != 2:
        return None
    other = {pids[0]: pids[1], pids[1]: pids[0]}
    region = region or _region
    taken = {o: {r: 0.0 for r in regions} for o in pids}
    unattr, series, fi = 0.0, [], 0
    for i in range(len(snaps) - 1):
        a, b = snaps[i], snaps[i + 1]
        nodes = {n["id"]: n for n in a["nodes"] if n["x"] is not None and n["type"] in NATURAL_TAKE
                 and (n.get("left") or 0) > 0}
        if not nodes:
            continue
        g = _grid([(n["x"], n["z"], nid) for nid, n in nodes.items()])
        near = {}
        while fi < len(frames) and frames[fi]["t"] <= b["t"]:
            fr = frames[fi]
            if fr["t"] > a["t"] and fi % STEP == 0:
                for e in fr["entities"]:
                    if e["kind"] == "w" and e.get("res") == 1 and e["x"] is not None and e["owner"] in taken:
                        hit = _near(g, e["x"], e["z"], REACH)
                        if hit:
                            d = near.setdefault(hit[2], {})
                            d[e["owner"]] = d.get(e["owner"], 0) + 1
            fi += 1
        after = {n["id"]: n.get("left") or 0 for n in b["nodes"]}
        for nid, n in nodes.items():
            drop = (n.get("left") or 0) - after.get(nid, 0)
            if drop <= 0:
                continue
            who = near.get(nid)
            if not who:
                unattr += drop
                continue
            tot = sum(who.values())
            for o, c in who.items():
                taken[o][region(n["x"], n["z"], tc0[o], tc0[other[o]])] += drop * c / tot
        series.append([round(b["t"]), {o: round(sum(taken[o].values())) for o in pids}])
    start = {o: {r: 0.0 for r in regions} for o in pids}
    for n in snaps[0]["nodes"]:
        if n["x"] is not None and n["type"] in ("berry", "deer", "boar", "sheep") and (n.get("left") or 0) > 0:
            for o in pids:
                start[o][region(n["x"], n["z"], tc0[o], tc0[other[o]])] += n["left"]
    return {"taken": {str(o): {r: round(v) for r, v in d.items()} for o, d in taken.items()},
            "start": {str(o): {r: round(v) for r, v in d.items()} for o, d in start.items()},
            "unattributed": round(unattr), "series": series}


def economy(tl, costs_full):
    E = load_econ()
    frames, snaps = tl["frames"], tl.get("nodes") or []
    pl = {p["idx"]: p for p in tl["players"]}
    start_ids = {e["id"] for e in frames[0]["entities"]}
    tc0 = {o: next(((e["x"], e["z"]) for e in frames[0]["entities"]
                    if e["owner"] == o and "town_center" in (e["bp"] or "") and e["x"] is not None), None) for o in pl}
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        bought = {o: [] for o in pl}
    snap_grids = {}

    def food_grid(i):
        if i not in snap_grids:
            snap_grids.clear()
            snap_grids[i] = _grid([(n["x"], n["z"], _food_kind(n)) for n in snaps[i]["nodes"]
                                   if n["x"] is not None and _food_kind(n) and (n.get("left") is None or n["left"] > 0)])
        return snap_grids[i]
    out = {}
    for o in pl:
        civ = pl[o]["civ"]
        code = civ_code(tl, o)
        rates = dict(E["rates"], **(E["civRates"].get(civ) or {}))
        techs = sorted(((x["done"], x["attrib"]) for x in bought.get(o, [])), key=lambda x: x[0])

        def mult(t):
            m = {"food": 1.0, "hunt": 1.0, "berry": 1.0, "farm": 1.0, "wood": 1.0, "gold": 1.0, "stone": 1.0}
            for done, at in techs:
                if done > t:
                    break
                eff = E["techMultipliers"].get(at)
                if eff and "byCiv" in eff:
                    eff = eff["byCiv"].get(code) or next(iter(eff["byCiv"].values()))
                for k, v in (eff or {}).items():
                    m[k] *= v
            return m

        def src_rate(s, m):
            if s in ("deer", "boar"):
                return rates[s] * m["food"] * m["hunt"]
            if s == "berry":
                return rates["berry"] * m["food"] * m["berry"]
            if s == "farm":
                return rates["farm"] * m["food"] * m["farm"]
            if s == "sheep":
                return rates["sheep"] * m["food"]
            if s == "fish":
                return rates["shore_fish"] * m["food"]
            return 0.0
        # spending per resource (for measured income) and the investments
        spent_at, invest, seen, farms_built = [], [], set(), []
        for fr in frames:
            for e in fr["entities"]:
                if e["owner"] != o or e["id"] in seen:
                    continue
                seen.add(e["id"])
                if e["id"] in start_ids or is_free(e["bp"]):
                    continue
                c = costs_full.get(resolve(e["bp"], costs_full) or "") if e["bp"] else None
                if not c:
                    continue
                spent_at.append((fr["t"], {r: c.get(r) or 0 for r in RES}))
                bp, tot = e["bp"], sum(c.get(r) or 0 for r in RES)
                if bp.startswith("building_resource_farm"):
                    farms_built.append((fr["t"], tot))
                if e["kind"] == "o" and tc0[o] and e["x"] is not None:
                    if any(k in bp for k in DROP_FWD) and math.dist((e["x"], e["z"]), tc0[o]) > BASE_R:
                        invest.append((fr["t"], "drop", tot, c.get("name") or bp))
                    elif any(k in bp for k in DEFENCE):
                        invest.append((fr["t"], "defence", tot, c.get("name") or bp))
        for x in bought.get(o, []):
            if x.get("res"):
                spent_at.append((x["t"], {r: x["res"].get(r, 0) for r in RES}))
        spent_at.sort(key=lambda x: x[0])
        b0 = {r: (frames[0]["players"].get(str(o)) or {}).get("bank", {}).get(r) or 0.0 for r in RES}

        si, spent = 0, {r: 0.0 for r in RES}
        ii, inv = 0, {"drop": 0.0, "defence": 0.0}
        cum = {"premium": 0.0, "mapPremium": 0.0, "farm": 0.0}
        vs = {s: 0.0 for s in SOURCES}             # villager-seconds per food source
        vs_res = {r: 0.0 for r in RES}
        vs_map = 0.0
        nominal = {r: 0.0 for r in RES}
        series, win_marks = [], []
        recent, farm_major = [], None            # (t, farm vil-s, food vil-s) for the trailing minute
        for k in range(0, len(frames), STEP):
            fr = frames[k]
            t = fr["t"]
            dt = (frames[min(k + STEP, len(frames) - 1)]["t"] - t) or STEP
            m = mult(t)
            snap_i = _snap_index(snaps, t)
            g = food_grid(snap_i) if snap_i >= 0 else {}
            farms = _grid([(e["x"], e["z"], "farm") for e in fr["entities"] if e["owner"] == o and e["x"] is not None
                           and (e["bp"] or "").startswith("building_resource_farm")])
            sheep = _grid([(sh[2], sh[3], "sheep") for sh in fr.get("sheep_o", []) if sh[1] == o])
            row_farm = 0
            for e in fr["entities"]:
                if e["owner"] != o or e["kind"] != "w" or e["x"] is None:
                    continue
                r = {1: "food", 2: "wood", 3: "gold", 4: "stone"}.get(e.get("res"))
                if not r:
                    continue
                vs_res[r] += dt
                if r != "food":
                    nominal[r] += dt * rates[r] * m[r]
                    continue
                s = "other"
                if _near(farms, e["x"], e["z"], FARM_R):
                    s = "farm"
                else:
                    n = _near(g, e["x"], e["z"], REACH)
                    if n:
                        s = n[2]
                    elif _near(sheep, e["x"], e["z"], SHEEP_R):
                        s = "sheep"
                vs[s] += dt
                row_farm += s == "farm"
                rate = src_rate(s, m)
                nominal["food"] += dt * rate
                if s == "farm":
                    cum["farm"] += dt * rate
                if s in ("deer", "boar"):
                    prem = dt * (rate - src_rate("farm", m))
                    cum["premium"] += prem
                    if tc0[o] and math.dist((e["x"], e["z"]), tc0[o]) > BASE_R:
                        cum["mapPremium"] += prem
                        vs_map += dt
            ff = sum(1 for e in fr["entities"] if e["owner"] == o and e["kind"] == "w" and e.get("res") == 1)
            recent.append((t, row_farm, ff))
            recent = [x for x in recent if t - x[0] <= 60]
            if farm_major is None and t >= 180:
                fs, fa = sum(x[1] for x in recent), sum(x[2] for x in recent)
                if fa >= 10 and fs >= 0.5 * fa:
                    farm_major = round(t)
            while si < len(spent_at) and spent_at[si][0] <= t:
                for r, v in spent_at[si][1].items():
                    spent[r] += v or 0
                si += 1
            while ii < len(invest) and invest[ii][0] <= t:
                inv[invest[ii][1]] += invest[ii][2]
                ii += 1
            bank = (fr["players"].get(str(o)) or {}).get("bank", {})
            measured = {r: (bank.get(r) or 0.0) - b0[r] + spent[r] for r in RES}
            row = {"t": round(t), "measured": {r: round(v) for r, v in measured.items()},
                   "nominal": {r: round(v) for r, v in nominal.items()},
                   "premium": round(cum["premium"]), "mapPremium": round(cum["mapPremium"]), "farm": round(cum["farm"]),
                   "drop": round(inv["drop"]), "defence": round(inv["defence"]),
                   "vs": {s: round(v) for s, v in vs.items()}, "vsRes": {r: round(v) for r, v in vs_res.items()},
                   "vsMap": round(vs_map)}
            series.append(row)
        # windows: per minute rates and efficiency
        def at(T):
            return min(series, key=lambda x: abs(x["t"] - T)) if series else None
        wins = []
        for a, b in WINDOWS:
            ra, rb = at(a), at(b)
            if not ra or not rb or rb["t"] <= ra["t"] or abs(rb["t"] - b) > STEP * 2:
                wins.append(None)
                continue
            span = (rb["t"] - ra["t"]) / 60
            w = {"res": {}}
            for r in RES:
                meas = (rb["measured"][r] - ra["measured"][r]) / span
                nom = (rb["nominal"][r] - ra["nominal"][r]) / span
                vils = (rb["vsRes"][r] - ra["vsRes"][r]) / (span * 60)
                w["res"][r] = {"vils": round(vils, 1), "nominal": round(nom), "measured": round(meas),
                               "eff": round(meas / nom, 2) if nom > 30 else None}
            food_vs = sum(rb["vs"][s] - ra["vs"][s] for s in SOURCES) or 1
            w["food"] = {s: round((rb["vs"][s] - ra["vs"][s]) / food_vs, 2) for s in SOURCES}
            w["mapHunt"] = round((rb["vsMap"] - ra["vsMap"]) / food_vs, 2)
            w["premium"] = rb["premium"] - ra["premium"]
            wins.append(w)
        last = series[-1] if series else {}
        tot_vs = sum((last.get("vs") or {}).values()) or 1
        out[str(o)] = {
            "windows": wins,
            "foodSplit": {s: round(v / tot_vs, 2) for s, v in (last.get("vs") or {}).items()},
            "mapHunt": round((last.get("vsMap") or 0) / tot_vs, 2),
            "premium": last.get("premium", 0), "mapPremium": last.get("mapPremium", 0),
            "drop": last.get("drop", 0), "defence": last.get("defence", 0),
            "net": last.get("premium", 0) - last.get("drop", 0) - last.get("defence", 0),
            "invest": [[round(t), k, round(c), n] for t, k, c, n in invest],
            "series": [[r["t"], r["premium"], r["mapPremium"], r["drop"] + r["defence"], r["measured"]["food"],
                        sum(r["measured"].values()), r["farm"]] for r in series[::5]],
            "techs": [[round(d), a] for d, a in techs if E["techMultipliers"].get(a)],
            "farms": {"first": round(farms_built[0][0]) if farms_built else None, "majority": farm_major,
                      "by": {str(T): [sum(1 for t, _ in farms_built if t <= T), round(sum(c for t, c in farms_built if t <= T))]
                             for T in (600, 900, 1200)}},
        }
    nat = natural_food(tl, tc0)
    if nat:
        for o in out:
            out[o]["natural"] = {"taken": nat["taken"][o], "start": nat["start"][o], "unattributed": nat["unattributed"]}
            out[o]["naturalSeries"] = [[t, d.get(int(o), 0)] for t, d in nat["series"][::2]]
    # where their food came from: natural (taken, above), farms (farm villager-time x farm rate), and the
    # rest = food gathered minus both: passive and non-villager food (Malian cattle, Mongol pastures, fishing
    # boats, trade, ...) plus whatever the two estimates miss
    for o, d in out.items():
        last = d["series"][-1] if d["series"] else None
        if not last:
            continue
        natv = sum((d.get("natural") or {}).get("taken", {}).values())
        d["foodSources"] = {"total": last[4], "natural": natv, "farm": last[6],
                            "other": max(0, last[4] - natv - last[6])}
    return out
