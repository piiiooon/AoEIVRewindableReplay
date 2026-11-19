"""Fight review page data (full information) -> compact JSON for viewer/fights.html.

Usage: python export_fights.py analyzed.json fights.json

The whole game, not only fights:
- units: [id, owner, bp index, class, cost] for every player entity of the game
- timeline: one full row per dump second, [t, 0, rows], and between seconds the v6 fight samples as
  partial rows [t, 1, rows] that update only the units they list (x null = gone). A row entry is
  [unit index, x, z, HP fraction, target unit index or -1, target-choice score or -1]
  (scores exist inside fights, from fightlab.py; other attacks have -1)
- fights: bookmarks with fightlab.py's measures and the area to frame
- deaths [t, owner, x, z, bp index], map objects (full snapshots), terrain heights, map bounds
"""
import argparse
import re
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fightlab import fight_reviews, nato_class  # noqa: E402
from fights import find_deaths  # noqa: E402
from techs_bought import techs_bought  # noqa: E402
from counter import load_units  # noqa: E402
from gamedata import resolve  # noqa: E402
from analyze import load_costs  # noqa: E402
from export_view import pretty  # noqa: E402
from mapgeo import blocked_rows, footprint_tiles, grid_origin  # noqa: E402

MAP_PAD = 25.0
ECO_RE = re.compile(r"econ|villager|wheelbarrow|gather|farm|lumber|mining|forestry|horticulture|fertil|"
                    r"precision|survival|crosscut|acid|cupellation|textile|ration|drift_net|extended_lines|"
                    r"trade|market|tax|double_broadaxe|wheelbarrow|specialized_pick|professional_scouts", re.I)


def techs_list(tl):
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        return {}
    # [4] = real start (dump v19 UpgradeStart event or v18 queue head), [5] = how ("event" / "queue" / "estimated"),
    # [6] = the replay's click (tl["queueCmds"]) or None
    return {str(p): [[x["done"], x["attrib"], x["name"], 0 if ECO_RE.search(x["attrib"]) else 1,
                      x["t"] if x.get("exact") else None, x.get("how") or "estimated", x.get("click")] for x in v]
            for p, v in bought.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("analyzed")
    ap.add_argument("out")
    a = ap.parse_args(argv)
    with open(a.analyzed) as fh:
        tl = json.load(fh)
    cost, costs_full = load_costs()
    cost_of = lambda bp: cost.get(resolve(bp, cost) or "", 0.0) if bp else 0.0  # noqa: E731
    fights_in = tl["analysis"].get("fights", [])
    reviews = fight_reviews(tl, fights_in, cost_of)
    U = load_units()
    bps, bpi = [], {}

    def bix(bp):
        if bp not in bpi:
            bpi[bp] = len(bps)
            bps.append(bp)
        return bpi[bp]

    # target-choice scores from the fight reviews, by (time, attacker)
    score = {}
    for r in reviews:
        for (t, _), lines in zip(r["samples"], r["lines"]):
            for att, _, s in lines:
                if s is not None:
                    score[(round(t, 2), att)] = s

    # unit table over the whole game
    units, uix, hpmax = [], {}, {}
    frames, fast = tl["frames"], tl.get("fast") or []
    for fr in frames:
        for e in fr["entities"]:
            if e["id"] is None:
                continue
            if e["id"] not in uix:
                k = resolve(e["bp"], U) if e["bp"] else None
                st = U.get(k) if k else None
                cls = "building" if e["kind"] == "o" else nato_class(e["bp"], st)
                uix[e["id"]] = len(units)
                units.append([e["id"], e["owner"], bix(e["bp"]), cls, round(cost_of(e["bp"]))])
                hpmax[e["id"]] = (st.get("hp") or 0.0) if st else 0.0
            if e.get("hp"):
                hpmax[e["id"]] = max(hpmax[e["id"]], e["hp"])

    # HP fraction (owner 2026-11-13: "why do TIGER's spearmen / villagers spawn hurt?"): the dump records current HP only. Units
    # divide by the highest HP seen SO FAR (running max, rows are built in time order), not over their whole life - an upgrade
    # (Textiles, Lancaster HP auras ...) that raised the maximum later made them look hurt from birth (80 / 110). Buildings keep
    # the lifetime maximum (their height grows with the construction HP).
    run = {}
    bld = {u[0] for u in units if u[3] == "building"}

    def row(i, x, z, hp, tg, t):
        s = score.get((round(t, 2), i))
        if i in bld:
            den = hpmax.get(i)
        else:
            den = run[i] = max(run.get(i, 0.0), hp or 0.0)
        return [uix[i], round(x, 1), round(z, 1),
                round(min(1.0, hp / den), 2) if den else 1.0,
                uix.get(tg, -1) if tg is not None else -1, -1 if s is None else s]

    timeline, si = [], 0
    fast = sorted(fast, key=lambda s: s["t"])
    for n, fr in enumerate(frames):
        t = fr["t"]
        timeline.append([round(t, 2), 0, [row(e["id"], e["x"], e["z"], e.get("hp") or 0.0, e.get("target"), t)
                                          for e in fr["entities"] if e["id"] in uix and e["x"] is not None]])
        nxt = frames[n + 1]["t"] if n + 1 < len(frames) else t + 1
        while si < len(fast) and fast[si]["t"] < nxt:
            s = fast[si]
            si += 1
            if s["t"] <= t:
                continue
            rows = []
            for k, v in s["u"].items():
                k = int(k)
                if k not in uix:
                    continue
                if v[0] is None:
                    rows.append([uix[k], None, None, 0, -1, -1])
                else:
                    rows.append(row(k, v[0], v[1], v[2] or 0.0, v[3], s["t"]))
            timeline.append([round(s["t"], 2), 1, rows])

    # fight bookmarks: measures and the area to frame
    fights = []
    for r in reviews:
        fd = next((f["deaths"] for f in fights_in if f["n"] == r["n"]), [])
        xs = [d["x"] for d in fd] + [r["x"] - r["r"], r["x"] + r["r"]]
        zs = [d["z"] for d in fd] + [r["z"] - r["r"], r["z"] + r["r"]]
        dmg = {k: dict(v, by=[[n, d, bix(bp) if bp else -1] for n, d, bp in v["by"]]) for k, v in r["damage"].items()}
        fights.append({**{k: r[k] for k in ("n", "start", "end", "x", "z", "r", "data", "lost", "unitsLost", "odds",
                                             "target", "focus", "overkill")},
                       "damage": dmg,
                       "army": {k: [[bix(bp), n] for bp, n in v] for k, v in r["army"].items()},
                       "lostBy": {k: [[bix(bp), n] for bp, n in v] for k, v in r["lostBy"].items()},
                       "bbox": [round(min(xs) - MAP_PAD), round(min(zs) - MAP_PAD),
                                round(max(xs) + MAP_PAD), round(max(zs) + MAP_PAD)],
                       "deaths": len(fd)})
    deaths = [[d["t"], d["owner"], round(d["x"]), round(d["z"]), bix(d["bp"])] for d in find_deaths(frames, cost_of, tl.get("events"))]
    foot = footprint_tiles(tl)
    nodes = [{"t": s["t"], "n": [[n["type"], round(n["x"], 1), round(n["z"], 1)] + ([foot[n["bp"]]] if n.get("bp") in foot else [])
                                 for n in s["nodes"] if n["x"] is not None]}
             for s in (tl.get("nodes") or []) if s["full"]]
    T = tl.get("terrain")
    terrain = None
    if T and T.get("h"):
        terrain = {"x0": T["x0"], "z0": T["z0"], "step": T["step"],
                   "h": [[None if v is None else round(v, 1) for v in (r_ or [])] for r_ in T["h"]]}
    xs = [e["x"] for fr in frames for e in fr["entities"] if e["x"] is not None]
    zs = [e["z"] for fr in frames for e in fr["entities"] if e["x"] is not None]
    names = []
    for bp in bps:
        c = costs_full.get(resolve(bp, costs_full) or "")
        names.append(c["name"] if c else pretty(bp))
    out = {"format": "a4d-fights/2", "players": tl["players"], "bps": bps, "names": names,
           "units": units, "timeline": timeline, "fights": fights, "deaths": deaths, "nodes": nodes,
           "terrain": terrain, "bounds": [min(xs), min(zs), max(xs), max(zs)] if xs else [0, 0, 1, 1],
           "fast": bool(fast), "tiles": [foot.get(bp) for bp in bps],
           # what each player researched (game's upgrade events): [done, attrib, name, military]
           "techs": techs_list(tl),
           "blocked": blocked_rows(tl), "tile0": grid_origin(tl)}
    with open(a.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(fights)} fights, {len(timeline)} timeline rows -> {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
