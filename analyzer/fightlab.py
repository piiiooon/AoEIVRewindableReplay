"""Fight review (full information, for the fights page; not part of Fogline's sight-limited reading).

Per fight from fights.py (deaths chained in time and space), using the dump's 1 s entity lists plus
the v6 fight samples (4/s, A4D|F) where present:

- odds: Lanchester square law at the fight's start. Each side's units within 1.5 r of the centre:
  D = sum of dps against the other side's mix (weighted by its current HP share; bonus damage and
  armour from data/units.json), H = sum of current HP, P = D * H. p(side A) = 1 / (1 + exp(-ln(PA/PB) / TAU)).
  TAU = 1.5 is a calibration constant (not theory). Compared with the actual result: the side that
  lost less resource value came out ahead.
- target choice: every attack sample (attacker -> target, both units with stats) is scored by the value
  it destroys per second, dps(a, t) * cost(t) / max HP(t), divided by the best such value among the
  enemy units within the attacker's reach at that moment (weapon range + REACH_PAD). 1 = the best
  available target. Side score = mean; "good" >= 0.8, "poor" < 0.5.
- focus fire: per sample, a side's attackers N spread over K distinct targets: focus = 1 - (K - 1)/(N - 1)
  (1 = everyone on one target), weighted by N.
- damage: HP lost by each unit between samples, split among its recorded attackers by expected dps,
  summed per attacker unit type and side; HP lost with no recorded attacker is "unattributed".
- overkill: for each unit that dies, the attackers on it at the last sample before death. Sorted by
  dps, the first ones whose damage until the next sample covers its remaining HP were needed; the
  rest were wasted. Overkill = wasted dps / all dps on dying units. With only 1 s data the window is
  4x coarser, so the figure is rough (data = "1/s").
Not modelled: projectiles in flight, splash, charges, upgrades (base stats only), buildings' weapons.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from counter import load_units, dps  # noqa: E402
from gamedata import resolve  # noqa: E402

TAU = 1.5
REACH_PAD = 8.0          # map units beyond weapon range counted as "within reach"
VIEW_PAD = 1.6           # units within VIEW_PAD * r of the centre are part of the fight view
PRE, POST = 5.0, 5.0     # seconds shown before the first HP loss and after the last death


def nato_class(bp, u):
    """NATO-style symbol class: inf, ranged, cav, horse_archer, siege, monk, villager, hero, naval, other."""
    b = (bp or "").lower()
    c = set(u["classes"]) if u else set()
    if "villager" in b or "worker" in c:
        return "villager"
    if c & {"naval_unit", "ship"} or "ship" in b:
        return "naval"
    if c & {"hero", "leader"} or "khan" in b or "jeanne" in b:
        return "hero"
    if "siege" in c or any(k in b for k in ("mangonel", "trebuchet", "springald", "bombard", "ram", "culverin", "ribauldequin", "nest_of_bees")):
        return "siege"
    if "monk" in c or c & {"religious"} or any(k in b for k in ("monk", "imam", "priest", "shaman")):
        return "monk"
    cav = "cavalry" in c or any(k in b for k in ("horse", "knight", "lancer", "cavalry", "camel", "keshik", "elephant"))
    rng = "ranged" in c or any(k in b for k in ("archer", "crossbow", "handcannon", "longbow", "musket", "arbaletrier"))
    if cav and rng:
        return "horse_archer"
    if cav:
        return "cav"
    if rng:
        return "ranged"
    if "infantry" in c or any(k in b for k in ("spear", "manatarms", "man_at_arms", "maa", "infantry")):
        return "inf"
    return "other"


BUILDING_DPS = 8.0       # weight for attackers without weapon data (Town Centers, towers, keeps)
_names = {}


def type_name(bp):
    """Display name of a unit type (tiers merge: Archer II and Archer III are both "Archer")."""
    if bp not in _names:
        from analyze import load_costs
        from export_view import pretty
        _, full = load_costs()
        c = full.get(resolve(bp, full) or "") if bp else None
        _names[bp] = (c or {}).get("name") or pretty(bp)
    return _names[bp]


def fight_reviews(tl, fights, cost_of):
    U = load_units()
    stats = {}

    def st(bp):
        if bp not in stats:
            k = resolve(bp, U) if bp else None
            stats[bp] = U.get(k) if k else None
        return stats[bp]

    frames, fast = tl["frames"], tl.get("fast") or []
    ftimes = [f["t"] for f in frames]
    has_fast = bool(fast)
    out = []
    for f in fights:
        t0, t1 = f["start"] - PRE, f["end"] + POST
        cx, cz, r = f["x"], f["z"], f["r"]
        R = r * VIEW_PAD
        # unit table: every player entity seen in the view area during the window
        units = {}
        samples = []           # [(t, {id: [x, z, hp, target]})]
        state = {}
        fi = max(0, next((i for i, t in enumerate(ftimes) if t >= t0), len(ftimes)) - 1)
        fs = [s for s in fast if t0 <= s["t"] <= t1]
        si = 0
        while fi < len(frames) and frames[fi]["t"] <= t1:
            fr = frames[fi]
            nxt = frames[fi + 1]["t"] if fi + 1 < len(frames) else fr["t"] + 1
            state = {}
            for e in fr["entities"]:
                if e["x"] is None:
                    continue
                if math.hypot(e["x"] - cx, e["z"] - cz) <= R or e["id"] in units:
                    if e["id"] not in units:
                        units[e["id"]] = {"owner": e["owner"], "bp": e["bp"], "kind": e["kind"]}
                    state[e["id"]] = [e["x"], e["z"], e.get("hp") or 0.0, e.get("target")]
            samples.append((fr["t"], dict(state)))
            # fight samples between this second and the next
            while si < len(fs) and fs[si]["t"] < nxt:
                s = fs[si]
                if s["t"] > fr["t"]:
                    cur = dict(state)
                    for k, v in s["u"].items():
                        k = int(k)
                        if k in units:
                            if v[0] is None:
                                cur.pop(k, None)
                            else:
                                cur[k] = v
                    samples.append((s["t"], cur))
                    state = cur
                si += 1
            fi += 1
        if not samples:
            continue
        pids = sorted({u["owner"] for u in units.values()})
        for k, u in units.items():
            u["stats"] = st(u["bp"])
            u["cls"] = nato_class(u["bp"], u["stats"]) if u["kind"] != "o" else "building"

        # ---- odds at the start
        def side_strength(snap, a, b):
            mine = [(units[k], v) for k, v in snap.items() if units[k]["owner"] == a and units[k]["stats"]
                    and units[k]["cls"] not in ("villager", "building") and math.hypot(v[0] - cx, v[1] - cz) <= 1.5 * r]
            them = [(units[k], v) for k, v in snap.items() if units[k]["owner"] == b and units[k]["stats"]
                    and units[k]["cls"] not in ("villager", "building") and math.hypot(v[0] - cx, v[1] - cz) <= 1.5 * r]
            ht = sum(v[2] for _, v in them)
            if not mine or ht <= 0:
                return 0.0, sum(cost_of(u["bp"]) for u, _ in mine)
            D = sum(dps(u["stats"], w["stats"]) * v2[2] / ht for u, _ in mine for w, v2 in them)
            H = sum(v[2] for _, v in mine)
            return D * H, sum(cost_of(u["bp"]) for u, _ in mine)
        start_snap = min(samples, key=lambda s: abs(s[0] - f["start"]))[1]
        odds = None
        if len(pids) == 2:
            a, b = pids
            pa, va = side_strength(start_snap, a, b)
            pb, vb = side_strength(start_snap, b, a)
            if pa > 0 and pb > 0:
                p = 1 / (1 + math.exp(-math.log(pa / pb) / TAU))
                odds = {"p": {str(a): round(p, 2), str(b): round(1 - p, 2)}, "value": {str(a): round(va), str(b): round(vb)},
                        "predicted": a if p >= 0.5 else b}
        lost = {str(p): 0.0 for p in pids}
        n_lost = {str(p): 0 for p in pids}
        for d in f["deaths"]:
            if str(d["owner"]) in lost:
                lost[str(d["owner"])] += d["cost"] or 0.0
                n_lost[str(d["owner"])] += 1
        if odds:
            a, b = pids
            odds["actual"] = a if lost[str(a)] < lost[str(b)] else b if lost[str(b)] < lost[str(a)] else None
            odds["upset"] = odds["actual"] is not None and odds["actual"] != odds["predicted"]

        # ---- target choice, focus fire, overkill
        tc = {p: [] for p in pids}
        foc = {p: [0.0, 0] for p in pids}
        ok_w = {p: [0.0, 0.0, 0] for p in pids}     # wasted dps, all dps on dying units, kills
        att_lines = []                                 # per sample index: [(attacker, target, score)]
        for i, (t, snap) in enumerate(samples):
            lines = []
            by_side = {p: {} for p in pids}
            for k, v in snap.items():
                tg = v[3]
                if tg is None or tg not in snap or units[k]["owner"] == units.get(tg, {}).get("owner"):
                    continue
                if tg not in units:
                    continue
                by_side[units[k]["owner"]].setdefault(tg, []).append(k)
                a_s, t_s = units[k]["stats"], units[tg]["stats"]
                score = None
                if a_s and t_s:
                    reach = ((a_s.get("w") or {}).get("range") or 0) * 4 + REACH_PAD

                    def val(w):
                        ws = units[w]["stats"]
                        return dps(a_s, ws) * cost_of(units[w]["bp"]) / max(1.0, ws.get("hp") or 0)
                    cands = [w for w, vw in snap.items() if units[w]["owner"] != units[k]["owner"] and units[w]["stats"]
                             and math.hypot(vw[0] - v[0], vw[1] - v[1]) <= reach]
                    if tg not in cands:
                        cands.append(tg)
                    best = max(val(w) for w in cands)
                    if best > 0:
                        score = val(tg) / best
                        tc[units[k]["owner"]].append(score)
                lines.append([k, tg, None if score is None else round(score, 2)])
            att_lines.append(lines)
            for p, tg_map in by_side.items():
                n = sum(len(v) for v in tg_map.values())
                if n > 1:
                    foc[p][0] += (1 - (len(tg_map) - 1) / (n - 1)) * n
                    foc[p][1] += n
            # overkill: targets present now and gone at the next sample
            if i + 1 < len(samples):
                t_next, nxt = samples[i + 1]
                dt = t_next - t
                for p, tg_map in by_side.items():
                    for tg, atts in tg_map.items():
                        if tg in nxt or not units[tg]["stats"]:
                            continue
                        hp = snap[tg][2]
                        ds = sorted((dps(units[a]["stats"], units[tg]["stats"]) for a in atts if units[a]["stats"]), reverse=True)
                        if not ds:
                            continue
                        need, cum = 0, 0.0
                        for d in ds:
                            need += 1
                            cum += d * dt
                            if cum >= hp:
                                break
                        ok_w[p][0] += sum(ds[need:])
                        ok_w[p][1] += sum(ds)
                        ok_w[p][2] += 1
        # ---- damage dealt, by attacker type: each unit's HP drop between two samples is split among the
        # enemy units recorded attacking it, in proportion to their expected dps against it (bonus damage
        # and armour; buildings and units without data count BUILDING_DPS). A unit gone at the next
        # sample lost its remaining HP. HP drops with no recorded attacker are "unattributed".
        rep_bp = {}
        dmg = {p: {} for p in pids}
        unattr = {p: 0.0 for p in pids}
        dead_ids = {d.get("id") for d in f["deaths"]}
        for i in range(len(samples) - 1):
            snap, nxt = samples[i][1], samples[i + 1][1]
            attackers = {}
            for k, v in snap.items():
                tg = v[3]
                if tg is not None and tg in snap and tg in units and units[tg]["owner"] != units[k]["owner"]:
                    attackers.setdefault(tg, []).append(k)
            for k, v in snap.items():
                hp0 = v[2] or 0.0
                if k in nxt:
                    drop = hp0 - (nxt[k][2] or 0.0)
                elif k in dead_ids:
                    drop = hp0
                else:
                    continue
                if drop <= 0.5:
                    continue
                atts = attackers.get(k, [])
                if not atts:
                    for p in pids:
                        if p != units[k]["owner"]:
                            unattr[p] += drop
                    continue
                w = [dps(units[a_]["stats"], units[k]["stats"]) if units[a_]["stats"] and units[k]["stats"] else BUILDING_DPS
                     for a_ in atts]
                tw = sum(w) or 1.0
                for a_, wi in zip(atts, w):
                    side = dmg[units[a_]["owner"]]
                    name = type_name(units[a_]["bp"])
                    side[name] = side.get(name, 0.0) + drop * wi / tw
                    # icon for the merged type: its most expensive tier seen
                    rb = rep_bp.get(name)
                    if rb is None or cost_of(units[a_]["bp"]) > cost_of(rb):
                        rep_bp[name] = units[a_]["bp"]
        damage = {}
        for p in pids:
            tot = sum(dmg[p].values())
            damage[str(p)] = {"total": round(tot), "unattributed": round(unattr[p]),
                              "by": [[n, round(v), rep_bp.get(n)] for n, v in sorted(dmg[p].items(), key=lambda kv: -kv[1]) if v >= 1]}
        # army at the start (units counted for the odds: non-villagers within 1.5 r) and losses, per type
        army = {str(p): {} for p in pids}
        for k, v in start_snap.items():
            u = units[k]
            if u["cls"] not in ("villager", "building") and math.hypot(v[0] - cx, v[1] - cz) <= 1.5 * r:
                army[str(u["owner"])][u["bp"]] = army[str(u["owner"])].get(u["bp"], 0) + 1
        lost_by = {str(p): {} for p in pids}
        for d in f["deaths"]:
            if str(d["owner"]) in lost_by:
                lost_by[str(d["owner"])][d["bp"]] = lost_by[str(d["owner"])].get(d["bp"], 0) + 1
        by_val = lambda m: [[bp, n] for bp, n in sorted(m.items(), key=lambda kv: -cost_of(kv[0]) * kv[1])]  # noqa: E731
        res = {"n": f["n"], "start": f["start"], "end": f["end"], "x": cx, "z": cz, "r": r, "damage": damage,
               "data": "4/s" if has_fast and any(f["start"] - 1 <= s["t"] <= f["end"] + 1 for s in fast) else "1/s",
               "lost": {k: round(v) for k, v in lost.items()}, "unitsLost": n_lost, "odds": odds,
               "army": {k: by_val(v) for k, v in army.items()}, "lostBy": {k: by_val(v) for k, v in lost_by.items()},
               "target": {str(p): None if not v else {"score": round(sum(v) / len(v), 2), "n": len(v),
                                                      "good": round(sum(1 for x in v if x >= 0.8) / len(v), 2),
                                                      "poor": round(sum(1 for x in v if x < 0.5) / len(v), 2)}
                          for p, v in tc.items()},
               "focus": {str(p): None if not v[1] else round(v[0] / v[1], 2) for p, v in foc.items()},
               "overkill": {str(p): None if not v[1] else {"wasted": round(v[0] / v[1], 2), "kills": v[2]}
                            for p, v in ok_w.items()},
               "units": units, "samples": samples, "lines": att_lines}
        out.append(res)
    return out
