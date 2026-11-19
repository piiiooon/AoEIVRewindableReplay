"""Basics page: the three lenses (analyzer/lenses.py; owner 2026-10-27), rendered in the owner's order:
hindsight from true values, foresight from true values, inference (what you saw)."""
import html

esc = html.escape
ME, THEM = "var(--me)", "var(--them)"


def _tbl(head, rows, empty="None in this game."):
    if not rows:
        return f'<p class="note">{empty}</p>'
    return ("<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>")


def _vil(v):
    return " / ".join(f"{v.get(r, 0)}" for r in ("food", "wood", "gold", "stone"))


def _signed(v, good_if_pos=True):
    cls = "good" if (v >= 0) == good_if_pos else "bad"
    return f'<span class="{cls}">{v:+,}</span>'


def hindsight(L, me, them, mmss, chart, legend, t_end):
    M, T = L[str(me)]["hindsight"], L[str(them)]["hindsight"]
    who = (("You", M), ("Them", T))
    # idle production
    idle_rows = []
    for w, H in who:
        for x in H["idleProduction"]:
            if x["couldPay"] or x["housed"]:
                idle_rows.append([w, esc(x["name"]), esc(x["unit"]), f'{x["couldPay"]} s', f'{x["housed"]} s',
                                  ", ".join(f"age {k}: {v} s" for k, v in sorted(x["byAge"].items()))])
    # raids / pushes
    raid_rows = []
    for w, H in who:
        for r in H["raids"]:
            u = ", ".join(f"{n} ×{c}" for n, c in sorted(r["units"].items(), key=lambda kv: -kv[1]))
            flag = '<span class="bad">units for villagers</span>' if r["unitsForVillagers"] else ""
            raid_rows.append([w, f'<span class="nw">{mmss(r["t0"])}–{mmss(r["t1"])}</span>', r["kind"],
                              f'{esc(u)} <span class="note">({r["share"]:.0%} of army)</span>',
                              f'{r["vilKilled"]} ({r["killedValue"]:,})', f'{r["forcedSecs"]} s (~{r["forcedValue"]:,})',
                              f'{r["lostValue"]:,}', _signed(r["net"]), flag])
    # arrivals
    arr_rows = []
    for w, H in who:
        for a in H["arrivals"]:
            fb = f'+{a["firstBuilding"][0]} s {esc(a["firstBuilding"][1])}' if a["firstBuilding"] else "–"
            fu = f'+{a["firstUnit"][0]} s {esc(a["firstUnit"][1])}' if a["firstUnit"] else "–"
            te = "; ".join(f"+{d} s {esc(n)}" for d, n in a["techs"]) or "–"
            arr_rows.append([w, f'{"Feudal" if a["age"] == 2 else "Castle"} {mmss(a["t"])}',
                             " / ".join(f'{v:,}' for v in a["bank"].values()), fb, fu, f'<span class="wrap">{te}</span>',
                             f'+{a["push"]} s' if a["push"] is not None else "–"])
    # landmark builds
    lm_rows = []
    for w, H in who:
        for x in H["landmarkBuilds"]:
            lm_rows.append([w, esc(x["name"]), f'{mmss(x["t"])}–{mmss(x["done"]) if x["done"] else "?"}',
                            f'{x["armyMine"]:,} vs {x["armyTheirs"]:,}', f'{x["lostMine"]:,}', f'{x["lostTheirs"]:,}'])
    # dives
    dive_rows = []
    for w, H in who:
        for x in H["dives"]:
            dive_rows.append([w, f'{mmss(x["t0"])}–{mmss(x["t1"])}', f'{x["lostMine"]:,} vs {x["lostTheirs"]:,}',
                              "yes" if x["aheadBefore"] else "no", f'{x["lead"][0]:+,} → {x["lead"][1]:+,}',
                              '<span class="bad">dived while ahead, lead shrank</span>' if x["flag"] else ""])
    # food per third
    ft_rows = []
    for w, H in who:
        if H.get("foodThirds"):
            ft_rows.append([w] + [f'{H["foodThirds"][k]:,} <span class="note">of {H["foodThirdsStart"][k]:,}</span>'
                                  for k in ("mine", "middle", "theirs")])
    # split at click
    sp_rows = []
    for w, H in who:
        for x in H["splits"]:
            th = x["then"]
            did = [f'2nd TC +{th["tc"]} s' if th["tc"] is not None else "",
                   f'{th["towers"]} tower(s)' if th["towers"] else "", f'{th["production"]} production' if th["production"] else "",
                   f'next age-up +{th["next"]} s' if th["next"] is not None else ""]
            sp_rows.append([w, f'{esc(x["name"])} {mmss(x["t"])}', _vil(x["vil"]), x["idle"], x["read"],
                            ", ".join(d for d in did if d) or "–"])
    gap_rows = []
    for w, H in who:
        for x in H.get("gapOnsets", []):
            res = ", ".join(f"{r} {v:+,}" for r, v in sorted(x["byRes"].items(), key=lambda kv: kv[1]) if v)
            gap_rows.append([w, f'<span class="nw">{mmss(x["t0"])}</span> <span class="note">to {mmss(x["t1"])}</span>',
                             f'{x["opened"]:,}', f'{x["rateGap"]:,}/min', f'<span class="wrap">{esc(res)}</span>',
                             f'{x["vils"][0]} vs {x["vils"][1]}', f'{x["perVil"][0]} vs {x["perVil"][1]}',
                             f'<b>{x["main"]}</b> <span class="note">({x["countEffect"]:+,} count, {x["effEffect"]:+,} per villager)</span>',
                             f'<span class="wrap">{esc("; ".join(x["near"])) or "–"}</span>'])
    return f"""<section><h2>Hindsight · what happened (true values)</h2>
<p class="note">Full information, after the fact. Thresholds are first guesses; the rules come from the MSN, Myriad and
TeamTriangle talks (Paper Cut's podcast).</p>
<h3>Where the gathering gap starts</h3>
<p>Each stretch where a side's gathering rate (centred 60 s window) stays below the other's for 90 s or more and the gap grows by
300+. The onset is the first second of it; the columns describe its first 90 s: the gap per resource (per minute), villagers
(this side vs the other), gathered per villager per minute, and whether the gap comes mostly from villager count or from
gathering per villager, with what happened from a minute before.</p>
{_tbl(["falls behind", "from", "gap opened", "rate gap", "by resource /min", "villagers", "per villager /min", "mostly", "around it"], gap_rows)}
<h3>Production buildings idle</h3>
<p>Seconds a production building had nothing queued while the bank could pay for the cheapest unit that player made there
(TeamTriangle: "I'm not producing half the time"). Summed over buildings; housed = pop at the cap.</p>
{_tbl(["", "building", "cheapest unit made", "idle, could pay", "idle, housed", "by age"], idle_rows)}
<h3>Raids and pushes</h3>
<p>One of your army units within {25} units of their villager on their half. Raid = under half your army value, push = more.
Forced idle = their villagers idle or garrisoned above their usual level, valued at their true income per villager
(Myriad: 8 villagers in the TC for 5–10 s beats a kill if you lose nothing; don't trade three horsemen for one villager).</p>
{_tbl(["", "when", "kind", "units", "villagers killed (value)", "forced idle", "lost", "net", ""], raid_rows)}
<h3>Arriving in an age</h3>
<p>Bank on arrival (food / wood / gold / stone), then the first production building and military unit (TeamTriangle:
an efficient age-up places a stable at once), military techs (veterancy, blacksmith: "win in Feudal, end in Castle"),
and the first push (half your army value in their third of the map).</p>
{_tbl(["", "reached", "bank", "first production", "first unit", "military techs", "first push"], arr_rows)}
<h3>While the landmark was building</h3>
{_tbl(["", "landmark", "placed–done", "army at click (you vs them)", "army lost (this side)", "army lost (other side)"], lm_rows)}
<h3>Dives</h3>
<p>Fights within 35 units of their TC, keep or landmark. Lead = gathered gap + army value gap, at the fight and 2 min after
(MSN: a lead is an investment; diving to end it fast is how leads are thrown).</p>
{_tbl(["", "when", "lost (this side vs other)", "ahead before", "lead", ""], dive_rows)}
<h3>Natural food taken, by map third</h3>
<p>Thirds along the line between the starting TCs (Myriad): yours, the middle, theirs. "of" = what was there at the start.</p>
{_tbl(["", "own third", "middle", "their third"], ft_rows)}
<h3>Villager split at the age-up click</h3>
<p>Food / wood / gold / stone villagers when the landmark was placed, the read TeamTriangle gives scouts (gold-heavy = fast
Castle, wood = production, 3+ on stone = 2nd TC), and what followed in the next 3 min.</p>
{_tbl(["", "landmark", "villagers", "idle", "read", "then"], sp_rows)}
</section>"""


def foresight(L, me, them, mmss, chart, legend, t_end):
    M, T = L[str(me)]["foresight"], L[str(them)]["foresight"]
    cap = 20.0

    def pts(c):
        return [(t, min(cap, v) if v is not None else None) for t, v in c]
    catch = chart([("they need to match your army", ME, pts(M["catchup"]), ""),
                   ("you need to match theirs", THEM, pts(T["catchup"]), "5 3")], t_end, ymax=cap,
                  ylabel="minutes", fmt=lambda v: f"{v:.0f}")
    food = chart([("your safe food", ME, [(x["t"], min(cap, x["foodMin"]) if x["foodMin"] is not None else None) for x in M["farmRisk"]], ""),
                  ("their safe food", THEM, [(x["t"], min(cap, x["foodMin"]) if x["foodMin"] is not None else None) for x in T["farmRisk"]], "5 3")],
                 t_end, ymax=cap, ylabel="minutes", fmt=lambda v: f"{v:.0f}")
    risk_rows = []
    for w, F in (("You", M), ("Them", T)):
        rs = [x for x in F["farmRisk"] if x["risk"]]
        if rs:
            risk_rows.append([w, ", ".join(mmss(x["t"]) for x in rs[:12]),
                              f'{rs[0]["foodMin"]} min of food, {rs[0]["short"]} villagers without a farm, '
                              f'{rs[0]["woodMin"] if rs[0]["woodMin"] is not None else "no"} min of wood income to place them'])
    eta_rows = []
    for w, F in (("You", M), ("Them", T)):
        for x in F["ageEta"]:
            pts_ = [p for p in x["eta"] if p[1] is not None]
            if not pts_:
                continue
            best = min(p[1] for p in pts_)
            first_ok = next((p for p in pts_ if p[1] <= p[0] + 1), None)
            eta_rows.append([w, esc(x["name"]), mmss(x["click"]), mmss(best),
                             _signed(x["click"] - best, good_if_pos=False) + " s",
                             f"bank covered it at {mmss(first_ok[0])}" if first_ok else "–"])
    ia_rows = [[w, f'{mmss(x["t0"])}–{mmss(x["t1"])}', f'{x["army"]:,}',
                f'{x["catchup"][0] if x["catchup"][0] is not None else "–"} → {x["catchup"][1] if x["catchup"][1] is not None else "–"} min']
               for w, F in (("You", M), ("Them", T)) for x in F["idleArmy"]]
    sf_rows = []
    for w, F in (("You", M), ("Them", T)):
        for x in F["ageupSafety"]:
            if x["reach"] is None:
                sf_rows.append([w, esc(x["name"]), mmss(x["t"]), "no army", f'{x["build"]} s' if x["build"] else "?", "–"])
                continue
            unsafe = x["build"] is not None and x["reach"] < x["build"]
            sf_rows.append([w, esc(x["name"]), mmss(x["t"]), f'{x["reach"]} s (first unit {x["first"]} s)',
                            f'{x["build"]} s' if x["build"] else "?",
                            f'<span class="{"bad" if unsafe else "good"}">{x["armyMine"]:,} vs {x["armyTheirs"]:,}</span>'])
    return f"""<section><h2>Foresight · what was coming (true values)</h2>
<p class="note">At each moment, the true state projected forward at the current rates: what a player could have planned for
if they had known everything. Compare with hindsight: a bad projection that came true was a bad decision; a good one that
went wrong was execution.</p>
<h3>Minutes to catch up</h3>
<p>How long the other side needs, from its bank and current income (60 s), to match an army's value (MSN: it is over when
they need about 15 minutes). 0 = their bank already covers it. Capped at 20.</p>
{catch}{legend([("they need to match yours", ME), ("you need to match theirs (dashed)", THEM)])}
<h3>Safe food left and the farm switch</h3>
<p>All natural food in a player's own third at their current natural-food rate (Paper Cut: plan farms when you're on your
second-to-last safe food). Risk (Feudal and later): it runs out within 3 min before the wood for the missing farms comes in.</p>
{food}{legend([("you", ME), ("them (dashed)", THEM)])}
{_tbl(["", "at risk", "first time"], risk_rows, "No farm-switch risk in this game.")}
<h3>Age-up timing</h3>
<p>The earliest click the true bank + per-resource income (60 s) allowed for the standard landmark cost, vs the actual click.</p>
{_tbl(["", "landmark", "clicked", "earliest projected", "late by", ""], eta_rows)}
<h3>Army idle at home while they grow</h3>
<p>Stretches of 60 s+ with 70 % of the army in its own third, nobody attacking, their army not in that third, and their income
above yours (MSN: you can't have 80 units sitting in your base while he booms). Catch-up minutes at both ends.</p>
{_tbl(["", "when", "army value", "they need to catch up"], ia_rows)}
<h3>Age-up safety</h3>
<p>At the click: how long half their army (true positions, measured unit speeds) needs to reach your starting TC, vs how long
the landmark took (Myriad: go Castle from a position of strength, when their army is far from your base).</p>
{_tbl(["", "landmark", "clicked", "their army reaches you", "landmark took", "army (yours vs theirs)"], sf_rows)}
</section>"""


def inference(L, me, them, mmss, chart, legend, t_end):
    I = L[str(me)]["inference"]
    sp_rows = [[esc(x["name"]), mmss(x["t"]), _vil(x["seen"]), x["readSeen"], _vil(x["true"]), x["readTrue"],
                '<span class="good">same</span>' if x["readSeen"] == x["readTrue"] else '<span class="bad">differs</span>']
               for x in I["splits"]]
    fs, ft = I["farm"]["seen"], I["farm"]["true"]
    farm = ("They never farmed." if ft is None else
            f"First farm {mmss(ft)}; you first saw one at {mmss(fs)} ({fs - ft:+} s)." if fs is not None else
            f"First farm {mmss(ft)}; you never saw one.")
    arr = I["arrivals"]
    seen_n = sum(1 for a in arr if a["seenAfter"] is not None)
    ar_rows = [[mmss(a["t"]), a["type"], f'{a["x"]}, {a["z"]}',
                (f'+{a["seenAfter"]} s' if a["seenAfter"] is not None else '<span class="bad">never</span>')] for a in arr]
    S = I["series"]
    army = chart([("army seen (last 60 s)", ME, [(t, s) for t, s, _, _, _ in S], ""),
                  ("true army", THEM, [(t, v) for t, _, v, _, _ in S], "5 3")], t_end, h=180, ylabel="army value")
    prod = chart([("production buildings seen", ME, [(t, s) for t, _, _, s, _ in S], ""),
                  ("true", THEM, [(t, v) for t, _, _, _, v in S], "5 3")], t_end, h=140, ylabel="buildings",
                 fmt=lambda v: f"{v:.0f}")
    return f"""<section><h2>Inference · what you could know (your sight)</h2>
<p class="note">Only what your units and buildings saw (the game's visibility flags), compared with the truth: the gap is
what scouting missed.</p>
<h3>Their age-up intention</h3>
<p>Their villagers you saw in the minute before their age-up was announced, the read from that, and their true split then.</p>
{_tbl(["landmark", "announced", "seen f / w / g / s", "read (seen)", "true f / w / g / s", "read (true)", ""], sp_rows)}
<h3>Their farm switch</h3><p>{farm}</p>
<h3>Their new food and gold</h3>
<p>Each time their villagers started on a new natural food or gold spot, and how long until you saw them there
(Paper Cut: keep a unit on patrol where their next food is). Seen {seen_n} of {len(arr)}.</p>
<details><summary>All spots</summary>{_tbl(["started", "type", "x, z", "you saw it"], ar_rows)}</details>
<h3>Their army and production</h3>
<p>Army value of their units you saw in the last 60 s (can include units that died since: you wouldn't know), production
buildings you have seen and that still stand, vs the truth.</p>
{army}{legend([("seen (last 60 s)", ME), ("true (dashed)", THEM)])}
{prod}
</section>"""


def sections(B, me, them, mmss, chart, legend):
    L = B.get("lenses")
    if not L:
        return f'<section><h2>Hindsight / foresight / inference</h2><p class="note">Not available: {esc(B.get("lensesError") or "1v1 games with both starting TCs only")}.</p></section>'
    t_end = B["t_end"]
    return (hindsight(L, me, them, mmss, chart, legend, t_end) + foresight(L, me, them, mmss, chart, legend, t_end)
            + inference(L, me, them, mmss, chart, legend, t_end))
