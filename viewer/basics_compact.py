"""Compact the basics checks (work/<name>.basics.json, from build_basics.py --json) for the replay viewer:
timeline marks and the "Basics (review)" panel (owner 2026-10-27). Review-only data: the viewer shows it only with
Show true values or Everything."""


def compact(B):
    P = {}
    L = B.get("lenses") or {}
    for p, d in B["players"].items():
        h = (L.get(p) or {}).get("hindsight") or {}
        f = (L.get(p) or {}).get("foresight") or {}
        P[p] = {
            # [t, gathered, bank total, army value, villagers, idle villagers, spent]
            "series": [[s[0], s[1], sum(s[2].values()), s[3], sum(s[4].values()), s[5], s[7]] for s in d["series"]],
            "floats": [[x["t0"], x["t1"], x["grade"], x["res"], x.get("peak")] for x in d["floats"]],
            "style": [[x["t0"], x["t1"], x["kind"]] for x in d["style"]],
            "saves": [[x["t0"], x["t1"], x["name"], x.get("afford"), x["took"], x.get("ideal")] for x in d["saves"]],
            "overq": [e for e in (d.get("overqueue") or {}).get("episodes", []) if e[0] >= 60],
            "catch": f.get("catchup", []),
            "food": [[x["t"], x["foodMin"], x["risk"]] for x in f.get("farmRisk", [])],
            "idleArmy": [[x["t0"], x["t1"], x["army"]] for x in f.get("idleArmy", [])],
            "raids": [[x["t0"], x["t1"], x["kind"], x["vilKilled"], x["killedValue"], x["lostValue"], x["forcedSecs"],
                       x["net"], x["unitsForVillagers"]] for x in h.get("raids", [])],
            "gaps": [[x["t0"], x["t1"], x["opened"], x["rateGap"], x["main"], x["byRes"], "; ".join(x["near"])]
                     for x in h.get("gapOnsets", [])],
            "dives": [[x["t0"], x["t1"], x["lostMine"], x["lostTheirs"], x["flag"]] for x in h.get("dives", [])],
        }
    return {"me": B.get("me"), "them": B.get("them"), "p": P,
            "trades": [[x["t0"], x["t1"], x["lost"], x["minutes"]] for x in B.get("trades", [])]}
