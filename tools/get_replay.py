"""Download match replays from the official Age of Empires stats API into the playback folder (owner 2026-11-09).

    python tools/get_replay.py 252754529:1102458                       # matchId:profileId (a player in that match)
    python tools/get_replay.py 252754529:1102458 252760011:1102458 ...
    python tools/get_replay.py --file matches.txt                      # one matchId:profileId per line (# comments)
    python tools/get_replay.py --recent 1102458 --custom --n 5         # a player's last 5 custom games, no IDs needed
    python tools/get_replay.py --recent 1102458 --list                 # just list their recent games (type, time, ID)
    python tools/get_replay.py --recent 1102458 --page                 # the same as a page: filter, tick, copy command

Recent games (owner 2026-11-09: "the last 5 custom matches with no known match ID"): the game's own community API,
    https://aoe-api.worldsedgelink.com/community/leaderboard/getRecentMatchHistory?title=age4&profile_ids=[<id>]
(documented by librematch; the game's recent-match list for that profile, custom lobbies included as far as known).
Custom = not a matchmaking game (its description isn't AUTOMATCH); --list shows each game's type and description
so that can be checked. Each replay then comes from the stats API above, or, if that fails, from the same community
API's getReplayFiles (signed download links).

Endpoint (found by the owner in the stats page's network log; no login, rate-limited):
    https://api.ageofempires.com/api/GameStats/AgeIV/GetMatchReplay/?matchId=<match>&profileId=<player>
The answer is a zip (or gzip) holding AgeIV_Replay_<matchId>; it is unpacked into Documents\\My Games\\Age of Empires
IV\\playback, ready for record.py (python tools\\record.py AgeIV_Replay_<matchId> --name ...). A replay loads only on
the game version it was played on. Requests are spaced --gap s apart (default 5); a refusal (429) waits and retries.
The stats page lists ranked / unranked games only; for custom (tournament) games the match ID has to come from
elsewhere (aoe4replays.gg, the organisers).
"""
import argparse
import gzip
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
URL = "https://api.ageofempires.com/api/GameStats/AgeIV/GetMatchReplay/?matchId={m}&profileId={p}"
UA = "fogline-replay-fetch/1.0"


def fetch(match, profile, tries=4, wait=30.0):
    req = urllib.request.Request(URL.format(m=match, p=profile), headers={"User-Agent": UA})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and k < tries - 1:
                print(f"  rate-limited; waiting {wait:.0f} s")
                time.sleep(wait)
                wait *= 2
                continue
            raise
    return None


COMMUNITY = "https://aoe-api.worldsedgelink.com/community/leaderboard/"


def _get_json(url):
    import json
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def recent(profile):
    """[{id, start, type, desc, map, players}] newest first, from getRecentMatchHistory"""
    import urllib.parse
    q = urllib.parse.urlencode({"title": "age4", "profile_ids": f"[{profile}]"})
    d = _get_json(COMMUNITY + "getRecentMatchHistory?" + q)
    names = {p.get("profile_id"): p.get("alias") for p in d.get("profiles") or []}
    out = []
    for m in d.get("matchHistoryStats") or []:
        res = m.get("matchhistoryreportresults") or []
        mem = {x.get("profile_id"): x for x in m.get("matchhistorymember") or []}
        ids = [x.get("profile_id") for x in res] or list(mem)
        rows = []
        for pid in ids:
            r = next((x for x in res if x.get("profile_id") == pid), {})
            mm = mem.get(pid, {})
            rows.append({"id": pid, "name": names.get(pid, str(pid)), "team": r.get("teamid", mm.get("teamid")),
                         "result": r.get("resulttype"), "civ": r.get("civilization_id", mm.get("civilization_id")),
                         "old": mm.get("oldrating"), "new": mm.get("newrating")})
        out.append({"id": m.get("id"), "start": m.get("startgametime") or 0, "end": m.get("completiontime") or 0,
                    "type": m.get("matchtype_id"), "desc": m.get("description") or "", "map": m.get("mapname") or "",
                    "players": [x["name"] for x in rows], "rows": rows})
    out.sort(key=lambda x: -x["start"])
    return out


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,
initial-scale=1"><title>Match history __NAME__</title><style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e3e3dd;--win:#2f8a55;--loss:#c23a2b;--acc:#2a6fdb}
@media (prefers-color-scheme:dark){:root{--bg:#171715;--card:#20201d;--ink:#ecece6;--mute:#9a9a92;--line:#30302b;
--win:#5cc488;--loss:#ef6b58;--acc:#6b9cf0}}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif;margin:20px 16px}
h1{font-size:19px;margin:0}.sub{color:var(--mute);margin:2px 0 12px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
button,input,select{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 10px}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:8px;font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mute);font-weight:500}
.w{color:var(--win)}.l{color:var(--loss)}.m{color:var(--mute)}.tag{font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 7px}
textarea{width:100%;height:70px;font:12px ui-monospace,monospace;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px}
</style></head><body><h1>Match history: __NAME__</h1><p class="sub">profile __PID__ · __N__ recent games from the game's
community API, fetched __WHEN__. Tick games, then copy the command into PowerShell (in C:\\aoe4\\aoe4-analyzer).</p>
<div class="bar"><select id="f"><option value="all">all games</option><option value="custom">custom only</option>
<option value="mm">matchmaking only</option></select><input id="q" placeholder="filter: player, map, lobby" size="28">
<button id="sel">tick all shown</button><button id="none">untick all</button></div>
<table><thead><tr><th></th><th>when</th><th>length</th><th>kind</th><th>lobby</th><th>map</th><th>team 1</th><th>team 2</th>
<th>match ID</th></tr></thead><tbody id="b"></tbody></table>
<p class="bar"><button id="cp">copy download command</button><span id="msg" class="m"></span></p><textarea id="cmd" readonly></textarea>
<script>
const G=__DATA__, PID=__PID__;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
const ts=t=>t?new Date(t*1000).toLocaleString():"–", len=(a,b)=>a&&b&&b>a?Math.floor((b-a)/60)+":"+String((b-a)%60).padStart(2,"0"):"–";
function pl(rows,team){return rows.filter(r=>r.team===team).map(r=>`<span class="${r.result===1?"w":r.result===0?"l":""}">${esc(r.name)}</span>`
 +(r.old!=null&&r.new!=null&&r.old!==r.new?` <span class="m">${r.old}→${r.new}</span>`:"")+(r.civ!=null?` <span class="m">civ ${r.civ}</span>`:"")).join("<br>")}
function draw(){const f=document.getElementById("f").value,q=document.getElementById("q").value.toLowerCase();
 const teams=g=>[...new Set(g.rows.map(r=>r.team))].sort();
 document.getElementById("b").innerHTML=G.filter(g=>(f==="all"||(f==="custom")===g.custom)&&(!q||JSON.stringify([g.desc,g.map,g.players]).toLowerCase().includes(q)))
 .map(g=>{const T=teams(g);return `<tr><td><input type="checkbox" data-id="${g.id}" ${g.sel?"checked":""}></td><td>${esc(ts(g.start))}</td>`
 +`<td>${len(g.start,g.end)}</td><td><span class="tag">${g.custom?"custom":"matchmaking"}</span> <span class="m">type ${g.type}</span></td>`
 +`<td>${esc(g.desc)}</td><td>${esc(g.map)}</td><td>${pl(g.rows,T[0])}</td><td>${pl(g.rows,T[1])}</td><td>${g.id}</td></tr>`}).join("");cmd()}
function cmd(){const s=G.filter(g=>g.sel);document.getElementById("cmd").value=s.length?"python tools/get_replay.py "+s.map(g=>g.id+":"+PID).join(" "):"";
 document.getElementById("msg").textContent=s.length+" ticked"}
document.getElementById("b").onchange=e=>{const g=G.find(x=>String(x.id)===e.target.dataset.id);if(g){g.sel=e.target.checked;cmd()}};
document.getElementById("f").onchange=draw;document.getElementById("q").oninput=draw;
document.getElementById("sel").onclick=()=>{document.querySelectorAll("#b input").forEach(i=>{const g=G.find(x=>String(x.id)===i.dataset.id);if(g)g.sel=true});draw()};
document.getElementById("none").onclick=()=>{G.forEach(g=>g.sel=false);draw()};
document.getElementById("cp").onclick=()=>{const t=document.getElementById("cmd");t.select();try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand("copy")}
 document.getElementById("msg").textContent="copied"};
draw();
</script></body></html>"""


def history_page(profile, games, out_path):
    """the player's recent games as a page: filter (custom / matchmaking, text), tick games, copy the download command"""
    import html
    import json
    name = next((r["name"] for g in games for r in g["rows"] if r["id"] == profile), str(profile))
    data = json.dumps(games).replace("</", "<\\/")
    page = (PAGE.replace("__NAME__", html.escape(str(name))).replace("__PID__", str(profile))
            .replace("__N__", str(len(games))).replace("__WHEN__", time.strftime("%Y-%m-%d %H:%M"))
            .replace("__DATA__", data))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    return out_path


def community_replay(match):
    """bytes of the first uploaded replay of the match from getReplayFiles' signed links, or None"""
    import urllib.parse
    q = urllib.parse.urlencode({"title": "age4", "matchIDs": f"[{match}]"})
    d = _get_json(COMMUNITY + "getReplayFiles?" + q)
    for f in d.get("replayFiles") or []:
        if f.get("datatype", 0) == 0 and (f.get("size") or -1) > 0 and f.get("url"):
            with urllib.request.urlopen(urllib.request.Request(f["url"], headers={"User-Agent": UA}), timeout=120) as r:
                return r.read()
    return None


def unpack(data, match, dest_dir):
    """zip / gzip / plain -> files in dest_dir; returns the paths written"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                name = Path(n).name
                body = z.read(n)
                if body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                    name = name[:-3] if name.lower().endswith(".gz") else name
                p = dest_dir / name
                p.write_bytes(body)
                out.append(p)
        return out
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    p = dest_dir / f"AgeIV_Replay_{match}"
    p.write_bytes(data)
    return [p]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="*", help="matchId:profileId")
    ap.add_argument("--file", type=Path, help="one matchId:profileId per line")
    ap.add_argument("--out", type=Path, help="folder (default: the game's playback folder)")
    ap.add_argument("--gap", type=float, default=5.0, help="s between requests (rate limit)")
    ap.add_argument("--recent", type=int, metavar="PROFILE_ID", help="take that player's most recent games")
    ap.add_argument("--n", type=int, default=5, help="how many of them (default 5)")
    ap.add_argument("--custom", action="store_true", help="custom games only (not matchmaking)")
    ap.add_argument("--list", action="store_true", help="only list the recent games, download nothing")
    ap.add_argument("--page", action="store_true", help="write the recent games as a page (views/history_<id>.html) "
                    "and open it: filter, tick games, copy the download command")
    a = ap.parse_args()
    pairs = list(a.pairs)
    if a.recent:
        try:
            games = recent(a.recent)
        except (urllib.error.URLError, OSError, ValueError) as e:
            sys.exit(f"recent games of {a.recent}: {e}")
        for x in games:
            x["custom"] = "AUTOMATCH" not in x["desc"].upper()
        if a.page:
            import webbrowser
            pth = history_page(a.recent, games, Path(__file__).resolve().parents[1] / "views" / f"history_{a.recent}.html")
            print(f"{len(games)} recent games -> {pth}")
            webbrowser.open(pth.as_uri())
            return
        if a.list:
            for x in games:
                print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(x['start']))}  {x['id']}  type {x['type']}  "
                      f"{'custom' if x['custom'] else 'matchmaking'}  {x['desc'][:30]!r}  {x['map']}  "
                      f"{', '.join(str(p) for p in x['players'])}")
            print(f"{len(games)} recent games")
            return
        pick = [x for x in games if x["custom"] or not a.custom][:a.n]
        if not pick:
            sys.exit("no such games in their recent history (try --list)")
        pairs += [f"{x['id']}:{a.recent}" for x in pick]
    if a.file:
        pairs += [ln.split("#")[0].strip() for ln in a.file.read_text(encoding="utf-8").splitlines()]
    pairs = [p for p in pairs if p]
    if not pairs:
        sys.exit("give matchId:profileId pairs (or --file)")
    if a.out:
        dest = a.out
    else:
        import gamelink as gl
        dest = gl.PLAYBACK
    ok = 0
    for i, pr in enumerate(pairs):
        m, _, p = pr.partition(":")
        if not (m.isdigit() and p.isdigit()):
            print(f"{pr}: expected matchId:profileId")
            continue
        if i:
            time.sleep(a.gap)
        try:
            data = fetch(m, p)
        except (urllib.error.HTTPError, OSError) as e:
            print(f"{m}: stats API: {e}; trying the community API")
            data = None
        if not data or len(data) < 100:
            try:
                data = community_replay(m)
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f"{m}: community API: {e}")
                data = None
        if not data or len(data) < 100:
            print(f"{m}: empty answer (that player may not share their history, or no replay was kept)")
            continue
        files = unpack(data, m, dest)
        ok += 1
        for f in files:
            print(f"{m}: {f}  ({f.stat().st_size / 1e6:.1f} MB)")
    print(f"{ok} of {len(pairs)} replays -> {dest}")


if __name__ == "__main__":
    main()
