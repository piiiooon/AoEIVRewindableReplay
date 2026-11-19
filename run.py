"""One command: warnings.log -> viewer page.

    python run.py                      # uses the game's warnings.log
    python run.py path\\to\\warnings.log
    python run.py --rate 0.52 --name himeyama_1017
    python run.py --name x --icons                 # unit icons: a local copy of aoe4world/data if there is one
                                                   # (aoe4world-data or data-main, in or next to this folder),
                                                   # else downloaded from data.aoe4world.com
    python run.py --name x --icons-from C:/aoe4world-data   # or from a local clone
    python run.py --name x --no-replay   # skip player cameras
    python run.py --name x --player 上杉謙信   # basics page from your side (part of your in-game name)
    python run.py --name x --out viewer,fights,3d   # which pages (default viewer,fights); 3d = views/<name>.3d.html

Player cameras: the replay file is found automatically. The log's first lines name it
(RUN-OPTIONS ... playback:AgeIV_Replay_...), and it is read from the game's playback folder.
--replay takes another path or just the file name.

Steps: copy the log to logs/<name>.log (the game overwrites warnings.log on each launch),
parse, analyze, export, build views/<name>.html, open it in the browser.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(os.path.expanduser("~"), "Documents", "My Games",
                           "Age of Empires IV", "warnings.log")
# Gather rate per villager per second (owner's setting). It multiplies the assumed perfect-production
# villager count, so it sits below a true per-villager rate (test5: true 0.40 and 0.55).
# Never fit it on the game being analysed: that uses the true banks (hidden information).
DEFAULT_RATE = 0.40
PLAYBACKS = [os.path.join(os.path.expanduser("~"), d, "My Games", "Age of Empires IV", "playback")
             for d in ("Documents", os.path.join("OneDrive", "Documents"), os.path.join("OneDrive", "ドキュメント"))]


def find_replay(log, given):
    """Replay file for this log: --replay (path or bare name), else the name in RUN-OPTIONS."""
    name = given
    if not name:
        with open(log, encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(20), fh):
                # the name can be followed by other launch options (Steam's own, e.g. -nomovies)
                m = re.search(r"playback:([^\s\]]+)", line) if "RUN-OPTIONS" in line else None
                if m:
                    name = m.group(1).rstrip("]")
                    break
    if not name:
        return None
    dirs = list(PLAYBACKS)
    try:                                    # the game's own playback folder (registry Documents: moved / OneDrive)
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import gamelink
        dirs.insert(0, str(gamelink.PLAYBACK))
    except Exception:  # noqa: BLE001 - not on Windows
        pass
    base = os.path.basename(name)
    for cand in [name] + [os.path.join(d, base) for d in dirs]:
        if os.path.isfile(cand):
            return cand
    for d in dirs:                          # same name with an extension (not the .gz download)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.startswith(base + ".") and not f.endswith(".gz") and os.path.isfile(os.path.join(d, f)):
                    return os.path.join(d, f)
    print(f"replay file not found ({name}); continuing without player cameras")
    return None


def local_icons():
    """A local copy of github.com/aoe4world/data (git clone, or GitHub's "Download ZIP", which unzips to
    data-main), in the project folder or next to it."""
    for base in (HERE, os.path.dirname(HERE)):
        for name in ("aoe4world-data", "data-main", "aoe4world-data-main"):
            d = os.path.join(base, name)
            if os.path.isdir(os.path.join(d, "images")):
                return d
    return None


def step(*args, soft=False):
    print(">", " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args)))
    r = subprocess.run([sys.executable, *args], check=not soft)
    if soft and r.returncode:
        print(f"  (skipped: {os.path.basename(args[0])} failed; the other pages are still built)")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default=DEFAULT_LOG)
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE)
    ap.add_argument("--name", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--icons", action="store_true", help="embed unit icons (downloaded once, cached in icons/)")
    ap.add_argument("--no-icons", action="store_true", help="no icons, even when a local aoe4world data copy is found")
    ap.add_argument("--icons-from", help="take icons from a local clone of github.com/aoe4world/data")
    ap.add_argument("--replay", help="replay file path or name (default: taken from the log)")
    ap.add_argument("--no-replay", action="store_true", help="don't add player cameras")
    ap.add_argument("--player", help="part of your in-game name: the basics page is written from that side "
                                     "(default: player 1)")
    ap.add_argument("--lang", default="en", choices=["en", "ja"],
                    help="ja: Japanese labels and controls; pages saved as <name>.ja.html / <name>.fights.ja.html")
    ap.add_argument("--out", default="viewer,fights",
                    help="pages to write, comma-separated: viewer, fights, 3d (owner 2026-11-10; 3d needs the fights data "
                         "and the models exported on this PC: tools/game_assets.py export-parts)")
    ap.add_argument("--levels", default="best", choices=["best", "all"],
                    help="3d page: best = one detail level per building mesh; all = every exported file stacked")
    ap.add_argument("--mine-shapes", action="store_true", help="3d page: gold / stone deposits as rock shapes instead of the game's models")
    ap.add_argument("--mirror-models", action="store_true", help="3d page: treat the exported models as glTF space and mirror them into game space")
    ap.add_argument("--detail", default="light", choices=["light", "medium", "heavy"],
                    help="3d page: light = Gen7 flat colours; medium / heavy = game textures on the lowest / full detail "
                         "meshes (tools/game_assets.py export-parts --detail heavy --civs ...)")
    a = ap.parse_args()
    outs = {o.strip().lower() for o in a.out.split(",") if o.strip()}
    bad = outs - {"viewer", "fights", "3d"}
    if bad:
        sys.exit(f"--out: unknown page(s) {', '.join(sorted(bad))} (viewer, fights, 3d)")
    if not os.path.exists(a.log):
        sys.exit(f"log not found: {a.log}")
    with open(a.log, encoding="utf-8", errors="replace") as fh:
        if not any("A4D|CAPS" in line for line in fh):
            sys.exit(f"{a.log} holds no dump output (the game rewrites warnings.log at every launch).\n"
                     "To record a replay: python tools\\record.py [replay] --name NAME --icons\n"
                     "To redo a recorded game: python run.py logs\\NAME.log --name NAME --icons")
    for d in ("logs", "work", "views"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    log = os.path.join(HERE, "logs", a.name + ".log")
    if os.path.abspath(a.log) != os.path.abspath(log):
        shutil.copyfile(a.log, log)
    w = lambda ext: os.path.join(HERE, "work", f"{a.name}.{ext}.json")
    an = os.path.join(HERE, "analyzer")
    step(os.path.join(an, "parse_log.py"), log, w("timeline"))
    step(os.path.join(an, "analyze.py"), w("timeline"), w("analyzed"), "--rate", str(a.rate))
    rep = None if a.no_replay else find_replay(log, a.replay)
    if rep:
        print("replay:", rep)
    step(os.path.join(an, "export_view.py"), w("analyzed"), w("view"),
         *(["--replay", rep] if rep else []))
    # owner 2026-11-12: icons on by default when a local aoe4world data copy (data-main) is found - nothing is downloaded;
    # --no-icons turns them off, --icons also downloads when there is no local copy
    if not a.no_icons and not a.icons and not a.icons_from and local_icons():
        a.icons = True
    if a.icons or a.icons_from:
        src = a.icons_from or local_icons()
        if src:
            print("icons from", src)
        step(os.path.join(HERE, "tools", "icons.py"), w("view"), *(["--from", src] if src else []))
    suffix = "" if a.lang == "en" else "." + a.lang
    html = None
    # fights data first: the observer bar's fight recaps (owner 2026-11-11) need it on every page
    step(os.path.join(an, "export_fights.py"), w("analyzed"), w("fights"))
    if os.path.exists(w("hud")):
        os.remove(w("hud"))
    step(os.path.join(an, "hud.py"), w("analyzed"), w("hud"), "--fights", w("fights"), *(["--replay", rep] if rep else []), soft=True)
    # buffs (review only; owner 2026-11-12): aura / cast buffs from positions, then recorded vs calculated stats with the
    # deviations those buffs explain - the viewer's buffs lane + panel
    for old in (w("auras"), w("statdiff")):
        if os.path.exists(old):
            os.remove(old)
    if step(os.path.join(an, "auras.py"), w("timeline"), *(["--replay", rep] if rep else []), w("auras"), soft=True):
        step(os.path.join(an, "statdiff.py"), w("timeline"), w("statdiff"), "--auras", w("auras"), soft=True)
    if "viewer" in outs:
        build_viewer_page(a, w, an, rep, suffix)
        html = os.path.join(HERE, "views", a.name + suffix + ".html")
    if "fights" in outs:
        fhtml = os.path.join(HERE, "views", a.name + ".fights" + suffix + ".html")
        if a.icons or a.icons_from:
            step(os.path.join(HERE, "tools", "icons.py"), w("fights"), *(["--from", src] if src else []))
        step(os.path.join(HERE, "viewer", "build_fights.py"), w("fights"), fhtml, "--lang", a.lang)
        print("fights:", fhtml)
    if "3d" in outs:
        if (a.icons or a.icons_from) and "fights" not in outs:     # building icons over the 3d buildings
            step(os.path.join(HERE, "tools", "icons.py"), w("fights"), *(["--from", src] if src else []))
        thtml = os.path.join(HERE, "views", a.name + ".3d.html")
        if not os.path.exists(w("basics")) or "viewer" not in outs:     # the graph at the bottom
            step(os.path.join(HERE, "viewer", "build_basics.py"), w("analyzed"), os.path.join(HERE, "work", a.name + ".basics.html"),
                 "--json", w("basics"), *(["--player", a.player] if a.player else []), soft=True)
        step(os.path.join(HERE, "viewer", "build_3d.py"), w("fights"), thtml, "--timeline", w("timeline"),
             "--basics", w("basics"), "--hud", w("hud"), *(["--replay", rep] if rep else []),
             "--detail", a.detail, "--levels", a.levels, *(["--mine-shapes"] if a.mine_shapes else []), *(["--mirror-models"] if a.mirror_models else []), soft=True)
        print("3d:", thtml)
        html = html or thtml
    if "viewer" in outs:
        print("viewer:", html)
    if html:
        if not a.no_open:
            webbrowser.open("file:///" + html.replace("\\", "/"))


def build_viewer_page(a, w, an, rep, suffix):
    # basics page (owner's rules; full information): gathering, floating, age-up saves, spending, trades
    # basics / spikes pages are only built to be embedded in the viewer (owner 2026-11-10: two files per game, the
    # viewer and the fights page): written to work/, the separate copies earlier builds left in views/ removed
    for old in (os.path.join(HERE, "views", a.name + ".basics" + suffix + ".html"),
                os.path.join(HERE, "views", a.name + ".spikes.html")):
        if os.path.exists(old):
            os.remove(old)
    bhtml = os.path.join(HERE, "work", a.name + ".basics" + suffix + ".html")
    for old in (w("basics"), bhtml):                    # never embed a stale one from an earlier build
        if os.path.exists(old):
            os.remove(old)
    step(os.path.join(HERE, "viewer", "build_basics.py"), w("analyzed"), bhtml, "--lang", a.lang,
         "--json", w("basics"), *(["--player", a.player] if a.player else []), soft=True)
    # spikes page (owner 2026-11-09; full information): army value + gap, causes, spikes, fights by line, nodes
    shtml = os.path.join(HERE, "work", a.name + ".spikes.html")
    for old in (w("spikes"), shtml):
        if os.path.exists(old):
            os.remove(old)
    if step(os.path.join(an, "spikes.py"), w("analyzed"), w("spikes"), *(["--replay", rep] if rep else []), soft=True):
        step(os.path.join(HERE, "viewer", "build_spikes.py"), w("spikes"), shtml, soft=True)
    # the viewer embeds basics and spikes (graphs on the replay's time + both full reports; owner 2026-11-09)
    html = os.path.join(HERE, "views", a.name + suffix + ".html")
    step(os.path.join(HERE, "viewer", "build_viewer.py"), w("view"), html, "--lang", a.lang, "--basics", w("basics"),
         "--spikes", w("spikes"), "--hud", w("hud"), "--buffs", w("auras"), "--statdiff", w("statdiff"),
         "--report", "Basics=" + bhtml, "--report", "Spikes=" + shtml)


if __name__ == "__main__":
    main()
