"""Read the scripted test fights (tools/fight_tests.py -> logs/fighttests/<test>_r<k>.txt) for calibrating the fight
simulator (owner 2026-11-10).

    python analyzer/fighttests.py [folder]          # one summary line per run

load(path) -> {"meta", "start", "units": {squad: {side, bp, entity}}, "ent2sq", "frames": [(t, {squad: rec})],
"hits": [(t, att_ent, vic_ent, dmg, hp)], "shots": [(t, "F"/"L", att, proj, target, x, z)], "form": [(t, side, x, y)],
"cmd", "end": (t, reason), "errors"}; rec = {"n", "x", "z", "hp", "hpmax", "hx", "hz", "atk"}.
"""
import json
import os
import sys


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(path):
    out = {"meta": {}, "start": None, "units": {}, "ent2sq": {}, "frames": [], "hits": [], "shots": [], "form": [],
           "cmd": {}, "end": None, "errors": [], "up": []}
    fr = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("# "):
                out["meta"] = json.loads(line[2:])
                continue
            p = line.split("|")
            if len(p) < 3 or p[0] != "A4D" or p[1] != "FT":
                continue
            k = p[2]
            if k == "START":
                out["start"] = {"cx": _f(p[4]), "cz": _f(p[5]), "dx": _f(p[6]), "dz": _f(p[7]), "gap": _f(p[8])}
            elif k == "U":
                sq, side, bp, ent = int(p[3]), int(p[4]), p[5], p[6]
                out["units"][sq] = {"side": side, "bp": bp, "entity": int(ent) if ent else None}
                if ent:
                    out["ent2sq"][int(ent)] = sq
            elif k == "S":
                t = float(p[3])
                d = fr.setdefault(t, {})
                for r in "|".join(p[4:]).split(";"):
                    f = r.split(",")
                    if len(f) < 3 or not f[0]:
                        continue
                    sq = int(f[0])
                    if f[2] == "0" or len(f) < 8:
                        d[sq] = {"n": 0}
                        continue
                    hx = hz = None
                    if f[7] and ":" in f[7]:
                        hx, hz = (_f(v) for v in f[7].split(":"))
                    d[sq] = {"n": int(f[2]), "x": _f(f[3]), "z": _f(f[4]), "hp": _f(f[5]), "hpmax": _f(f[6]),
                             "hx": hx, "hz": hz, "atk": len(f) > 8 and f[8] == "A"}
            elif k == "H":
                t = float(p[3])
                for r in "|".join(p[4:]).split(";"):
                    f = r.split(",")
                    if len(f) >= 4:
                        out["hits"].append((t, int(f[0]), int(f[1]), _f(f[2]), _f(f[3])))
            elif k in ("PF", "PL"):
                t = float(p[3])
                for r in "|".join(p[4:]).split(";"):
                    f = r.split(",")
                    if len(f) >= 5:
                        out["shots"].append((t, k[1], int(f[0]), int(f[1]), int(f[2]), _f(f[3]), _f(f[4])))
            elif k == "FORM":
                out["form"].append((float(p[3]), int(p[4]), _f(p[5]), _f(p[6])))
            elif k == "CMD":
                out["cmd"][int(p[3])] = (p[4], p[5])
            elif k == "KITE":
                out.setdefault("kite", []).append((float(p[3]), p[4]))
            elif k == "INV":
                out.setdefault("inv", []).append(int(p[3]))
            elif k == "UP":
                out["up"].append((int(p[3]), p[4], p[5]))
            elif k == "END":
                out["end"] = (_f(p[4]), p[5] if len(p) > 5 else "")
            elif k == "ERR":
                out["errors"].append("|".join(p[3:]))
    out["frames"] = sorted(fr.items())
    return out


def summary(R):
    """per side: units, alive at the end, HP left, value lost (hits: damage dealt by each side)"""
    last = R["frames"][-1][1] if R["frames"] else {}
    s = {}
    for side in (1, 2):
        sqs = [q for q, u in R["units"].items() if u["side"] == side]
        alive = [q for q in sqs if (last.get(q) or {}).get("n")]
        hp = sum((last.get(q) or {}).get("hp") or 0 for q in alive)
        side_ents = {u["entity"] for q, u in R["units"].items() if u["side"] == side}
        dealt = sum(h[3] or 0 for h in R["hits"] if h[1] in side_ents)
        s[side] = {"n": len(sqs), "alive": len(alive), "hp": round(hp), "dealt": round(dealt)}
    return s


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "logs", "fighttests")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".txt"):
            continue
        R = load(os.path.join(d, fn))
        s = summary(R)
        e = R["end"] or (None, "no END")
        print(f"{fn:14s} {R['meta'].get('name', '')[:34]:34s} end {e[0]} {e[1]:12s} "
              + "  ".join(f"S{k}: {v['alive']}/{v['n']} hp {v['hp']} dealt {v['dealt']}" for k, v in s.items())
              + f"  hits {len(R['hits'])} shots {len(R['shots'])}" + (f"  ERR {R['errors'][:2]}" if R["errors"] else ""))


if __name__ == "__main__":
    main()
