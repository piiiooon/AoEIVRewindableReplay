"""Spikes page for one game (review only, full information): views/<name>.spikes.html.

    python viewer/build_spikes.py work/<name>.spikes.json views/<name>.spikes.html

Reads analyzer/spikes.py's output. Sections: army value and the gap (main lines) with spikes and fights marked;
the cause lines (income per minute, army produced per minute, villagers); each spike as a parent line with its
measured details as children; fights by line (frontline / backline); composition swaps and rally points; how long
each resource node lasted while worked.
"""
import argparse
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_basics import chart, legend, mmss  # noqa: E402

esc = html.escape
COL = {0: "var(--p1)", 1: "var(--p2)"}


def num(v, sign=False):
    if v is None:
        return "–"
    return f"{v:+,.0f}" if sign else f"{v:,.0f}"


def arrow(pair, unit=""):
    a, b = pair
    if a is None and b is None:
        return "–"
    ch = ""
    if a and b is not None:
        ch = f" ({(b - a) / a:+.0%})"
    return f"{num(a)} → {num(b)}{unit}{ch}"


def page(D):
    P = D["players"]
    idx = [p["idx"] for p in P]
    name = {p["idx"]: f"{p['name']} ({p['civ']})" for p in P}
    col = {p: COL[i % 2] for i, p in enumerate(idx)}
    t_end = D["t_end"]
    S = D["series"]

    def line(key, p, dash=""):
        return (name[p], col[p], [(s["t"], s[key]) for s in S[str(p)]], dash)
    marks = [(s["t1"], ("▲" if s["kind"] == "age" else "◆" if s["kind"] == "tech" else "●") + " " +
              s["name"].split(": ", 1)[-1][:18], col[s["p"]]) for s in D["spikes"]]
    fmarks = [(f["start"], f"F{f['n']}", "var(--axis)") for f in D["fights"]]
    lines = [line("army", p) for p in idx]
    if len(idx) == 2:
        a, b = idx
        gap = [(x["t"], x["army"] - y["army"]) for x, y in zip(S[str(a)], S[str(b)])]
        lines.append((f"gap ({P[0]['name']} − {P[1]['name']})", "var(--ink)", gap, "4 3"))
    sec1 = (f"<section><h2>1 · Army value and the gap</h2><p>Value of each side's army in the field (resources "
            f"spent on the units alive). The dashed line is the gap: above 0, {esc(P[0]['name'])} is ahead. "
            f"▲ age-up, ◆ unique tech, ● first unique unit; F = fight.</p>"
            + chart(lines, t_end, h=260, marks=marks + fmarks, ylabel="army value")
            + legend([(name[p], col[p]) for p in idx] + [("gap", "var(--ink)")]) + "</section>")
    sec2 = ("<section><h2>2 · The causes</h2><p>Income per minute (all resources gathered over the last minute: "
            "every eco spike shows here: villagers, eco techs, a second TC, relics, trade), army produced per minute "
            "(value of military units as they come out, not when queued), villagers.</p>"
            "<h3>Income per minute</h3>" + chart([line("income", p) for p in idx], t_end, h=180, marks=marks)
            + "<h3>Army produced per minute</h3>" + chart([line("output", p) for p in idx], t_end, h=180, marks=marks)
            + "<h3>Villagers</h3>" + chart([line("vil", p) for p in idx], t_end, h=160, marks=marks)
            + legend([(name[p], col[p]) for p in idx]) + "</section>")

    # spikes: parent + children
    items = []
    for s in D["spikes"]:
        who = name[s["p"]]
        if s["led"]:
            head = (f"<b>{mmss(s['t1'])}</b> {esc(who)} · {esc(s['name'])}: army lead +{num(s['peak_gain'])} "
                    f"(peak {mmss(s['peak_t'])}), lasted {num(s['dur'])} s · <i>{esc(s['why'])}</i>")
        else:
            head = (f"<b>{mmss(s['t1'])}</b> {esc(who)} · {esc(s['name'])}: <span class='mute'>no army lead within "
                    f"{D['params']['LOOK'] // 60:.0f} min</span>")
        ch = [f"eco (true): income {arrow(s['income'], '/min')}, villagers {arrow(s['vil'])}, "
              f"per villager {arrow(s['per_vil'], '/min')}",
              f"production (true): army output {arrow(s['output'], '/min')}",
              f"armies at the spike (true): {num(s['army_at'])} vs {num(s['their_army_at'])}; "
              f"gap before {num(s['base_gap'], True)}",
              f"visibility: {esc(s['seen'])}"]
        if s["t1"] > s["t0"]:
            ch.insert(0, f"started {mmss(s['t0'])} (placed / research started), done {mmss(s['t1'])}"
                      + (f"; idle villagers meanwhile ≈ {num(s['build_idle'])}" if s.get("build_idle") else ""))
        for f in s.get("fights") or []:
            res = "good" if f["killed"] > f["lost"] else "bad" if f["lost"] > f["killed"] else "mute"
            ch.append(f"<span class='{res}'>fight {f['n']} at {mmss(f['t'])}: lost {num(f['lost'])}, "
                      f"killed {num(f['killed'])}</span>")
        items.append(f"<li><span style='color:{col[s['p']]}'>■</span> {head}<ul>"
                     + "".join(f"<li>{c}</li>" for c in ch) + "</ul></li>")
    sec3 = (f"<section><h2>3 · Spikes</h2><p>A spike counts as an army lead when the gap moves at least "
            f"{num(D['params']['MIN_GAIN'])} in the player's favour against the gap in the "
            f"{D['params']['WIN'] / 60:g} min before it; it lasts until the gap is back to that level (caught up), "
            f"its landmark is destroyed, or the game ends. Before → after = {D['params']['WIN']:.0f} s before it "
            f"started against {D['params']['WIN']:.0f} s after it was done. True values = hindsight (the opponent "
            f"couldn't see them).</p><ul class='sp'>{''.join(items) or '<li>none found</li>'}</ul></section>")

    # fights by line
    rows = []
    for f in D["fights"]:
        cells = []
        for p in idx:
            sv, lo = f["start_value"][str(p)], f["lost"][str(p)]
            parts = [f"{k} {num(lo[k])}/{num(sv[k])}" for k in ("front", "back", "siege") if sv[k] or lo[k]]
            rem = f["remain"][str(p)]
            cells.append(("; ".join(parts) or "–") + (f" · {rem:.0%} left" if rem is not None else ""))
        col_ = "; ".join(f"{esc(name[c['p']].split(' (')[0])} {c['line']} at {mmss(c['t'])}" for c in f["collapse"]) or "–"
        rows.append(f"<tr><td>F{f['n']}</td><td class='nw'>{mmss(f['start'])}–{mmss(f['end'])}</td>"
                    + "".join(f"<td>{esc(c)}</td>" for c in cells) + f"<td>{col_}</td></tr>")
    sec4 = ("<section><h2>4 · Fights by line</h2><p>Per side: value lost / value engaged (in the fight at its start, plus reinforcements that died in it), per line "
            "(front = melee, back = ranged, siege), and how much was left. Collapsed = a line lost half its value; "
            "listed in order.</p><table><tr><th></th><th>when</th>"
            + "".join(f"<th>{esc(name[p])}</th>" for p in idx) + "<th>collapsed first</th></tr>"
            + "".join(rows) + "</table></section>")

    # composition and rallies
    comp = []
    for p in idx:
        for c in D["comp"].get(str(p)) or []:
            mix = ", ".join(f"{k} {v}" for k, v in c["mix"].items())
            comp.append((c["t"], f"<tr><td class='nw'>{mmss(c['t'])}</td><td style='color:{col[p]}'>{esc(name[p])}</td>"
                                 f"<td>{esc(c['from'])} → <b>{esc(c['to'])}</b></td><td class='mute'>{esc(mix)}</td></tr>"))
    ral = []
    for p in idx:
        for r in D["rally"].get(str(p)) or []:
            ral.append((r["t"], f"<tr><td class='nw'>{mmss(r['t'])}</td><td style='color:{col[p]}'>{esc(name[p])}</td>"
                                f"<td>{esc(r['region'])}</td><td>{esc(r['army'] or '–')}</td>"
                                f"<td>{'<b class=warn>defensive</b>' if r['defensive'] else ''}</td></tr>"))
    rally_note = ("" if D["rally"] else "<p class='mute'>No rally data: the replay file wasn't found "
                  "(spikes.py --replay).</p>") + (f"<p class='bad'>{esc(D['rallyError'])}</p>" if D.get("rallyError") else "")
    sec5 = ("<section><h2>5 · Composition swaps and rally points</h2><p>Swap = the unit type produced most in a "
            "minute changes (both minutes with 3+ units). Rally = where a military building's rally point was set "
            "(base = within 10 tiles of the TC, then thirds of the line between the TCs: mine / middle / theirs), "
            "with where that player's army was; a rally home while the army is forward is marked defensive. "
            "Rallies changed back within 10 s are left out.</p>"
            "<h3>Composition</h3><table><tr><th>minute</th><th>player</th><th>swap</th><th>that minute</th></tr>"
            + "".join(r for _, r in sorted(comp)) + "</table><h3>Rally points</h3>" + rally_note
            + ("<table><tr><th>when</th><th>player</th><th>rally</th><th>army</th><th></th></tr>"
               + "".join(r for _, r in sorted(ral)) + "</table>" if ral else "") + "</section>")

    # nodes
    nrows = []
    for n in D["nodes"]:
        p = n["player"]
        amt = f"{n['trees']} trees" if "trees" in n else num(n.get("amount"))
        rate = (f"{n['rate']} trees/min" if "trees" in n else f"{num(n['rate'])}/min") if n.get("rate") is not None else "–"
        why = n["why"] + (f" ({num(n['left'])} left)" if n.get("left") and "abandon" in n["why"] else "")
        nrows.append(f"<tr><td style='color:{col.get(p, 'inherit')}'>■</td><td>{esc(n['type'])}</td><td>{esc(n['region'])}</td>"
                     f"<td class='nw'>{mmss(n['start'])}–{mmss(n['end'])}</td><td>{num(n['lasted'])} s</td>"
                     f"<td>{num(n['worked'])} s</td><td>{num(n['vil_s'])}</td><td>{amt}</td><td>{rate}</td>"
                     f"<td>{esc(why)}</td></tr>")
    sec6 = ("<section><h2>6 · Resource nodes</h2><p>Per player, each stretch a node was worked (a break of over "
            "1 min, 2 for wood, starts a new one): lasted = first to last gathering, worked = time with someone on it, "
            "villager-seconds, amount taken, rate while worked, how it ended. Berry patches, deer packs and the sheep "
            "at one drop site count as one node; wood per forest patch (trees cut, from the dump's checks: coarse).</p>"
            "<table><tr><th></th><th>node</th><th>where</th><th>when</th><th>lasted</th><th>worked</th>"
            "<th>villager-s</th><th>taken</th><th>rate</th><th>end</th></tr>" + "".join(nrows) + "</table>"
            + legend([(name[p], col[p]) for p in idx]) + "</section>")

    title = "Spikes: " + " vs ".join(p["name"] for p in P)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>
:root{{--bg:#f7f7f5;--card:#ffffff;--ink:#1d1d1b;--mute:#6b6b66;--grid:#e3e3dd;--axis:#9a9a92;--p1:#2a6fdb;--p2:#d9622b;
--good:#2f8a55;--bad:#c23a2b;--warn:#b07a16}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171715;--card:#20201d;--ink:#ececE6;--mute:#9a9a92;--grid:#30302b;
--axis:#5c5c55;--p1:#6b9cf0;--p2:#f08a55;--good:#5cc488;--bad:#ef6b58;--warn:#d9a441}}}}
body{{background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,sans-serif;margin:24px 16px;max-width:1000px}}
h1{{font-size:20px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 6px}} h3{{font-size:14px;margin:14px 0 2px}}
p{{margin:4px 0 8px}} .sub,.mute{{color:var(--mute)}} section{{background:var(--card);border:1px solid var(--grid);
border-radius:10px;padding:14px 16px;margin:14px 0;overflow-x:auto}} .tk{{font-size:10px;fill:var(--mute)}}
table{{border-collapse:collapse;margin:6px 0;font-variant-numeric:tabular-nums;font-size:13px}}
th,td{{padding:3px 12px 3px 0;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}}
th{{color:var(--mute);font-weight:500}} .nw{{white-space:nowrap}} .good{{color:var(--good)}} .bad{{color:var(--bad)}}
.warn{{color:var(--warn)}} .lg{{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mute);margin:2px 0 6px}}
.lg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
ul.sp{{padding-left:18px}} ul.sp>li{{margin:8px 0}} ul.sp ul{{margin:2px 0;padding-left:20px;color:var(--mute);font-size:13px}}
</style></head><body>
<h1>{esc(title)}</h1>
<p class="sub">{' vs '.join(esc(p['civ']) for p in P)} · {mmss(t_end)} · review page: true values for both players
(hindsight). Charts: time in minutes.</p>
{sec1}{sec2}{sec3}{sec4}{sec5}{sec6}
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spikes")
    ap.add_argument("out")
    a = ap.parse_args()
    with open(a.spikes, encoding="utf-8") as fh:
        D = json.load(fh)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(page(D))
    print("spikes page:", a.out)


if __name__ == "__main__":
    main()
