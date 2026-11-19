"""One-time setup on a friend's PC (owner 2026-11-11: package for a few players; Python installed by them, the toolchain
downloaded here). Safe to run again: every step that is already done is skipped.

    python tools\\setup.py                      # everything
    python tools\\setup.py --heavy vik,sco      # also the textured models for these civs (3D page --detail heavy)
    python tools\\setup.py --game "F:\\SteamLibrary\\steamapps\\common\\Age of Empires IV"

Steps
1. checks: Windows, Python 3.8+, the game (found through Steam, or --game).
2. toolchain (into toolchain\\ inside this folder): a .NET runtime (a system one of version 6+ is used if present, else
   Microsoft's dotnet-install.ps1 installs .NET 8 here) and the AOEMods.Essence command-line tool (MIT licence, latest
   GitHub release) - they read the game's archives.
3. game data, from YOUR installation (never shipped): weapon values, unit / building / map-object art map, building stamps,
   the 3D models (tools\\game_assets.py attrib, weapons, artmap, stamps; tools\\unit_models.py; export-parts).
   The unpacked archives go to toolchain\\content-local (several GB); --clean removes them afterwards.
"""
import argparse
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TC = ROOT / "toolchain"
ESSENCE_API = "https://api.github.com/repos/aoemods/AOEMods.Essence/releases/latest"
DOTNET_INSTALL = "https://dot.net/v1/dotnet-install.ps1"


def say(msg):
    print(msg, flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fogline-setup"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def dotnet_ok():
    """a runtime 6+ (Essence targets .NET 6; run with DOTNET_ROLL_FORWARD=Major) in toolchain\\ or on PATH"""
    for exe in (TC / "tools" / "dotnet" / "dotnet.exe", shutil.which("dotnet")):
        if exe and Path(exe).exists():
            try:
                out = subprocess.run([str(exe), "--list-runtimes"], capture_output=True, text=True).stdout
            except OSError:
                continue
            if any(line.startswith("Microsoft.NETCore.App ") and int(line.split()[1].split(".")[0]) >= 6
                   for line in out.splitlines()):
                return str(exe)
    return None


def install_dotnet():
    d = TC / "tools" / "dotnet"
    d.mkdir(parents=True, exist_ok=True)
    script = TC / "dotnet-install.ps1"
    say("  downloading Microsoft's dotnet-install.ps1 ...")
    script.write_bytes(fetch(DOTNET_INSTALL))
    say("  installing the .NET 8 runtime into toolchain\\tools\\dotnet ...")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-Runtime", "dotnet", "-Channel", "8.0", "-InstallDir", str(d)], check=True)


def install_essence():
    d = TC / "tools" / "essence"
    if (d / "AOEMods.Essence.CLI.dll").exists():
        return True
    say("  looking up the latest AOEMods.Essence release ...")
    rel = json.loads(fetch(ESSENCE_API))
    assets = [a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")]
    pick = next((a for a in assets if "cli" in a["name"].lower()), assets[0] if assets else None)
    if not pick:
        say("  no zip in the latest release - download the CLI by hand and unzip it into toolchain\\tools\\essence")
        return False
    say(f"  downloading {pick['name']} ({rel.get('tag_name')}) ...")
    z = zipfile.ZipFile(io.BytesIO(fetch(pick["browser_download_url"])))
    tmp = TC / "essence_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    z.extractall(tmp)
    dll = next(tmp.rglob("AOEMods.Essence.CLI.dll"), None)
    if dll is None:
        say("  the release zip has no AOEMods.Essence.CLI.dll - unzip a CLI build into toolchain\\tools\\essence by hand")
        return False
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(dll.parent, d)
    shutil.rmtree(tmp)
    return True


def run(*args):
    say("> " + " ".join(str(a) for a in args))
    r = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="the game folder (default: found through Steam)")
    ap.add_argument("--heavy", default="", help="art prefixes for the textured 3D models, e.g. vik,sco (3D --detail heavy)")
    ap.add_argument("--clean", action="store_true", help="delete the unpacked archives (toolchain\\content-local) at the end")
    a = ap.parse_args()

    say("1. checks")
    if platform.system() != "Windows":
        sys.exit("  Windows only (the recorder drives the game)")
    if sys.version_info < (3, 8):
        sys.exit(f"  Python 3.8+ needed (this is {platform.python_version()})")
    archives = None
    if a.game:
        archives = Path(a.game) / "cardinal" / "archives"
    else:
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import gamelink
            exe = gamelink.game_exe()
            archives = Path(exe).parent / "cardinal" / "archives" if exe else None
        except Exception as e:  # noqa: BLE001
            say(f"  game lookup failed: {e}")
    if not archives or not archives.exists():
        sys.exit("  Age of Empires IV not found - run again with --game \"<the game folder>\"")
    say(f"  game archives: {archives}")

    say("2. toolchain")
    if dotnet_ok():
        say(f"  .NET runtime: {dotnet_ok()}")
    else:
        install_dotnet()
        if not dotnet_ok():
            sys.exit("  .NET runtime still missing - install the .NET 8 runtime from Microsoft and run again")
    if not install_essence():
        sys.exit("  AOEMods.Essence missing (see above)")
    ga = ["tools/game_assets.py"]
    arch = ["--archives", str(archives), "--toolchain", str(TC)]
    if not run(*ga, "check", *arch):
        sys.exit("  the toolchain check failed (see above)")

    say("3. game data from your installation (unpacking takes a while the first time)")
    models = ROOT / "models"
    steps = [("data/game_weapons.json", [*ga, "attrib", *arch], [*ga, "weapons", *arch]),
             ("models/artmap.json", [*ga, "artmap", *arch]),
             ("models/stamps.json", [*ga, "stamps", *arch]),
             ("models/unit_models.json", ["tools/unit_models.py"]),
             ("models/parts", [*ga, "export-parts", *arch])]
    models.mkdir(exist_ok=True)
    for target, *cmds in steps:
        if (ROOT / target).exists() and (not (ROOT / target).is_dir() or any((ROOT / target).iterdir())):
            say(f"  {target}: already there")
            continue
        for c in cmds:
            if not run(*c):
                sys.exit(f"  step for {target} failed (see above); fix and run setup again")
    if a.heavy:
        run(*ga, "export-parts", "--detail", "heavy", "--civs", a.heavy, *arch)
    if a.clean:
        d = TC / "content-local"
        if d.exists():
            say(f"  removing {d} ...")
            shutil.rmtree(d)
    say("\nDone. Record a replay:  python tools\\record.py --name game1 --out viewer,fights,3d --icons")


if __name__ == "__main__":
    main()
