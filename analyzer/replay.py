"""Read an AoE4 replay file (the playback-folder file, or its .gz download).

Layout: a header with two Relic Chunky blocks, then the command stream:
  record = u32 type, u32 length, body; type 0 = one tick:
    body: u8 ?, u32 tick, u32 ?, u32 n_bundles, then n_bundles x (u32 slot, u32 ?, u32 len, data)
    data = commands: u16 length, u8 type, payload
Ticks run at 8 per second.

Command header (24 bytes; layout from github.com/BigManJohn000/aoe4-replay-viewer docs/rec-record-types.md,
checked here on test5): u16 length, u8 type, u8 player index | 0x80 when shift-queued, ..., u32 player id @20.
Receivers @24: 0x80 + u8 n + n x u32 LE; or 0x40|n + n x u32 LE; or one u32 BE. Each id = kind << 28 | index:
kind 1 entity (index + 1000005000), kind 2 squad (index + 50000 = the dump's squad id).
Then u8 data type, u8 length (0x80: a u8 length follows), data. Data type 1/3/6 hold a target:
u8 kind (2 position f32 x, y, z; 3 entity id; 4 squad id).

Used command types:
  153 (0x99) player camera: sample tick u32 @27, eye x / y / z int32 cm @31, rotation quaternion w, x, y, z
      as i16 / 16384 @43, vertical FOV x 100 u16 @51
  orders: ORDER_TYPES below
"""
import gzip
import re
import math
import struct

TICKS_PER_S = 8.0
ENTITY_BASE = 1000005000
SQUAD_BASE = 50000
ORDER_TYPES = {0x3e: "move", 0x43: "attack", 0x47: "attack-move", 0x69: "gather", 0x41: "build",
               0x42: "capture", 0x49: "garrison", 0x4c: "unload", 0x74: "patrol", 0x16: "attack",
               0x3f: "stop", 0x6d: "hold"}
MAGIC = b"Relic Chunky\r\n\x1a\x00"


def _walk(b, off, end):
    while off + 20 <= end:
        typ = b[off:off + 4]
        if typ not in (b"FOLD", b"DATA"):
            return off
        _, ln, nl = struct.unpack_from("<III", b, off + 8)
        body = off + 20 + nl
        if typ == b"FOLD":
            _walk(b, body, body + ln)
        off = body + ln
    return off


def stream_start(b):
    pos, end = b.find(MAGIC), 0
    while pos >= 0:
        end = _walk(b, pos + 24, len(b))
        pos = b.find(MAGIC, end)
    return end


def _read(path):
    with open(path, "rb") as fh:
        b = fh.read()
    return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b


def info(path):
    """{"build": game build the replay was made on, "duration": seconds (last tick / 8)}."""
    b = _read(path)
    build = struct.unpack_from("<H", b, 2)[0]
    off, last = stream_start(b), 0
    while off + 8 <= len(b):
        typ, ln = struct.unpack_from("<II", b, off)
        if typ == 0 and ln >= 5:
            last = struct.unpack_from("<I", b, off + 9)[0]
        off += 8 + ln
    return {"build": build, "duration": last / TICKS_PER_S}


_NAME_CIV = re.compile(rb"\x01([\x01-\x40])\x00\x00\x00((?:[\s\S][\s\S]){1,64}?)[\s\S]{8}\x01([\x02-\x40])\x00\x00\x00([a-z][a-z0-9_]{1,63})")
_DIGITS16 = re.compile(rb"((?:[0-9]\x00){6,24})")


def players(path):
    """the players in the replay header (owner 2026-11-01: a player who changes name stays the same person):
    [{"slot", "name", "civ", "steam", "profile"}] in the header's order (= the game's player 1, 2, ...).
    steam: the Steam ID string stored after the civ (absent for players without one); profile: the u32 nine bytes
    before that ID's length (the Relic / aoe4world profile number, by its value - check against aoe4world).
    Also the game's date and map when present (date, map). Header layout found on replay_258000890."""
    b = _read(path)
    head = b[:0x4000]
    out = []
    for m in _NAME_CIV.finditer(head):
        n = m.group(1)[0]
        raw = m.group(2)
        if len(raw) != 2 * n:
            continue
        try:
            name = raw.decode("utf-16le")
        except UnicodeDecodeError:
            continue
        if not name.strip() or any(ord(c) < 32 for c in name):
            continue
        civ = m.group(4).decode()
        rec = {"slot": len(out) + 1, "name": name, "civ": civ, "steam": None, "profile": None, "at": m.start()}
        d = _DIGITS16.search(head, m.end(), m.end() + 400)
        if d:
            ln_pos = d.start() - 4
            ln = struct.unpack_from("<I", head, ln_pos)[0] if ln_pos >= 0 else 0
            sid = d.group(1).decode("utf-16le")
            if ln == len(sid):
                rec["steam"] = sid
                if ln_pos - 9 >= 0:
                    rec["profile"] = struct.unpack_from("<I", head, ln_pos - 9)[0]
        out.append(rec)
    return out


def header(path):
    """{"date": as stored (UTF-16 at the start), "map": map name, "players": players(path)}"""
    b = _read(path)
    head = b[:0x2000]
    date = None
    m = re.search(rb"((?:[0-9/:. \-]\x00){8,40})", head[:0x80])
    if m:
        date = m.group(1).decode("utf-16le").strip()
    mm = re.search(rb"map_size_\d+\x00{0,8}[\s\S]{0,8}?([a-z][a-z0-9_]{2,40})", head)
    return {"date": date, "map": mm.group(1).decode() if mm else None, "players": players(path),
            "build": struct.unpack_from("<H", b, 2)[0]}


def commands(path):
    b = _read(path)
    off = stream_start(b)
    while off + 8 <= len(b):
        typ, ln = struct.unpack_from("<II", b, off)
        body = b[off + 8: off + 8 + ln]
        off += 8 + ln
        if typ != 0 or len(body) < 13:
            continue
        tick = struct.unpack_from("<I", body, 1)[0]
        n = struct.unpack_from("<I", body, 9)[0]
        p = 13
        for _ in range(n):
            slot, _, l = struct.unpack_from("<III", body, p)
            p += 12
            d = body[p:p + l]
            p += l
            q = 0
            while q + 3 <= len(d):
                cl = struct.unpack_from("<H", d, q)[0]
                if cl < 3:
                    break
                yield tick, slot, d[q + 2], d[q:q + cl]
                q += cl


def receivers(c):
    """[(kind, full id)]: kind 1 entity id, 2 squad id (as the dump reports them), 0 player."""
    o = 24
    if c[o] == 0x80:
        n, o = c[o + 1], o + 2
        ids = struct.unpack_from(f"<{n}I", c, o)
        o += 4 * n
    elif c[o] & 0x40:
        n, o = c[o] & 0x3F, o + 1
        ids = struct.unpack_from(f"<{n}I", c, o)
        o += 4 * n
    else:
        ids = struct.unpack_from(">I", c, o)
        o += 4
    out = []
    for i in ids:
        k, n = i >> 28, i & 0x0FFFFFFF
        out.append((k, n + (ENTITY_BASE if k == 1 else SQUAD_BASE if k == 2 else 0)))
    return out, o


def data_of(c, o):
    """(data type, data) at offset o (after the receivers)."""
    if o >= len(c):
        return None, b""
    dt = c[o]
    if dt == 0xFF:
        return dt, b""
    n, o = c[o + 1], o + 2
    if n == 0x80:
        n, o = c[o], o + 1
    return dt, c[o:o + n]


def target_of(dt, d):
    """("pos", x, z) / ("entity", id) / ("squad", id) / None."""
    if dt == 6:
        d = d[4:]
    elif dt not in (1, 3):
        return None
    if not d:
        return None
    if d[0] == 2 and len(d) >= 13:
        x, _, z = struct.unpack_from("<fff", d, 1)
        return ("pos", round(x, 1), round(z, 1))
    if d[0] in (3, 4) and len(d) >= 5:
        return ("entity" if d[0] == 3 else "squad", struct.unpack_from("<I", d, 1)[0])
    return None


def orders(path):
    """Unit orders: [{t, slot, type, shift, squads, entities, target}], in game order."""
    out = []
    for tick, slot, typ, c in commands(path):
        if typ not in ORDER_TYPES or len(c) < 29:
            continue
        rec, o = receivers(c)
        dt, d = data_of(c, o)
        out.append({"t": round(tick / TICKS_PER_S, 2), "slot": slot, "type": ORDER_TYPES[typ],
                    "shift": bool(c[3] & 0x80),
                    "squads": [i for k, i in rec if k == 2], "entities": [i for k, i in rec if k == 1],
                    "target": target_of(dt, d)})
    return out


# ability commands (owner 2026-11-11: palings, volley, stances, ...): types 0x0e (entity receivers) / 0x48 (squad
# receivers); data type 36 = 01 + u32 ability PBG, 37 / 42 add a target at data offset 10 / 6 (u8 kind: 2 position
# f32 x y z, 3 entity, 4 squad). Layout per github.com/BigManJohn000/aoe4-replay-viewer docs/rec-record-types.md.
# 0x72 = stop ability (toggles off). Names: data/abilities.json (aoe4world, by PBG id). Player-clicked only - auto-cast
# abilities are not commands (dump v12 A4D|AB has those).
ABILITY_TYPES = {0x0e: "cast", 0x48: "cast", 0x72: "stop"}


def abilities(path):
    """[{t, slot, kind: cast / stop, pbg, squads, entities, target}] in game order"""
    out = []
    for tick, slot, typ, c in commands(path):
        kind = ABILITY_TYPES.get(typ)
        if kind is None or len(c) < 29:
            continue
        try:
            rec, o = receivers(c)
            dt, d = data_of(c, o)
        except struct.error:
            continue
        pbg, target = None, None
        if dt in (36, 37, 42) and len(d) >= 5:
            pbg = struct.unpack_from("<I", d, 1)[0]
            off = 6 if dt == 42 else 10
            if dt != 36 and len(d) >= off + 5:
                k = d[off]
                if k == 2 and len(d) >= off + 13:
                    x, _, z = struct.unpack_from("<fff", d, off + 1)
                    target = ("pos", round(x, 1), round(z, 1))
                elif k in (3, 4):
                    target = ("entity" if k == 3 else "squad", struct.unpack_from("<I", d, off + 1)[0])
        out.append({"t": round(tick / TICKS_PER_S, 2), "slot": slot, "kind": kind, "pbg": pbg,
                    "squads": [i for k_, i in rec if k_ == 2], "entities": [i for k_, i in rec if k_ == 1],
                    "target": target})
    return out


# every command sent to units or buildings, by category, for highlighting the receivers (owner 2026-10-25:
# "highlight what they issued something to"). Types beyond ORDER_TYPES identified on test5: 3 / 16 queue
# production or research at a building (blueprint in the data), 5 cancel a queue slot, 12 / 22 rally /
# building target. Selection itself is not in the file; the receivers of a command are what was selected then.
ACT_TYPES = {3: "queue", 16: "queue", 5: "cancel", 12: "rally", 22: "rally"}
NOT_ACTS = {146, 148, 153, 154}      # camera and per-tick records


def acts(path):
    """[{t, slot, cat, squads, entities}] for every command with receivers."""
    out = []
    for tick, slot, typ, c in commands(path):
        if typ in NOT_ACTS or len(c) < 29:
            continue
        try:
            rec, _ = receivers(c)
        except (IndexError, ValueError, struct.error):
            continue
        sq = [i for k, i in rec if k == 2]
        en = [i for k, i in rec if k == 1]
        if not sq and not en:
            continue
        cat = ORDER_TYPES.get(typ) or ACT_TYPES.get(typ) or "other"
        if cat in ("attack-move",):
            cat = "attack"
        out.append({"t": round(tick / TICKS_PER_S, 2), "slot": slot, "cat": cat, "squads": sq, "entities": en})
    return out


# queue commands (owner 2026-11-12: "record both the clicked events and the completed events"): type 3 (unit) / 16 (research)
# at a building, data type 21 = 01 + u32 PBG id of what was queued (+ u16 game player id + 4 bytes); one command per item
# (a shift-click batch of 5 = 5 commands); type 5 cancels a slot (data 04 + u32 slot / item number, meaning unchecked).
# PBG ids -> data/pbgids.json (tools/update_data.py, aoe4world). Checked on replay 259818624 (20 research clicks, building
# ids = the dump's executers).
_PBG = None


def pbg_names():
    global _PBG
    if _PBG is None:
        import json
        import os
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pbgids.json"), encoding="utf-8") as fh:
                _PBG = json.load(fh)["pbgids"]
        except (OSError, ValueError, KeyError):
            _PBG = {}
    return _PBG


def queues(path):
    """[{t, slot, kind: "unit" / "tech" / "cancel", pbg, attrib (None if unknown), building, index}] in game order"""
    names = pbg_names()
    out = []
    for tick, slot, typ, c in commands(path):
        if typ not in (3, 16, 5) or len(c) < 29:
            continue
        try:
            rec, o = receivers(c)
        except (IndexError, ValueError, struct.error):
            continue
        b = next((i for k, i in rec if k == 1), None)
        dt, d = data_of(c, o)
        row = {"t": round(tick / TICKS_PER_S, 2), "slot": slot, "building": b, "pbg": None, "attrib": None, "index": None}
        if typ == 5:
            if len(d) >= 5:
                row["index"] = struct.unpack_from("<I", d, 1)[0]
            row["kind"] = "cancel"
        else:
            if dt != 21 or len(d) < 5 or d[0] != 1:
                continue
            pbg = struct.unpack_from("<I", d, 1)[0]
            nm = names.get(str(pbg))
            row.update(pbg=pbg, attrib=nm[1] if nm else None,
                       kind=nm[0] if nm and nm[0] in ("unit", "tech") else ("tech" if typ == 16 else "unit"))
        out.append(row)
    return out


# APM (owner 2026-11-15). Not counted: 0x99 camera, 0x9a (exactly 30 / min for every player: a heartbeat).
# 0x92 ... 0x94 (owner 2026-11-18): the client wraps each order click (right-click, or the click that ends a hotkey order)
# in this pair, with the order(s) the click turned into inside (none when it led to nothing): one action per pair, its
# category from the first order inside ("unit other" when empty). Commands outside a pair count one each.
APM_SKIP = {0x99, 0x9a}
APM_OPEN, APM_CLOSE = 0x92, 0x94
APM_ATTACK = {0x43, 0x47, 0x16}     # attack / attack-move / attack (focus): breaks a move-spam run
APM_SPAM_S = 2.0
# Categories (owner 2026-11-15): first by who receives the order - squads = units, entities = buildings, only the player =
# unknown (except 0x7b building placement -> build) - then by command type. Outside a pair, one ability use sent to several
# squads (one record each, same tick) is one action.
APM_CATS = ["move", "attack-move", "focus", "gather", "build", "ability", "unit other",
            "rally", "queue", "research", "building other", "unknown"]
_UNIT_CAT = {0x3e: "move", 0x47: "attack-move", 0x43: "focus", 0x16: "focus", 0x69: "gather", 0x41: "build",
             0x48: "ability", 0x0e: "ability", 0x72: "ability"}
_BLD_CAT = {0x0c: "rally", 0x16: "rally", 0x03: "queue", 0x10: "research"}
_ABILITY = {0x0e, 0x48, 0x72}


def _apm_cat(typ, c, rec, o):
    kinds = {k for k, _ in rec or ()}
    if 2 in kinds:
        return _UNIT_CAT.get(typ, "unit other")
    if 1 in kinds:
        cat = _BLD_CAT.get(typ, "building other")
        if typ in (0x03, 0x10):             # queue vs research by the PBG's kind (a tech can be queued with type 3)
            dt, d = data_of(c, o)
            if dt == 21 and len(d) >= 5 and d[0] == 1:
                nm = pbg_names().get(str(struct.unpack_from("<I", d, 1)[0]))
                if nm and nm[0] in ("unit", "tech"):
                    cat = "queue" if nm[0] == "unit" else "research"
        return cat
    if typ == 0x7b:     # place a building: player-only receiver, builders + PBG in the data (owner 2026-11-18)
        return "build"
    return "unknown"


def actions(path):
    """{slot: [[t, effective, category index], ...]} every counted action in game order (APM_CATS): one per 0x92 ... 0x94
    pair (at the 0x92) and one per command outside a pair. effective = 0 for move spam: a ground move (0x3e to a position)
    by the same player to the same units within APM_SPAM_S of their previous ground move, with no attack / attack-move /
    focus command by that player in between (owner 2026-11-15); a pair is spam only when every order in it is (an empty
    pair is effective)."""
    out, last, seen, open_ = {}, {}, set(), {}

    def close(slot):
        t, inner = open_.pop(slot)
        cat = inner[0][1] if inner else APM_CATS.index("unit other")
        out.setdefault(slot, []).append([t, 1 if not inner or any(e for e, _ in inner) else 0, cat])

    for tick, slot, typ, c in commands(path):
        if typ in APM_SKIP:
            continue
        t, eff = tick / TICKS_PER_S, 1
        if typ == APM_OPEN:
            if slot in open_:
                close(slot)
            open_[slot] = (t, [])
            continue
        if typ == APM_CLOSE:
            if slot in open_:
                close(slot)
            continue
        try:
            rec, o = receivers(c)
        except Exception:  # noqa: BLE001 - a record this reader doesn't know counts as unknown
            rec, o = None, len(c)
        if typ in _ABILITY:             # one record per squad: the same ability (PBG) in the same tick = one use
            try:
                dt, d = data_of(c, o)
                pbg = struct.unpack_from("<I", d, 1)[0] if dt in (36, 37, 42) and len(d) >= 5 else None
            except Exception:  # noqa: BLE001
                pbg = None
            key = (slot, tick, typ, pbg)
            if key in seen:
                continue
            seen.add(key)
        if typ in APM_ATTACK:
            last.pop(slot, None)
        elif typ == 0x3e and rec:
            try:
                tg = target_of(*data_of(c, o))
            except Exception:  # noqa: BLE001
                tg = None
            if tg and tg[0] == "pos":
                key = frozenset(i for _, i in rec)
                pv = last.get(slot)
                if pv and pv[1] == key and t - pv[0] <= APM_SPAM_S:
                    eff = 0
                last[slot] = (t, key)
        row = (eff, APM_CATS.index(_apm_cat(typ, c, rec, o)))
        if slot in open_:
            open_[slot][1].append(row)
        else:
            out.setdefault(slot, []).append([t, *row])
    for slot in list(open_):
        close(slot)
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def cameras(path):
    """{slot: [[t, x, height, z, qw, qx, qy, qz, fov]]} in dump coordinates (eye position, metres)."""
    out = {}
    for tick, slot, typ, c in commands(path):
        if typ == 153 and len(c) >= 43:
            x, h, z = (v / 100.0 for v in struct.unpack_from("<iii", c, 31))
            row = [round(tick / TICKS_PER_S, 2), round(x, 1), round(h, 1), round(z, 1)]
            if len(c) >= 53:
                w, qx, qy, qz, fov = struct.unpack_from("<4hH", c, 43)
                row += [w / 16384, qx / 16384, qy / 16384, qz / 16384, fov / 100]
            out.setdefault(slot, []).append(row)
    return out


def _rot(q, v):
    w, x, y, z = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


def footprint(row, ground=0.0, aspect=16 / 9, far=400.0):
    """Ground seen by a camera sample: (centre, [4 corners]) as (x, z), rays cut where they meet the plane
    y = ground (or at `far` metres). 16:9 screen assumed, FOV taken as the vertical angle. None without rotation.
    ground: a height, or a function (x, z) -> terrain height; then the plane is the terrain height at the view
    centre (found in two passes, as the centre depends on it)."""
    if callable(ground):
        h = ground(row[1], row[3])
        c = footprint(row, h, aspect, far)
        if c is None:
            return None
        return footprint(row, ground(*c[0]), aspect, far)
    if len(row) < 9:
        return None
    _, x, y, z, *q, fov = row
    n = math.sqrt(sum(v * v for v in q)) or 1
    q = [v / n for v in q]
    f, u, r = _rot(q, (0, 0, 1)), _rot(q, (0, 1, 0)), _rot(q, (1, 0, 0))
    tv = math.tan(math.radians(fov) / 2)
    th = tv * aspect

    def hit(a, b):
        d = [f[i] + a * th * r[i] + b * tv * u[i] for i in range(3)]
        k = min(far, (y - ground) / -d[1]) if d[1] < -1e-3 else far
        return (x + d[0] * k, z + d[2] * k)
    return hit(0, 0), [hit(-1, -1), hit(1, -1), hit(1, 1), hit(-1, 1)]


def terrain_fn(T):
    """Height at (x, z) from the dump's terrain grid (nearest cell), or None without one."""
    if not T or not T.get("h"):
        return None

    def h(x, z):
        c = min(max(int(round((x - T["x0"]) / T["step"])), 0), T["cols"] - 1)
        r = min(max(int(round((z - T["z0"]) / T["step"])), 0), T["rows"] - 1)
        row = T["h"][r] or []
        v = row[c] if c < len(row) else None
        return v if v is not None else 0.0
    return h


def match_slots(cams, tl):
    """Replay slot -> dump player: the player whose starting Town Center is nearest the slot's
    first camera. Also fitted from the same 0:00 views (each camera looks at its own Town Center):
    k, look-at = camera + k * height on both axes (fallback for samples without rotation), and
    ground, the plane height that puts the rotated view centre on the Town Center (17 in test5)."""
    tcs = {}
    for e in tl["frames"][0]["entities"]:
        if "town_center" in (e["bp"] or "") and e["x"] is not None and "dummy" not in e["bp"]:
            tcs.setdefault(e["owner"], (e["x"], e["z"]))
    slot2p, ks, gs = {}, [], []
    for slot, track in cams.items():
        row = track[0]
        _, x, h, z = row[:4]
        p = min(tcs, key=lambda q: (tcs[q][0] - x) ** 2 + (tcs[q][1] - z) ** 2) if tcs else None
        if p is None:
            continue
        slot2p[slot] = p
        tx, tz = tcs[p]
        if h > 0:
            ks.append(((tx - x) / h + (tz - z) / h) / 2)
        if len(row) >= 9:
            err = lambda g: (lambda c: (c[0] - tx) ** 2 + (c[1] - tz) ** 2)(footprint(row, g)[0])
            gs.append(min((g / 2 for g in range(-200, 200)), key=err))
    k = sum(ks) / len(ks) if ks else 0.0
    ground = sorted(gs)[len(gs) // 2] if gs else 0.0
    return slot2p, k, ground
