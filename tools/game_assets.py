"""Read the game's own files from your installation (owner 2026-11-10: 3D viewer step 1, and exact weapon values for the
fight simulator). Nothing is downloaded from the game or shipped: everything stays on this PC (like the icons rule).

Uses the AOEMods.Essence command-line tool (github.com/aoemods/AOEMods.Essence, release 0.7.0) on a .NET runtime:
    C:/aoe4/toolchain/tools/essence/AOEMods.Essence.CLI.dll
    C:/aoe4/toolchain/tools/dotnet/dotnet.exe        (or a dotnet on PATH)
(--toolchain to change the folder.) The game's archives are found from the installed game (Steam), cardinal/archives.

    python tools/game_assets.py check                   # what is found / missing
    python tools/game_assets.py attrib                  # unpack Attrib.sga, decode the weapon + unit files to JSON
    python tools/game_assets.py weapons                 # -> data/game_weapons.json: every weapon value for our units
    python tools/game_assets.py list-models spearman [--in DX12GeoEnglish,Gen7AssetsGeometry]   # unpack once, list by name
    python tools/game_assets.py artmap [spearman]       # -> models/artmap.json: the art each unit file points to
    python tools/game_assets.py export-parts [filter]   # every part in models/unit_models.json -> models/parts/*.glb
    python tools/game_assets.py export-parts --detail heavy --civs hre,rus   # textured -> models/parts_heavy/
    python tools/game_assets.py parts-info              # -> models/parts_info.json: size / box of every exported mesh
    python tools/game_assets.py heavy-probe [name]      # the detailed, textured version of one model -> models/heavy/
    python tools/game_assets.py stamps                  # buildings: stamp -> structure models (models/stamps.json)
    python tools/game_assets.py model <name>            # export one model (.rrgeom) to models/<name>.glb (a first look)
    python tools/game_assets.py scar-search [w1,w2]     # the game's scripts: lines naming the words -> logs/scar_search.txt
    python tools/game_assets.py ability-names           # replay ability ids -> names (models/ability_names.json)
    python tools/game_assets.py attrib-search [w1,w2]   # blueprint files named so: state / timer / spawn values -> logs/attrib_search.txt
    python tools/game_assets.py buff-scout              # buff / debuff list -> the game's files and values -> logs/buff_scout.txt

Essence commands used: sga-unpack <archive> <dir>; rgd-decode [--batch] -f json <in> <out>; model-export -m
--texture-path <dir> <file.rrgeom> <out.glb> (the same commands github.com/BigManJohn000/aoe4-replay-viewer uses).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# the toolchain inside the package (tools/setup.py puts it there); the owner's own setup keeps it next to the folder
DEFAULT_TC = next((d for d in (ROOT / "toolchain", ROOT.parent / "toolchain") if d.exists()), ROOT / "toolchain")


def paths(a):
    tc = Path(a.toolchain)
    dotnet = tc / "tools" / "dotnet" / ("dotnet.exe" if os.name == "nt" else "dotnet")
    if not dotnet.exists():
        dotnet = Path(shutil.which("dotnet") or dotnet)
    cli = tc / "tools" / "essence" / "AOEMods.Essence.CLI.dll"
    arch = Path(a.archives) if a.archives else None
    if arch is None:
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import gamelink
            exe = gamelink.game_exe() if hasattr(gamelink, "game_exe") else None
            if exe:
                arch = Path(exe).parent / "cardinal" / "archives"
        except Exception:  # noqa: BLE001 - not Windows / no game
            arch = None
    return {"tc": tc, "dotnet": dotnet, "cli": cli, "archives": arch, "out": tc / "content-local" / "extracted"}


def essence(P, *args):
    env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
    cmd = [str(P["dotnet"]), str(P["cli"]), *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip()
        print(f"  essence {' '.join(map(str, args[:2]))} failed ({r.returncode}):\n{msg[:1500]}")
    return r.returncode == 0


def unpack(P, name):
    d = P["out"] / name
    if d.exists() and any(d.iterdir()):
        return d
    sga = P["archives"] / f"{name}.sga"
    if not sga.exists():
        print(f"  no {sga}")
        return None
    d.mkdir(parents=True, exist_ok=True)
    print(f"  unpacking {sga.name} ...")
    return d if essence(P, "sga-unpack", sga, d) else None


def cmd_check(P):
    ok = True
    for what, p in (("toolchain folder", P["tc"]), (".NET runtime", P["dotnet"]), ("Essence CLI", P["cli"]),
                    ("game archives", P["archives"])):
        have = p is not None and Path(p).exists()
        ok &= have
        print(f"  {'ok     ' if have else 'MISSING'} {what}: {p}")
    if P["archives"] and Path(P["archives"]).exists():
        sgas = sorted(x.name for x in Path(P["archives"]).glob("*.sga"))
        print(f"  {len(sgas)} archives, e.g. {', '.join(sgas[:8])}")
    if ok:
        r = subprocess.run([str(P["dotnet"]), str(P["cli"]), "--help"], capture_output=True, text=True,
                           env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
        print("  Essence answers:", (r.stdout or r.stderr).strip().splitlines()[:3])
    return ok


def cmd_attrib(P):
    d = unpack(P, "Attrib")
    if not d:
        return
    js = P["out"] / "attrib_json"
    for sub in ("weapon", "ebps", "sbps", "upgrade", "attachment_lists", "statemodel_schema", "abilities"):
        src = next((p for p in d.rglob(sub) if p.is_dir()), None)
        if src is None:
            print(f"  no {sub} folder in Attrib")
            continue
        out = js / sub
        if out.exists() and any(out.rglob("*.json")):
            continue
        out.mkdir(parents=True, exist_ok=True)
        print(f"  decoding {src} ...")
        essence(P, "rgd-decode", "--batch", "-f", "json", src, out)
    print("  decoded:", {p.name: sum(1 for _ in p.rglob("*.json")) for p in js.iterdir()} if js.exists() else {})


def flat(node, pre="", out=None):
    """rgd JSON -> [(path, value)]; nodes may be {key, value} entries or plain dicts / lists"""
    out = [] if out is None else out
    if isinstance(node, dict):
        if "key" in node and "value" in node and len(node) <= 3:
            flat(node["value"], f"{pre}/{node['key']}", out)
        else:
            for k, v in node.items():
                flat(v, f"{pre}/{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            flat(v, pre if isinstance(v, dict) and "key" in v else f"{pre}[{i}]", out)
    else:
        out.append((pre, node))
    return out


WANT = ("area", "radius", "damage", "falloff", "charge", "pierce", "range", "speed", "duration", "wind", "reload",
        "aim", "accuracy", "scatter", "projectile", "splash", "distance", "max_targets", "penetration", "bonus", "armor")


def cmd_weapons(P):
    js = P["out"] / "attrib_json" / "weapon"
    if not js.exists():
        print("  run attrib first")
        return
    U = json.loads((ROOT / "data" / "units.json").read_text(encoding="utf-8"))["units"]
    want_units = {"spearman", "man-at-arms", "archer", "crossbowman", "knight", "horseman", "mangonel", "springald",
                  "ribauldequin", "nest-of-bees", "cannon", "bombard", "bedcrossbow", "war-elephant", "longbowman",
                  "handcannoneer", "trebuchet", "culverin"}
    files = list(js.rglob("*.json"))
    out = {}
    for f in files:
        name = f.stem.lower()
        if not any(w.replace("-", "_") in name for w in want_units):
            continue
        try:
            fl = flat(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
        out[str(f.relative_to(js))] = {p: v for p, v in fl if any(w in p.lower() for w in WANT)}
    dst = ROOT / "data" / "game_weapons.json"
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=True), encoding="ascii")
    print(f"  {len(out)} weapon files of {len(files)} -> {dst} (send this file)")
    _ = U


def cmd_list_models(P, term, archives):
    """unpack the given archives (once) and list every file whose name has the term, with the extension counts of each
    archive - the model file type is not known yet (ArtHigh / DX12Assets had no spearman .rrgeom)"""
    from collections import Counter
    found = []
    for name in archives:
        d = unpack(P, name)
        if not d:
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        ext = Counter(p.suffix.lower() for p in files)
        print(f"  {name}: {len(files)} files; types {dict(ext.most_common(8))}")
        found += [p for p in files if term.lower() in p.name.lower()]
    for p in found[:80]:
        print(" ", p.relative_to(P["out"]), p.stat().st_size // 1024, "KB")
    print(f"  {len(found)} files match '{term}'")
    lst = ROOT / "models" / "model_list.txt"
    lst.parent.mkdir(exist_ok=True)
    lst.write_text("\n".join(f"{p.relative_to(P['out'])}\t{p.stat().st_size // 1024}" for p in found), encoding="utf-8")
    print(f"  full list -> {lst} (send this file)")


def _art_refs(fl):
    return sorted({str(v) for _, v in fl if isinstance(v, str) and ("art\\" in v.lower() or "art/" in v.lower())})


def cmd_artmap(P, term):
    """which art each unit uses -> models/artmap.json. Soldiers carry no art path themselves: their entity file names
    attachment lists ($PBGMAP attachments\\attachment_lists, $PBGNAME e.g. unit_spearman_2 / wpn_melee_spearman_2_eng /
    tier2_spearman_eng), and those lists point into art/. Lists naming other lists are followed (depth 4)."""
    js = P["out"] / "attrib_json"
    al_dir = js / "attachment_lists"
    lists = {f.stem.lower(): f for f in al_dir.rglob("*.json")} if al_dir.exists() else {}
    if not lists:
        print("  no decoded attachment_lists - run attrib again (it now decodes them)")
    cache = {}

    def load(f):
        if f not in cache:
            try:
                cache[f] = flat(json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                cache[f] = []
        return cache[f]

    def pbg_names(fl):
        out, last = [], None
        for p_, v in fl:
            if p_.endswith("$PBGNAME"):
                last = (p_[:-len("$PBGNAME")], str(v))
            elif p_.endswith("$PBGMAP") and last and p_[:-len("$PBGMAP")] == last[0] and "attachment" in str(v).lower():
                out.append((last[0], last[1]))
        return out

    def resolve(name, depth=0, seen=None):
        seen = set() if seen is None else seen
        f = lists.get(name.lower())
        if f is None or name.lower() in seen or depth > 4:
            return []
        seen.add(name.lower())
        fl = load(f)
        refs = _art_refs(fl)
        for _, sub in pbg_names(fl):
            refs += resolve(sub, depth + 1, seen)
        return sorted(set(refs))

    out = {}
    for sub in ("ebps",):
        for f in (js / sub).rglob("*.json") if (js / sub).exists() else []:
            fp = str(f).replace("\\", "/")
            if "/dev/" in fp or "/campaign/" in fp:   # units, buildings, and map objects (trees, mines, animals)
                continue
            if term and term.lower() not in f.stem.lower():
                continue
            fl = load(f)
            rec = {"direct": _art_refs(fl), "lists": {}}
            for path, name in pbg_names(fl):
                key = ("unit" if path.startswith("/data/default/entity_blueprint_ext") else
                       "tier" if "tier_ext" in path else "weapon" if "weapon" in path else "other")
                if not path.startswith("/data/default/"):
                    continue
                rec["lists"].setdefault(key, {})[name] = resolve(name)
            if rec["direct"] or rec["lists"]:
                out[str(f.relative_to(js / sub))] = rec
    dst = ROOT / "models" / "artmap.json"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in [k for k in out if "spearman_2_eng" in k or "knight_3_eng" in k][:2]:
        print(" ", k, json.dumps(out[k])[:600])
    print(f"  {len(out)} unit files, {len(lists)} attachment lists -> {dst} (send this file)")


GEO_ARCH = {"english": "DX12GeoEnglish", "french": "DX12GeoFrench", "hre": "DX12GeoHRE", "rus": "DX12GeoRus",
            "mongols": "DX12GeoMongols", "chinese": "DX12GeoChinese", "abbasids": "DX12GeoAbbasids",
            "sultanate": "DX12GeoSultanate", "malian": "DX12GeoMalian", "ottoman": "DX12GeoOttoman",
            "japanese": "DX12GeoJapanese", "byzantine": "DX12GeoByzantine", "jin_dynasty": "DX12GeoJin",
            "lancaster": "DX12GeoLancaster", "templar": "DX12GeoTemplar", "scots": "DX12GeoScots",
            "vikings": "DX12GeoVikings"}


def cmd_export_parts_heavy(P, civs, only=""):
    """detail medium / heavy (owner 2026-11-10: see the heaviest colouring): the parts of the given civs (art prefix: eng,
    hre, rus, ...) plus the shared ones (weapons, trees, mines) with the game's textures -> models/parts_heavy/<name>.<i>.glb
    (every mesh and detail level; viewer/build_3d.py --detail picks). Geometry: DX12Geo<civ>, else Gen7; material
    <name>.rrmaterial from DX12Assets<civ> / DX12Assets staged next to the .rrgeom (the CLI looks there), one batch per
    texture archive. Parts without a material come out untextured."""
    um = ROOT / "models" / "unit_models.json"
    if not um.exists():
        print("  run python tools/unit_models.py first")
        return
    U = json.loads(um.read_text(encoding="utf-8"))
    paths = U.get("paths", {})
    civs = [c.strip().lower() for c in civs.split(",") if c.strip()]
    if not civs:
        print("  --civs needed for heavy (e.g. --civs hre,rus: the archives are ~150-300 MB per civ)")
        return

    def civ_of(n):
        pre = n.split("_")[0].lower()
        if pre in PREFIX_CIV:
            return pre
        parts = paths.get(n, "").split("\\")
        folder = parts[2].lower() if len(parts) > 2 else ""
        return next((k for k, v in PREFIX_CIV.items() if v.lower() == folder or GEO_ARCH.get(folder, "") == f"DX12Geo{v}"), None)

    need = [n for n in U["parts"] if (only.lower() in n if only else True)]
    need = [n for n in need if civ_of(n) in civs or civ_of(n) is None]
    geo, mats = {}, {}
    g7 = unpack(P, "Gen7AssetsGeometry")
    for c in civs:
        d = unpack(P, f"DX12Geo{PREFIX_CIV[c]}")
        if d:
            for f in d.rglob("*.rrgeom"):
                geo.setdefault(f.stem.lower(), f)
    for f in (g7.rglob("*.rrgeom") if g7 else []):
        geo.setdefault(f.stem.lower(), f)
    roots = [d for d in [unpack(P, f"DX12Assets{PREFIX_CIV[c]}") for c in civs] + [unpack(P, "DX12Assets")] if d]
    for r in roots:
        for f in r.rglob("*.rrmaterial"):
            mats.setdefault(f.stem.lower(), (r, f))
    batches = {}
    for n in need:
        g = geo.get(n)
        if g is None:
            continue
        r, m = mats.get(n, (None, None))
        batches.setdefault(str(r) if r else "", []).append((g, m))
    raw = P["out"] / "parts_heavy_glb"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    for root, items in batches.items():
        stage = P["out"] / "parts_heavy_stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        for g, m in items:
            shutil.copy2(g, stage / g.name)
            if m:
                shutil.copy2(m, stage / m.name)
        print(f"  {len(items)} parts, textures from {Path(root).name if root else '(none: untextured)'} ...")
        args = ["-b", "-m", "--texture-path", root] if root else ["-b"]
        essence(P, "model-export", *args, stage, raw)
    dst = ROOT / "models" / "parts_heavy"
    dst.mkdir(parents=True, exist_ok=True)
    got = set()
    for f in raw.rglob("*.glb"):
        idx, _, name = f.stem.partition("_")
        if not idx.isdigit():
            idx, name = "0", f.stem
        shutil.copy2(f, dst / f"{name}.{idx}.glb")
        got.add(name.lower())
    print(f"  {len(got)} of {len(need)} parts -> {dst}; textured: {sum(1 for n in need if n in mats)}; "
          f"missing: {sorted(set(need) - got)[:15]}")


def cmd_export_parts(P, only=""):
    """every part tools/unit_models.py listed (models/unit_models.json), Gen7 copies only (owner) -> models/parts/*.glb.
    Copies the needed .rrgeom files into one folder and runs the batch export once (one .NET start, not 900); the CLI
    names its output <index>_<name>.glb, so each mesh is kept as <name>.<index>.glb."""
    um = ROOT / "models" / "unit_models.json"
    if not um.exists():
        print("  run python tools/unit_models.py first")
        return
    need = set(json.loads(um.read_text(encoding="utf-8"))["parts"])
    if only:
        need = {n for n in need if only.lower() in n}
    g7 = P["out"] / "Gen7AssetsGeometry"
    if not g7.exists():
        unpack(P, "Gen7AssetsGeometry")
    src = {p.stem.lower(): p for p in g7.rglob("*.rrgeom")}
    # not in Gen7 (most buildings): the civ's DX12Geo archive, named from the art path's civilisation folder
    paths = json.loads(um.read_text(encoding="utf-8")).get("paths", {})
    civs = sorted({GEO_ARCH.get(paths[n].split("\\")[2].lower()) for n in need - set(src) if n in paths
                   and len(paths[n].split("\\")) > 2} - {None})
    for arch in civs:
        d = unpack(P, arch)
        if d:
            for p in d.rglob("*.rrgeom"):
                src.setdefault(p.stem.lower(), p)
    # owner 2026-11-11: shared structures / props ("com_" mill, mining camp; art\civilizations\common\..., art\props\...)
    # sit in no civ archive - every other DX12Geo*.sga is searched for the parts still missing (each unpacked once)
    left = {n for n in need - set(src) if n in paths}
    if left:
        done = set(civs)
        # owner's archive list (2026-11-11): there is no common geometry archive; the shared models were in none of the
        # DX12Geo*.sga - next the LOD archives, Art / ArtCivilizations, then DX12Assets (620 MB)
        cands = sorted(P["archives"].glob("DX12Geo*.sga")) + sorted(P["archives"].glob("Gen7AssetsGeometryLODs*.sga")) + \
            [P["archives"] / f"{x}.sga" for x in ("Art", "ArtCivilizations", "DX12Assets")]
        for arch in cands:
            if not arch.exists():
                continue
            if arch.stem in done or not left:
                continue
            d = unpack(P, arch.stem)
            if not d:
                continue
            found = 0
            for p in d.rglob("*.rrgeom"):
                k = p.stem.lower()
                if k in left:
                    src.setdefault(k, p)
                    left.discard(k)
                    found += 1
            if found:
                print(f"  {arch.stem}: {found} shared parts")
        if left:
            print(f"  not in any archive searched (DX12Geo*, LODs, Art, ArtCivilizations, DX12Assets): {sorted(left)[:15]}")
    stage = P["out"] / "parts_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for n in sorted(need):
        if n in src:
            shutil.copy2(src[n], stage / src[n].name)
    raw = P["out"] / "parts_glb"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    print(f"  {len(list(stage.iterdir()))} of {len(need)} parts found (Gen7, buildings from DX12Geo<civ>); exporting ...")
    essence(P, "model-export", "-b", stage, raw)
    dst = ROOT / "models" / "parts"
    dst.mkdir(parents=True, exist_ok=True)
    got = {}
    for f in raw.rglob("*.glb"):
        idx, _, name = f.stem.partition("_")
        if not idx.isdigit():
            idx, name = "0", f.stem
        shutil.copy2(f, dst / f"{name}.{idx}.glb")
        got.setdefault(name.lower(), []).append(int(idx))
    multi = {k: len(v) for k, v in got.items() if len(v) > 1}
    print(f"  {len(got)} parts exported -> {dst}; {len(multi)} with several meshes, e.g. {dict(list(multi.items())[:5])}")
    print(f"  missing: {sorted(need - set(got))[:20]}")


def cmd_parts_info(P):
    """size of every exported mesh (models/parts/*.glb) -> models/parts_info.json: vertices, triangles, bounding box,
    skinned or not. Small enough to send instead of the models (owner: never ship game art)."""
    import struct
    out = {}
    for f in sorted((ROOT / "models" / "parts").glob("*.glb")):
        b = f.read_bytes()
        try:
            n = struct.unpack("<I", b[12:16])[0]
            j = json.loads(b[20:20 + n])
            a = j["accessors"][0]
            prim = j["meshes"][0]["primitives"][0]
            out[f.stem] = {"v": a["count"], "t": j["accessors"][prim["indices"]]["count"] // 3,
                           "min": [round(x, 3) for x in a["min"]], "max": [round(x, 3) for x in a["max"]],
                           "skin": "JOINTS_0" in prim["attributes"] or "skins" in j,
                           "nodes": [{k: v for k, v in nd.items() if k in ("translation", "rotation", "scale", "matrix")}
                                     for nd in j.get("nodes", []) if any(k in nd for k in ("translation", "rotation",
                                                                                           "scale", "matrix"))]}
        except (ValueError, KeyError, IndexError, struct.error) as e:
            out[f.stem] = {"error": str(e)}
    dst = ROOT / "models" / "parts_info.json"
    dst.write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"  {len(out)} meshes -> {dst} (send this file)")


PREFIX_CIV = {"eng": "English", "fre": "French", "hre": "HRE", "rus": "Rus", "mon": "Mongols", "chi": "Chinese",
              "abb": "Abbasids", "sul": "Sultanate", "mal": "Malian", "ott": "Ottoman", "jpn": "Japanese", "byz": "Byzantine",
              "jin": "Jin", "lan": "Lancaster", "tem": "Templar", "sco": "Scots", "vik": "Vikings"}


def cmd_heavy_probe(P, name):
    """the heaviest detail level for one model (owner 2026-11-10: "what colouring would be the heaviest"): the detailed
    DX12Geo<civ> mesh exported with its materials and textures (DX12Assets<civ> + DX12Assets) -> models/heavy/<name>.glb;
    reports the file size, meshes, triangles and embedded images, to compare with the Gen7 flat-colour export"""
    import struct
    civ = PREFIX_CIV.get(name.split("_")[0].lower())
    geo = unpack(P, f"DX12Geo{civ}") if civ else None
    src = None
    for d in [geo] if geo else []:
        src = next((p for p in d.rglob("*.rrgeom") if p.stem.lower() == name.lower()), None)
    if src is None:
        print(f"  no {name}.rrgeom in DX12Geo{civ or '?'}")
        return
    tex_dirs = [d for d in (unpack(P, f"DX12Assets{civ}"), unpack(P, "DX12Assets")) if d]
    out = ROOT / "models" / "heavy"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob(f"*{name}*.glb"):
        f.unlink()
    # first run: the CLI looks for <name>.rrmaterial next to the .rrgeom (it ignored --material-path). Find the material
    # in the asset archives, stage both side by side, textures from the archive root.
    mats = [p for d in tex_dirs + [geo] for p in d.rglob(f"{name}.rrmaterial")]
    if not mats:
        near = [p for d in tex_dirs for p in d.rglob("*.rrmaterial") if name.split("_age")[0] in p.stem][:10]
        print(f"  no {name}.rrmaterial in DX12Assets{civ} / DX12Assets; similar: {[str(p.relative_to(P['out'])) for p in near]}")
        exts = {}
        for d in tex_dirs:
            for p in d.rglob(f"*{name}*"):
                exts.setdefault(p.suffix, []).append(str(p.relative_to(P["out"])))
        print(f"  files named like it in the asset archives: {json.dumps({k: v[:3] for k, v in exts.items()})}")
        return
    mat = mats[0]
    print(f"  material: {mat.relative_to(P['out'])}")
    stage = P["out"] / "heavy_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(src, stage / src.name)
    shutil.copy2(mat, stage / mat.name)
    root = next((d for d in tex_dirs if str(mat).startswith(str(d))), tex_dirs[0])
    cmd = ["model-export", "-v", "-m", "--texture-path", str(root), str(stage / src.name), str(out / f"{name}.glb")]
    print("  run:", " ".join(cmd[:5]), "...")
    r = subprocess.run([str(P["dotnet"]), str(P["cli"]), *cmd], capture_output=True, text=True,
                       env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
    msg = ((r.stdout or "") + (r.stderr or "")).strip()
    if msg:
        print("  " + msg[:1200].replace("\n", "\n  "))
    tot_t, imgs, size = 0, 0, 0
    for f in sorted(out.glob(f"*{name}*.glb")):
        b = f.read_bytes()
        n = struct.unpack("<I", b[12:16])[0]
        j = json.loads(b[20:20 + n])
        tris = sum(j["accessors"][pr["indices"]]["count"] // 3 for m in j.get("meshes", []) for pr in m["primitives"])
        tot_t += tris
        imgs += len(j.get("images", []))
        size += len(b)
        print(f"  {f.name}: {len(b) // 1024} KB, {tris} triangles, {len(j.get('images', []))} images, "
              f"{len(j.get('materials', []))} materials")
    print(f"  heavy total: {size // 1024} KB, {tot_t} triangles, {imgs} images (send this output)")


def cmd_building_art(P, bp):
    """where a building's look comes from (owner 2026-11-11: most buildings had no model): its artmap entry, and for every
    art path the files of that name in the unpacked archives (Art / ArtCivilizations / ArtHigh unpacked if needed)"""
    A = json.loads((ROOT / "models" / "artmap.json").read_text(encoding="utf-8"))
    keys = [k for k in A if Path(k.replace("\\", "/")).stem.lower() == bp.lower()]
    if not keys:
        print(f"  {bp} not in models/artmap.json")
        return
    rec = A[keys[0]]
    print(f"  {keys[0]}: {json.dumps(rec)[:3000]}")
    refs = set(rec.get("direct", []))
    for v in rec.get("lists", {}).values():
        for x in v.values():
            refs |= set(x)
    # stamps (art\stamps\civ_<civ>\...) were in none of Art / ArtCivilizations / ArtHigh: every small Art* archive
    # (the per-civ ones are 4-9 MB) and Data; match by name with any extension, also as a part of a longer file name
    for arch in sorted(P["archives"].glob("Art*.sga")) + [P["archives"] / "Data.sga"]:
        if arch.stem not in ("ArtHigh",) and arch.exists():
            unpack(P, arch.stem)
    names = {r.replace("/", "\\").split("\\")[-1].lower() for r in refs}
    hits = [f for d in P["out"].iterdir() if d.is_dir() and not d.name.startswith("parts")
            for f in d.rglob("*") if f.is_file() and (f.stem.lower() in names or f.name.lower().split(".")[0] in names)]
    stamp_dirs = sorted({str(f.parent.relative_to(P["out"])) for d in P["out"].iterdir() if d.is_dir()
                         for f in d.rglob("*") if f.is_file() and "\\stamps\\" in str(f).replace("/", "\\").lower()})
    print(f"  folders with 'stamps' in the path: {len(stamp_dirs)}, e.g. {stamp_dirs[:8]}")
    for f in hits[:40]:
        print(f"  {f.relative_to(P['out'])}  {f.stat().st_size} bytes")
    print(f"  {len(hits)} files for {len(names)} art names")


def cmd_stamps(P):
    import struct
    """buildings get their look from stamps (owner 2026-11-11: Data\\art\\stamps\\civ_scots\\sco_house_a_age_01.bin, Relic
    Chunky): the art paths each stamp names (RFCI chunk strings) -> models/stamps.json {stamp path: [art paths]}; the
    structure models (art\\civilizations\\<civ>\\structures\\...) are the building, the rest props (fences, chickens)"""
    import re as _re
    d = P["out"] / "Data" / "art" / "stamps"
    if not d.exists():
        unpack(P, "Data")
    out = {}
    for f in d.rglob("*.bin"):
        b = f.read_bytes()
        if not b.startswith(b"Relic Chunky"):
            continue
        # each placed object (owner's sco_house_a_age_01, read 2026-11-11): quaternion x y z w (16 bytes), position x y z,
        # scale x y z, 4 flag bytes, 4 id bytes, 4 more, then the art path; kept when the quaternion is a unit one
        refs = []
        for m in _re.finditer(rb"art\\[\x20-\x7e]{4,200}", b):
            p, path = m.start(), m.group().decode("ascii", "replace")
            xf = None
            if p >= 52:
                q = struct.unpack_from("<4f", b, p - 52)
                pos = struct.unpack_from("<3f", b, p - 36)
                sc = struct.unpack_from("<3f", b, p - 24)
                if abs(sum(v * v for v in q) - 1) < 0.02 and all(0.01 < v < 100 for v in sc) and all(abs(v) < 500 for v in pos):
                    xf = [round(v, 4) for v in (*q, *pos, *sc)]
            refs.append([path, xf])
        key = "art\\stamps\\" + str(f.relative_to(d)).replace("/", "\\")[:-4]
        out[key.lower()] = refs
    dst = ROOT / "models" / "stamps.json"
    dst.write_text(json.dumps(out, indent=0), encoding="utf-8")
    n = sum(1 for v in out.values() if any("\\structures\\" in r[0] for r in v))
    print(f"  {len(out)} stamps, {n} with a structure model -> {dst}")


def cmd_scar_search(P, words):
    """owner 2026-11-11: vizier point progress (Ottomans), landmarks / buildings that spawn units on a condition (Zhu Xi's
    Jiangnan Tower, Ottoman military schools) are not in the dump - the game's own scripts name the values to read
    (state-model keys, timers). Searches the game's script files (.scar / .lua) in the unpacked archives for the words
    and writes every matching line, with the 3 lines around it, to logs/scar_search.txt (send that file)."""
    unpack(P, "Data")
    words = [w.lower() for w in words]
    hits, files = [], 0
    for f in sorted(P["out"].rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".scar", ".lua", ".ai", ".rdo", ".xml", ".txt"):
            continue
        files += 1
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            low = line.lower()
            if any(w in low for w in words):
                ctx = "\n".join(f"  {j + 1:5d}: {lines[j][:220]}" for j in range(max(0, i - 3), min(len(lines), i + 4)))
                hits.append(f"== {f.relative_to(P['out'])}:{i + 1}\n{ctx}")
    dst = ROOT / "logs" / "scar_search.txt"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(f"words: {', '.join(words)}; {files} script files searched; {len(hits)} matches\n\n" + "\n".join(hits), encoding="utf-8")
    print(f"  {files} script files, {len(hits)} matching lines -> {dst}")


def cmd_attrib_search(P, words):
    """owner 2026-11-11: what drives the free / triggered unit spawns (Zhu Xi's Jiangnan Tower = landmark prefecture,
    Ottoman military schools, ...): the decoded blueprint files (attrib first) whose path names one of the words,
    every value whose key looks like a state model / timer / spawn / threshold -> logs/attrib_search.txt"""
    js = P["out"] / "attrib_json"
    if not (js / "statemodel_schema").exists():
        cmd_attrib(P)
    words = [w.lower() for w in words]
    keys = ("state", "timer", "spawn", "interval", "threshold", "cooldown", "exp", "resource_spent", "spent", "trigger",
            "squad_", "rate", "count", "limit", "duration", "modifier")
    out, nf = [], 0
    for f in sorted(js.rglob("*.json")):
        rel = str(f.relative_to(js)).lower()
        if not any(w in rel for w in words):
            continue
        nf += 1
        try:
            rows = flat(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        schema = "statemodel_schema" in rel        # a state model's keys and defaults: everything
        hit = [f"    {k} = {v}" for k, v in rows if schema or any(x in k.lower() for x in keys)]
        out.append(f"== {rel} ({len(rows)} values)\n" + "\n".join(hit[:400]))
    dst = ROOT / "logs" / "attrib_search.txt"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(f"words: {', '.join(words)}; {nf} files\n\n" + "\n\n".join(out), encoding="utf-8")
    print(f"  {nf} blueprint files -> {dst}")


def cmd_ability_names(P):
    """owner 2026-11-11: the replay file's ability commands carry the ability's PBG id; aoe4world names only some of them.
    The decoded ability blueprints (attrib/abilities) hold their own pbgid -> models/ability_names.json {pbgid: name}
    (game-derived: stays on this PC, like the models)."""
    js = P["out"] / "attrib_json" / "abilities"
    if not js.exists():
        cmd_attrib(P)
    out, info = {}, {}
    for f in js.rglob("*.json"):
        try:
            rows = flat(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        pid = next((v for k, v in rows if k.lower().endswith("/pbgid") and str(v).isdigit()), None)
        if pid is None:
            pid = next((v for k, v in rows if "pbgid" in k.lower() and str(v).isdigit()), None)
        if pid is not None:
            out[str(pid)] = f.stem
            info[str(pid)] = ability_info(f.stem, rows)
    dst = ROOT / "models" / "ability_names.json"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"  {len(out)} abilities with a pbgid -> {dst}")
    dst2 = ROOT / "models" / "ability_info.json"
    dst2.write_text(json.dumps(info, indent=0), encoding="utf-8")
    nd = sum(1 for v in info.values() if v.get("duration"))
    print(f"  activation / recharge / duration ({nd} found) / radius -> {dst2} (3D buff rings)")


def ability_info(stem, rows):
    """owner 2026-11-11, 3D buff rings: how long a cast lasts. The ability bag has activation (always_on / timed / toggle /
    targeted / self_targeted), recharge_time and the cast range; the effect's duration sits in the action list under a key
    with "duration" (the largest positive one is taken; UI / fx / animation keys skipped) and an area radius under "radius"
    (ui reticule keys skipped). Tooltip numbers (help_text_formatter args) are kept for checking."""
    d = {"attrib": stem}
    dur, rad, args = [], [], []
    for k, v in rows:
        kl = k.lower()
        last = kl.rsplit("/", 1)[-1]
        if last == "activation" and isinstance(v, str):
            d["activation"] = v
        elif last == "recharge_time" and isinstance(v, (int, float)):
            d["recharge"] = v
        elif "formatter_arguments" in kl and isinstance(v, (int, float)):
            args.append(v)
        elif isinstance(v, (int, float)) and v > 0 and not any(x in kl for x in ("ui_", "/fx", "anim", "audio", "sound", "decorator")):
            if "duration" in last:
                dur.append(v)
            elif "radius" in last:
                rad.append(v)
    if dur:
        d["duration"] = max(x for x in dur if x < 600) if any(x < 600 for x in dur) else None
    if rad:
        d["radius"] = max(rad)
    if args:
        d["args"] = args[:12]
    return d


BUFF_KEYS = ("modifier", "value", "duration", "radius", "range", "recharge", "cooldown", "target", "filter", "application",
             "usage", "multiplier", "addition", "amount", "rate", "timer", "exclusive", "stack", "toggle", "activation",
             "requirement", "cost", "speed", "armor", "damage", "health", "heal", "aura", "area", "type")
BUFF_SUBS = ("abilities", "upgrade", "sbps", "ebps", "statemodel_schema", "weapon")


def cmd_buff_scout(P):
    """owner 2026-11-11: buff / debuff test program, step 1. For every entry of tools/buff_list.py (owner's list + Scots /
    Vikings) and every aoe4world ability not in it: the decoded blueprint files whose path names its words (abilities first),
    with the values whose key looks like a modifier / duration / radius / target / cooldown -> logs/buff_scout.txt. That
    fixes the blueprint names, the real numbers (the owner's list may be off) and how each is triggered (always / toggle /
    manual) before the dev-skirmish tests are written."""
    js = P["out"] / "attrib_json"
    if not (js / "abilities").exists():
        cmd_attrib(P)
    sys.path.insert(0, str(ROOT / "tools"))
    from buff_list import OWNER
    abil = json.loads((ROOT / "data" / "abilities.json").read_text(encoding="utf-8"))["abilities"]
    files = {}
    for sub in BUFF_SUBS:
        d = js / sub
        if d.exists():
            files[sub] = sorted(d.rglob("*.json"))

    def values(f, cap=80):
        try:
            rows = flat(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return ["    (unreadable)"]
        hit = [f"    {k} = {v}" for k, v in rows if v not in ("", None) and any(x in k.lower() for x in BUFF_KEYS)]
        return hit[:cap] + ([f"    ... {len(hit) - cap} more"] if len(hit) > cap else [])

    def find(words, exact=()):
        out, seen = [], set()
        for sub in BUFF_SUBS:                         # exact stems first (the aoe4world attrib), then word matches
            for f in files.get(sub, []):
                if f.stem.lower() in exact and f not in seen:
                    out.append((sub, f)); seen.add(f)
        for sub in BUFF_SUBS:
            for f in files.get(sub, []):
                rel = str(f.relative_to(js)).lower().replace("\\", "/")
                if f not in seen and any(w in rel for w in words):
                    out.append((sub, f)); seen.add(f)
        return out

    lines, used = [], set()
    for name, civ, grp, words in OWNER:
        ws = [w.strip().lower() for w in words.split(",") if w.strip()]
        ab = [(pid, a) for pid, a in abil.items()
              if (civ == "*" or civ in a.get("civs", [])) and (a["name"].lower() == name.lower() or any(w in a["attrib"].lower() for w in ws))]
        used.update(pid for pid, _ in ab)
        hits = find(ws, {a["attrib"].lower() for _, a in ab})
        lines.append(f"## [{grp}] {name} ({civ}) words {','.join(ws)}: {len(hits)} files")
        for pid, a in ab:
            lines.append(f"  aoe4world ability {pid} {a['name']} = {a['attrib']} ({a.get('active')}, {','.join(a.get('civs', []))})")
        for sub, f in hits[:10]:
            lines.append(f"  == {sub}/{f.stem}")
            lines += values(f)
        if len(hits) > 10:
            lines.append("  more files: " + ", ".join(f.stem for _, f in hits[10:60]))
        lines.append("")
    lines.append("# aoe4world abilities not in the list")
    for pid, a in abil.items():
        if pid in used:
            continue
        hits = find((), {a["attrib"].lower()})
        lines.append(f"## {a['name']} ({','.join(a.get('civs', []))}) {a['attrib']} ({a.get('active')}): {len(hits)} files")
        for sub, f in hits[:3]:
            lines.append(f"  == {sub}/{f.stem}")
            lines += values(f, 40)
        lines.append("")
    dst = ROOT / "logs" / "buff_scout.txt"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(f"{len(OWNER)} list entries, {len(abil)} aoe4world abilities; files: "
                   + ", ".join(f"{k} {len(v)}" for k, v in files.items()) + "\n\n" + "\n".join(lines), encoding="utf-8")
    print(f"  {len(OWNER)} entries -> {dst} ({dst.stat().st_size // 1024} KB)")


def cmd_model(P, name):
    """export one model to models/<name>.glb; the Gen7 copy first (owner: Gen7 models are enough). The CLI exits 0 even when
    it writes nothing, so it runs verbose and every file that appears under models/ is reported."""
    hits = [p for p in P["out"].rglob("*.rrgeom") if p.stem.lower() == name.lower()]
    if not hits:
        print(f"  no {name}.rrgeom in {P['out']} (list-models first)")
        return
    hits.sort(key=lambda p: 0 if "Gen7" in str(p) else 1)
    src = hits[0]
    print(f"  source {src.relative_to(P['out'])} ({src.stat().st_size} bytes)")
    mdir = ROOT / "models"
    mdir.mkdir(exist_ok=True)
    dst = mdir / f"{name}.glb"
    env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
    for args in ((), ("-m",)):
        before = {p: p.stat().st_mtime for p in mdir.rglob("*")}
        cmd = [str(P["dotnet"]), str(P["cli"]), "model-export", "-v", *args, str(src), str(dst)]
        print("  run:", " ".join(cmd[2:]))
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        print(f"  exit {r.returncode}; output:\n" + ((r.stdout or "") + (r.stderr or "")).strip()[:2000])
        new = [p for p in mdir.rglob("*") if p.is_file() and before.get(p) != p.stat().st_mtime]
        print("  new files:", [f"{p.relative_to(mdir)} {p.stat().st_size // 1024} KB" for p in new] or "none")
        if new:
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["check", "attrib", "weapons", "list-models", "artmap", "model", "export-parts", "parts-info", "heavy-probe", "building-art", "stamps", "scar-search", "attrib-search", "ability-names", "buff-scout"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--toolchain", default=str(DEFAULT_TC))
    ap.add_argument("--detail", default="light", choices=["light", "heavy"],
                    help="export-parts: light = Gen7 meshes (models/parts); heavy = DX12 meshes with textures "
                         "(models/parts_heavy, needs --civs)")
    ap.add_argument("--civs", default="", help="export-parts --detail heavy: art prefixes, e.g. hre,rus")
    ap.add_argument("--in", dest="inarch", default="DX12GeoEnglish,Gen7AssetsGeometry",
                    help="list-models: archives to search, comma-separated names without .sga")
    ap.add_argument("--archives", help="the game's cardinal/archives folder (default: found from the game)")
    a = ap.parse_args()
    P = paths(a)
    if a.what == "check":
        cmd_check(P)
        return
    if not (P["cli"].exists() and Path(P["dotnet"]).exists() and P["archives"] and P["archives"].exists()):
        cmd_check(P)
        sys.exit("toolchain or archives missing (see above)")
    {"attrib": lambda: cmd_attrib(P), "weapons": lambda: cmd_weapons(P),
     "list-models": lambda: cmd_list_models(P, a.arg or "spearman", [x.strip() for x in a.inarch.split(",") if x.strip()]), "model": lambda: cmd_model(P, a.arg), "artmap": lambda: cmd_artmap(P, a.arg or ""), "export-parts": lambda: (cmd_export_parts_heavy(P, a.civs, a.arg or "") if a.detail == "heavy"
                                 else cmd_export_parts(P, a.arg or "")), "parts-info": lambda: cmd_parts_info(P), "heavy-probe": lambda: cmd_heavy_probe(P, a.arg or "eng_infantry_light_age02"), "building-art": lambda: cmd_building_art(P, a.arg or "building_house_control_sco"), "stamps": lambda: cmd_stamps(P),
     "ability-names": lambda: cmd_ability_names(P), "buff-scout": lambda: cmd_buff_scout(P),
     "attrib-search": lambda: cmd_attrib_search(P, (a.arg or "prefecture,military_school,jiangnan,imperial_council,wonder_age1,vizier").split(",")),
     "scar-search": lambda: cmd_scar_search(P, (a.arg or "vizier,imperial_council,jiangnan,military_school,prefecture,spawn_on_spend").split(","))}[a.what]()


if __name__ == "__main__":
    main()
