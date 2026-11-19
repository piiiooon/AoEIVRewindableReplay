"""Aura and cast buffs from positions (owner 2026-11-12: "aura buffs can be checked post data recording, if a unit enters the
radius they would get buffed"; review only - full information).

Sources, from aoe4world's ability data (data/abilities.json: auraRange in tiles, activatedOn units / buildings, effects with a
select of unit classes / ids):
  always   passive auras: on while the source stands (buildings: finished). Source = an entity whose base id is in
           activatedOn, or an entity the dump's ability events name as the caster of that ability (field_stone_buff_info_byz
           has no activatedOn).
  toggle   on from the source's AbilityExecuted of that toggle until it executes another toggle (dump v12+ AB events; the
           replay's cast / stop commands too). Abilities named *default* are on from the start.
  manual / timed   a cast (AB AbilityExecuted, or the replay's ability command) lasts DURATION (build_3d.KNOWN_DUR, else the
           effect's duration, else DEFAULT_S).
Who gets it: a cast with no activatedOn = the caster only (Trample). Else the source owner's entities matching the effect's select (units.json classes / base id; buildings by base id or
class "building"), within auraRange x 4 map units of the source each second; auraRange 0 / None = the whole map (Triumph:
all of the player's cavalry). Spans per entity [id, ability, start, end] merged over consecutive seconds.
Not modelled: auras that need a condition (sacred sites, relics, "while attacking"), stacking limits, enemy debuff auras
(effects on the other player's units: listed with "debuff" when the name says so, not placed).

    python analyzer/auras.py work/<name>.timeline.json [--replay <file>] [out.json]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedata import class_match, resolve   # noqa: E402

TILE = 4.0
DEFAULT_S = 10.0
STEP_GAP = 1.6        # s: a span continues while the gaps between seconds stay below this
DEBUFF_RE = re.compile(r"debuff|curse|poison|bleed|slow|stun", re.I)
# casts whose buff stays on a unit until the window ends once it has been inside the radius (owner 2026-11-12: Akritoi Defense -
# villagers within 9.5 tiles of the cistern get +2 melee / ranged armour and a spear attack for 30 s, keep it after leaving, and
# villagers entering later get it for what is left)
STICKY = {"activate_akritoi_byz", "landmark_activate_akritoi_byz"}
# game ability names aoe4world lists under another entry (the regular cistern's Akritoi = the landmark cistern's entry)
ALIAS = {"activate_akritoi_byz": "landmark_activate_akritoi_byz"}


def _load(name, key=None):
    try:
        d = json.load(open(os.path.join(HERE, "..", "data", name), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d.get(key, {}) if key else d


def known_durations():
    try:
        sys.path.insert(0, os.path.join(HERE, "..", "viewer"))
        from build_3d import KNOWN_DUR
        return dict(KNOWN_DUR)
    except Exception:  # noqa: BLE001 - build_3d needs nothing at import, but stay independent
        return {"hippodrome_triumph_byz": 45}


class Classes:
    """base id + classes of a blueprint (units.json; buildings: production.json buildingBase + "building")"""

    def __init__(self):
        self.U = _load("units.json", "units")
        self.B = _load("production.json").get("buildingBase") or {}
        self.cache = {}

    def of(self, bp):
        if bp not in self.cache:
            u = self.U.get(bp) or self.U.get(resolve(bp, self.U) or "")
            if u:
                self.cache[bp] = (u.get("base") or "", set(u.get("classes") or []))
            elif bp.startswith("building_"):
                b = self.B.get(bp) or self.B.get(resolve(bp, self.B) or "") or ""
                self.cache[bp] = (b, {"building"})
            else:
                self.cache[bp] = ("", set())
        return self.cache[bp]


def selects(sel, base, cls):
    if not sel:
        return False
    if base and base in (sel.get("id") or []):
        return True
    return any(class_match(g, cls) for g in (sel.get("class") or []))


# auras aoe4world's data does not have (owner's rules)
OWNER_AURAS = [
    # owner 2026-11-13: Lord of Lancaster Inspiration (passive) - all military units within 5 tiles gain +5 % health, the Lord
    # included; stacks for each Lord
    {"attrib": "lord_of_lancaster_inspiration_lan", "name": "Lord of Lancaster Inspiration", "pbg": 0, "active": "always",
     "range": 5 * TILE, "civs": {"hl"}, "on": ["lord-of-lancaster"], "debuff": False, "stack": True,
     "effects": [{"property": "hitpoints", "effect": "multiply", "value": 1.05, "select": {"class": [["military"]]}}]},
]


def aura_table():
    out = {}
    for pbg, a in _load("abilities.json", "abilities").items():
        eff = [e for e in a.get("effects") or [] if e.get("property") not in (None, "unknown")]
        out[a["attrib"]] = {"attrib": a["attrib"], "name": a.get("name") or a["attrib"], "pbg": int(pbg),
                            "active": a.get("active"), "range": (a.get("auraRange") or 0) * TILE, "civs": set(a.get("civs") or []),
                            "on": [x.split("/", 1)[-1] for x in a.get("activatedOn") or []], "effects": eff,
                            "debuff": bool(DEBUFF_RE.search(a["attrib"]))}
    for a in OWNER_AURAS:
        out.setdefault(a["attrib"], dict(a))
    return out


def _squad_entities(tl):
    sq = {}
    for fr in tl["frames"][::5]:
        for e in fr["entities"]:
            if e.get("squad") is not None and e["id"] is not None:
                sq.setdefault(e["squad"], set()).add(e["id"])
    return sq


def casts(tl, A, replay=None):
    """[(t, caster entity id, attrib, kind)] kind = cast / stop; dump AB events + the replay's ability commands"""
    out = []
    for r in tl.get("abilities") or []:
        t, ev, caster, ab = r[0], r[1], r[2], ALIAS.get(r[3], r[3])
        if ev == "AbilityExecuted" and ab in A and str(caster).isdigit():
            out.append((t, int(caster), ab, "cast"))
    if replay:
        try:
            from replay import abilities
            by_pbg = {v["pbg"]: k for k, v in A.items()}
            sq = _squad_entities(tl)
            for c in abilities(replay):
                ab = by_pbg.get(c.get("pbg"))
                if not ab:
                    continue
                ents = list(c.get("entities") or [])
                for s_ in c.get("squads") or []:
                    ents += sorted(sq.get(s_, ()))[:1]
                for e in ents:
                    out.append((c["t"], e, ab, "stop" if c.get("kind") == "stop" else "cast"))
        except Exception as e:  # noqa: BLE001 - the replay only adds casts
            print(f"  replay ability commands: {e}")
    out.sort()
    # the same cast from both sources within 1 s: keep one
    ded, last = [], {}
    for x in out:
        k = (x[1], x[2], x[3])
        if k in last and x[0] - last[k] < 1.0:
            continue
        last[k] = x[0]
        ded.append(x)
    return ded


def auras(tl, replay=None):
    A = aura_table()
    from techs_bought import civ_code
    pcode = {}
    for pl in tl["players"]:
        try:
            pcode[pl["idx"]] = civ_code(tl, pl["idx"])
        except (StopIteration, KeyError):
            pcode[pl["idx"]] = None
    C = Classes()
    dur = known_durations()
    frames = tl["frames"]
    cl = casts(tl, A, replay)
    # callers of always-on abilities from the dump's events / runs (field_stone_buff_info_byz: the buildings themselves)
    callers = {}
    for r in tl.get("abilities") or []:
        if r[3] in A and str(r[2]).isdigit():
            callers.setdefault(r[3], set()).add(int(r[2]))
    for r in tl.get("abilityRuns") or []:
        if r[2] in A and str(r[1]).isdigit():
            callers.setdefault(r[2], set()).add(int(r[1]))
    # the dump's AbilityComplete = the real end of a cast (v19+; Triumph 806.75 -> 840.75 = 34 s, 922.75 -> 933.75 = 11 s)
    completes = {}
    for r in tl.get("abilities") or []:
        if r[1] == "AbilityComplete" and str(r[2]).isdigit():
            completes.setdefault((int(r[2]), r[3]), []).append(r[0])
    # Triumph without an end event (owner 2026-11-12): 1 s per supply point, max 45; 10 points when the Hippodrome is done,
    # +1 per 25 s, all spent by a cast (259818624: the rule gives 29 s for the first cast, the game ran 34 s)
    done_at, spent_at = {}, {}
    for fr in frames:
        for e_ in fr["entities"]:
            if "hippodrome" in (e_["bp"] or "") and e_["build"] is None and e_["id"] not in done_at:
                done_at[e_["id"]] = fr["t"]

    def triumph_s(e_, t):
        if e_ in spent_at:
            pts = (t - spent_at[e_]) / 25.0
        else:
            pts = 10 + (t - done_at.get(e_, t)) / 25.0
        spent_at[e_] = t
        return max(1.0, min(45.0, float(int(pts))))

    # timed / toggle windows per (caster, ability): [start, end]
    windows = {}
    toggles = {}
    for t, e, ab, kind in cl:
        a = A[ab]
        if a["active"] == "toggle":
            prev = toggles.get(e)
            if prev and prev[1] != ab or (prev and kind == "stop"):
                windows.setdefault((e, prev[1]), []).append([prev[0], t])
                toggles.pop(e, None)
            if kind == "cast" and not (prev and prev[1] == ab):
                toggles[e] = (t, ab)
        elif kind == "cast":
            end = next((c for c in completes.get((e, ab), []) if 0 < c - t <= 120), None)
            if end is None and ab == "hippodrome_triumph_byz":
                end = t + triumph_s(e, t)
            if end is None:
                end = t + (dur.get(ab) or max([x.get("duration") or 0 for x in a["effects"]] + [0]) or DEFAULT_S)
            windows.setdefault((e, ab), []).append([t, end])
    end_t = frames[-1]["t"] if frames else 0
    for e, (t0, ab) in toggles.items():
        windows.setdefault((e, ab), []).append([t0, end_t])

    spans, open_ = [], {}           # open_: (target, ability) -> [start, last]
    held = set()                    # (source, ability, entity) inside a sticky cast's radius at some point
    used = {}

    def touch(i, ab, t):
        k = (i, ab)
        s = open_.get(k)
        if s and t - s[1] <= STEP_GAP:
            s[1] = t
        else:
            if s:
                spans.append([i, ab, s[0], s[1]])
            open_[k] = [t, t]

    stacks, last_n = {}, {}         # stackable auras: (ability) -> {entity: [[t0, t1, n]]} segments of a constant stack count

    for fr in frames:
        t = fr["t"]
        cnt = {}                    # (entity, stackable ability) -> sources in range this frame
        ents = [e for e in fr["entities"] if e["id"] is not None and e["x"] is not None]
        by_owner = {}
        for e in ents:
            by_owner.setdefault(e["owner"], []).append(e)
        active = []                 # (source entity, ability)
        for e in ents:
            base, _ = C.of(e["bp"])
            if e.get("build") is not None and e["bp"].startswith("building_"):
                continue            # under construction
            for ab in AURAS_BY_BASE.get(base, ()) if AURAS_BY_BASE else ():
                a = A[ab]
                if a["active"] == "always" or (a["active"] == "toggle" and "default" in ab):
                    active.append((e, ab))
        ids = {e["id"]: e for e in ents}
        for ab, cs in callers.items():
            if A[ab]["active"] == "always":
                for i in cs:
                    if i in ids and (ids[i], ab) not in active:
                        active.append((ids[i], ab))
        for (i, ab), W in windows.items():
            if i in ids and any(w0 <= t <= w1 for w0, w1 in W):
                active.append((ids[i], ab))
        for src, ab in active:
            a = A[ab]
            if not a["effects"] or a["debuff"]:
                continue
            if a["civs"] and pcode.get(src["owner"]) not in a["civs"]:
                continue            # another civ's aura on a shared base id (Network of Castles on any town centre)
            if not a["range"] and a["active"] == "always":
                continue            # no radius in the data: not placed (listed under "no radius")
            r2 = a["range"] ** 2
            used[ab] = used.get(ab, 0) + 1
            if a["active"] in ("manual", "timed") and not a["on"]:
                # cast by a unit with nothing it sits on in the data = a self buff (Trample: the cataphract that cast it;
                # aoe4world's 7.5-tile range is the trample's reach, not a buff radius)
                base, cls = C.of(src["bp"])
                if any(selects(x.get("select"), base, cls) for x in a["effects"]):
                    touch(src["id"], ab, t)
                continue
            sticky = ab in STICKY and a["active"] in ("manual", "timed")
            for e in by_owner.get(src["owner"], ()):
                if sticky and (src["id"], ab, e["id"]) in held:
                    touch(e["id"], ab, t)               # once inside, kept until the window ends
                    continue
                if r2 and (e["x"] - src["x"]) ** 2 + (e["z"] - src["z"]) ** 2 > r2:
                    continue
                if sticky:
                    held.add((src["id"], ab, e["id"]))
                base, cls = C.of(e["bp"])
                if any(selects(x.get("select"), base, cls) for x in a["effects"]):
                    touch(e["id"], ab, t)
                    if a.get("stack"):
                        cnt[(e["id"], ab)] = cnt.get((e["id"], ab), 0) + 1
        # stack segments: a new one whenever the count changes, closed when the unit leaves every source's range
        for k in set(cnt) | {k for k, v in last_n.items() if v[0] > 0}:
            n = cnt.get(k, 0)
            prev = last_n.get(k)
            segs = stacks.setdefault(k[1], {}).setdefault(k[0], [])
            if prev and prev[0] == n and n > 0 and t - prev[1] <= STEP_GAP:
                segs[-1][1] = t
                last_n[k] = (n, t)
                continue
            if n > 0:
                segs.append([t, t, n])
            last_n[k] = (n, t)
    for (i, ab), s in open_.items():
        spans.append([i, ab, s[0], s[1]])
    spans.sort(key=lambda s: (s[2], s[0]))
    summ = {}
    for i, ab, t0, t1 in spans:
        r = summ.setdefault(ab, {"ability": ab, "name": A[ab]["name"], "active": A[ab]["active"], "range": A[ab]["range"],
                                 "entities": set(), "seconds": 0.0, "first": t0, "last": t1, "sourceSeconds": used.get(ab, 0),
                                 "effects": [[x["property"], x["effect"], x["value"]] for x in A[ab]["effects"]]})
        r["entities"].add(i)
        r["seconds"] += t1 - t0 + 1
        r["first"], r["last"] = min(r["first"], t0), max(r["last"], t1)
    rows = sorted(({**r, "entities": len(r["entities"]), "seconds": round(r["seconds"])} for r in summ.values()),
                  key=lambda r: -r["seconds"])
    # per player and ability: merged intervals [start, end, peak units buffed at once] (the viewer's buffs lane)
    owner = {}
    for fr in frames[::5]:
        for e in fr["entities"]:
            if e["id"] is not None:
                owner.setdefault(e["id"], e["owner"])
    ev = {}
    for i, ab, t0, t1 in spans:
        p = owner.get(i)
        if p is not None:
            ev.setdefault((p, ab), []).extend([(t0, 1), (t1 + 1.0, -1)])
    by_player = {}
    for (p, ab), L in ev.items():
        L.sort()
        cur, peak, start, out_ = 0, 0, None, []
        for t, d in L:
            cur += d
            if cur > 0 and start is None:
                start, peak = t, cur
            elif cur > 0:
                peak = max(peak, cur)
            elif cur == 0 and start is not None:
                out_.append([round(start, 1), round(t - 1.0, 1), peak])
                start = None
        by_player.setdefault(str(p), {})[ab] = out_
    return {"spans": [[i, ab, round(t0, 1), round(t1, 1)] for i, ab, t0, t1 in spans], "summary": rows,
            "effects": {ab: A[ab]["effects"] for ab in summ}, "casts": len(cl), "byPlayer": by_player,
            "names": {ab: A[ab]["name"] for ab in summ},
            "stacks": {ab: {str(i): [[round(a_, 1), round(b_, 1), n] for a_, b_, n in L] for i, L in E.items() if L}
                       for ab, E in stacks.items()}}


AURAS_BY_BASE = None


def _by_base(A):
    out = {}
    for ab, a in A.items():
        for b in a["on"]:
            out.setdefault(b, []).append(ab)
    return out


def run(tl, replay=None):
    global AURAS_BY_BASE
    AURAS_BY_BASE = _by_base(aura_table())
    return auras(tl, replay)


def _mm(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main():
    args = [a for a in sys.argv[1:]]
    rep = None
    if "--replay" in args:
        i = args.index("--replay")
        rep = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    tl = json.load(open(args[0], encoding="utf-8"))
    R = run(tl, rep)
    out = args[1] if len(args) > 1 else os.path.splitext(args[0].replace(".timeline", ""))[0] + ".auras.json"
    json.dump(R, open(out, "w", encoding="utf-8"))
    print(f"{R['casts']} casts / toggles; {len(R['spans'])} buff spans")
    for r in R["summary"]:
        eff = ", ".join(f"{p} {'x' if e == 'multiply' else '+'}{v if v is not None else '?'}" for p, e, v in r["effects"])
        print(f"  {r['name'][:30]:30} {r['active'] or '':7} r {r['range']:5g}  units {r['entities']:4}  unit-s {r['seconds']:7}"
              f"  {_mm(r['first'])}-{_mm(r['last'])}  {eff}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
