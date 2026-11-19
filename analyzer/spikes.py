"""Power spikes, fights by line, composition / rally changes and resource-node lifetimes for one game (review only:
full information). Owner 2026-11-09, the first step towards per-matchup decision trees ("big picture" episodes with
the details as children): a per-game timeline before any episodes are built.

    python analyzer/spikes.py work/<name>.analyzed.json work/<name>.spikes.json [--replay <replay file>]

Owner's rules:
- The tangible power spike is army value, and how much of it remains after fights; eco is the reason (a child line).
- A spike is relative: it lasts until the opponent catches up. Measured on the gap (my army value - theirs): its size
  is how far the gap moves in my favour after it, against the gap just before. It ends at the earliest of: caught up
  (the gap back to its pre-spike level - credited to an opponent spike that came in between, or a fight that cost
  the lead), removed (its landmark destroyed), game end.
- Spike events: age-ups (landmark completed), unique technologies (aoe4world's "unique" flag), unique units (first
  one produced; same flag). Eco spikes of any kind show in the slope of resources gathered; production surges in units
  produced (counted when they appear, not when queued).
- Fights: frontline (melee) vs backline (ranged) - each side's value per line at the start, losses per line, and
  which line collapsed first (lost half its value).
- Composition swaps (the most produced unit type per minute changes) and rally points (military buildings; a rally
  in the own third while the army is forward = defensive, owner's example of a flank being covered).
- Resource nodes: how long each lasted while worked, per player.
Every child line says where it comes from: "true" (hindsight, values the other player could not see) or "seen".
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from basics import per_player, _is_army, RES  # noqa: E402
from fights import find_deaths  # noqa: E402
from gamedata import resolve  # noqa: E402
from techs_bought import civ_code  # noqa: E402

STEP = 5.0            # s between series samples
RATE_SPAN = 60.0      # s: income / army output over the trailing minute
WIN = 90.0            # s: before / after windows for a spike's effect
GRACE = 20.0          # s after a spike before "caught up" can end it
MIN_GAIN = 150.0      # army value: smallest gap rise that counts as an army lead
LOOK = 180.0          # s: no lead within this after the spike = "no army lead"
FIGHT_PAD = 25.0      # map units around a fight's circle: units counted as in it
COLLAPSE = 0.5        # a line has collapsed when it lost this share of its value
COMP_WIN = 60.0       # s: production-mix window
COMP_MIN = 3          # units in both windows before a swap counts
BASE_R = 40.0         # map units from the starting TC = base
ABANDON = 60.0        # s without gathering (trees: 120) ends a node stint
NODE_LINK = {"berry": 12.0, "deer": 24.0, "carcass": 12.0}   # map units: one group (berry patch, deer pack, sheep at
                                                               # one drop site)
REACH = {"gold": 14.0, "stone": 14.0}       # map units: villager at the node (default 9)
TREE_LINK, TREE_REACH = 10.0, 20.0
RALLY_HOLD = 10.0     # s a rally must stand to count
MIL_CLASSES = ("military", "land_military", "naval_military")


def _load(name, key):
    with open(os.path.join(HERE, "..", "data", name), encoding="utf-8") as fh:
        return json.load(fh)[key]


def mmss(t):
    t = int(round(t or 0))
    return f"{t // 60}:{t % 60:02d}"


def _at(R, t):
    """row of R at time t (rows are 1 s apart, from R[0]["t"])"""
    i = int(round(t - R[0]["t"]))
    return R[max(0, min(len(R) - 1, i))]


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------- series
def series(R, t_end):
    """every STEP s: army (field value), income /min (gathered over the last minute), output /min (army value
    produced over the last minute), villagers"""
    out = []
    t = R[0]["t"]
    while t <= t_end:
        r, q = _at(R, t), _at(R, t - RATE_SPAN)
        span = max(1.0, r["t"] - q["t"])
        inc = sum(r["gathered"][x] - q["gathered"][x] for x in RES) * 60 / span
        outp = (r["cat"]["army"] - q["cat"]["army"]) * 60 / span
        early = t - R[0]["t"] < RATE_SPAN       # first minute: the opening queue is spent before anything is gathered
        out.append({"t": round(t, 1), "army": round(r["army"]), "income": None if early else round(inc),
                    "output": None if early else round(outp),
                    "vil": r["nvil"], "idle": r["idle"],
                    "res": {x: round((r["gathered"][x] - q["gathered"][x]) * 60 / span) for x in RES}})
        t += STEP
    return out


def _window(S, a, b, key):
    return _mean([s[key] for s in S if a <= s["t"] < b])


# ---------------------------------------------------------------- spike events
def _spike_events(tl, per, p, bought, units, upgrades, cancelled):
    frames = tl["frames"]
    R = per[p]["rows"]
    ev = []
    # age-ups: the player's age goes up when the landmark completes
    lms = [L for L in per[p]["landmarks"] if L["id"] not in cancelled]
    prev = R[0]["age"]
    for r in R:
        a = r["age"]
        if a is not None and prev is not None and a > prev:
            L = next((x for x in lms if x["age"] == prev), None)
            ev.append({"kind": "age", "t0": L["t"] if L else r["t"], "t1": r["t"], "age": a,
                       "name": f"Age {a}: " + (L["name"] if L else "(no landmark: this civ ages up another way)"),
                       "src": L["id"] if L else None, "seen": "announced"})
        if a is not None:
            prev = a
    # unique technologies
    code = civ_code(tl, p)
    for x in bought.get(p, []):
        v = upgrades.get(x["attrib"]) or []
        e = next((e for e in v if code in (e.get("civs") or [])), v[0] if v else None)
        if e and e.get("unique"):
            ev.append({"kind": "tech", "t0": x["t"], "t1": x["done"], "name": "Tech: " + x["name"], "src": None,
                       "seen": "hidden (research isn't visible; its effect may be)"})
    # unique units: the first of each type produced
    first = {}
    start_ids = {e["id"] for e in frames[0]["entities"]}
    o = [q["idx"] for q in tl["players"] if q["idx"] != p]
    for fr in frames:
        for e in fr["entities"]:
            if e["owner"] != p or e["id"] in start_ids or e["kind"] != "m" or not _is_army(e):
                continue
            u = units.get(e["bp"]) or units.get(resolve(e["bp"], units) or "")
            if not u or not u.get("unique") or not any(c in (u.get("classes") or []) for c in MIL_CLASSES):
                continue
            base = u.get("base") or e["bp"]
            if base not in first:
                first[base] = {"kind": "unit", "t0": fr["t"], "t1": fr["t"], "name": "Unit: " + (u.get("name") or base),
                               "src": None, "base": base, "seen": "not seen"}
            f = first[base]
            if f["seen"] == "not seen" and o and e.get("vis") and e["vis"] & (1 << (o[0] - 1)):
                f["seen"] = f"seen at {mmss(fr['t'])}"
    ev += list(first.values())
    ev.sort(key=lambda x: x["t1"])
    return ev


def _removed_at(frames, eid, owner, t_from):
    """time the entity left the lists for good while its owner still had entities (destroyed; not the end of the
    owner's lists at a resignation), None if it stands to the end"""
    last, gone = None, None
    for fr in frames:
        if fr["t"] < t_from:
            continue
        if any(e["id"] == eid for e in fr["entities"]):
            last, gone = fr["t"], None
        elif last is not None and gone is None and any(e["owner"] == owner for e in fr["entities"]):
            gone = fr["t"]
    return gone


def _measure(ev, S, So, fights, t_end, frames, p):
    """the spike's effect: windows before / after, gap rise, how it ended"""
    t0, t1 = ev["t0"], ev["t1"]
    gap = {s["t"]: s["army"] - so["army"] for s, so in zip(S, So)}
    ts = sorted(gap)
    base = _mean([gap[t] for t in ts if t0 - WIN <= t < t0])
    if base is None:
        base = gap[ts[0]]
    rm = _removed_at(frames, ev["src"], p, t1) if ev.get("src") else None
    peak, peak_t, end, why = 0.0, None, None, None
    led = False
    for t in ts:
        if t < t1:
            continue
        if rm is not None and t >= rm:
            end, why = rm, "removed (landmark destroyed)"
            break
        rise = gap[t] - base
        if rise > peak:
            peak, peak_t = rise, t
        if rise >= MIN_GAIN:
            led = True
        if not led and t - t1 > LOOK:
            end, why = t, "no army lead"
            break
        if led and t - t1 > GRACE and rise <= 0:
            end, why = t, "caught up"
            break
    if end is None:
        end, why = t_end, "game end"
    b = lambda k: _window(S, t0 - WIN, t0, k)  # noqa: E731
    a = lambda k: _window(S, t1, t1 + WIN, k)  # noqa: E731
    inc_b, inc_a, vil_b, vil_a = b("income"), a("income"), b("vil"), a("vil")
    m = {"base_gap": round(base), "peak_gain": round(peak), "peak_t": peak_t, "led": led, "end": end, "why": why,
         "dur": round(end - t1) if led else None,
         "income": [_r(inc_b), _r(inc_a)], "output": [_r(b("output")), _r(a("output"))],
         "vil": [_r(vil_b), _r(vil_a)],
         "per_vil": [_r(inc_b / vil_b, 1) if inc_b and vil_b else None, _r(inc_a / vil_a, 1) if inc_a and vil_a else None],
         "army_at": round(next(s["army"] for s in S if s["t"] >= t1 - 0.01) if any(s["t"] >= t1 for s in S) else 0),
         "their_army_at": round(next(s["army"] for s in So if s["t"] >= t1 - 0.01) if any(s["t"] >= t1 for s in So) else 0),
         "build_idle": _r(_window(S, t0, t1, "idle")) if t1 > t0 else None}
    # fights while it was up
    m["fights"] = [f["n"] for f in fights if t1 <= f["start"] <= end]
    return m


def _r(v, nd=0):
    return None if v is None else round(v, nd) if nd else round(v)


# ---------------------------------------------------------------- fights by line
def _line(bp, units):
    u = units.get(bp) or units.get(resolve(bp, units) or "") or {}
    cl = u.get("classes") or []
    if "siege" in cl:
        return "siege"
    return "back" if "ranged" in cl else "front"


def fight_lines(tl, fights, units, cost_of, pids):
    frames = tl["frames"]
    by_t = {round(fr["t"]): fr for fr in frames}
    out = []
    for f in fights:
        fr = by_t.get(round(f["start"])) or min(frames, key=lambda q: abs(q["t"] - f["start"]))
        R = (f.get("r") or 15.0) + FIGHT_PAD
        start = {p: {"front": 0.0, "back": 0.0, "siege": 0.0} for p in pids}
        there = set()
        for e in fr["entities"]:
            if e["owner"] in start and e["x"] is not None and _is_army(e) and \
                    math.hypot(e["x"] - f["x"], e["z"] - f["z"]) <= R:
                start[e["owner"]][_line(e["bp"], units)] += cost_of(e["bp"])
                there.add(e["id"])
        # units that joined later and died in it count as engaged too (reinforcements)
        for d in f["deaths"]:
            if d["owner"] in start and d["kind"] == "m" and _is_army(d) and d["id"] not in there:
                start[d["owner"]][_line(d["bp"], units)] += d.get("cost") or 0
        lost = {p: {"front": 0.0, "back": 0.0, "siege": 0.0} for p in pids}
        collapse = []
        for d in sorted(f["deaths"], key=lambda d: d["t"]):
            if d["owner"] not in lost or d["kind"] != "m" or not _is_army(d):
                continue
            ln = _line(d["bp"], units)
            lost[d["owner"]][ln] += d.get("cost") or 0
            s0 = start[d["owner"]][ln]
            if s0 > 0 and lost[d["owner"]][ln] >= COLLAPSE * s0 and (d["owner"], ln) not in [(c[0], c[1]) for c in collapse]:
                collapse.append((d["owner"], ln, d["t"]))
        out.append({"n": f["n"], "start": f["start"], "end": f["end"], "x": f["x"], "z": f["z"],
                    "start_value": {str(p): {k: round(v) for k, v in start[p].items()} for p in pids},
                    "lost": {str(p): {k: round(v) for k, v in lost[p].items()} for p in pids},
                    "remain": {str(p): (round(1 - sum(lost[p].values()) / sum(start[p].values()), 2)
                                        if sum(start[p].values()) else None) for p in pids},
                    "collapse": [{"p": c[0], "line": c[1], "t": c[2]} for c in collapse]})
    return out


# ---------------------------------------------------------------- composition swaps
def comp_swaps(tl, p, units):
    frames = tl["frames"]
    start_ids = {e["id"] for e in frames[0]["entities"]}
    seen = set()
    made = []
    for fr in frames:
        for e in fr["entities"]:
            if e["owner"] != p or e["id"] in seen:
                continue
            seen.add(e["id"])
            if e["id"] in start_ids or not _is_army(e):
                continue
            u = units.get(e["bp"]) or units.get(resolve(e["bp"], units) or "") or {}
            made.append((fr["t"], u.get("base") or e["bp"], u.get("name") or e["bp"]))
    if not made:
        return []
    names = {b: n for _, b, n in made}
    wins = []
    t, t_end = 0.0, frames[-1]["t"]
    while t < t_end:
        c = {}
        for tt, b, _ in made:
            if t <= tt < t + COMP_WIN:
                c[b] = c.get(b, 0) + 1
        wins.append((t, c))
        t += COMP_WIN
    out, prev = [], None
    for t, c in wins:
        if sum(c.values()) < COMP_MIN:
            continue
        top = max(c, key=c.get)
        if prev and top != prev[0]:
            out.append({"t": t, "from": names.get(prev[0], prev[0]), "to": names.get(top, top),
                        "mix": {names.get(k, k): v for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:4]}})
        prev = (top, t)
    return out


# ---------------------------------------------------------------- rally points
def rallies(tl, replay_path, tcs, prod):
    """rally changes of military production buildings, per player (needs the replay file)"""
    try:
        from replay import commands, receivers, data_of, target_of
    except ImportError:
        return {}
    frames = tl["frames"]
    info, sq_ent = {}, {}
    for fr in frames[::5]:
        for e in fr["entities"]:
            info.setdefault(e["id"], (e["owner"], e["bp"], e["kind"]))
    mil_bases = set()
    U = prod.get("units") or {}
    costs = _load("costs.json", "costs")
    for u, by in U.items():
        if (costs.get(u) or {}).get("military"):
            mil_bases.update(by)
    mil_bases -= {"town-center", "capital-town-center"}       # TC rallies send villagers (scouts aside)
    bbase = prod.get("buildingBase") or {}

    def pos_of(kind, i, t):
        fr = min(frames, key=lambda q: abs(q["t"] - t))
        for e in fr["entities"]:
            if (kind == "entity" and e["id"] == i) or (kind == "squad" and e.get("squad") == i):
                return e["x"], e["z"]
        for snap in tl.get("nodes") or []:
            for n in snap["nodes"]:
                if n["id"] == i:
                    return n["x"], n["z"]
        return None
    out = {}
    last = {}
    for tick, slot, typ, c in commands(replay_path):
        if typ not in (12, 22):
            continue
        try:
            rec, o = receivers(c)
            tg = target_of(*data_of(c, o))
        except Exception:  # noqa: BLE001 - a record this reader doesn't know
            continue
        t = tick / 8.0
        bld = [i for k, i in rec if k == 1 and i in info]
        if not bld or not tg:
            continue
        owner, bp, _ = info[bld[0]]
        base = bbase.get(bp) or bbase.get(resolve(bp, bbase) or "")
        if base not in mil_bases or owner not in tcs:
            continue
        xz = (tg[1], tg[2]) if tg[0] == "pos" else pos_of(tg[0], tg[1], t)
        if not xz:
            continue
        reg = _region(xz, owner, tcs)
        army_reg = _army_region(frames, owner, t, tcs)
        key = (owner, reg)
        if last.get(owner) == reg:
            continue
        last[owner] = reg
        out.setdefault(str(owner), []).append({
            "t": round(t, 1), "region": reg, "x": round(xz[0]), "z": round(xz[1]), "army": army_reg,
            "defensive": reg in ("base", "mine") and army_reg in ("middle", "theirs")})
        del key
    # a rally changed back within RALLY_HOLD s was a correction, not an intent: keep the ones that stood
    for p, v in out.items():
        keep = [r for k, r in enumerate(v) if k == len(v) - 1 or v[k + 1]["t"] - r["t"] >= RALLY_HOLD]
        out[p] = [r for k, r in enumerate(keep) if k == 0 or r["region"] != keep[k - 1]["region"]]
    return out


def _region(xz, p, tcs):
    me = tcs[p]
    them = next((v for k, v in tcs.items() if k != p), None)
    if math.hypot(xz[0] - me[0], xz[1] - me[1]) <= BASE_R:
        return "base"
    if them is None:
        return "mine"
    dx, dz = them[0] - me[0], them[1] - me[1]
    s = ((xz[0] - me[0]) * dx + (xz[1] - me[1]) * dz) / ((dx * dx + dz * dz) or 1.0)
    return "mine" if s < 1 / 3 else "theirs" if s > 2 / 3 else "middle"


def _army_region(frames, p, t, tcs):
    fr = min(frames, key=lambda q: abs(q["t"] - t))
    pts = [(e["x"], e["z"]) for e in fr["entities"] if e["owner"] == p and e["x"] is not None and _is_army(e)]
    if not pts:
        return None
    return _region((sum(x for x, _ in pts) / len(pts), sum(z for _, z in pts) / len(pts)), p, tcs)


# ---------------------------------------------------------------- resource nodes
def _groups(items, link):
    par = list(range(len(items)))

    def root(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if math.hypot(items[i][1] - items[j][1], items[i][2] - items[j][2]) < link:
                par[root(i)] = root(j)
    g = {}
    for i in range(len(items)):
        g.setdefault(root(i), []).append(items[i][0])
    return list(g.values())


def nodes(tl, pids, tcs):
    """per (node group, player) stints: start, end, lasted, worked s, villager-s, amount, rate, end reason, region"""
    frames = tl["frames"]
    by_t = {}
    for fr in frames:
        by_t[round(fr["t"])] = fr
    snaps = tl.get("nodes") or []
    if not snaps:
        return []
    # series per node (tracked nodes: every 5 s; trees: in the full snapshots, every 60 s)
    ser, meta = {}, {}
    for s in snaps:
        for n in s["nodes"]:
            if n["type"] in ("tree", "stealth", "straggler", "wolf", "relic", "site", "other") or n["x"] is None:
                continue
            ser.setdefault(n["id"], []).append((s["t"], n.get("left")))
            meta.setdefault(n["id"], (n["type"], n["x"], n["z"], n["bp"]))
    last_t = snaps[-1]["t"]
    # groups: berry patches and deer packs by start position, the rest one node each
    groups = []
    for typ in sorted({m[0] for m in meta.values()}):
        items = [(i, m[1], m[2]) for i, m in meta.items() if m[0] == typ]
        if typ in NODE_LINK:
            groups += [(typ, g) for g in _groups(items, NODE_LINK[typ])]
        else:
            groups += [(typ, [i]) for i, _, _ in items]

    def gatherers(t, x, z, reach, res_id=None):
        fr = by_t.get(round(t))
        if fr is None:
            return {}
        c = {}
        for e in fr["entities"]:
            if e["kind"] != "w" or e["x"] is None or not e.get("res"):
                continue
            if res_id is not None and e.get("res") != res_id:
                continue
            if math.hypot(e["x"] - x, e["z"] - z) <= reach:
                c[e["owner"]] = c.get(e["owner"], 0) + 1
        return c
    out = []
    for typ, ids in groups:
        drops = []      # (t_a, t_b, amount, {player: gatherers})
        total0 = 0.0
        for i in ids:
            s = sorted(ser[i])
            total0 += next((v for _, v in s if v is not None), 0) or 0
            x, z = meta[i][1], meta[i][2]
            for (ta, la), (tb, lb) in zip(s, s[1:]):
                if la is None or lb is None or lb >= la:
                    continue
                g = gatherers(tb, x, z, REACH.get(typ, 9.0))
                drops.append((ta, tb, la - lb, g))
            # gone between snapshots with food left (eaten to 0 between samples, or depleted)
            if s and s[-1][0] < last_t - 6 and (s[-1][1] or 0) > 0:
                tb = s[-1][0] + 5
                g = gatherers(s[-1][0], x, z, REACH.get(typ, 9.0))
                drops.append((s[-1][0], tb, s[-1][1], g))
        if not drops:
            continue
        left_end = sum((sorted(ser[i])[-1][1] or 0) if sorted(ser[i])[-1][0] >= last_t - 6 else 0 for i in ids)
        cx = sum(meta[i][1] for i in ids) / len(ids)
        cz = sum(meta[i][2] for i in ids) / len(ids)
        out += _stints(typ, ids, meta, drops, pids, left_end, last_t, cx, cz, tcs, ABANDON)
    out += _trees(tl, snaps, pids, tcs, gatherers)
    out.sort(key=lambda s: (s["player"], s["start"]))
    return out


def _stints(typ, ids, meta, drops, pids, left_end, last_t, cx, cz, tcs, abandon):
    out = []
    for p in pids:
        mine = []
        for ta, tb, amt, g in sorted(drops, key=lambda d: d[0]):
            n = sum(g.values())
            if g.get(p):
                mine.append((ta, tb, amt * g[p] / n, g[p]))
        if not mine:
            continue
        cur = None
        stints = []
        for ta, tb, amt, n in mine:
            if cur and ta - cur["end"] > abandon:
                stints.append(cur)
                cur = None
            if cur is None:
                cur = {"start": ta, "end": tb, "amount": 0.0, "spans": [], "vils": 0.0}
            cur["end"] = max(cur["end"], tb)
            cur["amount"] += amt
            cur["spans"].append((ta, tb))
            cur["vils"] += n * (tb - ta)
        stints.append(cur)
        for s in stints:            # time with anyone working it: the union of the intervals (group nodes overlap)
            w, hi = 0.0, None
            for a, b in sorted(s["spans"]):
                if hi is None or a > hi:
                    w += b - a
                    hi = b
                elif b > hi:
                    w += b - hi
                    hi = b
            s["worked"] = w
        for k, s in enumerate(stints):
            last = k == len(stints) - 1
            why = ("depleted" if last and left_end <= 0.02 * max(1.0, s["amount"]) else
                   "game end" if s["end"] >= last_t - abandon else "abandoned (left with resources)")
            name = meta[ids[0]][3]
            out.append({"player": p, "type": typ, "name": name + (f" ×{len(ids)}" if len(ids) > 1 else ""),
                        "x": round(cx), "z": round(cz), "region": _region((cx, cz), p, tcs),
                        "start": round(s["start"]), "end": round(s["end"]), "lasted": round(s["end"] - s["start"]),
                        "worked": round(s["worked"]), "vil_s": round(s["vils"]), "amount": round(s["amount"]),
                        "rate": round(s["amount"] / s["worked"] * 60) if s["worked"] else None, "why": why,
                        "left": round(left_end) if last else None})
    return out


def _trees(tl, snaps, pids, tcs, gatherers):
    full = [s for s in snaps if s.get("full")]
    if len(full) < 2:
        return []
    first = {n["id"]: (n["x"], n["z"]) for n in full[0]["nodes"] if n["type"] == "tree" and n["x"] is not None}
    patches = _groups([(i, x, z) for i, (x, z) in first.items()], TREE_LINK)
    patch_of = {i: k for k, g in enumerate(patches) for i in g}
    drops = {}          # patch -> [(ta, tb, trees cut, {player: wood villagers})]
    for a, b in zip(full, full[1:]):
        now = {n["id"] for n in b["nodes"] if n["type"] == "tree"}
        before = {n["id"] for n in a["nodes"] if n["type"] == "tree"}
        cut = [i for i in before - now if i in patch_of]
        per_patch = {}
        for i in cut:
            per_patch.setdefault(patch_of[i], []).append(i)
        for k, ids in per_patch.items():
            cx = sum(first[i][0] for i in ids) / len(ids)
            cz = sum(first[i][1] for i in ids) / len(ids)
            g = {}
            t = a["t"] + 5
            while t <= b["t"]:
                for p, n in gatherers(t, cx, cz, TREE_REACH, res_id=2).items():
                    g[p] = g.get(p, 0) + n * 10.0 / (b["t"] - a["t"])     # mean wood villagers there
                t += 10
            drops.setdefault(k, []).append((a["t"], b["t"], len(ids), g))
    out = []
    last_t = full[-1]["t"]
    for k, dl in drops.items():
        ids = patches[k]
        cx = sum(first[i][0] for i in ids) / len(ids)
        cz = sum(first[i][1] for i in ids) / len(ids)
        left = len([i for i in ids if i in {n["id"] for n in full[-1]["nodes"]}])
        meta = {ids[0]: ("tree", cx, cz, f"forest ({len(ids)} trees)")}
        for s in _stints("wood", [ids[0]], meta, [(ta, tb, n, {p: v for p, v in g.items() if v > 0})
                                                  for ta, tb, n, g in dl if g], pids, left, last_t, cx, cz, tcs,
                         2 * ABANDON):
            s["trees"] = s.pop("amount")
            s["rate"] = round(s["trees"] / s["worked"] * 60, 1) if s["worked"] else None
            s["left"] = left
            out.append(s)
    return out


# ---------------------------------------------------------------- all
def analyze(tl, replay_path=None):
    from analyze import load_costs
    tbl, full = load_costs()
    cost_of = lambda bp: tbl.get(resolve(bp, tbl), 0.0)  # noqa: E731
    units = _load("units.json", "units")
    upgrades = _load("upgrades.json", "upgrades")
    if not any("unique" in v for v in list(units.values())[:50]):
        print("data/units.json has no 'unique' flags: run tools/update_data.py (unique techs / units are skipped)")
    pids = [p["idx"] for p in tl["players"]]
    per, cancelled, bought = per_player(tl, full, cost_of)
    frames = tl["frames"]
    # the game ends for this purpose when a player's lists go empty (resignation): after that their army reads 0
    # and would show as a lead for the other side
    last = {p: max((fr["t"] for fr in frames if any(e["owner"] == p for e in fr["entities"])), default=frames[-1]["t"])
            for p in pids}
    t_end = min(last.values())
    S = {p: series(per[p]["rows"], t_end) for p in pids}
    deaths = [d for d in find_deaths(frames, cost_of, tl.get("events")) if d["id"] not in cancelled]
    fights = (tl.get("analysis") or {}).get("fights") or []
    if not fights:
        from fights import fights_for
        fights = fights_for(tl, cost_of)
    tcs = {}
    for e in frames[0]["entities"]:
        if "town_center" in (e["bp"] or "") and "dummy" not in e["bp"] and e["x"] is not None:
            tcs.setdefault(e["owner"], (e["x"], e["z"]))
    out = {"format": "a4d-spikes/1", "t_end": t_end, "players": tl["players"], "series": {}, "spikes": [],
           "fights": fight_lines(tl, fights, units, cost_of, pids), "comp": {}, "rally": {},
           "nodes": nodes(tl, pids, tcs), "params": {"WIN": WIN, "MIN_GAIN": MIN_GAIN, "LOOK": LOOK,
                                                    "RATE_SPAN": RATE_SPAN}}
    for p in pids:
        out["series"][str(p)] = S[p]
        out["comp"][str(p)] = comp_swaps(tl, p, units)
    if len(pids) == 2:
        evs = {p: _spike_events(tl, per, p, bought, units, upgrades, cancelled) for p in pids}
        fd = {f["n"]: f for f in out["fights"]}
        for p in pids:
            o = [q for q in pids if q != p][0]
            for ev in evs[p]:
                m = _measure(ev, S[p], S[o], fights, t_end, frames, p)
                # caught up: by an opponent spike that came in between, or a fight that cost the lead
                if m["why"] == "caught up":
                    theirs = [x for x in evs[o] if (m["peak_t"] or ev["t1"]) <= x["t1"] <= m["end"]]
                    near = [f for f in fights if f["start"] <= m["end"] and f["end"] >= m["end"] - 40]
                    lost_fight = None
                    if near:
                        f = fd.get(near[-1]["n"]) or {}
                        lm = sum((f.get("lost") or {}).get(str(p), {}).values())
                        lo = sum((f.get("lost") or {}).get(str(o), {}).values())
                        if lm > lo:
                            lost_fight = f"lead lost in fight {near[-1]['n']} ({mmss(near[-1]['start'])}: lost {lm:,} vs {lo:,})"
                    by = f"their {theirs[-1]['name']} ({mmss(theirs[-1]['t1'])})" if theirs else None
                    m["why"] = (lost_fight + (f"; {by} came in between" if by else "") if lost_fight else
                                f"caught up by {by}" if by else "caught up (their production)")
                cashed = []
                for n in m["fights"]:
                    f = fd.get(n) or {}
                    lm = sum((f.get("lost") or {}).get(str(p), {}).values())
                    lo = sum((f.get("lost") or {}).get(str(o), {}).values())
                    cashed.append({"n": n, "t": f.get("start"), "lost": lm, "killed": lo})
                m["fights"] = cashed
                out["spikes"].append({"p": p, **{k: v for k, v in ev.items() if k != "src"}, **m})
        out["spikes"].sort(key=lambda s: s["t1"])
    if replay_path:
        try:
            out["rally"] = rallies(tl, replay_path, tcs, _load_prod())
        except Exception as e:  # noqa: BLE001 - rallies are optional
            out["rallyError"] = f"{type(e).__name__}: {e}"
    return out


def _load_prod():
    with open(os.path.join(HERE, "..", "data", "production.json"), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("analyzed")
    ap.add_argument("out")
    ap.add_argument("--replay", help="replay file: rally points")
    a = ap.parse_args()
    with open(a.analyzed, encoding="utf-8") as fh:
        tl = json.load(fh)
    out = analyze(tl, a.replay)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(out['spikes'])} spikes, {len(out['fights'])} fights, {len(out['nodes'])} node stints -> {a.out}")


if __name__ == "__main__":
    main()
