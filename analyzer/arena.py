"""Fight arenas (owner 2026-11-11): who started a fight, who fled, who came back, who joined as reinforcement - and an
arena that follows the armies when one side kites and the other chases. Log-parsing side only (no recorder change):
1 s positions of every unit + the game's damage events (dump v9+; older logs: movement only).

Per fights.json fight (death clusters), in time order:
1. start t0 = the earliest damage between players near the fight (victim within r + 30 of its centre), going back from
   the fight's first death while the hits are no more than GAP_START s apart (at most 30 s back).
2. snapshot at t0: each side's army units (kind m) within max(r + 20, 30) of the centre = "start".
3. every second: each side's centre = value-weighted middle of its active units (start + reinforcements + returned, alive,
   not fled); arena centre = the middle of both centres, radius = max(25, half their distance + 20) - it moves with a
   kite and chase.
   - fled: an active unit beyond radius + 5 of the arena centre, moving away from the enemy centre (vs 3 s before) and with
     no damage dealt or taken for FLEE_QUIET s. Marked with the time and its HP share (HP now / HP first seen).
   - returned: a fled unit back inside the arena that deals or takes damage.
   - reinforcement: an army unit that was not in the snapshot, inside the arena, dealing or taking damage there.
   - end: no damage between players involving any arena unit for END_QUIET s -> end = the last such hit; or one side has no
     active unit left (after the last hit). Fights that start inside an arena already running are merged into it.
Output per arena: s / e, the fights merged, per side the unit lists (start, reinf, fled, returned, died), and the track
(every 2 s: t, arena centre x z, radius, side centres).
"""
import bisect
import math

GAP_START = 10.0     # s between hits when walking back to the fight's first damage
FLEE_QUIET = 5.0     # s without damage dealt or taken before a unit beyond the arena counts as fled
END_QUIET = 10.0     # s without damage between arena units = the fight is over
MIN_R = 25.0
START_WIN = 5.0      # s after the start: units fighting then (near the circle) count as starters
TRACK_STEP = 2.0
MAX_LEN = 900.0      # s: an arena never runs longer (safety)


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def arenas(tl, fights, cost_of):
    frames = tl["frames"]
    if not frames:
        return []
    pids = {p["idx"] for p in tl["players"]}
    ft = [fr["t"] for fr in frames]
    info, first_hp = {}, {}
    for fr in frames:
        for e in fr["entities"]:
            if e["id"] not in info:
                info[e["id"]] = (e["owner"], e["bp"], e["kind"])
            if e.get("hp") and e["id"] not in first_hp:
                first_hp[e["id"]] = e["hp"]
    # damage between players (deflected hits count as contact too)
    hits = [h for h in (tl.get("hits") or [])
            if info.get(h[1], (None,))[0] in pids and info.get(h[2], (None,))[0] in pids
            and info[h[1]][0] != info[h[2]][0]]
    hits.sort(key=lambda h: h[0])
    ht = [h[0] for h in hits]
    combat = {}
    for h in hits:
        combat.setdefault(h[1], []).append(h[0])
        combat.setdefault(h[2], []).append(h[0])

    def fought(i, a, b):                          # unit i dealt / took damage in (a, b]
        L = combat.get(i)
        if not L:
            return False
        k = bisect.bisect_right(L, a)
        return k < len(L) and L[k] <= b

    def last_fight(i, t):
        L = combat.get(i)
        if not L:
            return None
        k = bisect.bisect_right(L, t)
        return L[k - 1] if k else None

    def frame_at(t):
        return frames[max(0, bisect.bisect_right(ft, t) - 1)]

    out = []
    for F in sorted(fights, key=lambda f: f["start"]):
        if out and out[-1]["s"] - 1 <= F["start"] <= out[-1]["e"] + 5:
            out[-1]["fights"].append(F["n"])
            continue
        cx, cz, r = F["x"], F["z"], F.get("r") or 15
        # 1. start
        lo, hi = bisect.bisect_left(ht, F["start"] - 30), bisect.bisect_right(ht, F["start"] + 1)
        near = hits[lo:hi]
        t0 = F["start"]
        pos_cache = {}

        def pos_of(i, t):
            k = (i, int(t))
            if k not in pos_cache:
                fr = frame_at(t)
                pos_cache[k] = next(((e["x"], e["z"]) for e in fr["entities"] if e["id"] == i and e["x"] is not None), None)
            return pos_cache[k]

        for h in reversed(near):
            p = pos_of(h[2], h[0])
            if p and _d(p, (cx, cz)) <= r + 30 and t0 - h[0] <= GAP_START:
                t0 = min(t0, h[0])
        # 2. snapshot
        fr0 = frame_at(t0)
        R0 = max(r + 20, 30)
        role, side_of = {}, {}
        for e in fr0["entities"]:
            if e["kind"] != "m" or e["owner"] not in pids or e["x"] is None:
                continue
            dd = _d((e["x"], e["z"]), (cx, cz))
            # in the circle at the start, or fighting in the first START_WIN s a bit further out (the fight's circle comes
            # from where units died, which can be off to one side)
            if dd <= R0 or (dd <= R0 + 25 and fought(e["id"], t0 - 0.01, t0 + START_WIN)):
                role[e["id"]] = ["start", t0]
                side_of[e["id"]] = e["owner"]
        fled, returned, reinf, died = {}, {}, {}, {}
        track, last_hit, prev_c = [], t0, {}
        hist = {}                                # side -> [(t, centre)]
        t, end = t0, None
        i0 = bisect.bisect_left(ft, t0)
        for fi in range(i0, len(frames)):
            fr = frames[fi]
            t = fr["t"]
            if t - t0 > MAX_LEN:
                end = last_hit
                break
            ents = {e["id"]: e for e in fr["entities"] if e["x"] is not None}
            for i in list(role):
                if i not in ents and i not in died and fr["t"] > t0:
                    died[i] = t
            active = {p: [] for p in pids}
            for i, sd in side_of.items():
                if i in ents and i not in died and (i not in fled or i in returned and returned[i] > fled[i][0]):
                    active[sd].append(ents[i])
            cen = {}
            for p, L in active.items():
                if L:
                    w = [max(1.0, cost_of(e["bp"])) for e in L]
                    W = sum(w)
                    cen[p] = (sum(e["x"] * k for e, k in zip(L, w)) / W, sum(e["z"] * k for e, k in zip(L, w)) / W)
                    hist.setdefault(p, []).append((t, cen[p]))
            if cen:
                ax = sum(c[0] for c in cen.values()) / len(cen)
                az = sum(c[1] for c in cen.values()) / len(cen)
                cs = list(cen.values())
                rad = max(MIN_R, (_d(cs[0], cs[1]) / 2 if len(cs) > 1 else 0) + 20)
            else:
                ax, az, rad = cx, cz, MIN_R
            # reinforcements / returns
            for e in ents.values():
                i = e["id"]
                if e["kind"] != "m" or e["owner"] not in pids or _d((e["x"], e["z"]), (ax, az)) > rad:
                    continue
                if not fought(i, t - 1, t):
                    continue
                if i not in role:
                    role[i] = ["reinf", t]
                    side_of[i] = e["owner"]
                    reinf[i] = t
                elif i in fled and (i not in returned or returned[i] < fled[i][0]):
                    returned[i] = t
            # fled
            for p, L in active.items():
                enemy = [c for q, c in cen.items() if q != p]
                for e in L:
                    i = e["id"]
                    if _d((e["x"], e["z"]), (ax, az)) <= rad + 5:
                        continue
                    lf = last_fight(i, t)
                    if lf is not None and t - lf < FLEE_QUIET:
                        continue
                    if lf is None and t - role[i][1] < FLEE_QUIET:
                        continue
                    if enemy:
                        back = pos_of(i, t - 3)
                        if back and _d(back, enemy[0]) >= _d((e["x"], e["z"]), enemy[0]):
                            continue        # not moving away from the enemy
                    hp0 = first_hp.get(i) or e.get("hp") or 1
                    fled[i] = [t, round((e.get("hp") or 0) / hp0, 2)]
            # last damage involving arena units
            k0 = bisect.bisect_right(ht, t - 1)
            for h in hits[k0:bisect.bisect_right(ht, t)]:
                if h[1] in role or h[2] in role:
                    last_hit = max(last_hit, h[0])
            if not track or t - track[-1][0] >= TRACK_STEP:
                track.append([round(t, 1), round(ax, 1), round(az, 1), round(rad, 1)]
                             + [v for p in sorted(pids) for v in (cen.get(p) and [round(cen[p][0], 1), round(cen[p][1], 1)] or [None, None])])
            if t - last_hit > END_QUIET and t > F["end"]:
                end = last_hit
                break
            if t > last_hit + 2 and t > F["end"] and len([p for p in pids if active[p]]) < 2:
                end = last_hit
                break
        if end is None:
            end = last_hit
        end = max(end, F["end"])
        track = [x for x in track if x[0] <= end + TRACK_STEP]
        sides = {}
        for p in pids:
            mine = [i for i, s in side_of.items() if s == p]
            sides[str(p)] = {
                "start": [i for i in mine if role[i][0] == "start"],
                "reinf": [[i, reinf[i]] for i in mine if i in reinf and reinf[i] <= end],
                "fled": [[i] + fled[i] for i in mine if i in fled and fled[i][0] <= end + 1],
                "returned": [[i, returned[i]] for i in mine if i in returned and returned[i] <= end],
                "died": [[i, died[i]] for i in mine if i in died and died[i] <= end + 2],
            }
        out.append({"n": F["n"], "fights": [F["n"]], "s": round(t0, 1), "e": round(end, 1), "sides": sides, "track": track,
                    "bp": {str(i): info[i][1] for i in side_of}})
    return out


if __name__ == "__main__":
    import json
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from analyze import load_costs
    from gamedata import resolve
    tl = json.load(open(sys.argv[1], encoding="utf-8"))
    F = json.load(open(sys.argv[2], encoding="utf-8"))
    tbl, _ = load_costs()
    A = arenas(tl, F["fights"], lambda bp: tbl.get(resolve(bp, tbl), 0.0))
    for a in A:
        print(f"fights {a['fights']} {a['s']:.0f}-{a['e']:.0f}s:",
              "; ".join(f"P{p} start {len(v['start'])} reinf {len(v['reinf'])} fled {len(v['fled'])} returned {len(v['returned'])} died {len(v['died'])}"
                        for p, v in a["sides"].items()))
