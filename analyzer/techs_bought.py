"""What each player researched, from the dump's upgrade events (GE_UpgradeComplete): review only.

The game reports the completion; the cost was paid when research started. Start, best first (owner 2026-11-12:
"record both the clicked events and the completed events"; completion is what matters, the start shows when it was
being researched): dump v19 GE_UpgradeStart ("event"), the building's queue head turning to it (dump v18 Q lines,
"queue", ~1 s), else completion minus the research time in data/upgrades.json ("estimated"; aoe4world technologies +
unit-tier upgrades, by attribName; Delhi's scholar speed-up and free techs make that one wrong). The click =
the replay's queue command (tl["queueCmds"] from replay.queues(), set by the caller that has the replay file).
Age-ups are left out (the landmark is counted already). Upgrades with no data entry are listed with
cost None.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# game civ name -> aoe4world civ code
CIV_CODE = {"abbasid": "ab", "abbasid_ha_01": "ay", "byzantine": "by", "byzantine_ha_mac": "mac",
            "chinese": "ch", "chinese_ha_01": "zx", "english": "en", "lancaster": "hl", "french": "fr",
            "french_ha_01": "je", "hre": "hr", "hre_ha_01": "od", "japanese": "ja", "japanese_ha_sen": "sen",
            "malian": "ma", "mongol": "mo", "mongol_ha_gol": "gol", "ottoman": "ot", "rus": "ru",
            "sultanate": "de", "sultanate_ha_tug": "tug", "templar": "kt", "jin": "jin"}
AGE_UPS = ("feudal_age", "castle_age", "imperial_age")
_CODES = {}
UNKNOWN_CIVS = set()


def civ_code(tl, p):
    """aoe4world civ code of player p: the game's civ name in CIV_CODE, else (a civ added in a patch: owner
    2026-11-01) the civ most of the player's first units / buildings belong to in data/units.json + costs.json"""
    pl = next(x for x in tl["players"] if x["idx"] == p)
    if pl["civ"] in CIV_CODE:
        return CIV_CODE[pl["civ"]]
    key = (id(tl), p)
    if key not in _CODES:
        with open(os.path.join(HERE, "..", "data", "units.json"), encoding="utf-8") as fh:
            U = json.load(fh)["units"]
        n = {}
        for fr in tl["frames"][:30]:
            for e in fr["entities"]:
                if e["owner"] == p and e["bp"] in U:
                    for c in U[e["bp"]].get("civs") or []:
                        n[c] = n.get(c, 0) + 1
        _CODES[key] = max(n, key=n.get) if n else None
        UNKNOWN_CIVS.add((pl["civ"], _CODES[key]))
    return _CODES[key]
RES = ("food", "wood", "stone", "gold")


def load_upgrades():
    with open(os.path.join(HERE, "..", "data", "upgrades.json"), encoding="utf-8") as fh:
        return json.load(fh)["upgrades"]


def _entry(name, code, table):
    from gamedata import canon_attrib
    v = table.get(name) or table.get(canon_attrib(name, table) or "")
    if not v:
        return None
    return next((e for e in v if code in e["civs"]), v[0])


def player_ids(tl, owner=None):
    """the game's player ids (p1003, ...) -> player index, from kill events naming a victim entity and its owner"""
    if owner is None:
        owner = {}
        for fr in tl["frames"]:
            for e in fr["entities"]:
                if e["id"] is not None and e["owner"]:
                    owner.setdefault(e["id"], e["owner"])
    pid = {}
    for ev in tl.get("events") or []:
        v, vo = ev.get("victim") or "", ev.get("victimOwner") or ""
        if v[:1] == "e" and v[1:].isdigit() and vo[:1] == "p" and vo not in pid and int(v[1:]) in owner:
            pid[vo] = owner[int(v[1:])]
    return pid


def _bare(u):
    return u[1:] if u.startswith("b") else u


def techs_bought(tl, table=None, clicks_out=None):
    """{player: [{"t": paid, "done": t, "how": event / queue / estimated, "exact", "click": t or None, "name", "attrib",
    "gold", "cost" (all resources) or None}]}. clicks_out (dict): filled with {player: [{t, attrib, name, building,
    done or None}]} - every research click, None = never completed (cancelled or not reached)."""
    table = table or load_upgrades()
    owner = {}
    for fr in tl["frames"]:
        for e in fr["entities"]:
            if e["id"] is not None and e["owner"]:
                owner.setdefault(e["id"], e["owner"])
    civ = {p["idx"]: p["civ"] for p in tl["players"]}
    out = {p["idx"]: [] for p in tl["players"]}
    pid = player_ids(tl, owner)
    # dump v18 GE_UpgradeStart: the real research start (queued, paid); the latest unused start of the same attrib (and
    # executer when both name one) before the completion
    starts = {}
    for ev in tl.get("events") or []:
        if ev.get("type") == "upgrade_start":
            u = ev.get("upgrade") or ""
            starts.setdefault(u[1:] if u.startswith("b") else u, []).append([ev["t"], ev.get("executer") or "", False])
    # dump v18 Q lines: building id -> [[t, size, type, bp]]; a start = the head turning to that upgrade
    qstarts = {}
    for bid, rows in (tl.get("queueHead") or {}).items():
        prev = None
        for r in rows:
            if r[2] == "upgrade" and r[3] and r[3] != prev:
                qstarts.setdefault((int(bid), r[3]), []).append([r[0], False])
            prev = r[3] if r[2] == "upgrade" else None
    # replay research clicks: [t, building, attrib or None, used, done]
    clicks = [[c["t"], c["building"], c.get("attrib"), False, None] for c in (tl.get("queueCmds") or []) if c.get("kind") == "tech"]
    for ev in tl.get("events") or []:
        if ev.get("type") != "upgrade":
            continue
        name = (ev.get("upgrade") or "")[1:]          # dump tags blueprints with a leading "b"
        ex = ev.get("executer") or ""
        # player-level upgrades (executer p####: Ottoman vizier picks, age-ups) - the player id from kill events
        # (victim e... with victimOwner p...; owner 2026-11-11 otto1 / chn1 / zxl1 logs)
        p = (pid.get(ex) if ex.startswith("p") else owner.get(int(ex[1:]))) if ex[1:].isdigit() else None
        if p not in out or name in AGE_UPS:
            continue
        e = _entry(name, civ_code(tl, p), table)
        t0, exact, how = round(ev["t"] - (e["time"] if e else 0), 1), False, "estimated"
        bid = int(ex[1:]) if ex.startswith("e") and ex[1:].isdigit() else None
        cand = [x for x in starts.get(name, []) if not x[2] and x[0] <= ev["t"] and (not x[1] or not ex or x[1] == ex)]
        qc = [x for x in qstarts.get((bid, name), []) if not x[1] and x[0] <= ev["t"] + 0.5]
        if cand:
            c = max(cand, key=lambda x: x[0])
            c[2], t0, exact, how = True, round(c[0], 1), True, "event"
        elif qc:
            c = max(qc, key=lambda x: x[0])
            c[1], t0, exact, how = True, round(min(c[0], ev["t"]), 1), True, "queue"
        # the click: the latest unused one of this upgrade at this building up to the start (unknown PBG ids at the
        # same building as a fallback: merc contracts / landmark techs missing from aoe4world)
        ck = None
        for named in (True, False):
            cc = [x for x in clicks if not x[3] and x[1] == bid and x[0] <= t0 + 1.0
                  and ((x[2] == name) if named else x[2] is None)]
            if cc:
                ck = max(cc, key=lambda x: x[0])
                ck[3], ck[4] = True, ev["t"]
                break
        if ck is not None and how == "estimated" and ck[0] > t0:
            t0 = round(ck[0], 1)                       # it cannot have started before it was clicked
        elif ck is not None and how == "queue" and 0 <= t0 - ck[0] <= 1.05:
            t0 = round(ck[0], 2)                       # idle building: it started at the click (the Q line is 1 s coarse)
        out[p].append({"t": t0, "exact": exact, "how": how, "click": ck[0] if ck else None, "done": ev["t"], "attrib": name,
                       "name": e["name"] if e else name.replace("upgrade_", "").replace("_", " "),
                       "gold": e["gold"] if e else None,
                       "cost": sum(e[r] for r in RES) if e else None,
                       "res": {r: e[r] for r in RES} if e else None})
    for v in out.values():
        v.sort(key=lambda x: x["t"])
    if clicks_out is not None:
        for p in out:
            clicks_out[p] = []
        for t, b, at, used, done in clicks:
            p = owner.get(b)
            if p not in clicks_out:
                continue
            e = _entry(at, civ_code(tl, p), table) if at else None
            clicks_out[p].append({"t": t, "attrib": at, "name": e["name"] if e else at, "building": b,
                                  "done": done})
    return out
