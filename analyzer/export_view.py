"""Convert an analyzed timeline (analyze.py output) into the compact file the viewer loads.

Usage: python export_view.py analyzed.json view.json [--step 1]
--step N keeps every Nth frame for the map (analysis curves keep full resolution).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedata import resolve, is_free  # noqa: E402
from mapgeo import blocked_rows, footprint_tiles, grid_origin  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KIND = {"w": 0, "m": 1, "o": 2, "e": 3}
ACT_CATS = ["move", "attack", "gather", "build", "queue", "cancel", "rally", "garrison", "other"]
COST_KEYS = ["food", "wood", "gold", "stone", "oliveoil", "silver"]
NODE_TYPES = ["tree", "gold", "stone", "berry", "deer", "boar", "sheep", "fish", "carcass",
              "olive", "wolf", "relic", "site", "other", "straggler", "stealth", "silver", "trade"]


def pretty(bp):
    """Readable name for a blueprint missing from the data: unit_shinobi_2_jpn -> Shinobi."""
    core = re.sub(r"^(unit|building)_", "", bp or "")
    core = re.sub(r"_(\d)(_.*)?$", "", core)
    core = re.sub(r"_(control|defense)?_?[a-z]{3}(_ha_\d+)?$", "", core)   # civ suffix
    core = re.sub(r"^(defense|econ|unit|tech)_", "", core)
    return core.replace("_", " ").strip().title() or bp


def ageups(tl):
    out = {}
    for p in tl["players"]:
        k, prev, ev = str(p["idx"]), None, []
        for fr in tl["frames"]:
            a = (fr["players"].get(k) or {}).get("age")
            if a is not None and prev is not None and a > prev:
                ev.append([fr["t"], a])
            if a is not None:
                prev = a
        out[k] = ev
    return out


def food_params():
    import food
    return {k: getattr(food, k) for k in ("TC_COVER", "TC_COVER_BONUS", "AURA_R", "AURA_V0", "ARMY_SPEED")}


def unit_age(bp, c):
    """Age tier of a unit blueprint: data 'age', else the _N_ in the name (unit_knight_3_fre)."""
    if c and c.get("age"):
        return c["age"]
    m = re.search(r"_(\d)(?:_|$)", bp or "")
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 4 else None


ORDER_NAMES = ["move", "attack", "attack-move", "gather", "build", "capture", "garrison", "unload",
               "patrol", "stop", "hold"]


def add_replay(out, tl, path):
    """Player cameras (view footprint on the ground) and unit orders from the replay file."""
    from replay import cameras, match_slots, footprint, orders, terrain_fn, acts
    import bisect
    cams = cameras(path)
    slot2p, k, ground = match_slots(cams, tl)
    th = terrain_fn(tl.get("terrain"))
    if th:          # v4 dump: terrain heights under the view instead of one fitted plane
        ground = th
    cam = {}
    for sl, tr in cams.items():
        if sl not in slot2p:
            continue
        rows = []
        for r in tr:
            fp = footprint(r, ground)
            if fp:     # [t, centre x, z, then 4 corners x, z]
                (cx, cz), cor = fp
                rows.append([r[0], round(cx, 1), round(cz, 1)] + [round(v, 1) for c in cor for v in c])
            else:      # old record without rotation: k model, 16:9 box 1.6 x height
                x, h, z = r[1], r[2], r[3]
                cx, cz, w = x + k * h, z + k * h, 0.8 * r[2]
                hh = w * 9 / 16
                rows.append([r[0], round(cx, 1), round(cz, 1), cx - w, cz - hh, cx + w, cz - hh, cx + w, cz + hh, cx - w, cz + hh])
        cam[str(slot2p[sl])] = rows
    out["camera"] = cam
    out["cameraGround"] = "terrain" if callable(ground) else ground
    # orders: [t, type, shift, from x, z (centroid of the ordered units), to x, z (or null), units]
    fts = [f["t"] for f in tl["frames"]]
    pos_cache = {}

    def frame_pos(i):
        if i not in pos_cache:
            sq, en = {}, {}
            for e in tl["frames"][i]["entities"]:
                if e["x"] is None:
                    continue
                en[e["id"]] = (e["x"], e["z"])
                if e.get("squad") is not None:
                    sq.setdefault(e["squad"], (e["x"], e["z"]))
            pos_cache.clear()
            pos_cache[i] = (sq, en)
        return pos_cache[i]
    od, missing = {}, 0
    for o in orders(path):
        p = slot2p.get(o["slot"])
        if p is None:
            continue
        i = min(bisect.bisect_left(fts, o["t"]), len(fts) - 1)
        sq, en = frame_pos(i)
        pts = [sq[s] for s in o["squads"] if s in sq] + [en[e] for e in o["entities"] if e in en]
        missing += len(o["squads"]) + len(o["entities"]) - len(pts)
        if not pts:
            continue
        fx, fz = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
        tg, to = o["target"], None
        if tg and tg[0] == "pos":
            to = (tg[1], tg[2])
        elif tg:
            to = (sq if tg[0] == "squad" else en).get(tg[1])
        od.setdefault(str(p), []).append([o["t"], ORDER_NAMES.index(o["type"]), int(o["shift"]), round(fx), round(fz),
                                          None if to is None else round(to[0]), None if to is None else round(to[1]),
                                          len(pts)])
    out["orders"] = od
    out["orderTypes"] = ORDER_NAMES
    # command receivers to highlight: [t, category, [entity ids]] per player
    ac, cats = {}, ACT_CATS
    sq_ents, sq_i = {}, -1
    for a_ in acts(path):
        p = slot2p.get(a_["slot"])
        if p is None:
            continue
        i = min(bisect.bisect_left(fts, a_["t"]), len(fts) - 1)
        if i != sq_i:
            sq_i, sq_ents = i, {}
            for e in tl["frames"][i]["entities"]:
                if e.get("squad") is not None:
                    sq_ents.setdefault(e["squad"], []).append(e["id"])
        ids = [x for s_ in a_["squads"] for x in sq_ents.get(s_, [])] + a_["entities"]
        if ids:
            ac.setdefault(str(p), []).append([a_["t"], cats.index(a_["cat"]) if a_["cat"] in cats else cats.index("other"), ids])
    out["acts"], out["actCats"] = ac, cats
    print(f"cameras: {', '.join(f'P{p} {len(v)} samples' for p, v in cam.items())}; ground {out['cameraGround']}; "
          f"orders: {', '.join(f'P{p} {len(v)} ({sum(r[2] for r in v)} shift)' for p, v in od.items())}; "
          f"{missing} ordered units not found in the dump")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("analyzed")
    ap.add_argument("out")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--synthetic", action="store_true", help="mark as synthetic test data")
    ap.add_argument("--replay", help="the game's replay file (playback folder): adds player cameras")
    a = ap.parse_args(argv)
    with open(a.analyzed) as fh:
        tl = json.load(fh)
    with open(os.path.join(HERE, "..", "data", "costs.json")) as fh:
        costs = json.load(fh)["costs"]
    with open(os.path.join(HERE, "..", "data", "sight.json")) as fh:
        sight = json.load(fh)["sight"]
    an = tl["analysis"]
    bps, bpi = [], {}

    def bp_index(bp):
        if bp not in bpi:
            bpi[bp] = len(bps)
            bps.append(bp)
        return bpi[bp]

    frames, ft = [], []
    for i, fr in enumerate(tl["frames"]):
        if i % a.step:
            continue
        ft.append(fr["t"])
        frames.append([[e["owner"], e["id"], bp_index(e["bp"]),
                        None if e["x"] is None else round(e["x"]),
                        None if e["z"] is None else round(e["z"]),
                        e["vis"], KIND.get(e["kind"], 2),
                        # gather: 0 none, 1 food, 2 wood, 3 gold, 4 stone; +8 walking; +16 garrisoned
                        (e.get("res") or 0) + (8 if e.get("res_moving") else 0)
                        + (16 if e.get("garrisoned") else 0)]
                       for e in fr["entities"]])
    # Castle timing per observer (castle.py): projected / reference arrival, off-path items seen
    # (before bpinfo: implied buildings may add blueprints)
    castle_out = {k: {"proj": [r["proj"] for r in v["rows"]], "ref": [r["ref"] for r in v["rows"]],
                   "off": [r["off"] for r in v["rows"]], "reached": v["reached"], "build": v["build"],
                   "items": [[round(i["t"], 1), bp_index(i["bp"]), i["n"], i["cost"], i["sec"], i.get("implied") or ""]
                             for i in v["items"]]}
               for k, v in an.get("castle", {}).items()}
    foot = footprint_tiles(tl)
    bpinfo = []
    for bp in bps:
        c = None if is_free(bp) else costs.get(resolve(bp, costs))
        bpinfo.append({"name": c["name"] if c else pretty(bp),
                       "cost": sum(c.get(k) or 0 for k in COST_KEYS) if c else None,
                       "sight": sight.get(bp) or sight.get(resolve(bp, sight) or ""),
                       "age": unit_age(bp, c),
                       "wall": bool(re.search(r"palisade|_wall|wall_", bp or "")),
                       "tiles": foot.get(bp)})
    out = {
        "format": "a4d-view/1",
        "synthetic": a.synthetic,
        "players": tl["players"],
        "caps": tl["caps"],
        "params": an["params"],
        "warnings": an["warnings"],
        "t": [r["t"] for r in next(iter(an["truth"].values()))],
        "truth": {p: {k: [r[k] for r in rows] for k in ("bank", "spent", "villagers", "gold")}
                  for p, rows in an["truth"].items()},
        "estimate": {key: {k: [None if r.get(k) is None else round(r[k], 1) for r in rows]
                           for k in ("bank_est", "n_est", "n_seen", "spent_seen",
                                     "bank_est_k", "n_est_k", "kills", "gold_est",
                                     "gold_vil_now", "gold_vil", "gold_est_tech", "tech_gold")}
                     for key, rows in an["estimate"].items()},
        "events": an["events"],
        "castle": castle_out,
        # review only (full information): villager economy per player (econ.py)
        "econ": an.get("econ", {}),
        # review only: what each player researched (the game's upgrade events), paid at start
        "techs": an.get("techs", {}),
        "counter": an.get("counter", {}),
        # opponent's safe natural food, per observer (food.py): rows every 5 s
        "food": {k: v["rows"] for k, v in an.get("food", {}).items()},
        "foodParams": food_params(),
        # age-up completions (announced to every player): {player: [[t, new age], ...]}
        "ageups": ageups(tl),
        "fights": [dict(f, deaths=[dict(d, name=(costs.get(resolve(d["bp"], costs)) or {}).get("name") or pretty(d["bp"]),
                                         known=is_free(d["bp"]) or resolve(d["bp"], costs) is not None) for d in f["deaths"]])
                   for f in an.get("fights", [])],
        "bps": bps, "bpinfo": bpinfo,
        "nodeTypes": NODE_TYPES,
        "explored": an.get("explored", {}),
        "nodes": [{"t": snap["t"], "full": snap["full"],
                   "n": [[NODE_TYPES.index(n["type"]), round(n["x"], 1), round(n["z"], 1), n["id"]]
                         + ([foot[n["bp"]]] if n.get("bp") in foot else [])
                         for n in snap["nodes"] if n["x"] is not None]}
                  for snap in tl.get("nodes") or []],
        "ft": ft, "frames": frames,
        # v7 map geometry: tiles land units can't stand on ('.' / 'w' water / 'c' cliff), tile grid origin
        "blocked": blocked_rows(tl), "tile0": grid_origin(tl),
    }
    if a.replay:
        add_replay(out, tl, a.replay)
    with open(a.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(frames)} map frames, {len(bps)} blueprints -> {a.out} "
          f"({os.path.getsize(a.out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
