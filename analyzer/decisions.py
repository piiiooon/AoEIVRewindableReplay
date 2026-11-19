"""Decision points for one game, logged in hindsight (review only: full information). Owner 2026-11-10.

Purpose: per civ, from pro games, "in this situation pros did this, and it paid off / didn't", for a player learning
the civ while watching replays. We cannot see into a player's mind: a decision shows only in what they did over the
next minutes, so the response is read from the RESP window after the situation started.

    python analyzer/decisions.py <name>          # reads work/<name>.analyzed / .spikes / .basics / .fights json,
                                                 # writes work/<name>.decisions.json

Situations (owner's picks; held long enough that blips don't count):
- income lead / deficit: income /min gap >= max(INC_ABS, INC_REL of theirs), held >= INC_HOLD
- army lead / deficit: army value gap >= ARMY_GAP, held >= ARMY_HOLD
- the enemy ages up; the player first sees a new enemy army unit type (the game's own visibility bit)
- a fight trading >= FIGHT_MIN value (both sides' losses)
Triggers within MERGE of the first one are one decision point.
Response, RESP after the point: what the spending went to (army by unit type incl. production buildings and military
techs / age-up = landmark placed by RESP + LM_LATE / boom = villagers, TCs, eco buildings, eco techs / defence =
towers, walls, keeps, outposts) and the fights taken (on their side of the map / at home).
Judged by (owner): the lead change over RESP (gathered gap + army gap) and the game result. Ahead in both and the lead
extended counts as paid off (owner: players ahead often extend the lead rather than end the game).

Army return per unit type (owner's rule 1): value destroyed (fight damage share x the enemy's value lost) + counter
units forced (enemy spending on units with a bonus against it, after its first one) + villagers forced idle (raids)
against its cost, and the share of its time on the enemy's third of the map.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from basics import _is_army, RES  # noqa: E402
from gamedata import class_match, is_free, resolve  # noqa: E402
from techs_bought import civ_code, techs_bought  # noqa: E402

FORMAT = "a4d-decisions/1"
INC_ABS, INC_REL, INC_HOLD = 60.0, 0.10, 90.0     # /min, share of their income, s
ARMY_GAP, ARMY_HOLD = 300.0, 60.0
FIGHT_MIN = 300.0
MERGE = 60.0
RESP = 150.0          # s: the response window (owner: decisions show 2-3 min later)
LM_LATE = 60.0        # s: a landmark placed this long after the window still counts as the save it was for
SECOND = 0.30         # share: a second response named
COUNTER_BONUS = 0.5   # a bonus >= this share of the base damage = a counter
STEP = 5              # frames between position samples (time on the enemy side)
DEFENCE = ("tower", "wall", "palisade", "keep", "outpost", "gate", "bastion", "fortress", "barbican")
ECO_B = ("house", "mill", "lumber", "mining", "farm", "town_center", "dock", "granary", "ger", "pasture", "hunting",
         "cistern", "orchard")


def _load(name, key=None):
    with open(os.path.join(HERE, "..", "data", name), encoding="utf-8") as fh:
        d = json.load(fh)
    return d[key] if key else d


def mmss(t):
    t = int(round(t or 0))
    return f"{t // 60}:{t % 60:02d}"


def _at(S, t, key):
    """value of key in series S (dicts with "t", every 5 s) at time t (last sample at or before t)"""
    v = None
    for x in S:
        if x["t"] > t:
            break
        v = x.get(key)
    return v


def _stretches(ts, vals, hold):
    """[(t0, t1, state)] runs of the same state lasting >= hold s (state 0 included)"""
    out, i = [], 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        if ts[j] - ts[i] >= hold:
            out.append((ts[i], ts[j], vals[i]))
        i = j + 1
    return out


def _onsets(stretches):
    """times a held state (+1 / -1) starts after a different held state"""
    out, prev = [], 0
    for t0, _, s in stretches:
        if s != prev and s != 0:
            out.append((t0, s))
        prev = s
    return out


def result_of(tl):
    """{p: "W"/"L"/"?"}: the side whose entities vanish first lost (1v1)"""
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    last = {p: 0.0 for p in pids}
    for fr in frames:
        for e in fr["entities"]:
            if e["owner"] in last:
                last[e["owner"]] = fr["t"]
    end = frames[-1]["t"]
    res = {p: "?" for p in pids}
    if len(pids) == 2:
        a, b = pids
        if last[a] < end - 2 and last[a] < last[b] - 1:
            res = {a: "L", b: "W"}
        elif last[b] < end - 2 and last[b] < last[a] - 1:
            res = {a: "W", b: "L"}
    return res


def _unit_name_map(units):
    """display name (any tier) -> base"""
    m = {}
    for u in units.values():
        if u.get("name") and u.get("base"):
            m.setdefault(u["name"], u["base"])
    return m


def _base_of(bp, units):
    u = units.get(bp) or units.get(resolve(bp, units) or "") or {}
    return u.get("base"), u


def _title(base):
    return (base or "?").replace("-", " ").replace("_", " ").title()


def spending(tl, p, units, costs, bought):
    """[(t, category, sub, value)]: category army / ageup / boom / defence / other; sub = unit base etc."""
    frames = tl["frames"]
    start = {e["id"] for e in frames[0]["entities"]}
    seen, out = set(), []
    for fr in frames:
        for e in fr["entities"]:
            if e["owner"] != p or e["id"] in seen:
                continue
            seen.add(e["id"])
            bp = e["bp"] or ""
            if e["id"] in start or not bp or is_free(bp):
                continue
            c = costs.get(resolve(bp, costs) or "")
            if not c:
                continue
            v = sum(float(c.get(r) or 0) for r in RES)
            if v <= 0:
                continue
            if e["kind"] == "w":
                out.append((fr["t"], "boom", "villagers", v))
            elif _is_army(e):
                base, _ = _base_of(bp, units)
                out.append((fr["t"], "army", base or bp, v))
            elif e["kind"] == "o":
                if "landmark" in bp or c.get("landmark_age"):
                    out.append((fr["t"], "ageup", c.get("name") or bp, v))
                elif "town_center" in bp:
                    out.append((fr["t"], "boom", "town center", v))
                elif any(w in bp for w in DEFENCE):
                    out.append((fr["t"], "defence", c.get("name") or bp, v))
                elif any(w in bp for w in ECO_B):
                    out.append((fr["t"], "boom", "eco buildings", v))
                elif c.get("military") is False and any(w in bp for w in ("barracks", "range", "stable", "siege",
                                                                          "workshop", "military")):
                    out.append((fr["t"], "army", "production buildings", v))
                else:
                    out.append((fr["t"], "other", c.get("name") or bp, v))
            else:
                out.append((fr["t"], "other", c.get("name") or bp, v))
    for x in bought.get(p, []):
        v = sum(float((x.get("res") or {}).get(r) or 0) for r in RES)
        if v <= 0:
            continue
        a = x.get("attrib") or ""
        eco = "econ" in a or "wheelbarrow" in a or "villager" in a
        out.append((x["t"], "boom" if eco else "army", "eco techs" if eco else "military techs", v))
    out.sort(key=lambda s: s[0])
    return out


def _tcs(tl):
    tc = {}
    for e in tl["frames"][0]["entities"]:
        if "town_center" in (e["bp"] or "") and e["owner"] not in tc:
            tc[e["owner"]] = (e["x"], e["z"])
    return tc


def _s(xz, me, them):
    """0 at my starting TC, 1 at theirs, along the line between them"""
    dx, dz = them[0] - me[0], them[1] - me[1]
    L2 = dx * dx + dz * dz or 1.0
    return ((xz[0] - me[0]) * dx + (xz[1] - me[1]) * dz) / L2


def counters_of(units):
    """{(attacker base, target base)} pairs: some variant of the attacker has a bonus >= COUNTER_BONUS x its damage
    against classes all of which some variant of the target has"""
    by_base = {}
    for u in units.values():
        if u.get("base"):
            by_base.setdefault(u["base"], []).append(u)
    cls = {b: [set(u.get("classes") or []) for u in us] for b, us in by_base.items()}
    out = set()
    for a, us in by_base.items():
        mods = []
        for u in us:
            w = u.get("w") or {}
            for tg, val in w.get("mods") or []:
                if w.get("dmg") and val >= COUNTER_BONUS * w["dmg"]:
                    for alt in tg:
                        alts = alt if alt and isinstance(alt[0], list) else [alt]
                        for al in alts:
                            mods.append(set(al))
        if not mods:
            continue
        for b, cs in cls.items():
            if b != a and any(class_match(sorted(m), c) for m in mods for c in cs):
                out.add((a, b))
    return out


def analyze(tl, spikes, basics, fights=None):
    units = _load("units.json", "units")
    costs = _load("costs.json", "costs")
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        bought = {}
    names = _unit_name_map(units)
    counter = counters_of(units)
    pids = [p["idx"] for p in tl["players"]]
    if len(pids) != 2:
        raise ValueError("decision points: 1v1 games only")
    res = result_of(tl)
    tcs = _tcs(tl)
    frames = tl["frames"]
    S = {p: spikes["series"][str(p)] for p in pids}
    G = {p: (basics.get("players") or {}).get(str(p), {}).get("series") or [] for p in pids}
    spend = {p: spending(tl, p, units, costs, bought) for p in pids}
    age_t = {p: [] for p in pids}
    last_age = {p: 1 for p in pids}
    for fr in frames:
        for p in pids:
            a = (fr["players"].get(str(p)) or {}).get("age")
            if a and int(a) > last_age[p]:
                for k in range(last_age[p] + 1, int(a) + 1):
                    age_t[p].append((fr["t"], k))
                last_age[p] = int(a)
    first_seen = {p: {} for p in pids}          # p's first sight of each enemy army base
    for fr in frames:
        for e in fr["entities"]:
            p = next((q for q in pids if q != e["owner"]), None) if e["owner"] in pids else None
            if p is None or not _is_army(e) or not e.get("vis") or not (e["vis"] & (1 << (p - 1))):
                continue
            b, _ = _base_of(e["bp"] or "", units)
            if b and b not in first_seen[p] and "scout" not in b:
                first_seen[p][b] = fr["t"]
    out = {"format": FORMAT, "players": {}, "params": {
        "INC_ABS": INC_ABS, "INC_REL": INC_REL, "INC_HOLD": INC_HOLD, "ARMY_GAP": ARMY_GAP, "ARMY_HOLD": ARMY_HOLD,
        "FIGHT_MIN": FIGHT_MIN, "MERGE": MERGE, "RESP": RESP}}
    t_end = frames[-1]["t"]
    for p in pids:
        o = next(q for q in pids if q != p)
        ts = [x["t"] for x in S[p]]
        So = S[o]
        inc_state, army_state = [], []
        for i, x in enumerate(S[p]):
            y = So[i] if i < len(So) else So[-1]
            mi, ti = x.get("income"), y.get("income")
            if mi is None or ti is None:
                inc_state.append(0)
            else:
                th = max(INC_ABS, INC_REL * ti)
                inc_state.append(1 if mi - ti >= th else -1 if ti - mi >= th else 0)
            g = (x.get("army") or 0) - (y.get("army") or 0)
            army_state.append(1 if g >= ARMY_GAP else -1 if g <= -ARMY_GAP else 0)
        inc_run = _stretches(ts, inc_state, INC_HOLD)
        army_run = _stretches(ts, army_state, ARMY_HOLD)
        trig = []
        for t, s in _onsets(inc_run):
            trig.append((t, "income lead" if s > 0 else "income deficit"))
        for t, s in _onsets(army_run):
            trig.append((t, "army lead" if s > 0 else "army deficit"))
        for t, k in age_t[o]:
            trig.append((t, f"enemy reached age {k}"))
        for b, t in first_seen[p].items():
            trig.append((t, f"saw enemy {_title(b)}"))
        for f in spikes.get("fights") or []:
            lost = {q: sum(v for v in (f["lost"].get(str(q)) or {}).values()) for q in pids}
            if lost[p] + lost[o] >= FIGHT_MIN:
                trig.append((f["start"], "fight won" if lost[p] < lost[o] else "fight lost"))
        trig = sorted(x for x in trig if x[0] < t_end - 30)
        points, i = [], 0
        while i < len(trig):
            t0 = trig[i][0]
            group = []
            while i < len(trig) and trig[i][0] - t0 <= MERGE:
                if trig[i][1] not in group:
                    group.append(trig[i][1])
                i += 1
            points.append(_point(t0, group, p, o, S, G, spend, spikes, tcs, age_t, frames, t_end, res))
        out["players"][str(p)] = {"civ": next(x["civ"] for x in tl["players"] if x["idx"] == p),
                                  "code": civ_code(tl, p), "result": res[p], "points": points,
                                  "units": unit_returns(tl, p, o, spend, fights, basics, units, names, counter, tcs)}
    return out


def _lead(G, p, o, t):
    """(gathered gap, army gap) at t from the basics series [t, gathered, bank, army, ...]"""
    def at(s):
        v = None
        for x in s:
            if x[0] > t:
                break
            v = x
        return v
    a, b = at(G[p]), at(G[o])
    if not a or not b:
        return None
    return a[1] - b[1], a[3] - b[3]


def _age_at(age_t, p, t):
    a = 1
    for tt, k in age_t[p]:
        if tt <= t:
            a = k
    return a


def _state(v, lo_hi):
    return "ahead" if v >= lo_hi else "behind" if v <= -lo_hi else "even"


def _point(t0, group, p, o, S, G, spend, spikes, tcs, age_t, frames, t_end, res):
    t1 = min(t0 + RESP, t_end)
    mi, ti = _at(S[p], t0, "income"), _at(S[o], t0, "income")
    inc = "even"
    if mi is not None and ti is not None:
        th = max(INC_ABS, INC_REL * ti)
        inc = "ahead" if mi - ti >= th else "behind" if ti - mi >= th else "even"
    army = _state((_at(S[p], t0, "army") or 0) - (_at(S[o], t0, "army") or 0), ARMY_GAP)
    # response: spending in the window (age-up: landmarks placed up to LM_LATE after it - the save was for them)
    cat, sub = {}, {}
    for t, c, s, v in spend[p]:
        if t0 <= t < t1 or (c == "ageup" and t1 <= t < t1 + LM_LATE):
            cat[c] = cat.get(c, 0) + v
            sub.setdefault(c, {})
            sub[c][s] = sub[c].get(s, 0) + v
    tot = sum(cat.values()) or 1.0
    shares = {c: round(v / tot, 2) for c, v in sorted(cat.items(), key=lambda kv: -kv[1])}
    order = [c for c in shares if c != "other"]
    main = order[0] if order else "nothing"
    second = order[1] if len(order) > 1 and shares[order[1]] >= SECOND else None
    army_mix = sorted(((s, v) for s, v in (sub.get("army") or {}).items()), key=lambda kv: -kv[1])
    fights = []
    for f in spikes.get("fights") or []:
        if t0 <= f["start"] < t1:
            lost = {q: sum(v for v in (f["lost"].get(str(q)) or {}).values()) for q in (p, o)}
            if lost[p] + lost[o] < 100:
                continue
            where = "their side" if _s((f["x"], f["z"]), tcs[p], tcs[o]) > 0.5 else "home side"
            fights.append({"t": f["start"], "where": where, "lost": round(lost[p]), "killed": round(lost[o])})
    l0, l1 = _lead(G, p, o, t0), _lead(G, p, o, t1)
    dl = None
    if l0 and l1:
        dl = {"gathered": round(l1[0] - l0[0]), "army": round(l1[1] - l0[1]),
              "total": round((l1[0] + l1[1]) - (l0[0] + l0[1])), "at": [round(l0[0]), round(l0[1])]}
    lab = main if main != "army" else "army (" + ", ".join(_title(s) for s, _ in army_mix[:2]) + ")"
    if second:
        lab += " + " + (second if second != "army" else "army (" + ", ".join(_title(s) for s, _ in army_mix[:2]) + ")")
    if fights:
        theirs = sum(1 for f in fights if f["where"] == "their side")
        lab += " + fights " + ("on their side" if theirs * 2 >= len(fights) else "at home")
    return {"t": round(t0, 1), "age": _age_at(age_t, p, t0), "income": inc, "army": army, "triggers": group,
            "situation": f"age {_age_at(age_t, p, t0)}, income {inc}, army {army}",
            "response": {"main": main, "second": second, "shares": shares, "label": lab,
                         "army_mix": [[s, round(v)] for s, v in army_mix[:4]],
                         "spent": round(sum(cat.values())), "fights": fights},
            "until": round(t1, 1), "lead_change": dl,
            "paid_off": None if dl is None else dl["total"] > 0, "result": res[p]}


def unit_returns(tl, p, o, spend, fights, basics, units, names, counter, tcs):
    """{base: {n, cost, destroyed, countered, forced_idle, return, enemy_side}} for p's army unit types"""
    out = {}
    first = {}
    for t, c, s, v in spend[p]:
        if c == "army" and s not in ("production buildings", "military techs"):
            d = out.setdefault(s, {"n": 0, "cost": 0.0, "destroyed": 0.0, "countered": 0.0, "forced_idle": 0.0})
            d["n"] += 1
            d["cost"] += v
            first.setdefault(s, t)
    if not out:
        return {}
    # value destroyed: each fight's enemy losses split by p's damage share per unit type
    for f in (fights or {}).get("fights") or []:
        D = (f.get("damage") or {}).get(str(p)) or {}
        dmg = D.get("by") or []
        # share of all HP the enemy lost: damage with no recorded attacker (TCs, towers, gaps) is credited to nobody
        tot = sum(x[1] for x in dmg) + (D.get("unattributed") or 0)
        lost_o = (f.get("lost") or {}).get(str(o)) or 0
        if tot <= 0 or lost_o <= 0:
            continue
        for name, d, *_ in dmg:
            b = names.get(name)
            if b in out:
                out[b]["destroyed"] += lost_o * d / tot
    # counter units forced: their spending on units with a bonus against my type, after my first one, split among my
    # types it counters by my spending on them
    for t, c, s, v in spend[o]:
        if c != "army":
            continue
        targets = [b for b in out if (s, b) in counter and first[b] <= t]
        w = sum(out[b]["cost"] for b in targets)
        for b in targets:
            out[b]["countered"] += v * out[b]["cost"] / w
    # villagers forced idle by raids: split by the raid's units
    raids = (((basics.get("lenses") or {}).get(str(p)) or {}).get("hindsight") or {}).get("raids") or []
    for r in raids:
        us = r.get("units") or {}
        n = sum(us.values()) or 0
        for b, k in us.items():
            if b in out and n:
                out[b]["forced_idle"] += (r.get("forcedValue") or 0) * k / n
    # time on the enemy's third of the map
    side = {b: [0, 0] for b in out}
    if p in tcs and o in tcs:
        for fr in tl["frames"][::STEP]:
            for e in fr["entities"]:
                if e["owner"] != p or not _is_army(e):
                    continue
                b, _ = _base_of(e["bp"] or "", units)
                if b in side:
                    side[b][1] += 1
                    if _s((e["x"], e["z"]), tcs[p], tcs[o]) > 2 / 3:
                        side[b][0] += 1
    for b, d in out.items():
        back = d["destroyed"] + d["countered"] + d["forced_idle"]
        d["return"] = round(back / d["cost"], 2) if d["cost"] else None
        d["enemy_side"] = round(side[b][0] / side[b][1], 2) if side.get(b) and side[b][1] else None
        for k in ("cost", "destroyed", "countered", "forced_idle"):
            d[k] = round(d[k])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="game name: work/<name>.*.json")
    ap.add_argument("--work", default=os.path.join(HERE, "..", "work"))
    a = ap.parse_args()

    def rd(k, need=True):
        f = os.path.join(a.work, f"{a.name}.{k}.json")
        if not os.path.exists(f):
            if need:
                sys.exit(f"missing {f}")
            return None
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    out = analyze(rd("analyzed"), rd("spikes"), rd("basics"), rd("fights", False))
    f = os.path.join(a.work, f"{a.name}.decisions.json")
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    for p, d in out["players"].items():
        print(f"P{p} {d['civ']} ({d['result']}): {len(d['points'])} decision points")
        for x in d["points"]:
            dl = x["lead_change"]
            print(f"  {mmss(x['t'])} {x['situation']} [{'; '.join(x['triggers'])}] -> {x['response']['label']}"
                  f" | lead {'' if dl is None else f'{dl['total']:+}'}")
        for b, u in sorted(d["units"].items(), key=lambda kv: -kv[1]["cost"]):
            print(f"  unit {b}: {u}")
    print("->", f)


if __name__ == "__main__":
    main()
