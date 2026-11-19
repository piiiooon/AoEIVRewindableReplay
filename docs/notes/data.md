# Game data: aoe4world files, patch updates, name matching

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Updating data after a patch (owner 2026-11-01: new civs' buildings / units were not recognised)
`python tools/update_data.py [--data C:/aoe4/data-main] [--check]` rebuilds costs / icons / sight / units /
upgrades / production from a local aoe4world data copy, same formats; entries only in the old files are kept (old
replays). Rules: worker = "villager" class; landmark age = wonder_*_age class (attribName ageN is wrong for Mongols);
landmarks = ages 1-3, civs with all three (ab / ay / gol / kt age up differently); TCs not in baseCost.
techs.json / econ.json are not from aoe4world. Civ codes: techs_bought.civ_code(tl, p) = CIV_CODE by the game's civ
name, else the civ most of the player's first units belong to (units.json civs) - new civs work before their game
name is added; UNKNOWN_CIVS collects (game name, code) to add to CIV_CODE.

## Name matching
Game blueprint names can differ from aoe4world's (tier digit position, word order, an extra
word like workshop/bastion). analyzer/gamedata.resolve() handles it; FREE lists spawned units
with no cost (pilgrims).

## Data
`data/costs.json`, `data/sight.json`, `data/techs.json`: from github.com/aoe4world/data
(commit b2cd382). Keyed by blueprint name as the game reports it. `data/upgrades.json`, `data/production.json`
(producedBy, building baseId/cost, landmark build times): same repo @ ce8f375.
