"""Deaths and fights, from the dump's entity lists (truth; the viewer filters by sight).

Death: an entity present in one sample and absent from every list in the next, except
  - it shows up again later (a gap in the recording, e.g. a log line cut at the length limit),
  - its owner's whole list is empty (game end / resignation),
  - the same ID shows up under another owner (conversion),
  - a new entity of the same owner appears within TRANSFORM_R (packing, transforming),
  - the log has the game's kill events (dump v4+) for player units and none names this entity.
Fight: deaths chained within FIGHT_GAP s and FIGHT_R map units of the fight's recent deaths.
Its window starts at the first HP loss within FIGHT_R in the PRE s before the first death.
"""
import math

FIGHT_GAP, FIGHT_R, PRE, TRANSFORM_R, HOLD_AFTER = 20.0, 40.0, 30.0, 3.0, 10.0


def last_seen(frames):
    """id -> last sample time it was in any list."""
    last = {}
    for fr in frames:
        for e in fr["entities"]:
            last[e["id"]] = fr["t"]
    return last


def killed_ids(frames, events):
    """Victim ids from the game's kill events, or None if they name no player entity (then unused)."""
    if not events:
        return None
    ids = {e["id"] for fr in frames for e in fr["entities"]}
    victims = set()
    for ev in events:
        v = ev.get("victim", "") if ev.get("type") == "kill" else ""
        if v.startswith("e") and v[1:].isdigit():
            victims.add(int(v[1:]))
    return victims if victims & ids else None


def find_deaths(frames, cost_of, events=None):
    deaths = []
    prev = {}
    last = last_seen(frames)
    killed = killed_ids(frames, events)
    for i, fr in enumerate(frames):
        cur = {e["id"]: e for e in fr["entities"]}
        if prev:
            owners_alive = {e["owner"] for e in fr["entities"]}
            new = [e for k, e in cur.items() if k not in prev and e["x"] is not None]
            for k, e in prev.items():
                if k in cur or e["owner"] not in owners_alive or e["x"] is None:
                    continue
                if last.get(k, -1) > fr["t"] or (killed is not None and k not in killed):
                    continue
                if any(n["owner"] == e["owner"] and math.hypot(n["x"] - e["x"], n["z"] - e["z"]) <= TRANSFORM_R
                       for n in new):
                    continue
                deaths.append({"t": fr["t"], "owner": e["owner"], "id": k, "bp": e["bp"], "kind": e["kind"],
                               "x": e["x"], "z": e["z"], "vis": e.get("vis") or 0,
                               "hp_last": e.get("hp"), "cost": cost_of(e["bp"])})
        prev = cur
    return deaths


def cluster(deaths):
    fights = []
    for d in sorted(deaths, key=lambda d: d["t"]):
        best = None
        for f in fights:
            if d["t"] - f["last"] > FIGHT_GAP:
                continue
            recent = [x for x in f["deaths"] if d["t"] - x["t"] <= FIGHT_GAP]
            if any(math.hypot(d["x"] - x["x"], d["z"] - x["z"]) <= FIGHT_R for x in recent):
                best = f
                break
        if best is None:
            best = {"deaths": [], "last": d["t"]}
            fights.append(best)
        best["deaths"].append(d)
        best["last"] = d["t"]
    return fights


def summarize(frames, fights, pids):
    times = [f["t"] for f in frames]

    def idx(t):
        lo, hi = 0, len(times) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if times[mid] < t:
                lo = mid + 1
            else:
                hi = mid
        return lo

    out = []
    for n, f in enumerate(fights):
        ds = f["deaths"]
        if len(ds) < 2 and ds[0]["kind"] != "m":
            continue                      # a lone building or villager death is not a fight
        cx = sum(d["x"] for d in ds) / len(ds)
        cz = sum(d["z"] for d in ds) / len(ds)
        r = max(15.0, max(math.hypot(d["x"] - cx, d["z"] - cz) for d in ds) + 10.0)
        t0, t1 = ds[0]["t"], ds[-1]["t"]
        # start: first HP loss near the fight in the PRE s before the first death
        start = t0
        i0 = idx(t0 - PRE)
        prev_hp = {}
        for fr in frames[i0:idx(t1) + 1]:
            for e in fr["entities"]:
                if e.get("hp") is None or e["x"] is None:
                    continue
                if math.hypot(e["x"] - cx, e["z"] - cz) <= r:
                    if e["id"] in prev_hp and e["hp"] < prev_hp[e["id"]] - 0.5 and fr["t"] < start:
                        start = fr["t"]
                prev_hp[e["id"]] = e["hp"]
        # HP lost per side inside the circle during the fight (truth; review only)
        hp_lost = {p: 0.0 for p in pids}
        prev_hp = {}
        for fr in frames[idx(start) - 1 if idx(start) > 0 else 0: idx(t1) + 1]:
            for e in fr["entities"]:
                if e.get("hp") is None or e["x"] is None:
                    continue
                inside = math.hypot(e["x"] - cx, e["z"] - cz) <= r
                if inside and e["id"] in prev_hp and e["hp"] < prev_hp[e["id"]]:
                    hp_lost[e["owner"]] += prev_hp[e["id"]] - e["hp"]
                prev_hp[e["id"]] = e["hp"]
        for d in ds:
            if d["hp_last"]:
                hp_lost[d["owner"]] += d["hp_last"]

        def army_near(t):
            fr = frames[min(idx(t), len(frames) - 1)]
            v = {p: 0.0 for p in pids}
            for e in fr["entities"]:
                if e["kind"] == "m" and e["x"] is not None and math.hypot(e["x"] - cx, e["z"] - cz) <= r * 1.5:
                    v[e["owner"]] += e.get("_cost", 0.0)
            return v
        out.append({"n": len(out) + 1, "start": start, "end": t1, "x": round(cx, 1), "z": round(cz, 1),
                    "r": round(r, 1), "hp_lost": {str(p): round(v) for p, v in hp_lost.items()},
                    "army_before": {str(p): round(v) for p, v in army_near(start - 5).items()},
                    "army_after": {str(p): round(v) for p, v in army_near(t1 + HOLD_AFTER).items()},
                    "deaths": [{"t": d["t"], "owner": d["owner"], "id": d["id"], "bp": d["bp"], "kind": d["kind"],
                                "x": round(d["x"]), "z": round(d["z"]), "vis": d["vis"], "cost": d["cost"]}
                               for d in ds]})
    return out


def fights_for(tl, cost_of):
    frames = tl["frames"]
    for fr in frames:                     # cost per entity for army value near the fight
        for e in fr["entities"]:
            e["_cost"] = cost_of(e["bp"]) if e["kind"] == "m" else 0.0
    pids = [p["idx"] for p in tl["players"]]
    res = summarize(frames, cluster(find_deaths(frames, cost_of, tl.get("events"))), pids)
    for fr in frames:
        for e in fr["entities"]:
            e.pop("_cost", None)
    return res
