"""Safe natural food of the opponent and when it runs out, from what the observer saw.

Natural food: berries, deer, boar, carcasses, wild sheep (resource nodes) and the opponent's own sheep.
Farms are endless and not counted; farms seen are reported so the move to farms can be anticipated.

Safety of a food spot for player P against player O (owner's definition): a score, sum of three
terms each in [-1, 1]; the spot is safe for P when the score is > 0.
- base (static, map): (dO - dP) / (dO + dP), dP / dO = distance to P's / O's main Town Center
  (0 on the equidistant line), plus TC_COVER_BONUS within TC_COVER of P's main TC.
- aura (static radius): every army group (scouts excluded) projects value * (1 - d / AURA_R) within
  AURA_R; (P's - O's) / (P's + O's + AURA_V0). AURA_V0 keeps a lone small group from swinging it.
- arrival (dynamic): who gets there first. O's main army at distance dE; P's defence at
  dD = min(P's main army, P's main TC: villagers can flee there). (dE - dD) / (dE + dD), scaled by
  O's share of the two main armies' value; more negative as O's army closes in. Same speed assumed
  for both sides, so no speed constant (ETA shown at ARMY_SPEED).
Constants are first guesses.

Active and potential (owner's model): the opponent is assumed to eat the safest food first unless
scouted otherwise.
- active: their sheep seen (SHEEP_FOOD each, last ACTIVE_MEMORY s), carcasses within ACTIVE_R of their
  main TC, and their main berry group by the TC. Every start has one, so before it is scouted it is
  assumed at the point reflection of the observer's own TC berry group through the two TCs, with the
  observer's own starting amount (labelled assumed); once any of it is scouted, the amounts seen are used.
- potential: every other food group (berries, deer, boar, carcasses; FOOD_GROUP_R clustering) the
  observer has scouted and that scores safe for them, best score first; "next" = the safest of them,
  where they go when the active food runs out.
- once the active food is gone, the eating moves on to the safest scouted group ("current"), then the
  next; each scouted spot's assumed eating starts over when the observer looks at it again.
- unsafe but taken: groups scoring unsafe for them where their gatherers were seen in the last
  GATHER_MEMORY s; one event per group (raid window).
- consumption: food gatherers = max(food gatherers seen in the last GATHER_MEMORY s, FOOD_SHARE x
  estimated villagers; the latter labelled assumed); those seen at a potential spot or a farm don't eat
  active food. Active ETA = active food / (active gatherers x rate).

Observer knowledge only:
- Opponent's main TC: its position once seen; before that, assumed at the mirror of the observer's
  own TC through the map centre (labelled assumed).
- Opponent's army: military seen in the last ARMY_MEMORY s at its last-seen positions, minus those
  seen dying. Own army: as it is.
- Food amounts: remaining amount at the last look. Consumption per spot: opponent villagers seen
  gathering there x rate, carried forward while out of sight; measured from two looks when nobody is
  seen there. A spot seen empty (gone while in sight) counts 0.
"""
import math

FOOD_NODES = ("berry", "deer", "boar", "carcass", "sheep")
SHEEP_FOOD = 200.0            # a sheep's food (wild sheep node amount in the dump)
ARMY_MEMORY = 60.0
GROUP_R = 30.0                # army group: units chained within this distance
REACH = 8.0                   # villager at a food spot
GATHER_MEMORY = 30.0          # gatherers seen at a spot count for this long
STEP = 5.0
WARN_ETA = 90.0               # event when safe food runs out within this many seconds
TC_COVER = 40.0               # map units around the defender's main TC counted as under its fire (guess)
TC_COVER_BONUS = 0.5
AURA_R = 60.0                 # army aura radius, map units (15 tiles; guess)
AURA_V0 = 200.0               # resources; damps the aura of small groups
ARMY_SPEED = 5.0              # map units / s, only for the ETA shown
ACTIVE_R = 40.0               # carcasses this close to their main TC count as active (sheep being eaten)
ACTIVE_MEMORY = 30.0          # their sheep seen this recently count as active
TC_BERRY_R = 60.0             # the main berry group lies within this of the main TC
FOOD_GROUP_R = 15.0           # food spots chained within this form one group
FOOD_SHARE = 0.5              # assumed share of their villagers on food when fewer are seen
FARM_R = 9.0


def groups(units):
    """units: [(x, z, value)] -> [(cx, cz, value, n)] by single linkage within GROUP_R."""
    left, out = list(units), []
    while left:
        grp = [left.pop()]
        i = 0
        while i < len(grp):
            x, z, _ = grp[i]
            near = [u for u in left if math.hypot(u[0] - x, u[1] - z) <= GROUP_R]
            for u in near:
                left.remove(u)
            grp += near
            i += 1
        v = sum(u[2] for u in grp) or 1e-9
        out.append((sum(u[0] * u[2] for u in grp) / v, sum(u[1] * u[2] for u in grp) / v, v, len(grp)))
    return out


def food_groups(items):
    """items: [(key, type, x, z, amount)] -> [{type, x, z, left, keys}] chained within FOOD_GROUP_R by type."""
    left, out = list(items), []
    while left:
        grp = [left.pop()]
        i = 0
        while i < len(grp):
            _, ty, x, z, _ = grp[i]
            near = [u for u in left if u[1] == ty and math.hypot(u[2] - x, u[3] - z) <= FOOD_GROUP_R]
            for u in near:
                left.remove(u)
            grp += near
            i += 1
        n = len(grp)
        out.append({"type": grp[0][1], "x": sum(u[2] for u in grp) / n, "z": sum(u[3] for u in grp) / n,
                    "left": sum(u[4] for u in grp), "keys": [u[0] for u in grp]})
    return out


def true_food(nodes, fr, p, tcp):
    """Hidden-information check of the estimate (review only): the real amounts of the same food, and
    what P's food gatherers are really on. nodes: the current snapshot (all food with true amounts)."""
    food = [n for n in nodes if n["type"] in FOOD_NODES and n["x"] is not None and (n.get("left") or 0) > 0]
    d = lambda n: math.hypot(n["x"] - tcp[0], n["z"] - tcp[1])
    carc = sum(n["left"] for n in food if n["type"] == "carcass" and d(n) <= ACTIVE_R)
    berries = [(n["id"], "berry", n["x"], n["z"], n["left"]) for n in food if n["type"] == "berry"]
    tcb = [g for g in food_groups(berries) if math.hypot(g["x"] - tcp[0], g["z"] - tcp[1]) <= TC_BERRY_R]
    tcb = min(tcb, key=lambda g: math.hypot(g["x"] - tcp[0], g["z"] - tcp[1]))["left"] if tcb else 0.0
    n_sheep = sum(1 for sh in fr.get("sheep_o", []) if sh[1] == p)
    # what their food gatherers are really on
    farms = [(e["x"], e["z"]) for e in fr["entities"] if e["owner"] == p and e["x"] is not None
             and (e["bp"] or "").startswith("building_resource_farm")]
    sheep_xy = [(sh[2], sh[3]) for sh in fr.get("sheep_o", []) if sh[1] == p]
    eating = {}
    for e in fr["entities"]:
        if e["owner"] != p or e["kind"] != "w" or e.get("res") != 1 or e["x"] is None:
            continue
        what = "other"
        near = min(food, key=lambda n: math.hypot(n["x"] - e["x"], n["z"] - e["z"]), default=None)
        if any(math.hypot(e["x"] - x, e["z"] - z) <= FARM_R for x, z in farms):
            what = "farm"
        elif near is not None and math.hypot(near["x"] - e["x"], near["z"] - e["z"]) <= REACH:
            what = near["type"]
        elif any(math.hypot(e["x"] - x, e["z"] - z) <= REACH for x, z in sheep_xy):
            what = "sheep"
        eating[what] = eating.get(what, 0) + 1
    return {"active": round(n_sheep * SHEEP_FOOD + carc + tcb), "sheep": n_sheep, "carcass": round(carc),
            "tcBerries": round(tcb), "eating": eating}


def score(x, z, g):
    """Safety score of spot (x, z) for the target P, from geometry row g: (total, base, aura, arrival)."""
    tp, to = g["tcP"], g["tcO"]
    dp, do = math.hypot(x - tp[0], z - tp[1]), math.hypot(x - to[0], z - to[1])
    base = (do - dp) / ((do + dp) or 1.0) + (TC_COVER_BONUS if dp <= TC_COVER else 0.0)

    def aura(gs):
        return sum(v * max(0.0, 1.0 - math.hypot(x - gx, z - gz) / AURA_R) for gx, gz, v in gs)
    ap, ao = aura(g["groupsP"]), aura(g["groupsO"])
    aur = (ap - ao) / (ap + ao + AURA_V0)
    arr = 0.0
    if g["armyO"]:
        de = math.hypot(x - g["armyO"][0], z - g["armyO"][1])
        dd = dp
        if g["armyP"]:
            dd = min(dd, math.hypot(x - g["armyP"][0], z - g["armyP"][1]))
        vo, vp = g["armyO"][2], (g["armyP"][2] if g["armyP"] else 0.0)
        arr = (de - dd) / ((de + dd) or 1.0) * (vo / (vo + vp) if vo + vp else 0.0)
    return base + aur + arr, base, aur, arr


def classify(x, z, g):
    """(safe, score, parts) for spot (x, z)."""
    sc = score(x, z, g)
    return sc[0] > 0, sc[0], sc[1:]


def food_forecast(tl, explored, cost_of, deaths, rate, estimates=None):
    frames, snaps = tl["frames"], tl.get("nodes") or []
    pids = [p["idx"] for p in tl["players"]]
    if not snaps:
        return {}, ["no resource nodes in this dump: food forecast off"]
    from analyze import load_sight, sight_cells, in_sight
    sight = load_sight()
    # map centre: middle of all resource nodes (map size and layout are known to every player)
    xs = [n["x"] for n in snaps[0]["nodes"] if n["x"] is not None]
    zs = [n["z"] for n in snaps[0]["nodes"] if n["x"] is not None]
    centre = ((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2)
    main_tc = {}
    for e in frames[0]["entities"]:
        if "town_center" in (e["bp"] or "") and "dummy" not in e["bp"] and e["x"] is not None:
            main_tc.setdefault(e["owner"], (e["id"], e["x"], e["z"]))
    # each player's own main berry group at the start (map knowledge: their own base)
    berries0 = [(n["id"], "berry", n["x"], n["z"], n.get("left") or 0.0) for n in snaps[0]["nodes"]
                if n["type"] == "berry" and n["x"] is not None]
    own_berries = {}
    for q, (_, qx, qz) in main_tc.items():
        gs = [g for g in food_groups(berries0) if math.hypot(g["x"] - qx, g["z"] - qz) <= TC_BERRY_R]
        if gs:
            own_berries[q] = min(gs, key=lambda g: math.hypot(g["x"] - qx, g["z"] - qz))
    dead_seen = {}
    for d in deaths:
        for o in pids:
            if d["owner"] == o or ((d.get("vis") or 0) >> (o - 1)) & 1:
                dead_seen.setdefault(o, {})[d["id"]] = d["t"]
    out, warnings = {}, []
    for o in pids:
        bit = 1 << (o - 1)
        for p in pids:
            if p == o or o not in main_tc or p not in main_tc:
                continue
            tco = main_tc[o][1:]
            tcp_true, tcp_seen = main_tc[p], None
            army_seen = {}             # id -> (t, x, z, value)
            spots = {}                 # node id -> dict(x, z, left, ts, r, gat_t)
            sheep = {}                 # sheep id -> (t, x, z)
            farms = {}                 # farm id -> t last seen
            rows, events, warned = [], [], False
            est_rows = (estimates or {}).get(f"{o}->{p}") or []
            gat_seen = {}              # their villager id -> (t, "farm" | "other", x, z)
            eaten, eaten_ts, warned_ids, risky_warned = {}, {}, set(), set()   # assumed eating per scouted spot since its last look
            act = {"t": None, "cons": 0.0, "sheep": 0.0, "sheep_t": -1e9, "carc": 0.0, "carc_t": -1e9,
                   "berry": None, "berry_t": -1e9, "berry_xy": None, "berry_assumed": True, "cur": None}
            si, next_t = -1, frames[0]["t"]
            for fi, fr in enumerate(frames):
                t = fr["t"]
                ents = fr["entities"]
                vis = [e for e in ents if e["owner"] == p and e["vis"] and e["vis"] & bit and e["x"] is not None]
                for e in vis:
                    if e["id"] == tcp_true[0]:
                        tcp_seen = tcp_true[1:]
                    if e["kind"] == "m" and "scout" not in (e["bp"] or ""):
                        army_seen[e["id"]] = (t, e["x"], e["z"], cost_of(e["bp"]))
                    if (e["bp"] or "").startswith("building_resource_farm"):
                        farms[e["id"]] = t
                for sh in fr.get("sheep_o", []):
                    if sh[1] == p and sh[4] and sh[4] & bit:
                        sheep[sh[0]] = (t, sh[2], sh[3])
                # node snapshots up to t: amounts of food spots in sight
                new_snap = False
                while si + 1 < len(snaps) and snaps[si + 1]["t"] <= t:
                    si += 1
                    new_snap = True
                gat = [e for e in vis if e["kind"] == "w" and e.get("res") == 1]
                if new_snap:
                    snap = snaps[si]
                    present = set()
                    for n in snap["nodes"]:
                        if n["type"] not in FOOD_NODES or n["x"] is None or n.get("left") is None:
                            continue
                        present.add(n["id"])
                        if not (n["vis"] is not None and (n["vis"] >> (o - 1)) & 1):
                            continue
                        s = spots.get(n["id"])
                        if s is None:
                            spots[n["id"]] = s = {"x": n["x"], "z": n["z"], "left": n["left"], "ts": snap["t"],
                                                  "r": 0.0, "gat_t": -1e9, "type": n["type"]}
                        else:
                            if snap["t"] - s["gat_t"] > GATHER_MEMORY and snap["t"] > s["ts"]:
                                s["r"] = max(0.0, (s["left"] - n["left"]) / (snap["t"] - s["ts"]))
                            s["x"], s["z"], s["left"], s["ts"] = n["x"], n["z"], n["left"], snap["t"]
                    # spots gone while in the observer's sight: eaten up
                    # (every snapshot lists all gaia_/resource_ nodes, so missing = gone)
                    if spots:
                        grid = sight_cells([e for e in ents if e["owner"] == o], sight)
                        for nid, s in spots.items():
                            if nid not in present and s["left"] > 0 and in_sight(grid, s["x"], s["z"]):
                                s["left"], s["ts"], s["r"] = 0.0, snap["t"], 0.0
                farm_xy = [(e["x"], e["z"]) for e in vis if (e["bp"] or "").startswith("building_resource_farm")]
                for e in gat:
                    where = "other"
                    if any(math.hypot(e["x"] - fx, e["z"] - fz) <= FARM_R for fx, fz in farm_xy):
                        where = "farm"
                    gat_seen[e["id"]] = (t, where, e["x"], e["z"])
                # gatherers seen at a spot set its consumption
                if gat and spots:
                    cnt = {}
                    for e in gat:
                        nid = min(spots, key=lambda k: math.hypot(spots[k]["x"] - e["x"], spots[k]["z"] - e["z"]))
                        if math.hypot(spots[nid]["x"] - e["x"], spots[nid]["z"] - e["z"]) <= REACH:
                            cnt[nid] = cnt.get(nid, 0) + 1
                    for nid, c in cnt.items():
                        spots[nid]["r"] = c * rate
                        spots[nid]["gat_t"] = t
                if t < next_t:
                    continue
                next_t = t + STEP
                # geometry: main TCs and main armies, as the observer knows them
                tcp = tcp_seen or (2 * centre[0] - tco[0], 2 * centre[1] - tco[1])
                dead = dead_seen.get(o, {})
                ap = [(x, z, v) for i, (ts, x, z, v) in army_seen.items()
                      if t - ts <= ARMY_MEMORY and not (i in dead and dead[i] <= t)]
                ao = [(e["x"], e["z"], cost_of(e["bp"])) for e in ents
                      if e["owner"] == o and e["kind"] == "m" and e["x"] is not None and "scout" not in (e["bp"] or "")]
                gp, go = groups(ap), groups(ao)
                mp = max(gp, key=lambda g: g[2]) if gp else None
                mo = max(go, key=lambda g: g[2]) if go else None
                vp, vo = (mp[2] if mp else 0.0), (mo[2] if mo else 0.0)
                geo = {"tcP": [round(tcp[0], 1), round(tcp[1], 1)], "tcO": [round(tco[0], 1), round(tco[1], 1)],
                       "tcAssumed": tcp_seen is None,
                       "armyP": [round(mp[0]), round(mp[1]), round(vp)] if mp else None,
                       "armyO": [round(mo[0]), round(mo[1]), round(vo)] if mo else None}
                geo["groupsP"] = [[round(x), round(z), round(v)] for x, z, v, _ in gp]
                geo["groupsO"] = [[round(x), round(z), round(v)] for x, z, v, _ in go]
                # known food spots now (amount at last look, minus what gatherers seen there eat)
                items = []
                for nid, sp in spots.items():
                    if eaten_ts.get(nid) != sp["ts"]:       # looked at again: assumed eating starts over
                        eaten[nid], eaten_ts[nid] = 0.0, sp["ts"]
                    lf = max(0.0, sp["left"] - sp["r"] * (t - sp["ts"]) - eaten[nid])
                    if lf > 0:
                        items.append((nid, sp["type"], sp["x"], sp["z"], lf))
                fgroups = food_groups(items)
                for g in fgroups:
                    g["score"] = score(g["x"], g["z"], geo)[0]
                    g["d_tc"] = math.hypot(g["x"] - tcp[0], g["z"] - tcp[1])
                # active pool, eaten safest first (sheep, then carcasses at their TC, then their TC berries).
                # Each part is a running estimate: drained by the assumed eating since the last row, reset to
                # what the observer sees whenever they look again.
                last_sheep_t = max((ts for ts, x, z in sheep.values()), default=None)
                n_sheep = sum(1 for ts, x, z in sheep.values() if t - ts <= ACTIVE_MEMORY)
                if last_sheep_t is not None and last_sheep_t > act["sheep_t"]:
                    act["sheep"], act["sheep_t"] = n_sheep * SHEEP_FOOD, last_sheep_t
                carc_sp = [(nid, sp) for nid, sp in spots.items() if sp["type"] == "carcass"
                           and math.hypot(sp["x"] - tcp[0], sp["z"] - tcp[1]) <= ACTIVE_R]
                carc_t = max((sp["ts"] for _, sp in carc_sp), default=None)
                if carc_t is not None and carc_t > act["carc_t"]:
                    seen = sum(sp["left"] for _, sp in carc_sp)
                    full = all(sp["ts"] == carc_t for _, sp in carc_sp)
                    # a partial look (some spots seen now, others at older looks) can only lower the estimate
                    act["carc"] = seen if full else min(act["carc"], seen)
                    act["carc_t"] = carc_t
                berry_raw = [(nid, "berry", sp["x"], sp["z"], sp["left"]) for nid, sp in spots.items()
                             if sp["type"] == "berry"]
                tcb = [g for g in food_groups(berry_raw) if math.hypot(g["x"] - tcp[0], g["z"] - tcp[1]) <= TC_BERRY_R]
                tcb = min(tcb, key=lambda g: math.hypot(g["x"] - tcp[0], g["z"] - tcp[1])) if tcb else None
                if tcb is not None:
                    bt = max(spots[k]["ts"] for k in tcb["keys"])
                    if bt > act["berry_t"]:
                        full = all(spots[k]["ts"] == bt for k in tcb["keys"])
                        first = act["berry_assumed"] or act["berry"] is None
                        act["berry"] = tcb["left"] if (full or first) else min(act["berry"], tcb["left"])
                        act["berry_t"] = bt
                    act["berry_xy"], act["berry_assumed"] = (tcb["x"], tcb["z"]), False
                elif act["berry_assumed"] and own_berries.get(o) and act["berry"] is None:
                    ob = own_berries[o]       # mirror of own TC berries through the two TCs
                    act["berry"], act["berry_t"] = ob["left"], t
                if act["berry_assumed"] and own_berries.get(o):
                    ob = own_berries[o]
                    act["berry_xy"] = (tcp[0] - (ob["x"] - tco[0]), tcp[1] - (ob["z"] - tco[1]))
                eat = act["cons"] * (t - act["t"]) if act["t"] is not None else 0.0
                for part in ("sheep", "carc", "berry"):
                    if act[part]:
                        take = min(act[part], eat)
                        act[part] -= take
                        eat -= take
                act["t"] = t
                spill = eat              # eating left over once the active food is gone
                sheep_food, carc, berries = act["sheep"], act["carc"], act["berry"] or 0.0
                active = sheep_food + carc + berries
                tcb_row = None if act["berry"] is None or act["berry_xy"] is None else \
                    [round(act["berry_xy"][0]), round(act["berry_xy"][1]), round(berries), act["berry_assumed"]]
                active_keys = {nid for nid, _ in carc_sp} | (set(tcb["keys"]) if tcb else set())
                # potential: other scouted groups that are safe for them, best first
                pot = sorted((g for g in fgroups if not set(g["keys"]) & active_keys and g["score"] > 0),
                             key=lambda g: -g["score"])
                # active food gone: the villagers move on to the safest scouted group and stay there while it
                # has food and is still safe (no hopping as scores shift), then the next safest
                for g in pot:
                    g["id"] = min(g["keys"])
                if active > 1:
                    act["cur"] = None
                stay = [g for g in pot if g["id"] == act["cur"]]
                if stay:
                    pot = stay + [g for g in pot if g is not stay[0]]
                for g in pot:
                    if spill <= 0:
                        break
                    for k in g["keys"]:
                        sp = spots[k]
                        avail = max(0.0, sp["left"] - sp["r"] * (t - sp["ts"]) - eaten[k])
                        take = min(avail, spill)
                        eaten[k] += take
                        g["left"] -= take
                        spill -= take
                        if spill <= 0:
                            break
                pot = [g for g in pot if g["left"] > 1]
                unsafe = sum(g["left"] for g in fgroups if g["score"] <= 0 and not set(g["keys"]) & active_keys)
                potential = sum(g["left"] for g in pot)
                cur = pot[0] if active <= 1 and pot else None      # the group they are assumed on now
                act["cur"] = cur["id"] if cur else None
                nxt = (pot[1] if len(pot) > 1 else None) if cur else (pot[0] if pot else None)
                # consumption: assume the safest (active) food unless gatherers are seen elsewhere
                pot_xy = [(g["x"], g["z"]) for g in pot] + [(g["x"], g["z"]) for g in fgroups
                                                           if g["score"] <= 0 and not set(g["keys"]) & active_keys]
                recent = [(w, x, z) for ts, w, x, z in gat_seen.values() if t - ts <= GATHER_MEMORY]
                elsewhere = sum(1 for w, x, z in recent if w == "farm" or
                                any(math.hypot(x - px_, z - pz_) <= FOOD_GROUP_R for px_, pz_ in pot_xy))
                n_est = (est_rows[fi]["n_est"] if fi < len(est_rows) else 0) or 0
                assumed_n = FOOD_SHARE * n_est
                n_food = max(len(recent), assumed_n)
                n_active = max(0.0, n_food - elsewhere)
                cons = n_active * rate
                act["cons"] = cons
                feeding = active if active > 1 else (cur["left"] if cur else 0.0)
                eta = feeding / cons if cons > 0 and feeding > 0 else None
                # unsafe but taken: groups that score unsafe for them where their gatherers were seen recently
                risky = []
                for g in fgroups:
                    if g["score"] > 0 or set(g["keys"]) & active_keys:
                        continue
                    n_there = sum(1 for w, x, z in recent if w != "farm" and
                                  min(math.hypot(x - spots[k]["x"], z - spots[k]["z"]) for k in g["keys"]) <= REACH)
                    if n_there:
                        gid = min(g["keys"])
                        risky.append({"type": g["type"], "x": round(g["x"]), "z": round(g["z"]), "left": round(g["left"]),
                                      "score": round(g["score"], 2), "n": n_there})
                        if gid not in risky_warned:
                            risky_warned.add(gid)
                            events.append({"t": t, "name": f"Gathering unsafe food: {g['type']} (score {g['score']:+.2f})",
                                           "why": f"{n_there} of their villagers seen on {g['type']} at "
                                                  f"({g['x']:.0f}, {g['z']:.0f}), {g['left']:.0f} left; raid window"})
                n_farms = sum(1 for ts in farms.values() if t - ts <= 600)
                truth = true_food(snaps[si]["nodes"] if si >= 0 else [], fr, p, tcp_true[1:])
                rows.append({"t": t, "active": round(active), "sheep": n_sheep, "carcass": round(carc),
                             "tcBerries": tcb_row, "potential": round(potential), "potGroups": len(pot),
                             "unsafe": round(unsafe),
                             "next": None if nxt is None else {"type": nxt["type"], "x": round(nxt["x"]),
                                                               "z": round(nxt["z"]), "left": round(nxt["left"]),
                                                               "score": round(nxt["score"], 2)},
                             "current": None if cur is None else {"type": cur["type"], "x": round(cur["x"]),
                                                                  "z": round(cur["z"]), "left": round(cur["left"]),
                                                                  "score": round(cur["score"], 2)},
                             "nFood": round(n_food, 1), "nActive": round(n_active, 1),
                             "consAssumed": len(recent) < assumed_n, "cons": round(cons, 2),
                             "eta": None if eta is None else round(eta), "farms": n_farms,
                             "safe": round(active + potential), "geo": geo, "risky": risky,
                             "true": truth})     # hidden information: review only ("Show true values")
                on_now = "active" if cur is None else cur["id"]
                if eta is not None and eta <= WARN_ETA and not (warned if on_now == "active" else on_now in warned_ids):
                    if on_now == "active":
                        warned = True
                    else:
                        warned_ids.add(on_now)      # once per group
                    where = (f"next safest: {nxt['type']} at ({nxt['x']:.0f}, {nxt['z']:.0f}), "
                             f"score {nxt['score']:+.2f}") if nxt else "no scouted safe food left: farms or unsafe food"
                    what = (f"active safe food {active:.0f} ({sheep_food:.0f} on sheep, TC berries "
                            f"{'assumed' if tcb_row and tcb_row[3] else 'seen'})") if cur is None else \
                        f"the {cur['type']} they moved on to ({cur['left']:.0f} left, score {cur['score']:+.2f})"
                    events.append({"t": t, "name": f"{'Active safe food' if cur is None else cur['type'].capitalize() + ' (assumed current)'} "
                                                   f"runs out in ~{int(eta)} s",
                                   "why": f"{what}, {n_active:.0f} on it{' (assumed)' if len(recent) < assumed_n else ''}; "
                                          f"{where}; {n_farms} farms seen"})
                elif on_now == "active" and (eta is None or eta > 2 * WARN_ETA):
                    warned = False
            out[f"{o}->{p}"] = {"rows": rows, "events": events}
    return out, warnings
