"""Embed view files into viewer.html.

python build_viewer.py view.json out.html [--lang ja] [--basics work/<name>.basics.json] [--spikes work/<name>.spikes.json]
                      [--buffs work/<name>.auras.json --statdiff work/<name>.statdiff.json]
                      [--report "Basics=views/<name>.basics.html" --report "Spikes=views/<name>.spikes.html"]
python build_viewer.py out.html "Label 1=view1.json" "Label 2=view2.json"   (game selector)
"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from i18n import translate  # noqa: E402
lang = "en"
if "--lang" in sys.argv:          # --lang ja: Japanese labels and controls
    i = sys.argv.index("--lang"); lang = sys.argv[i + 1]; del sys.argv[i:i + 2]
basics = None
if "--basics" in sys.argv:        # basics checks (review only) for timeline marks + panel
    i = sys.argv.index("--basics"); basics = sys.argv[i + 1]; del sys.argv[i:i + 2]
lite = "--lite" in sys.argv       # the basic package's viewer: full information, army + income graphs only
if lite:
    sys.argv.remove("--lite")
hud = None
if "--hud" in sys.argv:           # work/<name>.hud.json (analyzer/hud.py): observer bar, stats, fight recaps (owner 2026-11-11)
    i = sys.argv.index("--hud"); hud = sys.argv[i + 1]; del sys.argv[i:i + 2]
spikes = None
if "--spikes" in sys.argv:        # spikes.json (review only): graphs + spike list in the viewer (owner 2026-11-09)
    i = sys.argv.index("--spikes"); spikes = sys.argv[i + 1]; del sys.argv[i:i + 2]
buffs = statd = None
if "--buffs" in sys.argv:          # work/<name>.auras.json (analyzer/auras.py): buffs lane + panel (review only, 2026-11-12)
    i = sys.argv.index("--buffs"); buffs = sys.argv[i + 1]; del sys.argv[i:i + 2]
if "--statdiff" in sys.argv:       # work/<name>.statdiff.json: explained / unexplained stat deviations
    i = sys.argv.index("--statdiff"); statd = sys.argv[i + 1]; del sys.argv[i:i + 2]
reports = {}
while "--report" in sys.argv:     # whole report pages shown inside the viewer (Label=path)
    i = sys.argv.index("--report"); lab, _, path = sys.argv[i + 1].partition("="); del sys.argv[i:i + 2]
    if os.path.exists(path):
        reports[lab] = open(path, encoding="utf-8").read()
src = translate(open(os.path.join(here, "viewer.html"), encoding="utf-8").read(), lang)
if sys.argv[1].endswith(".json"):
    data, out = open(sys.argv[1], encoding="utf-8").read(), sys.argv[2]
    if basics and os.path.exists(basics):
        from basics_compact import compact
        bc = json.dumps(compact(json.load(open(basics, encoding="utf-8"))), separators=(",", ":"))
        data = data.rstrip()
        assert data.endswith("}")
        data = data[:-1] + ',"basics":' + bc + "}"
    extra = []
    if spikes and os.path.exists(spikes):
        sp = json.load(open(spikes, encoding="utf-8"))
        sp.pop("players", None)
        extra.append('"spikes":' + json.dumps(sp, separators=(",", ":")))
    if buffs and os.path.exists(buffs):
        A = json.load(open(buffs, encoding="utf-8"))
        B = {"p": A.get("byPlayer") or {}, "names": A.get("names") or {},
             "fx": {ab: [[e.get("property"), e.get("effect"), e.get("value")] for e in L] for ab, L in (A.get("effects") or {}).items()}}
        if statd and os.path.exists(statd):
            S = json.load(open(statd, encoding="utf-8"))
            B["find"] = S.get("find") or []
            B["explained"] = [[r["att"], r["vic"], r["exp"], k, n] for r in S.get("damage") or [] for k, n in r.get("explained") or []]
            B["dot"] = [[d["source"], d["ticks"], d["dmg"], d["victims"], d.get("named") or []] for d in S.get("dot") or []]
            B["heals"] = S.get("heals") or []
        extra.append('"buffs":' + json.dumps(B, separators=(",", ":")))
    if hud and os.path.exists(hud):
        extra.append('"hud":' + open(hud, encoding="utf-8").read().strip())
    if reports:
        extra.append('"reports":' + json.dumps(reports, separators=(",", ":")))
    if lite:
        extra.append('"lite":true')
    if extra:
        data = data.rstrip()
        assert data.endswith("}")
        data = data[:-1] + "," + ",".join(extra) + "}"
else:
    out, parts = sys.argv[1], []
    for spec in sys.argv[2:]:
        label, _, path = spec.partition("=")
        parts.append('{"label":%s,"data":%s}' % (json.dumps(label), open(path, encoding="utf-8").read()))
    data = "[" + ",".join(parts) + "]"
data = data.replace("</", "<\\/")
src = src.replace("/*__HUD_JS__*/", open(os.path.join(here, "hud.js"), encoding="utf-8").read().replace("</", "<\\/"), 1)
open(out, "w", encoding="utf-8").write(src.replace("/*__SAMPLE__*/null", data, 1))
print("wrote", out, f"{os.path.getsize(out) / 1e6:.1f} MB")
