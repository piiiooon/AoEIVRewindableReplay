"""Generate a SYNTHETIC warnings.log in dump.lua's format, for testing only.

Costs and production times of the blueprints used come from data/costs.json.
Everything else (gather rate, map, sight radius, build decisions, movement) is made up
so the pipeline can run before a real log exists. Do not read anything about the
game into its output.

Usage: python synth_log.py out.log [--minutes 12] [--seed 1]
"""
import argparse
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
RES = ["food", "wood", "gold", "stone"]

SYNTH_RATE = 0.7      # resource per villager per second (made up)
SIGHT = 40.0          # sight radius in map units (made up)
MAP = 500.0


def load_costs():
    with open(os.path.join(HERE, "..", "data", "costs.json")) as fh:
        return json.load(fh)["costs"]


class Player:
    def __init__(self, idx, name, civ, base, plan):
        self.idx, self.name, self.civ, self.base, self.plan = idx, name, civ, base, plan
        self.bank = {r: 200.0 for r in RES}
        self.ents = []
        self.vil_timer = [0.0]   # one production slot per TC
        self.mix = {"food": 0.5, "wood": 0.3, "gold": 0.2, "stone": 0.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    costs = load_costs()
    nid = [1000]

    def spawn(p, bp, x, z, kind):
        nid[0] += 1
        e = {"id": nid[0], "bp": bp, "x": x, "z": z, "kind": kind, "target": None}
        p.ents.append(e)
        return e

    def afford(p, bp):
        c = costs[bp]
        return all(p.bank[r] >= c[r] for r in RES)

    def pay(p, bp):
        for r in RES:
            p.bank[r] -= costs[bp][r]

    # A: early military pressure.  B: saves, second TC at ~4 min, then army.
    A = Player(1, "SynthAggro", "english", (100.0, 100.0), "aggro")
    B = Player(2, "SynthBoom", "chinese", (400.0, 400.0), "boom")
    sfx = {"english": "eng", "chinese": "chi"}
    for p in (A, B):
        s = sfx[p.civ]
        spawn(p, f"building_town_center_{s}", *p.base, "o")
        for i in range(6):
            ang = 2 * math.pi * i / 6
            spawn(p, f"unit_villager_1_{s}", p.base[0] + 15 * math.cos(ang),
                  p.base[1] + 15 * math.sin(ang), "w")
        sc = spawn(p, f"unit_scout_1_{s}", *p.base, "m")
        sc["scout"] = True
    players = [A, B]
    lines = []
    lines.append("A4D|CAPS|World_GetGameTime=1|Player_GetResource=1|Entity_GetPosition=1|"
                 "Player_CanSeeEntity=1|Entity_GetBlueprint=1|BP_GetName=1|Entity_GetID=1|RT_Food=1")

    for t in range(1, int(a.minutes * 60) + 1):
        for p in players:
            s = sfx[p.civ]
            vil = f"unit_villager_1_{s}"
            nv = sum(1 for e in p.ents if e["kind"] == "w")
            for r in RES:
                p.bank[r] += SYNTH_RATE * nv * p.mix[r]
            # villager production, one per TC slot
            ntc = sum(1 for e in p.ents if e["bp"].startswith("building_town_center"))
            while len(p.vil_timer) < ntc:
                p.vil_timer.append(0.0)
            for k in range(ntc):
                if p.vil_timer[k] <= 0 and afford(p, vil) and nv < 60:
                    pay(p, vil)
                    p.vil_timer[k] = costs[vil].get("time", 20) if "time" in costs[vil] else 20
                    tc = [e for e in p.ents if e["bp"].startswith("building_town_center")][k]
                    ang = rnd.random() * 2 * math.pi
                    spawn(p, vil, tc["x"] + 20 * math.cos(ang), tc["z"] + 20 * math.sin(ang), "w")
                p.vil_timer[k] -= 1
            # build decisions
            if p.plan == "aggro":
                rng = f"building_unit_ranged_control_{s}"
                if t == 150:
                    p.mix = {"food": 0.45, "wood": 0.45, "gold": 0.1, "stone": 0.0}
                if t in (150, 240, 330, 480) and afford(p, rng):
                    pay(p, rng)
                    spawn(p, rng, p.base[0] + 40, p.base[1] + 20 * (t // 100), "o")
                nr = sum(1 for e in p.ents if e["bp"] == rng)
                if t > 160 and t % 15 == 0:
                    for _ in range(nr):
                        if afford(p, f"unit_archer_2_{s}"):
                            pay(p, f"unit_archer_2_{s}")
                            spawn(p, f"unit_archer_2_{s}", p.base[0] + 45, p.base[1] + 5, "m")
            else:
                if t == 120:
                    p.mix = {"food": 0.4, "wood": 0.35, "gold": 0.0, "stone": 0.25}
                if t > 120 and len(p.vil_timer) == 1 and afford(p, f"building_town_center_{s}"):
                    pay(p, f"building_town_center_{s}")
                    spawn(p, f"building_town_center_{s}", p.base[0] - 80, p.base[1] + 10, "o")
                    p.mix = {"food": 0.5, "wood": 0.3, "gold": 0.2, "stone": 0.0}
                bar = f"building_unit_infantry_control_{s}"
                if t in (420, 430, 440, 450) and afford(p, bar):
                    pay(p, bar)
                    spawn(p, bar, p.base[0] - 30, p.base[1] - 30 - 15 * (t - 420) // 10, "o")
                nb = sum(1 for e in p.ents if e["bp"] == bar)
                if t > 430 and t % 12 == 0:
                    for _ in range(nb):
                        if afford(p, f"unit_spearman_1_{s}"):
                            pay(p, f"unit_spearman_1_{s}")
                            spawn(p, f"unit_spearman_1_{s}", p.base[0] - 30, p.base[1] - 30, "m")
            # movement
            enemy = B if p is A else A
            for e in p.ents:
                if e["kind"] == "w":
                    e["x"] += rnd.uniform(-1, 1)
                    e["z"] += rnd.uniform(-1, 1)
                elif e["kind"] == "m":
                    if e.get("scout"):
                        if e["target"] is None or math.dist((e["x"], e["z"]), e["target"]) < 5:
                            e["target"] = (rnd.uniform(0, MAP), rnd.uniform(0, MAP))
                        speed = 6.0
                    else:
                        go = (p.plan == "aggro" and t > 300) or (p.plan == "boom" and t > 600)
                        e["target"] = enemy.base if go else (p.base[0] + 50, p.base[1] + 50) \
                            if p.plan == "aggro" else (p.base[0] - 40, p.base[1] - 40)
                        speed = 3.0
                    dx, dz = e["target"][0] - e["x"], e["target"][1] - e["z"]
                    d = math.hypot(dx, dz) or 1
                    e["x"] += speed * dx / d * min(1, d / speed)
                    e["z"] += speed * dz / d * min(1, d / speed)
        # crude combat: military within 15 of an enemy military unit may die
        for p in players:
            enemy = B if p is A else A
            dead = []
            for e in p.ents:
                if e["kind"] != "m":
                    continue
                near = sum(1 for f in enemy.ents if f["kind"] == "m"
                           and math.dist((e["x"], e["z"]), (f["x"], f["z"])) < 15)
                if near and rnd.random() < 0.03 * near:
                    dead.append(e)
            for e in dead:
                p.ents.remove(e)
        # write frame
        for p in players:
            b = p.bank
            lines.append(f"A4D|P|{t:.1f}|{p.idx}|{p.name}|{p.civ}|{p.idx - 1}|"
                         f"{b['food']:.1f}|{b['wood']:.1f}|{b['gold']:.1f}|{b['stone']:.1f}|0|0|0|0")
            ents = []
            for e in p.ents:
                mask = 0
                for q in players:
                    if q is p:
                        continue
                    if any(math.dist((e["x"], e["z"]), (f["x"], f["z"])) <= SIGHT for f in q.ents):
                        mask |= 1 << (q.idx - 1)
                ents.append(f"{e['id']},{e['bp']},{e['x']:.1f},{e['z']:.1f},{mask},{e['kind']},"
                            + ("" if e["kind"] == "o" else "0"))
            for i in range(0, len(ents), 60):
                lines.append(f"A4D|E|{t:.1f}|{p.idx}|" + ";".join(ents[i:i + 60]))
    lines.append("A4D|STOP")
    with open(a.out, "w") as fh:
        for ln in lines:
            fh.write(f"{rnd.randint(0, 9)}:{rnd.randint(10, 59)} [SCAR] {ln}\n")
    print(f"wrote {len(lines)} lines to {a.out}")


if __name__ == "__main__":
    main()
