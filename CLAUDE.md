# Fogline: AoE4 replay reader

Replay viewer / analyzer for Age of Empires IV (Steam). Core question: from what one player could see, what is the
opponent's bank, and are they saving or spending? Loaded into every session: keep this file short and change it rarely.

## Hard rule: no maphack (decision 0002)
The observer view may use only what that player could know: entities visible to them (the game's visibility flags) and
what they saw earlier; game rules and data; announcements every player gets (age-up completion); assumed optimal play,
labelled assumed / confirmed / contradicted. Never in the observer view: true banks, unseen entities, the opponent's own
commands, parameters fitted on the same game's hidden data (`--fit-rate` is review-only). Hidden data appears only in
"Everything" mode and "Show true values". Exception: the observer bar / stats / fight recap (viewer/hud.js) show full
values for both players in every view, like the in-game caster bar.

## Pipeline
1. `ingame/dump.lua` in the game console during replay playback (`-dev`), driven by `tools/record.py` -> `A4D|...` lines in
   `Documents/My Games/Age of Empires IV/warnings.log`. Current format: dump v21, delta records (decision 0003).
2. `analyzer/parse_log.py` log -> timeline JSON; 3. `analyzer/analyze.py` truth + per-observer estimates;
4. `analyzer/export_view.py` view JSON; 5. `viewer/build_viewer.py` -> page. `python run.py` does 2-5 plus the other pages
   (fights, basics / spikes, HUD, 3D). Commands: `COMMANDS.md`.

## Conventions
- Python 3.8+, standard library only. Pages: one HTML file each, no build step; desktop only.
- Map units: 4 per tile (villager 1.125 tiles/s = 4.5 units/s). Gather rate default 0.40 per villager-second.
- Testing without the game: `analyzer/synth_log.py`, `ingame/mock_harness.lua` (Lua 5.x; none on the owner's PC).
- Game-derived files (models, icons, game_weapons, stamps) are never shipped (`docs/notes/distribution.md`).
- Owner's preferences: terse, technically precise; reasoning before conclusions; don't overscope; treat explicit
  corrections as firm constraints. Current priority: complete the recorder first (decision 0004).

## Where things are written down
- Before searching for a file, read `INDEX.md`. It lists files whose purpose is not clear from their name. When you create
  such a file, add one line there (path, purpose); remove the line when the file is deleted.
- Before working on a subsystem, read its notes in `docs/notes/` (topics in `INDEX.md`). After a change, add a short entry
  to that notes file, not to this file. Later entries supersede earlier ones.
- Before changing something a decision record covers, read it in `docs/decisions/`. When a non-obvious choice is made, add a
  new numbered record there.
- Commit messages: one line saying what changed and why. Commit only when asked.
- If the goal, the deliverable or the scope of a request is unclear, ask before starting.

# Compact instructions

When compacting, keep: decisions made, files changed, open questions, the owner's corrections.
