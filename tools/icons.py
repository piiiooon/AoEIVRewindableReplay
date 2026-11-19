"""Embed unit and building icons into a view file (for the viewer's Icons mode).

python tools/icons.py work/<name>.view.json                 # download from data.aoe4world.com
python tools/icons.py work/<name>.view.json --from C:/aoe4world-data   # local clone of
                                                              # github.com/aoe4world/data
Only the icons this game needs are fetched; downloads are cached in icons/ next to this
project. The icons are game art from aoe4world's data: keep them on your own PC.
"""
import argparse
import base64
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "analyzer"))
from gamedata import resolve, canon_attrib  # noqa: E402

BASE = "https://data.aoe4world.com/images/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fetch(rel, cache, src, missing, label):
    """Icon bytes from the cache, a local data clone, or the aoe4world server (cached)."""
    local = os.path.join(cache, rel.replace("/", "_"))
    if not os.path.exists(local):
        try:
            if src:
                with open(os.path.join(src, "images", rel), "rb") as fh:
                    data = fh.read()
            else:
                # the server refuses Python's default user agent (HTTP 403)
                req = urllib.request.Request(BASE + rel, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
            with open(local, "wb") as fh:
                fh.write(data)
        except OSError as e:
            missing.append(f"{label} ({e})")
            return None
    with open(local, "rb") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("view")
    ap.add_argument("--from", dest="src", help="local clone of github.com/aoe4world/data")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "data", "icons.json")) as fh:
        icons = json.load(fh)["icons"]
    with open(a.view) as fh:
        view = json.load(fh)
    cache = os.path.join(ROOT, "icons")
    os.makedirs(cache, exist_ok=True)
    out, missing = {}, []
    for bp in view["bps"]:
        key = resolve(bp, icons)
        if not key:
            missing.append(bp)
            continue
        data = fetch(icons[key], cache, a.src, missing, bp)
        if data:
            out[bp] = "data:image/png;base64," + base64.b64encode(data).decode()
    # technology icons for the researched-tech lists (view: {p: [{attrib}]}, fights: {p: [[done, attrib, ...]]})
    with open(os.path.join(ROOT, "data", "upgrades.json"), encoding="utf-8") as fh:
        ups = json.load(fh)["upgrades"]
    attribs = {(x["attrib"] if isinstance(x, dict) else x[1]) for v in (view.get("techs") or {}).values() for x in v}
    tech_out = {}
    for at in sorted(attribs):
        rel = next((e.get("icon") for e in ups.get(canon_attrib(at, ups) or at, []) if e.get("icon")), None)
        if not rel:
            missing.append(at)
            continue
        data = fetch(rel, cache, a.src, missing, at)
        if data:
            tech_out[at] = "data:image/png;base64," + base64.b64encode(data).decode()
    view["icons"] = out
    view["techIcons"] = tech_out
    with open(a.view, "w") as fh:
        json.dump(view, fh, separators=(",", ":"))
    print(f"{len(out)} unit/building + {len(tech_out)} tech icons embedded; no icon for: {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main()
