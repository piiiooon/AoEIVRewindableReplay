"""Visible-only bank estimate for each (observer, target) pair, plus ground truth.

Estimate, built only from what the observer saw (plus game-rule knowledge) up to time t:
    bank_est(t) = bank_start + r * integral(N_est dt) - spent_seen(t) - vil_cost * (N_max - N_start)
  N_seen(t)     distinct target villagers seen in the last --window seconds
  N_est(t)      --vil-model seen: max(N_seen, N_start)
                --vil-model tc:   also >= N_start + integral(TCs_known / vil_time dt),
                                  i.e. nonstop production from every Town Center seen
  spent_seen(t) summed cost of every non-starting, non-villager target entity seen so far
  r             resource per villager per second (--rate, required unless --fit-rate)

Truth (review only, uses hidden information):
  bank_true(t)      logged bank
  spent_true(t)     summed cost of every non-starting entity that existed
  gathered_true(t)  bank_true - bank_start + spent_true
Technologies are not entities, so their cost is missing from both spent terms.

Usage: python analyze.py timeline.json out.json (--rate R | --fit-rate) [--window 120]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gather import label_villagers  # noqa: E402
from gamedata import resolve, is_free  # noqa: E402
from techs_bought import techs_bought  # noqa: E402
from fights import fights_for, find_deaths, last_seen, killed_ids  # noqa: E402
from counter import counters  # noqa: E402
from food import food_forecast  # noqa: E402
from castle import castle_forecast  # noqa: E402
from econ import economy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
COST_KEYS = ["food", "wood", "gold", "stone", "oliveoil", "silver"]


def load_costs():
    with open(os.path.join(HERE, "..", "data", "costs.json")) as fh:
        d = json.load(fh)
    return {k: sum(v.get(r) or 0 for r in COST_KEYS) for k, v in d["costs"].items()}, d["costs"]


def load_sight():
    with open(os.path.join(HERE, "..", "data", "sight.json")) as fh:
        return json.load(fh)["sight"]


def sight_cells(own, sight, cell=20.0):
    """Own entities as sight circles, bucketed by grid cell for fast point tests."""
    grid = {}
    for e in own:
        r = sight.get(e["bp"]) or sight.get(resolve(e["bp"], sight) or "")
        if not r or e["x"] is None:
            continue
        for cx in range(int((e["x"] - r) // cell), int((e["x"] + r) // cell) + 1):
            for cz in range(int((e["z"] - r) // cell), int((e["z"] + r) // cell) + 1):
                grid.setdefault((cx, cz), []).append((e["x"], e["z"], r))
    return grid


def in_sight(grid, x, z, cell=20.0):
    for (ex, ez, r) in grid.get((int(x // cell), int(z // cell)), ()):
        if (x - ex) ** 2 + (z - ez) ** 2 <= r * r:
            return True
    return False


def load_techs():
    with open(os.path.join(HERE, "..", "data", "techs.json")) as fh:
        return json.load(fh)["techs"]


# Wheelbarrow from villager speed (dump units: 4 per tile). Base villager 1.125 tiles/s
# -> 4.5/s; Wheelbarrow x1.15 -> 5.18/s. Per-second displacement of a visible villager.
SPEED_BASE = (4.35, 4.65)
SPEED_WB = (5.05, 5.35)
WB_WINDOW, WB_MIN, WB_RATIO = 60.0, 8, 2.0
# civs whose villagers reach Wheelbarrow speed by other means (Mongol: seen from ~7:00
# without the tech, coinciding with Deer Stones / Yam Network)
WB_NOT_INFERABLE = ("mongol",)


# Age-up: an opponent's age-up completion is announced to every player, so the observer may
# charge the landmark cost then, even with the landmark unseen. Standard landmark cost by the
# age it is built in (aoe4world data: 400f/200g, 1200f/600g, 2400f/1200g).
LANDMARK_COST = {1: (400, 200), 2: (1200, 600), 3: (2400, 1200)}
AGE_NAME = {2: "Feudal", 3: "Castle", 4: "Imperial"}

# Implied gold, from what the observer sees: a visible gold deposit shows its remaining
# amount (as clicking it does). Mined by the opponent = start amount - remaining - the
# observer's own mining there (own gold villagers within GOLD_R). Between looks, each
# deposit's last measured rate carries forward. Gold seen spent can't exceed gold mined,
# so the estimate never goes below 0. Reported only until both players are in Castle.
GOLD_R = 14.0


def bank_total(b):
    vals = [v for v in b.values() if v is not None]
    return sum(vals) if vals else None


def analyze(tl, rate=None, fit_rate=False, window=120.0, vil_model="tc", vil_time=20.0,
            vil_cap=100):
    cost, costs_full = load_costs()
    techs = load_techs()
    sight = load_sight()
    civ = {p["idx"]: p["civ"] for p in tl["players"]}
    frames = tl["frames"]
    pids = [p["idx"] for p in tl["players"]]
    warnings = []
    if not frames:
        raise SystemExit("timeline has no frames")
    if frames[0]["t"] > 5:
        warnings.append(f"first frame at t={frames[0]['t']}s: dump started late, "
                        "starting state and early spending are wrong")
    if not tl["caps"].get("Player_CanSeeEntity"):
        warnings.append("no visibility data: visible-only estimate impossible")
    if not tl["caps"].get("Player_GetResource"):
        warnings.append("no bank data: no ground truth")

    start_ids = {e["id"] for e in frames[0]["entities"]}
    start_vil = {p: sum(1 for e in frames[0]["entities"] if e["owner"] == p and e["kind"] == "w")
                 for p in pids}
    def pl(fr, p):
        d = fr["players"]
        return d.get(str(p)) or d.get(p)

    start_bank = {p: bank_total(pl(frames[0], p)["bank"]) for p in pids}
    unknown_bp = {}
    substituted = {}
    vil_cost = {}
    for p in pids:
        bps = [e["bp"] for e in frames[0]["entities"] if e["owner"] == p and e["kind"] == "w"]
        vil_cost[p] = cost.get(bps[0], 50.0) if bps else 50.0

    def c(bp):
        if is_free(bp):
            return 0.0
        k = resolve(bp, cost)
        if k:
            if k != bp:
                cost[bp] = cost[k]
                costs_full[bp] = costs_full[k]
                substituted[bp] = k
            return cost[k]
        unknown_bp[bp] = unknown_bp.get(bp, 0) + 1
        return 0.0

    # ---- truth per player
    truth = {}
    for p in pids:
        seen_ids, spent, integ = set(), 0.0, 0.0
        rows = []
        prev_t = frames[0]["t"]
        prev_up = dict(pl(frames[0], p)["eco_up"])
        for fr in frames:
            dt = fr["t"] - prev_t
            prev_t = fr["t"]
            # economy upgrades the dump reports (levels only go up)
            up = pl(fr, p)["eco_up"]
            if up["wheelbarrow"] > prev_up["wheelbarrow"]:
                spent += techs["wheelbarrow"]["cost"]
            for r in ("food", "wood", "gold"):
                for lv in range(prev_up[r] + 1, up[r] + 1):
                    spent += techs[f"{r}{lv}"]["cost"]
            prev_up = {k: max(prev_up[k], up[k]) for k in up}
            n = 0
            for e in fr["entities"]:
                if e["owner"] != p:
                    continue
                if e["kind"] == "w":
                    n += 1
                if e["id"] not in seen_ids:
                    seen_ids.add(e["id"])
                    if e["id"] not in start_ids:
                        spent += c(e["bp"])
            integ += n * dt
            b = bank_total(pl(fr, p)["bank"])
            g = None if b is None or start_bank[p] is None else b - start_bank[p] + spent
            rows.append({"t": fr["t"], "bank": b, "spent": spent, "gathered": g,
                         "gold": pl(fr, p)["bank"].get("gold"),
                         "villagers": n, "vil_seconds": integ})
        truth[p] = rows

    if fit_rate:
        # least squares through the origin: gathered ~ r * integral(N dt), all players pooled
        num = den = 0.0
        for rows in truth.values():
            for r in rows:
                if r["gathered"] is not None:
                    num += r["gathered"] * r["vil_seconds"]
                    den += r["vil_seconds"] ** 2
        if den == 0:
            raise SystemExit("cannot fit rate: no bank data")
        rate = num / den
        warnings.append(f"rate fitted from THIS game's true banks (hidden information, review only): "
                        f"r={rate:.4f}/s")
    if rate is None:
        raise SystemExit("give --rate or --fit-rate")

    # resource nodes: gold positions per snapshot (latest full snapshot for anything missing)
    node_snaps = tl.get("nodes") or []
    node_gold = [[(n["id"], (n["x"], n["z"])) for n in snap["nodes"]
                  if n["type"] == "gold" and n["x"] is not None] for snap in node_snaps]
    # start amount of every gold deposit (map knowledge: deposits start full)
    gold_start_amt = {}
    for snap in node_snaps:
        for n in snap["nodes"]:
            if n["type"] == "gold" and n.get("left") is not None and n["id"] not in gold_start_amt:
                gold_start_amt[n["id"]] = n["left"]
    has_left = bool(gold_start_amt)
    if not has_left:
        warnings.append("no deposit amounts in this dump: implied gold off")
    # first time each observer had each node in sight (game's own mask if dumped,
    # else the observer's sight circles at the snapshot time)
    explored = {o: {} for o in pids}
    if node_snaps:
        fi_ = 0
        has_mask = any(n.get("vis") is not None for snap in node_snaps for n in snap["nodes"])
        for snap in node_snaps:
            while fi_ + 1 < len(frames) and frames[fi_ + 1]["t"] <= snap["t"]:
                fi_ += 1
            for o in pids:
                grid = None      # the observer's sight circles, built only if a node lacks visibility
                for n in snap["nodes"]:
                    if n["id"] in explored[o] or n["x"] is None:
                        continue
                    if n["vis"] is not None:      # game's own visibility
                        seen_now = (n["vis"] >> (o - 1)) & 1
                    else:                          # trees in v5 dumps, or dumps without visibility
                        if grid is None:
                            grid = sight_cells([e for e in frames[fi_]["entities"] if e["owner"] == o], sight)
                        seen_now = in_sight(grid, n["x"], n["z"])
                    if seen_now:
                        explored[o][n["id"]] = snap["t"]
        if not has_mask:
            warnings.append("resource nodes: no visibility in dump, explored area approximated "
                            "from sight radii at snapshot times")
    if not tl["caps"].get("age"):
        warnings.append("no age data in this dump: age-up notification correction off")

    last_t = last_seen(frames)
    killed_ev = killed_ids(frames, tl.get("events"))
    # ---- visible-only estimate per observer/target
    est = {}
    events = {}
    for o in pids:
        bit = 1 << (o - 1)
        for p in pids:
            if p == o:
                continue
            key = f"{o}->{p}"
            seen, last_seen_vil = {}, {}
            spent, gathered = 0.0, 0.0
            tcs_known = 1          # the starting Town Center
            n_prod = float(start_vil[p])
            n_max = start_vil[p]
            rows, evs = [], []
            prev_t = frames[0]["t"]
            wb_ok = not civ[p].startswith(WB_NOT_INFERABLE)
            wb_done, spent_tech, prev_pos, samples = False, 0.0, {}, []
            # age-up notifications
            age_prev = pl(frames[0], p).get("age")
            lm_paid, lm_seen, spent_age, spent_age_gold = {}, {}, 0.0, 0.0
            # villager kills seen
            killed, gathered_k, vis_prev = set(), 0.0, set()
            # gold
            gold_start = pl(frames[0], p)["bank"].get("gold") or 0.0
            gold_spent, gold_flagged, gold_deficit = 0.0, set(), 0.0
            gold_obs, own_mined = {}, {}   # node -> (t, mined by opponent, rate); node -> own mined
            gold_vil_seen = {}             # their villager -> last time seen mining gold
            node_i = -1
            for fr in frames:
                t = fr["t"]
                dt = t - prev_t
                prev_t = t
                new, inferred = [], []
                cur_pos = {}
                n_kills_now = 0
                for e in fr["entities"]:
                    if e["owner"] != p or not e["vis"] or not (e["vis"] & bit):
                        continue
                    if e["kind"] == "w":
                        last_seen_vil[e["id"]] = t
                        cur_pos[e["id"]] = (e["x"], e["z"])
                        if e.get("res") == 3:
                            gold_vil_seen[e["id"]] = t
                    if e["id"] not in seen:
                        seen[e["id"]] = e["bp"]
                        if e["id"] not in start_ids and e["kind"] != "w":
                            la = (costs_full.get(e["bp"]) or {}).get("landmark_age")
                            if la:
                                lm_seen[la] = lm_seen.get(la, 0) + 1
                                if lm_seen[la] > lm_paid.get(la, 0):
                                    lm_paid[la] = lm_seen[la]
                                    spent += c(e["bp"])
                                    g_ = (costs_full.get(e["bp"]) or {}).get("gold") or 0
                                    gold_spent += g_
                            else:
                                spent += c(e["bp"])
                                g_ = (costs_full.get(e["bp"]) or {}).get("gold") or 0
                                gold_spent += g_
                            new.append(e["bp"])
                            if (e["bp"] or "").startswith("building_town_center"):
                                tcs_known += 1
                # speed samples need the villager visible in two consecutive samples
                if wb_ok and not wb_done:
                    for i, pos in cur_pos.items():
                        if i in prev_pos and pos[0] is not None and prev_pos[i][0] is not None:
                            v = math.dist(pos, prev_pos[i]) / (dt or 1.0)
                            if SPEED_BASE[0] <= v <= SPEED_BASE[1]:
                                samples.append((t, "b"))
                            elif SPEED_WB[0] <= v <= SPEED_WB[1]:
                                samples.append((t, "w"))
                    samples = [x for x in samples if t - x[0] <= WB_WINDOW]
                    nw = sum(1 for x in samples if x[1] == "w")
                    if nw >= WB_MIN and nw >= WB_RATIO * (len(samples) - nw):
                        wb_done = True
                        spent_tech += techs["wheelbarrow"]["cost"]
                        inferred.append({"name": "Wheelbarrow", "cost": techs["wheelbarrow"]["cost"],
                                         "why": f"{nw} villager moves at Wheelbarrow speed in the last "
                                                f"{int(WB_WINDOW)} s"})
                # villagers that were visible last sample and no longer exist: seen killed.
                # Skip the sample where the owner's whole entity list empties (game end).
                owner_ids = {e["id"] for e in fr["entities"] if e["owner"] == p}
                if owner_ids:
                    # gone from the lists and never back (a gap is not a death); confirmed by the
                    # game's kill events when the log has them
                    dead = {i for i in vis_prev if i not in owner_ids and last_t.get(i, -1) <= t
                            and (killed_ev is None or i in killed_ev)}
                    if dead:
                        grid = sight_cells([e for e in fr["entities"] if e["owner"] == o], sight)
                        dead = {i for i in dead if prev_pos.get(i, (None,))[0] is not None
                                and in_sight(grid, *prev_pos[i])}
                    n_kills_now = len(dead)
                    killed |= dead
                vis_prev = set(cur_pos)
                # age-up notification
                age_now = pl(fr, p).get("age")
                if age_now is not None and age_prev is not None and age_now > age_prev:
                    for a in range(age_prev, age_now):
                        name = f"Age-up to {AGE_NAME.get(a + 1, a + 1)} (notification)"
                        if lm_paid.get(a, 0) == 0:
                            lm_paid[a] = 1
                            f_, g_ = LANDMARK_COST.get(a, (0, 0))
                            spent_age += f_ + g_
                            spent_age_gold += g_
                            inferred.append({"name": name, "cost": f_ + g_,
                                             "why": "landmark not seen yet; standard landmark cost"})
                        else:
                            inferred.append({"name": name, "cost": 0,
                                             "why": "landmark already seen and counted"})
                if age_now is not None:
                    age_prev = age_now
                # gold deposits: own mining, and remaining amounts of deposits in sight
                if has_left:
                    golds = node_gold[node_i] if node_i >= 0 else []
                    for e in fr["entities"]:
                        if e["owner"] == o and e["kind"] == "w" and e.get("res") == 3 and e["x"] is not None:
                            near = min(golds, key=lambda g: math.dist((e["x"], e["z"]), g[1]), default=None)
                            if near and math.dist((e["x"], e["z"]), near[1]) <= GOLD_R:
                                own_mined[near[0]] = own_mined.get(near[0], 0.0) + rate * dt
                    new_snap = False
                    while node_i + 1 < len(node_snaps) and node_snaps[node_i + 1]["t"] <= t:
                        node_i += 1
                        new_snap = True
                    if new_snap:
                        for n in node_snaps[node_i]["nodes"]:
                            if n["type"] != "gold" or n.get("left") is None or n["id"] not in gold_start_amt:
                                continue
                            if n["vis"] is None or not (n["vis"] >> (o - 1)) & 1:
                                continue
                            mined = max(0.0, gold_start_amt[n["id"]] - n["left"] - own_mined.get(n["id"], 0.0))
                            ts = node_snaps[node_i]["t"]
                            prev = gold_obs.get(n["id"])
                            r_ = (mined - prev[1]) / (ts - prev[0]) if prev and ts > prev[0] else 0.0
                            gold_obs[n["id"]] = (ts, mined, max(0.0, r_))
                prev_pos = cur_pos
                n_seen = sum(1 for ts in last_seen_vil.values() if t - ts <= window)
                n_seen_k = sum(1 for i, ts in last_seen_vil.items()
                               if t - ts <= window and i not in killed)
                n_prod = min(n_prod + tcs_known * dt / vil_time, vil_cap)
                n_est = max(n_seen, start_vil[p], int(n_prod) if vil_model == "tc" else 0)
                n_max = max(n_max, n_est)
                spent_vil = (n_max - start_vil[p]) * vil_cost[p]
                gathered += rate * n_est * dt
                b_est = (start_bank[p] or 0.0) + gathered - spent - spent_vil - spent_tech - spent_age
                # second model: same, but villagers seen killed stop gathering
                n_est_k = max(n_seen_k, (int(n_prod) if vil_model == "tc" else start_vil[p]) - len(killed))
                gathered_k += rate * n_est_k * dt
                b_est_k = (start_bank[p] or 0.0) + gathered_k - spent - spent_vil - spent_tech - spent_age
                gold_est = gold_raw = None
                both_castle = (age_prev or 1) >= 3 and (pl(fr, o).get("age") or 1) >= 3
                if has_left and not both_castle:
                    mined_all = sum(min(m + r_ * (t - ts), gold_start_amt[nid]) for nid, (ts, m, r_) in gold_obs.items())
                    gold_raw = gold_start + mined_all - gold_spent - spent_age_gold
                    gold_est = gold_raw + gold_deficit
                    if gold_est < 0:               # spent more than seen mined: mined out of sight
                        gold_deficit -= gold_est
                        gold_est = 0.0
                rows.append({"t": t, "n_seen": n_seen, "n_est": n_est,
                             "spent_seen": spent + spent_vil + spent_tech + spent_age,
                             "gathered_est": gathered, "bank_est": b_est,
                             "n_est_k": n_est_k, "bank_est_k": b_est_k, "kills": len(killed),
                             "gold_est": gold_est, "gold_raw": gold_raw,
                             "gold_vil_now": sum(1 for ts in gold_vil_seen.values() if ts == t),
                             "gold_vil": sum(1 for i, ts in gold_vil_seen.items()
                                             if t - ts <= window and i not in killed)})
                if gold_est is not None and age_prev is not None and age_prev < 3 \
                        and age_prev not in gold_flagged \
                        and gold_est >= LANDMARK_COST[age_prev][1]:
                    gold_flagged.add(age_prev)
                    inferred.append({"name": f"Gold for {AGE_NAME[age_prev + 1]} landmark likely ready",
                                     "cost": 0, "why": f"implied gold {gold_est:.0f} from gold deposits seen "
                                     f"mined >= {LANDMARK_COST[age_prev][1]}"})
                if n_kills_now:
                    inferred.append({"name": f"{n_kills_now} villager(s) seen killed", "cost": 0,
                                     "why": "visible last sample, gone now"})
                if inferred and not new:
                    evs.append({"t": t, "saw": [], "inferred": inferred, "bank_est_after": b_est})
                if new:
                    grouped = {}
                    for bp in new:
                        grouped[bp] = grouped.get(bp, 0) + 1
                    evs.append({"t": t, "saw": [
                        {"bp": bp, "name": costs_full.get(bp, {}).get("name", bp), "n": n,
                         "cost": c(bp) * n} for bp, n in grouped.items()],
                        "inferred": inferred, "bank_est_after": b_est})
            est[key] = rows
            events[key] = evs

    no_wb = sorted({civ[p] for p in pids if civ[p].startswith(WB_NOT_INFERABLE)})
    if no_wb:
        warnings.append("Wheelbarrow not inferred for " + ", ".join(no_wb)
                        + ": villagers reach Wheelbarrow speed without it")
    if substituted:
        warnings.append("cost taken from the data entry with a different name (tier or word order): "
                        + ", ".join(f"{k} <- {v}" for k, v in sorted(substituted.items())))
    if unknown_bp:
        warnings.append("blueprints with no cost entry (counted as 0): "
                        + ", ".join(f"{k} x{v}" for k, v in sorted(unknown_bp.items())))
    return {"params": {"rate": rate, "window": window, "vil_model": vil_model,
                       "vil_time": vil_time, "vil_cap": vil_cap}, "warnings": warnings,
            "truth": {str(k): v for k, v in truth.items()}, "estimate": est, "events": events,
            "explored": {str(o): v for o, v in explored.items()}}


def add_techs(res, tl):
    """Review only (the game's upgrade events): what each player researched, and the implied gold with
    those purchases taken off (own deficit and floor, like gold_est)."""
    try:
        bought = techs_bought(tl)
    except (OSError, ValueError) as ex:
        res["warnings"].append(f"tech list skipped: {ex}")
        return
    res["techs"] = {str(p): v for p, v in bought.items()}
    unknown = sorted({x["attrib"] for v in bought.values() for x in v if x["gold"] is None})
    if unknown:
        res["warnings"].append("upgrades with no cost entry (gold counted as 0): " + ", ".join(unknown))
    for key, rows in res["estimate"].items():
        tp = bought.get(int(key.split("->")[1]), [])
        deficit, i, paid = 0.0, 0, 0.0
        for r in rows:
            while i < len(tp) and tp[i]["t"] <= r["t"]:
                paid += tp[i]["gold"] or 0
                i += 1
            g = None
            if r.get("gold_raw") is not None:
                g = r["gold_raw"] - paid + deficit
                if g < 0:
                    deficit -= g
                    g = 0.0
            r["gold_est_tech"] = g
            r["tech_gold"] = paid


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("out")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rate", type=float)
    g.add_argument("--fit-rate", action="store_true")
    ap.add_argument("--window", type=float, default=120.0)
    ap.add_argument("--vil-model", choices=["seen", "tc"], default="tc",
                    help="seen: villagers = recently seen only; tc: also assume continuous "
                         "production from every known Town Center")
    ap.add_argument("--vil-time", type=float, default=20.0,
                    help="villager production time, s (aoe4world data: 20)")
    ap.add_argument("--vil-cap", type=int, default=100)
    a = ap.parse_args(argv)
    with open(a.timeline) as fh:
        tl = json.load(fh)
    label_villagers(tl)
    res = analyze(tl, a.rate, a.fit_rate, a.window, a.vil_model, a.vil_time, a.vil_cap)
    cost_tbl, _ = load_costs()
    cost_of = lambda bp: cost_tbl.get(resolve(bp, cost_tbl), 0.0)  # noqa: E731
    res["fights"] = fights_for(tl, cost_of)
    deaths = find_deaths(tl["frames"], cost_of, tl.get("events"))
    res["counter"] = counters(tl, deaths)
    res["food"], fw = food_forecast(tl, res["explored"], cost_of, deaths, res["params"]["rate"], res["estimate"])
    res["warnings"] += fw
    for key, f in res["food"].items():          # food warnings join the observer's log
        evs = res["events"].setdefault(key, [])
        evs += [{"t": e["t"], "saw": [], "inferred": [{"name": e["name"], "cost": 0, "why": e["why"]}],
                 "bank_est_after": None} for e in f["events"]]
        evs.sort(key=lambda e: e["t"])
    add_techs(res, tl)
    _, costs_full = load_costs()
    res["econ"] = economy(tl, costs_full)          # review only: villager economy, hunt premium (econ.py)
    res["castle"] = castle_forecast(tl, res["estimate"], res["events"], costs_full, cost_of, res["params"]["rate"])
    for key, cf in res["castle"].items():       # off-path purchases join the observer's log
        evs = res["events"].setdefault(key, [])
        for it in cf["items"]:
            why = (f"implied: {it['implied']} seen, no production building for it seen" if it.get("implied")
                   else "off the Feudal -> Castle path")
            evs.append({"t": it["t"], "saw": [], "bank_est_after": None, "inferred": [
                {"name": f"Castle +{it['sec']} s: {it['name']}" + (f" x{it['n']}" if it['n'] > 1 else ""),
                 "cost": it["cost"] if it.get("implied") else 0, "why": why}]})
        evs.sort(key=lambda e: e["t"])
    tl["analysis"] = res
    # damage-over-time ticks are logged under the victim's latest attacker (owner 2026-11-12): credit them to the unit that
    # applied the poison / bleed (analyzer/dot.py) before anything splits damage by attacker
    try:
        from dot import retag
        tl["hits"], moved = retag(tl)
        if moved:
            print(f"damage over time: {moved} tick(s) re-credited to the unit that applied them")
    except Exception as e:  # noqa: BLE001 - the raw hits stay
        print(f"damage over time: not re-credited ({e})")
    with open(a.out, "w") as fh:
        json.dump(tl, fh, separators=(",", ":"))
    for w in res["warnings"]:
        print("WARNING:", w)
    for key, rows in res["estimate"].items():
        o, p = key.split("->")
        tr = res["truth"][p]
        print(f"observer {o} on player {p}:")
        for i in range(0, len(rows), max(1, len(rows) // 6)):
            r, q = rows[i], tr[i]
            print(f"  t={r['t']:6.0f}  est bank {r['bank_est']:7.0f}  true bank {q['bank'] or 0:7.0f}"
                  f"  vils seen/est/true {r['n_seen']:2d}/{r['n_est']:2d}/{q['villagers']:2d}"
                  f"  spent seen/true {r['spent_seen']:6.0f}/{q['spent']:6.0f}")


if __name__ == "__main__":
    main()
