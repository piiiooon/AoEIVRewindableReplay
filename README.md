# Fogline — AoE4 replay reader

The usual run is in `QUICKSTART.md`. The 3D models and icons are game art and are not in this repository: section 0 of
`QUICKSTART.md` makes them from your own installation (`python tools\setup.py`).

Pipeline: game replay → in-game state dump → timeline → visible-only analysis → viewer.

## 1. Dump (in game, Steam, launched with `-dev`)
`-dev` opens the in-game Lua console but disables multiplayer and live observing; restart normally to play online.
1. Load the replay from the start (t = 0).
2. Console: `dofile("C:/path/to/aoe4-analyzer/ingame/dump.lua")`
3. Let it play to the end (high speed is fine; sampling is 1 s of game time).
4. Stop: `Scar_DoString("A4D_Stop()")`

Output lands in `Documents/My Games/Age of Empires IV/warnings.log`.
The first line, `A4D|CAPS|...`, reports which game API calls work. Three are unconfirmed for AoE4:
`Player_GetResource` (bank), `Entity_GetPosition` (map), `Player_CanSeeEntity` (fog).
Missing ones are written as empty fields; nothing crashes.

### Automatic (Windows)
`python tools/record.py [replay] [--name x] [--speed 64]` does all of section 1 and then runs the analysis:
it launches the replay through Steam with `-dev`, opens the console in the background, loads dump.lua,
speeds up, stops at the end and closes the game. Default replay: the newest file in the playback folder.

## 2. Process (Python 3, standard library only)
One command (copies the log, runs everything, opens the page):
```
python run.py                       # reads Documents/My Games/Age of Empires IV/warnings.log
python run.py path/to/warnings.log --name my_game
python run.py --name my_game --icons     # also embed unit icons (from data.aoe4world.com, cached in icons/)
# player cameras: the replay file named in the log is picked up from the playback folder automatically
```
Or step by step:
```
python analyzer/parse_log.py  warnings.log  timeline.json
python analyzer/analyze.py    timeline.json analyzed.json --rate 0.40
python analyzer/export_view.py analyzed.json view.json
```
`--rate`: resources per villager per second (one effective number for now).
`--fit-rate`: least-squares fit from this game's true banks. Hidden information: use it only to calibrate the rate for *other* games.
`--vil-model tc` (default): villager estimate also assumes nonstop production from every Town Center seen.

## 3. View
Open `viewer/viewer.html` and load `view.json`, or embed it: `python viewer/build_viewer.py view.json out.html`.

## Testing without a game
`python analyzer/synth_log.py out/synth_warnings.log` writes a SYNTHETIC log (made-up gather rate, map, behaviour; real costs).
`ingame/mock_harness.lua` runs dump.lua against a mocked API: `lua mock_harness.lua dump.lua full|minimal`.

## Data
`data/costs.json`: costs by blueprint name, from github.com/aoe4world/data @ b2cd382 (2026-05-04).

## Known gaps
- Gather rates by source (boar, deer, farm, berries, Chinese officials' tax) are not modelled; one effective rate is used.
- Landmark costs are 0 in the cost table, so age-ups are invisible to both estimate and truth.
- Technologies are not entities, so their cost is missing from spending.
- Blueprint names from a real log may not match the cost table; unmatched names are listed in the analysis warnings.
