"""Basics check for one game (review only: full information). Owner's rules, 2026-10-26:

1. The player who gathers more in total, and does not float unless saving for an age-up, wins.
2. When I fall behind in gathering: what was the enemy doing differently (resource split, villagers lost, idle)?
3. During a purposeful save (age-up cost), are villagers allocated to reach it, not over-rallied into wood?
4. Spending style: turbo (spending on units), trickle (undecided), saving, floating.
   Floating, graded until 200 pop (owner): hard = >= 500 of one resource for >= 60 s, soft = >= 300 for >= 30 s,
   not counting the resources of an age-up being saved for.
5. Army value and value destroyed, both sides.
6. Trades: value lost per fight first; minutes of income lost second (matters when one side cannot replace losses
   while the other trades badly but keeps a stream of units that taxes the enemy's bank).
7. Aggression clock: minutes of the worked natural food / gold / stone nodes left at the current depletion rate.

Input: an analyzed timeline (work/<name>.analyzed.json: frames with villager resource labels, nodes, events).
"""
import math
import re

from fights import find_deaths
from gamedata import is_free, resolve
from techs_bought import techs_bought

RES = ("food", "wood", "gold", "stone")
RES_ID = {1: "food", 2: "wood", 3: "gold", 4: "stone"}
STEP = 1.0                 # s, resample step
WIN = 30.0                 # s, spending-style window
HARD, SOFT = (500.0, 60.0), (300.0, 30.0)
POP_CAP = 200
SAVE_LOOKBACK = 240.0      # s before a landmark start to look for the start of the save
STD_AGE_COST = {1: {"food": 400, "gold": 200}, 2: {"food": 1200, "gold": 600}, 3: {"food": 2400, "gold": 1200}}
DEFICIT_MIN = 60.0         # s: a stretch where my income is below theirs at least this long
REACH = 8.0                # map units: villager on a node
NATURAL = {"berry": "food", "deer": "food", "sheep": "food", "carcass": "food", "boar": "food",
           "gold": "gold", "stone": "stone"}
SUPPORT = ("scout", "monk", "prelate", "imam", "scholar", "priest", "shaman", "dervish")


def _pl(fr, p):
    return fr["players"].get(str(p)) or fr["players"].get(p) or {}


def _is_army(e):
    return e["kind"] == "m" and not any(s in (e["bp"] or "") for s in SUPPORT)


def per_player(tl, costs_full, cost_of, bought=None):
    """({player: {"rows": [per frame: t, bank, spent, cat (cumulative spent by category), gathered, vil, nvil, idle,
    pop, age, army]}, "landmarks": [...]}}, cancelled landmark ids, bought). Also used by spikes.py."""
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    start_ids = {e["id"] for e in frames[0]["entities"]}
    if bought is None:
        try:
            bought = techs_bought(tl)
        except (OSError, ValueError):
            bought = {p: [] for p in pids}

    # ---- per player per frame: bank, spent (per resource, incl. techs), villagers by resource, idle, pop, army
    per = {}
    cancelled = set()
    for p in pids:
        spent_ev = []
        seen = set()
        landmarks = []
        for fr in frames:
            for e in fr["entities"]:
                if e["owner"] != p or e["id"] in seen:
                    continue
                seen.add(e["id"])
                if e["id"] in start_ids or not e["bp"] or is_free(e["bp"]):
                    continue
                c = costs_full.get(resolve(e["bp"], costs_full) or "")
                if not c:
                    continue
                cost = {r: float(c.get(r) or 0) for r in RES}
                cat = "army" if _is_army(e) else "villager" if e["kind"] == "w" else "building" if e["kind"] == "o" else "other"
                if "landmark" in e["bp"]:
                    cat = "landmark"
                    m = re.search(r"_age(\d)", e["bp"])
                    age = int(m.group(1)) if m else None
                    landmarks.append({"t": fr["t"], "id": e["id"], "bp": e["bp"], "name": c.get("name") or e["bp"],
                                      "age": age, "cost": cost})
                spent_ev.append((fr["t"], cost, cat))
        for x in bought.get(p, []):
            if x.get("res"):
                spent_ev.append((x["t"], {r: float(x["res"].get(r) or 0) for r in RES}, "tech"))
        # a second landmark of the same age placed while one is up gets cancelled (one per age): it vanishes and the
        # bank jumps back by most of its cost (game1: HRE placed Meinwerk Palace and Aachen Chapel 5 s apart)
        for L in _cancelled(frames, p, landmarks):
            cancelled.add(L["id"])
            spent_ev.append((L["gone"], {r: -v for r, v in L["cost"].items()}, "landmark"))
        for L in landmarks:
            L["cancelled"] = L["id"] in cancelled
        spent_ev.sort(key=lambda s: s[0])
        b0 = {r: float(_pl(frames[0], p).get("bank", {}).get(r) or 0) for r in RES}
        rows, si = [], 0
        cum = {r: 0.0 for r in RES}
        cum_cat = {"army": 0.0, "villager": 0.0, "building": 0.0, "landmark": 0.0, "tech": 0.0, "other": 0.0}
        for fr in frames:
            while si < len(spent_ev) and spent_ev[si][0] <= fr["t"]:
                for r in RES:
                    cum[r] += spent_ev[si][1][r]
                cum_cat[spent_ev[si][2]] += sum(spent_ev[si][1].values())
                si += 1
            pl = _pl(fr, p)
            bank = {r: float(pl.get("bank", {}).get(r) or 0) for r in RES}
            vil = {r: 0 for r in RES}
            idle = nvil = 0
            army = 0.0
            for e in fr["entities"]:
                if e["owner"] != p:
                    continue
                if e["kind"] == "w":
                    nvil += 1
                    r = RES_ID.get(e.get("res") or 0)
                    if r:
                        vil[r] += 1
                    elif e.get("idle"):
                        idle += 1
                elif _is_army(e):
                    army += cost_of(e["bp"])
            rows.append({"t": fr["t"], "bank": bank, "spent": dict(cum), "cat": dict(cum_cat),
                         "gathered": {r: bank[r] - b0[r] + cum[r] for r in RES},
                         "vil": vil, "nvil": nvil, "idle": idle, "pop": pl.get("pop"), "age": pl.get("age"),
                         "army": army})
        per[p] = {"rows": rows, "landmarks": landmarks}
    return per, cancelled, bought


def basics(tl, costs_full, cost_of):
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    per, cancelled, bought = per_player(tl, costs_full, cost_of)

    deaths = [d for d in find_deaths(frames, cost_of, tl.get("events")) if d["id"] not in cancelled]
    out = {"players": {str(p): {} for p in pids}, "t_end": frames[-1]["t"]}
    for p in pids:
        o = [q for q in pids if q != p][0] if len(pids) > 1 else p
        R = per[p]["rows"]
        d = out["players"][str(p)]
        d["landmarks"] = [{"t": round(L["t"]), "name": L["name"], "age": L["age"], "cancelled": bool(L.get("cancelled"))}
                          for L in per[p]["landmarks"]]
        d["saves"] = _saves(R, [L for L in per[p]["landmarks"] if not L.get("cancelled")])
        d["floats"] = _floats(R, d["saves"])
        d["style"] = _style(R, d["saves"], d["floats"])
        d["series"] = _series(R)
        d["deaths"] = _death_sums(deaths, p)
        d["clock"] = _clock(tl, R, p)
        d["overqueue"] = _overqueue(frames, p, costs_full)
    if len(pids) == 2:
        a, b = pids
        out["deficits"] = {str(a): _deficits(per[a]["rows"], per[b]["rows"], deaths, a, b),
                           str(b): _deficits(per[b]["rows"], per[a]["rows"], deaths, b, a)}
        out["trades"] = _trades(tl, per, deaths, a, b)
        try:
            from castle import load_production
            from lenses import lenses
            out["lenses"] = lenses(tl, per, deaths, out["trades"],
                                   {p: out["players"][str(p)]["clock"] for p in pids},
                                   costs_full, cost_of, bought, load_production())
        except Exception as e:  # noqa: BLE001 - the rest of the page must still build
            import traceback
            traceback.print_exc()
            out["lensesError"] = f"{type(e).__name__}: {e}"
    return out


def _cancelled(frames, p, landmarks):
    last = {}
    for i, fr in enumerate(frames):
        for e in fr["entities"]:
            if e["owner"] == p and e["id"] in {L["id"] for L in landmarks}:
                last[e["id"]] = i
    out = []
    for L in landmarks:
        i = last.get(L["id"])
        if i is None or i >= len(frames) - 2:
            continue
        same_age = [M for M in landmarks if M is not L and M["age"] == L["age"] and abs(M["t"] - L["t"]) < 120]
        if not same_age:
            continue
        b_before = sum((_pl(frames[i], p).get("bank", {}).get(r) or 0) for r in RES)
        b_after = max(sum((_pl(frames[k], p).get("bank", {}).get(r) or 0) for r in RES)
                      for k in range(i + 1, min(len(frames), i + 4)))
        if b_after - b_before >= 0.6 * sum(L["cost"].values()):
            out.append(dict(L, gone=frames[i + 1]["t"]))
    return out


# ---------------------------------------------------------------- 3. saves for an age-up
def _saves(R, landmarks):
    """Per landmark: save window = from the minimum of the needed bank in the SAVE_LOOKBACK s before the landmark
    start (the bank starts climbing) to the start; villager split in it; time to afford as allocated vs ideal."""
    out = []
    times = [r["t"] for r in R]
    for L in landmarks:
        need = {r: v for r, v in L["cost"].items() if v > 0} or STD_AGE_COST.get(L["age"] or 0, {})
        if not need:
            continue
        iL = max(0, next((i for i, t in enumerate(times) if t >= L["t"]), len(times) - 1) - 1)
        i0 = next((i for i, t in enumerate(times) if t >= L["t"] - SAVE_LOOKBACK), 0)
        if iL <= i0:
            continue
        tot = [sum(R[i]["bank"][r] for r in need) for i in range(i0, iL + 1)]
        iS = i0 + min(range(len(tot)), key=lambda k: tot[k])
        if iL - iS < 10:
            continue
        span = R[iL]["t"] - R[iS]["t"]
        vs = {r: sum(R[i]["vil"][r] for i in range(iS, iL)) / max(1, iL - iS) for r in RES}
        eco = sum(vs.values()) or 1
        rate = {r: (R[iL]["gathered"][r] - R[iS]["gathered"][r]) / span for r in RES}
        per_vil = {r: rate[r] / vs[r] if vs[r] > 0.5 else None for r in RES}
        missing = {r: max(0.0, need[r] - R[iS]["bank"][r]) for r in need}
        # ideal: the same number of eco villagers, split so every needed resource arrives at the same moment, after
        # keeping enough villagers to cover what was being spent meanwhile on every resource (villagers, houses):
        #   n_r = (missing_r / T + spend_r) / pv_r for needed r, spend_r / pv_r for the others, sum n_r = eco
        #   -> T = sum_need(missing_r / pv_r) / (eco - sum_all(spend_r / pv_r))
        pv = [v for v in per_vil.values() if v]
        mean_pv = sum(pv) / len(pv) if pv else 0.7
        pvr = {r: per_vil.get(r) or mean_pv for r in RES}
        spend = {r: max(0.0, (R[iL]["spent"][r] - R[iS]["spent"][r]) / span) for r in RES}
        # income on a resource with (almost) no villagers on it is passive (Rus hunting bounty gold, ...)
        passive = {r: max(0.0, rate[r]) if vs[r] < 0.5 else 0.0 for r in RES}
        need_vils = sum(vs[r] for r in need)
        free = eco - sum(max(0.0, spend[r] - passive[r]) / pvr[r] for r in RES)
        work = sum(max(0.0, missing[r] - passive[r] * span) / pvr[r] for r in need)
        ideal_t = work / free if free > 0.5 else None
        ideal_vils = None
        if ideal_t:
            # the split behind that time: needed resources get missing / T on top of their spending
            ideal_vils = {r: round((max(0.0, missing.get(r, 0.0) - passive[r] * span) / ideal_t if r in need else 0.0)
                                   / pvr[r] + max(0.0, spend[r] - passive[r]) / pvr[r], 1) for r in RES}
            ideal_t = min(ideal_t, span)          # no faster split found = the allocation was fine
        # first moment the bank covered the cost (a landmark placed later = time lost after saving up)
        afford = next((R[i]["t"] for i in range(iS, iL + 1) if all(R[i]["bank"][r] >= need[r] - 0.5 for r in need)), None)
        out.append({"t0": round(R[iS]["t"]), "t1": round(R[iL]["t"]), "name": L["name"], "age": L["age"],
                    "afford": round(afford) if afford is not None else None,
                    "placeDelay": round(R[iL]["t"] - afford) if afford is not None else None,
                    "need": {r: round(v) for r, v in need.items()}, "bank0": {r: round(R[iS]["bank"][r]) for r in need},
                    "vils": {r: round(v, 1) for r, v in vs.items()}, "eco": round(eco, 1),
                    "needShare": round(need_vils / eco, 2), "woodShare": round(vs["wood"] / eco, 2),
                    "took": round(span), "ideal": round(ideal_t) if ideal_t is not None else None,
                    "idealVils": ideal_vils, "spentDuring": round(
                        sum(R[iL]["spent"][r] - R[iS]["spent"][r] for r in RES))})
    return out


def _saving_at(saves, t, r):
    return any(s["t0"] <= t <= s["t1"] and r in s["need"] for s in saves)


# ---------------------------------------------------------------- 4. floating
def _floats(R, saves):
    out = []
    for grade, (amt, dur) in (("hard", HARD), ("soft", SOFT)):
        for r in RES:
            start = None
            for row in R + [None]:
                ok = row is not None and row["bank"][r] >= amt and (row["pop"] or 0) < POP_CAP \
                    and not _saving_at(saves, row["t"], r)
                if ok and start is None:
                    start, peak = row["t"], row["bank"][r]
                elif ok:
                    peak = max(peak, row["bank"][r])
                elif start is not None:
                    end = (row or R[-1])["t"]
                    if end - start >= dur:
                        out.append({"grade": grade, "res": r, "t0": round(start), "t1": round(end), "peak": round(peak)})
                    start = None
    # a soft float fully inside a hard one of the same resource is the same float
    hard = [f for f in out if f["grade"] == "hard"]
    out = hard + [f for f in out if f["grade"] == "soft" and not any(
        h["res"] == f["res"] and h["t0"] >= f["t0"] and h["t1"] <= f["t1"] for h in hard)]
    return sorted(out, key=lambda f: f["t0"])


# ---------------------------------------------------------------- 4. spending style per window
def _style(R, saves, floats):
    """turbo: spending >= 90 % of income, mostly army, bank < 400; saving: inside a save window; floating: a float
    overlaps; trickle: the rest with spending 40-90 % of income (bank creeping up, no save); idle: spending < 40 %."""
    out = []
    i = 0
    while i < len(R):
        j = i
        while j < len(R) and R[j]["t"] - R[i]["t"] < WIN:
            j += 1
        if j >= len(R):
            break
        a, b = R[i], R[j]
        dt = b["t"] - a["t"]
        inc = sum(b["gathered"].values()) - sum(a["gathered"].values())
        sp = sum(b["spent"].values()) - sum(a["spent"].values())
        army = b["cat"]["army"] - a["cat"]["army"]
        bank = sum(b["bank"].values())
        if any(s["t0"] <= b["t"] and s["t1"] >= a["t"] for s in saves):
            kind = "saving"
        elif any(f["t0"] <= b["t"] and f["t1"] >= a["t"] and f["grade"] == "hard" for f in floats):
            kind = "floating"
        elif inc > 0 and sp >= 0.9 * inc and army >= 0.5 * sp and bank < 400:
            kind = "turbo"
        elif any(f["t0"] <= b["t"] and f["t1"] >= a["t"] for f in floats):
            kind = "floating (soft)"
        elif inc > 0 and sp >= 0.9 * inc:
            kind = "spending"
        elif inc > 0 and sp >= 0.4 * inc:
            kind = "trickle"
        else:
            kind = "banking"
        out.append({"t0": round(a["t"]), "t1": round(b["t"]), "kind": kind, "income": round(inc / dt * 60),
                    "spend": round(sp / dt * 60), "army": round(army / dt * 60), "bank": round(bank)})
        i = j
    return out


# ---------------------------------------------------------------- series for the charts (every 5 s)
def _series(R):
    s = []
    for row in R[::5]:
        s.append([round(row["t"]), round(sum(row["gathered"].values())),
                  {r: round(v) for r, v in row["bank"].items()}, round(row["army"]),
                  {r: v for r, v in row["vil"].items()}, row["idle"], row["pop"], round(sum(row["spent"].values())),
                  {r: round(v) for r, v in row["gathered"].items()}])      # [8] gathered per resource (3D graph)
    return s


def _income_per_min(R, i, span=120.0):
    j = i
    while j > 0 and R[i]["t"] - R[j]["t"] < span:
        j -= 1
    dt = R[i]["t"] - R[j]["t"]
    return (sum(R[i]["gathered"].values()) - sum(R[j]["gathered"].values())) / dt * 60 if dt > 0 else 0.0


def _death_sums(deaths, p):
    lost = {"army": 0.0, "villager": 0.0, "building": 0.0}
    cnt = {"army": 0, "villager": 0, "building": 0}
    for d in deaths:
        if d["owner"] != p:
            continue
        k = "villager" if d["kind"] == "w" else "building" if d["kind"] == "o" else "army" if d["kind"] == "m" else None
        if k:
            lost[k] += d["cost"] or 0
            cnt[k] += 1
    return {"value": {k: round(v) for k, v in lost.items()}, "count": cnt,
            "army_t": [[round(d["t"]), round(d["cost"] or 0)] for d in deaths if d["owner"] == p and d["kind"] == "m"]}


# ---------------------------------------------------------------- 2. deficits
def _deficits(R, Q, deaths, me, them):
    """Stretches >= DEFICIT_MIN where my gathering rate (60 s) is below theirs; what differed."""
    out = []
    times = [r["t"] for r in R]
    rate = []
    for i in range(len(R)):
        rate.append(_income_per_min(R, i, 60.0) - _income_per_min(Q, min(i, len(Q) - 1), 60.0))
    i = 0
    while i < len(R):
        if rate[i] >= 0 or R[i]["t"] < 60:
            i += 1
            continue
        j = i
        while j < len(R) and rate[j] < 0:
            j += 1
        if times[min(j, len(R) - 1)] - times[i] >= DEFICIT_MIN and _gap(R, Q, i, min(j, len(R) - 1)) >= 100:
            a, b = i, min(j, len(R) - 1)
            n = max(1, b - a)
            mv = {r: sum(R[k]["vil"][r] for k in range(a, b)) / n for r in RES}
            tv = {r: sum(Q[min(k, len(Q) - 1)]["vil"][r] for k in range(a, b)) / n for r in RES}
            m_idle = sum(R[k]["idle"] for k in range(a, b)) / n
            t_idle = sum(Q[min(k, len(Q) - 1)]["idle"] for k in range(a, b)) / n
            t0, t1 = times[a], times[b]
            lost_me = sum(1 for d in deaths if d["owner"] == me and d["kind"] == "w" and t0 - 60 <= d["t"] <= t1)
            lost_them = sum(1 for d in deaths if d["owner"] == them and d["kind"] == "w" and t0 - 60 <= d["t"] <= t1)
            gm = sum(R[b]["gathered"].values()) - sum(R[a]["gathered"].values())
            gt = sum(Q[min(b, len(Q) - 1)]["gathered"].values()) - sum(Q[min(a, len(Q) - 1)]["gathered"].values())
            per_m = gm / max(1e-6, sum(R[k]["vil"][r] for k in range(a, b) for r in RES) * STEP) if b > a else 0
            per_t = gt / max(1e-6, sum(Q[min(k, len(Q) - 1)]["vil"][r] for k in range(a, b) for r in RES) * STEP) if b > a else 0
            out.append({"t0": round(t0), "t1": round(t1), "gap": round(gt - gm),
                        "mineVils": {r: round(v, 1) for r, v in mv.items()},
                        "theirVils": {r: round(v, 1) for r, v in tv.items()},
                        "mineIdle": round(m_idle, 1), "theirIdle": round(t_idle, 1),
                        "mineLost": lost_me, "theirLost": lost_them,
                        "minePerVil": round(per_m * 60, 1), "theirPerVil": round(per_t * 60, 1)})
        i = max(j, i + 1)
    return out


def _gap(R, Q, a, b):
    gm = sum(R[b]["gathered"].values()) - sum(R[a]["gathered"].values())
    gt = sum(Q[min(b, len(Q) - 1)]["gathered"].values()) - sum(Q[min(a, len(Q) - 1)]["gathered"].values())
    return gt - gm


# ---------------------------------------------------------------- 6. trades
def _trades(tl, per, deaths, a, b):
    from fights import cluster
    frames_t = [r["t"] for r in per[a]["rows"]]

    def idx(t):
        return min(range(len(frames_t)), key=lambda k: abs(frames_t[k] - t))
    out = []
    for f in cluster([d for d in deaths if d["kind"] == "m" or d["kind"] == "w"]):
        ds = f["deaths"]
        if not any(d["kind"] == "m" for d in ds):
            continue
        lost = {p: sum(d["cost"] or 0 for d in ds if d["owner"] == p) for p in (a, b)}
        if sum(lost.values()) < 100:
            continue
        t0, t1 = ds[0]["t"], ds[-1]["t"]
        i = idx(t0)
        inc = {p: _income_per_min(per[p]["rows"], i) for p in (a, b)}
        bank = {p: sum(per[p]["rows"][i]["bank"].values()) for p in (a, b)}
        mins = {p: lost[p] / inc[p] if inc[p] > 1 else None for p in (a, b)}
        vil = {p: sum(1 for d in ds if d["owner"] == p and d["kind"] == "w") for p in (a, b)}
        out.append({"t0": round(t0), "t1": round(t1), "x": round(sum(d["x"] for d in ds) / len(ds)),
                    "z": round(sum(d["z"] for d in ds) / len(ds)),
                    "lost": {str(p): round(v) for p, v in lost.items()},
                    "vilLost": {str(p): v for p, v in vil.items()},
                    "income": {str(p): round(v) for p, v in inc.items()},
                    "bank": {str(p): round(v) for p, v in bank.items()},
                    "minutes": {str(p): (round(v, 2) if v is not None else None) for p, v in mins.items()}})
    return out


# ---------------------------------------------------------------- overqueue (owner 2026-10-26)
OVERQ = 2                  # more than this many items in one building's production queue = overqueued
OVERQ_MIN = 3.0            # s: shorter blips are not counted
OPENING = 60.0             # s: the opening villager queue at the TC is normal; profile counts from here


def _overqueue(frames, p, costs_full):
    """Per production building, stretches with more than OVERQ items queued (the dump's production queue size,
    which most likely includes the item being made). Resources sit in the queue instead of the bank."""
    open_ = {}          # id -> [t0, peak, bp]
    eps = []
    last_t = frames[-1]["t"]
    for fr in frames:
        seen = set()
        for e in fr["entities"]:
            if e["owner"] != p or e.get("queue") is None:
                continue
            q = e["queue"]
            seen.add(e["id"])
            if q > OVERQ:
                if e["id"] in open_:
                    open_[e["id"]][1] = max(open_[e["id"]][1], q)
                else:
                    open_[e["id"]] = [fr["t"], q, e["bp"]]
            elif e["id"] in open_:
                t0, peak, bp = open_.pop(e["id"])
                eps.append((t0, fr["t"], peak, bp))
        for i in [i for i in open_ if i not in seen]:          # building gone
            t0, peak, bp = open_.pop(i)
            eps.append((t0, fr["t"], peak, bp))
    for t0, peak, bp in open_.values():
        eps.append((t0, last_t, peak, bp))
    eps = [x for x in eps if x[1] - x[0] >= OVERQ_MIN]

    def nm(bp):
        c = costs_full.get(resolve(bp, costs_full) or "") if bp else None
        return (c or {}).get("name") or re.sub(r"^building_|_\d.*$|_(control|capital)?_?[a-z]{2,4}$", "", bp or "?").replace("_", " ")
    by = {}
    for t0, t1, peak, bp in eps:
        if t0 < OPENING:
            continue                     # opening TC queue: in episodes (faded on the page), not in the totals
        k = nm(bp)
        b = by.setdefault(k, {"n": 0, "secs": 0.0, "longest": 0.0, "peak": 0, "first": None, "firstAfter": None})
        b["n"] += 1
        b["secs"] += t1 - t0
        b["longest"] = max(b["longest"], t1 - t0)
        b["peak"] = max(b["peak"], int(peak))
        b["first"] = t0 if b["first"] is None else min(b["first"], t0)
        if t0 >= OPENING:
            b["firstAfter"] = t0 if b["firstAfter"] is None else min(b["firstAfter"], t0)
    after = [x for x in eps if x[0] >= OPENING]
    return {"episodes": [[round(t0), round(t1), int(peak), nm(bp)] for t0, t1, peak, bp in sorted(eps)],
            "byBuilding": {k: {kk: (round(vv) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                           for k, v in sorted(by.items(), key=lambda kv: -kv[1]["secs"])},
            "openingSecs": round(sum(t1 - t0 for t0, t1, _, _ in eps if t0 < OPENING)),
            "secsAfterOpening": round(sum(t1 - t0 for t0, t1, _, _ in after)),
            "firstAfterOpening": round(min(x[0] for x in after)) if after else None}


# ---------------------------------------------------------------- 7. aggression clock
def _clock(tl, R, p, every=30.0, look=60.0):
    """Every 30 s: natural nodes this player's villagers worked in the last 60 s (food: berries / deer / sheep /
    carcasses / boar; gold; stone), what is left in them and how fast they dropped -> minutes left at that rate."""
    snaps = tl.get("nodes") or []
    if not snaps:
        return []
    frames = tl["frames"]
    times = [s["t"] for s in snaps]
    out = []
    t = every
    fi = 0
    worked = {}                 # node id -> last time a villager of p on that resource stood within REACH
    snap_i = 0
    while t <= frames[-1]["t"]:
        while fi < len(frames) and frames[fi]["t"] <= t:
            fr = frames[fi]
            while snap_i + 1 < len(snaps) and times[snap_i + 1] <= fr["t"]:
                snap_i += 1
            vils = [(e["x"], e["z"], RES_ID.get(e.get("res") or 0)) for e in fr["entities"]
                    if e["owner"] == p and e["kind"] == "w" and e["x"] is not None and e.get("res")]
            if vils and fi % 2 == 0:
                for n in snaps[snap_i]["nodes"]:
                    kind = NATURAL.get(n.get("type"))
                    if not kind or n.get("left") is None or n["x"] is None or n["left"] <= 0:
                        continue
                    if any(r == kind and abs(x - n["x"]) <= REACH and abs(z - n["z"]) <= REACH for x, z, r in vils):
                        worked[n["id"]] = (fr["t"], kind)
            fi += 1
        # amounts now and `look` s ago for the nodes worked in the last `look` s
        j_now = max(0, next((k for k, s in enumerate(times) if s > t), len(times)) - 1)
        j_old = max(0, next((k for k, s in enumerate(times) if s > t - look), len(times)) - 1)
        now = {n["id"]: n for n in snaps[j_now]["nodes"]}
        old = {n["id"]: n for n in snaps[j_old]["nodes"]}
        row = {"t": round(t)}
        for kind in ("food", "gold", "stone"):
            ids = [i for i, (tt, k) in worked.items() if k == kind and t - tt <= look]
            left = sum((now[i].get("left") or 0) for i in ids if i in now)
            drop = sum(max(0.0, (old[i].get("left") or 0) - ((now[i].get("left") or 0) if i in now else 0))
                       for i in ids if i in old)
            dt = times[j_now] - times[j_old]
            rate = drop / dt * 60 if dt > 0 else 0
            row[kind] = {"left": round(left), "perMin": round(rate),
                         "minutes": round(left / rate, 1) if rate > 5 else None}
        out.append(row)
        t += every
    return out
