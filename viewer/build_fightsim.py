"""Fight simulator page (owner 2026-11-10: "a fight simulator like the circle villager model"): each recorded fight next
to its simulated runs, units as circles moving and fighting.

    python viewer/build_fightsim.py work/<name>.fightsim.json views/<name>.fightsim.html
(analyzer/fightsim.py <name> --html does both steps.)

Left: the real fight (4/s fight samples, else 1 s frames). Right: one simulated run (attack-move / micro per side).
Same map scale on both, same clock from the fight's start. Circle = unit at its size (filled = melee, ring = ranged,
square = siege, small = villager), the arc = HP left, a line = the unit it is attacking (bright when it hits).
"""
import json
import sys

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Fight simulator</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1e1e1c;--mute:#6d6c66;--line:#e1dfd7;--p1:#2f6fd0;--p2:#d0452f;--map:#eef0e6}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1e1e1c;--ink:#ebeae4;--mute:#9b9990;--line:#33322e;
--p1:#5b95f0;--p2:#f0705b;--map:#1c211b}}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.4 system-ui,sans-serif}
header{padding:12px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
h1{font-size:16px;margin:0 12px 0 0}select,button{font:inherit;padding:4px 8px;background:var(--card);color:var(--ink);
border:1px solid var(--line);border-radius:5px}button{cursor:pointer}
.wrap{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px 16px}
.pane{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
.pane h2{font-size:14px;margin:0 0 4px}.pane canvas{width:100%;aspect-ratio:1/1;background:var(--map);border-radius:6px;display:block}
.stat{display:flex;gap:16px;font-size:12px;margin:4px 0}.p1{color:var(--p1)}.p2{color:var(--p2)}.mute{color:var(--mute)}
.bar{padding:0 16px 8px;display:flex;gap:10px;align-items:center}#t{flex:1}
table{border-collapse:collapse;margin:0 16px 16px;font-size:12px}td,th{border-bottom:1px solid var(--line);padding:3px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}.note{padding:0 16px 16px;max-width:1100px}
</style></head><body>
<header><h1>Fight simulator</h1>
<label>Fight <select id="fight"></select></label>
<label>Simulated run <select id="run"></select></label>
<button id="play">▶ Play</button>
<label>Speed <select id="spd"><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select></label>
<span class="mute" id="units"></span></header>
<div class="bar"><span id="clock">0.0 s</span><input type="range" id="t" min="0" max="10" step="0.05" value="0"></div>
<div class="wrap">
<div class="pane"><h2>Real fight</h2><div class="stat" id="sr"></div><canvas id="cr" width="900" height="900"></canvas></div>
<div class="pane"><h2>Simulated: <span id="rname"></span></h2><div class="stat" id="ss"></div><canvas id="cs" width="900" height="900"></canvas></div>
</div>
<table id="tab"></table>
<p class="note mute">Simulation on open ground (no terrain, buildings or tower fire), units in the fight area at its start,
until one side is wiped out. Attack-move: nearest enemy, kept until it dies. Micro (survive &gt; priority &gt; focus): ranged
units step back from slower melee while reloading, badly hurt units pull back from slower threats, targets chosen by
(cost + threat) / (walk + kill time), damage already committed by allies avoids overkill. The real fight keeps everything
that came within the area (reinforcements, villagers), so its unit count can be higher. No splash or cleave yet.</p>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const NAMES = {"am-am": "attack-move vs attack-move", "micro-am": "P1 micro vs P2 attack-move",
  "am-micro": "P1 attack-move vs P2 micro", "micro-micro": "micro vs micro"};
let F = null, T = 0, playing = false, last = null;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function mmss(t){t=Math.round(t);return Math.floor(t/60)+":"+String(t%60).padStart(2,"0")}
D.fights.filter(f => f.anim).forEach((f, k) => {
  const o = document.createElement("option"); o.value = k;
  o.textContent = `#${f.n} ${mmss(f.start)}–${mmss(f.end)} (P1 ${f.units["1"]} vs P2 ${f.units["2"]})`;
  $("fight").appendChild(o);
});
Object.keys(NAMES).forEach(k => { const o = document.createElement("option"); o.value = k; o.textContent = NAMES[k]; $("run").appendChild(o); });
const fights = D.fights.filter(f => f.anim);
function bounds(f){
  let xs = [], zs = [];
  const add = fr => fr.forEach(r => r[1].forEach(u => { xs.push(u[1]); zs.push(u[2]); }));
  add(f.anim.real.frames.slice(0, 8)); Object.values(f.anim.runs).forEach(fr => add(fr.slice(0, 1)));
  if (!xs.length) return [0, 0, 1];
  xs.sort((a, b) => a - b); zs.sort((a, b) => a - b);
  const q = (a, p) => a[Math.min(a.length - 1, Math.floor(p * a.length))];
  const x0 = q(xs, .02), x1 = q(xs, .98), z0 = q(zs, .02), z1 = q(zs, .98);
  const s = Math.max(x1 - x0, z1 - z0, 30) * 2.4;
  return [(x0 + x1) / 2, (z0 + z1) / 2, s];
}
function frameAt(frs, t){
  if (!frs.length) return null;
  let lo = 0, hi = frs.length - 1;
  if (t <= frs[0][0]) return [frs[0], frs[0], 0];
  if (t >= frs[hi][0]) return [frs[hi], frs[hi], 0];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (frs[m][0] <= t) lo = m; else hi = m; }
  const a = frs[lo], b = frs[hi];
  return [a, b, (t - a[0]) / Math.max(b[0] - a[0], 1e-6)];
}
function draw(cv, units, frs, B, statEl, endT){
  const ctx = cv.getContext("2d"), W = cv.width;
  ctx.clearRect(0, 0, W, W);
  const sc = W / B[2], px = x => (x - B[0]) * sc + W / 2, pz = z => W / 2 - (z - B[1]) * sc;
  const col = s => s === 1 ? css("--p1") : css("--p2");
  // grid: 4 tiles
  ctx.strokeStyle = "rgba(127,127,127,.12)"; ctx.lineWidth = 1;
  const step = 16 * sc;
  for (let g = (W / 2) % step; g < W; g += step) { ctx.beginPath(); ctx.moveTo(g, 0); ctx.lineTo(g, W); ctx.stroke(); ctx.beginPath(); ctx.moveTo(0, g); ctx.lineTo(W, g); ctx.stroke(); }
  const fa = frameAt(frs, T);
  if (!fa) return;
  const [a, b, w] = fa, bm = new Map(b[1].map(u => [u[0], u]));
  const pos = new Map();
  a[1].forEach(u => { const v = bm.get(u[0]) || u; pos.set(u[0], [u[1] + (v[1] - u[1]) * w, u[2] + (v[2] - u[2]) * w, u[3], u[4], u[5]]); });
  // attack lines
  pos.forEach((p, i) => {
    if (p[3] < 0 || !pos.has(p[3])) return;
    const q = pos.get(p[3]), U = units[i];
    ctx.strokeStyle = col(U[1]); ctx.globalAlpha = p[4] ? 0.9 : 0.25; ctx.lineWidth = p[4] ? 2 : 1;
    ctx.beginPath(); ctx.moveTo(px(p[0]), pz(p[1])); ctx.lineTo(px(q[0]), pz(q[1])); ctx.stroke();
  });
  ctx.globalAlpha = 1;
  const alive = {1: 0, 2: 0}, left = {1: 0, 2: 0};
  pos.forEach((p, i) => {
    const U = units[i], r = Math.max(U[3] * sc, 2.5), x = px(p[0]), y = pz(p[1]);
    const hp = Math.max(0, p[2]) / Math.max(U[4], 1), c = col(U[1]);
    if (p[2] <= 0) { ctx.strokeStyle = c; ctx.globalAlpha = .5; ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r); ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke(); ctx.globalAlpha = 1; return; }
    alive[U[1]]++; left[U[1]] += U[6] * hp;
    ctx.fillStyle = c; ctx.strokeStyle = c; ctx.lineWidth = Math.max(1.5, r * .35);
    if (U[5] === "siege") { ctx.fillRect(x - r, y - r, 2 * r, 2 * r); }
    else if (U[5] === "ranged") { ctx.beginPath(); ctx.arc(x, y, r * .8, 0, 7); ctx.stroke(); }
    else if (U[5] === "villager") { ctx.globalAlpha = .55; ctx.beginPath(); ctx.arc(x, y, r * .7, 0, 7); ctx.fill(); ctx.globalAlpha = 1; }
    else { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); }
    ctx.strokeStyle = hp > .5 ? "#3a9a5a" : hp > .25 ? "#d9a21b" : "#d33";
    ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 3, -Math.PI / 2, -Math.PI / 2 + hp * 2 * Math.PI); ctx.stroke();
  });
  const n = {1: units.filter(u => u[1] === 1).length, 2: units.filter(u => u[1] === 2).length};
  statEl.innerHTML = `<span class="p1">P1 ${alive[1]}/${n[1]} · ${Math.round(left[1])} res left</span>` +
    `<span class="p2">P2 ${alive[2]}/${n[2]} · ${Math.round(left[2])} res left</span>` +
    (T >= endT ? `<span class="mute">ended ${endT.toFixed(1)} s</span>` : "");
}
function setFight(){
  F = fights[+$("fight").value];
  F.B = bounds(F);
  const ends = [F.anim.real.frames.at(-1)?.[0] || 0, ...Object.values(F.anim.runs).map(r => r.at(-1)?.[0] || 0)];
  $("t").max = Math.max(...ends).toFixed(1);
  T = 0; table(); render();
}
function table(){
  const rows = [["", "time", "winner", "P1 lost", "P1 left", "P2 lost", "P2 left"]];
  rows.push(["real fight", (F.end - F.start).toFixed(0) + " s", "–", F.real["1"], "", F.real["2"], ""]);
  Object.entries(F.runs).forEach(([k, r]) => rows.push([NAMES[k], r.t + " s", r.winner ? "P" + r.winner : "none",
    r["1"].lost, `${r["1"].n_left}/${r["1"].n}`, r["2"].lost, `${r["2"].n_left}/${r["2"].n}`]));
  $("tab").innerHTML = rows.map((r, i) => "<tr>" + r.map(c => i ? `<td>${c}</td>` : `<th>${c}</th>`).join("") + "</tr>").join("");
}
function render(){
  if (!F) return;
  const k = $("run").value, frs = F.anim.runs[k];
  $("rname").textContent = NAMES[k];
  $("units").textContent = `simulated: P1 ${F.units["1"]} vs P2 ${F.units["2"]} units at the start`;
  draw($("cr"), F.anim.real.units, F.anim.real.frames, F.B, $("sr"), F.anim.real.frames.at(-1)?.[0] || 0);
  draw($("cs"), F.anim.units, frs, F.B, $("ss"), frs.at(-1)?.[0] || 0);
  $("clock").textContent = T.toFixed(1) + " s";
  $("t").value = T;
}
function tick(now){
  if (!playing) return;
  if (last != null) { T += (now - last) / 1000 * +$("spd").value; if (T >= +$("t").max) { T = +$("t").max; playing = false; $("play").textContent = "▶ Play"; } }
  last = now; render(); if (playing) requestAnimationFrame(tick);
}
$("play").onclick = () => { playing = !playing; $("play").textContent = playing ? "❚❚ Pause" : "▶ Play"; last = null; if (playing) { if (T >= +$("t").max) T = 0; requestAnimationFrame(tick); } };
$("t").oninput = () => { T = +$("t").value; render(); };
$("fight").onchange = setFight; $("run").onchange = render;
if (fights.length) setFight(); else document.body.insertAdjacentHTML("beforeend", "<p class=note>No fights with both sides.</p>");
</script></body></html>"""


def build(data, out):
    html = PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        build(json.load(fh), sys.argv[2])
    print("->", sys.argv[2])
