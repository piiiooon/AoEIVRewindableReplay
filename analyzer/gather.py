"""Label what each villager is gathering, from position only (no hidden game state).

A villager that moved less than STILL map units since the previous sample and stands within
reach of a resource source gets that source's resource. Sources: resource nodes from the
dump (trees, gold, stone, berries, carcasses, deer, boar), player farms, player sheep.
A walking villager keeps its last label for KEEP seconds (trip to the drop-off).
When the dump has the game's own gather flags (F/W/G/S) those are used instead, and
e['res_pos'] keeps the position-based guess for comparison. H = garrisoned.
Reach distances are first guesses (4 map units per tile), to be checked against data.
"""
import math

FOOD, WOOD, GOLD, STONE = 1, 2, 3, 4
RES_NAME = {0: "none", FOOD: "food", WOOD: "wood", GOLD: "gold", STONE: "stone"}
NODE_RES = {"tree": (WOOD, 7.0), "straggler": (WOOD, 7.0), "stealth": (WOOD, 7.0), "gold": (GOLD, 12.0), "stone": (STONE, 12.0),
            "berry": (FOOD, 6.0), "carcass": (FOOD, 6.0), "deer": (FOOD, 6.0),
            "boar": (FOOD, 7.0), "sheep": (FOOD, 5.0), "olive": (FOOD, 6.0)}
TREES = ("tree", "straggler", "stealth")
FARM_R, SHEEP_R = 9.0, 5.0
STILL, KEEP, CELL = 1.5, 30.0, 16.0


def _grid(points):
    g = {}
    for x, z, res, r in points:
        g.setdefault((int(x // CELL), int(z // CELL)), []).append((x, z, res, r))
    return g


def _nearest(g, x, z):
    best, bd = 0, 1e9
    cx, cz = int(x // CELL), int(z // CELL)
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for nx, nz, res, r in g.get((cx + dx, cz + dz), ()):
                d = math.hypot(x - nx, z - nz) / r
                if d <= 1.0 and d < bd:
                    best, bd = res, d
    return best


def label_villagers(tl):
    """Adds e['res'] (0..4) to every villager entity, e['res_moving'] when inherited."""
    frames, snaps = tl["frames"], tl.get("nodes") or []
    si, sfull = -1, -1
    prev_pos, last, last_true = {}, {}, {}
    for fr in frames:
        t = fr["t"]
        while si + 1 < len(snaps) and snaps[si + 1]["t"] <= t:
            si += 1
            if snaps[si]["full"]:
                sfull = si
        pts = []
        if sfull >= 0:
            pts += [(n["x"], n["z"], *NODE_RES["tree"]) for n in snaps[sfull]["nodes"]
                    if n["type"] in TREES and n["x"] is not None]
        if si >= 0:
            pts += [(n["x"], n["z"], *NODE_RES[n["type"]]) for n in snaps[si]["nodes"]
                    if n["type"] in NODE_RES and n["type"] not in TREES and n["x"] is not None]
        pts += [(e["x"], e["z"], FOOD, FARM_R) for e in fr["entities"]
                if (e["bp"] or "").startswith("building_resource_farm") and e["x"] is not None]
        pts += [(x, z, FOOD, SHEEP_R) for x, z in fr.get("sheep", [])]
        g = _grid(pts)
        for e in fr["entities"]:
            if e["kind"] != "w" or e["x"] is None:
                continue
            i = e["id"]
            res, moving = 0, False
            still = i in prev_pos and math.hypot(e["x"] - prev_pos[i][0], e["z"] - prev_pos[i][1]) < STILL
            if still and e.get("idle") is not True:
                res = _nearest(g, e["x"], e["z"])
            if res:
                last[i] = (res, t)
            elif e.get("idle") is not True and i in last and t - last[i][1] <= KEEP:
                res, moving = last[i][0], True
            e["res_pos"] = res
            fl = e.get("flags")
            if fl is not None:
                true_res = next((r for ch, r in (("F", FOOD), ("W", WOOD), ("G", GOLD), ("S", STONE))
                                 if ch in fl), 0)
                if true_res:
                    res, moving = true_res, False
                    last_true[i] = (true_res, t)
                elif "H" not in fl and e.get("idle") is not True and i in last_true \
                        and t - last_true[i][1] <= KEEP:
                    res, moving = last_true[i][0], True     # walking to drop-off / switching target
                else:
                    res, moving = 0, False
            e["res"], e["res_moving"] = res, moving
            e["garrisoned"] = bool(fl and "H" in fl)
            prev_pos[i] = (e["x"], e["z"])
    return tl
