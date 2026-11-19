"""Ideal army against the enemy army the observer has seen, for the observer's own army budget.

Damage per second of unit a on unit b: max(1, damage + bonus(b's classes) - b's armor of the
weapon's type) / attack interval. Army strength (Lanchester square law): D * H, where
D = sum over own units of dps against the seen enemy mix (weighted by the enemy's HP share)
and H = own total HP. Matchup = own strength vs them / their strength vs us (the enemy's
damage depends on our mix too). Ideal: the single type or pair of types with the best matchup
for the same resource budget. Effectiveness = own matchup / ideal matchup.
Candidates: own civ's land military at or below the observer's current age, at the tier the
observer already fields (no assumed upgrades). Not modelled: range, kiting, charges,
upgrades, terrain, production buildings.

Enemy army: enemy military seen in the last ENEMY_MEMORY s, minus those seen dying.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedata import class_match, resolve  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENEMY_MEMORY, STEP = 60.0, 5.0
EXCLUDE = {"naval_unit", "ship", "siege", "monk", "hero", "worker", "scout"}   # exact class names


def load_units():
    with open(os.path.join(HERE, "..", "data", "units.json")) as fh:
        return json.load(fh)["units"]


def dps(a, b):
    w = a.get("w")
    if not w or not w.get("dmg"):
        return 0.0                      # no weapon (traders, monks, some ships - data-main 2026-11)
    bonus = sum(v for cls_lists, v in (w.get("mods") or [])
                if any(class_match(cl, set(b.get("classes") or [])) for cl in cls_lists))
    arm = (b.get("armor") or {}).get(w.get("type"), 0) if w.get("type") in ("melee", "ranged") else 0
    return max(1.0, w["dmg"] + bonus - arm) / max(0.1, w.get("speed") or 1.0)


def strength(comp, enemy, U):
    """comp, enemy: {attribName: count}"""
    eh = sum((U[k].get("hp") or 0) * n for k, n in enemy.items())
    if eh <= 0:
        return 0.0
    D = sum(n * sum(dps(U[k], U[j]) * (U[j].get("hp") or 0) * m / eh for j, m in enemy.items()) for k, n in comp.items())
    H = sum((U[k].get("hp") or 0) * n for k, n in comp.items())
    return D * H


def best_mix(cands, enemy, budget, U):
    best, bs = {}, 0.0
    for i, a in enumerate(cands):
        for b in cands[i:]:
            for f in [x / 10 for x in range(0, 11)] if a != b else [1.0]:
                comp = {}
                na = int(budget * f // U[a]["cost"])
                nb = int(budget * (1 - f) // U[b]["cost"]) if a != b else 0
                if na:
                    comp[a] = na
                if nb:
                    comp[b] = comp.get(b, 0) + nb
                if not comp:
                    continue
                se = strength(enemy, comp, U)
                s = strength(comp, enemy, U) / se if se else float("inf")
                if s > bs:
                    best, bs = comp, s
    return best, bs


def counters(tl, deaths):
    U = load_units()
    frames = tl["frames"]
    # game blueprint names that differ from the data: alias them to the data entry
    seen_bps = {e["bp"] for fr in frames for e in fr["entities"] if e["bp"]}
    for bp in seen_bps:
        if bp not in U:
            k = resolve(bp, U)
            if k:
                U[bp] = U[k]
    pids = [p["idx"] for p in tl["players"]]
    dead_seen = {}                      # observer -> {id: t}
    for d in deaths:
        for o in pids:
            if d["owner"] == o or (d["vis"] >> (o - 1)) & 1:
                dead_seen.setdefault(o, {})[d["id"]] = d["t"]

    def civ_codes(p):
        codes = {}
        for fr in frames[:30]:
            for e in fr["entities"]:
                if e["owner"] == p and e["bp"] in U:
                    for c in U[e["bp"]]["civs"] or []:
                        codes[c] = codes.get(c, 0) + 1
        return max(codes, key=codes.get) if codes else None

    pool = {}
    for p in pids:
        code = civ_codes(p)
        pool[p] = [k for k, v in U.items() if code in (v["civs"] or []) and "land_military" in v["classes"]
                   and not EXCLUDE.intersection(v["classes"]) and v["cost"] > 0]
    out = {}
    for o in pids:
        for p in pids:
            if p == o:
                continue
            last_seen, fielded, rows, next_t = {}, {}, [], frames[0]["t"]
            for fr in frames:
                t = fr["t"]
                bit = 1 << (o - 1)
                for e in fr["entities"]:
                    if e["kind"] != "m" or e["bp"] not in U:
                        continue
                    if e["owner"] == p and e["vis"] and e["vis"] & bit:
                        last_seen[e["id"]] = (t, e["bp"])
                    elif e["owner"] == o:
                        b = U[e["bp"]]["base"]
                        fielded[b] = max(fielded.get(b, 0), U[e["bp"]]["age"] or 0)
                if t < next_t:
                    continue
                next_t = t + STEP
                dead = dead_seen.get(o, {})
                enemy = {}
                for i, (ts, bp) in last_seen.items():
                    if t - ts <= ENEMY_MEMORY and not (i in dead and dead[i] <= t):
                        enemy[bp] = enemy.get(bp, 0) + 1
                mine = {}
                for e in fr["entities"]:
                    if e["owner"] == o and e["kind"] == "m" and e["bp"] in U and U[e["bp"]]["cost"] > 0:
                        mine[e["bp"]] = mine.get(e["bp"], 0) + 1
                budget = sum(U[k]["cost"] * n for k, n in mine.items())
                age = fr["players"].get(str(o), fr["players"].get(o, {})).get("age") or 4
                cands = {}
                for k in pool[o]:
                    v = U[k]
                    if (v["age"] or 1) > age:
                        continue
                    tier = fielded.get(v["base"])
                    cur = cands.get(v["base"])
                    # the tier already fielded; otherwise the lowest tier available
                    if tier is not None:
                        if v["age"] == tier or (cur is None and (v["age"] or 1) <= tier):
                            cands[v["base"]] = k
                    elif cur is None or (v["age"] or 1) < (U[cur]["age"] or 1):
                        cands[v["base"]] = k
                row = {"t": t, "budget": budget,
                       "enemy": {U[k]["name"]: n for k, n in enemy.items()},
                       "mine": {U[k]["name"]: n for k, n in mine.items()}}
                if enemy and budget > 0:
                    ideal, s_ideal = best_mix(list(cands.values()), enemy, budget, U)
                    s_enemy = strength(enemy, mine, U)
                    m_mine = strength(mine, enemy, U) / s_enemy if s_enemy else None
                    row.update({"ideal": {U[k]["name"]: n for k, n in ideal.items()},
                                "eff": round(m_mine / s_ideal, 3) if m_mine is not None and s_ideal not in (0, float("inf")) else None,
                                # Lanchester: matchup ratio > 1 means this army wins; sqrt = share of strength
                                "vs": round(m_mine ** 0.5, 2) if m_mine is not None else None})
                rows.append(row)
            out[f"{o}->{p}"] = rows
    return out
