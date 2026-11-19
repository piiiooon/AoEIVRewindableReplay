"""Castle Age timing from the observer's sight (owner, 2026-10-25).

Reference (owner's choice 1c): plain landmark-cost math. From the implied bank and income, when could
they afford the Feudal landmark, build it, then afford and build the Castle landmark:
    income   = rate x estimated villagers - villager production (50 food / 20 s per known TC)
    feudal   = announced, or seen landmark + build time, or now + (feudal cost - bank) / income + build
    castle   = max(feudal done, now + (landmark costs still unpaid - bank) / income) + build time
Delay: the same with every off-path purchase you saw added back to the bank (reference) vs as seen
(projected); delay = projected - reference. Off path = what a straight Feudal -> Castle build doesn't
need: military units, military / defensive buildings, walls, blacksmith, market, religious, extra TCs.
On path: villagers, houses, drop sites, farms, docks, age landmarks, the first TC.
A military unit seen with none of its production buildings seen implies the cheapest one (e.g. a
stable for a horseman), unless one of the civ's landmarks can make it (they may have that landmark).
Everything is a lower bound: spending you didn't see delays them further. Observer knowledge only:
seen entities, public age-up announcements, game data.
"""
import json
import os
import re

from gamedata import resolve, is_free
from techs_bought import civ_code

HERE = os.path.dirname(os.path.abspath(__file__))
LANDMARK_COST = {1: 600, 2: 1800}           # Feudal / Castle landmark, all resources (400f 200g, 1200f 600g)
BUILD_DEFAULT = {1: 190, 2: 220}            # landmark build time, s (aoe4world; per civ in production.json)
VIL_COST, VIL_TIME = 50.0, 20.0
ON_PATH_RE = re.compile(r"house|econ_(food|wood|mining|gold|stone)|mill|lumber|mining_camp|resource_farm|_farm_|"
                        r"granary|dock|fishing|ger_|hunting_cabin|wynguard", re.I)
STEP, HORIZON = 2.0, 1800.0          # projection step and how far ahead it looks, s
VIL_CAP = 100


def load_production():
    with open(os.path.join(HERE, "..", "data", "production.json"), encoding="utf-8") as fh:
        return json.load(fh)


def classify(bp, info):
    """'vil' / 'landmark' / 'tc' / 'on' / 'off' / None (free or unknown)."""
    if is_free(bp) or info is None:
        return None
    if info.get("worker"):
        return "vil"
    if info.get("landmark_age"):
        return "landmark"
    if "town_center" in bp:
        return "tc"
    if info.get("type") == "building" and ON_PATH_RE.search(bp):
        return "on"
    if info.get("type") != "building" and not info.get("military") and re.search(r"fishing|trade|cart|camel_trade", bp):
        return "on"
    return "off"


def castle_forecast(tl, est, events, costs_full, cost_of, rate):
    prod = load_production()
    units, base_of, base_cost = prod["units"], prod["buildingBase"], prod["baseCost"]
    civ = {p["idx"]: p["civ"] for p in tl["players"]}
    frames = tl["frames"]
    # public age-up announcements: player -> {age: time reached}
    reached = {p: {} for p in civ}
    for fr in frames:
        for k, pl in fr["players"].items():
            a, i = pl.get("age"), int(k)
            if a is not None and i in reached and a not in reached[i]:
                reached[i][a] = fr["t"]
    out = {}
    for key, rows in est.items():
        o, p = (int(x) for x in key.split("->"))
        code = civ_code(tl, p)
        lm_time = {a: (prod["landmarkTime"].get(code) or {}).get(str(a)) or BUILD_DEFAULT[a] for a in (1, 2)}
        civ_lms = {b for v in (prod["landmarks"].get(code) or {}).values() for b in v}
        start_age = min(reached[p]) if reached[p] else 1
        seen_base, tcs, items, implied = {"town-center"}, 1, [], set()
        lm_seen = {}                                          # landmark age -> first seen time
        timeline = []                                         # (t, off-path cost) in time order
        for ev in sorted(events.get(key, []), key=lambda e: e["t"]):
            for s in ev.get("saw", []):
                bp, n = s["bp"], s["n"]
                info = costs_full.get(resolve(bp, costs_full) or "")
                cat = classify(bp, info)
                b = base_of.get(bp) or base_of.get(resolve(bp, base_of) or "")
                if b:
                    seen_base.add(b)
                if cat == "landmark":
                    lm_seen.setdefault(info["landmark_age"], ev["t"])
                    continue
                if cat == "tc":
                    tcs += n
                    if tcs - n >= 1:      # every TC beyond the first is off path
                        cat = "off"
                if cat == "off":
                    c = cost_of(bp) * n
                    items.append({"t": ev["t"], "bp": bp, "name": s["name"], "n": n, "cost": round(c)})
                    timeline.append((ev["t"], c))
                # a military unit with none of its producers seen: the cheapest producer is implied
                if info and info.get("military"):
                    pr = units.get(bp) or units.get(resolve(bp, units) or "") or []
                    if pr and not (set(pr) & seen_base) and not (set(pr) & civ_lms):
                        opts = [(base_cost[x][code][1], x, base_cost[x][code][0]) for x in pr
                                if x in base_cost and code in base_cost[x]]
                        if opts:
                            c, x, abp = min(opts)
                            if x not in implied:
                                implied.add(x)
                                seen_base.add(x)
                                nm = (costs_full.get(resolve(abp, costs_full) or "") or {}).get("name") or x.replace("-", " ")
                                items.append({"t": ev["t"], "bp": abp, "name": nm, "n": 1, "cost": round(c),
                                              "implied": s["name"]})
                                timeline.append((ev["t"], c))
        res_rows, j, off = [], 0, 0.0
        tc_t = sorted([e["t"] for e in items if "town_center" in e["bp"]])

        def project(t, bank, n, ntc):
            """Step forward: income = rate x villagers, villagers keep coming from every known TC (50 food
            per 20 s each); Feudal landmark when affordable (unless already paid / reached), built in
            lm_time[1]; then the Castle landmark when affordable, built in lm_time[2]. -> Castle reached."""
            if 2 in lm_seen and lm_seen[2] <= t:
                return lm_seen[2] + lm_time[2]
            if 2 in reached[p] and reached[p][2] <= t or start_age >= 2:
                f_done = reached[p].get(2, t)
            elif 1 in lm_seen and lm_seen[1] <= t:
                f_done = lm_seen[1] + lm_time[1]
            else:
                f_done = None
            tt, end = t, t + HORIZON
            while tt < end:
                if f_done is None and bank >= LANDMARK_COST[1]:
                    bank -= LANDMARK_COST[1]
                    f_done = tt + lm_time[1]
                elif f_done is not None and tt >= f_done and bank >= LANDMARK_COST[2]:
                    return tt + lm_time[2]
                grow = ntc * STEP / VIL_TIME if n < VIL_CAP else 0.0
                bank += rate * n * STEP - grow * VIL_COST
                n += grow
                tt += STEP
            return None
        for r in rows:
            t = r["t"]
            while j < len(timeline) and timeline[j][0] <= t:
                off += timeline[j][1]
                j += 1
            ntc = 1 + sum(1 for x in tc_t if x <= t)
            inc = rate * r["n_est"]
            if 3 in reached[p] and reached[p][3] <= t or start_age >= 3:
                res_rows.append({"t": t, "proj": None, "ref": None, "off": round(off), "inc": round(inc, 1)})
                continue
            if int(t) % 5 and res_rows:          # every 5 s is enough; repeat the last projection between
                last = res_rows[-1]
                res_rows.append(dict(last, t=t, off=round(off), inc=round(inc, 1)))
                continue
            b, n = r["bank_est"], r["n_est"]
            pr, rf = project(t, b, n, ntc), project(t, b + off, n, ntc)
            res_rows.append({"t": t, "proj": None if pr is None else round(pr, 1),
                             "ref": None if rf is None else round(rf, 1), "off": round(off), "inc": round(inc, 1)})
        for it in items:                       # seconds each item adds at the income when it was seen
            r = next((x for x in res_rows if x["t"] >= it["t"]), res_rows[-1] if res_rows else None)
            it["sec"] = round(it["cost"] / max(1.0, r["inc"])) if r else None
        out[key] = {"rows": res_rows, "items": items, "reached": reached[p].get(3),
                    "build": lm_time, "rate": rate}
    return out
