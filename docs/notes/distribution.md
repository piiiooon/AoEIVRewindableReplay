# Packaging, friend setup, Japanese pages

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Japanese pages (2026-10-25)
- `viewer/i18n.py`: `translate(html, lang)` applied at build time. TEXT = exact text between tags (also matched
  html-escaped), PATTERNS = regex for counted strings, RAW = literal script snippets (labels built in JS).
- `--lang ja` on `run.py`, `viewer/build_viewer.py`, `viewer/build_fights.py`, and fogline-profile `profile.py`;
  output `<name>.ja.html`, `<name>.fights.ja.html`, `profile/<player>.ja.html` (links to .ja game pages).
- Scope (owner): labels and controls only. Unit / building / tech names, explanatory paragraphs and dynamic
  notes stay English. New UI labels: add them to TEXT (or RAW if built in script) or they stay English.
## 2026-11-11 packaging + p15
- tools/package.py -> dist/fogline-YYYYMMDD.zip (top folder fogline/): allowlist of code + aoe4world-derived data; refuses
  game-derived files (models/, icons/, game_weapons.json, stamps/artmap/unit_models). Excludes civ_notes.json, dev probes
  (fight_probe/fight_tests, synth_log, fighttests). Adds FRIENDS.md (guide) and NOTICE.txt (Microsoft GCUR notice, aoe4world,
  Essence MIT, three.js MIT). Fresh-unzip smoke test: run.py builds viewer/fights/3d without game_weapons.json or models.
- tools/setup.py: friend's one-time setup (.NET + Essence download, then attrib/weapons/artmap/stamps/unit_models/export-parts).
  Not yet tested on Windows; Essence release asset name unverified.
