"""Embed a fights file (export_fights.py output) into fights.html.

python build_fights.py fights.json out.html [--lang ja]
"""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from i18n import translate  # noqa: E402
lang = "en"
if "--lang" in sys.argv:          # --lang ja: Japanese labels and controls
    i = sys.argv.index("--lang"); lang = sys.argv[i + 1]; del sys.argv[i:i + 2]
src = translate(open(os.path.join(here, "fights.html"), encoding="utf-8").read(), lang)
data = open(sys.argv[1], encoding="utf-8").read().replace("</", "<\\/")
out = sys.argv[2]
open(out, "w", encoding="utf-8").write(src.replace("/*__FIGHTS__*/null", data, 1))
print("wrote", out, f"{os.path.getsize(out) / 1e6:.1f} MB")
