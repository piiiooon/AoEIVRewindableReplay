"""Buffs / debuffs from stat differences (owner 2026-11-12: "one other way to check for buffs or debuffs would be how stat
is different from the calculated stats"; review only - full information).

Each stat the recording shows is compared with what data/units.json + the upgrades the player had completed by then
predict (fightcal.stats / fightcal.hit, aoe4world effects; techs_bought for the completion times):
  damage   every recorded hit (dump v9 GE_DamageReceived) between two units of different players: observed damage vs
           expected (base + bonus vs the victim's classes - armour, floor 1, per projectile); the killing hit (hp after 0)
           reports only the HP left and is skipped; hits of buildings / siege / splash weapons are left out (no data /
           area damage), hits on buildings listed apart (building armour is not in units.json)
  hp       each unit's highest HP seen (E records, 1 s) vs its calculated maximum
  interval each attacker's time between consecutive hits on the same target vs its weapon period (median per blueprint;
           stretches with intervals < INT_FAST x period = attack-speed buff)
  speed    distance per second while flagged moving vs walk speed (90th percentile per blueprint; seconds > SPD_FAST x
           walk = speed buff or charge)
  self     hits where attacker = victim (palings: the damage event names the knight as attacker and itself as victim)
Output: work/<name>.statdiff.json + a text summary. Deviations are what a known buff (aura / cast) should explain;
the rest are the "find the source" list.

    python analyzer/statdiff.py work/<name>.timeline.json [out.json]
"""
import bisect
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fightcal import effects_of, hit, stats   # noqa: E402
from techs_bought import civ_code, techs_bought  # noqa: E402

DMG_TOL = 0.51        # observed - expected beyond this = a deviation (game damage is in 0.5 steps or finer)
HP_TOL = 1.0
INT_FAST, INT_SLOW = 0.85, 1.25
SPD_FAST = 1.15
MIN_N = 3             # hits / samples before a blueprint pair is reported

from dot import DOTS, DOT_TOL, tick_of, too_old, bp_index as _index, who as _who   # noqa: E402,F401 - damage over time: analyzer/dot.py

# second weapons the data has no entry for (owner 2026-11-12): Malian spearmen's donso javelin throw - ranged 5 / 7 / 8 / 10
# (regular / hardened / veteran / elite), +5 / +7 / +8 / +10 vs cavalry, range 6.5 tiles (min 2.5), every 15 s. 259818624: it
# also takes the blacksmith's ranged damage upgrades (+1 per stage done; aoe4world lists them for ranged units only):
# hardened vs horseman 7 + 7 - 2 = 12 (x19), vs Byzantine spearman / longbowman 7 - 1 = 6, veteran vs knight 10 + 1 = 11
ALT_WEAPONS = [
    {"name": "donso javelin throw", "att": re.compile(r"unit_spearman_(\d)_mal"), "type": "ranged",
     "dmg": {"1": 5, "2": 7, "3": 8, "4": 10}, "vs": [("cavalry", {"1": 5, "2": 7, "3": 8, "4": 10})],
     "ups": re.compile(r"upgrade_ranged_damage_i+$")},
]


def alt_expected(abp, A, V, ups_done):
    """[(name, expected damage)] of the attacker's second weapons"""
    out = []
    for w in ALT_WEAPONS:
        m = w["att"].search(abp)
        if not m:
            continue
        tier = m.group(1)
        d = w["dmg"].get(tier, 0) + sum(1 for u in ups_done if w["ups"].search(u))
        for cls, b in w["vs"]:
            if cls in V["classes"]:
                d += b.get(tier, 0)
        d -= V["rarmor"] if w["type"] == "ranged" else V["marmor"]
        out.append((w["name"], max(1.0, d)))
    return out


def _ups_by_player(tl):
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        bought = {}
    out = {}
    for p, v in bought.items():
        out[p] = sorted((x["done"], x["attrib"]) for x in v)
    return out


class Calc:
    """calculated stats of a blueprint for a player at a time (upgrades completed by then), cached"""

    def __init__(self, tl):
        self.ups = _ups_by_player(tl)
        self.code = {}
        for pl in tl["players"]:
            try:
                self.code[pl["idx"]] = civ_code(tl, pl["idx"])
            except (StopIteration, KeyError):
                self.code[pl["idx"]] = None
        self.done_t = {p: [u[0] for u in v] for p, v in self.ups.items()}
        self.cache = {}

    def done(self, p, t):
        n = bisect.bisect_right(self.done_t.get(p, []), t)
        return [a for _, a in self.ups.get(p, [])[:n]]

    def at(self, bp, p, t):
        n = bisect.bisect_right(self.done_t.get(p, []), t)
        key = (bp, p, n)
        if key not in self.cache:
            names = [a for _, a in self.ups.get(p, [])[:n]]
            self.cache[key] = stats(bp, effects_of(names, self.code.get(p)))
        return self.cache[key]


def _mm(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


BUFFS = {}           # entity id -> [(t0, t1, ability)] from analyzer/auras.py (set by statdiff())
BUFF_FX = {}         # ability -> aoe4world effects


def buff_adjust(exp, A, V, a, v, t):
    """expected damage with the attacker's attack buffs and the victim's armour buffs active at t -> (value, names)"""
    from auras import selects
    names, add, mul = [], 0.0, 1.0
    atk = "meleeAttack" if A["type"] == "melee" else "rangedAttack"
    arm = "meleeArmor" if A["type"] == "melee" else "rangedArmor"
    for who, props, S in ((a, (atk,), A), (v, (arm,), V)):
        for t0, t1, ab in BUFFS.get(who, ()):
            if not (t0 - 0.5 <= t <= t1 + 1.0):
                continue
            for e in BUFF_FX.get(ab, ()):
                if e.get("property") not in props or e.get("value") is None or not selects(e.get("select"), S["base"], S["classes"]):
                    continue
                val = float(e["value"])
                if who == a:
                    if e.get("effect") == "multiply":
                        mul *= val
                    else:
                        add += val
                else:
                    add -= val if e.get("effect") != "multiply" else 0.0
                names.append(ab)
    if not names:
        return exp, []
    return round(max(1.0, exp * mul + add), 2), sorted(set(names))


def buffed(i, t, props):
    """names of the buffs on entity i at t with an effect on one of props (moveSpeed / attackSpeed ...)"""
    out = []
    for t0, t1, ab in BUFFS.get(i, ()):
        if t0 - 0.5 <= t <= t1 + 1.0 and any(e.get("property") in props for e in BUFF_FX.get(ab, ())):
            out.append(ab)
    return out


def damage_check(tl, calc, hist):
    pairs = collections.OrderedDict()
    selfhits, on_bld, heals = collections.Counter(), collections.Counter(), collections.Counter()
    src = {}             # (victim, damage-over-time source) -> [(t, attacker bp)] of the hits that start ticks
    dots = collections.OrderedDict()
    for h in sorted(tl.get("hits") or [], key=lambda h: h[0]):
        t, a, v, dmg, hp_after = h[0], h[1], h[2], h[3], h[4]
        if dmg is None or dmg <= 0:
            continue
        abp, ap = _who(hist, a, t)
        vbp, vp = _who(hist, v, t)
        if not abp or not vbp:
            continue
        if len(h) > 6 and h[6] is True:
            # the game flags heals / repair as isRepairing (dump v18; owner 2026-11-12: Triumph's 2.5 / s regeneration
            # shows as the unit "damaging" itself) - not damage
            heals[(abp, round(dmg, 2), "self" if a == v else "other")] += 1
            continue
        if a == v:
            if abp.startswith("building_") and (not hp_after or hp_after <= 0):
                heals[(abp, round(dmg, 2), "deleted by its owner")] += 1   # owner 2026-11-12: Malian houses around a pit
                continue                                                    # mine, deleted to make room for a mining camp
            selfhits[(abp, round(dmg, 2))] += 1
            continue
        if ap == vp:
            continue
        # owner 2026-11-12 (259818624): a poison tick is credited to the victim's latest attacker, not the unit that
        # poisoned it (mansa ticks named after a Malian spearman walking away 30 units off, or the town centre) - so a tick
        # is matched against every source hit on that victim, whoever the event names
        cand = [d for d in DOTS if abs(dmg - d["tick"]) < 0.01]
        if cand:
            hit_dot = None
            for d in cand:
                ts = src.get((v, d["name"]), [])
                for t0, sa in reversed(ts):
                    if too_old(d, t, t0):
                        break
                    if tick_of(d, t, t0):                  # analyzer/dot.py: the same rule as the re-credit
                        hit_dot, src_bp = d, sa
                        break
                if hit_dot:
                    break
            if hit_dot:
                r = dots.setdefault((hit_dot["name"], src_bp), {"source": hit_dot["name"], "att": src_bp, "ticks": 0, "dmg": 0.0,
                                                                "victims": set(), "first": t, "last": t, "named": collections.Counter()})
                r["named"][abp] += 1                   # who the event names
                r["ticks"] += 1
                r["dmg"] += dmg
                r["victims"].add(v)
                r["last"] = t
                continue
        for d in DOTS:
            if d["att"].search(abp) and abs(dmg - d["tick"]) >= 0.01:
                src.setdefault((v, d["name"]), []).append((t, abp))
        if not abp.startswith("unit_"):
            continue                                   # buildings' hits: no unit data to compare with
        if vbp.startswith("building_"):
            on_bld[(abp, vbp, round(dmg, 2))] += 1
            continue
        if not hp_after or hp_after <= 0:
            continue                                   # killing hit: only the HP left
        A, V = calc.at(abp, ap, t), calc.at(vbp, vp, t)
        if not A or not V or A["type"] == "siege" or A.get("splash"):
            continue
        exp = round(hit(A, V, per_projectile=True), 2)
        key = (abp, vbp, exp)
        r = pairs.setdefault(key, {"att": abp, "vic": vbp, "exp": exp, "n": 0, "obs": collections.Counter(), "dev": [],
                                   "expl": collections.Counter(), "p": ap})
        r["n"] += 1
        r["obs"][round(dmg, 2)] += 1
        if abs(dmg - exp) > DMG_TOL:
            adj, names = buff_adjust(exp, A, V, a, v, t) if BUFFS else (exp, [])
            alt = [n for n, d in alt_expected(abp, A, V, calc.done(ap, t)) if abs(dmg - d) <= DMG_TOL]
            if names and abs(dmg - adj) <= DMG_TOL:
                r["expl"][", ".join(names)] += 1          # a known aura / cast covers the difference
            elif alt:
                r["expl"][alt[0]] += 1                    # the unit's second weapon
            else:
                r["dev"].append([round(t, 2), a, v, round(dmg, 2)] + ([names] if names else []))
    rows = []
    for r in pairs.values():
        if r["n"] < MIN_N and not r["dev"] and not r["expl"]:
            continue
        rows.append({"att": r["att"], "vic": r["vic"], "exp": r["exp"], "n": r["n"],
                     "obs": sorted(r["obs"].items(), key=lambda x: -x[1]), "devN": len(r["dev"]), "dev": r["dev"][:200],
                     "explained": sorted(r["expl"].items(), key=lambda x: -x[1]), "p": r["p"]})
    rows.sort(key=lambda r: (-r["devN"], -r["n"]))
    damage_check.heals = [[k[0], k[1], k[2], n] for k, n in heals.most_common()]
    damage_check.dots = [{"source": r["source"], "att": r["att"], "ticks": r["ticks"], "dmg": round(r["dmg"], 1),
                          "victims": len(r["victims"]), "first": round(r["first"], 1), "last": round(r["last"], 1),
                          "named": r["named"].most_common()}
                         for r in dots.values()]
    return rows, [[k[0], k[1], n] for k, n in selfhits.most_common()], \
        [[k[0], k[1], k[2], n] for k, n in on_bld.most_common(40)]


def hp_check(tl, calc, hist):
    best = {}
    for fr in tl["frames"]:
        for e in fr["entities"]:
            if e["id"] is None or e["hp"] is None or not (e["bp"] or "").startswith("unit_"):
                continue
            b = best.get(e["id"])
            if b is None or e["hp"] > b[0] or e["bp"] != b[2]:
                best[e["id"]] = (e["hp"], fr["t"], e["bp"], e["owner"])
    per = {}
    for i, (hp, t, bp, p) in best.items():
        S = calc.at(bp, p, t)
        if not S:
            continue
        r = per.setdefault(bp, {"bp": bp, "n": 0, "calc": round(S["hp"], 1), "above": [], "below": 0})
        r["n"] += 1
        if hp > S["hp"] + HP_TOL:
            r["above"].append([i, round(hp, 1), round(t, 1), round(S["hp"], 1)])
        elif hp < S["hp"] - HP_TOL:
            r["below"] += 1
    rows = sorted(per.values(), key=lambda r: (-len(r["above"]), -r["below"]))
    for r in rows:
        r["aboveN"] = len(r["above"])
        r["above"] = r["above"][:50]
    return rows


def interval_check(tl, calc, hist):
    by = {}
    for h in tl.get("hits") or []:
        t, a, v, dmg = h[0], h[1], h[2], h[3]
        if a == v or dmg is None:
            continue
        by.setdefault((a, v), []).append(t)
    per = {}
    for (a, v), ts in by.items():
        ts = sorted(set(round(x, 3) for x in ts))
        if len(ts) < 2:
            continue
        abp, ap = _who(hist, a, ts[0])
        vbp, vp = _who(hist, v, ts[0])
        if not abp or not abp.startswith("unit_") or not vbp or not vbp.startswith("unit_") or vp == ap:
            continue                                   # buildings take several damage events per hit
        for t0, t1 in zip(ts, ts[1:]):
            S = calc.at(abp, ap, t0)
            if not S or S.get("splash") or S["burst"] > 1:
                continue
            d = t1 - t0
            if d <= 0.05 or d > 3 * S["period"]:
                continue                               # same volley / not continuous attacking
            r = per.setdefault(abp, {"bp": abp, "period": round(S["period"], 3), "iv": [], "fast": [], "slow": 0, "expl": {}})
            r["iv"].append(d)
            if d < INT_FAST * S["period"]:
                nb = buffed(a, t0, ("attackSpeed",))
                if nb:
                    r["expl"][", ".join(nb)] = r["expl"].get(", ".join(nb), 0) + 1   # an attack-speed buff covers it
                else:
                    r["fast"].append([round(t0, 2), a, round(d, 3)])
            elif d > INT_SLOW * S["period"]:
                r["slow"] += 1
    rows = []
    for r in per.values():
        iv = sorted(r["iv"])
        if len(iv) < MIN_N:
            continue
        rows.append({"bp": r["bp"], "period": r["period"], "n": len(iv), "median": round(iv[len(iv) // 2], 3),
                     "fastN": len(r["fast"]), "fast": r["fast"][:100], "slowN": r["slow"], "explained": sorted(r["expl"].items())})
    rows.sort(key=lambda r: -r["fastN"])
    return rows


def speed_check(tl, calc, hist):
    prev, per = {}, {}
    for fr in tl["frames"]:
        t = fr["t"]
        for e in fr["entities"]:
            i = e["id"]
            if i is None or e["x"] is None or not (e["bp"] or "").startswith("unit_"):
                continue
            p = prev.get(i)
            prev[i] = (t, e["x"], e["z"])
            if not p or "M" not in (e["flags"] or "") or not (0.5 < t - p[0] < 1.6):
                continue
            v = ((e["x"] - p[1]) ** 2 + (e["z"] - p[2]) ** 2) ** 0.5 / (t - p[0])
            S = calc.at(e["bp"], e["owner"], t)
            if not S:
                continue
            r = per.setdefault(e["bp"], {"bp": e["bp"], "walk": round(S["spd"], 2), "v": [], "fast": [], "expl": {}})
            r["v"].append(v)
            if v > SPD_FAST * S["spd"]:
                nb = buffed(i, t, ("moveSpeed",))
                if not nb and S.get("charge", 1.0) > 1.0 and S["base"] != "villager" and v <= S["spd"] * S["charge"] * 1.08:
                    nb = ["charge"]                    # melee charge speed (fightcal: knight 1.19, spearman 1.25 x walk)
                if nb:
                    r["expl"][", ".join(nb)] = r["expl"].get(", ".join(nb), 0) + 1   # a speed buff covers it
                else:
                    r["fast"].append([round(t, 1), i, round(v, 2)])
    rows = []
    for r in per.values():
        v = sorted(r["v"])
        if len(v) < 10:
            continue
        rows.append({"bp": r["bp"], "walk": r["walk"], "n": len(v), "p90": round(v[int(0.9 * (len(v) - 1))], 2),
                     "max": round(v[-1], 2), "fastN": len(r["fast"]), "fast": r["fast"][:100], "explained": sorted(r["expl"].items())})
    rows.sort(key=lambda r: -r["fastN"] / max(1, r["n"]))
    return rows


def statdiff(tl, buffs=None):
    """buffs = analyzer/auras.py output: deviations a known aura / cast covers are counted as explained"""
    BUFFS.clear()
    BUFF_FX.clear()
    if buffs:
        for i, ab, t0, t1 in buffs.get("spans") or []:
            BUFFS.setdefault(i, []).append((t0, t1, ab))
        BUFF_FX.update(buffs.get("effects") or {})
    calc, hist = Calc(tl), _index(tl)
    dmg, selfh, bld = damage_check(tl, calc, hist)
    # the viewer's "find the source" list: every unexplained damage deviation [t, attacker's player, attacker, victim,
    # observed, expected]
    find = sorted([d[0], r["p"], r["att"], r["vic"], d[3], r["exp"]] for r in dmg for d in r["dev"])[:500]
    return {"find": find, "damage": dmg, "dot": damage_check.dots, "heals": damage_check.heals, "self": selfh, "onBuildings": bld, "hp": hp_check(tl, calc, hist),
            "interval": interval_check(tl, calc, hist), "speed": speed_check(tl, calc, hist),
            "upgrades": {str(p): [[round(d, 1), a] for d, a in v] for p, v in calc.ups.items()}}


def summary(R):
    out = ["damage per hit (unit vs unit, not the killing hit): expected vs observed"]
    for r in R["damage"][:25]:
        obs = ", ".join(f"{d:g} x{n}" for d, n in r["obs"][:4])
        flag = f"  {r['devN']} off, first {_mm(r['dev'][0][0])}" if r["devN"] else ""
        if r.get("explained"):
            flag += "  explained: " + ", ".join(f"{k} x{n}" for k, n in r["explained"])
        out.append(f"  {r['att'][:30]:30} -> {r['vic'][:28]:28} exp {r['exp']:6g}  n {r['n']:4}  obs {obs}{flag}")
    if R.get("dot"):
        out.append("damage over time (ticks matched to a source hit on the same victim; the attacker the event names varies)")
        for r in R["dot"]:
            out.append(f"  {r['source']:28} {r['att'][:30]:30} ticks {r['ticks']:4}  dmg {r['dmg']:6g}  victims {r['victims']:3}"
                       f"  {_mm(r['first'])}-{_mm(r['last'])}  event names: "
                       + ", ".join(f"{b[5:]} x{n}" for b, n in r["named"]))
    if R.get("heals"):
        out.append("heals / repair (isRepairing hits) and buildings deleted by their owner - not damage: " + ", ".join(f"{b} {d:g} {w} x{n}" for b, d, w, n in R["heals"][:8]))
    if R["self"]:
        out.append("hits on itself (attacker = victim): " + ", ".join(f"{b} {d:g} x{n}" for b, d, n in R["self"][:8]))
    out.append("max HP vs calculated")
    for r in R["hp"][:12]:
        if r["aboveN"] or r["below"]:
            out.append(f"  {r['bp'][:34]:34} calc {r['calc']:6g}  units {r['n']:3}  above {r['aboveN']}"
                       + (f" (e.g. {r['above'][0][1]:g} at {_mm(r['above'][0][2])})" if r["above"] else "")
                       + f"  never full {r['below']}")
    out.append("attack interval (same attacker, same target) vs weapon period")
    for r in R["interval"][:15]:
        out.append(f"  {r['bp'][:34]:34} period {r['period']:6g}  median {r['median']:6g}  n {r['n']:4}  faster {r['fastN']}"
                   f"  slower {r['slowN']}" + ("  explained: " + ", ".join(f"{k} x{n}" for k, n in r["explained"]) if r.get("explained") else ""))
    out.append("move speed while moving vs walk speed (units / s)")
    for r in R["speed"][:15]:
        out.append(f"  {r['bp'][:34]:34} walk {r['walk']:5g}  p90 {r['p90']:5g}  max {r['max']:5g}  n {r['n']:5}  "
                   f"> {SPD_FAST:g}x walk {r['fastN']}" + ("  explained: " + ", ".join(f"{k} x{n}" for k, n in r["explained"]) if r.get("explained") else ""))
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = sys.argv[1:]
    rep_ = None
    if "--replay" in args:
        i = args.index("--replay")
        rep_ = args[i + 1]
        del args[i:i + 2]
    sys.argv[1:] = args
    aur = None
    if "--auras" in sys.argv:            # work/<name>.auras.json from analyzer/auras.py (run.py), else computed here
        i = sys.argv.index("--auras")
        aur = json.load(open(sys.argv[i + 1], encoding="utf-8"))
        del sys.argv[i:i + 2]
    tl = json.load(open(sys.argv[1], encoding="utf-8"))
    if aur is None:
        from auras import run as aura_run
        aur = aura_run(tl, rep_)
    R = statdiff(tl, aur)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(sys.argv[1].replace(".timeline", ""))[0] + ".statdiff.json"
    json.dump(R, open(out, "w", encoding="utf-8"))
    print(summary(R))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
