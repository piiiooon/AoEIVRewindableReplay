# Fights: death detection, fight review page, fight simulator, calibrated engine, test batches 1-2

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

- `analyzer/fights.py`: deaths (vanished entities, minus conversions, in-place replacements and
  game end; never a unit that shows up again later, i.e. a recording gap; when the log's kill events
  name player units, only those) chained within 20 s / 40 units into fights. Same rule for Fogline's
  "villagers seen killed". Test: 5% of test5's lines tail-cut -> old rule 1,013 deaths, fixed 149 = true. Viewer Fights tab follows the Sight
  selector: own losses always, enemy losses only where seen.
## Fight review (separate page; full information)
- dump v6: while any unit attacks another player's entity, the fight set (attackers, targets, player
  entities within A4D_FIGHT_NEAR 30 of an attacker; rebuilt each second) is sampled every A4D_FAST 0.25 s:
  A4D|F|t|id,x,z,hp,target (x empty = gone). parse_log -> tl["fast"]. Mock harness runs 1 s and 0.25 s
  rules. Not yet run in the real game.
- analyzer/fightlab.py per fights.py fight: odds (Lanchester, current HP, units within 1.5 r at the
  start, TAU 1.5), actual = side that lost less value; target choice (value destroyed per s vs best
  target within weapon range + 8); focus fire; overkill (attackers on a unit not needed to finish it
  before the next sample). Needs the E target field (v4+); overkill rough without 4/s samples.
  NATO-style classes from units.json classes / name words.
- analyzer/export_fights.py -> viewer/fights.html (build_fights.py); run.py writes views/<name>.fights.html.
  Whole game (owner, 2026-10-24): format a4d-fights/2 = global unit table + timeline (full row per
  dump second, partial rows from the 4/s fight samples), fights as bookmarks (timeline marks + list;
  click = jump to start, framed on the fight), cards follow the fight at the current moment, deaths fade
  over 10 s, map objects from full snapshots, terrain cached per view. test5: 3.9 MB.
  P1 = rectangle frame, P2 = diamond (NATO friendly / hostile); glyphs: infantry X, ranged ^, cavalry /,
  horse archer / + ^, siege dot, religious +, hero star, ship wave. Attack lines coloured by target
  choice. Fight framing: deaths + fight circle; terrain relief when the dump has the height grid.
- damage dealt per fight (owner: grouped per unit type): each unit's HP drop between samples split
  among its recorded attackers by expected dps (buildings / no data: weight 8), summed per attacker type
  name (tiers merged) and side; HP lost with no recorded attacker = unattributed. Fight cards: stacked
  bar + shares.
- Fight cards (owner, 2026-10-24: icons over text): per side Army at start (icon x count, units counted
  for the odds), Lost (icon x count + res), Damage (stacked bar + icon chips with %, merged tiers use the
  priciest tier's icon), Techs done before the fight (U events; military and economy, economy faded,
  name + time on hover), then 4 compact meters (odds, target, focus, overkill; explanation on hover).
  Icons: tools/icons.py now also runs on the fights file and embeds tech icons (data/upgrades.json icon
  paths); without icons each falls back to a short-name chip. Fogline's tech list shows them too.
- test5 (v3 dump, no targets): odds only; 6 of 9 fights with odds were "upsets" (odds ignore units
  joining after the start). Target / focus / overkill checked only with synthetic targets.
## Fight simulator (analyzer/fightsim.py; owner 2026-11-10; first draft, review only)
Replaces the build-order maker (bo-maker dropped from the package). Per fights.json fight: army units in the fight
circle + 25 at its start (reinforcements later: "room to explore"), open ground only (owner: terrain / tree-line
positioning is a calibrated part 2), until one side is wiped out (T_MAX 240 s). Four runs: am-am, micro-am, am-micro,
micro-micro. Attack-move = nearest enemy, sticky. Micro, owner's order survive > priority > focus: kite only when every
melee threat is slower; hurt (< 35 %) pull back only from slower threats; target = (cost + 20 x threat dps) / (walk time +
kill time) among the 6 nearest + those within reach + 2 tiles, switch only for 1.3x; focus = allies' committed damage
covering a target's HP cuts its score to 5 %. Spread vs splash waits for splash data (dump v9 hits). Stats: units.json
(update_data now adds move speed, min range, burst) + upgrades done by the fight's start (upgrades.json now carries
aoe4world effects: attack / armour / hp / attack speed / move speed / max range). Score per side = (real share - floor) /
(ceiling - floor), share = enemy value lost / both lost; floor = I attack-move vs their micro, ceiling = I micro vs their
attack-move. game1 findings: real fights end in retreats (real shares far outside floor..ceiling); the micro heuristic
is not always better than attack-move (fight 3: Rus micro lost 3,280 vs attack-move 2,480) - open with the owner.
Page (owner 2026-11-10: "like the circle villager build-order model", i.e. watch it, not numbers): fightsim.py <name>
--html -> views/<name>.fightsim.html (viewer/build_fightsim.py; not part of run.py). Per fight: left the real fight (4/s
fight samples, else 1 s frames; every unit that came within the area), right one simulated run (menu of the four), same
scale and clock; circles at unit size (filled melee, ring ranged, square siege, faint villager), HP arc, attack lines
(bright on a hit), crosses for deaths; play / speed / scrub; results table. Sim frames every 0.2 s (FRAME_EVERY 2).
Calibration plan (owner 2026-11-10: "we need to predict real results"): scripted test fights in a dev skirmish (spawn +
attack-move on open ground, recorded with dump v9 hits + 4/s), one mechanic at a time (1v1 per weapon, melee crowding,
ranged vs melee approach, siege splash, mixed armies at 5 / 15 / 30, blacksmith on / off), fit, then held-out tests and
attack-move-like real fights. Owner adds: record the formation state; orb walking (moving between the attack animation's
end and the next shot; units.json w.dur now has aoe4world's aim / windup / attack / winddown / reload). Micro is a scale:
no micro (attack-move) .. superhuman (searched, so never worse than attack-move); players differ in priorities. Also a
fight-result model from real matches only. tools/fight_probe.py + ingame/fight_probe.lua: first step - do Squad_Create-
AndSpawnToward / Cmd_AttackMove / Formation_GetDimensionsAndOffset work from our console (all exist in the API list of
replay_258000890's log); output logs/fight_probe.txt.
Probe results (owner's skirmish, 2026-11-10): Squad_CreateAndSpawnToward / Cmd_AttackMove / BP_GetSquadBlueprint work;
Formation_GetDimensionsAndOffset returns a table x / y (3 spearmen: 6 x 2); Squad_EntityAt does not exist; a crash came
from touching squads after they died (now: ids + Squad_IsValid / Squad_FromID / Squad_IsAlive); GE_DamageReceived works
(c.attacker / victim / damage / currentHealth). Spearman 3v3: 8 per hit, the killing hit reports only the HP left (2),
12 hits to kill 90 HP; attack interval 1.875 s exactly (15 ticks; the first 2.0-2.13 s), first hit 2.25 s after the order
from 24 apart; approach ~6.2 map units/s (data 1.25 tiles/s = 5 at 4 units per tile: unexplained, check t01 single
unit). tools/fight_tests.py + ingame/fight_test.lua: the test batch (21 tests x 3 runs with jitter; every tick, hits,
projectiles, formation size each second, upgrades given / removed, everything spawned destroyed after each run) ->
logs/fighttests/<test>_r<k>.txt.
Owner 2026-11-10: melee units charge (the ~25 % faster approach); with plain Cmd_AttackMove the probe's groups formed
along the axis ("--" not "||"), so flank met flank. Tests now: t00 / t00b plain Cmd_Move without an enemy (base speed),
t07f the 10v10 with Cmd_FormationAttackMove (order per test: am / fam / move; A4D|FT|CMD line).
Batch 1 results (owner 2026-11-10, 72 runs, analyzer/fighttests.py reads them): 4 map units per tile confirmed (walk
spear 5.0 u/s = 1.25 tiles/s, knight 6.5 = 1.625). Charge on attack-move: spear peak 6.25 u/s (+25 %), knight 7.75,
horseman 8.0 (data 7.5); a spear facing cavalry slows / stops (brace). Damage = data (spear vs spear 8, spear vs knight
24 = 8 + 20 - 4, spear vs horseman 28, knight vs spear 24, archer 5, crossbow vs MAA 17); the killing hit reports only the HP
left. Intervals: spear 1.875 (first 2.0), archer 1.625, horseman 1.75, knight 1.625 (data 1.5); spears vs cavalry irregular
1.625-2.0. No knight charge bonus seen on the first hit (vs a bracing spear). First melee hit at centre distance 3.9 (spear
pair) / 4.7-4.8 (cavalry vs spear). Archer arrow flight 0.625 s; crossbow 0.25 s at contact range. 1v1s are deterministic
(3 runs alike to 0.25 s); groups spread (10v10 spears: winner keeps 1-7). With the batch's own rows, plain and formation
attack-move both meet face on (spread across 11-12, along 2-3); t07 side 2 won 3/3, t07f side 1 won 3/3 (mirror: small
effects decide). Splash (first look; siege died in 5-14 s to the blob): mangonel volley = 3 ground shots, flight 1.25 s,
10 each, full damage to ~3 units from the landing point; nest of bees rockets 6 near, 2.4 (40 %) floor, ~0-4.3 units;
ribauldequin 42 per bolt to ~3 adjacent targets per volley; bed crossbow 17 to 2-3 targets per shot; springald 11 (15 - 4)
one target; cannon one-shot 90 (no splash seen). Re-runs t11s-t16s + t15b: siege invulnerable (SGroup_SetInvulnerable),
the blob Cmd_HoldPosition in tight rows (spacing 1.8); per-test orders / inv / spacing.
Splash re-runs (owner 2026-11-10; siege invulnerable, 18 spears held at spacing 1.8; each hit assigned to the nearest
impact of its tick): mangonel = 3 ground stones per volley, 10 per stone hit (no damage falloff), every unit within ~1.25
units of a stone's landing point hit, ~57 % at 1.5, ~5 % at 2-2.5, none beyond; 1 in 3 stones hits nobody (scatter).
Nest of bees: every unit within 2.0 hit (summed rockets 7.6 near -> 5.3 at 2.0), single rockets 6 full / 2.4 outer
(40 %); outer hits ~20 % at 2.5-6 (likely other rockets of the same tick). Springald (vs held knights): 11 per hit,
2 targets per shot along the line - only because the knights stood 2 rows deep (owner: springald and bed crossbow bolts
pierce until they reach their maximum range; test that with a deep column). Bed crossbow: ground shots, half the F events hit nobody, the others
3-6 targets; hit chance by distance from the line 40-70 % (<= 0.5), 15-30 % (1-1.5), ~5 % (>= 2) - irregular, as the
owner said. Ribauldequin: 1-3 targets per tick, 42 / 31.5 / 27 / 26.3 / 6 (falloff over the volley). Cannon / bombard vs
spears at spacing 1.8: one target per shot (90 = kill), no splash seen. Landed events (PL) only for ground-targeted shots
in these runs; unit-targeted cannon / bombard shots have both F and L.

## Calibrated fight engine (analyzer/fightcal.py; owner 2026-11-10)
Every rule from the owner's test batches (see the docstring): tick 0.125 s; charge by base (spear 1.25, knight 1.19,
horseman 1.07); spear braces against cavalry, cavalry's first hit on a braced spear 2.25 s after contact; melee closes to
radii + min(range, 1.2); swing lands after aim + windup + attack, next one a period later (knight 1.625 override); arrow 35
u/s, bolt 80, siege stones 1.25 s; target = nearest, distance halved for targets with a bonus >= base damage (t17: spears
took the horsemen), re-picked when out of reach; splash re-measured with a 0.6 s window after each landing (hits spread
over 0.5 s): mangonel / rocket hit chance by distance (x1.6 / x1.45 to the measured totals - fitted in-sample), rocket
damage 6 -> 2.4 from 1 to 2.5 units; springald pierce width 1.2 to max range; bed crossbow chance by distance from the
line; ribauldequin volley split over the 3 nearest. Test upgrades applied (aoe4world effects). Check (`python
analyzer/fightcal.py <fighttests folder>`): 25/27 winners (the 2 misses are the mirror 10v10s the game itself splits),
damage dealt per side within 15 % in 41/46, median error 0 %; weak spots: mixed 5v5 / 15v15 side 1 at ~70 %, siege on a
charging blob (t11 / t12: the sim's stones land behind the charging spears), ribauldequin wipes 8 s slow. In-sample: the
held-out check is batch 2 and new mixed fights.
Bug fixed with it: aoe4world bonus targets are word lists whose joined name is the class ("light_melee_infantry"); the
old subset test never matched multi-word targets (archer +5 vs light melee infantry, bed crossbow +6 vs melee infantry)
- gamedata.class_match (strict joined name; loose tokens matched "siege" inside "find_non_siege_land_military") now in
fightcal, fightsim, decisions (counter table) and counter.py (Fogline's counter panel / odds).
tools/game_assets.py: AOEMods.Essence wrapper (sga-unpack, rgd-decode, model-export) for the game's own files on the owner's
PC: check / attrib / weapons (data/game_weapons.json: exact weapon values) / list-models / model. Batch 2 tests in
tools/fight_tests.py (--batch2): pierce columns (rows per side), orb walking (kite modes afterfire / interrupt), charge into
held targets, cavalry / elephant / villager matchups, siege walk, upgrade mirror pairs (u01-u11), siege upgrade pairs
(us01-us03 with baselines), walk upgrades (uw01-uw02).
Batch 2, first part (owner 2026-11-10: p01-p02, o01-o06): springald bolts pierce to maximum range - every knight of a
single-file column hit out to ~29-30 units (range 7.5 tiles = 30), none beyond (3-5 per shot); bed crossbow bolts also
reach max range but hit each unit on the line only ~55-80 % (17 per hit). Orb walking: moving right after the release costs
almost nothing - the weapon cycle runs on while moving (archer shots every 1.75 s vs 1.625 standing, crossbow 2.25 vs
2.125, the same for 0.5 s and 1.0 s moves; the attack order after the move fires as soon as the cycle allows). Moving
0.125-0.5 s after an attack order cancels the shot every time (0 shots in 30 s; a fresh shot from an attack order took 0.625
s in o01) - o07-o09 (0.625 / 0.75 / 1.0 s) find the threshold. Kite script: circles the held target one way round at the
same distance, re-attacks with an attack-move at its position (the first version stepped back each move and lost range).
fightcal: BED_P on the line 0.7; p01 sim 667 vs game 429-715, p02 533 vs 411-557.
Batch 2, rest (owner 2026-11-10; 207 runs in all): held out before any change, fightcal got 26/30 winners and 40/45 sides
within 15 % (misses: knight charge, elephant, villagers, the knight 5v5 mirror). Measured and added: knight charge = first
hit +12 (32 on a knight, 36 on an archer / horseman, 32 on MAA; none on a bracing spear), the next swing 1.25 s after it;
horseman no charge damage; villagers fight with 6 per hit every 3.875 s (the data's weapon is the torch); war elephant 50
every 3.0 s, cleave ~35 % to enemies within 3.5 of the target, its rider (second entity) 25 every 3.75 s; spears brace only
against cavalry coming at them (the rest close in). Upgrades, measured vs aoe4world: blacksmith +1s, Incendiary x1.2,
Elite Army Tactics x1.15 damage / HP (also on spearmen), Biology x1.25 HP, Royal Bloodlines x1.35 HP, Greased Axles x1.15
speed (mangonel 3.01 -> 3.45 u/s), Siege Works x1.2 HP - all as listed; Roller Shutter Triggers springald 3.125 -> 2.5 s
(listed x0.77 = 2.41, tick-rounded); Adjustable Crossbars = 4 stones per volley instead of 3, same 6.875 s (listed:
attack speed x0.99 - wrong; fightcal: stones 4); Chemistry not visible on 90-HP spears (every shot kills) - needs a
sturdier target. A starting HP equal to the old maximum is read as full (the first frame lags the HP upgrade). Orb walking
threshold: a shot from an attack order gets out when the move comes 0.625 s or later (o07 = standing), 0.5 s cancels it.
Now (all runs, kite tests excluded: the engine has no kiting yet): 51/53 winners (misses: the mirror spear 10v10s), 77/87
sides within 15 %, median 0 %. Weak: mixed 15v15 side 1 (393 vs 642), siege on a charging blob, the ribauldequin's wipe time.
Game weapon files (owner's export 2026-11-10, data/game_weapons.json, 676 weapons): fightcal.game_weapon() reads area radius,
near / mid / far bands and factors, landing scatter, angle scatter, range. Mangonel / rockets now use them (GAME_AOE) instead of
the fitted hit tables: each projectile lands uniformly in the scatter disk, every enemy within the area radius of it takes the
band's factor x damage. Distance = centre distance - AOE_EDGE x body radius: 0 = -40 % (t11s / t12s / us01), 1.0 = +20 %,
0.5 = 6/7 siege tests within 15 % - a fit, to be replaced by the game's own radius: fight_test.lua's U line now carries
Entity_GetRadius (fighttests.load -> units[sq]["radius"]). All runs: 51/53 winners, 79/87 sides within 15 % (was 77).
Not used yet: ribauldequin bands (R 1.5, angle 90, penetration 5), bed crossbow angle scatter 7 deg, charge weapon files.
- HP fraction fix (owner 2026-11-13: "why do TIGER's spearmen / villagers spawn hurt (58 / 80)?"): export_fights divided recorded HP
  by the unit's highest HP over its whole life, so units whose maximum rose later (Textiles, upgrades, Lancaster HP auras) looked
  hurt from birth. Units now divide by the running maximum (highest so far); buildings keep the lifetime maximum (3D height by
  construction HP). m260031756: all 852 units full at spawn (was: many spearmen / villagers below). Left: an HP aura that ends makes
  a unit look slightly hurt. Exact fix needs the recorder: Entity_GetHealthMax exists in the game's API (not recorded yet).
