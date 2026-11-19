"""3D replay page (owner 2026-11-10: "our own viewer", a third page next to the viewer and the fights page; full
information, review only, like the fights page).

    python viewer/build_3d.py work/<name>.fights.json views/<name>.3d.html [--models models]

Data: the fights page's JSON (units, timeline with the 4/s fight samples, terrain heights, map objects, deaths,
fights). Models: the Gen7 parts exported on this PC (tools/game_assets.py export-parts -> models/parts/<name>.<i>.glb)
assembled per unit type with models/unit_models.json (tools/unit_models.py). The parts are read here and embedded
into the page (only the unit types of this game, each once); without them a unit is a plain shape. Game art stays on
this PC: the page is built here and never shipped.

Owner's choices: flat colours in the player colours, Gen7 models only for units, instanced drawing (one draw call per
part per unit type). Owner 2026-11-10 (after the first look): attack / charge / brace motions required, units easier to
tell apart, buildings from the game's models, pan. So: per unit type three instanced parts - body (player colour: soldier
/ rider + shield), mount (neutral horse / camel / elephant colour), weapon (steel) - posed per frame in the page
(procedural rigid motions: the exports have no skeleton); player-coloured ground rings; unit size 1-3x; buildings from
DX12Geo<civ> (tools/unit_models.py buildings) at their true size, else boxes.
Assembly (read off the exported meshes; parts_info.json): y up, metres = map units, forward +z; weapons / shields have
the grip at the origin, blade up. A rider comes out standing on the ground: the horse / camel mesh (the one longer than
2 along z) stays, the others are lifted so the rider's hips (half its height) sit on the horse's back (its top over the
middle third). Weapon in the right hand (-x: the body faces +z), shield in the left; the hand = mean of the vertices
within 8 cm of the body's outermost x on that side. Horse direction: the end of the body with the higher top is the
head; a head at -z is turned round.
Heading in the page: the movement direction (> 0.3 units/s), else towards the target, else kept.
"""
import argparse
import base64
import bisect
import hashlib
import json
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# weapon tilt forward (about x, degrees) by weapon name
TILT = (("spear", 25), ("pike", 25), ("lance", 70), ("sword", 35), ("axe", 35), ("mace", 35), ("hammer", 35),
        ("bow", 0), ("cannon_hand", 80), ("torch", 20), ("staff", 10))


IMAGES = {}            # texture key -> [mime, base64] (detail medium / heavy)


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(nd):
    """glTF node -> 4x4 (row-major) from matrix (column-major in the file) or translation / rotation / scale"""
    if "matrix" in nd:
        m = nd["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = nd.get("translation", [0, 0, 0])
    qx, qy, qz, qw = nd.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = nd.get("scale", [1, 1, 1])
    r = [[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
         [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
         [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx], [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz], [0, 0, 0, 1]]


IDENT = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def read_glb(path, textured=False, first_only=False):
    """a SharpGLTF export -> list of mesh dicts {p, n, i, uv, tex}: every primitive of every mesh, placed by its node's
    transform. (owner 2026-11-11: the twin-minaret / Jiangnan Tower landmarks and the Zhu Xi village came out as a few
    scattered shards - only the first primitive of the first mesh was read, untransformed.) With textured the base colour
    image of each primitive's material is kept (IMAGES) and the UVs read."""
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bn = struct.unpack("<I", b[off:off + 4])[0]
    binc = b[off + 8:off + 8 + bn]
    acc = j["accessors"]

    def view(ai):
        a = acc[ai]
        bv = j["bufferViews"][a["bufferView"]]
        return a, bv, bv.get("byteOffset", 0) + a.get("byteOffset", 0)

    def vecs(ai, k):
        a, bv, o = view(ai)
        stride = bv.get("byteStride", 4 * k)
        return [struct.unpack_from(f"<{k}f", binc, o + i * stride) for i in range(a["count"])]

    def prim_mesh(prim, M):
        if "POSITION" not in prim.get("attributes", {}) or prim.get("mode", 4) != 4:
            return None
        pos = vecs(prim["attributes"]["POSITION"], 3)
        nor = vecs(prim["attributes"]["NORMAL"], 3) if "NORMAL" in prim["attributes"] else [(0.0, 1.0, 0.0)] * len(pos)
        if "indices" in prim:
            a, bv, o = view(prim["indices"])
            fmt = {5123: "H", 5125: "I", 5121: "B"}[a["componentType"]]
            idx = list(struct.unpack_from(f"<{a['count']}{fmt}", binc, o))
        else:
            idx = list(range(len(pos)))
        if M is not IDENT:
            pos = [tuple(M[r][0] * x + M[r][1] * y + M[r][2] * z + M[r][3] for r in range(3)) for x, y, z in pos]
            out = []
            for x, y, z in nor:
                v = [M[r][0] * x + M[r][1] * y + M[r][2] * z for r in range(3)]
                L = math.sqrt(sum(c * c for c in v)) or 1.0
                out.append(tuple(c / L for c in v))
            nor = out
        uv, tex = None, None
        if textured and "TEXCOORD_0" in prim["attributes"]:
            try:
                mat = j["materials"][prim.get("material", 0)]
                ti = mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]
                img = j["images"][j["textures"][ti]["source"]]
                ibv = j["bufferViews"][img["bufferView"]]
                data = binc[ibv.get("byteOffset", 0):ibv.get("byteOffset", 0) + ibv["byteLength"]]
                mime = img.get("mimeType", "image/png")
                if mime in ("image/png", "image/jpeg", "image/webp"):
                    key = hashlib.sha1(data).hexdigest()[:16]
                    IMAGES.setdefault(key, [mime, base64.b64encode(data).decode()])
                    tex = key
                    uv = vecs(prim["attributes"]["TEXCOORD_0"], 2)
            except (KeyError, IndexError, TypeError):
                pass
        return {"p": pos, "n": nor, "i": idx, "uv": uv, "tex": tex}

    if first_only:                     # the old reading (map objects; owner 2026-11-11): first primitive, untransformed
        try:
            m = prim_mesh(j["meshes"][0]["primitives"][0], IDENT)
        except (KeyError, IndexError):
            return []
        return [m] if m else []
    out, seen = [], set()

    def walk(ni, parent):
        nd = j["nodes"][ni]
        M = _mat_mul(parent, _node_matrix(nd)) if any(k in nd for k in ("matrix", "translation", "rotation", "scale")) else parent
        if "mesh" in nd:
            seen.add(nd["mesh"])
            for prim in j["meshes"][nd["mesh"]]["primitives"]:
                m = prim_mesh(prim, M)
                if m:
                    out.append(m)
        for c in nd.get("children", []):
            walk(c, M)

    scenes = j.get("scenes") or []
    roots = scenes[j.get("scene", 0)]["nodes"] if scenes else []
    for r in roots:
        walk(r, IDENT)
    for mi, mesh in enumerate(j.get("meshes", [])):      # meshes no node points at: untransformed
        if mi not in seen:
            for prim in mesh["primitives"]:
                m = prim_mesh(prim, IDENT)
                if m:
                    out.append(m)
    return out


DETAIL = "light"


def load_part(pdir, name):
    """the part's meshes. light (Gen7): every file is one mesh. medium / heavy (DX12 export): the files are several
    meshes x detail levels; files whose boxes match (to 5 cm) are levels of one mesh - heavy keeps the one with the
    most triangles, medium the fewest"""
    files = sorted(f for f in os.listdir(pdir) if f.lower().startswith(name.lower() + ".") and f.endswith(".glb"))
    # map objects (SIMPLE) are read with their node transforms too (owner 2026-11-12: veins still broken - the DX12 deposit
    # files carry a node rotation / offset; read untransformed the rocks lay on their sides as flat shards)
    fl = [[m for m in read_glb(os.path.join(pdir, f), DETAIL != "light") if m["p"]] for f in files]
    fl = [x for x in fl if x]
    if len(fl) < 2:
        return [m for x in fl for m in x]
    # light too (owner 2026-11-11: Viking landmarks misrendered, page 39 MB): building parts come from DX12Geo, whose
    # export holds every detail level - stacked, they flickered and tripled the size. Levels of one mesh share a box
    # (to 25 cm); Gen7 meshes of one part (horse / rider) have different boxes and stay. A file can hold several
    # primitives (one per material): its box / triangle count is over all of them.
    groups = {}
    for x in fl:
        (a, b2, c), (d, e, f) = bbox([p for m in x for p in m["p"]])
        groups.setdefault(tuple(round(v * 4) for v in (a, b2, c, d, e, f)), []).append(x)
    tri = lambda x: sum(len(m["i"]) for m in x) // 3
    if SIMPLE:                          # map objects (owner 2026-11-11: "a simpler level for the environment and the
        return simple_pick(fl, tri)     # buildings get the better treatment")
    if LEVELS == "all":                 # owner 2026-11-11: "what if we make all the building parts render?" - every file
        return [m for x in fl for m in x]
    if DETAIL == "heavy":
        return [m for g in groups.values() for m in max(g, key=tri)]
    # owner 2026-11-11: landmarks rendered properly before this grouping took the fewest triangles - for buildings the
    # lowest level is a crude stand-in (or the shards); light / medium now take the most detailed level up to
    # LEVEL_TRI_MAX triangles (the page size stays bounded), else the smallest
    out = []
    for g in groups.values():
        ok = [x for x in g if tri(x) <= LEVEL_TRI_MAX]
        out += max(ok, key=tri) if ok else min(g, key=tri)
    return out


def simple_pick(fl, tri):
    """map objects (owner's probe 2026-11-11, gold / stone deposits): a mine exports as several pieces (central rock, side
    rocks, base), each in 2-3 files over the same ground footprint whose tops get lower (stone_sml_deposit.1 / .7 / .8: top
    2.9 / 2.4 / 1.4) - the deposit's depletion stages, not detail levels; stacked they showed as shards poking out of the
    ground. Files are grouped by ground-footprint overlap (x / z box IoU >= 0.5); per group the tallest (= the full deposit),
    ties within 0.2 by fewest triangles."""
    info = []
    for x in fl:
        (a, b, c), (d, e, f) = bbox([p for m in x for p in m["p"]])
        info.append((x, a, c, d, f, e))
    groups = []
    for it in info:
        for g in groups:
            _, a, c, d, f, _ = g[0]
            ix = max(0.0, min(d, it[3]) - max(a, it[1]))
            iz = max(0.0, min(f, it[4]) - max(c, it[2]))
            inter = ix * iz
            union = (d - a) * (f - c) + (it[3] - it[1]) * (it[4] - it[2]) - inter
            if union > 0 and inter / union >= 0.5:
                g.append(it)
                break
        else:
            groups.append([it])
    out = []
    for g in groups:
        top = max(it[5] for it in g)
        best = min((it for it in g if it[5] >= top - 0.2), key=lambda it: tri(it[0]))
        out += best[0]
    return out


LEVEL_TRI_MAX = 12000
MINE_SHAPES = False                     # --mine-shapes: gold / stone deposits as rock clusters (default: the game's models)
SIMPLE = False                          # set while the map objects' models load: old reading + simplest level
LEVELS = "best"                         # --levels all: every exported file of a part (detail levels stacked)


def probe(pdir, name):
    """owner's check: every exported file of a part - meshes, triangles, box, detail-level group, which one is used"""
    files = sorted(f for f in os.listdir(pdir) if f.lower().startswith(name.lower() + ".") and f.endswith(".glb"))
    for f in files:
        ms = read_glb(os.path.join(pdir, f))
        pts = [p for m in ms for p in m["p"]]
        if not pts:
            print(f"  {f}: empty")
            continue
        (a, b2, c), (d, e, f2) = bbox(pts)
        raw = [p for m in read_glb(os.path.join(pdir, f), first_only=True) for p in m["p"]]
        (ra, rb, rc), (rd, re_, rf) = bbox(raw) if raw else ((0, 0, 0), (0, 0, 0))
        try:                                       # node transforms in the file (owner 2026-11-12: veins broken)
            b_ = open(os.path.join(pdir, f), "rb").read()
            nds = json.loads(b_[20:20 + struct.unpack("<I", b_[12:16])[0]]).get("nodes", [])
            xfs = [{k: nd[k] for k in ("matrix", "translation", "rotation", "scale") if k in nd} for nd in nds]
            xft = "; ".join(json.dumps(x) for x in xfs if x) or "none"
        except (OSError, ValueError, struct.error):
            xft = "?"
        print(f"  {f}: {len(ms)} meshes, {sum(len(m['i']) for m in ms) // 3} triangles, box x {a:.1f}..{d:.1f} "
              f"y {b2:.1f}..{e:.1f} z {c:.1f}..{f2:.1f} | untransformed y {rb:.1f}..{re_:.1f} | node transforms: {xft[:160]}")
    used = load_part(pdir, name)
    print(f"  used ({DETAIL}): {len(used)} meshes, {sum(len(m['i']) for m in used) // 3} triangles")
    global SIMPLE
    SIMPLE = True
    used = load_part(pdir, name)
    SIMPLE = False
    print(f"  used as a map object: {len(used)} meshes, {sum(len(m['i']) for m in used) // 3} triangles")


def bbox(pos):
    xs, ys, zs = zip(*pos)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def allpos(meshes):
    return [v for m in meshes for v in m["p"]]


def xform(mesh, rot_y=0.0, tilt=0.0, t=(0.0, 0.0, 0.0)):
    """rotate about x (tilt, degrees: top forward to +z), then about y (degrees), then translate"""
    ca, sa = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
    cb, sb = math.cos(math.radians(rot_y)), math.sin(math.radians(rot_y))

    def r(v, move):
        x, y, z = v
        y, z = y * ca - z * sa, y * sa + z * ca
        x, z = x * cb + z * sb, -x * sb + z * cb
        return (x + t[0], y + t[1], z + t[2]) if move else (x, y, z)
    return dict(mesh, p=[r(v, True) for v in mesh["p"]], n=[r(v, False) for v in mesh["n"]])


def xform_q(mesh, xf):
    """a stamp placement (game_assets.py stamps): scale, quaternion x y z w, then position"""
    qx, qy, qz, qw, px, py, pz, sx, sy, sz = xf
    # the placement is in game (left-handed) space, the meshes in glTF space: reflect it in x (owner 2026-11-12, mirroring)
    if MIRROR_MODELS:
        qy, qz, px = -qy, -qz, -px

    def rot(v):
        x, y, z = v
        tx, ty, tz = 2 * (qy * z - qz * y), 2 * (qz * x - qx * z), 2 * (qx * y - qy * x)
        return (x + qw * tx + (qy * tz - qz * ty), y + qw * ty + (qz * tx - qx * tz), z + qw * tz + (qx * ty - qy * tx))
    P = [rot((x * sx, y * sy, z * sz)) for x, y, z in mesh["p"]]
    return dict(mesh, p=[(x + px, y + py, z + pz) for x, y, z in P], n=[rot(v) for v in mesh["n"]])


def merge(meshes):
    """-> list of meshes, one per texture (all untextured ones merged into one); a new one is started before 65,536
    vertices so the page's indices stay uint16 (owner 2026-11-13: page size)"""
    by, out = {}, []
    for m in meshes:
        M = by.get(m["tex"])
        if M is None or (M["p"] and len(M["p"]) + len(m["p"]) > 65535):
            M = by[m["tex"]] = {"p": [], "n": [], "i": [], "uv": [] if m["tex"] else None, "tex": m["tex"]}
            out.append(M)
        base = len(M["p"])
        M["p"] += m["p"]
        M["n"] += m["n"]
        M["i"] += [base + i for i in m["i"]]
        if m["tex"]:
            M["uv"] += m["uv"]
    return out


CHARGERS = set()   # bp indices with a charge attack (main() fills it)
RIGHT = 1   # side of the right hand: game space (left-handed, facing +z) +x; -1 with --mirror-models (glTF space)


def hand(pos, side):
    """mean of the vertices within 8 cm of the outermost x on that side (-1 = -x, +1 = +x)"""
    ext = min(p[0] for p in pos) if side < 0 else max(p[0] for p in pos)
    pts = [p for p in pos if abs(p[0] - ext) < 0.08]
    return tuple(sum(c) / len(pts) for c in zip(*pts))


def crew_of(bps, UM):
    """owner 2026-11-13: Delhi / Tughlaq elephants are one unit with several weapons - the crew (spearman / rider, archers,
    handcannoneers, crossbows, springald crew, monks) are their own entities in the elephant's squad (the fight tests saw the
    rider hit as a second entity). Crew blueprints = war elephant blueprints whose model has no elephant: {bp index: 0 rider
    (the elephant model already has one: hidden while on an elephant) / 1 deck crew (stands on the elephant's back)}"""
    out = {}
    for bi, bp in enumerate(bps):
        if not re.search(r"war_elephant", bp) or "worker" in bp:
            continue
        body = ((UM.get(bp) or {}).get("body") or "").lower()
        if "elephant" in body:
            continue
        out[str(bi)] = 0 if re.search(r"spearman|cavalry_rider", bp + " " + body) and "tower" not in bp else 1
    return out


def components(m):
    """a mesh split into its connected pieces (vertices welded by position to 0.1 mm); one piece -> [m]"""
    P, I = m["p"], m["i"]
    weld, w = {}, []
    for p in P:
        w.append(weld.setdefault(tuple(round(c, 4) for c in p), len(weld)))
    par = list(range(len(weld)))

    def root(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a in range(0, len(I) - 2, 3):
        r0 = root(w[I[a]])
        for v in I[a + 1:a + 3]:
            par[root(w[v])] = r0
    by = {}
    for a in range(0, len(I) - 2, 3):
        by.setdefault(root(w[I[a]]), []).extend(I[a:a + 3])
    if len(by) < 2:
        return [m]
    return [dict(m, i=ix) for ix in by.values()]


def barding(mounts):
    """owner 2026-11-12 (knights need better visuals, "add some of the armor plating to the knights' horses"): plates made from
    the horse's own torso - triangles whose centre sits between 42 % and 80 % of the mount's height and away from the head /
    neck end (front 26 %) and the tail (back 14 %), pushed out 6 cm along their normals; flat colour (the page tints it steel).
    The mount is already turned head to +z here."""
    pts = [p for m in mounts for p in m["p"]]
    if not pts:
        return []
    (_, y0, z0), (_, y1, z1) = bbox(pts)
    h, L = max(0.5, y1 - y0), max(0.5, z1 - z0)
    out = []
    for m in mounts:
        tris = []
        for a in range(0, len(m["i"]) - 2, 3):
            tri = m["i"][a:a + 3]
            cy = (sum(m["p"][v][1] for v in tri) / 3 - y0) / h
            cz = (sum(m["p"][v][2] for v in tri) / 3 - z0) / L
            if 0.42 <= cy <= 0.80 and 0.14 <= cz <= 0.74:
                tris.append(tri)
        if not tris:
            continue
        used = sorted({v for t in tris for v in t})
        ix = {v: k for k, v in enumerate(used)}
        P, N = [], []
        for v in used:
            n = m["n"][v] if v < len(m["n"]) else (0.0, 1.0, 0.0)
            P.append(tuple(m["p"][v][k] + 0.06 * n[k] for k in range(3)))
            N.append(n)
        out.append({"p": P, "n": N, "i": [ix[v] for t in tris for v in t], "uv": None, "tex": None})
    return merge(out)


def split_kit(meshes, y0, y1):
    """light detail (owner 2026-11-11: units too bland, show their age): a soldier's mesh split by triangle height into
    team (torso: player colour), head (helmet / hood: age colour) and legs (trousers / greaves: dark, age-tinted) -
    from feet y0 to top y1 of the person; untextured meshes only"""
    parts = {"team": [], "head": [], "legs": []}
    h = max(0.5, y1 - y0)
    for m in meshes:
        if m.get("tex"):
            parts["team"].append(m)
            continue
        buckets = {k: [] for k in parts}
        for a in range(0, len(m["i"]) - 2, 3):
            tri = m["i"][a:a + 3]
            cy = (sum(m["p"][v][1] for v in tri) / 3 - y0) / h
            buckets["head" if cy > 0.86 else "legs" if cy < 0.45 else "team"].append(tri)
        for k, tris in buckets.items():
            if tris:
                parts[k].append(dict(m, i=[v for t in tris for v in t]))
    return parts      # called on merged meshes: the parts index one vertex list (stored once, pack_mesh "pv")


def split_roof(meshes):
    """owner 2026-11-11: buildings in muted, in-game-like colours so units stand out: untextured building meshes split into
    roof (triangles facing up - mean normal y > 0.35 - above 35 % of the model's height) and walls (the rest)"""
    pts = allpos(meshes)
    if not pts:
        return meshes, []
    (_, y0, _), (_, y1, _) = bbox(pts)
    h = max(0.5, y1 - y0)
    walls, roofs = [], []
    for m in meshes:
        if m.get("tex") or not m.get("n"):
            walls.append(m)
            continue
        w, r = [], []
        for a in range(0, len(m["i"]) - 2, 3):
            tri = m["i"][a:a + 3]
            ny = sum(m["n"][v][1] for v in tri) / 3
            cy = (sum(m["p"][v][1] for v in tri) / 3 - y0) / h
            (r if ny > 0.35 and cy > 0.35 else w).append(tri)
        if w:
            walls.append(dict(m, i=[v for t in w for v in t]))
        if r:
            roofs.append(dict(m, i=[v for t in r for v in t]))
    return walls, roofs


# muted building colours per civ (wall, roof): plaster / stone / wood / sandstone walls, thatch / slate / tile / turf roofs -
# close to the game's look; the page mixes in only a little of the player colour (walls 8 %, roofs 22 %)
CIV_PAL = {"eng": ("#bfb39a", "#8a7650"), "fre": ("#c9bfa8", "#5b6470"), "hre": ("#c8bba0", "#8c4a35"),
           "rus": ("#8a6a48", "#6a5038"), "chi": ("#a39882", "#3f4447"), "mon": ("#cfc6b0", "#a89a7c"),
           "abb": ("#c4a77c", "#9c7c55"), "ayy": ("#c4a77c", "#9c7c55"), "sul": ("#c4a77c", "#9c7c55"),
           "ott": ("#cbbfa6", "#8e4f36"), "mal": ("#a8744c", "#7a6040"), "jpn": ("#8a7058", "#3c4046"),
           "byz": ("#cbbfa8", "#9a5038"), "tem": ("#b8ae98", "#8a5a40"), "lan": ("#b9ad95", "#6a6058"),
           "vik": ("#6e5640", "#5e6a40"), "sco": ("#8e8a80", "#565c62"), "jin": ("#9a8f7a", "#4a4a48")}
PAL_DEFAULT = ("#a89d88", "#6e5c4a")


def building_palette(bp):
    toks = bp.lower().split("_")
    for t in reversed(toks):
        if t in CIV_PAL:
            return CIV_PAL[t]
    return PAL_DEFAULT


def weapon_kind(name):
    n = (name or "").lower()
    if any(w in n for w in ("spear", "pike", "lance", "halberd", "javelin")):
        return "thrust"
    if any(w in n for w in ("cannon_hand", "gun", "musket", "arquebus")):
        return "gun"
    if any(w in n for w in ("bow", "cross", "arbalest", "sling")):
        return "bow"
    return "swing" if n else None


def assemble(pdir, spec):
    """-> {"body": [meshes] (player colour: soldier / rider + shield + extras), "mount": [meshes] (horse / camel /
    elephant, neutral colour), "weapon": [meshes] (grip at the origin, posed in the page), "hand": [x, y, z],
    "kind": thrust / swing / bow / gun, "lift": rider lift, "ext": body box x0 x1 z0 z1} - the page animates weapon and
    body separately"""
    body = load_part(pdir, spec["body"]) if spec.get("body") else []
    if not body:
        return None
    if spec.get("building"):
        xf = spec.get("xf") or {}
        # owner 2026-11-11: models faced the wrong way / longhouses sat in the middle - the stamp's own placement
        if spec.get("pieces"):          # every placed piece with its own placement (a model can repeat in a landmark)
            cache, out = {spec["body"]: body}, []
            for nm, pxf in spec["pieces"]:
                if nm not in cache:
                    cache[nm] = load_part(pdir, nm)
                out += [xform_q(m, pxf) if pxf else m for m in cache[nm]]
        else:
            out = [xform_q(m, xf[spec["body"]]) if spec["body"] in xf else m for m in body]
            for nm in spec.get("extra") or []:
                out += [xform_q(m, xf[nm]) if nm in xf else m for m in load_part(pdir, nm)]
        (x0, _, z0), (x1, y1, z1) = bbox(allpos(out))
        # merged first, then split: roof and walls index one vertex list, which the page stores once (pack_mesh "pv")
        walls, roofs = split_roof(merge(out)) if DETAIL == "light" else (merge(out), [])
        return {"body": walls, "head": roofs, "mount": [], "weapon": [], "hand": [0, 0, 0], "kind": None,
                "lift": 0, "building": True, "ext": [round(v, 2) for v in (x0, x1, z0, z1)], "top": round(y1, 2)}
    mount = [m for m in body if bbox(m["p"])[1][2] - bbox(m["p"])[0][2] > 2.0]
    riders = [m for m in body if m not in mount]
    if mount:
        # owner 2026-11-12 ("elephant armours are floating"): armour / howdah pieces are short meshes already placed on the
        # mount's body - not riders (riders come out standing on the ground, feet ~0). A short mesh whose lowest point is
        # above 0.5 and that lies within the mount's box (+0.3) stays with the mount, unlifted.
        (mx0, _, mz0), (mx1, my1, mz1) = bbox(allpos(mount))
        def on_mount(m):
            (a, b, c), (d, e, f) = bbox(m["p"])
            # +1.0 (owner 2026-11-12: Tughlaq elephant armour has spikes sticking out sideways - with +0.3 they still
            # counted as riders and were lifted to the rider's height)
            return b > 0.5 and a >= mx0 - 1.0 and d <= mx1 + 1.0 and c >= mz0 - 1.0 and f <= mz1 + 1.0 and b < my1
        att = [m for m in riders if on_mount(m)]
        mount += att
        riders = [m for m in riders if m not in att]
    # elephants (owner 2026-11-13: "the elephant and their armor not rendering properly"): every mount mesh but the animal
    # itself (most triangles) is armour / howdah - drawn in its own colour (types[].armour), not the elephant grey
    elephant = bool(mount) and "elephant" in (spec.get("body") or "").lower()
    if elephant:            # Delhi (sul_elephant_combined_armor_*): animal and armour in one mesh - split into pieces
        mount = [c for m in mount for c in components(m)]
    animal = max(mount, key=lambda m: len(m["i"])) if elephant else None
    person, mount_out, lift = [], [], 0.0
    armour_out = []
    if mount:
        hp = allpos(mount)
        (x0, y0, z0), (x1, y1, z1) = bbox(hp)
        third = (z1 - z0) / 3
        # elephants: the rider's height from the animal's back, not the howdah / ballista frame on it (owner 2026-11-13:
        # the Tughlaq ballista elephant's rider stood on the frame's top)
        back = [p[1] for p in (animal["p"] if elephant else hp) if z0 + third <= p[2] <= z1 - third]
        head_front = max((p[1] for p in hp if p[2] > z1 - third), default=0) >= \
            max((p[1] for p in hp if p[2] < z0 + third), default=0)
        mount_out = [xform(m, rot_y=0.0 if head_front else 180.0) for m in mount if not elephant or m is animal]
        armour_out = [xform(m, rot_y=0.0 if head_front else 180.0) for m in mount if elephant and m is not animal]
        if riders:
            rh = bbox(allpos(riders))[1][1]
            lift = (max(back) if back else 1.2) - rh / 2
        mid_z = (z0 + z1) / 2 * (1 if head_front else -1)
        person = [xform(m, t=(0.0, lift, mid_z)) for m in riders]
    else:
        person = list(body)
    if not person:
        if elephant:            # worker elephant (no rider): elephant grey + armour colour, not all in the player colour
            return {"body": [], "mount": merge(mount_out), "armour": merge(armour_out), "weapon": [], "hand": [0, 0, 0],
                    "kind": None, "lift": 0}
        return {"body": merge(mount_out), "mount": [], "weapon": [], "hand": [0, 0, 0], "kind": None, "lift": 0}
    pp = allpos(person)
    for nm in (spec.get("extra") or [])[:2]:              # shields etc. in the left hand, baked into the body
        ex = load_part(pdir, nm)
        # owner 2026-11-12 (Tughlaq elephants: spiked armour pieces floating beside the rider): an extra that is already
        # placed on a mount (lowest point above 0.5 - hand-held pieces grip at the origin) stays with the mount, turned with it
        # owner 2026-11-13: the Tughlaq tusks (tug_tusks_collateral_damage, lowest point exactly 0.5, 5 m long) still went to
        # the hand and floated over the rider - longer than 2 along z = a mount piece too
        if mount and ex:
            (_, ey0, ez0), (_, _, ez1) = bbox(allpos(ex))
            if ey0 > 0.3 or ez1 - ez0 > 2.0:
                (armour_out if elephant else mount_out).extend(xform(m, rot_y=0.0 if head_front else 180.0) for m in ex)
                continue
        hx, hy, hz = hand(pp, -RIGHT)
        person += [xform(m, t=(hx, hy, hz + 0.1)) for m in ex]
    weapon = merge(load_part(pdir, spec["weapon"])) if spec.get("weapon") else []
    hx, hy, hz = hand(pp, RIGHT)
    (_, py0, _), (_, py1, _) = bbox(pp)
    kit = split_kit(merge(person), py0, py1) if DETAIL == "light" else {"team": merge(person), "head": [], "legs": []}
    # charge weapon (the lance; unit_models "charge" since 2026-11-12) when exported - the page draws a plain lance otherwise
    lance = merge(load_part(pdir, spec["charge"])) if spec.get("charge") else []
    return {"body": kit["team"], "head": kit["head"], "legs": kit["legs"], "mount": merge(mount_out), "weapon": weapon,
            "lance": lance, "mountRaw": mount_out, "armour": merge(armour_out),
            "deck": round(max(back), 3) if elephant and back else None,
            "hand": [round(hx, 3), round(hy, 3), round(hz + 0.15, 3)], "kind": weapon_kind(spec.get("weapon")),
            "lift": round(lift, 3)}


def b64f(vals, fmt):
    return base64.b64encode(struct.pack(f"<{len(vals)}{fmt}", *vals)).decode()


# owner 2026-11-12 (p44): with the meshes mirrored (p43) the buildings sat off their slabs - the stamp placements (raw game
# data) only line up with the meshes untouched, so the exports are already in game (left-handed) space. Default: models as
# exported; --mirror-models restores the p43 conversion.
MIRROR_MODELS = False


def mirror_mesh(m):
    """glTF (right-handed) -> game space (left-handed): x negated, winding reversed (owner 2026-11-12: the 3D replay was
    mirrored; the page draws in game coordinates inside a group mirrored in x, so models come out unmirrored)"""
    I = m["i"]
    J = []
    for k in range(0, len(I) - 2, 3):
        J += [I[k], I[k + 2], I[k + 1]]
    return dict(m, p=[(-x, y, z) for x, y, z in m["p"]], n=[(-x, y, z) for x, y, z in m["n"]], i=J)


VBUF = {}               # id(vertex list) -> [index of the mesh carrying it, the list (kept alive so the id is not reused)]


def pack_mesh(m, index):
    """owner 2026-11-13 (3d page 177 MB, 164 MB of it building meshes): positions as int16 over the mesh's box ("q" = min x y z,
    step x y z; < 0.3 mm on a 16 m keep), normals as int8 x 127; meshes cut from one vertex list (roof / walls, head / torso /
    legs) carry only their indices and "pv" = the mesh holding the vertices"""
    src = m["p"]
    if MIRROR_MODELS:
        m = mirror_mesh(m)
    I = m["i"]
    big = len(m["p"]) > 65535
    out = {"i": b64f(I, "I" if big else "H"), "big": big}
    hit = VBUF.get(id(src))
    if hit is not None and hit[1] is src and not m.get("tex"):
        out["pv"] = hit[0]
        return out
    P, N = m["p"], m["n"]
    lo = [min(v[k] for v in P) for k in range(3)]
    hi = [max(v[k] for v in P) for k in range(3)]
    st = [(b - a) / 65535 if b > a else 1.0 for a, b in zip(lo, hi)]
    out["q"] = [round(c, 5) for c in lo] + [float(f"{c:.6g}") for c in st]
    qs = []
    for v in P:
        for k in range(3):
            qs.append(max(-32768, min(32767, int(round((v[k] - lo[k]) / st[k])) - 32768)))
    out["p"] = b64f(qs, "h")
    out["n"] = b64f([max(-127, min(127, int(round(c * 127)))) for v in N for c in v], "b")
    if m.get("tex"):
        out["uv"] = b64f([c for v in m["uv"] for c in v], "f")
        out["tex"] = m["tex"]
    else:
        VBUF[id(src)] = [index, src]
    return out


def tracks(F):
    """per unit [t, x, z, hp, target, ...] keyframes; samples equal to both neighbours dropped"""
    T = {}
    alive = {}
    for t, kind, rows in F["timeline"]:
        seen = set()
        for r in rows:
            ui, x, z, hp, tg = r[0], r[1], r[2], r[3], r[4]
            seen.add(ui)
            if x is None:
                T.setdefault(ui, []).append([round(t, 2), None, None, 0, -1])
                alive.pop(ui, None)
                continue
            T.setdefault(ui, []).append([round(t, 2), round(x, 1), round(z, 1), round(hp or 0, 2), tg])
            alive[ui] = True
        if kind == 0:
            for ui in [u for u in alive if u not in seen]:
                T[ui].append([round(t, 2), None, None, 0, -1])
                alive.pop(ui)
    out = {}
    for ui, s in T.items():
        keep = [s[0]]
        for i in range(1, len(s) - 1):
            if s[i][1:] != s[i - 1][1:] or s[i][1:] != s[i + 1][1:]:
                keep.append(s[i])
        if len(s) > 1:
            keep.append(s[-1])
        out[ui] = [v for k in keep for v in (k[0], k[1] if k[1] is not None else "x", k[2] if k[2] is not None else 0,
                                             k[3], k[4])]
    return out


BUILD_TILES = (("town_center", 4), ("landmark", 4), ("wonder", 5), ("castle", 4), ("keep", 4), ("blacksmith", 4),
               ("market", 4), ("monastery", 4), ("mosque", 4), ("university", 4), ("barracks", 3), ("archery", 3),
               ("stable", 3), ("siege", 3), ("dock", 3), ("arsenal", 3), ("house", 2), ("mill", 2), ("camp", 2),
               ("cabin", 2), ("farm", 2), ("outpost", 1), ("tower", 2), ("wall", 1), ("palisade", 1), ("danevirke", 1), ("gate", 1))


def build_tiles(name):
    n = name.lower()
    return next((k for w, k in BUILD_TILES if w in n), 2)


BUFF_DEFAULT_S = 10.0   # an ability's duration when models/ability_info.json has none
BUFF_KIND = [("prod", r"supervis|oversee|production_speed|work_rate|efficien"), ("heal", r"heal|flask|restoration|regen|blessing"), ("speed", r"march|speed|gallop|maneuver|sails|deployment"),
             ("defence", r"armor|armour|pavise|shield|defensive|iron|reduction|fortif|deflect|guard"),
             ("attack", r"attack|damage|rate_of_fire|berserk|stamina|volley|valorous|inspir|zeal|fervor|strength")]


# durations known from the owner's tests (measured) or read off the tooltip by hand where the rule below picks wrong
KNOWN_DUR = {"longbow_rate_of_fire_ability": 6, "sipahi_stamina_ott": 10, "shaolin_monk_ranged_damage_reduction": 15,
             "infantry_forced_march_sul": 10,                                           # measured (group A buff tests)
             "varangian_berserk_byz": 30, "varangian_berserk_2_byz": 30, "deploy_pavise_fre": 30,
             "khan_attack_speed_signal_arrow_mon": 5, "khan_defensive_signal_arrow_mon": 5, "khan_maneuver_signal_arrow_mon": 5,
             "jeanne_d_arc_valorous_inspiration_fre_ha_01": 20, "jeanne_d_arc_inspired_ally_fre_ha_01": 30,
             "jeanne_d_arc_divine_restoration_fre_ha_01": 2, "hippodrome_triumph_byz": 45, "activate_akritoi_byz": 30, "landmark_activate_akritoi_byz": 30, "nehan_conversion": 20,
             "horse_archer_mounted_training_gallop_rus": 8, "streltsy_double_time_ability_rus": 10, "monk_aoe_heal": 10,
             "siege_carpentry_abb_ha_01": 10, "pilgrim_flask_byz": 6, "naval_man_the_sails": 10}


def tooltip_duration(I):
    """the game files keep an effect's duration in its modifier list, which ability-names does not reach (owner's
    ability_info.json: 0 of 979 with a duration). The tooltip numbers do carry it: the first is the effect's size, the
    duration is the largest later one under 45 s that is not the recharge (Berserking 6 / 30 / 4 -> 30, Body of Iron
    50 / 15 -> 15, Forced March 100 / 10 -> 10, Pavise 1 / 5 / 30 -> 30, Khan arrows 50 / 5 -> 5, Arrow Volley 1 / 6 -> 6).
    Wrong for Valorous Inspiration (4 / 35 / 20 -> 35, true 20): set "duration" by hand in ability_info.json for such."""
    a = [x for x in (I.get("args") or [])[1:] if isinstance(x, (int, float)) and 1 <= x < 45 and x != I.get("recharge")]
    return max(a) if a else None


CISTERN_KEYS = ("cistern_influence_bonus_active_byz",)


def aura_buffs(tl, replay, ui_of):
    """buff glows (owner 2026-11-12: "buff should be a whitish gold glow"): [ui, start, end, name index, kind] from
    analyzer/auras.py (passive auras, toggles, casts ending at the dump's AbilityComplete - the same spans as the viewer's
    buffs lane), + Byzantine buildings while their cistern bonus is active (dump v18 state model
    cistern_influence_bonus_active_byz; the bonus size is not in the data) + the older cast logic's spans on buildings
    (abilities aimed at a building). Kind kept for the tooltip only; every glow is the same colour."""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from auras import run as aura_run
    A = aura_run(tl, replay if replay and os.path.exists(replay) else None)
    names, nix, rows = [], {}, []

    def ni(nm):
        if nm not in nix:
            nix[nm] = len(names)
            names.append(nm)
        return nix[nm]

    def kind_of(fx):
        p = " ".join(str(e.get("property") or "") for e in fx or [])
        return ("attack" if re.search(r"Attack|attackSpeed", p) else "defence" if "Armor" in p else "speed" if "moveSpeed" in p
                else "heal" if "heal" in p.lower() else "other")

    stk = A.get("stacks") or {}
    for i, ab, t0, t1 in A.get("spans") or []:
        ui = ui_of.get(i)
        if ui is not None and ab not in stk:
            rows.append([ui, t0, t1 + 1.0, ni((A.get("names") or {}).get(ab) or ab), kind_of((A.get("effects") or {}).get(ab))])
    # stackable auras (owner 2026-11-13: Lord of Lancaster Inspiration, +5 % HP per Lord in range): one row per stack level,
    # the name carries the count and the total bonus; HUNTS["hp"] -> D.buffHp {name index: HP %} for the selected-units box
    for ab, E in stk.items():
        fx = (A.get("effects") or {}).get(ab) or []
        hp = next((round((float(x["value"]) - 1) * 100, 1) for x in fx if x.get("property") == "hitpoints" and x.get("effect") == "multiply"), None)
        for i, L in E.items():
            ui = ui_of.get(int(i))
            if ui is None:
                continue
            for t0, t1, n in L:
                nm = ((A.get("names") or {}).get(ab) or ab) + (f" ×{n}" if n > 1 else "") + (f" (+{hp * n:g}% HP)" if hp else "")
                k = ni(nm)
                if hp:
                    BUFF_HP[k] = hp * n
                rows.append([ui, t0, t1 + 1.0, k, kind_of(fx)])
    for k, L in (tl.get("esm") or {}).items():
        ui = ui_of.get(int(k))
        if ui is None:
            continue
        on = None
        for t, vals in L:
            act = any(vals.get(key) in (1, True, "1") for key in CISTERN_KEYS)
            if act and on is None:
                on = t
            elif not act and on is not None:
                rows.append([ui, on, t, ni("Cistern influence"), "prod"])
                on = None
        if on is not None:
            rows.append([ui, on, (tl["frames"][-1]["t"] if tl.get("frames") else on) + 1, ni("Cistern influence"), "prod"])
    try:
        old_rows, old_names = buff_spans(tl, replay, ui_of)
        bld = {ui for ui, u in enumerate(_UNITS_FOR_BUFFS or []) if u[3] == "building"}
        for r in old_rows or []:
            if r[0] in bld:
                rows.append([r[0], r[1], r[2], ni(old_names[r[3]]), r[4]])
    except Exception:  # noqa: BLE001 - the older building-cast spans are optional
        pass
    # Irrigated (owner 2026-11-12): villagers within 9.5 tiles of a cistern gather +10 / 14 / 18 / 22 / 24 % by its water level,
    # kept 20 s after leaving, not stacking - the game's own per-villager state model cistern_highest_tier_within_byz (the best
    # level around it, 0 = none) gives it directly
    IRR = {1: 10, 2: 14, 3: 18, 4: 22, 5: 24}
    for k, L in (tl.get("esm") or {}).items():
        ui = ui_of.get(int(k))
        if ui is None:
            continue
        on, lvl = None, 0
        for t, v in L:
            tier = int(v.get("cistern_highest_tier_within_byz") or 0)
            if tier > 0 and on is None:
                on, lvl = t, tier
            elif tier > 0 and tier != lvl:
                rows.append([ui, on, t, ni(f"Irrigated Lv {lvl} (+{IRR.get(lvl, '?')}% gather)"), "other"])
                on, lvl = t, tier
            elif tier == 0 and on is not None:
                rows.append([ui, on, t + 20, ni(f"Irrigated Lv {lvl} (+{IRR.get(lvl, '?')}% gather)"), "other"])
                on = None
        if on is not None:
            rows.append([ui, on, (tl["frames"][-1]["t"] if tl.get("frames") else on) + 1,
                         ni(f"Irrigated Lv {lvl} (+{IRR.get(lvl, '?')}% gather)"), "other"])
    n_c = sum(1 for r in rows if names[r[3]] == "Cistern influence")
    print(f"  buff glows: {len(rows)} spans ({n_c} cistern), {len(names)} buffs")
    return rows or None, names or None


_UNITS_FOR_BUFFS = None
BUFF_HP = {}            # buff name index -> HP % (stackable HP auras), filled by aura_buffs


def buff_spans(tl, replay, ui_of):
    """buff rings (owner 2026-11-11: "this is how it should be in the 3d replays"): per unit [ui, start, end, name index,
    kind] while a cast buff is up. Starts: the replay file's ability commands (every entity of each receiving squad, or the
    entities named) and dump v12 AB events (caster); toggles stay on until their stop command or the next toggle of the same
    ability; abilities aimed at a position buff the caster player's units within the ability's radius of it. Durations and
    radii: models/ability_info.json (game_assets.py ability-names, local), else BUFF_DEFAULT_S; always-on abilities (auras)
    are skipped. Names: data/abilities.json (aoe4world) / ability_info."""
    if not replay and not tl.get("abilities"):
        return None, None
    info, names = {}, {}
    try:
        info = json.load(open(os.path.join(ROOT, "models", "ability_info.json"), encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    try:
        for k, v in json.load(open(os.path.join(ROOT, "data", "abilities.json"), encoding="utf-8"))["abilities"].items():
            names[k] = v
    except (OSError, ValueError, KeyError):
        pass
    by_attrib = {v.get("attrib", "").lower(): k for k, v in names.items()}
    by_attrib.update({v.get("attrib", "").lower(): k for k, v in info.items() if v.get("attrib")})
    frames = tl.get("frames") or []
    ft = [fr["t"] for fr in frames]
    import bisect

    def frame_at(t):
        return frames[max(0, min(len(frames) - 1, bisect.bisect_right(ft, t) - 1))] if frames else {"entities": []}

    def ab(key):
        I = info.get(key) or {}
        N = names.get(key) or {}
        attrib = (I.get("attrib") or N.get("attrib") or str(key)).lower()
        act = I.get("activation") or {"manual": "timed", "toggle": "toggle", "always": "always_on"}.get(N.get("active"), "timed")
        nm = N.get("name") or I.get("name") or attrib
        kind = next((k for k, rx in BUFF_KIND if re.search(rx, attrib)), "other")
        return attrib, act, nm, float(I.get("duration") or KNOWN_DUR.get(attrib) or tooltip_duration(I) or BUFF_DEFAULT_S), float(I.get("radius") or 0), kind

    casts = []                                   # (t, kind cast / stop, key, entity ids, target pos)
    if replay and os.path.exists(replay):
        sys.path.insert(0, os.path.join(ROOT, "analyzer"))
        from replay import abilities
        for c in abilities(replay):
            if not c["pbg"]:
                continue
            fr = frame_at(c["t"])
            sq = set(c["squads"])
            ids = list(c["entities"]) + [e["id"] for e in fr["entities"] if e.get("squad") in sq]
            tgt = c["target"][1:] if c["target"] and c["target"][0] == "pos" else None
            # building buffs (owner 2026-11-12): an ability aimed at a building (Chinese officials supervising, ...) buffs
            # that building - the target gets the ring, not the caster
            if c["target"] and c["target"][0] in ("entity", "squad"):
                tid = c["target"][1]
                tb = [e for e in fr["entities"] if (e["id"] == tid if c["target"][0] == "entity" else e.get("squad") == tid)
                      and str(e.get("bp", "")).lower().startswith("building")]
                if tb:
                    ids = [e["id"] for e in tb]
            casts.append((c["t"], c["kind"], str(c["pbg"]), ids, tgt))
    for r in tl.get("abilities") or []:          # dump v12: [t, event, caster, ability name, target]
        t, ev, caster, an = r[0], r[1], r[2], (r[3] or "").lower()
        if "complete" not in str(ev).lower() and "executed" not in str(ev).lower():
            continue
        key = by_attrib.get(an)
        if key is None or not str(caster).isdigit():
            continue
        ids = [int(caster)]
        tg = str(r[4]) if len(r) > 4 and r[4] is not None else ""
        if tg.isdigit():                         # aimed at a building: the building is buffed
            tb = [e for e in frame_at(t)["entities"] if e["id"] == int(tg) and str(e.get("bp", "")).lower().startswith("building")]
            if tb:
                ids = [int(tg)]
        casts.append((t, "cast", key, ids, None))
    casts.sort(key=lambda c: c[0])
    spans, nidx, open_t = [], {}, {}
    for t, kind, key, ids, tgt in casts:
        attrib, act, nm, dur, rad, bk = ab(key)
        if act == "always_on":
            continue
        # unknown ids (not in aoe4world's list nor ability_info) and non-buff commands (unload, weapon swap, production
        # toggles ...: no buff word in the name and not an aoe4world ability) draw nothing
        if key not in names and (key not in info or bk == "other"):
            continue
        if re.search(r"production|swap|unload|pack|relocate|toggle_.*_off|loan|spawn|mover|town_bell|detonate", attrib):
            continue
        if nm not in nidx:
            nidx[nm] = len(nidx)
        if tgt and rad > 0:                      # area: the caster player's units near the target point
            fr = frame_at(t)
            own = {e["owner"] for e in fr["entities"] if e["id"] in set(ids)}
            ids = [e["id"] for e in fr["entities"] if e["owner"] in own and e.get("x") is not None
                   and math.hypot(e["x"] - tgt[0], e["z"] - tgt[1]) <= rad]
        for i in ids:
            ui = ui_of.get(i)
            if ui is None:
                continue
            k2 = (ui, nm)
            if act == "toggle":
                if k2 in open_t:                 # second toggle or stop = off
                    spans[open_t.pop(k2)][2] = round(t, 2)
                elif kind == "cast":
                    open_t[k2] = len(spans)
                    spans.append([ui, round(t, 2), None, nidx[nm], bk])
            elif kind == "cast":
                spans.append([ui, round(t, 2), round(t + dur, 2), nidx[nm], bk])
    tend = ft[-1] if ft else 0
    for sp in spans:
        if sp[2] is None:
            sp[2] = round(tend, 2)
    # one span per unit and ability: drop exact repeats (replay command + dump event of the same cast)
    seen, out = set(), []
    for sp in spans:
        k3 = (sp[0], sp[3], round(sp[1]))
        if k3 not in seen:
            seen.add(k3)
            out.append(sp)
    print(f"  buff rings: {len(out)} unit spans from {len(casts)} casts ({len(nidx)} abilities)")
    return out or None, [n for n, _ in sorted(nidx.items(), key=lambda x: x[1])] or None


PROD_R = 22.0         # a new unit / villager within this of a producing building of its owner came out of it (hud.SPAWN_R)


def prod_rows(tl, ui_of, F):
    """building production (owner 2026-11-12: "building production (unit production, upgrades) need to be shown"):
    {building ui: [[start, done, 0 unit / 1 upgrade, bp or attrib], ...]} and the queue size track {ui: [t, q, ...]}.
    Units: each new unit / villager (not at the start) credited to the nearest building of its owner with a queue now or a
    second before, within PROD_R, that can make it (production.json producedBy vs its base id; the dump has only the queue size, not the item); start = done - production time
    (units.json time) but not before the building's previous item was done. Upgrades: U events whose executer is the
    building, start = done - research time (upgrades.json for the owner's civ; none = 30 s, marked). Age-ups skipped.
    Both are hindsight: the page shows them in the observer view only for the observer's own buildings.
    Dump v18 queue heads (tl["queueHead"], owner 2026-11-12: replaces the nearest-building guess): a new unit goes to the
    owner's building whose queue head just before it appeared was that blueprint (nearest of several); none = the old
    rule. Upgrade starts = the head turning to that upgrade at that building, when recorded."""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from gamedata import resolve
    from techs_bought import AGE_UPS, _entry, civ_code, load_upgrades
    frames = tl.get("frames") or []
    if not frames:
        return None, None
    try:
        U = json.load(open(os.path.join(ROOT, "data", "units.json"), encoding="utf-8"))["units"]
    except (OSError, ValueError, KeyError):
        U = {}

    def utime(bp):
        e = U.get(bp) or U.get(resolve(bp, U) or "")
        return (e or {}).get("time")

    try:
        PR = json.load(open(os.path.join(ROOT, "data", "production.json"), encoding="utf-8"))
    except (OSError, ValueError):
        PR = {}
    PU, PB = PR.get("units") or {}, PR.get("buildingBase") or {}

    def can_make(bbp, ubp):
        """producer check (aoe4world producedBy vs the building's base id); unknown either way = allowed"""
        by = PU.get(ubp) or PU.get(resolve(ubp, PU) or "")
        base = PB.get(bbp) or PB.get(resolve(bbp, PB) or "")
        return not by or not base or base in by

    qhead = {int(k): v for k, v in (tl.get("queueHead") or {}).items()}
    qi = {k: 0 for k in qhead}

    def head_before(bid, t):
        """the building's queue head (bp) as last written before t"""
        rows, i = qhead[bid], qi[bid]
        while i + 1 < len(rows) and rows[i + 1][0] < t:
            i += 1
        qi[bid] = i
        return rows[i][3] if rows and rows[i][0] < t else None

    bowner = {}
    by_head = 0
    items, qtrack, lastq = {}, {}, {}
    seen = {e["id"] for e in frames[0]["entities"]}
    prevq = {}
    for fr in frames:
        t = fr["t"]
        prodb = {}
        for e in fr["entities"]:
            if e["kind"] != "o" or e["x"] is None:
                continue
            q = int(e.get("queue") or 0)
            ui = ui_of.get(e["id"])
            if ui is not None and lastq.get(ui, 0) != q:
                qtrack.setdefault(ui, []).extend([round(t, 1), q])
                lastq[ui] = q
            if q > 0 or prevq.get(e["id"]):
                prodb.setdefault(e["owner"], []).append(e)
            bowner.setdefault(e["id"], (e["owner"], e))
        for e in fr["entities"]:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            if e["kind"] not in ("m", "w") or e["x"] is None:
                continue
            hb = [bowner[b][1] for b in qhead if b in bowner and bowner[b][0] == e["owner"] and head_before(b, t) == e["bp"]]
            if hb:
                best = min(hb, key=lambda b: (b["x"] - e["x"]) ** 2 + (b["z"] - e["z"]) ** 2)
                if best["id"] in ui_of:
                    items.setdefault(ui_of[best["id"]], []).append([t, 0, e["bp"]])
                    by_head += 1
                continue
            cand = [b for b in prodb.get(e["owner"], []) if can_make(b["bp"], e["bp"])]
            best = min(cand, key=lambda b: (b["x"] - e["x"]) ** 2 + (b["z"] - e["z"]) ** 2, default=None)
            if best and (best["x"] - e["x"]) ** 2 + (best["z"] - e["z"]) ** 2 <= PROD_R ** 2 and best["id"] in ui_of:
                items.setdefault(ui_of[best["id"]], []).append([t, 0, e["bp"]])
        prevq = {e["id"]: (e.get("queue") or 0) > 0 for e in fr["entities"] if e["kind"] == "o"}
    table = load_upgrades()
    owner = {u[0]: u[1] for u in F["units"]}
    for ev in tl.get("events") or []:
        if ev.get("type") != "upgrade":
            continue
        ex, name = str(ev.get("executer") or ""), (ev.get("upgrade") or "")[1:]
        if not ex.startswith("e") or not ex[1:].isdigit() or name in AGE_UPS:
            continue
        ui = ui_of.get(int(ex[1:]))
        if ui is None:
            continue
        qs = [r[0] for r in qhead.get(int(ex[1:]), []) if r[2] == "upgrade" and r[3] == name and r[0] <= ev["t"] + 0.5]
        items.setdefault(ui, []).append([ev["t"], 1, name] + ([max(qs)] if qs else []))
    out = {}
    for ui, L in items.items():
        L.sort(key=lambda x: x[0])
        prev, rows = -1e9, []
        p = F["units"][ui][1]
        code = civ_code(tl, p) if p else None
        for it in L:
            done, k, key = it[:3]
            if k == 0:
                d = utime(key)
                st = max(done - (d or 20), prev) if d else max(done - 20, prev)
            elif len(it) > 3:
                st = it[3]                                 # dump v18 queue head
            else:
                e = _entry(key, code, table)
                st = done - ((e or {}).get("time") or 30)
            rows.append([round(min(st, done), 1), round(done, 1), k, key])
            if k == 0:
                prev = done
        out[str(ui)] = rows
    nu = sum(1 for L in out.values() for r in L if r[2] == 0)
    print(f"  building production: {nu} units / villagers ({by_head} by queue head), {sum(len(L) for L in out.values()) - nu} upgrades over {len(out)} buildings")
    return out or None, {str(k): v for k, v in qtrack.items()} or None


CHARGE_CD = 10.0      # s out of combat until a charge is ready again - a guess until buff-scout / a test gives the game's value
CHARGE_RE = re.compile(r"knight|lancer|cataphract|templar_brother|chevalier|elephant|gilded|royal_knight|demilancer")


def chargers(bps):
    """blueprint indices of units with a charge attack: charge weapon damage > normal weapon damage in the game's weapon
    files (data/game_weapons.json, local only); without that file a name rule (knights, lancers, elephants ...)"""
    try:
        W = json.load(open(os.path.join(ROOT, "data", "game_weapons.json"), encoding="utf-8"))
    except (OSError, ValueError):
        W = None
    dmg = {}
    if W:
        for k, v in W.items():
            n = re.split(r"[\\/]", k)[-1][:-5].lower()
            d = next((x for kk, x in v.items() if kk.endswith("/default/weapon_bag/damage/max")), None)
            if d is not None:
                dmg[n] = d
    out = set()
    for i, b in enumerate(bps):
        b = b.lower()
        if b.startswith("building") or not b.startswith("unit_"):
            continue
        m = re.match(r"unit_(.+?)_(\d)_?(.*)$", b)
        if dmg and m:
            base, tier, civ = m.groups()
            cands = [f"weapon_{base}_{tier}_charge_{civ}", f"weapon_{base}_{tier}_charge"] if civ else [f"weapon_{base}_{tier}_charge"]
            norm = [f"weapon_{base}_{tier}_{civ}", f"weapon_{base}_{tier}"] if civ else [f"weapon_{base}_{tier}"]
            c = next((dmg[x] for x in cands if x in dmg), None)
            nn = next((dmg[x] for x in norm if x in dmg), None)
            if c is not None:
                if nn is None or c > nn:
                    out.add(i)
                continue
        if CHARGE_RE.search(b):
            out.add(i)
    return out



# owner 2026-11-11: projected exhaust timer of the exhaustible resources near each drop-off point (not wood, not farms).
# Per node snapshot (5 s): food (berries, carcasses, animals being eaten), gold, stone nodes with what is left and how fast
# they went down over the last EXH_WIN s (all gatherers); nodes gone in that window count with 0 left. The page sums those
# within reach of each mill / mining camp / town centre: time = left / rate.
EXH_WIN = 60.0
EXH_KIND = {"berry": 0, "carcass": 0, "deer": 0, "boar": 0, "sheep": 0, "gold": 1, "stone": 2}
ANIMALS = ("deer", "boar", "sheep")


def exhaust_rows(node_snaps, most):
    hist, rows, j = [], [], 0
    for sn in node_snaps:
        cur = {}
        for n in sn["nodes"]:
            k = EXH_KIND.get(n.get("type"))
            if k is None or n.get("id") is None or n.get("x") is None or n.get("left") is None:
                continue
            cur[n["id"]] = (k, n["x"], n["z"], float(n["left"]), n.get("type"))
        hist.append((sn["t"], cur))
        while j + 1 < len(hist) and hist[j + 1][0] <= sn["t"] - EXH_WIN:
            j += 1
        t0, old = hist[j]
        dt = sn["t"] - t0
        R = []
        for i, (k, x, z, left, ty) in cur.items():
            was = old.get(i, (k, x, z, left, ty))[3]
            rate = max(0.0, was - left) / dt * 60 if dt > 0 else 0.0
            if ty in ANIMALS and rate <= 0 and left >= (most.get(i) or left):
                continue                       # a live animal nobody is eating
            if left > 0 or rate > 0:
                R.append([k, round(x, 1), round(z, 1), round(left), round(rate, 1)])
        for i, (k, x, z, left, ty) in old.items():   # gone in the window: eaten / mined out
            if i not in cur and left > 0 and dt > 0:
                R.append([k, round(x, 1), round(z, 1), 0, round(left / dt * 60, 1)])
        rows.append({"t": round(sn["t"], 1), "n": R})
    return rows


def fog_data(F, tl_path, bps, replay=None):
    """fog of war (owner 2026-11-10) from the game's own visibility flags (the no-maphack rule): per unit the times its
    vis mask changed [t, mask, ...] (bit p-1 = seen by player p), each player's age changes [t, age, ...], sight radius
    per blueprint (data/sight.json) for the explored / visible ground, and the blueprint tier digit"""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from gamedata import resolve
    out = {"vis": None, "ages": {}, "sight": [], "tier": []}
    try:
        sight = json.load(open(os.path.join(ROOT, "data", "sight.json"), encoding="utf-8"))["sight"]
    except (OSError, ValueError, KeyError):
        sight = {}
    for b in bps:
        r = sight.get(b) or sight.get(resolve(b, sight) or "") or (0 if b.lower().startswith("building") else 0)
        if not r and b.lower().startswith("building"):
            r = 20
        out["sight"].append(r or 0)
        m = re.search(r"_(\d)(?:_|$)", b)
        out["tier"].append(int(m.group(1)) if m else 0)
    if not tl_path or not os.path.exists(tl_path):
        return out
    tl = load_tl(tl_path)
    ui_of = {u[0]: i for i, u in enumerate(F["units"])}
    global _UNITS_FOR_BUFFS
    _UNITS_FOR_BUFFS = F["units"]
    vis, last = {}, {}
    for fr in tl.get("frames") or []:
        t = round(fr["t"], 2)
        for e in fr["entities"]:
            ui = ui_of.get(e["id"])
            if ui is None:
                continue
            m = e.get("vis") or 0
            if last.get(ui) != m:
                vis.setdefault(ui, []).extend([t, m])
                last[ui] = m
        for pk, P in (fr.get("players") or {}).items():
            ag = P.get("age")
            A = out["ages"].setdefault(pk, [])
            if ag is not None and (not A or A[-1] != ag):
                A.extend([t, ag])
    out["vis"] = vis
    # building headings (dump v7 A4D|BH; owner 2026-11-10: walls must follow the wall line)
    out["bhead"] = {str(ui_of[int(k)]): v for k, v in (tl.get("heading") or {}).items() if int(k) in ui_of}
    # map objects with their blueprints (mines / trees at their real size and model), full snapshots only
    nbps, nix = [], {}
    snaps = []
    most = {}                     # node id -> largest remaining amount seen (a tree being cut: felled in the page)
    for sn in tl.get("nodes") or []:
        for n in sn["nodes"]:
            if n.get("left") is not None and n.get("id") is not None:
                most[n["id"]] = max(most.get(n["id"], 0), n["left"])
    for sn in tl.get("nodes") or []:
        if not sn.get("full"):
            continue
        rows = []
        for n in sn["nodes"]:
            if n.get("x") is None:
                continue
            b = n.get("bp") or ""
            if b not in nix:
                nix[b] = len(nbps)
                nbps.append(b)
            left, top = n.get("left"), most.get(n.get("id"))
            frac = round(left / top, 2) if left is not None and top else None
            if frac is not None and frac <= 0:
                continue
            rows.append([n.get("type") or "", round(n["x"], 1), round(n["z"], 1), nix[b], frac])
        snaps.append({"t": sn["t"], "n": rows})
    if snaps:
        out["nodes"], out["nodeBps"] = snaps, nbps
        tr = [sum(1 for r in sn["n"] if r[0] in ("tree", "stealth", "straggler")) for sn in snaps]
        print(f"  trees in the snapshots: {tr[0]} at the start, {tr[-1]} at the end ({len(snaps)} snapshots"
              + ("; none cut: the log has no tree removals - dump v10 records trees being cut" if tr[0] == tr[-1] else "") + ")")
    out["exh"] = exhaust_rows(tl.get("nodes") or [], most)
    # projectiles (dump v9): fired [t, attacker ui, target ui or -1, x, z] / landed; arrows drawn from them
    shots = []
    for sh in tl.get("shots") or []:
        t, kind, att, proj, tgt, x, z = sh[:7]
        if kind == "F" and ui_of.get(att) is not None:
            shots.append([round(t, 2), ui_of[att], ui_of.get(tgt, -1) if tgt else -1,
                          round(x, 1) if x is not None else None, round(z, 1) if z is not None else None])
    out["shots"] = shots or None
    # emplacements (owner 2026-11-11): building upgrades (bupgrade_*, executer = the building) that add a weapon -
    # springald / cannon / arrowslits / handcannon slits; [building ui, done t, kind]. Shots from that building after it
    # are drawn as that weapon's projectile.
    empl = []
    for e in tl.get("events") or []:
        if e.get("type") != "upgrade" or not str(e.get("upgrade", "")).startswith("bupgrade_"):
            continue
        u = e["upgrade"].lower()
        kind = ("springald" if "springald" in u else "cannon" if re.search(r"cannon|culverin|bombard", u) and "handcannon" not in u
                else "handcannon" if "handcannon" in u or "hand_cannon" in u else "arrowslit" if "arrowslit" in u or "slit" in u else None)
        try:
            eid = int(str(e.get("executer", ""))[1:])
        except ValueError:
            continue
        if kind and eid in ui_of:
            empl.append([ui_of[eid], round(e["t"], 1), kind, e["upgrade"][1:]])     # attrib as in the techs list (icon)
    out["empl"] = empl or None
    out["prod"], out["queue"] = prod_rows(tl, ui_of, F)
    # splash radius per attacking blueprint (impact circles for stones / balls / rockets / grenades): the game's weapon
    # area radius (data/game_weapons.json, local) else none (the page uses its defaults)
    try:
        sys.path.insert(0, os.path.join(ROOT, "analyzer"))
        from fightcal import game_weapon
        aoe = {}
        for s_ in shots:
            bp = F["bps"][F["units"][s_[1]][2]]
            if bp not in aoe:
                w = game_weapon(bp)
                aoe[bp] = round(w["R"], 2) if w and w.get("R") else None
        out["aoe"] = {b: r for b, r in aoe.items() if r} or None
    except Exception:  # noqa: BLE001 - defaults in the page
        out["aoe"] = None
    # deflected hits (owner 2026-11-11: deflective armour negates a damage instance - shown white): dump v9 damage
    # events with no damage, per victim [t, ...]
    try:                # damage-over-time ticks credited to the unit that applied them (analyzer/dot.py)
        sys.path.insert(0, os.path.join(ROOT, "analyzer"))
        from dot import retag
        tl["hits"], _ = retag(tl)
    except Exception:  # noqa: BLE001 - the raw hits stay
        pass
    defl = {}
    for h in tl.get("hits") or []:
        t, att, vic, dmg = h[0], h[1], h[2], h[3]
        if dmg is not None and dmg <= 0 and ui_of.get(vic) is not None:
            defl.setdefault(str(ui_of[vic]), []).append(round(t, 2))
    out["deflect"] = defl or None
    # per-unit hits between players (owner 2026-11-13: selected units' share of the recap's damage / hits), flat
    # [t x 100, attacker ui, victim ui, damage x 10, ...]; deflected (0) hits kept - they count as hits landed, like hud.py
    # owner 2026-11-13 (selected spears / hobelars showed almost no damage): units upgraded to the next tier keep their first
    # blueprint in F["units"], while the recap names the attacker by its blueprint at the hit (veteran). D.bpAt {ui: [[t, bp
    # index]]} = each unit's blueprint over time (only units that changed); hits carry the attacker's blueprint at the hit.
    from dot import bp_index, who
    hist = bp_index(tl) if tl.get("frames") else {}
    bp_names = F.get("names")
    try:
        CN = json.load(open(os.path.join(ROOT, "data", "costs.json"), encoding="utf-8"))["costs"]
    except (OSError, ValueError, KeyError):
        CN = {}
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from gamedata import resolve as _res

    def bidx(bp):
        if bp not in bps:
            bps.append(bp)
            if isinstance(bp_names, list):
                bp_names.append((CN.get(_res(bp, CN) or "") or {}).get("name") or bp)
        return bps.index(bp)
    bp_at = {}
    for i, h in hist.items():
        ui = ui_of.get(i)
        if ui is not None and len({x[1] for x in h}) > 1:
            bp_at[str(ui)] = [[round(t, 1), bidx(b)] for t, b, _ in h]
    out["bpAt"] = bp_at or None
    he = []
    for h in sorted(tl.get("hits") or [], key=lambda h: h[0]):
        ua, uv = ui_of.get(h[1]), ui_of.get(h[2])
        if ua is None or uv is None or h[3] is None or h[3] < 0 or F["units"][ua][1] == F["units"][uv][1]:
            continue
        ab = who(hist, h[1], h[0])[0] if str(ua) in bp_at else None
        he += [int(round(h[0] * 100)), ua, uv, int(round(h[3] * 10)), bidx(ab) if ab else F["units"][ua][2]]
    out["hitsE"] = he or None
    out["hitsW"] = 5
    # cisterns (owner 2026-11-12: villager circle, level, influence square with the toggled buff): per cistern ui the recorded
    # state models over time [t, network level, influence mode] (dump v18 ES: cistern_network_level_byz,
    # cistern_influence_mode_byz); radii from the game files (building_cistern_byz: ui_range_radius 38 = the villager gather
    # aura, district_generator_ext range_metres 16 = the building influence beyond the cistern's edge - 259818624: all 21
    # buildings the game marked buffed lie in that square, 1 unbuffed one too)
    cist = {}
    for k, L in (tl.get("esm") or {}).items():
        ui = ui_of.get(int(k))
        if ui is None or "cistern" not in str(F["bps"][F["units"][ui][2]]):
            continue
        rows, last = [], None
        for t, v in L:
            r = [v.get("cistern_network_level_byz"), v.get("cistern_influence_mode_byz")]
            if r != last:
                rows.append([round(t, 1), r[0], r[1]])
                last = r
        if rows:
            cist[str(ui)] = rows
    out["cist"] = cist or None
    # charge (owner 2026-11-11: the knight's ring shows the charge cooldown): units whose charge weapon hits harder than
    # their normal one (game weapon files: knight 36 vs 24; horseman 9 = 9 = no charge). Per charger [spent, last combat]:
    # spent = first damage dealt while charged, last combat = last damage dealt / taken before CHARGE_CD s without any
    # (the page refills the ring over CHARGE_CD after that)
    cb = chargers(bps)
    ch_ui = {i for i, u in enumerate(F["units"]) if u[2] in cb}
    ev = {}
    for h in tl.get("hits") or []:
        t, att, vic = h[0], h[1], h[2]
        for who, dealt in ((att, 1), (vic, 0)):
            ui = ui_of.get(who)
            if ui in ch_ui:
                ev.setdefault(ui, []).append((t, dealt))
    charge = {}
    for ui, L in ev.items():
        L.sort()
        iv, ready, last = [], True, -1e9
        for t, dealt in L:
            if not ready and t - last >= CHARGE_CD:
                ready = True
            if dealt and ready:
                ready = False
                iv.append([round(t, 2), round(t, 2)])
            elif not ready and iv:
                iv[-1][1] = round(t, 2)
            last = t
        if iv:
            charge[str(ui)] = iv
    out["charge"] = charge or None
    out["chargeCD"] = CHARGE_CD
    try:
        out["buffs"], out["buffNames"] = aura_buffs(tl, replay, ui_of)
        out["buffHp"] = {str(k): v for k, v in BUFF_HP.items()} or None
    except Exception as e:  # noqa: BLE001 - the page builds without buff glows
        print(f"  buff glows skipped: {type(e).__name__}: {e}")
        out["buffs"], out["buffNames"] = None, None
    out["_ui_of"] = ui_of
    return out


MIL_RE = re.compile(r"unit_|armor|weapon|melee|ranged|siege|infantry|cavalry|archer|knight|spear|ballist|gunpowder|"
                    r"incendiary|chemistry|biology|greased|tactic|veteran|elite|bloodline|crossbow|springald|"
                    r"mangonel|cannon|bombard|handcannon|horseman|manatarms|lancer|camel|elephant|longbow|"
                    r"arrow|bodkin|fletching|steeled|serrated|fitted|insulated|siege_works|geometry|"
                    r"wedge|riveted|damascus|chainmail|plate|banded|outpost|tower|keep|wall|palisade|"
                    r"springald|burgrave|inspired|military", re.I)


def tech_rows(F):
    """done upgrades per player for the top bar (owner 2026-11-11): row 1 economy, row 2 military, row 3 unsure;
    a family (attrib without its trailing _N) is one icon with notches for the stages done of the stages known"""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    try:
        ups = json.load(open(os.path.join(ROOT, "data", "upgrades.json"), encoding="utf-8"))["upgrades"]
    except (OSError, ValueError, KeyError):
        ups = {}
    stems = {}
    for at in ups:
        m = re.match(r"(.+?)_(\d)$", at)
        if m:
            stems.setdefault(m.group(1), set()).add(int(m.group(2)))
    out = {}
    for p, lst in (F.get("techs") or {}).items():
        rows = []
        for done, at, name, mil, *_ in lst:
            m = re.match(r"(.+?)_(\d)$", at)
            stem, stage = (m.group(1), int(m.group(2))) if m else (at, 0)
            row = 0 if not mil else 1 if MIL_RE.search(at) else 2
            known = sorted(stems.get(stem, {stage}))      # owner 2026-11-11: count of stages, not the highest number
            idx = known.index(stage) + 1 if stage in known else stage
            rows.append([round(done, 1), at, name, row, stem, idx if stage else 0, len(known) if stage else 0])
        out[p] = rows
    return out


_TL = {}


def load_tl(path):
    """the timeline JSON, read once per build (several steps use it)"""
    if not path or not os.path.exists(path):
        return {}
    if path not in _TL:
        _TL[path] = json.load(open(path, encoding="utf-8"))
    return _TL[path]


WATER_R = 7          # tiles: closing radius - valleys up to ~2 x 7 tiles wide get a lid
WATER_DEPTH = 1.8    # m (owner's river2 vs the in-game minimap 2026-11-12; was 0.6): a tile counts as water when it lies this far below the lid (and its valley holds evidence)
NAVAL_RE = re.compile(r"naval|ship|boat|junk|galley|dhow|carrack|hulk|baochuan|lodya|baghlah|xebec|kobaya|atakebune|longship|drakkar|cog")


def _maxf(G, r, f):
    """separable max / min filter (square window, radius r) over a grid with None holes"""
    R, C = len(G), len(G[0])
    A = [[f([G[i][k] for k in range(max(0, j - r), min(C, j + r + 1)) if G[i][k] is not None] or [None]) if any(
        G[i][k] is not None for k in range(max(0, j - r), min(C, j + r + 1))) else None for j in range(C)] for i in range(R)]
    return [[f([A[k][j] for k in range(max(0, i - r), min(R, i + r + 1)) if A[k][j] is not None] or [None]) if any(
        A[k][j] is not None for k in range(max(0, i - r), min(R, i + r + 1))) else None for j in range(C)] for i in range(R)]


def water_map(F, tl):
    """where the water is and how high it stands, per tile (owner 2026-11-12: "some of the water doesn't have a level elevation
    ... it needs to identify where the water is and fill them properly"). Rivers slope, so one level per lake does not work.
    - lid = morphological closing of the ground (max then min filter, radius WATER_R): the ground with every valley up to ~14
      tiles wide bridged at its banks' height - it slopes with the river.
    - evidence: tiles the grid calls water ("w": cover name, dump v13 boat probe, basin rule), tiles naval units stood on,
      fish nodes.
    - the page grows the water from the evidence through tiles at least "min depth" (default WATER_DEPTH) below the lid; "w"
      tiles always count; level = lid - 0.15 smoothed; floor = lowest ground within 2 tiles (depth slider).
    -> {"lid", "dep" (lid - ground), "floor": rows of numbers, "ev": rows of "0" / "1" / "2" (grid water), "thr"}"""
    B, T, o = F.get("blocked"), F.get("terrain"), F.get("tile0")
    if not B or not T or not o:
        return None
    R, C = len(B), len(B[0])
    H = T["h"]

    def gh(r, c):
        x, z = o[0] + (c + 0.5) * 4, o[1] + (r + 0.5) * 4
        cc, rr = int(round((x - T["x0"]) / T["step"])), int(round((z - T["z0"]) / T["step"]))
        if 0 <= rr < len(H) and 0 <= cc < len(H[rr]):
            return H[rr][cc]
        return None
    G = [[gh(r, c) for c in range(C)] for r in range(R)]
    ev = set((r, c) for r in range(R) for c in range(C) if B[r][c] in "ws")

    def tile(x, z):
        c, r = int((x - o[0]) // 4), int((z - o[1]) // 4)
        return (r, c) if 0 <= r < R and 0 <= c < C else None
    for fr in (tl.get("frames") or [])[::3]:
        for e in fr["entities"]:
            if e.get("x") is not None and NAVAL_RE.search(str(e.get("bp", "")).lower()) and not str(e.get("bp", "")).startswith("building"):
                k = tile(e["x"], e["z"])
                if k:
                    ev.add(k)
    for sn in tl.get("nodes") or []:
        for n in sn["nodes"]:
            if n.get("x") is not None and re.search(r"fish|deep_water|shoreline", str(n.get("type", "")) + str(n.get("bp", ""))):
                k = tile(n["x"], n["z"])
                if k:
                    ev.add(k)
    if not ev:
        return None
    lid = _maxf(_maxf(G, WATER_R, max), WATER_R, min)
    flo = _maxf(G, 2, min)
    # owner 2026-11-12 ("kind of worked but some areas became collateral": dips inside an island joined the river): the page
    # picks the water itself from these per-tile values - "min depth" slider (lid - ground >= it), grown from the evidence
    # tiles through tiles that pass, so the threshold can be tuned per game without a rebuild
    dep = [[round(lid[r][c] - G[r][c], 1) if G[r][c] is not None and lid[r][c] is not None else 0 for c in range(C)] for r in range(R)]
    evm = [["0"] * C for _ in range(R)]
    for r, c in ev:
        evm[r][c] = "2" if B[r][c] in "ws" else "1"      # grid water / shallows (dump v14) count as water outright
    n = sum(1 for row in dep for v in row if v >= WATER_DEPTH)
    print(f"  water: {len(ev)} evidence tiles (grid water, naval units, fish); {n} tiles >= {WATER_DEPTH} m below the banks")
    return {"lid": [[round(v, 1) if v is not None else 0 for v in row] for row in lid],
            "dep": dep, "floor": [[round(v, 1) if v is not None else 0 for v in row] for row in flo],
            "ev": ["".join(row) for row in evm], "thr": WATER_DEPTH}


def camera_tracks(tl, replay):
    """player cameras (owner 2026-11-12: "can the 3d viewer show the player camera movements?"): the replay's camera records
    (replay.cameras: eye x / height / z, rotation, vertical fov) per player (slot matched by the starting TC, as on the 2D page)
    -> {p: [[t, eye x, eye y, eye z, fwd x, y, z, up x, y, z, fov, then the 4 ground corners x, z]]} in game coordinates;
    samples closer than 0.1 s and unchanged ones dropped. Corners from replay.footprint on the dump's terrain."""
    if not replay or not os.path.exists(replay):
        return None
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from replay import cameras, match_slots, footprint, terrain_fn, _rot
    cams = cameras(replay)
    slot2p, _, ground = match_slots(cams, tl)
    th = terrain_fn(tl.get("terrain"))
    if th:
        ground = th
    out = {}
    for sl, tr in cams.items():
        if sl not in slot2p:
            continue
        rows, last = [], None
        for r in tr:
            if len(r) < 9:
                continue
            q = r[4:8]
            n = math.sqrt(sum(v * v for v in q)) or 1
            q = [v / n for v in q]
            f, u = _rot(q, (0, 0, 1)), _rot(q, (0, 1, 0))
            fp = footprint(r, ground)
            row = [r[0], r[1], r[2], r[3], *[round(v, 3) for v in f], *[round(v, 3) for v in u], round(r[8], 1)]
            row += [round(v, 1) for c in fp[1] for v in c] if fp else []
            if last and (r[0] - last[0] < 0.1 or row[1:] == last[1:]):
                continue
            rows.append(row)
            last = row
        out[str(slot2p[sl])] = rows
    print(f"  cameras: {', '.join(f'P{p} {len(v)} samples' for p, v in out.items()) or 'none'}")
    return out or None


APM_STEP, APM_WIN = 2, 60


def apm_series(tl, replay):
    """APM / eAPM bars (owner 2026-11-15): replay.actions per player (slot matched by the starting TC, as for the cameras)
    -> {"step": 2, "win": 60, "p": {p: [[apm, eapm], ...]}, "cats": names, "acts": {p: [[tick, cat, effective], ...]}}, one sample every APM_STEP s from 0: the actions in the last
    APM_WIN s of game time (a per-minute rate; it ramps up over the first minute instead of guessing from a few seconds)."""
    if not replay or not os.path.exists(replay):
        return None
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from replay import actions, cameras, match_slots, APM_CATS
    slot2p = match_slots(cameras(replay), tl)[0]
    out, acts_out = {}, {}
    for sl, acts in actions(replay).items():
        if sl not in slot2p or not acts:
            continue
        rows, i, j, a, e = [], 0, 0, 0, 0     # acts[j:i] = the window
        end = int(acts[-1][0]) + APM_STEP
        for s in range(0, end + 1, APM_STEP):
            while i < len(acts) and acts[i][0] <= s:
                a += 1; e += acts[i][1]; i += 1
            while j < i and acts[j][0] <= s - APM_WIN:
                a -= 1; e -= acts[j][1]; j += 1
            rows.append([round(a * 60 / APM_WIN), round(e * 60 / APM_WIN)])
        out[str(slot2p[sl])] = rows
        acts_out[str(slot2p[sl])] = [[round(x[0] * 8), x[2], x[1]] for x in acts]       # [tick, category, effective]
    print("  apm: " + (", ".join(f"P{p} peak {max(r[0] for r in v)} / eAPM {max(r[1] for r in v)}" for p, v in out.items()) or "none"))
    return {"step": APM_STEP, "win": APM_WIN, "p": out, "cats": APM_CATS, "acts": acts_out} if out else None


def rally_points(F, replay, ui_of):
    """rally points (owner 2026-11-11): every rally command (replay types 12 / 22) of a building -> [t, building ui, x, z]
    (entity / squad targets at the target's position then)"""
    if not replay or not os.path.exists(replay):
        return None
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from replay import commands, receivers, data_of, target_of
    T = None
    out = []
    for tick, slot, typ, c in commands(replay):
        if typ not in (12, 22):
            continue
        try:
            rec, o = receivers(c)
            tg = target_of(*data_of(c, o))
        except Exception:  # noqa: BLE001 - a record this reader doesn't know
            continue
        if not tg:
            continue
        t = tick / 8.0
        for k, i in rec:
            if k == 1 and i in ui_of:
                if tg[0] == "pos":
                    out.append([round(t, 1), ui_of[i], round(tg[1], 1), round(tg[2], 1)])
                else:
                    out.append([round(t, 1), ui_of[i], tg[0][0], tg[1]])      # resolved in the page: "e" entity / "s" squad
    return out


NODE_RES = {"tree": ("wood", "trees"), "stealth": ("wood", "stealth forest"), "straggler": ("wood", "straggler tree"),
            "gold": ("gold", "gold"), "stone": ("stone", "stone"), "silver": ("gold", "silver"), "berry": ("food", "berries"),
            "deer": ("food", "deer"), "boar": ("food", "boar"), "sheep": ("food", "sheep"), "carcass": ("food", "carcass"),
            "fish": ("food", "fish"), "olive": ("food", "olives"), "relic": ("", "relic"), "site": ("", "sacred site")}


def bld_res(bp):
    """what a rally onto one of the player's own buildings means for new villagers"""
    b = bp.lower()
    if re.search(r"farm|paddy|rice|pasture", b) and "farmstead" not in b:
        return ("food", "farm")
    if re.search(r"econ_food|mill", b):
        return ("food", "mill")
    if re.search(r"econ_wood|lumber", b):
        return ("wood", "lumber camp")
    if re.search(r"mining|mine_camp", b):
        return ("", "mining camp")
    if "town_center" in b:
        return ("", "town center")
    return ("", re.sub(r"^(building|unit)_|_[a-z]{3}$|_ha_\w+$", "", b).replace("_", " "))


ORDER_NAMES = [(2, r"knight|horse|cavalry|lancer|camel|elephant|keshik|sipahi|scout|mangudai|kipchak|cataphract|ghulam|mounted"),
               (0, r"spear|manatarms|man_at_arms|serjeant|landsknecht|ronin|samurai|ghazi|limitanei|varangian|militia|warrior|axe|"
                  r"palace_guard|musofadi|donso|gilded"),
               (1, r"archer|crossbow|longbow|arbalet|handcannon|javelin|zhuge|repeater|musket|janissary|onna|yumi|grenadier|ozutsu"),
               (3, r"mangonel|springald|ram|trebuchet|bombard|cannon|culverin|ribauldequin|nest_of_bees|siege|tower")]


def army_order(bps):
    """(name words: cavalry first, so a gilded knight is cavalry) owner 2026-11-13: army row order from the middle outwards - melee infantry 0, ranged infantry 1, cavalry 2, siege 3, the rest
    (monks, traders ...) 4, ships 5 (own row, or the fifth part when the page's naval row is off); within a class units without gold first, then gold units, then by cost per unit (cheaper nearer
    the middle). Per unit blueprint [class, gold 0/1, cost]. Classes from aoe4world (units.json), else name words."""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    from gamedata import resolve
    try:
        U = json.load(open(os.path.join(ROOT, "data", "units.json"), encoding="utf-8"))["units"]
        C = json.load(open(os.path.join(ROOT, "data", "costs.json"), encoding="utf-8"))["costs"]
    except (OSError, ValueError, KeyError):
        U, C = {}, {}
    out = {}
    for bp in bps:
        if not bp.startswith("unit_") or "villager" in bp:
            continue
        cl = set((U.get(resolve(bp, U) or "") or {}).get("classes") or [])
        combat_monk = re.search(r"shaolin|warrior_monk", bp)
        naval = bp.startswith("unit_naval") or "naval_unit" in cl or "ship" in cl
        if naval:
            k = 5                   # owner 2026-11-13: ships get their own row under the production row (page toggle)
        elif not combat_monk and ("ship" in cl or "naval" in cl or "monk" in cl or "religious" in cl or "trade" in cl
                                or re.search(r"monk|prelate|imam|priest|scholar|dervish|pilgrim|trader|healer_|shaman", bp)):
            k = 4                   # owner 2026-11-13: the fifth (small) part - religious units and other non-combat units
        elif "cavalry" in cl:
            k = 2
        elif "siege" in cl:
            k = 3
        elif "ranged_infantry" in cl or ("infantry" in cl and "ranged" in cl):
            k = 1
        elif "melee_infantry" in cl or "infantry" in cl:
            k = 0
        else:
            k = next((n for n, rx in ORDER_NAMES if re.search(rx, bp)), 4)
        # sub-order (owner 2026-11-13): cavalry melee 0 before ranged 1; siege springalds 0, mangonels / nests of bees /
        # manjaniqs / cannons / culverins (and the rest) 1, rams / siege towers 2, catapults (trebuchets) 3
        sub = 0
        if k == 5:                  # warships, then transports, trade ships, fishing boats
            sub = 3 if ("naval_fishing_ship" in cl or "fishing" in bp) else 2 if ("naval_trade_ship" in cl or "trade" in bp) \
                else 1 if ("naval_transport" in cl or "transport" in bp) else 0
        elif k == 2 and ("ranged" in cl or re.search(r"archer|mangudai|ranged|gunner|tower", bp)):
            sub = 1
        elif k == 3:
            sub = 0 if "springald" in bp else 2 if re.search(r"_ram|ram_|siege_tower|tower_siege", bp) else \
                3 if re.search(r"trebuchet|catapult|huihui", bp) and "mangonel" not in bp else 1
        c = C.get(resolve(bp, C) or "") or {}
        tot = sum(float(c.get(r) or 0) for r in ("food", "wood", "gold", "stone", "oliveoil", "silver"))
        out[bp] = [k, sub, 1 if float(c.get("gold") or 0) > 0 else 0, round(tot)]
    return out


def unit_stats(F, tl, hud):
    """owner 2026-11-13 (selected units' stats): per player and unit blueprint index the stats with the upgrades completed by then
    (HUD tech rows; aoe4world effects through fightcal.stats / effects_of, the player's civ entry): rows [t, hp, damage, attack
    interval s, range tiles, melee armour, ranged armour, speed tiles/s, weapon type], a row only when something changed; plus
    the bonus damage per blueprint ("+17 vs cavalry"). Abilities / auras are not in these numbers (the box lists them apart)."""
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    import fightcal
    try:
        from techs_bought import civ_code
    except Exception:  # noqa: BLE001
        civ_code = None
    tech = (hud or {}).get("tech") or {}
    out, mods = {}, {}
    for pl in F.get("players") or []:
        p = pl["idx"]
        bis = sorted({u[2] for u in F["units"] if u[1] == p and str(F["bps"][u[2]]).startswith("unit_")})
        try:
            code = civ_code(tl, p) if civ_code and tl.get("players") else None
        except Exception:  # noqa: BLE001
            code = None
        done = sorted((r[0], r[1]) for r in tech.get(str(p)) or [] if r[0] is not None)
        rows = {}
        for t in [0.0] + [d[0] for d in done]:
            eff = fightcal.effects_of([a2 for t2, a2 in done if t2 <= t], code)
            for bi in bis:
                st = fightcal.stats(F["bps"][bi], eff)
                if not st:
                    continue
                r = [round(t, 1), round(st["hp"]), round(st["dmg"], 1), round(st["period"], 2), round(st["range"] / 4, 2),
                     round(st["marmor"], 1), round(st["rarmor"], 1), round(st["spd"] / 4, 3), st["type"]]
                L = rows.setdefault(str(bi), [])
                if not L or L[-1][1:] != r[1:]:
                    L.append(r)
                if str(bi) not in mods:
                    mods[str(bi)] = ", ".join(f"+{v:g} vs " + " / ".join(" ".join(g) for g in grp) for grp, v in st.get("mods") or [])
        out[str(p)] = rows
    return out, {k: v for k, v in mods.items() if v}


def rally_info(F, tl, rally, ui_of):
    """owner 2026-11-13 ("can the build order show what it is rallying to?"): per D.rally row [resource, label] - entity targets
    by what they are (own building / unit, map object by its node type), positions by the nearest map object (8) / own building
    footprint / own sheep (6), squad targets: a recorded unit squad, else a sheep (player sheep are recorded without squads:
    the early Town Center rallies onto 5007x squads)"""
    if not rally:
        return None
    snaps = tl.get("nodes") or []
    st = [x["t"] for x in snaps]
    node_type = {}
    for x in snaps:
        for n in x["nodes"]:
            node_type.setdefault(n["id"], n["type"])
    frames = tl.get("frames") or []
    ft = [f["t"] for f in frames]
    squad_bp = {}
    for f in frames:
        for e in f["entities"]:
            if e.get("squad") and e["squad"] not in squad_bp:
                squad_bp[e["squad"]] = e["bp"]
    def frame_at(t):
        i = bisect.bisect_right(ft, t) - 1
        return frames[max(0, i)] if frames else None
    def node_at(t, x, z, r=8.0):
        i = bisect.bisect_right(st, t) - 1
        if i < 0:
            return None
        best, bd = None, r * r
        for n in snaps[i]["nodes"]:
            if n.get("x") is None or (n.get("left") is not None and n["left"] <= 0):
                continue
            d = (n["x"] - x) ** 2 + (n["z"] - z) ** 2
            if d < bd:
                best, bd = n["type"], d
        return best
    tiles = F.get("tiles") or []
    out = []
    for r in rally:
        t, bui = r[0], r[1]
        owner = F["units"][bui][1]
        res, lab = "", "ground"
        if r[2] == "s":
            bp = squad_bp.get(r[3])
            if bp:
                res, lab = ("", "villager") if "villager" in bp else ("", re.sub(r"^unit_|_\d.*$", "", bp).replace("_", " "))
            else:
                fr = frame_at(t)
                own_sheep = fr and any(o[1] == owner for o in (fr.get("sheep_o") or []))
                res, lab = ("food", "sheep") if own_sheep else ("", "unit")
        elif r[2] == "e":
            ui = ui_of.get(r[3])
            if ui is not None:
                bp = F["bps"][F["units"][ui][2]]
                res, lab = bld_res(bp) if bp.startswith("building") else ("", "villager" if "villager" in bp else bp)
            else:
                ty = node_type.get(r[3])
                res, lab = NODE_RES.get(ty, ("", ty or "object"))
        else:
            x, z = r[2], r[3]
            ty = node_at(t, x, z)
            if ty:
                res, lab = NODE_RES.get(ty, ("", ty))
            else:
                fr = frame_at(t)
                hit = None
                for e in (fr["entities"] if fr else []):
                    if e["owner"] != owner or not e["bp"].startswith("building") or e["x"] is None:
                        continue
                    bi = F["bps"].index(e["bp"]) if e["bp"] in F["bps"] else -1
                    half = ((tiles[bi] if 0 <= bi < len(tiles) and tiles[bi] else 2) * 2) + 2
                    if abs(e["x"] - x) <= half and abs(e["z"] - z) <= half:
                        hit = e["bp"]
                        break
                if hit:
                    res, lab = bld_res(hit)
                elif fr and any(o[1] == owner and (o[2] - x) ** 2 + (o[3] - z) ** 2 < 36 for o in (fr.get("sheep_o") or [])):
                    res, lab = "food", "sheep"
        out.append([res, lab])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fights", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--mine-shapes", action="store_true", help="gold / stone deposits as rock shapes instead of the game's models")
    ap.add_argument("--mirror-models", action="store_true", help="treat the exported models as glTF (right-handed) space and mirror them into game space")
    ap.add_argument("--levels", default="best", choices=["best", "all"],
                    help="best = one detail level per mesh; all = every exported file (levels stacked: flicker, larger page)")
    ap.add_argument("--probe", help="a part name: list its exported files (meshes, triangles, box) and what is used")
    ap.add_argument("--models", default=os.path.join(ROOT, "models"))
    ap.add_argument("--detail", default="light", choices=["light", "medium", "heavy"],
                    help="light: Gen7 meshes, flat colours (models/parts); medium: game textures on the lowest detail level; "
                         "heavy: game textures on the full detail meshes (both from models/parts_heavy: "
                         "tools/game_assets.py export-parts --detail heavy)")
    ap.add_argument("--basics", help="work/<name>.basics.json: gathered / army value series for the graph at the bottom")
    ap.add_argument("--replay", help="the replay file: rally points")
    ap.add_argument("--hud", help="work/<name>.hud.json (analyzer/hud.py): the observer bar, stats and fight recaps")
    ap.add_argument("--timeline", help="work/<name>.timeline.json: the game's own visibility flags and the players' ages "
                                       "(fog of war per player, age colours); without it: Everything only")
    a = ap.parse_args()
    globals()["LEVELS"] = a.levels
    globals()["MINE_SHAPES"] = a.mine_shapes
    globals()["MIRROR_MODELS"] = a.mirror_models
    globals()["RIGHT"] = -1 if a.mirror_models else 1
    if a.probe:
        DETAIL_ = a.detail
        globals()["DETAIL"] = DETAIL_
        probe(os.path.join(a.models, "parts" if DETAIL_ == "light" else "parts_heavy"), a.probe)
        return
    F = json.load(open(a.fights, encoding="utf-8"))
    global DETAIL
    DETAIL = a.detail
    pdir = os.path.join(a.models, "parts" if a.detail == "light" else "parts_heavy")
    um_path = os.path.join(a.models, "unit_models.json")
    UM = json.load(open(um_path, encoding="utf-8"))["units"] if os.path.exists(um_path) else {}
    # owner 2026-11-11: "some of the model selections are bad, can I choose them manually?" - models/model_overrides.json
    # (yours, local): {"<blueprint>": "<other blueprint>"} = draw it with that one's model, or {"<blueprint>": {"body": ...,
    # "weapon": ..., "extra": [...], "pieces": ...}} = replace those fields (part names as in models/unit_models.json "parts";
    # the .models.txt report lists what each blueprint uses now)
    ov_path = os.path.join(a.models, "model_overrides.json")
    overridden = set()
    if os.path.exists(ov_path):
        try:
            OV = json.load(open(ov_path, encoding="utf-8"))
        except ValueError as e:
            print(f"  model_overrides.json not read: {e}")
            OV = {}
        for k, v in OV.items():
            if k.startswith("_"):
                continue
            k = k.lower()
            if isinstance(v, str):
                if v.lower() in UM:
                    UM[k] = UM[v.lower()]
                    overridden.add(k)
                else:
                    print(f"  model_overrides: {v} has no model entry (for {k})")
            elif isinstance(v, dict):
                UM[k] = dict(UM.get(k) or {}, **v)
                overridden.add(k)
        if overridden:
            print(f"  model_overrides: {len(overridden)} blueprints")
    have_parts = os.path.isdir(pdir)
    meshes, mlist, types, type_of, missing = {}, [], {}, {}, set()
    report = []           # why a blueprint has no model (owner 2026-11-11: buildings / gates missing)

    def mesh_index(ms):
        """a list of meshes (one per texture) -> list of indices"""
        out = []
        for m in ms or []:
            mlist.append(pack_mesh(m, len(mlist)))
            out.append(len(mlist) - 1)
        return out

    bps = F["bps"]
    globals()["CHARGERS"] = chargers(bps)            # knights ...: lance while charging, barding on the horse
    used = sorted({u[2] for u in F["units"]})
    sys.path.insert(0, os.path.join(ROOT, "analyzer"))
    try:
        import fightcal
    except Exception:  # noqa: BLE001 - motions fall back to defaults
        fightcal = None
    combat = {}
    for bi in used:
        bp = bps[bi].lower()
        if fightcal and not bp.startswith("building"):
            try:
                st = fightcal.stats(bps[bi])
            except Exception:  # noqa: BLE001
                st = None
            if st:
                combat[str(bi)] = {"period": round(st["period"], 3), "lead": round(st["lead"], 3),
                                   "range": round(st["range"], 2), "melee": st["melee"], "cav": st["cav"],
                                   "spd": round(st["spd"], 2), "base": st["base"]}
        if not have_parts:
            continue
        spec = UM.get(bp) or UM.get(re.sub(r"_ha_\w+$", "", bp)) or None
        if "gate" in bp and "landmark" not in bp:      # owner 2026-11-11: gates read as overlapping wall pieces - drawn with their wall's model
            wall = next((UM[w] for w in (bp.replace("_gate", ""), re.sub(r"gate_?", "", bp)) if w in UM), None)
            spec = wall or spec
        if spec is None:
            missing.add(bp)
            report.append(f"{bp}: no entry in unit_models.json")
            continue
        key = json.dumps(spec, sort_keys=True)
        if key not in types:
            try:
                A = assemble(pdir, spec)
            except (OSError, ValueError, KeyError, struct.error, ZeroDivisionError) as e:
                print(f"  {bp}: {e}")
                A = None
            if A:
                body_name = (spec.get("body") or "").lower()
                horse = not re.search(r"camel|elephant", body_name)
                charger = bi in CHARGERS
                types[key] = {"bard": mesh_index(barding(A["mountRaw"])) if charger and horse and A.get("mountRaw") else [],
                              "lance": mesh_index(A.get("lance")) if charger else [],
                              "armour": mesh_index(A.get("armour")), "deck": A.get("deck"),
                              "body": mesh_index(A["body"]), "head": mesh_index(A.get("head")),
                              "legs": mesh_index(A.get("legs")), "mount": mesh_index(A["mount"]),
                              "weapon": mesh_index(A["weapon"]), "hand": [-A["hand"][0], A["hand"][1], A["hand"][2]] if MIRROR_MODELS else A["hand"], "kind": A["kind"],
                              "lift": A["lift"], "building": bool(A.get("building")), "ext": ([-A["ext"][1], -A["ext"][0], A["ext"][2], A["ext"][3]] if MIRROR_MODELS and A.get("ext") else A.get("ext")), "top": A.get("top"),
                              "mountKind": "camel" if "camel" in body_name else "elephant" if "elephant" in body_name
                              else "horse"}
            else:
                types[key] = None
        if types[key]:
            type_of[bi] = key
            report.append(f"{bp}: model {spec.get('body')}" + (f" + {spec.get('extra')}" if spec.get("extra") else "")
                          + (" (override)" if bp in overridden else ""))
        else:
            missing.add(bp)
            files = {n: sum(1 for f in os.listdir(pdir) if f.lower().startswith(n.lower() + ".")) for n in
                     [spec.get("body")] + (spec.get("extra") or []) if n}
            report.append(f"{bp}: parts {files} (0 = not exported to {os.path.basename(pdir)})")
    fogd = fog_data(F, a.timeline, bps, a.replay)
    fogd["bpal"] = {str(bi): building_palette(bps[bi]) for bi in used if bps[bi].lower().startswith("building")}
    ui_of = fogd.pop("_ui_of", {u[0]: i for i, u in enumerate(F["units"])})
    fogd["techRows"] = tech_rows(F)
    fogd["armyOrder"] = army_order(bps)
    fogd["techIcons"] = F.get("techIcons")
    try:
        fogd["rally"] = rally_points(F, a.replay, ui_of)
        fogd["rallyInfo"] = rally_info(F, load_tl(a.timeline), fogd["rally"], ui_of)
    except Exception as e:  # noqa: BLE001 - the page builds without rally points
        print(f"  rally points skipped: {type(e).__name__}: {e}")
        fogd["rally"] = None
    try:
        fogd["water"] = water_map(F, load_tl(a.timeline))
    except Exception as e:  # noqa: BLE001 - the page falls back to the grid's water tiles
        print(f"  water skipped: {type(e).__name__}: {e}")
        fogd["water"] = None
    try:
        fogd["cams"] = camera_tracks(load_tl(a.timeline), a.replay)
    except Exception as e:  # noqa: BLE001 - the page builds without cameras
        print(f"  cameras skipped: {type(e).__name__}: {e}")
        fogd["cams"] = None
    try:
        fogd["apm"] = apm_series(load_tl(a.timeline), a.replay)
    except Exception as e:  # noqa: BLE001 - the page builds without the APM bars
        print(f"  apm skipped: {type(e).__name__}: {e}")
        fogd["apm"] = None
    if a.hud and os.path.exists(a.hud):
        fogd["hud"] = json.load(open(a.hud, encoding="utf-8"))
    try:
        fogd["ustats"], fogd["umods"] = unit_stats(F, load_tl(a.timeline), fogd.get("hud"))
    except Exception as e:  # noqa: BLE001 - the selection box shows names only
        print(f"  unit stats skipped: {type(e).__name__}: {e}")
        fogd["ustats"], fogd["umods"] = None, None
    if a.basics and os.path.exists(a.basics):
        B = json.load(open(a.basics, encoding="utf-8"))
        fogd["series"] = {p: [[r[0], r[1], r[3]] + ([[r[8].get(k, 0) for k in ("food", "wood", "gold", "stone")]] if len(r) > 8 else [])
                               for r in v.get("series", [])] for p, v in B.get("players", {}).items()}
    node_mesh = {}                               # node blueprint index -> mesh (game model of the tree / mine / animal)
    global SIMPLE
    if have_parts:
        for ni, nb in enumerate(fogd.get("nodeBps") or []):
            spec = UM.get(nb.lower())
            # --mine-shapes: gold / stone deposits as the page's rock clusters instead of the game's models
            if MINE_SHAPES and re.match(r"resource_(gold|stone)", nb.lower()):
                continue
            if spec and spec.get("prop"):
                # owner 2026-11-12: trees back to the detailed reading (the chopped stages); other map objects (mines,
                # berries, animals) the map-object pick (tallest stage of each piece)
                SIMPLE = not re.search(r"tree|forest|stealth|straggler", nb.lower())
                try:
                    A = assemble(pdir, dict(spec, building=True))
                except (OSError, ValueError, KeyError, struct.error, ZeroDivisionError):
                    A = None
                SIMPLE = False
                if A:
                    # the building roof / wall split (light detail) moved every upward-facing top into "head", which map
                    # objects never drew - the deposits' rock tops were missing (hollow rings / shells in the owner's
                    # screenshots), likewise canopy tops: body + head together
                    node_mesh[str(ni)] = mesh_index(merge((A["body"] or []) + (A.get("head") or [])))
    SIMPLE = False
    fogd["nodeMesh"] = node_mesh
    tkeys = sorted(k for k in types if types[k])
    D = {"players": F["players"], "bps": bps, "names": F.get("names"), "units": F["units"], "tracks": tracks(F),
         "terrain": F.get("terrain"), "blocked": F.get("blocked"), "tile0": F.get("tile0"), "bounds": F.get("bounds"),
         "tiles": [t if t else (build_tiles(b) if b.lower().startswith("building") else None)
                   for t, b in zip(F.get("tiles") or [None] * len(bps), bps)],
         "nodes": [{"t": s["t"], "n": [[n[0], round(n[1], 1), round(n[2], 1)] for n in s["n"]]} for s in F.get("nodes", [])],
         "deaths": F.get("deaths"), "fights": [{k: f.get(k) for k in ("n", "start", "end", "x", "z", "r")} for f in F["fights"]],
         "meshes": mlist, "types": [types[k] for k in tkeys], "typeOf": {str(b): tkeys.index(k) for b, k in type_of.items()},
         "combat": combat, "images": IMAGES, "detail": a.detail, "icons": F.get("icons"), "crew": crew_of(bps, UM)}
    D.update(fogd)
    tpl = open(os.path.join(HERE, "view3d.html"), encoding="utf-8").read()
    hud_js = open(os.path.join(HERE, "hud.js"), encoding="utf-8").read().replace("</", "<\\/")
    tpl = tpl.replace("/*__HUD_JS__*/", hud_js, 1)
    html = tpl.replace("/*__DATA__*/null", json.dumps(D, separators=(",", ":")).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    nb = sum(1 for k in tkeys if types[k]["building"])
    n_of = {}
    for u in F["units"]:
        n_of[bps[u[2]]] = n_of.get(bps[u[2]], 0) + 1
    rp = os.path.splitext(a.out)[0] + ".models.txt"
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write(f"detail {a.detail}, parts from {pdir}\n")
        for line in sorted(report):
            fh.write(f"{n_of.get(line.split(':')[0], 0):4d} x {line}\n")
    if a.detail != "light" and missing and any(len(x) == 3 for x in
                                               {(UM.get(b.lower()) or {}).get("body", "_").split("_")[0] for b in missing}):
        pre = sorted({(UM.get(b.lower()) or {}).get("body", "_").split("_")[0] for b in missing} - {"", "None"})
        print(f"  no heavy parts for art prefixes {pre}: python tools/game_assets.py export-parts --detail heavy --civs "
              + ",".join(p for p in pre if len(p) == 3))
    print(f"  why some blueprints have no model: {rp}")
    print(f"  3d: {a.out} ({os.path.getsize(a.out) // 1024} KB; {len(tkeys) - nb} unit models, {nb} building models, "
          f"{len(node_mesh)} map-object models"
          + (f", plain shapes for {len(missing)}: {', '.join(sorted(missing)[:6])}" if missing else "")
          + ("" if have_parts else "; no models/parts - run tools/game_assets.py export-parts") + ")")


if __name__ == "__main__":
    main()
