"""Map geometry from a v7 dump: where land units can't stand, and object footprints in tiles.

Both are first readings of game calls whose meaning is checked against one real recording:
- blocked tile: the nearest position a villager could be placed (World_GetSpawnablePosition & co.) is
  more than BLOCK_D from the tile centre, and no tree / building / resource stood on that tile at the
  start (those also push the spawn point away). Without the spawn call: the cover type name says water /
  cliff. Class: water when the cover name says so, else cliff.
- footprint: square of tiles_for(radius) tiles (see there), on the 4-unit tile grid.
"""
import math
import re

TILE = 4.0
BLOCK_D = 2.5            # spawn point moved further than this (map units) = can't stand here
OCCUPIED_R = 3.0         # an object at the start this close to the tile centre explains the move
WATER_RE = re.compile(r"water|ocean|river|lake|pond|sea", re.I)
BLOCK_NAME_RE = re.compile(r"cliff|impass|mountain|deep", re.I)
SHALLOW_RE = re.compile(r"shallow|ford", re.I)
WALL_RE = re.compile(r"palisade|_wall|wall_|gate|aqueduct", re.I)
WALL_SIDE = {"palisade": 2.0, "stone": 3.0}     # map units, square per wall piece, at its own position


def wall_side(bp):
    return WALL_SIDE["palisade"] if "palisade" in (bp or "") else WALL_SIDE["stone"]


def blocked_rows(tl):
    """['.' / 'w' / 'c' per tile, one string per row] or None (no v7 grid)."""
    P = tl.get("pass")
    if not P:
        return None
    covers = P.get("covers") or {}
    spawn = (P.get("caps") or {}).get("spawn", "none") != "none"
    occ = set()
    if spawn:
        objs = []
        snaps = tl.get("nodes") or []
        if snaps:
            objs += [(n["x"], n["z"], n.get("bp")) for n in snaps[0]["nodes"] if n["x"] is not None]
        if tl.get("frames"):
            objs += [(e["x"], e["z"], e["bp"]) for e in tl["frames"][0]["entities"] if e["x"] is not None]
        foot = footprint_tiles(tl)
        for x, z, bp in objs:
            n = foot.get(bp)
            if n:      # the object's own tiles (plus one ring: the spawn test keeps a unit's width off it)
                h = n * P["step"] / 2 + P["step"]
                for r in range(int((z - h - P["z0"]) // P["step"]), int((z + h - P["z0"]) // P["step"]) + 2):
                    for c in range(int((x - h - P["x0"]) // P["step"]), int((x + h - P["x0"]) // P["step"]) + 2):
                        if abs(P["x0"] + c * P["step"] - x) < h and abs(P["z0"] + r * P["step"] - z) < h:
                            occ.add((r, c))
                continue
            c = round((x - P["x0"]) / P["step"])
            r = round((z - P["z0"]) / P["step"])
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if math.dist((x, z), (P["x0"] + (c + dc) * P["step"], P["z0"] + (r + dr) * P["step"])) <= OCCUPIED_R:
                        occ.add((r + dr, c + dc))
    DN = P.get("dn") or []
    naval = any(v is not None for row in DN for v in row)
    out = []
    for r, row in enumerate(P["d"]):
        s = []
        for c, d in enumerate(row):
            cv = covers.get(str(int(P["cover"][r][c]))) if isinstance(P["cover"][r][c], float) else None
            name = cv or ""
            if spawn:
                bad = d is not None and d > BLOCK_D and (r, c) not in occ
            else:
                bad = bool(BLOCK_NAME_RE.search(name) or WATER_RE.search(name)) and not SHALLOW_RE.search(name)
            # dump v13: a fishing boat placeable on the tile = water (owner 2026-11-12: the game says where water is)
            dn = DN[r][c] if r < len(DN) and c < len(DN[r]) else None
            wet = WATER_RE.search(name) or (isinstance(dn, float) and dn <= BLOCK_D)
            # dump v14 (owner 2026-11-12): a tile a villager can stand on AND a fishing boat can be placed on = shallows "s"
            # (walkable: the 2D pages draw only "w" / "c"; the 3D page counts it as water)
            s.append(("w" if wet else "c") if bad else ("s" if spawn and d is not None and d <= BLOCK_D and isinstance(dn, float)
                                                           and dn <= BLOCK_D else "."))
        out.append("".join(s))
    if not naval:
        out = basins(out, tl)
    return out


BASIN_DROP = 1.0     # m: a blocked area this much below the ground around it is water, not cliff (logs before dump v13)


def basins(rows, tl):
    """older logs (no boat probe, one cover type): a connected blocked area whose median ground lies BASIN_DROP or more below
    the median of the land tiles touching it is a lake / river bed -> water; cliffs sit level with their surroundings
    (owner's otto2 / chn1 / zxl1 / otto1: blocked areas within 0.3 m of their banks)"""
    T = tl.get("terrain")
    P = tl.get("pass")
    if not T or not P or not rows:
        return rows
    H = T.get("h") or []
    def h(r, c):
        x = P["x0"] + c * P["step"]
        z = P["z0"] + r * P["step"]
        cc = int(round((x - T["x0"]) / T["step"]))
        rr = int(round((z - T["z0"]) / T["step"]))
        if 0 <= rr < len(H) and 0 <= cc < len(H[rr]) and H[rr][cc] is not None:
            return H[rr][cc]
        return None
    R, C = len(rows), len(rows[0])
    g = [list(x) for x in rows]
    seen = set()
    for r0 in range(R):
        for c0 in range(C):
            if g[r0][c0] != "c" or (r0, c0) in seen:
                continue
            st, cells = [(r0, c0)], []
            seen.add((r0, c0))
            while st:
                r, c = st.pop()
                cells.append((r, c))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    q = (r + dr, c + dc)
                    if 0 <= q[0] < R and 0 <= q[1] < C and g[q[0]][q[1]] == "c" and q not in seen:
                        seen.add(q)
                        st.append(q)
            cs = set(cells)
            inner = sorted(v for v in (h(r, c) for r, c in cells) if v is not None)
            bank = sorted(v for v in (h(r + dr, c + dc) for r, c in cells for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                                      if (r + dr, c + dc) not in cs and 0 <= r + dr < R and 0 <= c + dc < C) if v is not None)
            if len(cells) >= 4 and inner and bank and bank[len(bank) // 2] - inner[len(inner) // 2] >= BASIN_DROP:
                for r, c in cells:
                    g[r][c] = "w"
    return ["".join(x) for x in g]


def tiles_for(r):
    """Footprint side in tiles from the game's Entity_GetRadius. Calibrated on recorded positions
    (game1 / test5 / replay_252595969, 2026-10-25): houses and farms (r 2) sit 8 apart edge to edge = 2
    tiles, military buildings (r 4) 12 apart with centres on tile centres = 3 tiles, TC / landmarks /
    blacksmith / market (r 6) 12 from a 2-tile neighbour = 4 tiles; gold mines (r 6) block 4x4 tiles
    at the start. side = r / 2 + 1 tiles (berry bush r 1 -> 1 tile)."""
    return max(1, int(r / 2 + 1))


def footprint_tiles(tl):
    """{blueprint: side in tiles} from the v7 S records (radius; the collision radius came back empty)."""
    out = {}
    for bp, v in (tl.get("sizes") or {}).items():
        if WALL_RE.search(bp):        # walls aren't grid-tight (owner): drawn at their own size, unsnapped
            continue
        r = v[0] if v[0] else v[1]
        if r and r >= 1:
            out[bp] = tiles_for(r)
    return out


def grid_origin(tl):
    """x, z of a tile corner (tiles are TILE wide from there)."""
    T = tl.get("pass") or tl.get("terrain")
    if T:
        return [T["x0"] - T["step"] / 2, T["z0"] - T["step"] / 2]
    return [0.0, 0.0]
