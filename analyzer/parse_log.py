"""Parse A4D lines from AoE4 warnings.log into a timeline JSON.

Usage: python parse_log.py warnings.log timeline.json [--session N]
A log may hold several dump sessions (each starts with an A4D|CAPS line);
the last one is used unless --session is given (0-based).
"""
import argparse
import json
import sys

RES = ["food", "wood", "gold", "stone"]
CTX_TYPES = {"K": "kill", "U": "upgrade", "UQ": "upgrade_start", "UX": "upgrade_cancel", "C": "construct_done",
             "CS": "construct_start", "CW": "construct_worker", "CX": "construct_cancel", "SP": "point"}



def _sm_merge(rows, t, vals):
    """Append the state at t: the previous state with vals laid over it (same t -> one entry)."""
    if rows and rows[-1][0] == t:
        rows[-1][1].update(vals)
        return
    d = dict(rows[-1][1]) if rows else {}
    d.update(vals)
    rows.append([t, d])

def _f(x):
    return float(x) if x != "" else None


def _fs(x):
    """number if it is one, else the raw text (unknown API return types), None if empty"""
    try:
        return _f(x)
    except ValueError:
        return x


def split_sessions(lines):
    sessions, cur = [], None
    for line in lines:
        i = line.find("A4D|")
        if i < 0:
            continue
        rec = line[i:].rstrip("\r\n").split("|")
        if rec[1] == "CAPS":
            cur = [rec]
            sessions.append(cur)
        elif cur is not None:
            cur.append(rec)
    return sessions


def _pass_grid(pas, terrain):
    """v7 per-tile raw values -> {x0, z0, step, cell, cover, d, covers, caps}; None without the grid."""
    if not pas["rows"] or terrain is None:
        return None
    rows = terrain["rows"]
    get = lambda k: [[(c[k] if c else None) for c in pas["rows"].get(r, [])] for r in range(rows)]  # noqa: E731
    return {"x0": terrain["x0"], "z0": terrain["z0"], "step": terrain["step"], "caps": pas["caps"],
            "covers": {str(k): v for k, v in pas["covers"].items()},
            "cell": get(0), "cover": get(1), "d": get(2), "dn": get(3)}


def parse_session(recs):
    caps = {}
    for kv in recs[0][2:]:
        k, _, v = kv.partition("=")
        caps[k] = v == "1"
    players = {}
    frames = {}
    order = []
    nodes = []          # resource-node snapshots: {"t", "full", "nodes": [...]}
    api, io_type, node_method = [], None, None
    events, terrain = [], None   # v4: K/U game events, terrain height grid
    pas = {"caps": None, "covers": {}, "rows": {}}   # v7: where land units can stand
    sizes, heading = {}, {}                          # v7: radius per blueprint, building headings
    income, built, queue_hd, dest, bcost = [], [], {}, {}, {}   # v18 events / records
    psm, smk = {}, {}            # v18: player state models {player: [[t, {key: value}]]}; keys per blueprint
    esm = {}                     # v11: building state-model values {id: [[t, {key: value}]]} (UI_Progress, ...)
    abil, abk, gev = [], [], []  # v12: ability events [t, event, caster, ability, target], their context fields, GE_* names
    fast = []                    # v6: fight samples [{"t", "u": {id: [x, z, hp, target]}}]
    hits, shots = [], []         # v9: [t, attacker, victim, damage, hp after]; [t, "F"/"L", attacker, projectile,
                                 #     target, x, z] (target 0 = ground shot at x, z)
    # v5 "delta" nodes: start scan + changes (NC) + removals (NX); the snapshots the analysis reads are
    # rebuilt from that state: every NODE_STEP s the tracked objects, every NODE_FULL s everything.
    # Trees carry no visibility after the start scan (vis None: the analysis uses sight radii).
    delta, state, last_emit, last_full = False, {}, None, None

    def emit(t):
        nonlocal last_emit, last_full
        full = t - last_full >= NODE_FULL
        lst = []
        for nd in state.values():
            tr = tracked(nd["bp"])
            if full or tr:
                lst.append(dict(nd) if tr else dict(nd, vis=None))
        nodes.append({"t": t, "full": full, "nodes": lst})
        last_emit = t
        if full:
            last_full = t

    def frame(t):
        if t not in frames:
            frames[t] = {"t": t, "players": {}, "entities": []}
            order.append(t)
        return frames[t]

    def add_entity(fr, k, f):
        bp = f[1]
        # player-owned sheep: kept apart as food sources for gather classification
        if bp and bp.startswith("gaia_herdable"):
            if f[2] and f[3]:
                fr.setdefault("sheep", []).append((float(f[2]), float(f[3])))
                # with owner and visibility, for the food forecast: [id, owner, x, z, vismask]
                fr.setdefault("sheep_o", []).append([int(f[0]), k, float(f[2]), float(f[3]),
                                                     int(f[4]) if len(f) > 4 and f[4] else None])
            return
        # keep only player-made objects; drop props (wpn_*, falcons, nets, holy sites)
        if bp and not (bp.startswith("unit_") or bp.startswith("building_")):
            return
        f = list(f)
        # buildings (incl. packed Mongol buildings, outposts) are never army
        if bp.startswith("building_"):
            f[5] = "o"
        # "worker" means villager only; heroes that gather (Jeanne d'Arc) are army,
        # fishing boats and other gatherers are their own class "e"
        elif f[5] == "w" and "villager" not in bp:
            f[5] = "m" if "jeanne" in bp else "e"
        fr["entities"].append({
            "owner": k,
            "id": int(f[0]) if f[0] else None,
            "bp": f[1] or None,
            "x": _f(f[2]), "z": _f(f[3]),
            "vis": int(f[4]) if f[4] else None,
            "kind": f[5],
            "idle": None if f[6] == "" else f[6] == "1",
            "squad": int(float(f[7])) if len(f) > 7 and f[7] else None,
            "hp": _f(f[8]) if len(f) > 8 else None,
            "flags": f[9] if len(f) > 9 else None,
            "build": _f(f[10]) if len(f) > 10 else None,
            "queue": _f(f[11]) if len(f) > 11 else None,
            "target": int(f[12]) if len(f) > 12 and f[12] else None,
            "heading": int(f[13]) if len(f) > 13 and f[13] else None,      # v21: degrees, 5 deg steps
        })

    def settle(k, t):
        """v20: player k's entity state as of second t -> that frame's entities"""
        fr = frame(t)
        for f in ecur.get(k, {}).values():
            try:
                add_entity(fr, k, f)
            except (IndexError, ValueError):
                pass
        epend.pop(k, None)

    bad = ebad = 0
    # v20+: E lines are keyframes of a delta stream (the V line sits before the session's CAPS line, so the ED / EX lines
    # themselves tell)
    e_delta = any(len(r) > 1 and r[1] in ("ED", "EX") for r in recs)
    abil_rep = []                # v20: ability repeat runs [event, caster, ability, target, n, first, last]
    sites, site_info = [], {}    # v19: [t, id, owner, [progress], [near], secure, traders]; {id: [bp, sp, vp]}
    ecur, ecur_t, epend = {}, {}, {}
    # v21: active abilities {id: [[t, [names]]]}, abilities per blueprint, garrison {holder id: [[t, [squad ids] / n<count>]]},
    # win-condition script values {path: [[t, value]]} + their first values, squad state models (merged forward like esm),
    # full production queues {building: [[t, [bp, ...]]]}
    aact, aak, garr, vt, vtk, qsm, qfull = {}, {}, {}, {}, {}, {}, {}
    for rec in recs[1:]:
        if len(rec) > 1 and rec[1] == "STOP":
            break
        try:   # a record cut mid-write (game closed, line limit) is skipped, not fatal
                kind = rec[1]
                if kind == "STOP":
                    break
                if kind == "P":
                    t, k = float(rec[2]), int(rec[3])
                    if e_delta:            # v20: the state as of the player's previous second goes into that frame
                        if k in epend and epend[k] < t:
                            settle(k, epend[k])
                        epend[k] = t
                    if delta and last_emit is not None and t - last_emit >= NODE_STEP:
                        emit(t)
                    players.setdefault(k, {"idx": k, "name": rec[4], "civ": rec[5], "team": rec[6]})
                    frame(t)["players"][k] = {
                        "bank": dict(zip(RES, (_f(x) for x in rec[7:11]))),
                        "eco_up": {"wheelbarrow": int(rec[11]), "food": int(rec[12]),
                                   "wood": int(rec[13]), "gold": int(rec[14])},
                        "age": int(float(rec[15])) if len(rec) > 15 and rec[15] != "" else None,
                        "pop": _f(rec[16]) if len(rec) > 16 else None,
                        "popcap": _f(rec[17]) if len(rec) > 17 else None,
                    }
                    # v8: every resource type, bank and the game's income rate: X|Name:bank:rate;...
                    if len(rec) > 19 and rec[18] == "X":
                        xr = {}
                        for part in rec[19].split(";"):
                            f = part.split(":")
                            if len(f) == 3 and f[0]:
                                xr[f[0].lower()] = [_f(f[1]), _f(f[2])]
                        frame(t)["players"][k]["res"] = xr
                    # v11: player state-model values SM|key:value;... (Ottoman vizier experience / points)
                    if len(rec) > 21 and rec[20] == "SM" and rec[21]:
                        sm = {}
                        for part in rec[21].split(";"):
                            key, _, v = part.partition(":")
                            if key:
                                sm[key] = _fs(v)
                        frame(t)["players"][k]["sm"] = sm
                elif kind == "N":
                    t, full = float(rec[2]), rec[3] == "1"
                    if not nodes or nodes[-1]["t"] != t:
                        nodes.append({"t": t, "full": full, "nodes": []})
                    for ent in "|".join(rec[4:]).split(";"):
                        nd = node_rec(ent)
                        if nd:
                            nodes[-1]["nodes"].append(nd)
                            if delta:
                                state[nd["id"]] = nd
                    if delta:
                        last_emit = last_full = t
                elif kind == "F":          # v6 fight samples: id,x,z,hp,target (x empty = gone)
                    t = float(rec[2])
                    if not fast or fast[-1]["t"] != t:
                        fast.append({"t": t, "u": {}})
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) < 5 or not f[0]:
                            continue
                        fast[-1]["u"][int(f[0])] = [_f(f[1]), _f(f[2]), _f(f[3]) or 0.0, int(f[4]) if f[4] else None]
                elif kind == "H":          # v9 hits
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) < 4 or not f[0]:
                            continue
                        try:
                            h = [t, int(f[0]), int(f[1]), _f(f[2]), _f(f[3])]
                            if len(f) >= 6:            # v18: shield damage, repair tick
                                h += [_f(f[4]), f[5] == "1"]
                            hits.append(h)
                        except ValueError:
                            continue                   # a cut record
                elif kind in ("PF", "PL"):  # v9 projectiles fired / landed
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) < 5 or not f[0]:
                            continue
                        try:
                            shots.append([t, kind[1], int(f[0]), int(f[1]), int(f[2]), _f(f[3]), _f(f[4])])
                        except ValueError:
                            continue
                elif kind == "NMODE":
                    delta = rec[2] == "delta"
                elif kind == "NC":
                    for ent in "|".join(rec[3:]).split(";"):
                        nd = node_rec(ent)
                        if nd:
                            state[nd["id"]] = nd
                elif kind == "NX":
                    for i in "|".join(rec[3:]).split(";"):
                        if i:
                            state.pop(int(i), None)
                elif kind in CTX_TYPES:     # K / U; v18 UQ UX C CS CW CX SP (game event contexts)
                    ev = {"t": float(rec[2]), "type": CTX_TYPES[kind]}
                    for kv in "|".join(rec[3:]).split(";"):
                        k_, _, v = kv.partition("=")
                        if k_:
                            ev[k_] = v
                    events.append(ev)
                elif kind == "HMH":
                    terrain = {"x0": float(rec[2]), "z0": float(rec[3]), "step": float(rec[4]),
                               "cols": int(rec[5]), "rows": int(rec[6]), "h": [None] * int(rec[6])}
                elif kind == "HM" and terrain is not None:
                    row = int(rec[2])
                    if 0 <= row < terrain["rows"]:
                        terrain["h"][row] = [_f(x) for x in rec[3].split(",")]
                elif kind == "PCAPS":
                    pas["caps"] = dict(x.split("=", 1) for x in rec[2:] if "=" in x)
                elif kind == "PCV":
                    pas["covers"][int(rec[2])] = rec[3]
                elif kind == "PG":
                    pas["rows"][int(rec[2])] = [[_fs(v) for v in (c.split(":") + ["", "", "", ""])[:4]]
                                                for c in rec[3].split(",")]
                elif kind == "S":
                    sizes[rec[2]] = [_f(rec[3]), _f(rec[4])]
                elif kind == "AB":         # v12: A4D|AB|t|event,caster,ability,target;...  (caster / target: id or s<squad>)
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) >= 4 and f[0]:
                            abil.append([t, f[0], f[1], f[2], f[3]])
                elif kind in ("AA", "G"):      # v21: A4D|AA|t|id,a+b / -;...  A4D|G|t|holder,squad:squad / -;...
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        i_, _, v = ent.partition(",")
                        if not i_.isdigit() or not v:
                            continue
                        val = [] if v == "-" else v.split("+" if kind == "AA" else ":")
                        (aact if kind == "AA" else garr).setdefault(i_, []).append([t, val])
                elif kind == "AAK":            # v21: A4D|AAK|bp|ability,ability
                    aak[rec[2]] = rec[3].split(",") if len(rec) > 3 and rec[3] else []
                elif kind == "VTK":            # v21: A4D|VTK|path|type|value (first value)
                    vtk[rec[2]] = [rec[3], rec[4] if len(rec) > 4 else None]
                elif kind == "VT":             # v21: A4D|VT|t|path=value;...
                    t = float(rec[2])
                    for kv in "|".join(rec[3:]).split(";"):
                        k_, _, v = kv.partition("=")
                        if k_:
                            vt.setdefault(k_, []).append([t, _fs(v)])
                elif kind == "QS":             # v21: A4D|QS|t|squad|key=value;... (changed keys only)
                    vals = {}
                    for kv in "|".join(rec[4:]).split(";"):
                        k_, _, v = kv.partition("=")
                        if k_:
                            vals[k_] = _fs(v)
                    _sm_merge(qsm.setdefault(int(rec[3]), []), float(rec[2]), vals)
                elif kind == "ABR":        # v20: A4D|ABR|t|event,caster,ability,target,n,first,last;...
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) >= 7 and f[0]:
                            abil_rep.append([f[0], f[1], f[2], f[3], int(f[4]), float(f[5]), float(f[6])])
                elif kind == "SSI":        # v19: A4D|SSI|id|bp|strategic point|victory point
                    site_info[rec[2]] = [rec[3], rec[4] == "true", rec[5] == "true"]
                elif kind == "SS":         # v19: A4D|SS|t|id,owner,prog p1:p2,near p1:p2,secure,traders;... (on change)
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        if len(f) >= 6 and f[0]:
                            sites.append([t, int(f[0]), int(f[1] or 0), [_f(x) for x in f[2].split(":")],
                                          [x == "1" if x else None for x in f[3].split(":")], _f(f[4]), _f(f[5])])
                elif kind == "ABK":        # v12: context fields of the first ability events (kept for the notes)
                    abk.append("|".join(rec[2:]))
                elif kind == "GE":         # v12: every global event the game defines
                    gev[:] = rec[2].split(",")
                elif kind == "ES":         # v11: A4D|ES|t|id|key=value;...
                    vals = {}
                    for kv in "|".join(rec[4:]).split(";"):
                        k_, _, v = kv.partition("=")
                        if k_:
                            vals[k_] = _fs(v)
                    # v18 lines carry changed keys only: merge forward so every entry is the whole state at t
                    _sm_merge(esm.setdefault(int(rec[3]), []), float(rec[2]), vals)
                elif kind == "PS":         # v18: A4D|PS|t|player|key=value;... (changed keys only)
                    vals = {}
                    for kv in "|".join(rec[4:]).split(";"):
                        k_, _, v = kv.partition("=")
                        if k_:
                            vals[k_] = _fs(v)
                    _sm_merge(psm.setdefault(int(rec[3]), []), float(rec[2]), vals)
                elif kind in ("I", "BI", "Q", "D"):   # v18 buffered records
                    t = float(rec[2])
                    for ent in "|".join(rec[3:]).split(";"):
                        f = ent.split(",")
                        try:
                            if kind == "I" and len(f) >= 5:
                                income.append([t, int(f[0])] + [_f(x) or 0.0 for x in f[1:5]])
                            elif kind == "BI" and len(f) >= 3:
                                built.append([t, int(f[0]), f[1], int(f[2]) if f[2].isdigit() else None,
                                              int(f[3]) if len(f) > 3 and f[3].isdigit() and f[3] != "0" else None])
                            elif kind == "Q" and len(f) >= 4:
                                queue_hd.setdefault(int(f[0]), []).append([t, int(f[1]), None if f[2] == "-" else f[2],
                                                                           None if f[3] == "-" else f[3]])
                                if len(f) > 4:      # v21: the whole queue
                                    qfull.setdefault(f[0], []).append([t, [x for x in f[4].split("+") if x]])
                            elif kind == "D" and len(f) >= 2:
                                dest.setdefault(f[0], []).append([t, _f(f[1]), _f(f[2])] if len(f) >= 3 else [t, None, None])
                        except ValueError:
                            continue
                elif kind == "B":          # v18: A4D|B|t|player|bp|key=value,...
                    c = {}
                    for kv in "|".join(rec[5:]).split(","):
                        k_, _, v = kv.partition("=")
                        if k_:
                            c[k_] = _f(v)
                    bcost.setdefault(rec[3], {}).setdefault(rec[4], []).append([float(rec[2]), c])
                elif kind == "BIK":
                    abk.append("BI|" + "|".join(rec[2:]))
                elif kind == "SMK":        # v18: keys kept per blueprint after the probe
                    smk[rec[2]] = int(rec[3]) if rec[3].isdigit() else rec[3]
                elif kind == "BH":
                    heading[int(rec[2])] = [float(rec[3]), float(rec[4])]
                elif kind == "API":
                    api.extend(x for x in rec[2].split(",") if x)
                elif kind == "IO":
                    io_type = rec[2]
                elif kind == "NCAPS":
                    node_method = rec[2]
                elif kind in ("ED", "EX") or (kind == "E" and e_delta):
                    # v20 entity deltas: E = keyframe (the first E line of (t, player) replaces the state), ED = changed
                    # records (bp empty = unchanged), EX = gone ids; the frame gets the state at the player's next P line
                    t, k = float(rec[2]), int(rec[3])
                    body = "|".join(rec[4:])
                    cur = ecur.setdefault(k, {})
                    if kind == "E" and ecur_t.get(k) != t:
                        cur.clear()
                    ecur_t[k] = t
                    epend[k] = t
                    for ent in body.split(";"):
                        if not ent:
                            continue
                        if kind == "EX":
                            cur.pop(ent, None)
                            continue
                        f = ent.split(",")
                        if len(f) < 13:
                            ebad += 1                  # cut mid-write: resynced at the next keyframe
                            continue
                        if not f[1]:
                            old = cur.get(f[0])
                            if old is None:
                                ebad += 1              # blueprint unknown (its full record was lost)
                                continue
                            f[1] = old[1]
                        cur[f[0] or ("_" + str(len(cur)))] = f
                elif kind == "E":
                    t, k = float(rec[2]), int(rec[3])
                    body = "|".join(rec[4:])
                    fr = frame(t)
                    for ent in body.split(";"):
                        if ent:
                            add_entity(fr, k, ent.split(","))
        except (IndexError, ValueError):
            bad += 1
    for k_, t_ in list(epend.items()):
        settle(k_, t_)
    if ebad:
        print(f"v20 entity deltas: {ebad} record(s) lost (cut lines / unknown blueprint), resynced at the next keyframe")
    if bad:
        print(f"skipped {bad} malformed record(s) (cut mid-write)")
    # drop a trailing frame that may have been cut mid-write
    out = [frames[t] for t in order]
    if out and set(out[-1]["players"]) != set(players):
        out.pop()
    for snap in nodes:
        if snap["full"]:
            tree_subtypes(snap)
    caps["nodes"] = node_method
    caps["io"] = io_type
    caps["age"] = any(pl.get("age") is not None for fr in out for pl in fr["players"].values())
    return {"format": "a4d-timeline/1", "caps": caps,
            "players": [players[k] for k in sorted(players)], "frames": out,
            "nodes": nodes, "api": sorted(set(api)), "events": events, "terrain": terrain, "fast": fast,
            "esm": {str(k): v for k, v in esm.items()},
            "psm": {str(k): v for k, v in psm.items()},
            # v18: [t, player, food, wood, gold, stone] credits; [t, player, bp, squad, producer]; {building: [[t, size,
            # type, bp]]}; {squad: [[t, x, z] / [t, None, None]]}; {player: {bp: [[t, {res: cost}]]}}
            "income": income, "built": built, "queueHead": {str(k): v for k, v in queue_hd.items()},
            "dest": dest, "bpCost": bcost,
            "smk": smk,
            "abilities": abil, "abilityFields": abk, "globalEvents": gev,
            # v20 repeat runs of ability events (aura pulses); v19 strategic points (sacred sites, trade posts)
            "abilityRuns": abil_rep, "sites": sites, "siteInfo": site_info,
            # v21
            "activeAbilities": aact, "abilitiesOf": aak, "garrison": garr, "winValues": vt, "winValueKeys": vtk,
            "qsm": {str(k): v for k, v in qsm.items()}, "queueFull": qfull,
            "hits": sorted(hits, key=lambda h: h[0]), "shots": sorted(shots, key=lambda x: x[0]),
            "pass": _pass_grid(pas, terrain), "sizes": sizes, "heading": {str(k): v for k, v in heading.items()}}


NODE_STEP, NODE_FULL = 5.0, 60.0


def tracked(bp):
    """Map objects whose amount and visibility the dump follows (dump.lua Tracked())."""
    return bp.startswith("gaia_") or bp.startswith("resource_") or "relic" in bp


def node_rec(ent):
    """One node record id,bp,x,z,vismask,remaining -> dict (None if empty or dropped)."""
    if not ent:
        return None
    f = ent.split(",")
    if len(f) < 4:
        return None
    # trade posts (owner 2026-11-13: "trade posts should be drawn") are neutral buildings - kept as map objects of type "trade"
    if (f[1].startswith(NODE_DROP) or any(k in f[1] for k in NODE_DROP[3:])) and "trade_post" not in f[1]:
        return None
    return {"id": int(f[0]) if f[0] else None, "bp": f[1], "type": node_type(f[1]),
            "x": _f(f[2]), "z": _f(f[3]),
            "vis": int(f[4]) if len(f) > 4 and f[4] else None,
            "left": _f(f[5]) if len(f) > 5 else None}


# resource-node classes by blueprint substring; first match wins
TREE_WORDS = ("tree", "birch", "elm", "oak", "pine", "palm", "cedar", "maple", "spruce", "cypress",
              "bamboo", "willow", "aspen", "acacia", "baobab", "poplar", "fir_", "larch", "beech",
              "conifer", "cherry", "olive_tree", "_wild", "_dead_stealth")
NODE_TYPES = [("trade", ("trade_post",)), ("carcass", ("carcass", "corpse")), ("wolf", ("wolf",)), ("gold", ("gold",)),
              ("silver", ("silver",)),
              ("stone", ("stone",)), ("berry", ("berr", "bush", "fruit")),
              ("boar", ("boar",)), ("deer", ("deer", "huntable")), ("sheep", ("sheep", "herdable")),
              ("fish", ("fish", "shoreline", "deep_water")), ("olive", ("olive",)),
              ("relic", ("relic",)), ("site", ("holy_site", "sacred_site")),
              ("tree", TREE_WORDS)]
# trees: forest by default; "_stealth" = stealth forest (hides units); "_scatter" or no other
# tree within STRAGGLER_R = straggler (removable by placing a building on it)
STRAGGLER_R = 6.0
# neutral entities that are not resources or map objects: dropped
NODE_DROP = ("unit_", "building_", "projectile", "dynamic_spawn", "_viz", "dummy_minimap")


def tree_subtypes(snap):
    trees = [n for n in snap["nodes"] if n["type"] == "tree" and n["x"] is not None]
    grid = {}
    for n in trees:
        grid.setdefault((int(n["x"] // STRAGGLER_R), int(n["z"] // STRAGGLER_R)), []).append(n)
    for n in trees:
        if "stealth" in n["bp"]:
            n["type"] = "stealth"
            continue
        cx, cz = int(n["x"] // STRAGGLER_R), int(n["z"] // STRAGGLER_R)
        alone = not any(m is not n and (m["x"] - n["x"]) ** 2 + (m["z"] - n["z"]) ** 2 <= STRAGGLER_R ** 2
                        for dx in (-1, 0, 1) for dz in (-1, 0, 1) for m in grid.get((cx + dx, cz + dz), ()))
        if alone or "scatter" in n["bp"]:
            n["type"] = "straggler"


def node_type(bp):
    b = (bp or "").lower()
    for name, keys in NODE_TYPES:
        if any(k in b for k in keys):
            return name
    return "other"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out")
    ap.add_argument("--session", type=int, default=-1)
    a = ap.parse_args(argv)
    with open(a.log, encoding="utf-8", errors="replace") as fh:
        sessions = split_sessions(fh)
    if not sessions:
        sys.exit("no A4D|CAPS line found: dump.lua output not in this log")
    tl = parse_session(sessions[a.session])
    with open(a.out, "w") as fh:
        json.dump(tl, fh, separators=(",", ":"))
    print(f"{len(sessions)} session(s); using {a.session}: "
          f"{len(tl['players'])} players, {len(tl['frames'])} frames; caps={tl['caps']}")
    if tl["nodes"]:
        other = sorted({n["bp"] for snap in tl["nodes"] for n in snap["nodes"] if n["type"] == "other"})
        print(f"{len(tl['nodes'])} resource-node snapshots; unclassified blueprints: {other}")
    if tl["api"]:
        print(f"{len(tl['api'])} API functions listed")


if __name__ == "__main__":
    main()
