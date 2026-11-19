# Buffs and damage over time: auras, statdiff, dot, in-game buff / DoT / sacred-site test batches

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

- Lord of Lancaster Inspiration (owner 2026-11-13: passive, all military units within 5 tiles +5 % health incl. the Lord, stacks per
  Lord): not in aoe4world's data -> auras.py OWNER_AURAS (source base lord-of-lancaster = unit_abbey_king_2_lan, civ hl, select
  class military); stackable auras also give A["stacks"] {ability: {entity: [[t0, t1, n]]}} (segments of a constant count);
  build_3d writes one buff row per level ("Lord of Lancaster Inspiration ×n (+5n% HP)") and D.buffHp {name index: HP %}; the
  selected-units box raises each unit's full HP by its stacks (p65). m260031756: 287 TIGER units, up to 4 stacks (4 Lords:
  4 x 170 x 1.2 = 816). Open: the recorded HP does not follow +5 % per Lord - statdiff sees hobelars 122 / 100 (+22 %) with 1-4 Lords,
  crossbowmen 97 / 80 with 2-3, Lords 243 / 170 (+43 %): something else raises HP too, or the bonus works differently.
- Buff / debuff tests, step 1: tools/buff_list.py OWNER = owner's list (attachment "numbers may be incorrect") + Scots / Vikings +
  debuffs, each (name, civ, group A ordered / B unit aura-conditional / C building aura / D terrain-naval / E tech / eco / debuff,
  search words). game_assets.py buff-scout -> logs/buff_scout.txt: per entry the aoe4world abilities matched and the decoded
  attrib files (abilities, upgrade, sbps, ebps, statemodel_schema, weapon) naming its words, values with modifier / duration /
  radius / target / cooldown keys; then every aoe4world ability not in the list. Next: test batches per group on Dry Arabia 2p
  (owner clears the middle), buffed vs identical unbuffed setup, ability events from dump v12.
- Owner 2026-11-11: eco effects are tested too (own group after E). 3D p22 ring fill: inner arc in each unit's ground ring -
  ranged = time since its last shot / weapon period (dump v9 shot events; else the drawn cycle while attacking; full when idle),
  white; chargers = charge cooldown, gold: build_3d chargers() = units whose game charge weapon hits harder than the normal one
  (knight 36 vs 24; horseman 9 = 9; no game_weapons.json: name rule), D.charge per unit [spent at first damage dealt while
  charged, last combat], refill over D.chargeCD = CHARGE_CD 10 s out of combat - a guess (buff_list "Cavalry charge recharge"
  scouts the game's value). otto1: 2 hospitaller knights, 3 charges.
- buff_scout (owner 2026-11-11, 3 MB; 979 abilities / 1,854 upgrades / 2,093 sbps / 4,153 ebps decoded): each ability file gives
  activation (always_on / timed / toggle / targeted / self_targeted), recharge_time, range and the tooltip's numbers
  (ui_info help_text_formatter args). Corrections vs the owner's list: Mehter ranged armour +1 (not 2); Extra Materials 25 HP/s
  r16; Network of Citadels 30 % r50 (castles 20 %); Triumph is timed (recharge 30, 45 s, r32); Ryokan 3 / 4 / 6 per age;
  Khan arrows last 5 s (recharge 90, r35); Billmen = always-on aura r20 (-1 armour); Scorched Earth args 60 / 15 / 25 / 60.
  Not found by the words: Composite Bows, Long Wall, Tranquil Venue, Yam, Polish, House Unified, Khan's hunter, Torguud,
  Stronger Together, Bogmadr, Elephant Formations, Naval Deployment, camel unease, HRE prelate inspiration, the charge recharge.
  The scout's key filter is noisy (ui / cost lines) and caps at 80 values per file, so the applied modifiers (action lists)
  are not shown.
- Group A buff tests (tools/fight_tests.py --buffs A, ids a00-a08): fight_test.lua C.cast = {{side, ab, at = s or "hit",
  target self / pos / enemy, again}}: Player_SetAbilityAvailability then Cmd_Ability, trying (sg, ab[, tg]) / (sg, ab, tg, nil,
  true) / (pl, sg, ab, tg[, nil, true]); first form without an error is kept -> CAST line; every GE_*Abilit* event -> AB lines
  (ABEV lists them). a00 = probe (longbows, no enemy). Mock-run in Lua 5.4 (scratchpad ftmock.lua). Not run in the game.
- Group A run 1 (owner 2026-11-11): Cmd_Ability(sgroup, ability) works (form "sg,ab"). Measured vs baseline: Arrow Volley
  longbow shots 1.625 -> 0.625 s for 6 s; Fortitude sipahi swings 1.75 -> 1.25 (+40 %); Body of Iron arrows on the monk 5 ->
  2.5 for 15 s. No effect: Pavise (arrows on crossbows stay 5; owner: no glow), Palings (no stun / 19-damage hits), Forced March
  (5.0 u/s; the ability needs upgrade_landmark_force_march_sul) - Pavise / Palings sides were on Cmd_HoldPosition. Mehter a03:
  the toggled side swung 1.75 vs 1.625 and lost 3/3 - the drum is likely on as spawned and the toggle turned it off (a03b
  baseline added). Khan: spawning works (a04p); a position-targeted Cmd_Ability crashed the game twice (a04, a04q; CAST ok,
  crash ~1 s later) - position casts dropped. ABEV: one function registered only once (a05+ logged nothing); now one closure
  per GE_*Abilit* event, only our casters, GE_AbilityComplete names the cast; a cast with no event of its own ability within
  1.5 s is retried with the next form (3 tries, CASTRETRY). Order "none" = no command (Pavise / Palings sides).
- Owner 2026-11-11: the AI (side 2) had researched blacksmith upgrades while the stage was set up - seen as side 2 spear 9 vs
  8 (a03b), sipahi 12 vs 11 (a02), knight 25 vs 24 (a07); a02 / a07 / a07b need re-runs. fight_tests.py writes
  ingame/fight_clean.lua (150 generic combat upgrades from upgrades.json: not unique, not upgrade_add_*, with a combat effect);
  fight_test.lua removes those a player has before each test (CLEAN|side|n|names), then grants the test's own. --only skips
  runs already on disk (the owner's a06-a08 re-run did not happen) - use --redo.
  Mehter (owner: three toggleable auras): tests a03n (no mehter), a03z (untoggled = state as spawned), a03a / a03m / a03r (one
  drum each; side 2 without a mehter), a03rb baseline; casts go to the mehter alone (unit).
- Group A run 3 (owner 2026-11-11, CLEAN lines empty = no upgrades left on either player): Forced March with the tech: spears
  5.0 -> 8.0 u/s from 1 s to ~11 s (+60 %, files say 100 - a speed cap of 2 tiles/s?). Fortitude clean: 1.75 -> 1.125-1.25.
  Mehter: a03n spears 1.875 s, 8 per hit; a03z (mehter, no toggle) 1.75; a03a (attack drum) 1.625 in 2/3 (= +15 %); a03m / a03r
  casts failed (SGroup_Create of an existing name -> nil -> "Util_GetPlayerOwner: invalid type NIL"; now unique names).
  Pavise / Palings: still no effect with all three forms. ABEV empty: Rule_AddGlobalEvent took none of the closures - now
  named globals A4D_FT_Ab_<event> (errors listed). Added forms (sg, ab, sg) and (egroup, ab), 5 tries, CANCAST line
  (Squad_HasAbility / Entity_HasAbility / Squad_CanCastAbilityOnSquad / *_IsAbilityActive) and ACTIVE after each try.
- Manual buff tests (owner 2026-11-11: "provide the units and I press them"): ex "wait" = s before any order (WAIT line), "manual"
  = instruction printed after the console closes; ability events and first-hit tracking run without a scripted cast. a06m
  Pavise, a07m Palings, a03mm / a03rm Mehter armour drums, a04m Khan signal arrow (the scripted position cast crashed the game).
- Owner 2026-11-11: spawned units take the owning player's civ (his side 1 was Sengoku: "French" arbaletriers came out as an unknown
  unit without Pavise; abilities may also need the age). fight_tests.py CIV_OF per buff test (english / ottoman / mongol /
  chinese_ha_01 / french / sultanate = Player_GetRaceName), runs one civ's tests together and asks (input) before each civ:
  skirmish as that civ + 1 AI, Dry Arabia 2p, starting age Castle; --no-prompt skips. fight_test.lua: CIV|side|race|age|wanted,
  ERR when side 1's race does not contain the wanted one (the run goes on). Earlier group A runs were all on a Sengoku player.
- Owner 2026-11-11: units did not always spawn on his side -> side 1 = Game_GetLocalPlayer (else the first human), moved to the
  front of the player list (ME line). Pavise spawned on cooldown -> manual a06m / a07m use wait = "cast": orders only after side
  1's own cast is seen (AB event that is not an aura / influence; 120 s max) + ex "after" s (a07m 20: palings take ~15 s to go up), GO line; secs counts from the go.
- Manual group A (owner 2026-11-11; his run used the files before ME / wait = "cast"): Mehter drums are exclusive - each toggle
  fires the new drum's event and the attack drum's (attack drum on as spawned). Melee-armour drum: spear hits on side 1 8 -> 6
  (+2); ranged-armour drum: arrows 10 -> 9 / 5 -> 4 (+1, as the files say; owner's list +2). Pavise (French player, cast by hand):
  arrows 5 -> 1 for the 30 s (+5 ranged armour, floor 1). Palings: deployed late (sped-up game; orders came at 10 s): knights
  hit them in r2 / r3 - the damage event names the knight as attacker and itself as victim, 19 per hit (9 and 5 hits); stun
  not measured. Khan (a04m): side 1 was French (player order) so the owner cast on side 2; HA intervals 0.75 vs 0.875 in the
  5 s, no baseline - redo with the current files.
- Owner 2026-11-11 (Mehter): drum buffs stick to the unit ("retroactive"): a group buffed with melee armour by one mehter keeps
  it when merged with a group carrying another mehter's attack-speed buff - each unit holds one drum buff at a time, the one
  it got. Open: does it last after leaving the aura, and does a different drum ever overwrite it.
- Re-run (owner 2026-11-11, current files; ME = his player both times): Palings fully up (knights 20 s after the cast): each
  knight takes 19 per paling contact (2-3 hits within 0.5 s, logged knight -> itself), no stun - the knights' own hits land on
  the same tick and their next swings come at the usual 1.25 / 1.625 s (owner: "didn't stun for 2.5 s"). Khan attack-speed arrow:
  horse archer shots 0.875 -> 0.75 s for the 5 s in 3/3 runs (+17 %, not the listed +50 % = 0.58), the enemy's stayed 0.875.
- Owner 2026-11-11: Mehter drum buffs do NOT persist after a unit leaves the aura. Buff testing paused (owner).
  Khan attack-speed arrow (owner's source, community-measured, "affects every unit differently"): archer 1.5 -> 1.12, crossbow
  2 -> 1.38, handcannon 2 -> 1.5, mangudai 1.25 -> 0.94, khan 1.88 -> 1.25, springald 4 -> 2.62 (roller shutter 3.31 -> 1.94,
  improved 3.04 -> 1.66), mangonel 8.75 -> 5.75 (crossbars 7.25 -> 4.25, improved 6.65 -> 3.65), traction trebuchet 9.5 -> 9,
  bombard 5.5 -> 2.88, light junk 0.95 -> 0.85, war junk 4.5 -> 2.88 (swivel ballista 3.25 -> 2.25), baochuan 6.5 -> 3.5. Fits
  "the +50 % shortens only part of the cycle" (the reload), not the whole period; our horse archer 0.875 -> 0.75.
- tools/buff_check.py NAME [--replay]: test aid for building buffs and Tughlaq governors - upgrade events named *govern* + _tug
  upgrades unknown to upgrades.json; dump v12 ability events (count, event names, those aimed at a building, target values
  seen); replay ability commands aimed at a building entity (pbg, name); the building spans buff_spans() gives. Unverified: the
  replay's entity target ids = the dump's entity ids (squad ids are index + 50000).
- analyzer/statdiff.py <timeline> [out] (owner 2026-11-12: buffs / debuffs as the difference between recorded and calculated
  stats; review only, CLI, not in run.py yet): damage per hit (unit vs unit, other player, not the killing hit, no siege /
  splash) vs fightcal.hit with the upgrades completed by then (techs_bought + effects_of); max HP vs calculated; attack interval
  (same attacker / target, unit targets only - buildings log several events per hit) vs period; move speed while flagged M vs
  walk; hits on itself. 259818624 findings: Byzantine units +4 per hit 13:27-13:48 / 15:2x (horseman vs javelin 22 / 18, vs
  spearman 12 / 8, knight vs villager / javelin 31 / 27) = the Hippodrome's Triumph casts (13:26-14:11, 15:22-16:07); Malian
  spearmen vs cavalry 12 (expected 28 / 32: the spear bonus missing - the donso javelin throw?), spearman / mansa javelin hits of
  1 (unknown source); Malian spearman vs Byzantine spearman 6 (8) at 12:34; mansa javelin interval 1.5 s (period 2.125); knights /
  horsemen / scouts hit themselves for 2.5 (x144 / x138 / x5; unknown). Max HP matches everywhere. Speeds: p90 above walk for
  Malian spearmen (6.04 / 5 = the charge) and villagers (garrison jumps).
- statdiff damage over time (owner 2026-11-12, the known sources): Mansa Javelineers poison 3 over 6 s and Malian Poisoned Arrows
  (1 every 2 s x 3, stacking per hit), Kipchak bleed 2 / s x 6 (no stacking, reset by any Kipchak hit; Triple Shot side arrows
  0.6 / s), Zornhau gilded landsknecht 2 / s x 10. A tick = a hit of exactly that damage k x interval (+-0.2 s) after a real hit of
  the same attacker on the same victim -> R["dot"], not a deviation. 259818624: mansa javelin hit 16 then 1 at +2 / +4 / +6 s
  (as described), 85 ticks / 11 victims matched. Left over: Malian spearmen's 1-damage hits on knights (x23, ~1.6 s apart, up to 4
  in one tick - not one of the listed sources), mansa javelin 17 / 5 (= hit 16 / 4 + a poison tick on the same tick?), 8 lone
  1-damage mansa hits (their hit was a killing hit or a tier change?).
- analyzer/auras.py <timeline> [--replay] [out] (owner 2026-11-12: "if a unit enters the radius they would get buffed"; review
  only, CLI): data/abilities.json now carries aoe4world's auraRange (tiles), activatedOn and effects (tools/update_data.py).
  always = on while the source stands (finished buildings; sources by base id in activatedOn or the dump's AB / ABR callers),
  only for the source owner's civ (aoe4world civs; else Network of Castles fired on a Byzantine town centre), no radius = not
  placed; toggle = from the source's AbilityExecuted to its next toggle (*default* on from the start); manual / timed = cast
  (AB AbilityExecuted or the replay's ability command, deduped within 1 s) lasting build_3d.KNOWN_DUR / effect duration / 10 s;
  a cast with no activatedOn = the caster only (Trample: aoe4world's 7.5-tile range is the trample reach), else every owner
  entity matching the effect's select within the range (0 = whole map: Triumph). Spans [id, ability, start, end]. Not modelled:
  conditional auras, stacking limits, enemy debuff auras. 259818624: Triumph 20 cavalry 13:27-16:07 (1,091 unit-s), Trample 8
  casts; Byzantine / Malian civ auras with effects in aoe4world but no unit here: cistern akritoi, docks speed, gbeto ambush ...
  field_stone_buff_info_byz is executed by the 54 Byzantine villagers (not buildings), effect "unknown" in aoe4world.
- statdiff + auras: statdiff.py <timeline> [--replay] runs auras first; a damage deviation is "explained" when the attacker's
  attack buffs / the victim's armour buffs active then (span -0.5 / +1 s) cover it. 259818624: every Byzantine +4 (knight /
  horseman hits 13:27-15:32) explained by Triumph. fightcal SELECT_ALIAS mansa-javelineer -> javelin-thrower (aoe4world's Ranged
  Damage I list names javelin-thrower only; the game gave mansa +1 from 13:52: 16 -> 17, 4 -> 5). Left: Byzantine knights 1 below
  expected vs mansa javelins from 15:25 (Teardrop Shields done 15:24: extra ranged armour aoe4world does not give knights);
  Malian spearmen's non-melee hits - 6 on Byzantine spearman / longbowman (melee would be 8), 12-14 on horsemen (28-32), 1 on
  knights (28): consistent with a ranged javelin of 6 with a bonus vs light cavalry and the floor of 1 on knights, i.e. the donso
  throw (owner's guess); the dump's donso AB events (Executed -> Complete ~27 s later, target = self) do not line up with these
  hits, and data/game_weapons.json has no javelin / donso weapon (not in the owner's export) - unconfirmed.
- Owner 2026-11-12: Teardrop Shields gives Cataphracts +1 melee AND ranged armour (aoe4world lists melee only) -> fightcal
  EFFECT_FIX (owner's corrections appended by effects_of); 259818624 knight vs mansa javelin deviations gone. Triumph (owner):
  +10 % speed, +4 damage, 2.5 HP / s regeneration for all cavalry; lasts 1 s per supply point (max 45; 10 points when the
  Hippodrome is done, +1 per 25 s), 30 s cooldown. The regeneration is logged as GE_DamageReceived with attacker = victim and
  isRepairing true (2.5 every 1.0 s) -> statdiff "heals" (every isRepairing hit; also villagers repairing, 3.12). auras.py ends a
  cast at the dump's AbilityComplete (v19+: Triumph 806.75 -> 840.75 = 34 s, 922.75 -> 933.75 = 11 s; the heals ran 13:26-13:59 /
  15:22-15:32); without it Triumph uses the supply rule, which gives 29 s for the first cast (5 s short - rule or start count off).
- Donso javelin throw (owner 2026-11-12: Malian spearmen's second weapon, ranged 5 / 7 / 8 / 10 by tier, +5 / +7 / +8 / +10 vs
  cavalry, 6.5 tiles (min 2.5), every 15 s; torch 10 / 13 / 17 / 21 per age, 2.12 s): statdiff ALT_WEAPONS; the throw also takes the
  blacksmith ranged damage stages (+1 each; 259818624: hardened vs horseman 7 + 7 - 2 = 12, vs Byzantine spearman / longbowman
  7 - 1 = 6, veteran vs horseman 12-14 and vs knight 10-11 with Ranged Damage I / II). Buildings "hitting themselves" for their full
  HP = deleted by the owner (owner: Malians ring a pit mine with houses and delete one for a mining camp). Left on 259818624: 23
  one-damage hits by veteran Malian spearmen on knights, ~2 s apart in stacks (poison-like; not in the owner's list).
- Owner 2026-11-12: donsos have no poison. The 23 one-damage "spearman" hits on knights (259818624, 13:19-13:23 on knight
  1000006755 by spearman 1000006519 walking away 25-33 units off with no target; 15:27-15:31 and 15:38-15:40 on two more knights)
  are Mansa Javelineer poison ticks credited to the victim's latest attacker: the ticks keep the javelin hits' cadence (hits at
  13:16.50 x4 / .62 x2 / .88 / 17.12 -> ticks at +2 / +4 s, named after the spearman whose throw landed at 13:19.00). statdiff now
  matches a tick against every damage-over-time source hit on that victim, whoever the event names (buildings too): 159 ticks
  on 16 victims, named mansa 93 / capital TC 34 / spearman 23 / TC 9. So the attacker field of a GE_DamageReceived tick is not
  the poisoner - anything that credits damage to attackers (recaps, fight damage shares) gets poison wrong.
- analyzer/dot.py (owner 2026-11-12: "fix those"): the damage-over-time table (moved out of statdiff) and retag(tl): a tick is
  re-credited to the attacker of the source hit it lines up with (any attacker named on that victim); rows gain [source name,
  attacker the game named]. analyze.py rewrites tl["hits"] with it before analyzed.json (hud.py recaps / arenas), build_3d does the
  same on the raw timeline (charge / deflection). 259818624: 80 ticks re-credited. Also fixed: hud.hit_recaps / arena_recaps named
  each attacker / victim by its FIRST blueprint - tier upgrades (javelin thrower -> Mansa Javelineer, longbowman 2 -> 3, spearman
  1 -> 2) stayed under the old tier; now the blueprint at the hit (dot.who). Fight recaps on 259818624: mansa 330 -> 1,306,
  javelin thrower 954 -> 49, longbowman 3 1,207 -> 3,253 / longbowman 2 2,074 -> 28 (the upgraded units' damage moved to their tier).
- Buffs in the viewer (owner 2026-11-12: "go ahead"): run.py runs auras.py (timeline, --replay) -> work/<name>.auras.json and
  statdiff.py --auras -> work/<name>.statdiff.json after hud.py (soft steps; stale files removed first); build_viewer.py --buffs /
  --statdiff embeds D.buffs {p: {player: {ability: [[start, end, peak units]]}}, names, fx, find [[t, attacker's player, attacker,
  victim, observed, expected]] (unexplained, <= 500), explained, dot, heals}. Viewer, only with Show true values / Everything:
  lane under the basics marks (one per player; bands per ability coloured by effect - red attack, blue armour, green speed, lime
  heal, violet other - stacked 3 deep; "?" = unexplained damage dealt by that player's units, one per 10 s cluster, tooltip with
  the pairs; click = seek) and a "Buffs (review)" panel after the basics panel (buffed now per player with units / until,
  unexplained hits within 15 s, damage over time re-credited). auras.py also writes byPlayer / names. Checked in headless Chrome
  on 259818624 (lane: Triumph 13:27-14:00 / 15:23-15:33, Trample, one "?" at 13:23; panel at 13:30). Japanese labels not added.
- Buff glows (owner 2026-11-12: "buff should be a whitish gold glow"): build_3d aura_buffs() replaces the older cast logic as the
  3D page's buff source - analyzer/auras.py spans (the viewer's lane: auras, toggles, casts ending at AbilityComplete) + Byzantine
  buildings while the dump's state model cistern_influence_bonus_active_byz is on ("Cistern influence"; bonus size not in the
  data) + the older buff_spans() entries on buildings (abilities aimed at a building). Every buff = one colour: #fff0c2 ring +
  soft #ffe9a8 halo, additive, pulsing (units and building footprints). 259818624: 59 spans (21 cistern buildings). statdiff:
  attack intervals faster than the period and moves faster than 1.15 x walk count as explained when a buff with attackSpeed /
  moveSpeed is on the unit, and moves within a melee unit's charge speed (fightcal CHARGE, not villagers) as "charge"
  (259818624: Malian spearman 236 charge-seconds, knights 18 charge + 1 Triumph; ranged units' / villagers' fast seconds stay
  unexplained - formation catch-up, garrison jumps).
- Test batches D / S (owner 2026-11-12: "it's hard to find those events in games, so let's do the tests"; tools/fight_tests.py
  --buffs D / --buffs S, one skirmish per civ, starting age Castle):
  D damage over time, each vs held men-at-arms: d01 / d02 1 / 3 Mansa Javelineers (tick size, interval, stacking), d03 2 mansa
  + 3 spearmen (who the game names on a tick), d04 / d04b Malian archers with / without Poisoned Arrows, d05 / d06 1 / 3 Kipchaks
  (no stacking, reset), d07 Kipchak + upgrade_mangudai_triple_shot_mon_ha_gol (the upgrade name is a guess), d08 / d08b gilded
  landsknechts (hre_ha_01) with / without Zornhau. Civs: malian, mongol_ha_gol (Golden Horde), hre_ha_01 (Order of the Dragon).
  S sacred sites (English, a 2p map WITH sacred sites): s01 monk capture, s02 contest (enemy spearman 10-20 s), s03 monk leaves at
  15 s, s04 decapture of a site held from the start (Entity_InstantCaptureStrategicPoint), s05 decapture contested.
  fight_test.lua site mode: C.site centres the test on the sacred site nearest the axis centre (SITE line), C.on spawns a side
  on it, C.held pre-captures it, C.steps = {{at, side, go = site / away}} (Cmd_Move; STEP lines), SS|t|owner|prog 1:2|near 1:2|
  secure|gold 1:2 every 0.5 s; site tests run their full time with an empty side. Checked with a mocked API (scratchpad
  ftsite_mock.lua under lupa): steps, pre-capture, pause while contested, decapture, gold. Not yet run in the game.
- Test batch D results (owner's runs 2026-11-12, logs/fighttests/d*): mansa poison 1 at exactly +2 / +4 / +6 s after each hit,
  a stack per hit (3 mansa = 3 ticks per beat; 6 per javelin vs held MAA, period ~2.125 s); Kipchak bleed 2 / s on its own clock
  (first tick 0.5 s after the hit, then every 1.0 s, a new hit keeps the clock), ONE stream for 1 or 3 Kipchaks (no stacking);
  Triple Shot (upgrade_mangudai_triple_shot_mon_ha_gol works on Kipchaks) adds 1-damage side arrows and two 0.6 / s streams;
  Zornhau 2 / s, one stream for 2 landsknechts (not stacking; dot.py changed), none without it. Tick naming (d03): run 1 every
  tick named after the mansa, runs 2 / 3 about half after a spearman - the game names the poisoner or another recent attacker.
  dot.tick_of / too_old (shared with statdiff): stacking poisons = exact multiples, non-stacking bleeds = within n x every + 0.6 s
  of the latest source hit; on the test runs every tick matched (one false match: a killing blow capped at 2 HP). Durations not
  measured (attackers kept hitting): new d05d / d08d (hit 4 s, walk away). Poisoned Arrows granted right before the spawn did
  not reach the archers and stayed into the baseline (owner): d04b now runs first and removes it (C.rm), d04 gets a prep run
  before each run (an empty run granting it with C.keep); RM / prep lines in the logs.
- D reruns (owner 2026-11-12): Kipchak bleed lasts 6 s after the last hit (6 ticks of 2, +0.375 .. +5.375 s; 3/3 runs alike);
  Zornhau 10 s (10 ticks of 2 at exactly +1 .. +10 s); Poisoned Arrows: baseline clean (C.rm), with the upgrade ticks of 1 in
  runs 2 / 3 but not run 1 even after the prep run - a granted upgrade takes a while to reach newly spawned archers (r2 / r3 valid).
- S runs reset the site (owner: "the sacred site test has to have a decap in between"): before each run of a capture test (site,
  not held) fight_tests.py runs <id>reset - an enemy spearman on the site with C.until_neutral, which ends the run once the site
  is neutral with no capture progress (up to 90 s; END "site neutral"); the last run's monk is removed at its end as before.
  Mock-checked (a held site decaptured in 30 s, ended at "site neutral").
- Sacred site batch, first runs (owner 2026-11-12): s01 r1 fine - site 1000005002 at (2, -2), monk spawned 4.5 units from its centre
  (the game moves spawns off the monument), progress 0 -> 1 linearly (1/30 per s), captured at 30.5 s, "near" drops to 0 once it
  is held; progress is one signed value per site (side 2 reads -side 1); the skirmish had ~100k gold, so the trickle does not
  show. Run 2 logged "no sacred site on this map": a captured site belongs to the player and is no longer neutral, so the reset
  spearman / monk spawned around the axis centre (owner: "2 building tiles west of the site"). fight_test.lua now keeps the site
  for the session (A4D_FT_SITE_ID) and also searches both players' entities (Player_GetEntities). Mock-checked (owned site found,
  decaptured, "site neutral"). The two bad files are in logs/fighttests/invalid/.
- Sacred site batch S results (owner's runs 2026-11-12; 3 runs per test agree to 0.1 s; every reset ended "site neutral"):
  capture progress is ONE signed value per site, -1 .. +1 (+ toward player 1; player 2 reads it negated); 1/30 per s while one
  side's capturing units are on it alone - monk capture 30.5 s (s01); contested by an enemy spearman: frozen (0.36) while both
  are on it, resumes after, captured at 42 s (s02); monk leaves: drains at the same 1/30 per s (s03); decapture of a held site:
  drains 1/30 per s, the owner stays until the bar is empty, neutral at 30.5 s (s04); contested decapture: frozen (0.64) while
  both are on it, and once no unit of either side counts as near (34.5 s; the enemy spearman probably killed) the bar refills by
  itself at 1/30 per s (s05, as the owner's description). "Capturing unit near" = any unit that can change the state (monk
  capturing, a spearman decapturing / contesting); the owner's monk on its own held site counts 0. hud.js circles use the signed
  value (sign = colour, size = arc), a dark track under the arc (a held site being decaptured reads); the old "> 1 = percent"
  guess removed. Gold trickle not measured (the skirmish had ~100k gold).
- Cistern buffs (owner 2026-11-12): Irrigated = villagers within 9.5 tiles (38) of a cistern gather +10 / 14 / 18 / 22 / 24 % by its
  water level (aoe4world says 26 at 5), kept 20 s after leaving, not stacking - recorded per villager by the game
  (cistern_highest_tier_within_byz = the best level around it, cistern_gather_aura_overlaps = cisterns in range); build_3d glows a
  villager from tier > 0 to 20 s after it drops ("Irrigated Lv n (+x% gather)"). Akritoi Defense = a cast at a cistern: villagers
  within 9.5 tiles get a spear attack (+1 / 2 / 3 / 5 by age) and +2 melee / ranged armour for 30 s, keep it after leaving, and
  villagers entering later get the rest (150 s cooldown shared by all cisterns): auras.py STICKY (once inside, kept to the window's
  end), KNOWN_DUR 30, ALIAS activate_akritoi_byz -> landmark_activate_akritoi_byz (aoe4world lists only the landmark one; range
  9.5 tiles, armour +2 on villagers). Injected-cast check on 259818624: 50 villagers at the cast, 4 walking in later, all to +30 s.
  No real Akritoi cast recorded yet (the state model cistern_time_of_akritoi_complete stayed 999999).
