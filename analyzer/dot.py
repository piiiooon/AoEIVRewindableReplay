"""Damage over time: which hits are poison / bleed ticks, and who really dealt them (owner 2026-11-12).

The game logs each tick as its own GE_DamageReceived, but names the victim's LATEST attacker, not the unit that applied the
effect (259818624: Mansa Javelineer poison ticks named after a Malian spearman walking away 30 units off, or a town centre).
A tick = a hit of exactly the source's tick damage, k x interval (+-DOT_TOL) after a source hit on the same victim (any
attacker named). retag() rewrites those hits with the source's attacker id and marks them, so recaps and damage shares
credit the poisoner:
    hit row [t, attacker, victim, damage, hp after, shield, repairing] -> + [source name, attacker the game named]

Sources (owner's list):
  Mansa Javelineers (Farimba Garrison, Castle): poison 3 over 6 s - 259818624: hit, then 1 at +2 / +4 / +6 s, stacking
  Poisoned Arrows (Malian archers, Castle tech): 3 over 6 s, stacks per archer
  Kipchak bleed: 2 / s for 6 s, armour-free, no stacking, reset by any Kipchak hit; Triple Shot side arrows +0.6 / s
  Zornhau (Order of the Dragon gilded landsknecht, Meinwerk Palace tech): 2 / s for 10 s
Malian spearmen (donsos) have no poison (owner).
Test batch D (owner's runs 2026-11-12, logs/fighttests/d*): mansa = 1 at exactly +2 / +4 / +6 s after each hit, a stack per
hit (3 mansa -> 3 ticks per beat); Kipchak = 2 / s on a clock of its own (first tick 0.5 s after the hit, then every 1.0 s; a
new hit keeps the clock), one stream however many Kipchaks; Triple Shot adds two 0.6 / s streams; Zornhau = 2 / s, one stream
for 2 landsknechts. So the non-stacking bleeds are matched by window (a tick of that damage within n x every + 0.6 s after the
latest source hit), the stacking poisons by exact multiples. The game names a tick after the poisoner or another recent
attacker, varying run to run (d03: all mansa in run 1, about half spearmen in runs 2 / 3).
"""
import bisect
import re

DOTS = [
    {"name": "poison (Mansa Javelineers)", "att": re.compile(r"mansa_javelin"), "tick": 1.0, "every": 2.0, "n": 3, "stacks": True},
    {"name": "poison (Poisoned Arrows)", "att": re.compile(r"unit_archer.*_mal"), "tick": 1.0, "every": 2.0, "n": 3, "stacks": True},
    {"name": "bleed (Kipchak)", "att": re.compile(r"kipchak"), "tick": 2.0, "every": 1.0, "n": 6, "stacks": False},
    {"name": "bleed (Kipchak Triple Shot)", "att": re.compile(r"kipchak"), "tick": 0.6, "every": 1.0, "n": 6, "stacks": False},
    {"name": "bleed (Zornhau)", "att": re.compile(r"landsknecht.*_hre_ha_01|gilded_landsknecht"), "tick": 2.0, "every": 1.0,
     "n": 10, "stacks": False},
]
DOT_TOL = 0.2         # s: tick timing slack (the dump logs 8 ticks / s)


def bp_index(tl):
    """id -> sorted [(t, bp, owner)] whenever the blueprint (tier) changes"""
    hist = {}
    for fr in tl["frames"]:
        for e in fr["entities"]:
            if e["id"] is None:
                continue
            h = hist.setdefault(e["id"], [])
            if not h or h[-1][1] != e["bp"]:
                h.append((fr["t"], e["bp"], e["owner"]))
    return hist


def who(hist, i, t):
    """(bp, owner) of entity i around time t"""
    h = hist.get(i)
    if not h:
        return None, None
    k = bisect.bisect_right([x[0] for x in h], t + 1.0) - 1
    x = h[max(0, k)]
    return x[1], x[2]


def tick_of(d, t, t0):
    """is a hit of d's tick damage at t a tick of the source hit at t0? (stacking poisons: exact multiples of the interval;
    non-stacking bleeds: anywhere in the window - their ticks run on a clock of their own)"""
    if not d["stacks"]:
        return 0 < t - t0 <= d["every"] * d["n"] + 0.6
    k = round((t - t0) / d["every"])
    return 1 <= k <= d["n"] and abs(t - t0 - k * d["every"]) <= DOT_TOL


def too_old(d, t, t0):
    return t - t0 > d["every"] * d["n"] + DOT_TOL + 0.6


def retag(tl, hist=None):
    """tl["hits"] with damage-over-time ticks credited to the unit that applied them (rows extended, see the docstring);
    returns (hits, number of ticks re-credited away from the named attacker)"""
    hist = hist or bp_index(tl)
    src = {}              # (victim, source name) -> [(t, attacker id)]
    out, moved = [], 0
    for h in sorted(tl.get("hits") or [], key=lambda h: h[0]):
        t, a, v, dmg = h[0], h[1], h[2], h[3]
        if dmg is None or dmg <= 0 or (len(h) > 6 and h[6] is True) or a == v:
            out.append(h)
            continue
        abp, _ = who(hist, a, t)
        tagged = None
        for d in DOTS:
            if abs(dmg - d["tick"]) >= 0.01:
                continue
            for t0, sa in reversed(src.get((v, d["name"]), [])):
                if too_old(d, t, t0):
                    break
                if tick_of(d, t, t0):
                    tagged = (d["name"], sa)
                    break
            if tagged:
                break
        if tagged:
            row = list(h) + [None] * (7 - len(h))
            row[1] = tagged[1]
            out.append(row + [tagged[0], a])
            moved += tagged[1] != a
            continue
        for d in DOTS:
            if abp and d["att"].search(abp) and abs(dmg - d["tick"]) >= 0.01:
                src.setdefault((v, d["name"]), []).append((t, a))
        out.append(h)
    return out, moved
