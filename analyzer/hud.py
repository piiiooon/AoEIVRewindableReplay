"""Observer HUD data (owner 2026-11-11: the in-game caster bar as the layout; both the replay viewer and the 3D page;
full values for both players in every view - the owner's choice for this bar).

    python hud.py work/<name>.analyzed.json work/<name>.hud.json [--fights work/<name>.fights.json]

Per player every STEP s: bank and gathering rate per resource (gathered over the last 60 s, per minute), villagers per
resource and idle, pop / cap, age, villager / military counts, production buildings working (queue > 0) per blueprint,
landmarks under construction (progress), and running totals: idle villager-seconds, villager-seconds, gathered, army
value, enemy villagers killed, enemy value destroyed. Plus the upgrade rows (economy / military / other, stages) and,
with --fights, a recap per fight (value / units lost, losses per unit type, damage per unit type).
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from analyze import load_costs  # noqa: E402
from basics import per_player, RES, SUPPORT  # noqa: E402
from fights import find_deaths  # noqa: E402
from gamedata import is_crew, resolve  # noqa: E402

STEP = 2.0          # seconds between rows
RATE_WIN = 60.0     # gathering rate window (s)

MIL_RE = re.compile(r"unit_|armor|weapon|melee|ranged|siege|infantry|cavalry|archer|knight|spear|ballist|gunpowder|"
                    r"wedge|riveted|damascus|chainmail|plate|banded|outpost|tower|keep|wall|palisade|"
                    r"fletching|bodkin|incendiar|chemistry|greased|roller|crossbar|elite|veteran|hardened|"
                    r"military|naval|ship|arrow|bow|blade|lance|charge|horse|camel|elephant|gun|cannon|bombard", re.I)


ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
FAM_RE = re.compile(r"^(.+?)_(\d|i{1,3}|iv)(?:_(?:sul|ha|[a-z]{2,4}|\d+)(?:_[a-z0-9]+)*)?$")


def _family(at):
    """(stem, stage) of an upgrade attrib: trailing _N or (owner 2026-11-11: blacksmith tiers as in game) _i / _ii / _iii,
    a civ suffix after it ignored (upgrade_melee_damage_ii_sul_ha_tug); (attrib, 0) when not part of a family"""
    m = FAM_RE.match(at)
    if not m:
        return at, 0
    g = m.group(2)
    return m.group(1), int(g) if g.isdigit() else ROMAN[g]


def _stage_info(ups, civ=None):
    """family stem -> sorted stage numbers known in upgrades.json for that civ (entries' civs list; eco harvest families are
    2 / 3 / 4: no dark-age stage; Japanese alone have a 4th blacksmith melee tier)"""
    stems = {}
    for at, L in ups.items():
        st, n = _family(at)
        if n and civ and isinstance(L, list) and not any(civ in (e.get("civs") or []) for e in L):
            continue
        if n:
            stems.setdefault(st, set()).add(n)
    return {k: sorted(v) for k, v in stems.items()}


ALL_ST = None


def veterancy(at, name):
    """owner 2026-11-11: unit veterancy upgrades (Upgrade to Hardened / Veteran / Elite, tier 2-4 unit upgrades) are left
    out of the upgrade rows"""
    if re.match(r"upgrade to\b", name or "", re.I):
        return True
    st, n = _family(at)
    return st.startswith("upgrade_unit_") and n >= 2 and not re.search(r"religious|town_center|wheelbarrow", st)


def _up_entry(ups, at, civ):
    L = ups.get(at) or []
    if isinstance(L, dict):
        L = [L]
    for e in L:
        if civ and civ in (e.get("civs") or []):
            return e
    return L[0] if L else None


def _effects_text(e):
    out = []
    for f in (e or {}).get("effects") or []:
        sel = f.get("select") or {}
        who = ", ".join((sel.get("id") or []) + [" ".join(c) if isinstance(c, list) else str(c) for c in (sel.get("class") or [])])
        v = f.get("value")
        v = round(v, 3) if isinstance(v, float) else v
        op = {"multiply": "x", "change": "+" if (v or 0) >= 0 else "", "add": "+" if (v or 0) >= 0 else ""}.get(f.get("effect"), f.get("effect", "") + " ")
        out.append(f"{f.get('property')} {op}{v}" + (f" ({who})" if who else ""))
    return out


def _civs(tl):
    try:
        from techs_bought import civ_code
        return {str(pl["idx"]): civ_code(tl, pl["idx"]) for pl in (tl.get("players") or [])}
    except Exception:  # noqa: BLE001 - civ only picks the entry's research time
        return {}


def tech_rows(techs, civs=None):
    """upgrades per player (owner 2026-11-11): row 0 economy, 1 military, 2 unsure; a family (attrib without its trailing _N)
    is one icon with notches = the stages known in upgrades.json (count, not the highest number: the eco harvest families
    are _2 / _3 / _4 = 3 notches). Owner 2026-11-11: research in progress shown too - start = done - research time (the
    entry's time for the player's civ; civ speed bonuses not applied, so an estimate); hover = detail text.
    techs = export_fights techs_list: {p: [[done, attrib, name, mil]]}
    row = [done, attrib, name, row, stem, stage index (1..n, 0 = no family), stages n, start or None, detail, short label,
           start how ("event" dump v19 / "queue" dump v18 queue head / "" estimated), click time (replay) or None]
    data/tech_notes.json (owner-written, tools/tech_notes.py): name / short / desc / from for upgrades without data"""
    try:
        ups = json.load(open(os.path.join(HERE, "..", "data", "upgrades.json"), encoding="utf-8"))["upgrades"]
    except (OSError, ValueError, KeyError):
        ups = {}
    try:            # owner's descriptions for upgrades the game data has no entry / icon for (tools/tech_notes.py)
        notes = json.load(open(os.path.join(HERE, "..", "data", "tech_notes.json"), encoding="utf-8"))
    except (OSError, ValueError):
        notes = {}
    out = {}
    for p, lst in (techs or {}).items():
        civ = (civs or {}).get(str(p))
        stems, stems_all = _stage_info(ups, civ), ALL_ST if ALL_ST else _stage_info(ups)
        rows = []
        for tr in lst:
            done, at, name, mil = tr[:4]
            real0 = tr[4] if len(tr) > 4 else None        # dump v19 GE_UpgradeStart / v18 queue head
            how = (tr[5] if len(tr) > 5 else "event") if real0 is not None else ""
            click = tr[6] if len(tr) > 6 else None
            from gamedata import canon_attrib
            ca = canon_attrib(at, ups) or at
            if veterancy(ca, name):
                continue
            stem, stage = _family(ca)
            known = stems.get(stem) or stems_all.get(stem) or ([stage] if stage else [])
            idx = (known.index(stage) + 1 if stage in known else len([s for s in known if s <= stage])) if stage else 0
            row = 0 if not mil else 1 if MIL_RE.search(at) else 2
            e = _up_entry(ups, ca, civ)
            rt = float(e.get("time") or 0) if e else 0.0
            start = real0 if real0 is not None else round(max(0.0, done - rt), 1) if rt > 0 else None
            nt = notes.get(at) or notes.get(ca) or {}
            if nt.get("name"):
                name = nt["name"]
            det = [name or at]
            if nt.get("desc"):
                det.append(nt["desc"])
            if nt.get("from"):
                det.append("from: " + nt["from"])
            if not e and not nt.get("desc"):
                det.append("not in the game data (a landmark / civ bonus?) - describe it in data/tech_notes.json")
            if e:
                cost = " / ".join(f"{int(e.get(k) or 0)} {k}" for k in ("food", "wood", "gold", "stone") if e.get(k))
                det.append((cost + " · " if cost else "") + (f"{int(rt)} s research" if rt else ""))
                det += _effects_text(e)
            if stage and len(known) > 1:
                det.append(f"stage {idx} of {len(known)}")
            mm = lambda v: f"{int(v // 60)}:{int(v % 60):02d}"  # noqa: E731
            det.append(" · ".join(x for x in (f"clicked {mm(click)}" if click is not None else "",
                                              f"started {mm(start)} ({'recorded' if how == 'event' else 'queue' if how else 'estimated'})"
                                              if start is not None else "", f"done {mm(done)}") if x))
            det.append(at)
            rows.append([round(done, 1), at, name, row, stem, idx, len(known) if stage else 0, start, "\n".join(d for d in det if d),
                         nt.get("short") or "", how, click])
        out[str(p)] = rows
    return out


# dump v8 RT_* types that are not gathered resources (owner's logs 2026-11-11: Action, Begin, Command, Popcap, Count,
# Militia_HRE showed up as "2 0/min" cells)
NOT_RES = {"action", "begin", "command", "popcap", "count", "militia_hre"}
REACH_N = 9.0        # a gathering villager works the nearest node of its kind within this (gold / stone + 6)
FARM_N = 7.0         # ... or the farm within this
LIVE_STEP = 2.0      # s per step of the live fight recap (owner 2026-11-11)
QUEUE_LOOK = 180.0   # s ahead to find the units a queue turned into
SPAWN_R = 22.0       # a new unit within this of a producing building came out of it
BUILD_R = 13.0       # villagers standing (no gather / move flag) within this of a landmark build it
DYNASTY = {1: "Song", 2: "Yuan", 3: "Ming"}   # both landmarks of an age (aoe4world: Chinese, Zhu Xi's Legacy)


def _spawns(frames, pids):
    """{building id: [(t, unit bp)]}: each new military unit (not at the start) credited to the nearest producing
    building of its owner (queue > 0 in this or the last frame) within SPAWN_R"""
    out, seen, prevq = {}, {e["id"] for e in frames[0]["entities"]}, {}
    for fr in frames:
        prodb = {}
        for e in fr["entities"]:
            if e["kind"] == "o" and e["x"] is not None and ((e.get("queue") or 0) > 0 or prevq.get(e["id"])):
                prodb.setdefault(e["owner"], []).append(e)
        for e in fr["entities"]:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            if e["kind"] != "m" or e["x"] is None:
                continue
            best = min(prodb.get(e["owner"], []), key=lambda b: (b["x"] - e["x"]) ** 2 + (b["z"] - e["z"]) ** 2, default=None)
            if best and (best["x"] - e["x"]) ** 2 + (best["z"] - e["z"]) ** 2 <= SPAWN_R ** 2:
                out.setdefault(best["id"], []).append((fr["t"], e["bp"]))
        prevq = {e["id"]: (e.get("queue") or 0) > 0 for e in fr["entities"] if e["kind"] == "o"}
    return out


def _dynasties(tl, pids):
    """Chinese / Zhu Xi's Legacy (owner 2026-11-11): Tang from the start, then the game's own dynasty events
    (chn1: upgrade player_dynasty1_chi = Song; 2 Yuan, 3 Ming) -> {p: [(t, name)]}"""
    from techs_bought import techs_bought
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError):
        bought = {}
    civ = {p["idx"]: (p.get("civ") or "") for p in tl["players"]}
    out = {}
    for p in pids:
        ev = [(x["done"], DYNASTY.get(int(m.group(1)), "dynasty " + m.group(1)))
              for x in bought.get(p, []) for m in [re.search(r"player_dynasty(\d)", x["attrib"])] if m]
        if ev or "chinese" in civ[p] or "zhu" in civ[p]:
            out[p] = [(0.0, "Tang")] + sorted(ev)
    return out


def hud(tl, costs_full, cost_of):
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    per, cancelled, _ = per_player(tl, costs_full, cost_of)
    deaths = [d for d in find_deaths(frames, cost_of, tl.get("events")) if d["id"] not in cancelled]
    # resources beyond the four (dump v8: olive oil, silver, ...) when a player ever banks or earns them
    extra = []
    for fr in frames:
        for pl in fr["players"].values():
            for k, (b, r) in (pl.get("res") or {}).items():
                if k not in RES and k not in extra and k not in NOT_RES and ((b or 0) > 0 or (r or 0) > 0):
                    extra.append(k)
    res = list(RES) + extra
    fi = {fr["t"]: fr for fr in frames}
    out = {"res": res, "step": STEP, "players": [{"idx": p["idx"], "name": p["name"], "civ": p["civ"]} for p in tl["players"]],
           "rows": {}}
    spawns = _spawns(frames, pids)
    dyn = _dynasties(tl, pids)
    lm_name = lambda bp: (costs_full.get(resolve(bp, costs_full) or "") or {}).get("name") or bp  # noqa: E731
    # Ottoman vizier (owner 2026-11-11; game scripts: unspent points = RT_Command, experience = state model
    # imperial_council_exp_ott, points so far = total_viziers_ott - dump v11): [unspent, points so far, experience]
    civ_of = {p["idx"]: (p.get("civ") or "") for p in tl["players"]}

    def viz(pl, p):
        if "ottoman" not in civ_of[p]:
            return None
        cmd = ((pl.get("res") or {}).get("command") or [None])[0]
        sm = pl.get("sm") or {}
        return [None if cmd is None else round(cmd), sm.get("total_viziers_ott"), sm.get("imperial_council_exp_ott")]

    # building progress (dump v11 A4D|ES: UI_Progress of landmarks / military schools / the Jiangnan Tower; owner 2026-11-11)
    esm = {int(k): v for k, v in (tl.get("esm") or {}).items()}
    bown = {}
    for fr in frames[::10]:
        for e in fr["entities"]:
            if e["id"] in esm and e["id"] not in bown:
                bown[e["id"]] = (e["owner"], e["bp"])

    # what the villagers work on (owner 2026-11-11: hover on a resource): food = farm / berry / deer / boar / sheep / fish /
    # carcass; wood = tree / stealth forest / straggler; gold / stone = large / small deposit - the nearest node of that kind
    # within REACH_N (farms FARM_N) of the gathering villager; nodes from the latest snapshot (trees: the latest full one)
    snaps = tl.get("nodes") or []
    grids = {}

    def node_grid(t, full):
        idx = -1
        for i_, sn in enumerate(snaps):
            if sn["t"] > t:
                break
            if sn["full"] or not full:
                idx = i_
        if idx < 0:
            return {}
        key = (idx, full)
        if key not in grids:
            g = {}
            for n in snaps[idx]["nodes"]:
                if n["x"] is None or (n.get("left") is not None and n["left"] <= 0):
                    continue
                g.setdefault((int(n["x"] // 16), int(n["z"] // 16)), []).append(n)
            grids[key] = g
            if len(grids) > 8:
                grids.pop(next(iter(grids)))
        return grids[key]

    def nearest(g, x, z, r, ok):
        best, bd = None, r * r
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for n in g.get((int(x // 16) + dx, int(z // 16) + dz), ()):
                    d = (n["x"] - x) ** 2 + (n["z"] - z) ** 2
                    if d <= bd and ok(n):
                        best, bd = n, d
        return best

    FOODT = {"berry": "berry", "deer": "deer", "boar": "boar", "sheep": "sheep", "fish": "fish", "carcass": "carcass"}

    def sources(fr, p, t):
        gl, gf = node_grid(t, False), node_grid(t, True)
        farms = [(e["x"], e["z"]) for e in fr["entities"] if e["owner"] == p and e["x"] is not None
                 and (e["bp"] or "").startswith("building_resource_farm")]
        out_ = {"food": {}, "wood": {}, "gold": {}, "stone": {}}
        garr = 0
        for e in fr["entities"]:
            if e["owner"] != p or e["kind"] != "w" or e["x"] is None:
                continue
            fl = e.get("flags") or ""
            if "H" in fl:
                garr += 1
            r_ = {1: "food", 2: "wood", 3: "gold", 4: "stone"}.get(e.get("res"))
            if not r_:
                continue
            x, z = e["x"], e["z"]
            k_ = "other"
            if r_ == "food":
                if any((fx - x) ** 2 + (fz - z) ** 2 <= FARM_N ** 2 for fx, fz in farms):
                    k_ = "farm"
                else:
                    n = nearest(gl, x, z, REACH_N, lambda n: n["type"] in FOODT)
                    if n:
                        k_ = FOODT[n["type"]]
                    elif any((sh[2] - x) ** 2 + (sh[3] - z) ** 2 <= REACH_N ** 2 for sh in fr.get("sheep_o", [])):
                        k_ = "sheep"
                    elif "fish" in (e["bp"] or ""):
                        k_ = "fish"
            elif r_ == "wood":
                n = nearest(gf, x, z, REACH_N, lambda n: n["type"] in ("tree", "stealth", "straggler"))
                k_ = {"tree": "trees", "stealth": "stealth forest", "straggler": "straggler tree"}.get(n["type"]) if n else "other"
            else:
                n = nearest(gl, x, z, REACH_N + 6, lambda n: n["type"] == r_)
                k_ = ("small deposit" if "small" in n["bp"] else "large deposit") if n else "other"
            out_[r_][k_] = out_[r_].get(k_, 0) + 1
        return [{k: sorted(v.items(), key=lambda x: -x[1]) for k, v in out_.items() if v}, garr]

    def progs(p, t):
        out_ = []
        for i, L in esm.items():
            if bown.get(i, (None,))[0] != p:
                continue
            cur = None
            for t0, vals in L:
                if t0 > t:
                    break
                cur = vals
            if cur and isinstance(cur.get("UI_Progress"), (int, float)):
                out_.append([bown[i][1], i, round(cur["UI_Progress"], 3), cur.get("jiangnan_tower_unit_index")])
        return out_

    for p in pids:
        R = per[p]["rows"]
        rows, nxt = [], -1e9
        idle_s = vil_s = garr_s = 0.0
        prev_t = None
        j = 0
        for i, r in enumerate(R):
            t = r["t"]
            if prev_t is not None:
                dt = t - prev_t
                idle_s += r["idle"] * dt
                vil_s += r["nvil"] * dt
            prev_t = t
            if t < nxt:
                continue
            nxt = t + STEP
            while R[j]["t"] < t - RATE_WIN:
                j += 1
            dtw = t - R[j]["t"]
            fr = fi[t]
            pl = fr["players"].get(str(p)) or fr["players"].get(p) or {}
            xr = pl.get("res") or {}
            bank = [round(r["bank"][k]) for k in RES] + [round((xr.get(k) or [0, 0])[0] or 0) for k in extra]
            rate = [round((r["gathered"][k] - R[j]["gathered"][k]) / dtw * 60) if dtw > 0 else 0 for k in RES]
            rate += [round(((xr.get(k) or [0, 0])[1] or 0)) for k in extra]
            vil = [r["vil"][k] for k in RES] + [0] * len(extra)
            nmil = 0
            prod, lms, mq = {}, [], {}
            aby, acost = {}, [0.0, 0.0, 0.0, 0.0]
            # builders: the dump has no construct flag on villagers - standing (not gathering / moving / idle) next to it
            vpos = [(e["x"], e["z"]) for e in fr["entities"] if e["owner"] == p and e["kind"] == "w" and e["x"] is not None
                    and not any(c in (e.get("flags") or "") for c in "FWGSMH") and not e.get("idle")]
            for e in fr["entities"]:
                if e["owner"] != p:
                    continue
                if e["kind"] == "m":
                    nmil += 1
                    if not any(w in (e["bp"] or "") for w in SUPPORT) and not is_crew(e["bp"]):   # army (basics._is_army); crew ride their elephant
                        v = aby.setdefault(e["bp"], [0, 0.0])
                        v[0] += 1
                        v[1] += cost_of(e["bp"])
                        c = costs_full.get(resolve(e["bp"], costs_full) or "") or {}
                        for ri, rn in enumerate(RES):
                            acost[ri] += float(c.get(rn) or 0)
                elif e["kind"] == "o":
                    if (e.get("queue") or 0) > 0 and (e.get("build") is None or e["build"] >= 1):
                        prod[e["bp"]] = prod.get(e["bp"], 0) + 1
                        # military in the queue (hindsight): the next queue-size units that came out of this building
                        q = int(e["queue"])
                        for st, ubp in [x for x in spawns.get(e["id"], []) if t < x[0] <= t + QUEUE_LOOK][:q]:
                            mq[ubp] = mq.get(ubp, 0) + 1
                    if ("landmark" in e["bp"] or "wonder" in e["bp"]) and e.get("build") is not None and e["build"] < 1 \
                            and e["id"] not in cancelled:
                        nb = sum(1 for x, z in vpos if e["x"] is not None and (x - e["x"]) ** 2 + (z - e["z"]) ** 2 <= BUILD_R ** 2)
                        lms.append([e["bp"], round(e["build"], 3), nb, lm_name(e["bp"])])
            kills = [d for d in deaths if d["owner"] != p and d["t"] <= t]
            rows.append([round(t, 1), bank, rate, vil, r["idle"], r["pop"], pl.get("popcap"), r["age"], r["nvil"], nmil,
                         sorted(prod.items(), key=lambda x: -x[1]), lms, round(idle_s), round(vil_s),
                         round(sum(r["gathered"].values())), round(r["army"]),
                         sum(1 for d in kills if d["kind"] == "w"), round(sum(d["cost"] or 0 for d in kills)),
                         sorted(mq.items(), key=lambda x: -x[1]), next((n for t0, n in reversed(dyn.get(p, [])) if t0 <= t), None),
                         sorted([[k_, v[0], round(v[1])] for k_, v in aby.items()], key=lambda x: -x[2]), [round(x) for x in acost],
                         viz(pl, p), progs(p, t), *sources(fr, p, t)])
            garr_s += rows[-1][25] * STEP
            rows[-1].append(round(garr_s))
            # army produced per minute over the last RATE_WIN s (replenishment; owner 2026-11-11) - col 27
            rows[-1].append(round((r["cat"]["army"] - R[j]["cat"]["army"]) / dtw * 60) if dtw > 0 else 0)
        out["rows"][str(p)] = rows
    # landmarks per player (owner 2026-11-11: in the bar, click = jump to it): placed / finished / gone, position;
    # main TC (Templar: the age-up flags point to it)
    lm, last_t, tc = {}, frames[-1]["t"], {}
    for fr in frames:
        for e in fr["entities"]:
            bp = e["bp"] or ""
            if e["kind"] != "o" or e["x"] is None:
                continue
            if "town_center" in bp and e["owner"] not in tc:
                tc[e["owner"]] = [e["id"], round(e["x"], 1), round(e["z"], 1)]
            if ("landmark" not in bp and "wonder" not in bp) or e["id"] in cancelled:
                continue
            L = lm.setdefault(e["id"], {"p": e["owner"], "bp": bp, "t0": fr["t"], "done": None, "last": fr["t"],
                                        "x": round(e["x"], 1), "z": round(e["z"], 1)})
            L["last"] = fr["t"]
            if L["done"] is None and (e.get("build") is None or e["build"] >= 1):
                L["done"] = fr["t"]
    out["landmarks"] = {}
    for i, L in sorted(lm.items(), key=lambda x: x[1]["t0"]):
        out["landmarks"].setdefault(str(L["p"]), []).append(
            [L["t0"], L["done"], L["last"] if L["last"] < last_t - 2 else None, L["bp"], i, L["x"], L["z"], lm_name(L["bp"])])
    # vizier ring scale (owner's otto2, dump v11): experience resets at each new point - threshold of point k = experience
    # before + the usual step - experience after (otto2: ~58, ~94); later points use the last one seen
    out["vizThr"] = {}
    for p, R in out["rows"].items():
        th, prev, steps = [], None, []
        for r in R:
            v = r[22]
            if v and prev and v[2] is not None and prev[2] is not None:
                if v[1] is not None and prev[1] is not None and v[1] > prev[1]:
                    th.append([v[1], prev[2], v[2]])
                elif v[2] > prev[2]:
                    steps.append(v[2] - prev[2])
            prev = v
        if th:
            st = sorted(steps)[len(steps) // 2] if steps else 0
            out["vizThr"][p] = [round(b + st - a_) for k, b, a_ in th]
    out["mainTC"] = {str(p): v for p, v in tc.items()}
    # sacred sites (owner 2026-11-12: circles between the centre box and the army row): dump v19+ strategic points, holy /
    # sacred sites only (trade posts are not captured); per site its position and the state track as recorded (on change):
    # [t, owner (player index, 0 none), [capture progress per player], [has a capturing unit near, per player]]
    out["sites"] = []
    info = tl.get("siteInfo") or {}
    pos = {}
    for sn in tl.get("nodes") or []:
        for n in sn["nodes"]:
            if n.get("id") is not None and str(n["id"]) in info and n.get("x") is not None:
                pos.setdefault(str(n["id"]), (n["x"], n["z"]))
        if len(pos) == len(info):
            break
    track = {}
    for r in tl.get("sites") or []:
        track.setdefault(str(r[1]), []).append([r[0], r[2], r[3], r[4]])
    for sid, (bp, sp, vp) in sorted(info.items()):
        if not re.search(r"holy_site|sacred_site", bp):
            continue
        x, z = pos.get(sid, (None, None))
        out["sites"].append({"id": int(sid), "bp": bp, "x": x, "z": z, "vp": vp, "track": track.get(sid, [])})
    out["smith"] = {}
    for fr in frames[::30]:
        for e in fr["entities"]:
            if e["kind"] == "o" and "tech_unit_infantry" in (e["bp"] or "") and str(e["owner"]) not in out["smith"]:
                out["smith"][str(e["owner"])] = e["bp"]
    out["cols"] = ["t", "bank", "rate", "vil", "idle", "pop", "cap", "age", "nvil", "nmil", "prod", "landmarks", "idleSec",
                   "vilSec", "gathered", "army", "workerKills", "destroyed", "milQueue", "dynasty", "armyBy", "armyCost", "vizier", "progress", "sources", "garrisoned", "garrisonSec", "armyMadePerMin"]
    return out


def recaps(F):
    """per fight: value / units lost, losses per unit type (bp, count), damage per unit type (bp, name, damage) +
    unattributed, per side (owner 2026-11-11: fight recaps, what unit did the damage)"""
    bps, names = F.get("bps") or [], F.get("names") or []
    bp = lambda i: bps[i] if 0 <= i < len(bps) else ""
    out = []
    for f in F.get("fights") or []:
        dmg = {}
        for p, d in (f.get("damage") or {}).items():
            dmg[p] = {"by": [[bp(x[2]), x[0], round(x[1])] for x in d.get("by", [])], "un": round(d.get("unattributed") or 0)}
        out.append({"n": f["n"], "s": f["start"], "e": f["end"], "x": f["x"], "z": f["z"],
                    "lost": f.get("lost") or {}, "units": f.get("unitsLost") or {},
                    "lostBy": {p: [[bp(i), names[i] if i < len(names) else "", n] for i, n in v]
                               for p, v in (f.get("lostBy") or {}).items()},
                    "army": {p: [[bp(i), names[i] if i < len(names) else "", n] for i, n in v]
                             for p, v in (f.get("army") or {}).items()},
                    "dmg": dmg})
    return out


def hit_recaps(tl, F, H):
    """dump v9 hits per fight (owner 2026-11-11, Dota-style recap): per attacking player, per attacker type the damage
    and how it split over the victim types; army value at the start / end (hud rows). Only hits between players, in
    the fight's time (+-2 s) with the victim within the fight radius + 40 of its centre."""
    import bisect
    hits = tl.get("hits") or []
    if not hits:
        return False
    frames = tl["frames"]
    ft = [fr["t"] for fr in frames]
    info, pos = {}, []
    for fr in frames:
        P = {}
        for e in fr["entities"]:
            info.setdefault(e["id"], (e["owner"], e["bp"]))
            if e["x"] is not None:
                P[e["id"]] = (e["x"], e["z"])
        pos.append(P)
    hts = [h[0] for h in hits]
    rows = H["rows"]
    from dot import bp_index, who
    hist = bp_index(tl)

    def army_at(p, t):
        R = rows.get(str(p)) or []
        best = None
        for r in R:
            if r[0] <= t:
                best = r
            else:
                break
        return best[15] if best else 0

    for rc in H.get("recaps") or []:
        s0, e0, R2 = rc["s"] - 2, rc["e"] + 2, (rc.get("r") or 15) + 40
        by = {}
        for h in hits[bisect.bisect_left(hts, s0):bisect.bisect_right(hts, e0)]:
            t, a, v, d = h[0], h[1], h[2], h[3]
            if not d or d <= 0:
                continue
            oa, ov = info.get(a, (None, None)), info.get(v, (None, None))
            if not oa[0] or not ov[0] or oa[0] == ov[0]:
                continue
            # the blueprint at the time of the hit (owner 2026-11-12: javelin throwers upgraded to Mansa Javelineers kept
            # their first blueprint here)
            oa, ov = (oa[0], who(hist, a, t)[0] or oa[1]), (ov[0], who(hist, v, t)[0] or ov[1])
            i = max(0, bisect.bisect_right(ft, t) - 1)
            xz = pos[i].get(v) or (pos[i - 1].get(v) if i else None)
            if xz and (xz[0] - rc["x"]) ** 2 + (xz[1] - rc["z"]) ** 2 > R2 ** 2:
                continue
            A = by.setdefault(str(oa[0]), {}).setdefault(oa[1], {"d": 0.0, "v": {}})
            A["d"] += d
            A["v"][ov[1]] = A["v"].get(ov[1], 0.0) + d
        rc["hits"] = {p: sorted([[bp, round(x["d"]), sorted([[vb, round(vd)] for vb, vd in x["v"].items()], key=lambda y: -y[1])]
                                 for bp, x in A.items()], key=lambda y: -y[1]) for p, A in by.items()}
        rc["armyS"] = {str(p["idx"]): army_at(p["idx"], rc["s"] - 1) for p in H["players"]}
        rc["armyE"] = {str(p["idx"]): army_at(p["idx"], rc["e"] + 2) for p in H["players"]}
    return True


def replay_ability_events(tl, path):
    """ability commands from the replay file (replay.abilities) as [t, kind, caster entity id, name, target] like the dump's
    A4D|AB, so the recap counts both. Squad receivers -> one entity of that squad (dump squad ids); names from
    data/abilities.json (aoe4world), else models/ability_names.json (game_assets ability-names), else the PBG id."""
    if not path or not os.path.exists(path):
        return []
    from replay import abilities
    names = {}
    for f, key in ((os.path.join(HERE, "..", "data", "abilities.json"), "abilities"),
                   (os.path.join(HERE, "..", "models", "ability_names.json"), None)):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k, v in (d[key] if key else d).items():
            names.setdefault(k, v["name"] if isinstance(v, dict) else v)
    squad_ent = {}
    for fr in tl["frames"][::5]:
        for e in fr["entities"]:
            if e.get("squad") is not None:
                squad_ent.setdefault(e["squad"], e["id"])
    out = []
    try:
        casts = abilities(path)
    except Exception:  # noqa: BLE001 - an unreadable replay only loses this
        return []
    for c in casts:
        ids = c["entities"] + [squad_ent[q] for q in c["squads"] if q in squad_ent]
        nm = names.get(str(c["pbg"])) or (f"ability {c['pbg']}" if c["pbg"] else "ability")
        if c["kind"] == "stop":
            nm += " (off)"
        for i in ids[:1]:
            out.append([c["t"], "cmd", str(i), nm, ""])
    return out


def arena_recaps(tl, F, H, cost_of, replay_abilities=None):
    """owner 2026-11-11: the live recap follows arenas (analyzer/arena.py: start / fled / returned / reinforcements, an arena
    that moves with the armies). Per arena, every LIVE_STEP s: damage between players involving arena units, per attacking
    side, attacker type -> victim type; arena units lost (value, count) per side."""
    import bisect
    from arena import arenas
    A = arenas(tl, F.get("fights") or [], cost_of)
    info = {}
    for fr in tl["frames"]:
        for e in fr["entities"]:
            info.setdefault(e["id"], (e["owner"], e["bp"]))
    hits = sorted(tl.get("hits") or [], key=lambda h: h[0])
    ht = [h[0] for h in hits]
    from dot import bp_index, who
    hist = bp_index(tl)
    abil = sorted((tl.get("abilities") or []) + (replay_abilities or []), key=lambda x: x[0])
    at_ = [x[0] for x in abil]
    for a in A:
        members = set()
        for sd in a["sides"].values():
            members.update(sd["start"])
            members.update(x[0] for x in sd["reinf"])
        died = {}
        for p, sd in a["sides"].items():
            for i, t in sd["died"]:
                died.setdefault(round((t - a["s"]) // LIVE_STEP), {}).setdefault(p, [0, 0])
                v = died[round((t - a["s"]) // LIVE_STEP)][p]
                v[0] += round(cost_of(a["bp"].get(str(i)) or info.get(i, (0, ""))[1]))
                v[1] += 1
        steps, k = [], 0
        t = a["s"]
        while t <= a["e"] + LIVE_STEP:
            dmg = {}
            for h in hits[bisect.bisect_left(ht, t):bisect.bisect_left(ht, t + LIVE_STEP)]:
                # owner 2026-11-11: hits landed per attacker -> victim type as well as damage (damage favours targets the
                # attacker has a bonus against); a deflected hit (damage 0) counts as a hit, adds no damage
                if h[3] is None or h[3] < 0 or (h[1] not in members and h[2] not in members):
                    continue
                oa, ov = info.get(h[1]), info.get(h[2])
                if not oa or not ov or oa[0] == ov[0]:
                    continue
                oa, ov = (oa[0], who(hist, h[1], h[0])[0] or oa[1]), (ov[0], who(hist, h[2], h[0])[0] or ov[1])
                d = dmg.setdefault(str(oa[0]), {}).setdefault(oa[1], {})
                x = d.setdefault(ov[1], [0.0, 0])
                x[0] += h[3]
                x[1] += 1
            # abilities used by arena units in the step (dump v12 A4D|AB): {side: {ability: n}}
            used = {}
            for ev in abil[bisect.bisect_left(at_, t):bisect.bisect_left(at_, t + LIVE_STEP)]:
                c = ev[2]
                if c.isdigit() and int(c) in members:
                    u = used.setdefault(str(info.get(int(c), ("?",))[0]), {})
                    u[ev[3] or ev[1]] = u.get(ev[3] or ev[1], 0) + 1
            steps.append([round(t, 1), {p: [[ab, [[vb, round(x[0]), x[1]] for vb, x in V.items()]] for ab, V in D.items()] for p, D in dmg.items()},
                          died.get(k, {}), used])
            t += LIVE_STEP
            k += 1
        a["steps"] = steps
        a["bp"] = {i: b for i, b in a["bp"].items()}
    H["arenas"] = A
    return A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analyzed")
    ap.add_argument("out")
    ap.add_argument("--fights", help="work/<name>.fights.json: fight recaps and upgrade rows")
    ap.add_argument("--replay", help="the replay file: ability commands for the fight recap, research clicks")
    a = ap.parse_args()
    tl = json.load(open(a.analyzed, encoding="utf-8"))
    tbl, costs_full = load_costs()
    cost_of = lambda bp: tbl.get(resolve(bp, tbl), 0.0)  # noqa: E731
    H = hud(tl, costs_full, cost_of)
    if a.fights and os.path.exists(a.fights):
        F = json.load(open(a.fights, encoding="utf-8"))
        H["recaps"] = recaps(F)
        hit_recaps(tl, F, H)
        try:
            arena_recaps(tl, F, H, cost_of, replay_ability_events(tl, a.replay))
        except Exception as e:  # noqa: BLE001 - the rest of the HUD still builds
            import traceback
            traceback.print_exc()
            print(f"  arenas failed: {e}")
    # upgrade rows: completions + start (v19 event / v18 queue head) + the replay's research click (owner 2026-11-12);
    # clicks that never completed (cancelled / not reached) -> H["techClicks"] {p: [[t, attrib, name, building]]}
    from export_fights import techs_list
    from techs_bought import techs_bought
    if a.replay and os.path.exists(a.replay):
        try:
            from replay import queues
            tl["queueCmds"] = queues(a.replay)
        except Exception as e:  # noqa: BLE001 - an unreadable replay only loses the clicks
            print(f"  replay queue commands: {e}")
    H["tech"] = tech_rows(techs_list(tl), _civs(tl))
    if tl.get("queueCmds"):
        co = {}
        try:
            techs_bought(tl, clicks_out=co)
        except (OSError, ValueError):
            co = {}
        H["techClicks"] = {str(p): [[c["t"], c["attrib"], c["name"], c["building"]] for c in v if c["done"] is None]
                           for p, v in co.items()}
    # display names for every blueprint the HUD shows (costs.json names; aoe4world)
    tbl_full = costs_full
    bps = set()
    for R in H["rows"].values():
        for r in R:
            bps.update(x[0] for x in r[10] + r[18] + r[20])
    for a_ in H.get("arenas") or []:
        bps.update(a_["bp"].values())
        for st in a_["steps"]:
            for L in st[1].values():
                for ab, V in L:
                    bps.add(ab)
                    bps.update(v[0] for v in V)
    for rc in H.get("recaps") or []:
        for A in (rc.get("hits") or {}).values():
            for x in A:
                bps.add(x[0])
                bps.update(v[0] for v in x[2])
    H["names"] = {b: (tbl_full.get(resolve(b, tbl_full) or "") or {}).get("name") or b for b in sorted(bps) if b}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(H, fh, separators=(",", ":"))
    n = sum(len(v) for v in H["rows"].values())
    print(f"hud: {n} rows, {len(H.get('recaps') or [])} fight recaps -> {a.out} ({os.path.getsize(a.out) // 1024} KB)")


if __name__ == "__main__":
    main()
