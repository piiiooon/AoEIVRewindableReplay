# Index

One line per file or folder whose purpose is not clear from its name. Not loaded automatically: Claude reads it on demand
(see `CLAUDE.md`). Do not list files that explain themselves.

## Notes and records
| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Rules loaded into every Claude Code session |
| `.claude/settings.json` | Project permissions and the index-reminder hook |
| `.claude/hooks/index_check.py` | After Claude creates a file, reminds it to add the file here |
| `docs/decisions/` | Decision records: why something is the way it is |
| `docs/notes/recorder.md` | dump.lua record types v5-v21, record.py, replay file layout, log size, in-game API findings |
| `docs/notes/fogline.md` | 2D observer read: map geometry / walls, gold read, food forecast, castle timing, command rings, map controls |
| `docs/notes/3d.md` | 3D page: models / stamps, buildings, water, fog, motions, selection, minimap, cameras (p15-p77) |
| `docs/notes/hud.md` | Observer HUD and recaps, arenas, upgrade rows, vizier / dynasty / governors, sacred-site circles |
| `docs/notes/fights.md` | Death detection, fight review page, fightsim, fightcal and test batches 1-2 |
| `docs/notes/buffs.md` | auras / statdiff / dot, buff scout, in-game buff, DoT and sacred-site test batches, cisterns |
| `docs/notes/review.md` | Review-only pages: villager economy, basics, spikes, three lenses, decision points |
| `docs/notes/data.md` | data/ provenance, tools/update_data.py after a patch, blueprint name matching |
| `docs/notes/distribution.md` | Packaging rules, friend setup, Japanese pages |
| `docs/notes/roadmap.md` | Open items and parked work |
| `COMMANDS.md` | The owner's command cheat sheet (record, build, profile) |
| `QUICKSTART.md` | The usual run: recent games -> download -> record -> 3D page |
| `FRIENDS.md` | Guide shipped in the zip for friends |
| `NOTICE.txt` | Licence / attribution notice shipped in the zip |

## Code
| Path | Purpose |
| --- | --- |
| `ingame/dump.lua` | The recorder, run inside the game's SCAR console |
| `ingame/api_probe.lua` | Lists the game's scripting API (A4D\|API lines) |
| `ingame/fight_test.lua`, `ingame/fight_clean.lua` | Scripted skirmish tests; fight_clean = generated list of upgrades removed before a test |
| `analyzer/gamedata.py` | Blueprint name resolution, class matching, crew / free units |
| `analyzer/techs_bought.py` | Researched upgrades per player (U events, clicks), civ codes |
| `analyzer/fightlab.py` | Per-fight odds / target / focus / overkill measures |
| `analyzer/fightsim.py` | Fight simulator page (attack-move vs micro); on hold |
| `analyzer/fightcal.py` | Calibrated fight engine and unit stats with upgrades |
| `analyzer/fighttests.py` | Reads logs/fighttests runs |
| `analyzer/arena.py` | Fight arenas (start, fled, reinforcements) for the live recap |
| `analyzer/lenses.py` | Hindsight / inference / foresight analyses (basics page) |
| `analyzer/spikes.py` | Army-value spikes and their causes |
| `analyzer/castle.py` | Castle-timing projection from the implied bank |
| `analyzer/counter.py` | Ideal counter army vs the army seen |
| `analyzer/dot.py` | Damage-over-time table; re-credits poison / bleed ticks |
| `analyzer/auras.py` | Buff spans from auras, toggles and casts |
| `analyzer/statdiff.py` | Recorded vs calculated stats (unexplained buffs / debuffs) |
| `analyzer/mapgeo.py` | Impassable terrain, water / cliff / shallows, footprints |
| `viewer/hud.js` | Observer HUD, inlined into the 2D and 3D pages |
| `viewer/view3d.html` | 3D page template (three.js r128) |
| `viewer/basics_compact.py`, `viewer/lens_sections.py` | Basics data embedded in the viewer / lens sections of the basics page |
| `viewer/i18n.py` | Japanese translation applied at build time |
| `tools/gameinput.py`, `tools/gamelink.py` | Windows input to the game / paths, log tail, console, launching |
| `tools/game_assets.py` | AOEMods.Essence wrapper: unpack, decode attrib, export models, searches |
| `tools/cmd_probe.py` | Replay command stream for a time window (naming undecoded command types from a test game) |
| `tools/input_log.py` | Own key / mouse-button presses during a test game (AoE4 window only), for cmd_probe --keys |
| `tools/unit_models.py` | Unit / building -> model parts (models/unit_models.json) |
| `tools/buff_list.py`, `tools/buff_check.py` | Owner's buff list for the scout / check a log for buff and governor events |
| `tools/tech_notes.py` | Collects upgrades without an icon into data/tech_notes.json |
| `tools/log_size.py` | Bytes per record type of a dump log |
| `tools/get_replay.py` | Downloads match replays from the official stats API into the playback folder |

## Data and local folders (not in git unless noted)
| Path | Purpose |
| --- | --- |
| `data/costs.json`, `sight.json`, `techs.json`, `upgrades.json`, `production.json`, `units.json`, `civs.json`, `abilities.json`, `pbgids.json`, `icons.json` | From aoe4world data (git); provenance in `docs/notes/data.md` |
| `data/econ.json` | Wiki gather base rates (git) |
| `data/game_weapons.json` | Exported from the owner's game files (git, never shipped) |
| `data/tech_notes.json`, `data/civ_notes.json` | Owner-written notes (created when used; not in git yet); not packaged |
| `work/` | Intermediate JSON per game (timeline, analyzed, hud, basics, ...) |
| `views/` | Built pages per game |
| `logs/` | Recorded dump logs, test runs (logs/fighttests), search outputs |
| `models/`, `icons/` | Game-derived models and icons; never shipped |
| `out/`, `real/`, `real2/`, `t1/`, `t2/`, `t5/` | Old test outputs (synthetic and early real runs) |
| `aoe4-analyzer/` | An older nested copy of the project (own .git, 2026-10-26); ignored |
| `/fight_test.lua`, `/fightcal.py`, `/fighttests.py` | Stray copies at the root; ignored, the real ones are in ingame/ and analyzer/ |
