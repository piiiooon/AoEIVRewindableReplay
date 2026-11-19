"""Basics page for one game (review only, full information): views/<name>.basics.html.

    python viewer/build_basics.py work/<name>.analyzed.json views/<name>.basics.html --player <part of my name>

Checks (owner's rules, 2026-10-26; analyzer/basics.py): who gathered more and floated, why I fell behind, age-up
saves (villager allocation), spending style, army value and value destroyed, trades (value lost, minutes of income),
aggression clock (minutes left in the natural nodes being worked).
"""
import argparse
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "analyzer"))

from analyze import load_costs  # noqa: E402
from basics import basics, RES  # noqa: E402
from gamedata import resolve  # noqa: E402
from lens_sections import sections as lens_sections  # noqa: E402

ME, THEM = "var(--me)", "var(--them)"
STYLE_COL = {"turbo": "var(--turbo)", "spending": "var(--spend)", "trickle": "var(--trickle)",
             "saving": "var(--saving)", "floating": "var(--hard)", "floating (soft)": "var(--soft)",
             "banking": "var(--bankc)"}
STYLE_TXT = {"turbo": "turbo (spending ≥ 90 % of income, mostly army, bank < 400)",
             "spending": "spending (≥ 90 % of income)", "trickle": "trickle (spending 40–90 %: bank creeping up, no save)",
             "saving": "saving for an age-up", "floating": "floating (hard)", "floating (soft)": "floating (soft)",
             "banking": "banking (spending < 40 %, no save)"}
esc = html.escape


OPENING = 60.0     # analyzer/basics.py OPENING


def mmss(t):
    t = int(round(t or 0))
    return f"{t // 60}:{t % 60:02d}"


def chart(lines, t_end, h=220, w=900, bands=(), marks=(), ymax=None, ylabel="", fmt=lambda v: f"{v:,.0f}"):
    """lines: [(label, color, [(t, v)], dash)]; bands: [(t0, t1, color, lane)] drawn under the axis;
    marks: [(t, label, color)] vertical markers"""
    pl, pr, pt, pb = 52, 10, 10, 26 + 8 * (max([b[3] for b in bands], default=-1) + 1)
    vals = [v for _, _, pts, _ in lines for _, v in pts if v is not None]
    top = ymax or (max(vals) if vals else 1) * 1.08 or 1
    bot = min(0, min(vals) if vals else 0)
    X = lambda t: pl + (t / t_end) * (w - pl - pr)  # noqa: E731
    Y = lambda v: pt + (1 - (v - bot) / (top - bot)) * (h - pt - pb)  # noqa: E731
    g = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{esc(ylabel)}">']
    for k in range(5):
        v = bot + (top - bot) * k / 4
        g.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--grid)"/>'
                 f'<text x="{pl - 6}" y="{Y(v) + 3:.1f}" class="tk" text-anchor="end">{esc(fmt(v))}</text>')
    if bot < 0:
        g.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--axis)"/>')
    for m in range(0, int(t_end // 60) + 1, max(1, int(t_end // 60) // 12 or 1)):
        g.append(f'<text x="{X(m * 60):.1f}" y="{h - pb + 14}" class="tk" text-anchor="middle">{m}</text>')
    for t0, t1, col, lane in bands:
        y = h - pb + 18 + lane * 8
        g.append(f'<rect x="{X(t0):.1f}" y="{y}" width="{max(1.5, X(t1) - X(t0)):.1f}" height="6" rx="1.5" fill="{col}">'
                 f'<title>{mmss(t0)}–{mmss(t1)}</title></rect>')
    for k, (t, lab, col) in enumerate(sorted(marks)):
        g.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{pt}" y2="{h - pb}" stroke="{col}" stroke-dasharray="2 3"/>'
                 f'<text x="{X(t) + 3:.1f}" y="{pt + 9 + 11 * (k % 2)}" class="tk">{esc(lab)}</text>')
    for lab, col, pts, dash in lines:
        pts = [(t, v) for t, v in pts if v is not None]
        if len(pts) < 2:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(t):.1f},{Y(v):.1f}" for i, (t, v) in enumerate(pts))
        g.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" {"stroke-dasharray=" + chr(34) + dash + chr(34) if dash else ""}>'
                 f'<title>{esc(lab)}</title></path>')
    g.append("</svg>")
    return "".join(g)


def legend(items):
    return '<div class="lg">' + "".join(
        f'<span><i style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>"


def page(tl, B, me, them, lang="en"):
    pl = {p["idx"]: p for p in tl["players"]}
    M, T = B["players"][str(me)], B["players"][str(them)]
    nm = lambda p: esc(str(pl[p]["name"]))  # noqa: E731
    t_end = B["t_end"]
    sm = {r[0]: r for r in M["series"]}
    st = {r[0]: r for r in T["series"]}
    times = sorted(set(sm) & set(st))
    gm = [(t, sm[t][1]) for t in times]
    gt = [(t, st[t][1]) for t in times]
    lm = [(L["t"], "✕" if L["cancelled"] else f"age {L['age'] + 1 if L['age'] else '?'}", ME)
          for L in M["landmarks"]] + [(L["t"], "", THEM) for L in T["landmarks"] if not L["cancelled"]]
    fl_b = [(f["t0"], f["t1"], "var(--hard)" if f["grade"] == "hard" else "var(--soft)", 0) for f in M["floats"]] + \
           [(f["t0"], f["t1"], "var(--hard)" if f["grade"] == "hard" else "var(--soft)", 1) for f in T["floats"]]

    def at(series, T_):
        best = min(series, key=lambda r: abs(r[0] - T_)) if series else None
        return best if best and abs(best[0] - T_) <= 10 else None
    snap = []
    for T_ in (300, 600, 900, 1200, 1500, t_end):
        a, b = at(M["series"], T_), at(T["series"], T_)
        if a and b and (T_ == t_end or T_ < t_end - 30):
            snap.append((T_, a[1], b[1]))
    snap_rows = "".join(
        f"<tr><td>{mmss(t)}</td><td>{a:,}</td><td>{b:,}</td><td class='{'good' if a >= b else 'bad'}'>{a - b:+,}"
        f" ({(a - b) / max(1, b):+.0%})</td></tr>" for t, a, b in snap)

    def float_sum(F):
        h = [f for f in F if f["grade"] == "hard"]
        s = [f for f in F if f["grade"] == "soft"]
        return (f"{len(h)} hard ({sum(f['t1'] - f['t0'] for f in h)} s), "
                f"{len(s)} soft ({sum(f['t1'] - f['t0'] for f in s)} s)")
    sec1 = f"""<section><h2>1 · Who gathered more, who floated</h2>
<p>Rule: the player who gathers more in total and does not float (unless saving for an age-up) wins.</p>
{chart([(f"{nm(me)} gathered", ME, gm, ""), (f"{nm(them)} gathered", THEM, gt, "")], t_end, bands=fl_b, marks=lm, ylabel="gathered")}
{legend([(f"{pl[me]['name']} (you)", ME), (str(pl[them]['name']), THEM), ("hard float", "var(--hard)"), ("soft float", "var(--soft)")])}
<p class="note">Lanes under the axis: floats, you (upper) and them (lower). Dashed lines: landmark starts (✕ = cancelled).</p>
<table><tr><th>time</th><th>you</th><th>them</th><th>difference</th></tr>{snap_rows}</table>
<p>Floating until 200 pop, ages saved for excluded — you: {float_sum(M['floats'])}; them: {float_sum(T['floats'])}.</p>
</section>"""

    # 2. deficits
    defs = B.get("deficits", {}).get(str(me), [])
    rows = []
    for d in defs:
        diffs = []
        for r in RES:
            a, b = d["mineVils"][r], d["theirVils"][r]
            if abs(a - b) >= 1:
                diffs.append(f"{r} {a:g} vs {b:g}")
        rows.append(f"<tr><td>{mmss(d['t0'])}–{mmss(d['t1'])}</td><td class='bad'>−{d['gap']:,}</td>"
                    f"<td>{sum(d['mineVils'].values()):.0f} vs {sum(d['theirVils'].values()):.0f}</td>"
                    f"<td>{'; '.join(diffs) or '–'}</td><td>{d['mineIdle']:g} vs {d['theirIdle']:g}</td>"
                    f"<td>{d['mineLost']} vs {d['theirLost']}</td><td>{d['minePerVil']:g} vs {d['theirPerVil']:g}</td></tr>")
    sec2 = f"""<section><h2>2 · When you fell behind, what was different</h2>
<p>Stretches of 60 s or more where your gathering rate was below theirs (gap of 100 or more). Values: you vs them,
averaged over the stretch; villagers lost from 60 s before it.</p>
{"<table><tr><th>when</th><th>gap</th><th>villagers working</th><th>split difference</th><th>idle</th><th>villagers lost</th><th>gathered / villager / min</th></tr>" + "".join(rows) + "</table>" if rows else "<p class='good'>No stretch where you fell behind.</p>"}
</section>"""

    # 3. saves
    srows = []
    for s in M["saves"]:
        slow = s["ideal"] is not None and s["took"] - s["ideal"] > max(15, 0.15 * s["took"])
        late = (s.get("placeDelay") or 0) >= 8
        why = ""
        iv = s.get("idealVils") or {}
        if slow and iv:
            diff = sorted(((s["vils"][r] - iv.get(r, 0), r) for r in RES), key=lambda x: x[0])
            lo, hi = diff[0], diff[-1]
            parts = []
            if hi[0] >= 0.8:
                parts.append(f"{hi[1]} +{hi[0]:.1f}")
            if lo[0] <= -0.8:
                parts.append(f"{lo[1]} {lo[0]:.1f}")
            why = "slow: " + (", ".join(parts) + " villagers vs ideal" if parts else "split close to ideal")
            if s["woodShare"] >= 0.2 and hi[1] == "wood":
                why += " (over-rallied into wood)"
        elif slow:
            why = "slow"
        if late:
            why = (why + "; " if why else "") + f"affordable at {mmss(s['afford'])}, placed {s['placeDelay']} s later"
        vils = ", ".join(f"{r} {v:g}" for r, v in s["vils"].items() if v >= 0.5)
        ivs = ", ".join(f"{r} {v:g}" for r, v in iv.items() if v >= 0.5) if iv else "–"
        srows.append(f"<tr><td>{esc(s['name'])}</td><td class='nw'>{mmss(s['t0'])}–{mmss(s['t1'])}</td>"
                     f"<td>{' + '.join(f'{v} {r}' for r, v in s['need'].items())}</td><td>{vils}</td><td>{ivs}</td>"
                     f"<td class='nw'>{s['took']} s</td><td class='nw'>{'–' if s['ideal'] is None else str(s['ideal']) + ' s'}</td>"
                     f"<td class='{'bad' if slow or late else 'good'}'>{why or 'ok'}</td></tr>")
    sec3 = f"""<section><h2>3 · Saving for an age-up</h2>
<p>From the moment the needed bank starts climbing to the landmark start. Ideal: the same number of eco villagers,
split so every needed resource arrives at once, after covering what you spent meanwhile (villagers, houses) and
counting passive income. Flagged when it took 15 % (and 15 s) longer than that, or when the landmark went down 8 s
or more after the bank already covered it.</p>
{"<table><tr><th>landmark</th><th>save</th><th>cost</th><th>your villagers (avg)</th><th>ideal split</th><th>took</th><th>ideal</th><th></th></tr>" + "".join(srows) + "</table>" if srows else "<p>No landmark started.</p>"}
</section>"""

    # 4. style
    def strip(S):
        g = ['<svg viewBox="0 0 900 22" width="100%" preserveAspectRatio="none" role="img" aria-label="spending style">']
        for x in S:
            x0, x1 = 52 + x["t0"] / t_end * 838, 52 + x["t1"] / t_end * 838
            g.append(f'<rect x="{x0:.1f}" y="3" width="{max(1, x1 - x0 - 0.5):.1f}" height="16" fill="{STYLE_COL[x["kind"]]}">'
                     f'<title>{mmss(x["t0"])}–{mmss(x["t1"])} {x["kind"]}: income {x["income"]}/min, spent {x["spend"]}/min '
                     f'(army {x["army"]}), bank {x["bank"]}</title></rect>')
        g.append("</svg>")
        return "".join(g)

    def shares(S):
        tot = sum(x["t1"] - x["t0"] for x in S) or 1
        c = {}
        for x in S:
            c[x["kind"]] = c.get(x["kind"], 0) + x["t1"] - x["t0"]
        return ", ".join(f"{k} {v / tot:.0%}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))
    frows = "".join(f"<tr><td>{mmss(f['t0'])}–{mmss(f['t1'])}</td><td class='{'bad' if f['grade'] == 'hard' else 'warn'}'>"
                    f"{f['grade']}</td><td>{f['res']}</td><td>{f['peak']:,}</td><td>{f['t1'] - f['t0']} s</td></tr>"
                    for f in M["floats"])
    sec4 = f"""<section><h2>4 · Spending style</h2>
<p>Every 30 s. Hover a block for income, spending (army part) and bank.</p>
<div class="strip"><b>you</b>{strip(M['style'])}</div><div class="strip"><b>them</b>{strip(T['style'])}</div>
{legend([(STYLE_TXT[k], v) for k, v in STYLE_COL.items()])}
<p>You: {shares(M['style'])}.<br>Them: {shares(T['style'])}.</p>
{"<table><tr><th>your floats</th><th>grade</th><th>resource</th><th>peak</th><th>how long</th></tr>" + frows + "</table>" if frows else "<p class='good'>You did not float.</p>"}
<p class="note">Hard: ≥ 500 of one resource for ≥ 60 s; soft: ≥ 300 for ≥ 30 s; until 200 pop; resources of an
age-up being saved for are not counted.</p>
</section>"""

    # 5. army
    def cum_lost(D):
        out, s = [(0, 0)], 0
        for t, v in sorted(D["deaths"]["army_t"]):
            s += v
            out.append((t, s))
        out.append((t_end, s))
        return out
    am = [(t, sm[t][3]) for t in times]
    at_ = [(t, st[t][3]) for t in times]
    dm, dt_ = M["deaths"], T["deaths"]
    sec5 = f"""<section><h2>5 · Army value and value destroyed</h2>
{chart([("your army", ME, am, ""), ("their army", THEM, at_, ""), ("you destroyed (their army lost)", ME, cum_lost(T), "5 4"),
        ("they destroyed (your army lost)", THEM, cum_lost(M), "5 4")], t_end, ylabel="army value")}
{legend([("army value (solid)", "var(--ink)"), ("army destroyed so far (dashed)", "var(--mute)"), ("you", ME), ("them", THEM)])}
<table><tr><th></th><th>army lost</th><th>villagers lost</th><th>buildings lost</th></tr>
<tr><td>you</td><td>{dm['value']['army']:,} ({dm['count']['army']})</td><td>{dm['value']['villager']:,} ({dm['count']['villager']})</td><td>{dm['value']['building']:,} ({dm['count']['building']})</td></tr>
<tr><td>them</td><td>{dt_['value']['army']:,} ({dt_['count']['army']})</td><td>{dt_['value']['villager']:,} ({dt_['count']['villager']})</td><td>{dt_['value']['building']:,} ({dt_['count']['building']})</td></tr></table>
</section>"""

    # 6. trades
    trows = []
    net_val = net_min = 0.0
    for f in B.get("trades", []):
        a, b = f["lost"][str(me)], f["lost"][str(them)]
        ma, mb = f["minutes"][str(me)], f["minutes"][str(them)]
        net_val += b - a
        if ma is not None and mb is not None:
            net_min += mb - ma
        if abs(a - b) <= 0.1 * max(a, b, 1):
            v, cls = "even", ""
        elif b > a:
            v, cls = "good trade", "good"
        else:
            v, cls = "bad trade", "bad"
        note = []
        if a > b and ma is not None and mb is not None and ma < mb:
            note.append("lost more, but a smaller share of your income: net gain")
        if b > a and ma is not None and mb is not None and ma > mb:
            note.append("won the value, but it cost you more minutes of income")
        for side, lost_m, who in ((str(me), ma, "you"), (str(them), mb, "they")):
            if lost_m is not None and lost_m >= 1.5:
                note.append(f"{who} need {lost_m:.1f} min of income to replace it")
        if f["vilLost"][str(me)] or f["vilLost"][str(them)]:
            note.append(f"villagers lost {f['vilLost'][str(me)]} vs {f['vilLost'][str(them)]}")
        trows.append(f"<tr><td>{mmss(f['t0'])}</td><td>{a:,}</td><td>{b:,}</td><td class='{cls} nw'>{v}</td>"
                     f"<td>{'–' if ma is None else f'{ma:.1f}'}</td><td>{'–' if mb is None else f'{mb:.1f}'}</td>"
                     f"<td>{'; '.join(note)}</td></tr>")
    sec6 = f"""<section><h2>6 · Trades</h2>
<p>Each fight: value lost by each side first (resources). Second: the same as minutes of that side's income at the
time — a side that trades badly can still come out ahead if it replaces the losses faster and keeps units coming,
taxing the other side's bank.</p>
{"<table><tr><th>at</th><th>you lost</th><th>they lost</th><th>value</th><th>your min of income</th><th>their min of income</th><th></th></tr>" + "".join(trows) + "</table>" if trows else "<p>No fights with 100+ value lost.</p>"}
<p>Over all fights: value {'+' if net_val >= 0 else ''}{net_val:,.0f} in your favour; income
{'+' if net_min >= 0 else ''}{net_min:.1f} min in your favour.</p>
</section>"""

    # 7. clock
    def clock_lines(C, col, who):
        out = []
        for kind, dash in (("food", ""), ("gold", "5 3")):
            pts = [(c["t"], min(20.0, c[kind]["minutes"]) if c[kind]["minutes"] is not None else None) for c in C]
            out.append((f"{who} {kind}", col, pts, dash))
        return out
    sec7 = f"""<section><h2>7 · Aggression clock</h2>
<p>Minutes left in the natural nodes each side was working in the last minute (food: berries, deer, sheep,
carcasses, boar; gold mines), at the rate they were being emptied. When it runs low, that side has to move to farms
or a new mine: pressure that rests on those nodes has that long. Capped at 20 min.</p>
{chart(clock_lines(M['clock'], ME, 'you') + clock_lines(T['clock'], THEM, 'them'), t_end, ymax=20, ylabel="minutes left", fmt=lambda v: f"{v:.0f}")}
{legend([("food (solid)", "var(--ink)"), ("gold (dashed)", "var(--mute)"), ("you", ME), ("them", THEM)])}
</section>"""

    # 8. overqueue (owner 2026-10-26: more than 2 queued per production building)
    def oq_block(O, who):
        if not O or not O["episodes"]:
            return f"<p><b>{who}</b>: never more than 2 queued.</p>"
        rows_ = []
        names = list(O["byBuilding"]) + sorted({e[3] for e in O["episodes"]} - set(O["byBuilding"]))
        for k in names:
            eps = [e for e in O["episodes"] if e[3] == k]
            bars = "".join(
                f'<span title="{mmss(a)}-{mmss(b)}, peak {q}{" (opening)" if a < OPENING else ""}" style="position:absolute;'
                f'left:{100 * a / t_end:.2f}%;width:{max(0.3, 100 * (b - a) / t_end):.2f}%;top:2px;bottom:2px;'
                f'background:var({"--soft" if q == 3 else "--hard"});opacity:{0.35 if a < OPENING else 1}"></span>'
                for a, b, q, _ in eps)
            v = O["byBuilding"].get(k) or {"n": 0, "secs": 0, "longest": 0, "peak": "–", "firstAfter": None}
            rows_.append(f'<tr><td class="nw">{esc(k)}</td><td style="width:55%"><div style="position:relative;height:14px;'
                         f'background:var(--grid);border-radius:3px">{bars}</div></td><td>{v["n"]}</td><td>{v["secs"]} s</td>'
                         f'<td>{v["longest"]} s</td><td>{v["peak"]}</td>'
                         f'<td>{mmss(v["firstAfter"]) if v["firstAfter"] is not None else "–"}</td></tr>')
        return (f"<p><b>{who}</b>: {O['secsAfterOpening']} s overqueued after the first minute"
                + (f" (opening queue {O['openingSecs']} s)" if O.get("openingSecs") else "")
                + (f", first at {mmss(O['firstAfterOpening'])}" if O["firstAfterOpening"] is not None else "") + ".</p>"
                "<table><tr><th>building</th><th>when</th><th>times</th><th>total</th><th>longest</th><th>peak</th>"
                "<th>first after 1:00</th></tr>" + "".join(rows_) + "</table>")
    sec8 = f"""<section><h2>8 · Overqueue</h2>
<p>Stretches of 3 s or more where one production building had more than 2 items queued (the game's queue size,
which most likely counts the item being made). Queued items are paid for: that bank is tied up instead of spent
elsewhere. The opening villager queue at the TC (before 1:00) is shown faded and not counted in the totals.</p>
{oq_block(M.get('overqueue'), 'You')}{oq_block(T.get('overqueue'), 'Them')}
{legend([("3 queued", "var(--soft)"), ("4+ queued", "var(--hard)")])}
</section>"""

    title = f"Basics: {pl[me]['name']} vs {pl[them]['name']}"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>
:root{{--bg:#f7f7f5;--card:#ffffff;--ink:#1d1d1b;--mute:#6b6b66;--grid:#e3e3dd;--axis:#9a9a92;--me:#2a6fdb;--them:#d9622b;
--hard:#d23c2a;--soft:#f0b860;--turbo:#2a6fdb;--spend:#7aa6ea;--trickle:#b9b4a8;--saving:#2f9e6a;--bankc:#8a6fc4;
--good:#2f8a55;--bad:#c23a2b;--warn:#b07a16}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171715;--card:#20201d;--ink:#ececE6;--mute:#9a9a92;--grid:#30302b;--axis:#5c5c55;
--me:#6b9cf0;--them:#f08a55;--hard:#ef6b58;--soft:#c9973f;--turbo:#6b9cf0;--spend:#3d5f99;--trickle:#5a5850;--saving:#3fbf85;
--bankc:#9d86d6;--good:#5cc488;--bad:#ef6b58;--warn:#d9a441}}}}
body{{background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,sans-serif;margin:24px 16px;max-width:980px}}
h1{{font-size:20px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 6px}} h3{{font-size:14px;margin:14px 0 2px}}
details summary{{cursor:pointer;color:var(--mute);font-size:12px}} .wrap{{display:inline-block;max-width:260px}} p{{margin:4px 0 8px}} .sub,.note{{color:var(--mute)}}
.note{{font-size:12px}} section{{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:14px 16px;margin:14px 0}}
.tk{{font-size:10px;fill:var(--mute)}} table{{border-collapse:collapse;margin:6px 0;font-variant-numeric:tabular-nums;font-size:13px}}
th,td{{padding:3px 12px 3px 0;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}} th{{color:var(--mute);font-weight:500}}
.nw{{white-space:nowrap}} .good{{color:var(--good)}} .bad{{color:var(--bad)}} .warn{{color:var(--warn)}}
.lg{{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mute);margin:2px 0 6px}}
.lg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.strip{{display:grid;grid-template-columns:44px 1fr;align-items:center;font-size:12px}} .strip b{{font-weight:500;color:var(--mute)}}
</style></head><body>
<h1>{esc(title)}</h1>
<p class="sub">{esc(pl[me]['civ'])} vs {esc(pl[them]['civ'])} · {mmss(t_end)} · review page: uses everything both players had
(true banks, hidden units). Charts: time in minutes.</p>
{sec1}{sec2}{sec3}{sec4}{sec5}{sec6}{sec7}{sec8}
{lens_sections(B, me, them, mmss, chart, legend)}
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("analyzed")
    ap.add_argument("out")
    ap.add_argument("--player", help="part of your in-game name (any case); default: player 1")
    ap.add_argument("--lang", default="en", choices=["en", "ja"])
    ap.add_argument("--json", help="also write the checks as JSON here (for the profile)")
    a = ap.parse_args()
    with open(a.analyzed, encoding="utf-8") as fh:
        tl = json.load(fh)
    if len(tl["players"]) != 2:
        sys.exit("basics page: 1v1 games only")
    tbl, full = load_costs()
    cost_of = lambda bp: tbl.get(resolve(bp, tbl), 0.0)  # noqa: E731
    B = basics(tl, full, cost_of)
    pids = [p["idx"] for p in tl["players"]]
    me = pids[0]
    if a.player:
        hits = [p["idx"] for p in tl["players"] if a.player.casefold() in str(p["name"]).casefold()]
        if len(hits) == 1:
            me = hits[0]
        else:
            print(f"--player {a.player!r}: {'not found' if not hits else 'matches both'}; using player 1")
    them = [p for p in pids if p != me][0]
    out = page(tl, B, me, them, a.lang)
    if a.lang != "en":
        from i18n import translate
        out = translate(out, a.lang)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(out)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(dict(B, me=me, them=them), fh, separators=(",", ":"))
    print("basics:", a.out)


if __name__ == "__main__":
    main()
