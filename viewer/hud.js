// Fogline observer HUD (owner 2026-11-11: the in-game caster bar as the layout; replay viewer and 3D page).
// Data: analyzer/hud.py (D.hud). Full values for both players in every view (owner's choice for this bar).
// FoglineHUD.create({ bar, stats, recap, data, icon(bp), techIcon(attrib), pcolor(idx), civName(code)? }) -> { update(t, show) }
// show = { bar, stats, recap } booleans. Inlined into both pages at build time.
(function () {
  // owner 2026-11-11: food salmon pink, wood brown, gold sunflower yellow, stone ash
  const RES_COL = { food: "#fa8072", wood: "#8b5a2b", gold: "#ffc512", stone: "#b2beb5" };
  const ROMAN = ["", "I", "II", "III", "IV", "V"];
  const RECAP_HOLD = 90;   // arenas: s the recap stays after the fight ends          // s a fight's recap stays up after it ends (minimizable)
  const SEG = ["#e8b04f", "#6aa3e8", "#ec6f6f", "#5cc28a", "#a986e0", "#e0874f", "#4fc3c9", "#c9c94f"];
  const esc = x => String(x == null ? "" : x).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const mmss = s => { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
  const k = v => v >= 10000 ? (v / 1000).toFixed(1) + "k" : Math.round(v).toLocaleString();
  const CSS = `
.fh-bar { display: grid; grid-template-columns: 1fr auto 1fr; gap: 8px; align-items: start; font: 13px system-ui, sans-serif; color: var(--ink); pointer-events: none; }
.fh-side { display: flex; flex-direction: column; gap: 3px; min-width: 0; align-items: flex-start; }
.fh-side.r { align-items: flex-end; }
.fh-box { background: color-mix(in srgb, var(--panel) 86%, transparent); border: 1px solid var(--line); border-radius: 6px; padding: 3px 6px; pointer-events: auto; }
.fh-top { display: flex; gap: 8px; align-items: center; }
.fh-side.r > .fh-box > .fh-top { flex-direction: row-reverse; }
.fh-res { display: grid; grid-template-rows: auto auto auto; justify-items: center; min-width: 54px; line-height: 1.15; }
.fh-res b { font-size: 18px; font-variant-numeric: tabular-nums; }
.fh-res .sw { display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin-right: 3px; vertical-align: 0; }
.fh-res small { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.fh-pop { text-align: center; line-height: 1.15; } .fh-pop b { font-size: 18px; }
.fh-who { line-height: 1.2; } .fh-side.r .fh-who { text-align: right; }
.fh-who b { font-size: 16px; } .fh-who small { color: var(--muted); }
.fh-age { display: inline-grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; border: 2px solid #c9a24a; color: #e8c46a; font: 600 14px Georgia, serif; flex: none; }
.fh-tag { display: inline-block; padding: 1px 6px; border-radius: 3px; background: #6b4f1d; color: #f3d98b; font-size: 11px; margin: 1px; white-space: nowrap; }
.fh-flag { background: #7a1f24; color: #f6e2b0; } .fh-flag::before { content: "⚑ "; }
.fh-row { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; }
.fh-side.r .fh-row { justify-content: flex-end; }
.fh-tic { width: 38px; display: inline-flex; flex-direction: column; align-items: center; }
.fh-tic img, .fh-tic .ch { width: 36px; height: 36px; border-radius: 3px; display: block; background: linear-gradient(#2c9a9e, #17666b); box-shadow: inset 0 0 0 1px #5fd0d4; }
.fh-tic .ch { color: #e6eeff; font-size: 8px; line-height: 9px; overflow: hidden; text-align: center; word-break: break-word; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(#3561a8, #1d3768); box-shadow: inset 0 0 0 1px #7ea3e6; }
.fh-tic.prog img, .fh-tic.prog .ch { opacity: .45; } .fh-tic .pb { display: block; width: 36px; height: 4px; margin-top: 1px; background: var(--line); border-radius: 2px; overflow: hidden; } .fh-tic .pb i { display: block; height: 100%; background: #4fb3e8; }
.fh-gov { display: inline-flex; flex-direction: column; align-items: center; } .fh-gov .nt { display: flex; gap: 1px; margin-top: 1px; } .fh-gov .nt i { width: 7px; height: 4px; border-radius: 1px; background: #e8b04f; }
.fh-tic .nt { display: flex; gap: 1px; height: 5px; margin-top: 1px; } .fh-tic .nt i { width: 8px; height: 4px; background: var(--line); border-radius: 1px; } .fh-tic .nt i.on { background: #e8b04f; }
.fh-prod { display: inline-flex; align-items: center; gap: 2px; margin-right: 4px; }
.fh-prod img, .fh-prod .ch { width: 32px; height: 32px; border-radius: 3px; } .fh-prod .ch { background: var(--line); font-size: 9px; line-height: 32px; overflow: hidden; display: inline-block; text-align: center; }
.fh-lm { display: grid; grid-template-columns: auto 1fr; gap: 1px 6px; align-items: center; min-width: 220px; }
.fh-lm img, .fh-lm .ch { grid-row: 1 / 3; width: 38px; height: 38px; border-radius: 3px; } .fh-lm .ch { background: var(--line); font-size: 9px; line-height: 38px; overflow: hidden; display: inline-block; text-align: center; }
.fh-lm .nm { font-style: italic; } .fh-lm .pb { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; } .fh-lm .pb i { display: block; height: 100%; background: #4f9be8; }
.fh-viz { display: flex; align-items: center; gap: 6px; } .fh-viz .pb { width: 120px; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; } .fh-viz .pb i { display: block; height: 100%; background: #c9a24a; }
.fh-mid { text-align: center; min-width: 210px; }
.fh-midcol { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.fh-sites { display: flex; gap: 6px; justify-content: center; pointer-events: auto; }
.fh-site { width: 34px; height: 34px; cursor: pointer; filter: drop-shadow(0 1px 2px rgba(0,0,0,.6)); }
.fh-cmp { display: grid; grid-template-columns: 30px 1fr 30px; gap: 4px; align-items: center; font-size: 14px; font-variant-numeric: tabular-nums; }
.fh-cmp .bar { height: 8px; border-radius: 3px; overflow: hidden; display: flex; }
.fh-cmp small { grid-column: 1 / 4; color: var(--muted); font-size: 10px; margin-top: -2px; }
.fh-clock { font-size: 16px; font-variant-numeric: tabular-nums; margin-top: 2px; }
.fh-stats { font: 11px system-ui, sans-serif; color: var(--ink); }
.fh-stats table { border-collapse: collapse; } .fh-stats td, .fh-stats th { padding: 1px 7px; font-size: 13px; line-height: 1.3; text-align: right; font-variant-numeric: tabular-nums; }
.fh-stats th { color: var(--muted); font-weight: 400; font-size: 12px; } .fh-stats td:first-child { text-align: left; }
.fh-recap { font: 12px system-ui, sans-serif; color: var(--ink); max-width: 460px; }
.fh-recap h4 { margin: 0 0 3px; font-size: 11px; color: var(--muted); font-weight: 600; }
.fh-rs { margin: 3px 0; } .fh-rs .hd { display: flex; justify-content: space-between; gap: 8px; }
.fh-dbar { display: flex; height: 8px; border-radius: 3px; overflow: hidden; margin: 2px 0; background: var(--line); }
.fh-chips { display: flex; flex-wrap: wrap; gap: 3px; } .fh-chip { display: inline-flex; align-items: center; gap: 2px; font-size: 10px; }
.fh-chip img { width: 20px; height: 20px; border-radius: 2px; } .fh-chip .dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.fh-rtitle { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; padding: 2px 2px 6px; margin-bottom: 4px; border-bottom: 1px solid var(--line); font-size: 13px; }
.fh-rtitle b { font-size: 15px; } .fh-rtitle > span:not(.fh-rviews) { color: var(--muted); font-size: 11px; } .fh-rviews { margin-left: auto; display: flex; gap: 3px; } .fh-rviews .fh-rbtn { font-size: 10px; padding: 1px 6px; }
.fh-tip { position: fixed; z-index: 9999; pointer-events: none; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font: 12px system-ui, sans-serif; box-shadow: 0 6px 24px rgba(0,0,0,.35); max-width: 560px; }
.fh-tip-h { font-weight: 600; margin-bottom: 4px; }
.fh-pies { display: flex; gap: 18px; } .fh-pie { display: flex; flex-direction: column; align-items: center; min-width: 170px; }
.fh-leg div { display: flex; align-items: center; gap: 4px; font-size: 12px; } .fh-leg .dot, .fh-tl .dot { width: 9px; height: 9px; border-radius: 2px; display: inline-block; flex: none; }
.fh-leg .v, .fh-tl .v { margin-left: auto; padding-left: 10px; font-variant-numeric: tabular-nums; color: var(--muted); }
.fh-tl { display: grid; grid-template-columns: 20px 1fr 90px auto; gap: 6px; align-items: center; margin: 2px 0; }
.fh-tl .bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; } .fh-tl .bar i { display: block; height: 100%; background: #e8b04f; }
[data-pie] { cursor: help; }
.fh-vring { position: relative; width: 44px; height: 44px; display: inline-block; flex: none; } .fh-vring svg { position: absolute; inset: 0; }
.fh-vring img, .fh-vring b { position: absolute; left: 9px; top: 9px; width: 26px; height: 26px; border-radius: 50%; text-align: center; line-height: 26px; }
.fh-lmk { display: inline-flex; cursor: pointer; pointer-events: auto; border-radius: 3px; } .fh-lmk:hover { outline: 2px solid #ffd84a; }
.fh-lmk img, .fh-lmk .ch { width: 40px; height: 40px; border-radius: 3px; display: block; } .fh-lmk .ch { background: var(--line); font-size: 9px; line-height: 40px; overflow: hidden; text-align: center; }
.fh-lmk { position: relative; flex-direction: column; } .fh-lmk .pg, .fh-mbar { display: block; height: 4px; background: var(--line); border-radius: 2px; overflow: hidden; margin-top: 1px; } .fh-lmk .pg i, .fh-mbar i { display: block; height: 100%; background: #4f9be8; }
.fh-mbar { width: 30px; display: inline-block; vertical-align: middle; margin-left: 2px; }
.fh-lmk.b { opacity: .45; } .fh-lmk.x { opacity: .35; filter: grayscale(1); position: relative; } .fh-lmk.x::after { content: ""; position: absolute; left: 2px; right: 2px; top: 50%; height: 2px; background: #e23; transform: rotate(-35deg); }
.fh-recap { max-width: 560px; }
.fh-rc { padding: 6px 10px; min-width: 420px; }
.fh-rh { display: flex; justify-content: space-between; align-items: center; gap: 10px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
.fh-rbtn.on { background: #4f9be8; color: #fff; border-color: #4f9be8; }
.fh-rbtn { margin-left: 3px; font: 12px system-ui, sans-serif; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 4px; padding: 2px 8px; cursor: pointer; pointer-events: auto; }
.fh-rcols, .fh-rrow { display: grid; grid-template-columns: 1fr 110px 1fr; gap: 6px; align-items: baseline; }
.fh-rcols b:first-child, .fh-rrow .l { text-align: right; } .fh-rrow .c { text-align: center; color: var(--muted); font-size: 11px; }
.fh-rrow { font-size: 15px; font-variant-numeric: tabular-nums; margin: 2px 0; } .fh-rrow small { color: var(--muted); font-size: 11px; }
.fh-swing { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; margin: 4px 0; font-size: 12px; }
.fh-swing > span:first-child { color: var(--muted); } .fh-swing .bar { position: relative; height: 8px; background: var(--line); border-radius: 4px; }
.fh-swing .bar i { position: absolute; top: 0; height: 100%; border-radius: 4px; } .fh-swing .bar::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--ink); }
.fh-rgrid { display: grid; grid-template-columns: 1fr 70px 1fr; gap: 6px; margin-top: 6px; align-items: start; }
.fh-rmid { text-align: center; color: var(--muted); font-size: 11px; line-height: 1.25; }
.fh-ru { display: grid; grid-template-columns: 32px 1fr 44px; gap: 4px; align-items: center; margin: 2px 0; cursor: help; pointer-events: auto; }
.fh-rside.l .fh-ru { grid-template-columns: 44px 1fr 32px; } .fh-rside.l .fh-ru .ic { order: 3; } .fh-rside.l .fh-ru .n { order: 1; text-align: right; } .fh-rside.l .fh-ru .bar { order: 2; direction: rtl; }
.fh-ru .bar { height: 8px; background: var(--line); border-radius: 4px; overflow: hidden; display: flex; } .fh-ru .bar i { display: block; height: 100%; }
.fh-ru .n { font-variant-numeric: tabular-nums; } .fh-ru .ch { display: inline-block; width: 30px; height: 30px; background: var(--line); font-size: 9px; line-height: 30px; overflow: hidden; text-align: center; border-radius: 3px; }
`;
  function create(o) {
    const H = o.data; if (!H || !H.rows) return { update() {} };
    if (!document.getElementById("fh-css")) { const st = document.createElement("style"); st.id = "fh-css"; st.textContent = CSS; document.head.appendChild(st); }
    // swap (owner 2026-11-13: with some camera angles the armies sit on the other side): P = display order, P0 = data order
    const P0 = H.players.map(p => p.idx), resN = H.res; let P = P0.slice();
    const rowAt = (p, t) => { const R = H.rows[String(p)] || []; let lo = 0, hi = R.length - 1, b = 0;
      while (lo <= hi) { const m = (lo + hi) >> 1; if (R[m][0] <= t) { b = m; lo = m + 1; } else hi = m - 1; } return R[b]; };
    const pinfo = p => H.players.find(x => x.idx === p) || {};
    const img = (src, cls, title) => src ? `<img src="${src}" title="${esc(title)}" alt="">` : `<span class="${cls || "ch"}" title="${esc(title)}">${esc(String(title).slice(0, 5))}</span>`;
    const nice = bp => String(bp || "").replace(/^(building|unit)_/, "").replace(/_(control|ha_\w+|[a-z]{3})$/, "").replace(/_/g, " ");
    function techRows(p, t) {
      // owner 2026-11-11: research in progress too (start = done - research time; hud.py r[7]) - faded icon with a progress
      // bar; notches = stages done of the family's stages; hover = detail text (name, cost, time, effects, stage, attrib)
      const rows = [[], [], []], fam = {}, prog = {};
      for (const r of (H.tech || {})[String(p)] || []) {
        if (SPECIAL.test(r[1])) continue;
        if (r[0] <= t) { if (!fam[r[4]] || r[5] > fam[r[4]][5]) fam[r[4]] = r; }
        else if (r[7] != null && r[7] <= t && (!prog[r[4]] || r[7] < prog[r[4]][7])) prog[r[4]] = r;
      }
      const keys = new Set([...Object.keys(fam), ...Object.keys(prog)]);
      for (const k2 of keys) { const r = prog[k2] || fam[k2]; rows[r[3]].push([r, fam[k2], prog[k2]]); }
      return rows.map(R => !R.length ? "" : `<div class="fh-row">` + R.sort((a, b) => (a[1] ? a[1][0] : 1e9) - (b[1] ? b[1][0] : 1e9) || a[0][0] - b[0][0]).map(([r, d, g]) => {
        const ic = o.techIcon && o.techIcon(r[1]), nd = d ? d[5] : 0;
        const nt = r[6] > 1 ? `<span class="nt">${Array.from({ length: r[6] }, (_, i) => `<i class="${i < nd ? "on" : ""}"></i>`).join("")}</span>` : "";
        const f = g ? Math.max(0, Math.min(1, (t - g[7]) / Math.max(1, g[0] - g[7]))) : 0;
        const pb = g ? `<span class="pb"><i style="width:${(f * 100).toFixed(0)}%"></i></span>` : "";
        const tip = (g ? `researching: ${String(g[8] || g[2]).split("\n")[0]} - ${Math.round(f * 100)} %, done ${mmss(g[0])} (${g[10] === true || g[10] === "event" ? "start recorded" : g[10] === "queue" ? "start from the queue" : "start estimated"}${g[11] != null ? `, clicked ${mmss(g[11])}` : ""})\n\n${g[8] || g[2]}`
          + (d ? `\n\ndone before: ${d[2]} (${mmss(d[0])})` : "") : `${d[8] || d[2]}\ndone ${mmss(d[0])}`);
        return `<span class="fh-tic${g ? " prog" : ""}" title="${esc(tip)}">${ic ? `<img src="${ic}" alt="">` : `<span class="ch">${esc(r[9] || String(r[2]).split(/\s+/).slice(0, 2).join(" ").slice(0, 14))}</span>`}${nt}${pb}</span>`;
      }).join("") + `</div>`).join("");
    }
    // Templar commanderies (age-up flags) and Ottoman vizier picks / points (owner 2026-11-11): attrib names guessed until a
    // recording with them is checked - commander(ie|y) / vizier / imperial_council
    // checked on the owner's otto1 / chn1 logs: upgrade_age_dark_com_1_tem (Knights Hospitaller), upgrade_imperial_*_ott
    // (vizier picks, executed by the player), player_dynasty1_chi (dynasty, hud.py reads it)
    const FLAG_RE = /commander|_com_\d/i, VIZ_RE = /vizier|imperial_.*_ott/i, SPECIAL = /commander|_com_\d|vizier|imperial_.*_ott|player_dynasty|govern/i, GOV_RE = /govern/i;
    // Tughlaq governors (owner 2026-11-11: "like the Knights Templar"): one per Tughlaqabad Fort, six cities; aoe4world has no
    // governor icons, so a city tag with its level notches (the same governor appointed again = next level), in the landmark
    // row after the landmarks. Attrib names unchecked (matched on "govern"; the city from its name / attrib)
    const GOV_CITY = ["ajmer", "bhakkar", "jalor", "multan", "sehwan", "uch"];
    const specials = (p, t, re) => ((H.tech || {})[String(p)] || []).filter(r => r[0] <= t && re.test(r[1]));
    function side(p, t, right) {
      const r = rowAt(p, t), pi = pinfo(p), col = o.pcolor(p);
      const [, bank, rate, vil, idle, pop, cap, age, , , prod, lms] = r, dyn = r[19];
      const vi = resN.findIndex(n => /vizier/i.test(n));
      const res = resN.map((n, i) => i !== vi && (i < 4 || bank[i] > 0 || rate[i] > 0) ? `<div class="fh-res" data-pie="src|${p}|${n}">
        <b><span class="sw" style="background:${RES_COL[n] || "#6fb6c9"}"></span>${k(bank[i])}</b><small>${Math.max(0, rate[i])}/min</small><small>${i < 4 ? vil[i] + " vil" : ""}</small></div>` : "").join("");
      const popc = `<div class="fh-pop" title="population / cap; idle villagers"><b>${Math.round(pop || 0)}</b><small style="color:var(--muted)">/${Math.round(cap || 0)}</small><br><small style="color:${idle ? "#e8b04f" : "var(--muted)"}" title="idle villagers (in brackets: garrisoned, counted as idle)">${idle} idle${r[25] ? ` <span style="color:#9fb4d9">(${r[25]})</span>` : ""}</small></div>`;
      // landmarks row (owner 2026-11-11): landmark icons in order (faded while building, struck when gone); Knights Templar:
      // the age-up commanderie flags instead (their icons; click = their main TC). Click = jump to it, blinking yellow
      const tc = (H.mainTC || {})[String(p)];
      const flagL = specials(p, t, FLAG_RE);
      const lmRow = /templar/i.test(pi.civ || "") || flagL.length
        ? flagL.map(x => { const ic = o.techIcon && o.techIcon(x[1]);
            return `<span class="fh-lmk" ${tc ? `data-focus="${tc[1]},${tc[2]}"` : ""} title="${esc(x[2])} commanderie (${mmss(x[0])}) - click: their Town Center">${ic ? `<img src="${ic}" alt="">` : `<span class="fh-tag fh-flag">${esc(x[2])}</span>`}</span>`; }).join("")
        : ((H.landmarks || {})[String(p)] || []).filter(L => L[0] <= t).map(L => {
            const building = !(L[1] != null && L[1] <= t), gone = L[2] != null && L[2] <= t;
            const pg = (r[23] || []).find(x => x[1] === L[4]);      // UI_Progress (dump v11): Jiangnan Tower's next group, ...
            return `<span class="fh-lmk${building ? " b" : ""}${gone ? " x" : ""}" data-focus="${L[5]},${L[6]}" title="${esc(L[7])}${building ? " (building)" : ""}${gone ? " (destroyed)" : ""}${pg ? ` - progress ${Math.round(pg[2] * 100)} %` : ""} - click: jump to it">${ico(L[3], 30) || `<span class="ch">${esc(String(L[7]).slice(0, 6))}</span>`}`
              + (pg && !building && !gone ? `<i class="pg"><i style="width:${Math.round(Math.min(1, pg[2]) * 100)}%"></i></i>` : "") + `</span>`; }).join("");
      const gov = specials(p, t, GOV_RE), govBy = {};
      for (const x of gov) { const s2 = (x[1] + " " + x[2]).toLowerCase(), c = GOV_CITY.find(c2 => new RegExp("(^|[_ ])" + c2 + "([_ ]|$)").test(s2));
        const key = c || String(x[2]).replace(/governor( of)?/i, "").trim() || x[1]; (govBy[key] = govBy[key] || []).push(x); }
      const govH = Object.entries(govBy).map(([c, L]) => `<span class="fh-lmk fh-gov" title="${esc(L.map(x => `${String(x[8] || x[2]).split("\n")[0]} (${mmss(x[0])})`).join("\n"))}">`
        + `<span class="fh-tag fh-flag">${esc(c.charAt(0).toUpperCase() + c.slice(1))}</span>${L.length > 1 ? `<span class="nt">${L.map(() => `<i class="on"></i>`).join("")}</span>` : ""}</span>`).join("");
      const flags = "";
      const who = `<div class="fh-who"><b style="color:${col}">${esc(pi.name)}</b><br><small>${esc(o.civName ? o.civName(pi.civ) : pi.civ)}</small>`
        + (dyn ? ` <span class="fh-tag" title="dynasty (the game\'s dynasty event; Tang from the start)">${esc(dyn)} dynasty</span>` : "") + (flags ? `<br>${flags}` : "")
        + `</div><span class="fh-age" title="age">${ROMAN[age || 1] || age}</span>`;
      const vpicks = specials(p, t, VIZ_RE);
      // Ottoman vizier (owner 2026-11-11): the blacksmith icon in a progress ring (experience towards the next point, dump v11
      // imperial_council_exp_ott; the point thresholds are not known yet - the ring shows the experience against the
      // highest value seen before a point was earned), points earned / unspent (RT_Command), the bonuses picked
      const isOtt = /ottoman/i.test(pi.civ || ""), vz = r[22];
      let vizH = "";
      if (isOtt || vpicks.length) {
        const unspent = vz && vz[0] != null ? vz[0] : 0, earned = vz && vz[1] != null ? vz[1] : vpicks.length + unspent, exp = vz ? vz[2] : null;
        const TL = (H.vizThr || {})[String(p)] || [], thr = TL.length ? TL[Math.min(earned, TL.length - 1)] : null;   // per point
        const frac = exp != null && thr ? Math.min(1, exp / thr) : null;
        const C = 2 * Math.PI * 19, smith = (H.smith || {})[String(p)], src = smith && o.icon && o.icon(smith);
        const ring = `<span class="fh-vring" title="${exp != null ? `vizier experience ${Math.round(exp)}${thr ? " / ~" + Math.round(thr) : ""}` : "vizier experience: recorded from dump v11 on"}">`
          + `<svg viewBox="0 0 44 44" width="44" height="44"><circle cx="22" cy="22" r="19" fill="none" stroke="var(--line)" stroke-width="4"/>`
          + (frac != null ? `<circle cx="22" cy="22" r="19" fill="none" stroke="#e8b04f" stroke-width="4" stroke-dasharray="${(frac * C).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 22 22)"/>` : "")
          + `</svg>${src ? `<img src="${src}" alt="">` : `<b>V</b>`}</span>`;
        vizH = `<div class="fh-box"><div class="fh-viz">${ring}<span><b>Vizier</b> ${earned}/5${unspent ? ` <small style="color:#e8b04f">${unspent} unspent</small>` : ""}`
          + `${exp != null ? `<br><small style="color:var(--muted)">xp ${Math.round(exp)}</small>` : ""}</span>`
          + vpicks.map(x => `<span class="fh-tag" title="${mmss(x[0])}">${esc(x[2])}</span>`).join("") + `</div></div>`;
      }
      const prodH = (prod || []).map(([bp, n]) => `<span class="fh-prod" title="${esc(nice(bp))}: ${n} producing">${img(o.icon && o.icon(bp), "ch", nice(bp))}×${n}</span>`).join("")
        // military schools (dump v11 UI_Progress): one bar per school towards its next free unit
        + (r[23] || []).filter(x => /military_school/.test(x[0])).map(x => `<span class="fh-prod" title="military school: next unit ${Math.round(x[2] * 100)} %">${img(o.icon && o.icon(x[0]), "ch", "school")}<i class="fh-mbar"><i style="width:${Math.round(Math.min(1, x[2]) * 100)}%"></i></i></span>`).join("");
      // age-up under construction (owner 2026-11-11, like the in-game "Abbey of the Isles 3 [bar]"): name, builders, progress
      const lmH = (lms || []).map(([bp, f, nb, nm]) => `<div class="fh-box fh-lm" title="${esc(nm || nice(bp))}: ${Math.round(f * 100)} %, ${nb || 0} villagers building">${img(o.icon && o.icon(bp), "ch", nice(bp))}`
        + `<span><span class="nm">${esc(nm || nice(bp))}</span> &nbsp;${nb || 0}<small style="color:var(--muted)"> builders</small> <small style="float:right">${Math.round(f * 100)}%</small></span><span class="pb"><i style="width:${Math.round(f * 100)}%"></i></span></div>`).join("");
      return `<div class="fh-side ${right ? "r" : ""}"><div class="fh-box"><div class="fh-top"><div class="fh-top">${res}</div>${popc}${who}</div></div>`
        + (lmRow || govH ? `<div class="fh-box"><div class="fh-row">${lmRow}${govH}</div></div>` : "")
        + `<div class="fh-box">${techRows(p, t) || `<span style="color:var(--muted)">no upgrades</span>`}</div>`
        + vizH + lmH + (prodH ? `<div class="fh-box"><div class="fh-row">${prodH}</div></div>` : "") + `</div>`;
    }
    function cmp(a, b, ca, cb, lab) {
      const s = Math.max(1, a + b);
      return `<div class="fh-cmp"><span style="text-align:right">${a}</span><span class="bar"><i style="width:${a / s * 100}%;background:${ca}"></i><i style="width:${b / s * 100}%;background:${cb}"></i></span><span style="text-align:left">${b}</span><small>${lab}</small></div>`;
    }
    function cmpV(a, b, ca, cb, lab) {      // owner 2026-11-11: the army bar compares army value, not count
      const s = Math.max(1, a + b);
      return `<div class="fh-cmp" style="grid-template-columns:40px 1fr 40px"><span style="text-align:right">${k(a)}</span><span class="bar"><i style="width:${a / s * 100}%;background:${ca}"></i><i style="width:${b / s * 100}%;background:${cb}"></i></span><span style="text-align:left">${k(b)}</span><small>${lab}</small></div>`;
    }
    // sacred sites (owner 2026-11-12): one circle per site between the centre box and the army row - grey ring = neutral,
    // filled in the owner's colour = held, an arc = capture / decapture progress in that player's colour, dashed white ring =
    // contested (units of both players able to capture near it); click = jump to it
    function siteAt(S, t) { let r = null; for (const x of S.track) { if (x[0] <= t) r = x; else break; } return r; }
    function sites(t) {
      const L = H.sites || []; if (!L.length) return "";
      const held = {};
      const out = L.map((S, i) => {
        const r = siteAt(S, t), owner = r ? r[1] : 0, prog = r ? r[2] || [] : [], near = r ? r[3] || [] : [];
        // capture progress = one signed value per site (test batch S, 2026-11-12): -1 .. +1, + toward player 1, - toward
        // player 2 (player 2 reads the same value negated); 1/30 per s while one side's capturing units are on it alone
        const sv = prog[0] != null ? prog[0] : (prog[1] != null ? -prog[1] : 0);
        const pp = sv > 0 ? 1 : sv < 0 ? 2 : 0, pv = Math.min(1, Math.abs(sv || 0));
        const nearBoth = near.filter(Boolean).length >= 2;
        if (owner) held[owner] = (held[owner] || 0) + 1;
        const oc = owner ? o.pcolor(owner) : null, qc = pp ? o.pcolor(pp) : "#ccc";
        const R = 11, C = 2 * Math.PI * R;
        // a dark track under the arc, so a held site being decaptured (arc in the owner's colour on its own fill) still reads
        const arc = pv > 0 && pv < 1 ? `<circle cx="14" cy="14" r="${R}" fill="none" stroke="rgba(10,10,10,.75)" stroke-width="5"/>`
          + `<circle cx="14" cy="14" r="${R}" fill="none" stroke="${qc}" stroke-width="5" stroke-dasharray="${(pv * C).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 14 14)"/>` : "";
        const tipT = `Sacred site ${i + 1}: ${owner ? "held by " + pinfo(owner).name : "neutral"}`
          + (pv > 0 && pv < 1 ? ` · ${Math.round(pv * 100)} % toward ${pinfo(pp).name}` : "")
          + (nearBoth ? " · contested" : near.some(Boolean) ? " · " + near.map((v, j) => v ? pinfo(j + 1).name : null).filter(Boolean).join(", ") + " near" : "")
          + " - click: jump to it";
        return `<svg class="fh-site" viewBox="0 0 28 28" ${S.x != null ? `data-focus="${S.x},${S.z}"` : ""}><title>${esc(tipT)}</title>`
          + `<circle cx="14" cy="14" r="${R}" fill="${oc ? oc : "rgba(20,20,20,.55)"}" fill-opacity="${oc ? .85 : 1}" stroke="${oc ? "#fff8" : "#999"}" stroke-width="2"/>`
          + arc + (nearBoth ? `<circle cx="14" cy="14" r="13.2" fill="none" stroke="#fff" stroke-width="1.2" stroke-dasharray="3 2"/>` : "")
          + `<text x="14" y="18" text-anchor="middle" font-size="11" font-weight="700" fill="#f3e3b0">✚</text></svg>`;
      });
      const all = Object.entries(held).find(([p, n]) => n === L.length);
      return `<div class="fh-sites" title="${all ? esc(pinfo(+all[0]).name + " holds every sacred site (sacred victory countdown)") : "sacred sites"}">${out.join("")}</div>`;
    }
    function mid(t) {
      return `<div class="fh-midcol">${midBox(t)}${sites(t)}</div>`;
    }
    function midBox(t) {
      const [a, b] = P, ra = rowAt(a, t), rb = b != null ? rowAt(b, t) : null, ca = o.pcolor(a), cb = b != null ? o.pcolor(b) : "#888";
      return `<div class="fh-mid fh-box"><div data-pie="vil" title="">${cmp(ra[8], rb ? rb[8] : 0, ca, cb, "villagers")}</div>`
        + `<div data-pie="army">${cmpV(ra[15], rb ? rb[15] : 0, ca, cb, "army value · right-click: by cost")}</div><div class="fh-clock">${mmss(t)}</div></div>`;
    }
    function stats(t) {
      const R = P.map(p => [p, rowAt(p, t)]);
      const line = (lab, f, tip) => `<tr title="${esc(tip)}"><td>${lab}</td>${R.map(([p, r]) => `<td style="color:${o.pcolor(p)}">${f(r)}</td>`).join("")}</tr>`;
      return `<div class="fh-box"><table><tr><th style="text-align:left">Overview${o.statsHide ? ` <button class="fh-rbtn" data-shide="1" title="hide the stats box">Hide ▾</button>` : ""}</th>${R.map(([p]) => `<th style="color:${o.pcolor(p)}">${esc(pinfo(p).name)}</th>`).join("")}</tr>`
        + line("Villager work", r => r[13] ? (100 - r[12] / r[13] * 100).toFixed(1) + "%" : "–", "share of villager time not idle")
        + line("Idle time", r => mmss(r[12]) + (r[26] ? ` <small style="color:#9fb4d9">(${mmss(r[26])})</small>` : ""), "total villager idle time so far (villager-seconds); in brackets the part spent garrisoned")
        + line("Collected", r => k(r[14]), "resources gathered so far")
        + line("Army value", r => k(r[15]), "standing army value")
        + line("Worker kills", r => r[16], "enemy villagers killed")
        + line("Destroyed", r => k(r[17]), "enemy value destroyed") + `</table></div>`;
    }
    const nm = bp => (H.names || {})[bp] || nice(bp);
    const ico = (bp, sz) => { const src = o.icon && o.icon(bp); return src ? `<img src="${src}" alt="" style="width:${sz}px;height:${sz}px;border-radius:3px;vertical-align:middle">` : ""; };
    // ---------- pies on hover (owner 2026-11-11): villager split; army by unit type, right-click = by cost ----------
    let armyMode = "type", hoverKind = null, lastT = 0, mx = 0, my = 0;
    const tip = document.createElement("div");
    tip.className = "fh-tip"; tip.style.display = "none"; document.body.appendChild(tip);
    function donut(sl, center, sub) {
      const tot = sl.reduce((a, x) => a + x.v, 0); let a0 = -Math.PI / 2, path = "";
      const R1 = 46, R0 = 28, cx = 50, cy = 50;
      if (tot <= 0) path = `<circle cx="50" cy="50" r="${(R1 + R0) / 2}" fill="none" stroke="var(--line)" stroke-width="${R1 - R0}"/>`;
      else for (const x of sl) { if (x.v <= 0) continue;
        const f = x.v / tot, a1 = a0 + f * Math.PI * 2 - (f >= 1 ? 1e-4 : 0), L = a1 - a0 > Math.PI ? 1 : 0;
        const p = (r, a) => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
        path += `<path d="M${p(R1, a0)} A${R1} ${R1} 0 ${L} 1 ${p(R1, a1)} L${p(R0, a1)} A${R0} ${R0} 0 ${L} 0 ${p(R0, a0)}Z" fill="${x.c}"><title>${esc(x.l)}: ${Math.round(x.v)}</title></path>`;
        a0 = a1; }
      return `<svg viewBox="0 0 100 100" width="130" height="130">${path}<text x="50" y="${sub ? 50 : 54}" text-anchor="middle" font-size="13" font-weight="700" fill="var(--ink)">${esc(center)}</text>`
        + (sub ? `<text x="50" y="63" text-anchor="middle" font-size="8" fill="var(--muted)">${esc(sub)}</text>` : "") + `</svg>`;
    }
    function pieFor(kind, p, t) {
      const r = rowAt(p, t);
      if (kind === "vil") {
        const v = r[3], idle = r[4] || 0, other = Math.max(0, (r[8] || 0) - v.slice(0, 4).reduce((a, b) => a + b, 0) - idle);
        const sl = ["food", "wood", "gold", "stone"].map((n, i) => ({ v: v[i] || 0, c: RES_COL[n], l: n }))
          .concat([{ v: Math.max(0, idle - (r[25] || 0)), c: "#e8b04f", l: "idle" }, { v: r[25] || 0, c: "#9fb4d9", l: "garrisoned" },
            { v: other, c: "#5b6b8a", l: "building / walking" }]);
        return { svg: donut(sl, r[8] || 0, "villagers"), leg: sl.filter(x => x.v > 0).map(x => [x.c, x.l, x.v, ""]) };
      }
      if (armyMode === "cost") {
        const c = r[21] || [0, 0, 0, 0], sl = ["food", "wood", "gold", "stone"].map((n, i) => ({ v: c[i] || 0, c: RES_COL[n], l: n }));
        return { svg: donut(sl, k(r[15]), "army value"), leg: sl.filter(x => x.v > 0).map(x => [x.c, x.l, k(x.v), ""]) };
      }
      const by = r[20] || [], sl = by.map((x, i) => ({ v: x[2], c: SEG[i % SEG.length], l: nm(x[0]) + " ×" + x[1] }));
      return { svg: donut(sl, k(r[15]), "army value"), leg: by.map((x, i) => [SEG[i % SEG.length], nm(x[0]) + " ×" + x[1], k(x[2]), x[0]]) };
    }
    // resource hover (owner 2026-11-11): what that player's villagers on this resource work on (hud.py sources)
    const SRC_COL = { farm: "#e0b45a", berry: "#43a321", deer: "#c0528a", boar: "#8a5a3a", sheep: "#e8e2d0", fish: "#4fa3d1", carcass: "#a07050",
      trees: "#3c7a3c", "stealth forest": "#1f4d2f", "straggler tree": "#7aa86a", "large deposit": "#c9a24a", "small deposit": "#e8cf8a", other: "#888" };
    function srcTip(p, res) {
      const r = rowAt(+p, lastT), L = ((r[24] || {})[res] || []), tot = L.reduce((a, x) => a + x[1], 0), i = resN.indexOf(res);
      const sl = L.map(([k2, n]) => ({ v: n, c: SRC_COL[k2] || "#888", l: k2 }));
      return `<div class="fh-tip-h"><span style="color:${o.pcolor(+p)}">${esc(pinfo(+p).name)}</span> · ${esc(res)}: ${tot} villagers working · ${Math.max(0, r[2][i] || 0)}/min · bank ${k(r[1][i] || 0)}</div>`
        + `<div class="fh-pies"><div class="fh-pie">${donut(sl, tot, "villagers")}</div><div class="fh-leg" style="min-width:170px">`
        + (L.length ? L.map(([k2, n]) => `<div><span class="dot" style="background:${SRC_COL[k2] || "#888"}"></span>${esc(k2)}<span class="v">${n}</span></div>`).join("") : `<div style="color:var(--muted)">nobody on it</div>`)
        + `</div></div><div style="color:var(--muted);font-size:10px;margin-top:4px">node = the nearest of that kind to each gathering villager</div>`;
    }
    function drawTip() {
      if (!hoverKind) { tip.style.display = "none"; return; }
      if (hoverKind.startsWith("src|")) { const [, p, res] = hoverKind.split("|"); tip.innerHTML = srcTip(p, res); tip.style.display = "";
        const w = tip.offsetWidth, h = tip.offsetHeight;
        tip.style.left = Math.max(4, Math.min(window.innerWidth - w - 4, mx - w / 2)) + "px"; tip.style.top = Math.min(window.innerHeight - h - 4, my + 18) + "px"; return; }
      const head = hoverKind === "vil" ? "Villager distribution" : armyMode === "cost" ? "Army cost (right-click: by unit type)" : "Army value by unit type (right-click: by cost)";
      tip.innerHTML = `<div class="fh-tip-h">${head}</div><div class="fh-pies">` + P.slice(0, 2).map(p => {
        const q = pieFor(hoverKind, p, lastT);
        return `<div class="fh-pie"><b style="color:${o.pcolor(p)}">${esc(pinfo(p).name)}</b>${q.svg}<div class="fh-leg">`
          + q.leg.map(([c, l, v, bp]) => `<div><span class="dot" style="background:${c}"></span>${bp ? ico(bp, 16) : ""}${esc(l)}<span class="v">${v}</span></div>`).join("") + `</div></div>`;
      }).join("") + `</div>`;
      tip.style.display = "";
      const w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = Math.max(4, Math.min(window.innerWidth - w - 4, mx - w / 2)) + "px";
      tip.style.top = Math.min(window.innerHeight - h - 4, my + 18) + "px";
    }
    if (o.stats && o.statsHide) o.stats.addEventListener("click", e => { if (e.target.closest && e.target.closest("[data-shide]")) o.statsHide(); });
    if (o.bar) {
      o.bar.addEventListener("click", e => { const el = e.target.closest && e.target.closest("[data-focus]"); if (!el || !o.focus) return;
        const [x, z] = el.dataset.focus.split(",").map(Number); o.focus(x, z); });
      o.bar.addEventListener("mousemove", e => { mx = e.clientX; my = e.clientY; const el = e.target.closest && e.target.closest("[data-pie]");
        const kind = el ? el.dataset.pie : null; if (kind !== hoverKind) { hoverKind = kind; } drawTip(); });
      o.bar.addEventListener("mouseleave", () => { hoverKind = null; drawTip(); });
      o.bar.addEventListener("contextmenu", e => { const el = e.target.closest && e.target.closest('[data-pie="army"]'); if (!el) return;
        e.preventDefault(); armyMode = armyMode === "type" ? "cost" : "type"; hoverKind = "army"; drawTip(); });
    }
    // ---------- fight recap (owner 2026-11-11: Dota-style, minimizable; army value swing, damage per unit type with the
    // split over the victim types on hover) ----------
    let recapMin = false; try { recapMin = localStorage.getItem("fogline.recapMin") === "1"; } catch (e) {}
    let recapKey = "", recapF = null;
    function recapHTML(F, t) {
      if (recapMin) return `<button class="fh-rbtn" data-rt="1">Show fight recap ▸</button>`;
      const [a, b] = P.map(String), hits = F.hits;
      const sw = p => (F.armyE[p] || 0) - (F.armyS[p] || 0);
      const swing = F.armyS ? sw(a) - sw(b) : null;
      const dmgT = p => hits ? (hits[p] || []).reduce((s, x) => s + x[1], 0) : ((F.dmg[p] || {}).by || []).reduce((s, x) => s + x[2], 0);
      const row = (lab, fa, fb, tipt) => `<div class="fh-rrow" title="${esc(tipt || "")}"><span class="l">${fa}</span><span class="c">${lab}</span><span class="r">${fb}</span></div>`;
      const units = p => {
        const L = hits ? (hits[p] || []).map(x => [x[0], x[1]]) : ((F.dmg[p] || {}).by || []).map(x => [x[0], x[2]]);
        const mxd = Math.max(1, ...L.map(x => x[1]));
        return L.map(([bp, d], i) => `<div class="fh-ru" data-rk="${p}|${i}"><span class="ic">${ico(bp, 30) || `<span class="ch">${esc(nm(bp).slice(0, 6))}</span>`}</span>`
          + `<span class="bar"><i style="width:${d / mxd * 100}%;background:${o.pcolor(+p)}"></i></span><span class="n">${k(d)}</span></div>`).join("") || `<div class="fh-ru" style="color:var(--muted)">no damage</div>`;
      };
      const lost = p => ((F.lostBy || {})[p] || []).map(x => `<span class="fh-chip">${ico(x[0], 22) || esc(x[1])}×${x[2]}</span>`).join("") || `<span style="color:var(--muted)">none</span>`;
      const sgn = v => (v > 0 ? "+" : v < 0 ? "−" : "") + k(Math.abs(v));
      return `<div class="fh-box fh-rc"><div class="fh-rh"><span>Fight ${F.n} · ${mmss(F.s)}–${mmss(F.e)}${t > F.e + 1 ? ` · ${Math.round(t - F.e)} s ago` : ""}</span><button class="fh-rbtn" data-rt="1">Hide fight recap ▾</button></div>`
        + `<div class="fh-rcols"><b style="color:${o.pcolor(+a)}">${esc(pinfo(+a).name)}</b><span></span><b style="color:${o.pcolor(+b)}">${esc(pinfo(+b).name)}</b></div>`
        + (F.armyS ? row("Army value", `${k(F.armyS[a])} → ${k(F.armyE[a])}`, `${k(F.armyS[b])} → ${k(F.armyE[b])}`, "army value just before the fight and just after it") : "")
        + (swing != null ? `<div class="fh-swing" title="army value swing: change of ${esc(pinfo(+a).name)}'s army value minus change of ${esc(pinfo(+b).name)}'s"><span>Swing</span><span class="bar"><i style="left:50%;width:${Math.min(50, Math.abs(swing) / Math.max(1, F.armyS[a] + F.armyS[b]) * 100)}%;${swing < 0 ? "transform:translateX(-100%);" : ""}background:${o.pcolor(swing >= 0 ? +a : +b)}"></i></span><b style="color:${o.pcolor(swing >= 0 ? +a : +b)}">${sgn(Math.abs(swing))} ${esc(pinfo(swing >= 0 ? +a : +b).name)}</b></div>` : "")
        + row("Value lost", `${k((F.lost || {})[a] || 0)} <small>(${(F.units || {})[a] || 0})</small>`, `${k((F.lost || {})[b] || 0)} <small>(${(F.units || {})[b] || 0})</small>`)
        + row("Damage done", k(dmgT(a)), k(dmgT(b)), hits ? "from the game's damage events" : "estimated from HP drops (no damage events in this log)")
        + `<div class="fh-rgrid"><div class="fh-rside l">${units(a)}</div><div class="fh-rmid">Damage<br>by unit<br><small>hover: on what</small></div><div class="fh-rside r">${units(b)}</div></div>`
        + `<div class="fh-rgrid"><div class="fh-chips" style="justify-content:flex-end">${lost(a)}</div><div class="fh-rmid">Lost</div><div class="fh-chips">${lost(b)}</div></div></div>`;
    }
    // ---------- live arena recap (owner 2026-11-11): follows hud.py arenas in 2 s steps while the fight runs; span whole fight
    // or the last 60 s (auto: last 60 s once the fight runs past 2 min); right-click cycles bars -> pies -> hits (owner
    // 2026-11-11: hits landed per unit type, to judge targeting without the bonus-damage skew); hover = split by target
    let spanMode = "auto", chartMode = "bar", tgtMode = "units";
    // owner 2026-11-12: damage to units and damage to buildings shown apart (target filter); attackers of every kind - a TC /
    // tower shooting units counts under "vs units"
    try { tgtMode = localStorage.getItem("fogline.recapTgt") || "units"; } catch (e) {}
    const isBld = vb => /^building_/.test(vb || "");
    try { chartMode = localStorage.getItem("fogline.recapChart") || "bar"; } catch (e) {}
    // hit counts exist in hud.json built after 2026-11-11 (victim entries [bp, damage, hits])
    const hasHits = !!(H.arenas || []).some(A => A.steps.some(st => Object.values(st[1]).some(L => L.some(([, V]) => V.some(v => v.length > 2)))));
    if ((chartMode === "hits" || chartMode === "eff") && !hasHits) chartMode = "bar";
    function aggArena(A, t, span) {
      const t1 = Math.min(t, A.e + 2), t0 = span === "60" ? Math.max(A.s, t1 - 60) : A.s;
      const dmg = {}, lost = {}, used = {};
      for (const st of A.steps) {
        if (st[0] < t0 - 1e-6 || st[0] >= t1) continue;
        for (const [p, L] of Object.entries(st[1])) for (const [ab, V] of L) {
          const m = (dmg[p] = dmg[p] || {}); const x = (m[ab] = m[ab] || { d: 0, h: 0, v: {}, vh: {} });
          for (const [vb, d, h] of V) { if ((tgtMode === "buildings") !== isBld(vb)) continue; x.d += d; x.v[vb] = (x.v[vb] || 0) + d; x.h += h || 0; x.vh[vb] = (x.vh[vb] || 0) + (h || 0); } }
        for (const [p, v] of Object.entries(st[2] || {})) { const l = (lost[p] = lost[p] || [0, 0]); l[0] += v[0]; l[1] += v[1]; }
        for (const [p, U] of Object.entries(st[3] || {})) { const m = (used[p] = used[p] || {}); for (const [ab, n] of Object.entries(U)) m[ab] = (m[ab] || 0) + n; }
      }
      const out = {};
      // hits mode: [attacker, hits, [[victim, hits]]] sorted by hits; eff mode (owner 2026-11-12: hit efficiency = damage
      // dealt / hits landed): [attacker, dmg per hit, [[victim, dmg per hit, hits]]]; else by damage
      const H_ = chartMode === "hits", E_ = chartMode === "eff", r1 = v => Math.round(v * 10) / 10;
      for (const [p, m] of Object.entries(dmg)) out[p] = Object.entries(m).filter(([, x]) => (x.d > 0 || x.h > 0) && (!E_ || x.h > 0)).map(([ab, x]) => E_
        ? [ab, r1(x.d / x.h), Object.keys(x.v).filter(vb => x.vh[vb] > 0).map(vb => [vb, r1(x.v[vb] / x.vh[vb]), x.vh[vb]]).sort((a, b) => b[1] - a[1]), x.h]
        : [ab, H_ ? x.h : Math.round(x.d),
        Object.entries(H_ ? x.vh : x.v).sort((a, b) => b[1] - a[1]).map(([vb, d]) => [vb, Math.round(d)])]).sort((a, b) => b[1] - a[1]);
      const tot = {}; for (const [p, m] of Object.entries(dmg)) tot[p] = Object.values(m).reduce((a2, x) => a2 + x.d, 0);
      return { dmg: out, lost, used, t0, t1, tot };
    }
    function arenaHTML(A, t) {
      if (recapMin) return `<button class="fh-rbtn" data-rt="1">Show fight recap ▸</button>`;
      const live = t <= A.e, dur = Math.min(t, A.e) - A.s;
      const span = spanMode === "auto" ? (dur > 120 ? "60" : "whole") : spanMode;
      const G = aggArena(A, t, span); recapF = { arena: true, agg: G.dmg };
      // selected units (owner 2026-11-13; the 3D page's o.selAgg): their part of each bar in a darker shade of the team colour
      const SA = o.selAgg ? o.selAgg(G.t0, G.t1, tgtMode === "buildings") : null;
      const selV = (p, bp, cap, f) => { const x = SA && SA[p] && SA[p][bp]; return x ? Math.min(cap, x[f]) : 0; };
      const selI = (p, bp, v, mx, f) => { const sv = selV(p, bp, v, f); return sv > 0 ? `<i title="selected units: ${f === "h" ? sv.toLocaleString() + " hits" : k(sv) + " damage"}" style="width:${sv / mx * 100}%;background:${o.pcolor(+p)};filter:brightness(.5) saturate(1.2)"></i>` : ""; };
      const selTot = p => { const m = (SA && SA[p]) || {}; let d = 0, h = 0, n = 0; for (const x of Object.values(m)) { d += x.d; h += x.h; } return [d, h]; };
      const [a, b] = P.map(String);
      const row = (lab, fa, fb, tipt) => `<div class="fh-rrow" title="${esc(tipt || "")}"><span class="l">${fa}</span><span class="c">${lab}</span><span class="r">${fb}</span></div>`;
      const army = (p, tt) => rowAt(+p, tt)[15];
      const a0 = army(a, A.s - 1), b0 = army(b, A.s - 1), a1 = army(a, t), b1 = army(b, t), swing = (a1 - a0) - (b1 - b0);
      const lostV = p => (G.lost[p] || [0, 0]);
      const inc = p => { const r = rowAt(+p, t); return [r[2].slice(0, 4).reduce((x, y) => x + Math.max(0, y), 0), r[27] || 0]; };
      const cnt = p => { const S = A.sides[p] || {}, upto = L => (L || []).filter(x => x[1] <= t).length;
        return `${(S.start || []).length} started · <span title="left the arena (no damage for 5 s, moving away from the enemy)">${upto(S.fled)} fled</span>`
          + `${upto(S.returned) ? ` (${upto(S.returned)} back)` : ""} · <span title="joined while the fight ran and fought in the arena">${upto(S.reinf)} reinf.</span> · ${upto(S.died)} died`; };
      const dmgT = p => (G.dmg[p] || []).reduce((s2, x) => s2 + x[1], 0);
      const units = p => {
        const L = G.dmg[p] || []; if (!L.length) return `<div class="fh-ru" style="color:var(--muted)">no damage</div>`;
        if (chartMode === "eff") {
          const mxe = Math.max(1, ...L.map(x => x[1]));
          return L.map(([bp, e2, , h2], i2) => `<div class="fh-ru" data-rk="${p}|${i2}" title="${h2} hits"><span class="ic">${ico(bp, 30) || `<span class="ch">${esc(nm(bp).slice(0, 6))}</span>`}</span>`
            + `<span class="bar"><i style="width:${e2 / mxe * 100}%;background:${o.pcolor(+p)};opacity:.55"></i></span><span class="n">${e2.toFixed(1)}</span></div>`).join("");
        }
        if (chartMode === "hits") {
          const mxh = Math.max(1, ...L.map(x => x[1]));
          return L.map(([bp, n], i2) => `<div class="fh-ru" data-rk="${p}|${i2}"><span class="ic">${ico(bp, 30) || `<span class="ch">${esc(nm(bp).slice(0, 6))}</span>`}</span>`
            + `<span class="bar">${selI(p, bp, n, mxh, "h")}<i style="width:${Math.max(0, n - selV(p, bp, n, "h")) / mxh * 100}%;background:${o.pcolor(+p)};opacity:.7"></i></span><span class="n">${n.toLocaleString()}</span></div>`).join("");
        }
        if (chartMode === "pie") {
          const sl = L.map((x, i2) => ({ v: x[1], c: SEG[i2 % SEG.length], l: nm(x[0]) }));
          return `<div style="display:flex;flex-direction:column;align-items:center">${donut(sl, k(dmgT(p)), "damage")}</div>`
            + L.map((x, i2) => `<div class="fh-ru" data-rk="${p}|${i2}" style="grid-template-columns:12px 22px 1fr 44px"><span class="dot" style="width:9px;height:9px;border-radius:2px;background:${SEG[i2 % SEG.length]}"></span>${ico(x[0], 20)}<span>${esc(nm(x[0]))}</span><span class="n">${Math.round(x[1] / Math.max(1, dmgT(p)) * 100)}%</span></div>`).join("");
        }
        const mxd = Math.max(1, ...L.map(x => x[1]));
        return L.map(([bp, d], i2) => `<div class="fh-ru" data-rk="${p}|${i2}"><span class="ic">${ico(bp, 30) || `<span class="ch">${esc(nm(bp).slice(0, 6))}</span>`}</span>`
          + `<span class="bar">${selI(p, bp, d, mxd, "d")}<i style="width:${Math.max(0, d - selV(p, bp, d, "d")) / mxd * 100}%;background:${o.pcolor(+p)}"></i></span><span class="n">${k(d)}</span></div>`).join("");
      };
      const sgn = v => (v > 0 ? "+" : v < 0 ? "−" : "") + k(Math.abs(v));
      const sp = (v, lab) => `<button class="fh-rbtn${span === v ? " on" : ""}" data-span="${v}">${lab}</button>`;
      const ia = inc(a), ib = inc(b);
      // owner 2026-11-12: a title at the top of the box - what the chart below shows; the four views as pills (current one lit,
      // click = jump to it; right-click still cycles)
      const VIEWS = [["bar", "Damage"], ["pie", "Damage share"], ["hits", "Hits landed"], ["eff", "Damage per hit"]].filter(v => hasHits || v[0] === "bar" || v[0] === "pie");
      const cur = (VIEWS.find(v => v[0] === chartMode) || VIEWS[0])[1];
      const title = `<div class="fh-rtitle"><b>${cur}</b> <span>to ${tgtMode === "buildings" ? "buildings" : "units"} · by attacking unit type · ${span === "60" ? "last 60 s" : "whole fight"}</span>`
        + `<span class="fh-rviews">${VIEWS.map(v => `<button class="fh-rbtn${v[0] === chartMode ? " on" : ""}" data-chart="${v[0]}">${v[1]}</button>`).join("")}</span></div>`;
      return `<div class="fh-box fh-rc">${title}<div class="fh-rh"><span>${live ? `<b style="color:#e23">● live</b> ` : ""}<span title="fights merged into this arena: ${esc(A.fights.join(", "))}">Fight</span> ${mmss(A.s)}–${live ? mmss(t) : mmss(A.e)} · ${mmss(Math.max(0, (live ? t : A.e) - A.s))} long${!live && t > A.e + 1 ? ` · ${Math.round(t - A.e)} s ago` : ""}</span>`
        + `<span><button class="fh-rbtn${tgtMode === "units" ? " on" : ""}" data-tgt="units" title="damage done to units (by units and buildings)">units</button><button class="fh-rbtn${tgtMode === "buildings" ? " on" : ""}" data-tgt="buildings" title="damage done to buildings">bldgs</button> ${sp("whole", "whole")}${sp("60", "last 60 s")}<button class="fh-rbtn" data-rt="1">Hide ▾</button></span></div>`
        + `<div class="fh-rcols"><b style="color:${o.pcolor(+a)}">${esc(pinfo(+a).name)}</b><span></span><b style="color:${o.pcolor(+b)}">${esc(pinfo(+b).name)}</b></div>`
        + row("Army value", `${k(a0)} → ${k(a1)}`, `${k(b0)} → ${k(b1)}`, "army value when the fight started and now")
        + `<div class="fh-swing" title="army value swing since the fight started: change of ${esc(pinfo(+a).name)}'s army value minus change of ${esc(pinfo(+b).name)}'s"><span>Swing</span><span class="bar"><i style="left:50%;width:${Math.min(50, Math.abs(swing) / Math.max(1, a0 + b0) * 100)}%;${swing < 0 ? "transform:translateX(-100%);" : ""}background:${o.pcolor(swing >= 0 ? +a : +b)}"></i></span><b style="color:${o.pcolor(swing >= 0 ? +a : +b)}">${sgn(Math.abs(swing))} ${esc(pinfo(swing >= 0 ? +a : +b).name)}</b></div>`
        + row("Destroyed", `${k(lostV(b)[0])} <small>(${lostV(b)[1]})</small>`, `${k(lostV(a)[0])} <small>(${lostV(a)[1]})</small>`, "enemy arena units killed in the span: value (units) - the trade")
        + row("Trade", lostV(a)[0] ? (lostV(b)[0] / lostV(a)[0]).toFixed(2) + "×" : (lostV(b)[0] ? "∞" : "–"), lostV(b)[0] ? (lostV(a)[0] / lostV(b)[0]).toFixed(2) + "×" : (lostV(a)[0] ? "∞" : "–"), "value destroyed per value lost in the span")
        + row(tgtMode === "buildings" ? "Damage to bldgs" : "Damage to units", k(G.tot[a] || 0), k(G.tot[b] || 0), "from the game's damage events, involving arena units")
        + (SA && o.selCount && o.selCount() ? row("Selected", `${k(selTot(a)[0])} <small>(${selTot(a)[1]} hits)</small>`, `${k(selTot(b)[0])} <small>(${selTot(b)[1]} hits)</small>`, "damage and hits landed by the selected units in the span (the darker part of the bars)") : "")
        + row("Income /min", ia[0].toLocaleString(), ib[0].toLocaleString(), "resources gathered per minute (last 60 s) - what replenishes the army")
        + row("Army made /min", k(ia[1]), k(ib[1]), "army value produced per minute (last 60 s)")
        + `<div class="fh-rrow" style="font-size:11px"><span class="l">${cnt(a)}</span><span class="c">units</span><span class="r">${cnt(b)}</span></div>`
        + (Object.keys(G.used).length ? (() => { const ab = p => Object.entries(G.used[p] || {}).sort((x, y) => y[1] - x[1]).map(([n2, c]) => `${esc(String(n2).replace(/^(ability|abilities)_/, "").replace(/_/g, " "))} ×${c}`).join(", ") || "–";
            return `<div class="fh-rrow" style="font-size:11px" title="abilities used by arena units (dump v12)"><span class="l">${ab(a)}</span><span class="c">abilities</span><span class="r">${ab(b)}</span></div>`; })() : "")
        + `<div class="fh-rgrid"><div class="fh-rside l">${units(a)}</div><div class="fh-rmid">${chartMode === "hits" ? "Hits landed" : chartMode === "eff" ? "Damage<br>per hit" : "Damage"}<br>by unit<br><small>${span === "60" ? "last 60 s" : "whole fight"}<br>hover: on what<br>right-click: ${{ bar: "pies", pie: hasHits ? "hits" : "bars", hits: "per hit", eff: "bars" }[chartMode]}</small></div><div class="fh-rside r">${units(b)}</div></div></div>`;
    }
    const rtip = document.createElement("div"); rtip.className = "fh-tip"; rtip.style.display = "none"; document.body.appendChild(rtip);
    if (o.recap) {
      o.recap.addEventListener("click", e => {
        const cb = e.target.closest("[data-chart]");
        if (cb) { chartMode = cb.dataset.chart; try { localStorage.setItem("fogline.recapChart", chartMode); } catch (x) {} recapKey = ""; renderRecap(lastT, true); return; }
        const tb = e.target.closest("[data-tgt]");
        if (tb) { tgtMode = tb.dataset.tgt; try { localStorage.setItem("fogline.recapTgt", tgtMode); } catch (x) {} recapKey = ""; renderRecap(lastT, true); return; }
        const spb = e.target.closest("[data-span]");
        if (spb) { spanMode = spanMode === spb.dataset.span ? "auto" : spb.dataset.span; recapKey = ""; renderRecap(lastT, true); return; }
        if (!e.target.closest("[data-rt]")) return; recapMin = !recapMin;
        try { localStorage.setItem("fogline.recapMin", recapMin ? "1" : "0"); } catch (x) {} recapKey = ""; renderRecap(lastT, true); rtip.style.display = "none"; });
      o.recap.addEventListener("contextmenu", e => { if (!H.arenas) return; e.preventDefault(); chartMode = { bar: "pie", pie: hasHits ? "hits" : "bar", hits: "eff", eff: "bar" }[chartMode] || "bar";
        try { localStorage.setItem("fogline.recapChart", chartMode); } catch (x) {} recapKey = ""; renderRecap(lastT, true); });
      o.recap.addEventListener("mousemove", e => {
        const el = e.target.closest && e.target.closest("[data-rk]"); if (!el || !recapF) { rtip.style.display = "none"; return; }
        const [p, i] = el.dataset.rk.split("|"), F = recapF;
        let html;
        const L = F.arena ? F.agg[p] : F.hits ? F.hits[p] : null;
        if (L && F.arena && chartMode === "eff") { const x = L[+i]; if (!x) return; const mx = Math.max(1, ...x[2].map(v => v[1]));
          html = `<div class="fh-tip-h">${ico(x[0], 20)} ${esc(nm(x[0]))}: ${x[1].toFixed(1)} damage per hit (${x[3]} hits), on</div>` + x[2].map(([vb, e2, h2]) =>
            `<div class="fh-tl">${ico(vb, 18)}<span>${esc(nm(vb))}</span><span class="bar"><i style="width:${e2 / mx * 100}%"></i></span><span class="v">${e2.toFixed(1)} · ${h2} hits</span></div>`).join("");
        } else if (L) { const x = (L || [])[+i]; if (!x) return; const tot = Math.max(1, x[1]);
          const hm = F.arena && chartMode === "hits", fmt = v => hm ? v.toLocaleString() : k(v);
          html = `<div class="fh-tip-h">${ico(x[0], 20)} ${esc(nm(x[0]))}: ${fmt(x[1])} ${hm ? "hits" : "damage"}, on</div>` + x[2].map(([vb, d]) =>
            `<div class="fh-tl">${ico(vb, 18)}<span>${esc(nm(vb))}</span><span class="bar"><i style="width:${d / tot * 100}%"></i></span><span class="v">${fmt(d)} · ${Math.round(d / tot * 100)}%</span></div>`).join("");
        } else { const x = ((F.dmg[p] || {}).by || [])[+i]; if (!x) return;
          html = `<div class="fh-tip-h">${esc(x[1])}: ${k(x[2])} damage</div><div style="color:var(--muted)">no damage events in this log: no split by target</div>`; }
        rtip.innerHTML = html; rtip.style.display = "";
        const w = rtip.offsetWidth, h = rtip.offsetHeight;
        rtip.style.left = Math.max(4, Math.min(window.innerWidth - w - 4, e.clientX - w - 12)) + "px";
        rtip.style.top = Math.max(4, Math.min(window.innerHeight - h - 4, e.clientY - h / 2)) + "px";
      });
      o.recap.addEventListener("mouseleave", () => { rtip.style.display = "none"; });
    }
    function renderRecap(t, on) {
      if (H.arenas) {
        const A = on ? H.arenas.filter(x => x.s <= t && t - x.e <= RECAP_HOLD).sort((x, y) => y.s - x.s)[0] : null;
        const key2 = (A ? A.n : "-") + "|" + recapMin + "|" + spanMode + chartMode + tgtMode + "|" + (o.selKey ? o.selKey() : "") + "|" + P.join() + "|" + (A ? Math.floor(Math.min(t, A.e + 4) / 2) + "|" + (t > A.e ? Math.floor((t - A.e) / 5) : "") : "");
        if (key2 === recapKey) return; recapKey = key2;
        if (!A) recapF = null;
        o.recap.style.display = A ? "" : "none"; o.recap.innerHTML = A ? `<div class="fh-recap">${arenaHTML(A, t)}</div>` : "";
        if (!A) rtip.style.display = "none";
        return;
      }
      const F = on ? (H.recaps || []).filter(f => f.e <= t && t - f.e <= RECAP_HOLD).sort((a, b) => b.e - a.e)[0] : null;
      const key2 = (F ? F.n : "-") + "|" + recapMin + "|" + (F ? Math.floor((t - F.e) / 5) : "");
      if (key2 === recapKey) return; recapKey = key2; recapF = F;
      o.recap.style.display = F ? "" : "none"; o.recap.innerHTML = F ? `<div class="fh-recap">${recapHTML(F, t)}</div>` : "";
      if (!F) rtip.style.display = "none";
    }
    // arena state at t for the map pages (3D markers): {track [t, x, z, r], fled ids, reinforcement ids (last 20 s)}
    function arenaAt(t) {
      const A = (H.arenas || []).find(x => x.s <= t && t <= x.e + 3); if (!A) return null;
      let tr = A.track[0]; for (const x of A.track) { if (x[0] > t) break; tr = x; }
      const fled = new Set(), reinf = new Set();
      for (const S of Object.values(A.sides)) {
        const back = {}; for (const [i2, tt] of S.returned || []) if (tt <= t) back[i2] = tt;
        for (const [i2, tt] of S.fled || []) if (tt <= t && !(back[i2] >= tt)) fled.add(i2);
        for (const [i2, tt] of S.reinf || []) if (tt <= t && t - tt <= 20) reinf.add(i2);
      }
      return { n: A.n, x: tr[1], z: tr[2], r: tr[3], fled, reinf };
    }
    let key = "";
    return {
      update(t, show) {
        lastT = t;
        if (o.recap) renderRecap(t, show.recap);
        const sk = Math.floor(t / (H.step || 2)) + "|" + !!show.bar + !!show.stats;
        if (sk === key) return; key = sk;
        if (o.bar) { o.bar.style.display = show.bar ? "" : "none"; if (show.bar) o.bar.innerHTML = `<div class="fh-bar">${side(P[0], t, false)}${mid(t)}${P[1] != null ? side(P[1], t, true) : "<div></div>"}</div>`; if (!show.bar) hoverKind = null; drawTip(); }
        if (o.stats) { o.stats.style.display = show.stats ? "" : "none"; if (show.stats) o.stats.innerHTML = `<div class="fh-stats">${stats(t)}</div>`; }
      },
      reset() { key = ""; recapKey = ""; },
      setSwap(on) { P = on ? P0.slice().reverse() : P0.slice(); key = ""; recapKey = ""; },
      row: rowAt,
      arenaAt
    };
  }
  window.FoglineHUD = { create };
})();
