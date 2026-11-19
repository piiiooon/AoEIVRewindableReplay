# Recorder: dump.lua fields and versions, recording, replay file

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Dump fields (v5)
P line: banks, eco upgrades, age, pop, popcap. E entity: id,bp,x,z,vismask,kind,idle,squadid,
hp,flags,build,queue,target (flags: F/W/G/S gathering, H garrisoned, C constructing, A attacking,
M moving; target: entity it is attacking). K / U lines (GE_EntityKilled / GE_UpgradeComplete
context), HMH/HM terrain height grid (once), V version, READY, NMODE.
Map objects (v5, owner: "trees don't move"): one full scan at the start (N|t|1), then only changes:
NC (new/changed: moved, visibility, remaining) and NX (gone). Tracked objects (gaia_/resource_/relic)
every second; trees only checked for being chopped down (1/30 per second); new objects (carcasses)
from a neutral-list re-read every 10 s, a tenth per second. No bursts (v4's 5 s scan made the game
pause every 5 s). parse_log rebuilds 5 s / 60 s snapshots from the state; trees after the start have
vis None and analyze.py uses sight radii for them (explored).
Confirmed in game (v4 run, 2026-10-23): terrain grid 104x104, K/U events, target field,
Entity_FromID / Entity_IsValid / loadfile exist; that console has no dofile and no Scar_DoString
(the Alt+Shift+` console runs in the SCAR state), and it stops taking typed input once the dump runs:
record.py bakes A4D_AUTO_SPEED / A4D_AUTO_END into a temporary copy, one console line.
warnings.log cuts every line at ~4,067 bytes (test2/test5 lines max out at exactly that): dump lines
are split by size (A4D_LINE_MAX 3400) as well as count. v4 lost data there (game6: 831 cut E lines,
long byz_ha_mac names + target field); parse_log skips cut records.
Confirmed in game (v5 run, game6): recorder end to end, no stutter.
A4D_Speed(n) sets the sim rate (default 8 ticks/s; 64 = 8x; the game advances at most one tick
per rendered frame, so the real ceiling is FPS / 8).
`ingame/mock_harness.lua` covers v5 (modes full / noscar / minimal; a deer dies, a carcass appears,
a mine is mined, a tree is chopped). Lua 5.4 at /tmp/claude-0/luasrc/lua in the dev container.

## Resources (dump v8, 2026-10-25; not yet run in the game)
P line ends with X|Name:bank:rate;... for every RT_* resource type the game defines (olive oil, silver,
...; A4D|RT lists them once): bank and Player_GetResourceRate (units unknown until a real log).
parse_log -> players[k]["res"] = {name: [bank, rate]}. techs_bought entries carry per-resource costs.
Used by ../fogline-profile (player profile across games: batch.py records a replay folder, profile.py
builds the page).

## Hits and projectiles (dump v9, owner 2026-11-10; not yet run in the game)
For splash / cleave and the fight simulator. GE_DamageReceived -> A4D|H|t|attacker,victim,damage,hp-after;...;
GE_ProjectileFired / GE_ProjectileLanded -> A4D|PF / PL|t|attacker,projectile,target,x,z (target 0 = ground shot).
Buffered per game time, written when the time moves on and every second (A4D_Collect), chunked by Emit; A4D|EVCAPS
says which events registered; A4D|HERR handler errors (first 20). Context field names (attacker, victim, damage,
currentHealth, projectile, target) as BigManJohn000/aoe4-replay-viewer's recorder v6 found them in the game.
parse_log -> tl["hits"] [t, att, vic, dmg, hp], tl["shots"] [t, "F"/"L", att, proj, target, x, z]. Mock harness: two
hits, one ground shot fired + one landed at tick 4 (run with 6 ticks).
## Replay file (analyzer/replay.py)
Layout from github.com/BigManJohn000/aoe4-replay-viewer docs/rec-record-types.md, checked on test5.
Header: u16 ?, u16 build @2. Command: u16 len, u8 type, u8 player | 0x80 shift-queued, u32 player id @20,
receivers @24 (kind<<28 | index; squad index + 50000 = the dump's squad id: 98.6% of ordered units
found in test5, always the right player), then data type + data (target: 2 pos f32 x,y,z / 3 entity / 4 squad).
- orders(): move, attack, attack-move, gather, build, garrison, ... with shift flag and target.
  Viewer: last 4 s; sight view shows only the observer's own orders (never the opponent's).
- cameras(): eye x,y,z (cm), quaternion (i16/16384), vertical FOV x100. footprint(): view corners
  on the ground, 16:9 assumed; ground = terrain grid (v4 dump) or one plane fitted at 0:00 so each
  player's view centre hits their own TC (17.5 in test5, both players within 0.2 m).
- players() / header() (owner 2026-11-01, found on replay_258000890): per player in the header: 0x01 + u32 n +
  UTF-16 name, 8 bytes, 0x01 + u32 m + ASCII civ (game name, e.g. sultanate_ha_tug); after it the Steam ID as a
  UTF-16 string with its u32 length, and the Relic profile number as u32 nine bytes before that length (by value;
  check against aoe4world). Date (UTF-16) at 0x0a, map after map_size_N. Used by fogline-profile players.py.
- info(): build and duration. Selection, control groups, clicks, keystrokes: not in the file.
## Recording (tools/record.py, Windows)
Launches the replay with -dev through Steam, opens the console by posting the toggle chord
(Alt+Shift+`, then Ctrl+Shift+`), dofile(dump.lua), A4D_Speed, stops at the replay's end, runs run.py.
Console commands go through %TEMP%/fogline_cmd.lua (prints A4D|ACK|n / A4D|NAK|n|err); the typed line is only
loadfile(...) (~120 chars): game3 run cut a 454-char typed line ("unfinished long string"). Full run confirmed (game1).
Own code (owner 2026-11-06: rewritten so the program is his; the earlier adapted versions are gone):
- tools/gameinput.py: Windows input. Game process by a Toolhelp snapshot, main window = its largest visible window;
  posted WM_CHAR / WM_KEYDOWN text and keys (background); console chord posted with this thread joined to the game
  thread's input state and the modifier + Shift marked held; real SendInput presses only while the game is in front
  (never focuses it). Keys by name (KEYS), Chord / CONSOLE_CHORDS.
- tools/gamelink.py: paths (Documents from the registry's User Shell Folders), LogTail (warnings.log; restarts when the
  game recreates it), Console (run / ping / open = background then front, open_front, close), scar(), Steam / game exe
  / build, launch(), close_game(), stage_replay() (gzip unpacked into playback). Used by record.py, fogline-spawns
  spawns.py, bo-maker calib.py / record.py.
- tools/record.py: the replay recorder on top of gamelink (same CLI, "Log saved:", logs/<name>.recorded.log /
  .failed.log, exit 3 closed / 4 incomplete as batch.py expects). Checked against a simulated game and the generated
  Lua with a real interpreter; not yet run in the game.
- dump v11: P line ends with SM|key:value;... for A4D_SM (imperial_council_exp_ott, total_viziers_ott, military_school_limit_ott;
  every player, missing keys left out); parse_log -> players[k]["sm"]. Mock harness ok.
- dump v11 also writes A4D|ES|t|id|UI_Progress=..;jiangnan_tower_unit_index=.. on change for buildings matching A4D_ESM_BP
  (prefecture, military_school, landmark, wonder); parse_log -> tl["esm"]; hud rows col 23 progress [[bp, id, UI_Progress,
  unit index]]; HUD: bar under the landmark icon, a bar per military school in the production row. Not yet in a recording.
- Damage events (owner's question): GE_DamageReceived = when damage lands (projectile arrival), value after bonus / armour,
  killing hit capped at the HP left (no overkill), shots on dead targets log nothing, deflections log 0.
- dump v12: A4D|GE lists every GE_* global once; every GE_ name containing "Abilit" registered (EVCAPS), handler logs
  A4D|AB|t|event,caster,ability,target (caster / target entity id or s<squad id>, ability = BP_GetName of c.ability /
  abilityBlueprint / blueprint ...), the first 16 contexts' fields as A4D|ABK|event|key=type:value. parse_log -> tl["abilities"],
  ["abilityFields"], ["globalEvents"]. Mock harness: GE_AbilityExecuted = 6 fired at tick 4. Field names unconfirmed in game.
- Replay ability commands (replay.abilities; layout per BigManJohn000's docs): types 0x0e / 0x48 cast, 0x72 stop; data type
  36 / 37 / 42 = 01 + u32 PBG (+ target at 10 / 6). data/abilities.json (update_data.py, aoe4world abilities by pbgid: 235,
  always 117 / manual 76 / toggle 34); most PBGs in two test replays are not in it (170923 x159, 5020030 x41, ...) ->
  game_assets.py ability-names (decodes attrib/abilities, pbgid -> file name, models/ability_names.json, local only).
  hud.py --replay (run.py passes it) adds the casts to the recap's abilities row (squad receivers -> an entity of the squad).
- dump v14 (owner 2026-11-12: shallows / fords are walkable, so v13's boat probe on blocked tiles never saw them - "how about a
  check on, can a fishing boat and villager walk there?"): Pass() probes every tile with the fishing boat (one more spawn call per
  tile at load). mapgeo: walkable + boat placeable (both <= BLOCK_D) = "s" (shallows; the 2D pages draw only "w" / "c", so it
  stays walkable there); blocked + boat = "w"; blocked without = "c". build_3d water_map counts "w" and "s" as water outright
  (ev "2"); 3D terrain colours "s" like a water bed (p54). Mock harness ok (naval=0 in the mock); unit test ['.sw', '.sc'].
  Not yet run in the game: whether a fishing boat is placeable on shallows at all is the open question.
- dump v16 (owner 2026-11-12: "for now let's not do a boat check and ship it with your algorithm"): the fishing-boat probe is off
  (A4D_BOAT_PROBE = false; set true to bring v13-v15's probe back) - no extra spawn call per tile at load, PCAPS naval=0. Water
  in the 3D page = the terrain method (p52-p56: lid, min depth 1.8 m, fish / ship evidence, tidy, smooth shoreline).
- dump v17 light view (owner 2026-11-12: "why don't we remove the part that makes it process slower? we don't need the in-game
  visualization"): rendering cannot be turned off from script (no API) and the sim advances at most one tick per rendered frame,
  so frames are made cheap instead. A4D_LightView() (when A4D_LIGHT_VIEW; record.py bakes it in unless --full-view):
  Sound_ForceSilenceEnabled(true), Camera_SetInputEnabled(false), Camera_MoveTo(map corner), Camera_SetZoomDist(1),
  Camera_SetDeclination(89) - each pcall'd, reported A4D|LV|name|ok-or-error; sound / camera input restored at A4D_Stop.
  Camera and sound are local (not simulation), so the replay plays the same. A4D|PERF|t|renderFrames|appFrame every 10 game s;
  record.py's progress line shows "N.Nx real time, N fps" over the last ~60 game s. Mock harness ok (camera / sound functions
  absent in the mock -> logged errors, run continues). Not yet run in the game: whether the camera calls work during replay
  playback, and how much faster it gets, are open.
- dump v18 state models (owner 2026-11-12: "a recording script that records every bit of useful information so I don't have to
  re-record every time I make a non-graphical feature update ... building buffs ... yorishiro, Jeanne d'Arc consecration";
  keys from his attrib_search.txt, 538 state-model schemas). ingame/dump.lua: A4D_SMK_B (270 building keys) / A4D_SMK_U (134
  unit keys) / A4D_SMK_P (193 player keys), first letter = getter (b/i/f); per-tick internals filtered out (gaia wander,
  gather / carry upgrades, trade internals, timers that only count down, UI rates, drop-off tallies ...). Per blueprint the
  keys are probed once (a key that errors is dropped; a key ending in a base civ tag the bp does not carry is skipped) ->
  A4D|SMK|bp|n. Every building and unit (units: A4D_SM_UNITS, record.py --no-unit-sm turns them off) is read every
  A4D_SM_EVERY 2 s (buildings) / A4D_SM_EVERY_U 4 s (units), sliced by id; only changed keys are written, the first line
  of an entity only non-zero ones: A4D|ES|t|id|k=v;... (bool 1/0; units add vet = Squad_GetVeterancyRank). Players:
  A4D|PS|t|player|k=v;... every 2 s, changed only. The old P-line SM part stays. parse_log: ES / PS merged forward
  (_sm_merge) so tl["esm"][id] / tl["psm"][player] rows are the whole state at t; tl["smk"]. tools/buff_check.py section 5
  lists every key that was ever non-zero, with entity counts and blueprints. Cost unknown in the real game: check the PERF
  lines and the SMK counts on the first v18 recording; if slower, --no-unit-sm or raise A4D_SM_EVERY_U.
- dump v18 events (owner 2026-11-12: "add those events so it's more accurate"; compared with bigmanjohn000's recorder.lua, MIT):
  context events written like K / U (EventLine): UQ GE_UpgradeStart, UX GE_UpgradeCancelled, C GE_ConstructionComplete, CS
  ConstructionStart, CW ConstructionWorkerStart, CX ConstructionCancelled, SP StrategicPointChanged; buffered per tick like H:
  I GE_PlayerAddResource (player idx, food, wood, gold, stone; c.resources by name), BI GE_BuildItemComplete (player, BP_GetName
  c.pbg, squad id = Squad_GetGameID like the E records, producer if c.producer / building / entity / source exists - field
  unknown, A4D|BIK prints the first 3 contexts' keys); H gains shieldDamage and isRepairing. Per second: A4D|Q|t|id,size,type,bp
  (queue head via Entity_GetProductionQueueItem + BP_GetName, PITEM_* types; on change), A4D|D|t|squad,x,z / squad,- (Squad_
  HasDestination / GetDestination via SGroup_ForEach(Player_GetSquads); on change; DERR disables), A4D|B|t|player|bp|costs
  (Player_GetSquadBPCost / Player_GetEntityBPCost, first sighting per player + bp, requoted after any upgrade, written when
  changed). parse_log: events types upgrade_start / upgrade_cancel / construct_done / construct_start / construct_worker /
  construct_cancel / point (CTX_TYPES); tl income / built / queueHead / dest / bpCost; hits rows + [shield, repairing].
  Used so far: techs_bought takes the research start from upgrade_start (latest unused one of the attrib / executer before
  done; "exact"), techs_list row [4] = it, hud tech_rows start = it ("start recorded" on hover, row[10]). Not used yet: income
  (exact gathered), built / queueHead (production credit instead of the nearest-building guess), dest (order arrows), bpCost,
  construction events. Mock harness covers each (fake GE ids 7-10). His recorder samples at 0.5 s (ours 1 s, fights 0.25 s);
  otherwise nothing of his is missing now.
- First v18 recordings (owner 2026-11-12): AgeIV_Replay_259818624 (Byzantine vs Malian, 16:31): EVCAPS showed every v18 context
  handler (UQ / UX / C / CS / CW / CX / SP) and every ability handler =0 - they were closures; Rule_AddGlobalEvent takes only
  functions stored under a global name (the fight tests found the same). Worked: H (repair flag on 297 hits; shield 0 - no
  shield civs), I (2,858 credits), BI (producer always 0: the context is only spawnedSquad / pbg / player), Q, D, B, ES / PS.
  Sound_ForceSilenceEnabled(true) errors (takes no argument: a getter). PERF ~19 render frames per game second early, ~16.5
  late; record.py 7.4x -> 5x real time. AgeIV_Replay_259793744 played without anyone's commands taking effect (no neutral
  entities, map generator "holy_sites is all zero", the game's entity debug dump every frame -> 104 MB log): the replay
  does not play on this install (different map version?), not a recorder fault.
- dump v19 (owner 2026-11-12): context / ability handlers registered as named globals A4D_Ev_<tag> / A4D_Ev_<GE name> (EVCAPS
  now carries the error text on a failure); silence = Sound_SetForceSilence(true / false); no state models on wpn_* weapon
  entities (TC / outpost arrows: ~200 keys each, nothing useful). Strategic points (owner: sacred sites are captured from
  Castle by religious units in 30 s - Delhi Sanctity scholars from Feudal, Jeanne d'Arc too - held / paused by any unit on
  the aura, decapped by any unit in 30 s; all sites held = 10 min sacred victory, paused while contested; trade posts used by
  traders): neutral objects with Entity_IsStrategicPoint or a holy_site / sacred_site / trade_post name -> A4D|SSI|id|bp|sp|vp
  once, A4D|SS|t|id,owner,prog p1:p2,near p1:p2,secure,traders;... every second on change (owner = player index from
  Entity_IsStrategicPointCapturedBy, prog = Player_GetStrategicPointCaptureProgress, near = Player_HasCapturingSquadNear-
  StrategicPoint, Entity_GetStrategicPointSecureCount, Entity_GetActiveTraderCount); argument order tried both ways, A4D|SSCAPS
  names the one that worked. The sacred victory timer key is not known (player keys icapture_point_control_timer /
  isacred_sites_captured are in A4D_SMK_P). parse_log does not read SS / SSI yet. Mock harness: Rule_AddGlobalEvent refuses
  non-global functions (like the game), a holy site captured by Alice while Bob contests, fake GE ids 7-12 fired at tick 3;
  run here with lupa (pip --target in the scratchpad; Lua 5.5) - no Lua interpreter on the owner's PC. Not yet run in the game.
- Research clicks (owner 2026-11-12: "upgrade only matters when it is completed ... record both clicked events and completed
  events"): replay queue commands type 3 (unit) / 16 (research): data type 21 = 01 + u32 PBG id + u16 game player id + 4 bytes,
  one command per item; type 5 = cancel (04 + u32 index, meaning unchecked). data/pbgids.json (tools/update_data.py: units /
  buildings / technologies + upgrades by pbgid -> [kind, attribName], 2,729) -> replay.queues(). techs_bought: start = v19
  UpgradeStart event > v18 queue head turning to it at the executer building ("queue") > done - research time ("estimated");
  click = latest unused click of the attrib at that building up to the start (unknown PBG at the same building as a fallback:
  merc contracts, Farimba); queue start set to the click when it is within 1 s (idle building); clicks_out = every click with
  its completion or None. 259818624: all 20 completions got a click and a queue start; not completed: Byz ranged armour i
  593.25 (queued behind damage i, reached the head 617.1, cancelled 618.1, clicked again 637.9, done 661.8), Malian Forestry +
  Double Broadax 479.12 (cancelled). techs_list rows [5] how, [6] click; hud tech rows [10] how ("event" / "queue" / ""), [11]
  click; hover "clicked m:ss · started m:ss (queue) · done m:ss"; hud.py --replay adds tl["queueCmds"] and H["techClicks"]
  {p: [[t, attrib, name, building]]} (not completed; not drawn yet). The Fogline tech list / other techs_bought callers have
  no replay: estimated / queue starts only.
- Log size (owner 2026-11-12: one reference replay from now on, AgeIV_Replay_259818624; "track how much of a recorded element
  bloats the recorded file"): tools/log_size.py <log> [<older log>] = bytes / share / lines / KB per game minute per A4D tag,
  the E record split by field and the share of E records equal to the same entity's previous one. v18 on 259818624: 17.1 MB,
  1.03 MB / game min; E 71 % (12.2 MB: bp names 37 % of it, ids 17 %, x / z 19 %; 77 % of E records unchanged from the
  previous second), F 7 %, NC 5 %, P 4 %; every v18 addition together < 5 %.
- v19 in the game (owner 2026-11-12, 259818624): EVCAPS all 17 =1 (named globals fixed it), LV silence ok, PERF and speed as v18
  (7.4-8.3x early, 5x late). UQ 23 / UX 23 / CS 200 / CW 191 / C 189 / CX 3 / SP 0. SSCAPS: all three capture calls take (entity /
  player, ...) in the listed order ("ab"); SSI: 3 holy_site (strategic point, not victory points) + 2 building_trade_post_west (neither);
  no capture in that game (progress 0 throughout, "near" flickered twice). AB 13,199 lines / 498k events = 32 MB (65 % of a
  49.8 MB log): passive aura pulses field_stone_buff_info_byz (54 Byzantine buildings, ~4.4 / s each, target = executer) and
  open_pit_mine_influence_gen_mal (2 pit mines, ~11 / s); real casts among them: cistern_villager_buff_byz / winery_villager_buff_byz
  (49 each), donso_javelin_throw_mal, villager_town_bell. ABK context fields: executer, target, ability (+ earlyExit on Complete).
- dump v20 (owner 2026-11-12: "delta format"; the dump still reads every entity every second and compares with the last record
  it read): E = keyframe (every A4D_E_KEY 60 s and an entity's first record), ED = only records changed since the second before
  (bp empty when unchanged), EX = ids gone; AB events repeating within A4D_AB_REPEAT 1 s of the same (event, caster, ability,
  target) are counted and written as A4D|ABR|t|event,caster,ability,target,n,first,last (when the run ends and every 60 s).
  parse_log: delta mode when the session has ED / EX lines (the V line sits before CAPS); per player the raw record state,
  written into the frame at the player's next P line; a cut ED record is lost until the next keyframe (counted, printed);
  tl["abilityRuns"], tl["sites"] [t, id, owner, [progress], [near], secure, traders], tl["siteInfo"] {id: [bp, sp, vp]}.
  Check without the game: scratchpad to_v20.py re-encodes the v19 log -> 7.18 MB (from 49.8; ED 1.9 MB, E keyframes 0.21 MB,
  ABR 0.09 MB); parsed frames identical to the v19 parse except the last 9 s (converter artefact: it writes EX only for a player
  with E lines that second), hits / income / built / queueHead / esm / events / nodes identical, ability events 1,202 AB + 497,001
  folded = 498,203. Mock harness covers ED / EX / ABR. Not yet run in the game.
- v20 in the game (owner 2026-11-12, 259818624): 7.19 MB (v19 49.8, v18 17.1; 0.44 MB / game min): ED 1.9, F 1.2, NC 0.9, P 0.7,
  E keyframes 0.2, ABR 0.09, AB 0.08 MB. EVCAPS all =1, speed / PERF as before (the reads, not the writes, cost the frames).
  Parsed timeline vs the v19 one: 987 frames both, same end state, entity records 176,963 vs 176,999, hits / income / built /
  events equal within 1-3 (this run samples 0.1 s earlier). No lost delta records.
- Owner 2026-11-12: v20 is the format for every recording from now on.
- dump v21 (owner 2026-11-12: "complete the recorder first"; all on change): A4D|AA|t|id,a+b / - = active abilities (each
  blueprint probed once against A4D_AB_CAND - 427 toggle / manual / timed / self-cast ability names from aoe4world + the owner's
  models/ability_info.json, BP_GetAbilityBlueprint + Entity_HasAbility / Squad_HasAbility -> A4D|AAK|bp|names; then every
  A4D_AA_EVERY 2 s Entity_IsAbilityActive / Squad_IsDoingAbility); A4D|G|t|holder,squad:squad / - = garrison (buildings,
  Entity_GetFilledHoldSquadSlots / Entity_GetSquadsHeld; n<count> when the squads cannot be read); Q records gain a 5th field,
  the whole queue (bp+bp+..., up to 20); A4D|VTK / VT = win-condition script values (the world state-model schema has only a
  campaign counter, so the sacred / wonder countdowns are looked for in script tables: globals named relig / sacred / holy /
  wonder / victor / conquest / regicide / surrender / wincond / annihil / relic, two levels, numbers / bools, <= 300 paths;
  scanned at load and at 60 s); A4D|QS|t|squad|k=v = the unit key list read through Squad_GetStateModel* (one member per squad
  per tick; SMK "squad:<bp>"); E records gain a 14th field, heading in degrees (5 deg steps; Squad_GetHeading / Entity_GetHeading).
  Bug fixed with it: A4D_EntitySM returned before the squad part when a unit type had no entity keys and no veterancy.
  parse_log: tl activeAbilities {id: [[t, [names]]]}, abilitiesOf, garrison {holder: [[t, [squads]]]}, winValues {path: [[t, v]]},
  winValueKeys, qsm (merged forward), queueFull {building: [[t, [bp]]]}, entity "heading". Mock harness covers each (Trample on the
  spearman, the TC holding the villager, a ReligiousVictory table counting down). The ability probe costs ~427 calls per new
  blueprint (a hitch when a unit type first appears). Not yet run in the game.
- v21 in the game (owner 2026-11-12, AgeIV_Replay_259793744 - Malian M8.MarineLorD vs French SAS; this time it played, the earlier
  empty-map run did not repeat): 11.3 MB / 20.6 game min (0.55 MB / min), 6.6x -> 4.2x real time (57 fps late), EVCAPS all 1, no
  handler errors. AAK 59 blueprints (formation toggles, town bell, pit mine gold / stone toggles, guild hall resource, auto-heal ...;
  formation changes are noise), AA 158, G 60 (TC holding villagers), VTK 72 (_religious / _conquest / _surrender / _wonder found; no
  countdown ran in that game), QS 1,208, heading on every E record.
- Replay APM (owner 2026-11-15; replay.actions): every command per slot except 0x99 camera, 0x9a (exactly 30 / min for every
  player, a heartbeat) and 0x94 (always at the same tick as a 0x92, both 29 bytes; the pair is taken as a selection change -
  unverified - and counts once; owner: selections count in APM and eAPM). eAPM drops a ground move (0x3e to a position) by the same
  slot to the same receiver set within 2 s of its previous ground move, unless an attack (0x43 / 0x16) or attack-move (0x47) came in
  between (owner's rule). Other undecoded types (0x3, 0x5, 0xc, 0x7b, 0x48 ...) count as actions.
- Cached static reads on master (owner 2026-11-15, decision 0007): A4D_EC per id (bp, kind, squad id, building x / z /
  heading), re-read after an upgrade finishes (A4D_EC_ALL = 2 s, set in A4D_OnUpgrade), when the entity gains / loses a
  squad, while a building is under construction (c.uc), else every A4D_STATIC_EVERY = 30 s; gather flags stop at the
  first type; dropped when the id is gone. record.py --full-read = every second. The state-model cadence and the idle
  building lane stay on branch lighter-recorder only. Measured blueprint changes (24 games): see decision 0007.
- Replay APM (owner 2026-11-18, m260952857): 0x7b = place a building (player-only receiver; data type 27 holds u8 1 + u32
  PBG of the building, positions, +4 bytes per extra builder; counts match the building totals) -> now "build", was "unknown".
  0x92 / 0x94 are not a selection: every squad order (0x3e / 0x69 / 0x47 / 0x43 / 0x48 / 0x41 ...) is sent as 0x92, order,
  0x94 (3037 of 3037 pairs; building commands 0x3 / 0xc / 0x10 never are). u32 @4 is a per-player command sequence number
  (0x92 = n, order n+1, 0x94 n+2) and the 0x80 shift flag on 0x92 always equals the order's. So the pair is a wrapper around
  one order (98% wrap exactly one; a mixed selection can send up to 25 orders in one pair) and counted one extra
  "unknown" per click (pion 2280, kou 757, 28-31% of APM). Owner 2026-11-18: taken as start / end of a unit command, both
  now skipped (APM_SKIP); unknown left = 0x8f only. Bytes @8, @13-20
  vary, meaning unknown. 0x8f: one in that game, pion 8 s before the end (resign? unverified).
- 0x92 / 0x94 (owner 2026-11-18, m260952857; tools/cmd_probe.py): no payload of their own - u32 @8 (0..48), @12 = 2 and
  @13-15 vary the same way in every command type (common header), the receiver is the player only and the data is empty
  (0xff). Two layouts: right-click style orders (move / gather / attack / build) are numbered inside the pair (0x92 = n,
  orders n+1.., 0x94 last; 2793 pairs); orders from a command button / hotkey (all 210 attack-moves, abilities, stop, patrol,
  hold, 7 attacks) are numbered first and the pair follows with consecutive numbers (244 pairs). 79 moves have no pair,
  e.g. 10.88 s right after a rally (0xc) by the same player: maybe a mixed building + unit selection. Test game
  protocol: the docstring of tools/cmd_probe.py.
- APM per click (owner 2026-11-18, test skirmish + tools/input_log.py key log, 642 of 672 right-clicks matched to a pair):
  the 0x92 ... 0x94 pair is one order click (right-click, or the left-click ending a hotkey order such as A + click); the
  order(s) inside are what the click turned into (move to ground, gather on a resource, attack on an enemy ...), none when
  it led to nothing (88 empty pairs in the test). Selection keys (1-9, double-tap, `, Space, left-click) are followed by a
  0x92 no more often than a random moment (14-34% vs 37%; right-click 96%): selections are not in the replay. replay.actions
  now counts one action per pair (at the 0x92; category of the first order inside, empty = unit other; spam only if every
  order inside is) and one per command outside a pair: m260952857 pion 3434 -> 3399, kou 1666 -> 1655. Open: 563 unpaired
  0x3f "stop" in bursts in the test game (4 in m260952857); 0x91 at 0:00.25 = game settings (resource / popcap
  multipliers); 0x8b, 0x40 unknown. Skirmish replays are written only to playback/temp.rec (overwritten by the next game).
