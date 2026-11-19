"""Three lenses on one game (owner 2026-10-27), built on basics.py's per-frame rows:

1. Hindsight from true values: what happened, with full information.
2. Foresight from true values: at a moment, the true state projected forward (what was coming).
3. Inference: what one player could know from what they saw (no hidden data; observer = each player in turn).

Sources for the rules: three podcast transcripts the owner supplied (MSN on closing games, Myriad on Castle Age,
TeamTriangle on Feudal). Thresholds are first guesses.
"""
import math
import re

from fights import cluster
from gamedata import resolve

RES = ("food", "wood", "gold", "stone")
RES_ID = {1: "food", 2: "wood", 3: "gold", 4: "stone"}
SUPPORT = ("scout", "monk", "prelate", "imam", "scholar", "priest", "shaman", "dervish")
STD_AGE_COST = {1: {"food": 400, "gold": 200}, 2: {"food": 1200, "gold": 600}, 3: {"food": 2400, "gold": 1200}}
NATURAL_FOOD = ("berry", "deer", "boar", "sheep", "carcass", "fish")
REACH = 8.0            # map units: villager on a node
RAID_R = 25.0          # my army unit this close to one of their villagers on their half = pressure
RAID_GAP = 15.0        # s: pressure frames this close belong to one episode
RAID_MIN = 3.0         # s
DIVE_R = 35.0          # a fight this close to their TC / keep = a dive
AFTER = 120.0          # s: lead measured again this long after a dive
EVERY = 30.0           # s: foresight / inference sample step
IDLE_ARMY_MIN = 60.0   # s
PUSH_SHARE = 0.5       # share of my army value in their third = a push
PUSH_MIN = 300.0       # army value
FARM_HORIZON = 3.0     # min: farm-switch risk only when the worked natural food is this close to running out
RAID_SHARE = 0.5       # an episode with less than this share of my army value is a raid, else a push


def _is_army(e):
    return e["kind"] == "m" and not any(s in (e["bp"] or "") for s in SUPPORT)


def _vis(e, p):
    return bool(e.get("vis")) and bool(e["vis"] & (1 << (p - 1)))


def _thirds(a, b):
    """Map thirds along the line between the two starting TCs (Myriad): s < 1/3 a's, > 2/3 b's."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz or 1.0

    def f(x, z):
        s = ((x - a[0]) * dx + (z - a[1]) * dz) / L2
        return "mine" if s < 1 / 3 else "theirs" if s > 2 / 3 else "middle"
    return f


def _rate(R, i, span=60.0, res=None):
    """Gathered per minute over the last `span` s (one resource or all)."""
    j = i
    while j > 0 and R[i]["t"] - R[j]["t"] < span:
        j -= 1
    dt = R[i]["t"] - R[j]["t"]
    if dt <= 0:
        return 0.0
    g = (lambda r: R[r]["gathered"][res]) if res else (lambda r: sum(R[r]["gathered"].values()))
    return (g(i) - g(j)) / dt * 60


def _at(R, t):
    lo, hi = 0, len(R) - 1
    while lo < hi:
        m = (lo + hi) // 2
        if R[m]["t"] < t:
            lo = m + 1
        else:
            hi = m
    return lo


def _speeds(frames):
    """Measured top speed per blueprint (90th percentile of per-second moves while flagged moving), units/s."""
    last, mv = {}, {}
    for fr in frames:
        now = {}
        for e in fr["entities"]:
            if e["kind"] != "m" or e["x"] is None:
                continue
            now[e["id"]] = (fr["t"], e["x"], e["z"])
            prev = last.get(e["id"])
            if prev and "M" in (e.get("flags") or "") and 0 < fr["t"] - prev[0] <= 1.5:
                mv.setdefault(e["bp"], []).append(math.dist(prev[1:], (e["x"], e["z"])) / (fr["t"] - prev[0]))
        last = now
    out = {}
    for bp, v in mv.items():
        if len(v) >= 10:
            v.sort()
            out[bp] = v[int(len(v) * 0.9)]
    return out


# ================================================================ 1. hindsight (true values)
def _idle_production(frames, R, p, costs_full, prod):
    """Production buildings with an empty queue while the bank could pay for the cheapest unit this player made
    there during the game ('could pay'), or while housed (pop >= cap). Buildings under construction skipped."""
    base_of = prod.get("buildingBase") or {}
    made_by = prod.get("units") or {}
    start = {e["id"] for e in frames[0]["entities"]}
    made, seen = set(), set()
    for fr in frames:
        for e in fr["entities"]:
            if e["owner"] == p and e["kind"] in ("w", "m") and e["id"] not in seen:
                seen.add(e["id"])
                if e["id"] not in start:
                    k = resolve(e["bp"], made_by)
                    if k:
                        made.add(k)
    cheapest = {}
    for k in made:
        c = costs_full.get(resolve(k, costs_full) or "")
        if not c:
            continue
        if any(x in k for x in SUPPORT) or not (c.get("military") or c.get("worker")):
            continue                                    # scouts, monks, prelates: not the building's job here
        cost = {r: float(c.get(r) or 0) for r in RES}
        for b in made_by.get(k) or []:
            if b not in cheapest or sum(cost.values()) < sum(cheapest[b][1].values()):
                cheapest[b] = (c.get("name") or k, cost)
    agg = {}
    for i, fr in enumerate(frames):
        row = R[min(i, len(R) - 1)]
        pl = fr["players"].get(str(p)) or fr["players"].get(p) or {}
        housed = (pl.get("pop") or 0) >= (pl.get("popcap") or 1e9)
        dt = (frames[i + 1]["t"] - fr["t"]) if i + 1 < len(frames) else 1.0
        if dt > 3:
            continue
        for e in fr["entities"]:
            if e["owner"] != p or e["kind"] != "o" or e.get("queue") is None:
                continue
            if e.get("build") is not None and (e.get("build") or 0) < 1:
                continue
            base = base_of.get(resolve(e["bp"], base_of) or "")
            if base not in cheapest or "landmark" in (e["bp"] or ""):
                continue
            a = agg.setdefault(base, {"name": base.replace("-", " "), "unit": cheapest[base][0], "secs": 0.0,
                                      "couldPay": 0.0, "housed": 0.0, "byAge": {}})
            a["secs"] += dt
            if e["queue"] > 0:
                continue
            if housed:
                a["housed"] += dt
            elif all(row["bank"][r] >= v for r, v in cheapest[base][1].items()):
                a["couldPay"] += dt
                ag = str(row.get("age") or "?")
                a["byAge"][ag] = a["byAge"].get(ag, 0) + dt
    return [{"name": a["name"], "unit": a["unit"], "secs": round(a["secs"]), "couldPay": round(a["couldPay"]),
             "housed": round(a["housed"]), "byAge": {k: round(v) for k, v in a["byAge"].items()}}
            for a in sorted(agg.values(), key=lambda a: -a["couldPay"])]


def _raids(frames, p, o, R, Q, deaths, tc0, cost_of):
    """Pressure episodes: one of my army units within RAID_R of their villager on their half (closer to their
    starting TC). Per episode: their villagers killed, my army lost there, villager time they lost to idle /
    garrison above their usual level, valued at their true income per villager."""
    me, them = tc0[p], tc0[o]
    act = []
    for fr in frames:
        mine = [(e["x"], e["z"], e["id"], e["bp"]) for e in fr["entities"]
                if e["owner"] == p and _is_army(e) and e["x"] is not None]
        if not mine:
            continue
        hit = set()
        for e in fr["entities"]:
            if e["owner"] != o or e["kind"] != "w" or e["x"] is None:
                continue
            if math.dist((e["x"], e["z"]), them) > math.dist((e["x"], e["z"]), me):
                continue
            for x, z, i, bp in mine:
                if abs(x - e["x"]) <= RAID_R and abs(z - e["z"]) <= RAID_R and math.dist((x, z), (e["x"], e["z"])) <= RAID_R:
                    hit.add((i, bp))
        if hit:
            act.append((fr["t"], hit))
    eps = []
    for t, hit in act:
        if eps and t - eps[-1]["t1"] <= RAID_GAP:
            eps[-1]["t1"] = t
            eps[-1]["units"] |= hit
        else:
            eps.append({"t0": t, "t1": t, "units": set(hit)})
    eps = [e for e in eps if e["t1"] - e["t0"] >= RAID_MIN]

    def stopped(fr):
        return sum(1 for e in fr["entities"] if e["owner"] == o and e["kind"] == "w" and (e.get("idle") or e.get("garrisoned")))
    ft = [fr["t"] for fr in frames]
    out = []
    for ep in eps:
        t0, t1 = ep["t0"], ep["t1"]
        i0, i1 = _at(R, t0), _at(R, t1 + 10)
        base_fr = [frames[k] for k in range(len(frames)) if t0 - 60 <= ft[k] < t0]
        base = sum(stopped(f) for f in base_fr) / len(base_fr) if base_fr else 0.0
        forced = sum(max(0.0, stopped(frames[k]) - base) for k in range(len(frames)) if t0 <= ft[k] <= t1 + 10)
        qi = min(_at(Q, t0), len(Q) - 1)
        vils = sum(Q[qi]["vil"].values()) or 1
        per_vil_s = _rate(Q, qi, 120.0) / 60 / vils
        killed = [d for d in deaths if d["owner"] == o and d["kind"] == "w" and t0 <= d["t"] <= t1 + 5]
        lost = [d for d in deaths if d["owner"] == p and d["kind"] == "m" and t0 <= d["t"] <= t1 + 5
                and math.dist((d["x"], d["z"]), them) <= math.dist((d["x"], d["z"]), me)]
        kv = sum(d["cost"] or 0 for d in killed)
        lv = sum(d["cost"] or 0 for d in lost)
        fv = forced * per_vil_s
        army_value = max(R[k]["army"] for k in range(i0, max(i0 + 1, min(i1 + 1, len(R))))) or 1
        names = {}
        for _, bp in ep["units"]:
            n = re.sub(r"^unit_|_\d.*$", "", bp or "?").replace("_", " ")
            names[n] = names.get(n, 0) + 1
        share = sum(cost_of(bp) for _, bp in ep["units"]) / army_value
        out.append({"t0": round(t0), "t1": round(t1), "units": names, "kind": "raid" if share < RAID_SHARE else "push",
                    "share": round(min(1.0, share), 2),
                    "vilKilled": len(killed), "killedValue": round(kv), "lostValue": round(lv),
                    "forcedSecs": round(forced), "forcedValue": round(fv),
                    "net": round(kv + fv - lv), "unitsForVillagers": share < RAID_SHARE and lv > kv + fv and lv > 0})
    return out


def _landmark_builds(R, Q, landmarks, deaths, p, o):
    """Each of my age-up landmarks: placed -> next age reached; army lost by each side meanwhile."""
    out = []
    for L in landmarks:
        if L.get("cancelled") or not L.get("age"):
            continue
        i = _at(R, L["t"])
        done = next((r["t"] for r in R[i:] if (r.get("age") or 0) >= L["age"] + 1), None)
        t1 = done if done is not None else R[-1]["t"]
        lost = {who: sum(d["cost"] or 0 for d in deaths if d["owner"] == who and d["kind"] == "m" and L["t"] <= d["t"] <= t1)
                for who in (p, o)}
        qi = min(_at(Q, L["t"]), len(Q) - 1)
        out.append({"t": round(L["t"]), "done": round(done) if done is not None else None, "name": L["name"],
                    "age": L["age"], "armyMine": round(R[i]["army"]), "armyTheirs": round(Q[qi]["army"]),
                    "lostMine": round(lost[p]), "lostTheirs": round(lost[o])})
    return out


def _arrivals(frames, R, p, bought, prod, third, cost_of):
    """Per age reached (2, 3): bank on arrival, first production building placed and first military unit after,
    military techs (veterancy, blacksmith) after, and the first push (>= PUSH_SHARE of army value in their third)."""
    base_of = prod.get("buildingBase") or {}
    producers = {b for v in (prod.get("units") or {}).values() for b in v} - {"town-center", "capital-town-center"}
    out = []
    for age in (2, 3):
        i = next((k for k, r in enumerate(R) if (r.get("age") or 0) >= age), None)
        if i is None:
            continue
        t = R[i]["t"]
        nxt = next((r["t"] for r in R[i:] if (r.get("age") or 0) > age), R[-1]["t"])
        first_b = first_u = push = None
        seen = {e["id"] for e in frames[min(i, len(frames) - 1)]["entities"]}
        for fr in frames[i:]:
            if fr["t"] > nxt:
                break
            av, far = 0.0, 0.0
            for e in fr["entities"]:
                if e["owner"] != p:
                    continue
                if e["id"] not in seen:
                    seen.add(e["id"])
                    bb = base_of.get(resolve(e["bp"], base_of) or "")
                    if first_b is None and e["kind"] == "o" and bb in producers and "landmark" not in (e["bp"] or ""):
                        first_b = (fr["t"], bb.replace("-", " "))
                    if first_u is None and _is_army(e):
                        first_u = (fr["t"], e["bp"])
                if _is_army(e) and e["x"] is not None:
                    v = cost_of(e["bp"]) or 1.0
                    av += v
                    if third(e["x"], e["z"]) == "theirs":
                        far += v
            ri = min(_at(R, fr["t"]), len(R) - 1)
            if push is None and R[ri]["army"] >= PUSH_MIN and av and far / av >= PUSH_SHARE:
                push = fr["t"]
        techs = [x for x in bought if t <= x["done"] <= nxt and not re.search(r"econ|town_center|wheelbarrow", x.get("attrib") or "") and re.search(
            r"veteran|elite|hardened|damage|armor|arrow|undermesh|steeled|fitted|chainmail|plate|ballistics|siege",
            (x.get("attrib") or "") + " " + (x.get("name") or ""), re.I)]
        out.append({"age": age, "t": round(t), "bank": {r: round(v) for r, v in R[i]["bank"].items()},
                    "firstBuilding": [round(first_b[0] - t), first_b[1]] if first_b else None,
                    "firstUnit": [round(first_u[0] - t), re.sub(r"^unit_|_\d.*$", "", first_u[1]).replace("_", " ")] if first_u else None,
                    "techs": [[round(x["done"] - t), x["name"]] for x in techs[:8]],
                    "push": round(push - t) if push is not None else None})
    return out


def _dives(frames, trades, R, Q, p, o):
    """Fights within DIVE_R of their TC / keep while I was ahead in gathering, where I lost more value.
    Lead (gathered gap + army gap) before and AFTER s later."""
    out = []
    ft = [fr["t"] for fr in frames]
    for f in trades:
        i = min(range(len(ft)), key=lambda k: abs(ft[k] - f["t0"]))
        strong = [(e["x"], e["z"]) for e in frames[i]["entities"] if e["owner"] == o and e["kind"] == "o"
                  and re.search(r"town_center|keep|landmark", e["bp"] or "") and e["x"] is not None]
        if not strong or min(math.dist((f["x"], f["z"]), s) for s in strong) > DIVE_R:
            continue
        a, b = _at(R, f["t0"]), _at(Q, f["t0"])
        a2, b2 = _at(R, f["t1"] + AFTER), _at(Q, f["t1"] + AFTER)
        g0 = sum(R[a]["gathered"].values()) - sum(Q[b]["gathered"].values())
        g1 = sum(R[a2]["gathered"].values()) - sum(Q[b2]["gathered"].values())
        lead0 = g0 + R[a]["army"] - Q[b]["army"]
        lead1 = g1 + R[a2]["army"] - Q[b2]["army"]
        out.append({"t0": f["t0"], "t1": f["t1"], "lostMine": f["lost"][str(p)], "lostTheirs": f["lost"][str(o)],
                    "aheadBefore": g0 > 0, "gatheredGap": [round(g0), round(g1)], "lead": [round(lead0), round(lead1)],
                    "flag": g0 > 0 and f["lost"][str(p)] > f["lost"][str(o)] and lead1 < lead0})
    return out


def _splits(frames, R, landmarks, p, prod):
    """Villager split when this player placed each age-up landmark (TeamTriangle's read: gold-heavy + tower = fast
    Castle, wood-heavy = production, stone = second TC), then what they actually did in the next 180 s."""
    base_of = prod.get("buildingBase") or {}
    producers = {b for v in (prod.get("units") or {}).values() for b in v} - {"town-center", "capital-town-center"}
    out = []
    for L in landmarks:
        if L.get("cancelled"):
            continue
        i = _at(R, L["t"])
        v = R[i]["vil"]
        read = "2nd TC?" if v["stone"] >= 3 else "fast Castle?" if v["gold"] > v["wood"] else "production?"
        then = {"tc": None, "towers": 0, "production": 0, "next": None}
        seen = {e["id"] for e in frames[min(i, len(frames) - 1)]["entities"]}
        for fr in frames[i:]:
            if fr["t"] > L["t"] + 180:
                break
            for e in fr["entities"]:
                if e["owner"] != p or e["id"] in seen:
                    continue
                seen.add(e["id"])
                bp = e["bp"] or ""
                if "town_center" in bp and then["tc"] is None:
                    then["tc"] = round(fr["t"] - L["t"])
                elif re.search(r"tower|outpost", bp):
                    then["towers"] += 1
                elif e["kind"] == "o" and base_of.get(resolve(bp, base_of) or "") in producers:
                    then["production"] += 1
        nxt = next((M for M in landmarks if not M.get("cancelled") and M["t"] > L["t"]), None)
        then["next"] = round(nxt["t"] - L["t"]) if nxt else None
        out.append({"t": round(L["t"]), "age": L["age"], "name": L["name"], "vil": dict(v), "idle": R[i]["idle"],
                    "read": read, "then": then})
    return out


GAP_HALF = 30.0        # s: centred window for the gathering rate (60 s wide)
GAP_MIN_S = 90.0       # s: my rate below theirs at least this long
GAP_BLIP = 10.0        # s: shorter stretches above theirs don't end it
GAP_MIN_RES = 300.0    # gathered gap that must open over the stretch


def _gap_onsets(R, Q, deaths, raids_on_me, p, o, lms_mine, lms_theirs):
    """Where my gathering rate starts falling behind theirs (owner 2026-10-27: "where the resource gathering rate starts
    to be gapped"). Rate = gathered per minute over a centred 60 s window, so the onset is not 30 s late. A stretch:
    my rate below theirs >= GAP_MIN_S (blips above <= GAP_BLIP ignored) and the gathered gap growing >= GAP_MIN_RES.
    At the onset (first 90 s): which resources the gap is in, and how much of it is villager count vs gathered per
    villager (rate = villagers x per-villager rate: count effect = (Nm - Nt) x rt, efficiency effect = Nm x (rm - rt)),
    plus what happened around it."""
    n = min(len(R), len(Q))
    if n < 120:
        return []
    T = [R[k]["t"] for k in range(n)]

    def win(k):
        a, b = k, k
        while a > 0 and T[k] - T[a - 1] <= GAP_HALF:
            a -= 1
        while b < n - 1 and T[b + 1] - T[k] <= GAP_HALF:
            b += 1
        return a, b
    W = [win(k) for k in range(n)]

    def rate(X, k, res=None):
        a, b = W[k]
        dt = T[b] - T[a]
        if dt <= 0:
            return 0.0
        g = (lambda i: X[i]["gathered"][res]) if res else (lambda i: sum(X[i]["gathered"].values()))
        return (g(b) - g(a)) / dt * 60
    d = [rate(R, k) - rate(Q, k) for k in range(n)]
    out, k = [], 0
    while k < n:
        if d[k] >= 0 or T[k] < 60:
            k += 1
            continue
        j, last_neg = k, k
        while j < n and (d[j] < 0 or T[j] - T[last_neg] <= GAP_BLIP):
            if d[j] < 0:
                last_neg = j
            j += 1
        j = last_neg
        gm = lambda X, i: sum(X[i]["gathered"].values())  # noqa: E731
        opened = (gm(Q, j) - gm(Q, k)) - (gm(R, j) - gm(R, k))
        if T[j] - T[k] >= GAP_MIN_S and opened >= GAP_MIN_RES:
            e = min(n - 1, _at(R, T[k] + 90))
            m = max(1, e - k)
            Nm = sum(sum(R[i]["vil"].values()) for i in range(k, e)) / m
            Nt = sum(sum(Q[i]["vil"].values()) for i in range(k, e)) / m
            im = sum(R[i]["idle"] for i in range(k, e)) / m
            it = sum(Q[i]["idle"] for i in range(k, e)) / m
            gm_ = (gm(R, e) - gm(R, k)) / max(1e-6, T[e] - T[k]) * 60
            gt_ = (gm(Q, e) - gm(Q, k)) / max(1e-6, T[e] - T[k]) * 60
            rm, rt = gm_ / max(1e-6, Nm), gt_ / max(1e-6, Nt)
            count_eff, eff_eff = (Nm - Nt) * rt, Nm * (rm - rt)
            by_res = {}
            for r in RES:
                a_ = (R[e]["gathered"][r] - R[k]["gathered"][r]) - (Q[e]["gathered"][r] - Q[k]["gathered"][r])
                by_res[r] = round(a_ / max(1e-6, T[e] - T[k]) * 60)
            near = []
            lost = sum(1 for x in deaths if x["owner"] == p and x["kind"] == "w" and T[k] - 60 <= x["t"] <= T[e])
            if lost:
                near.append(f"{lost} own villagers killed")
            for x in raids_on_me:
                if T[k] - 60 <= x["t0"] <= T[e]:
                    near.append(f"opponent's {x['kind']} at {int(x['t0']) // 60}:{int(x['t0']) % 60:02d} ({x['forcedSecs']} villager-s idle forced)")
            grow_m = sum(R[e]["vil"].values()) - sum(R[max(0, _at(R, T[k] - 60))]["vil"].values())
            grow_t = sum(Q[e]["vil"].values()) - sum(Q[max(0, _at(Q, T[k] - 60))]["vil"].values())
            if grow_m < grow_t:
                near.append(f"villagers {grow_m:+} vs opponent {grow_t:+} (from 1 min before)")
            if im - it >= 1:
                near.append(f"{im:.1f} own villagers idle on average (opponent {it:.1f})")
            for L in lms_mine:
                if not L.get("cancelled") and T[k] - 60 <= L["t"] <= T[e]:
                    near.append(f"own landmark {L['name']} at {int(L['t']) // 60}:{int(L['t']) % 60:02d}")
            for L in lms_theirs:
                if not L.get("cancelled") and T[k] - 60 <= L["t"] <= T[e]:
                    near.append(f"opponent's landmark {L['name']} at {int(L['t']) // 60}:{int(L['t']) % 60:02d}")
            out.append({"t0": round(T[k]), "t1": round(T[j]), "opened": round(opened),
                        "rateGap": round(sum(d[k:j + 1]) / max(1, j + 1 - k)),
                        "byRes": by_res, "vils": [round(Nm, 1), round(Nt, 1)], "perVil": [round(rm, 1), round(rt, 1)],
                        "countEffect": round(count_eff), "effEffect": round(eff_eff),
                        "main": "fewer villagers" if abs(count_eff) >= abs(eff_eff) else "less per villager",
                        "near": near})
        k = j + 1
    return out


# ================================================================ 2. foresight (true values)
def _catchup(R, Q):
    """Every EVERY s: minutes they need, at their current income (60 s), to match my army value from their bank
    (MSN: the game is over when they need ~15 min to catch up). 0 = their bank already covers it."""
    out = []
    t = EVERY
    while t <= R[-1]["t"]:
        a, b = _at(R, t), min(_at(Q, t), len(Q) - 1)
        inc = _rate(Q, b)
        need = R[a]["army"] - Q[b]["army"] - sum(Q[b]["bank"].values())
        out.append([round(t), round(max(0.0, need) / inc, 1) if inc > 30 else None])
        t += EVERY
    return out


def _farm_risk(frames, R, clock, p, costs_full, nodes, third):
    """Every EVERY s: minutes of natural food left in my third (all berries / deer / boar / sheep / carcasses there,
    not just the ones being worked) at my current natural-food rate (aggression clock), vs minutes of wood income
    needed to place a farm for each food villager not yet on one. Risk (age 2+) when the safe food runs out first
    (Paper Cut: prepare the farm switch when on your second-to-last safe food in your third)."""
    farm_wood = next((float(c.get("wood") or 75) for k, c in costs_full.items() if "farm" in k and c.get("type") == "building"), 75.0)
    ck = {c["t"]: c for c in clock}
    snap_t = [x["t"] for x in nodes]
    out = []
    t = EVERY
    while t <= R[-1]["t"]:
        i = min(_at(R, t), len(frames) - 1)
        farms = sum(1 for e in frames[i]["entities"] if e["owner"] == p and e["kind"] == "o" and "farm" in (e["bp"] or ""))
        food_v = R[i]["vil"]["food"]
        short = max(0, food_v - farms)
        need = max(0.0, short * farm_wood - R[i]["bank"]["wood"])
        wood_inc = _rate(R, i, 60.0, "wood")
        wood_min = need / wood_inc if wood_inc > 5 else (0.0 if need == 0 else None)
        left = None
        if nodes:
            k = max(0, next((j for j, x in enumerate(snap_t) if x > t), len(snap_t)) - 1)
            left = sum(n.get("left") or 0 for n in nodes[k]["nodes"] if n["x"] is not None and n["type"] in NATURAL_FOOD
                       and n["type"] != "fish" and (n.get("left") or 0) > 0 and third(n["x"], n["z"]) == "mine")
        c = ck.get(round(t))
        rate = c["food"]["perMin"] if c and c.get("food") else 0
        food_min = round(left / rate, 1) if left is not None and rate > 30 else None
        risk = (food_min is not None and food_min <= FARM_HORIZON and short > 0 and (R[i].get("age") or 0) >= 2
                and (wood_min is None or wood_min > food_min))
        out.append({"t": round(t), "foodMin": food_min, "foodLeft": round(left) if left is not None else None,
                    "farms": farms, "foodVils": food_v, "short": short,
                    "woodMin": round(wood_min, 1) if wood_min is not None else None, "risk": risk})
        t += EVERY
    return out


def _age_eta(R, landmarks):
    """Before each age-up landmark: every EVERY s, the earliest click time the true bank + per-resource income
    (60 s) would allow for the standard landmark cost; vs the actual click."""
    out = []
    t_prev = 0.0
    for L in [L for L in landmarks if not L.get("cancelled") and L.get("age") in STD_AGE_COST]:
        need = STD_AGE_COST[L["age"]]
        pts = []
        t = max(EVERY, math.ceil(t_prev / EVERY) * EVERY)
        while t < L["t"]:
            i = _at(R, t)
            eta = 0.0
            for r, v in need.items():
                miss = v - R[i]["bank"][r]
                if miss <= 0:
                    continue
                rate = _rate(R, i, 60.0, r)
                eta = max(eta, miss / rate * 60) if rate > 5 else math.inf
            pts.append([round(t), round(t + eta) if eta != math.inf else None])
            t += EVERY
        out.append({"age": L["age"], "name": L["name"], "click": round(L["t"]), "eta": pts})
        t_prev = L["t"]
    return out


def _idle_army(frames, R, Q, p, third, catch):
    """Stretches >= IDLE_ARMY_MIN where >= 70 % of my army value sat in my third with none of it attacking, while
    their income was above mine (MSN: no 80 units idle in base while they boom). Catch-up minutes at both ends."""
    flags = []
    for i, fr in enumerate(frames):
        v, home, att = 0, 0, False
        for e in fr["entities"]:
            if e["owner"] != p and _is_army(e) and e["x"] is not None and third(e["x"], e["z"]) == "mine":
                att = True                              # they are in my third: defending, not idle
            if e["owner"] == p and _is_army(e) and e["x"] is not None:
                v += 1
                home += third(e["x"], e["z"]) == "mine"
                att = att or "A" in (e.get("flags") or "")
        a, b = min(i, len(R) - 1), min(_at(Q, fr["t"]), len(Q) - 1)
        ok = v >= 5 and home / v >= 0.7 and not att and _rate(Q, b) > _rate(R, a)
        flags.append((fr["t"], ok, R[a]["army"]))
    out, s = [], None
    for t, ok, av in flags + [(math.inf, False, 0)]:
        if ok and s is None:
            s = (t, av)
        elif not ok and s is not None:
            if t - s[0] >= IDLE_ARMY_MIN and t != math.inf or (t == math.inf and flags[-1][0] - s[0] >= IDLE_ARMY_MIN):
                t1 = flags[-1][0] if t == math.inf else t
                c0 = next((c for tt, c in catch if tt >= s[0]), None)
                c1 = next((c for tt, c in catch if tt >= t1), None)
                out.append({"t0": round(s[0]), "t1": round(t1), "army": round(s[1]), "catchup": [c0, c1]})
            s = None
    return out


def _ageup_safety(frames, R, Q, landmarks, p, o, tc0, speeds):
    """At each of my age-up clicks: how long their army (true positions) needs to reach my starting TC at its
    measured speed, vs how long the landmark took to finish."""
    out = []
    for L in landmarks:
        if L.get("cancelled") or not L.get("age"):
            continue
        i = min(_at(R, L["t"]), len(frames) - 1)
        army = [(e["x"], e["z"], e["bp"]) for e in frames[i]["entities"] if e["owner"] == o and _is_army(e) and e["x"] is not None]
        done = next((r["t"] for r in R[_at(R, L["t"]):] if (r.get("age") or 0) >= L["age"] + 1), None)
        if not army:
            out.append({"t": round(L["t"]), "name": L["name"], "reach": None, "build": round(done - L["t"]) if done else None,
                        "armyTheirs": 0})
            continue
        times = sorted(math.dist((x, z), tc0[p]) / max(1.0, speeds.get(bp, 4.5)) for x, z, bp in army)
        reach = times[len(times) // 2]                      # half their army there
        qi = min(_at(Q, L["t"]), len(Q) - 1)
        out.append({"t": round(L["t"]), "name": L["name"], "reach": round(reach), "first": round(times[0]),
                    "build": round(done - L["t"]) if done else None,
                    "armyMine": round(R[_at(R, L["t"])]["army"]), "armyTheirs": round(Q[qi]["army"])})
    return out


# ================================================================ 3. inference (observer = p, about o)
def _infer(frames, p, o, Q, landmarks_o, nodes, cost_of, prod):
    base_of = prod.get("buildingBase") or {}
    producers = {b for v in (prod.get("units") or {}).values() for b in v}
    # their villager split as I saw it (last 60 s, unique villagers, latest resource while visible) at each of their
    # age-up completions (announced to everyone), vs the true split at their click
    seen_res = {}
    splits = []
    done_ts = []
    for L in landmarks_o:
        if L.get("cancelled") or not L.get("age"):
            continue
        i = _at(Q, L["t"])
        d = next((r["t"] for r in Q[i:] if (r.get("age") or 0) >= L["age"] + 1), None)
        if d is not None:
            done_ts.append((d, L, dict(Q[_at(Q, d)]["vil"])))
    # army / production seen vs true, every EVERY s
    army_seen = {}
    bld_seen = {}
    rows = []
    farm_seen = farm_true = None
    k_done = 0
    t_next = EVERY
    for fr in frames:
        t = fr["t"]
        for e in fr["entities"]:
            if e["owner"] != o:
                continue
            if e["kind"] == "o" and "farm" in (e["bp"] or ""):
                farm_true = farm_true or t
                if _vis(e, p):
                    farm_seen = farm_seen or t
            if not _vis(e, p):
                continue
            if e["kind"] == "w" and e.get("res"):
                seen_res[e["id"]] = (t, RES_ID.get(e["res"]))
            elif _is_army(e):
                army_seen[e["id"]] = (t, cost_of(e["bp"]))
            elif e["kind"] == "o" and base_of.get(resolve(e["bp"], base_of) or "") in producers:
                bld_seen[e["id"]] = e["bp"]
        while k_done < len(done_ts) and done_ts[k_done][0] <= t:
            d, L, true_v = done_ts[k_done]
            sv = {r: 0 for r in RES}
            for tt, r in seen_res.values():
                if r and t - tt <= 60:
                    sv[r] += 1
            splits.append({"t": round(d), "name": L["name"], "seen": sv, "true": true_v,
                           "readSeen": "2nd TC?" if sv["stone"] >= 3 else "fast Castle?" if sv["gold"] > sv["wood"] else "production?",
                           "readTrue": "2nd TC?" if true_v["stone"] >= 3 else "fast Castle?" if true_v["gold"] > true_v["wood"] else "production?"})
            k_done += 1
        if t >= t_next:
            ids_now = {e["id"] for e in fr["entities"] if e["owner"] == o}
            sv = sum(v for tt, v in army_seen.values() if t - tt <= 60)
            true_army = sum(cost_of(e["bp"]) for e in fr["entities"] if e["owner"] == o and _is_army(e))
            true_prod = sum(1 for e in fr["entities"] if e["owner"] == o and e["kind"] == "o"
                            and base_of.get(resolve(e["bp"], base_of) or "") in producers)
            rows.append([round(t), round(sv), round(true_army), sum(1 for i in bld_seen if i in ids_now), true_prod])
            t_next += EVERY
    # their villagers starting on a natural food / gold node: did I see them there, and how long after
    arrivals = []
    if nodes:
        snap_t = [s["t"] for s in nodes]
        worked = set()
        first_seen = {}
        si = 0
        for k, fr in enumerate(frames):
            if k % 2:
                continue
            while si + 1 < len(nodes) and snap_t[si + 1] <= fr["t"]:
                si += 1
            vils = [e for e in fr["entities"] if e["owner"] == o and e["kind"] == "w" and e["x"] is not None and e.get("res")]
            if not vils:
                continue
            for n in nodes[si]["nodes"]:
                if n["x"] is None or (n.get("left") or 0) <= 0 or not (n["type"] in NATURAL_FOOD or n["type"] == "gold"):
                    continue
                want = 3 if n["type"] == "gold" else 1
                on = [e for e in vils if e["res"] == want and abs(e["x"] - n["x"]) <= REACH and abs(e["z"] - n["z"]) <= REACH]
                if not on:
                    continue
                if n["id"] not in worked:
                    worked.add(n["id"])
                    arrivals.append({"t": round(fr["t"]), "id": n["id"], "type": n["type"], "x": n["x"], "z": n["z"]})
                if n["id"] not in first_seen and any(_vis(e, p) for e in on):
                    first_seen[n["id"]] = fr["t"]
        # group arrivals within 20 units / 30 s (one deer pack, one berry patch)
        groups = []
        for a in arrivals:
            g = next((g for g in groups if g["type"] == a["type"] and abs(g["t"] - a["t"]) <= 30
                      and math.dist((g["x"], g["z"]), (a["x"], a["z"])) <= 20), None)
            if g:
                g["ids"].append(a["id"])
            else:
                groups.append({**a, "ids": [a["id"]]})
        arrivals = []
        for g in groups:
            fs = [first_seen[i] for i in g["ids"] if i in first_seen]
            arrivals.append({"t": g["t"], "type": g["type"], "x": round(g["x"]), "z": round(g["z"]),
                             "seenAfter": round(min(fs) - g["t"]) if fs else None})
    return {"splits": splits, "farm": {"seen": round(farm_seen) if farm_seen else None,
                                       "true": round(farm_true) if farm_true else None},
            "series": rows, "arrivals": arrivals}


# ================================================================ entry
def lenses(tl, per, deaths, trades, clock, costs_full, cost_of, bought, prod):
    from econ import natural_food
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    if len(pids) != 2:
        return None
    tc0 = {o: next(((e["x"], e["z"]) for e in frames[0]["entities"]
                    if e["owner"] == o and "town_center" in (e["bp"] or "") and e["x"] is not None), None) for o in pids}
    if any(v is None for v in tc0.values()):
        return None
    speeds = _speeds(frames)
    a, b = pids

    def region(x, z, mine, theirs):
        return _thirds(mine, theirs)(x, z)
    nat = natural_food(tl, tc0, region=region, regions=("mine", "middle", "theirs"))
    out = {}
    raids_by = {p: _raids(frames, p, o, per[p]["rows"], per[o]["rows"], deaths, tc0, cost_of) for p, o in ((a, b), (b, a))}
    for p, o in ((a, b), (b, a)):
        R, Q = per[p]["rows"], per[o]["rows"]
        third = _thirds(tc0[p], tc0[o])
        lms = per[p]["landmarks"]
        catch = _catchup(R, Q)
        out[str(p)] = {
            "hindsight": {
                "idleProduction": _idle_production(frames, R, p, costs_full, prod),
                "raids": raids_by[p],
                "landmarkBuilds": _landmark_builds(R, Q, lms, deaths, p, o),
                "arrivals": _arrivals(frames, R, p, bought.get(p, []), prod, third, cost_of),
                "dives": _dives(frames, trades, R, Q, p, o),
                "foodThirds": (nat or {}).get("taken", {}).get(str(p)),
                "foodThirdsStart": (nat or {}).get("start", {}).get(str(p)),
                "splits": _splits(frames, R, lms, p, prod),
                "gapOnsets": _gap_onsets(R, Q, deaths, raids_by[o], p, o, lms, per[o]["landmarks"]),
            },
            "foresight": {
                "catchup": catch,
                "farmRisk": _farm_risk(frames, R, clock.get(p, []), p, costs_full, tl.get("nodes") or [], third),
                "ageEta": _age_eta(R, lms),
                "idleArmy": _idle_army(frames, R, Q, p, third, catch),
                "ageupSafety": _ageup_safety(frames, R, Q, lms, p, o, tc0, speeds),
            },
            "inference": _infer(frames, p, o, Q, per[o]["landmarks"], tl.get("nodes") or [], cost_of, prod),
        }
    return out
