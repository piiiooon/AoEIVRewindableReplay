# Observer HUD (analyzer/hud.py, viewer/hud.js): bar, stats, recaps, arenas, upgrade rows, sacred sites

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Observer HUD (owner 2026-11-11: the in-game caster bar as the layout; both pages; full values in every view)
- analyzer/hud.py work/<name>.analyzed.json -> work/<name>.hud.json (--fights for recaps + upgrade rows); run.py now always runs
  export_fights, then hud.py (soft), before the pages; build_viewer.py / build_3d.py --hud embed it as D.hud.
- Rows every 2 s per player (cols in hud.json): bank + gathered /min over the last 60 s per resource (extras from dump v8
  res when ever > 0), villagers per resource, idle, pop / cap, age, villager / military (kind m) counts, production buildings
  with queue > 0 per bp, landmarks under construction (build < 1, cancelled excluded), cumulative idle / villager seconds,
  gathered, army value, enemy villagers killed, enemy value destroyed (basics.per_player + fights.find_deaths).
- Recaps per fights.json fight: lost value / units, lostBy (bp, name, n), damage by unit type (bp, name, dmg) + unattributed.
- viewer/hud.js (inlined at /*__HUD_JS__*/): FoglineHUD.create({bar, stats, recap, data, icon, techIcon, pcolor, civName}).
  Bar: per side resources (stock, /min, vil), pop / cap + idle, name / civ / age numeral, upgrade rows (eco / military / other,
  stage notches), production chips + landmark progress; centre villager / military compared bars + clock. Stats: villager
  work %, idle time, collected, army value, worker kills, destroyed. Recap: shown for RECAP_HOLD 25 s after a fight ends.
- 2D viewer: bar above the grid, stats / recap over the map's bottom corners; toggles Observer bar / Stats / Recap.
  3D (p16): bar replaces the upgrade boxes (toggle "bar"), army row under it, stats / recap above the graph; toggles stats /
  recap. Checked in Chromium (3D with the stub THREE) on game1.
- Owner 2026-11-11: centre bar compares army value (not military count); 3D standing army (p17) bigger (36 px icons) and split
  at the screen's middle - player 1 right-aligned to the centre line, player 2 left-aligned from it, biggest group innermost.
- Owner 2026-11-11 (p18): HUD ~20 % bigger; upgrade icons on a turquoise tile (in-game look); right side keeps food..stone order
  (only the blocks mirror). Army row sits right under the centre box; under it a dashed, muted "military in production" row:
  hud.py milQueue = per producing building (queue q > 0) the next q military units that spawned within SPAWN_R 22 of it in the
  next QUEUE_LOOK 180 s (hindsight; the dump has only the queue size). Age-up under construction: own box per landmark with
  name (costs.json), builders (villagers standing with no gather / move / garrison flag and not idle within BUILD_R 13 -
  the dump has no construct flag on villagers; game1: HRE 2, Rus 4) and progress. Dynasty (Chinese / Zhu Xi's Legacy): Tang,
  then Song / Yuan / Ming when the second landmark of age 1 / 2 / 3 finishes (civ guessed from the landmark bp: chinese / chi /
  zhu / zxl - unchecked). Templar commanderie flags and Ottoman vizier (picks + xp from a dump v8 resource named *vizier*):
  from U-event attribs matching commander / vizier / imperial_council - names guessed, no recording to check yet.
- Owner's logs 2026-11-11 (dump v10): otto1 (Templar vs Ottoman), zxl1 (Zhu Xi's Legacy chinese_ha_01 vs Scots), chn1 (Chinese
  vs Vikings, 105 MB). RT list = Action, Begin, Command, Food, Gold, Merc_Byz, Militia_HRE, Popcap, Stone, Wood: no vizier
  resource (vizier experience is not recorded); hud.py NOT_RES drops the non-resources from the bar. U events: Templar
  commanderie = upgrade_age_dark_com_1_tem (upgrades.json: Knights Hospitaller; executer the TC); Ottoman vizier picks =
  upgrade_imperial_*_ott executed by the player (p####); Chinese dynasty = upgrade player_dynasty1_chi (dynasty1 = Song,
  2 Yuan, 3 Ming; zxl1 reached none). Player executers (p1003 / p1006 / p1004 / p1007) were dropped by techs_bought - now
  mapped by techs_bought.player_ids() from kill events (victim e... + victimOwner p...). Dynasty now from these events
  (Tang from the start for chinese / zhu civs); vizier box = picks of 5 + names (no xp).
- Recap (owner 2026-11-11, Dota-style, minimizable - localStorage "fogline.recapMin"): latest fight that ended within
  RECAP_HOLD 90 s; army value before -> after (hud rows), swing = change of P1 minus change of P2, value lost (units),
  damage done; per side attacker types (icon, bar, damage) from dump v9 hits (hud.hit_recaps: inter-player hits in the
  fight's time +-2 s, victim within r + 40); hover = split over victim types; old logs fall back to the HP-drop estimate.
- Centre pies on hover (owner): villagers (food #fa8072 salmon, wood #8b5a2b, gold #ffc512 sunflower, stone #b2beb5 ash;
  idle, building / walking), army value by unit type with total in the middle; right-click on the army bar = army cost
  (food / wood / gold / stone from costs.json per unit). Same resource colours in the bar. hud rows add armyBy
  [[bp, n, value]] and armyCost [f, w, g, s]; H.names = display names (costs.json). Mongol double production: not in the dump.
- Owner 2026-11-11 (p19): landmark row in each player's bar block - landmark icons in placement order (faded while building,
  struck when destroyed); Knights Templar: their commanderie flags instead (techIcons = aoe4world flag icons, Hospitaller =
  black with a white cross), click = their main TC. Click = jump: 3D camera to it + yellow ring blinking 3 s; 2D map centred
  (zoom >= 3) + blinking ring. hud.py H.landmarks {p: [placed, done, gone, bp, id, x, z, name]}, H.mainTC {p: [id, x, z]}.
- Vizier point progress / landmark-spawned units (Jiangnan Tower, Ottoman military schools): not in the dump; the API has
  Player_ / Entity_GetStateModelFloat / Int / Bool (keys unknown). game_assets.py scar-search [words] greps the game's own
  scripts (unpacked Data) for the keys -> logs/scar_search.txt; dump v11 to read them once the keys are known.
- scar_search (owner 2026-11-11, 277 scripts, Data partly unpacked): rogue_misc.scar names the Ottoman vizier values -
  Player_GetStateModelFloat "imperial_council_exp_ott" (experience), Int "total_viziers_ott" (points so far); unspent points =
  RT_Command (already in dump v8's X list: otto1 Command 0 -> 1 at 6:22 / 10:28, spent at 6:25 / 11:13). AI script names
  "military_school_limit_ott". ui/vizierui.scar (the thresholds) and the Jiangnan Tower (= building_landmark_age1_prefecture_
  chi_ha_01) / military school spawn logic were not in the searched scripts.
- HUD vizier box: blacksmith icon (H.smith = the player's building_tech_unit_infantry_*) inside a progress ring = experience /
  H.vizThr (median experience just before a new point; none until a v11 recording) + points earned / 5, unspent (Command),
  picks. hud rows col 22 vizier [unspent, total, exp] (Ottoman players only).
- game_assets.py attrib-search [words] (default prefecture, military_school, jiangnan, imperial_council): decoded blueprint
  files named so, every value whose key looks like state / timer / spawn / threshold / limit -> logs/attrib_search.txt.
- attrib_search (owner 2026-11-11): the Jiangnan Tower (building_landmark_age1_prefecture_chi_ha_01) has an entity state model
  (schema jiangnan_tower_chi_ha_01) and spawns through spawner_ext production items: free "unit_free_dummy_*" squads
  (provincial guard 2 = 4 spearmen + 3 horsemen; city guard 2 = 4 repeater crossbows + 3 MAA; ranged specialist 3 = 4
  crossbows + grenadier; imperial retinue 4); military school = ordinary spawn items (spear / MAA / handcannon / archer per
  tier), Imperial Council dummy building has schema wonder_age1. game_assets attrib now also decodes statemodel_schema and
  attrib-search prints whole schema files (keys + defaults). dump v11 also probes production-queue items: A4D|PQ|id|bp|
  index 0/1 Entity_GetProductionQueueItem / ItemType (type and value), each blueprint twice, 24 in all - to find the
  production progress.
- otto2 (owner 2026-11-11, dump v11, Ottoman vs Zhu Xi): SM values arrive. Vizier experience grows ~2 per 20 s (+ jumps
  on spending, e.g. +15 at the age-up 4:21) and resets at each point: point 1 at 6:12 (57 -> 1), point 2 at 10:36 (92 -> 0);
  thresholds ~58 / ~94 (hud.vizThr per point = exp before + median step - exp after; later points use the last one).
  military_school_limit_ott 1 -> 2 at the age-up. Production-queue probe: Entity_GetProductionQueueItem = {PropertyBagGroupID,
  Type, ModPackID} (the item's blueprint id), ItemType userdata (1 unit / 0 upgrade) - no progress. Schema
  jiangnan_tower_chi_ha_01: int jiangnan_tower_unit_index, float UI_Progress (sub-schema, the building's progress bar; also
  in the shared building schema), vizier_exp_value (default 15).
- Owner 2026-11-11: resource hover = what that player's villagers on it work on (hud.py sources(): food farm / berry / deer /
  boar / sheep / fish / carcass, wood trees / stealth forest / straggler tree, gold / stone large / small deposit; nearest node
  of the kind within REACH_N 9 (gold / stone 15), farms FARM_N 7, live sheep from sheep_o; rows col 24). Garrisoned villagers
  (flag H; counted as idle - idle True in the data) shown as "N idle (G)" and as their own slice in the villager pie; stats
  "Idle time" = total villager idle seconds + (garrisoned part) (rows col 25 garrisoned, col 26 garrison-seconds, 2 s steps).
  otto2 P1 food "other" ~13 % (villagers between nodes / nodes newer than the 5 s snapshot).
## Arenas, live recap, abilities (owner 2026-11-11, "yes to all")
- analyzer/arena.py (log side, no recorder change): per fights.json fight in time order - start = earliest inter-player hit
  near the fight (victim within r + 30) walking back from its first death while hits are <= GAP_START 10 s apart (<= 30 s);
  snapshot "start" = army units (kind m) within max(r + 20, 30) at t0, or within +25 that fight in the first START_WIN 5 s;
  each second: side centres (value-weighted, active = alive, not fled unless returned), arena centre = their middle, radius
  max(25, half distance + 20); fled = beyond radius + 5, no damage dealt / taken FLEE_QUIET 5 s, moving away from the enemy
  centre (vs 3 s before), with HP share; returned = fled unit back inside and fighting; reinforcement = unit not in the
  snapshot fighting inside; end = END_QUIET 10 s without damage involving arena units (after the death cluster's end), or one
  side empty; fights starting inside a running arena merge. Track every 2 s. otto2: 13 fights -> 6 arenas (e.g. 615-699 s:
  P1 25 started, 11 fled / back, P2 1 started + 22 reinforcements). An arena whose army arrived after a raid starts with 0
  started (they all count as reinforcements).
- hud.py arena_recaps -> H.arenas: per arena LIVE_STEP 2 s steps [t, {side: [[attacker bp, [[victim bp, dmg]]]]}, {side: [lost
  value, units]}, {side: {ability: n}}] (damage between players involving arena units, positive only); rows col 27 army made
  /min (60 s). hud.js live recap (replaces the per-fight recap when H.arenas exists): from the arena start ("● live" while it
  runs) to 90 s after its end; span whole / last 60 s (auto: last 60 s once past 2 min; a button click pins one, again =
  auto); right-click = bars <-> pies (localStorage "fogline.recapChart"); rows army value start -> now + swing, destroyed
  (value, units), trade ratio, damage done, income /min, army made /min, unit counts (started / fled (back) / reinf. / died up
  to t), abilities used; damage by unit type with hover split by target. 3D (p20): "arena" toggle - white outline at the
  track, grey down-cone over fled units, green up-cone over reinforcements for 20 s (OHUD.arenaAt). 2D: recap only.
- Recap hits (owner 2026-11-11: damage favours bonus targets - archers do more to spears than MAA - so damage hides where the
  attacks went): hud.py arena steps' victim entries are [bp, damage, hits] (hits = damage events landed, deflected 0-damage hits
  included, add no damage; pierce / splash = one hit per unit struck). hud.js recap right-click cycles bars -> pies -> hits ->
  bars (localStorage "fogline.recapChart"); hits mode: bars of hits landed per attacker type, hover = hits per victim type.
  Older hud.json (no counts): hits mode skipped. otto2 example: Zhuge Nu 101 hits / 196 damage on sipahi; hardened spearman
  25 hits / 687.
- Upgrade rows (owner 2026-11-11): notches = the number of stages known for the family, not the highest stage number (eco
  harvest families are _2 / _3 / _4 = Feudal / Castle / Imperial, no dark-age stage: 3 notches, was 4); research in progress
  shown - hud.py tech_rows row = [done, attrib, name, row, stem, stage index, stages, start, detail]; start = done - research
  time of the upgrades.json entry for the player's civ (techs_bought.civ_code; civ speed bonuses not applied: an estimate;
  no time = not shown in progress); hud.js: faded icon + blue progress bar under it, notches = stages done; hover (title) =
  detail text (name, cost, research time, aoe4world effects, stage n of N, attrib) - for icons that are missing too.
  Blacksmith tiers (_i / _ii / _iii) are not grouped into families (separate icons, as before). otto2 at 6:10: Double
  Broadax 49 %, Wheelbarrow 50 %.
- Upgrade rows (owner 2026-11-11, screenshot Tughlaq vs Lancaster): civ-suffixed attribs (…_sul_ha_tug) now resolve to their
  upgrades.json entry (gamedata.canon_attrib: drop up to 3 trailing segments; techs_bought._entry, icons.py tech icons,
  hud.tech_rows) - they showed as "econ r" / "unit t" chips without icon or name. Blacksmith tiers grouped like in game:
  hud._family reads _N or _i / _ii / _iii (civ suffix after it ignored) -> one icon per line with 3 notches; stage sets per
  civ from the entries' civs (Japanese alone have melee damage iv), all-civ set as fallback. Unit veterancy upgrades
  (name "Upgrade to …", or upgrade_unit_* stage >= 2 except religious / town centre) left out (owner: unnecessary).
  Tughlaq governors (owner: "like the Knights Templar"): attribs matching /govern/ leave the rows and show as city tags
  (Ajmer / Bhakkar / Jalor / Multan / Sehwan / Uch from name / attrib) in the landmark row, notches when appointed again;
  aoe4world data has no governor icons or entries (data-main: only Tughlaqabad Fort Overwatch); attrib names unchecked.
- Recap (owner 2026-11-12): 4th right-click view "Damage per hit" = damage dealt / hits landed per attacker type (bars, 1
  decimal; hover = per victim type with hit counts); cycle bars -> pies -> hits -> per hit. Fixed with it: the "Damage done"
  row summed the shown list, so in the hits view it showed hit counts - now aggArena's raw damage total (G.tot) in every view.
- Recap title (owner 2026-11-12): "Fight m:ss–m:ss · m:ss long" (live: start–now) instead of the merged fight numbers (61+64+63...); the numbers on hover.
- Recap target filter (owner 2026-11-12): damage to units and damage to buildings apart - header buttons "units" / "bldgs"
  (localStorage "fogline.recapTgt"); the filter is on the victim (bp building_*), attackers of every kind stay (a TC / tower /
  keep shooting units counts under units); bars, pies, hits, per-hit and the "Damage to units / bldgs" row follow it. chn1
  24:11-26:00: P1 2.5k to units / 14.4k to buildings (one siege unit), P2 3.1k / 3.0k. Arena data across chn1: unit->unit
  129k, unit->building 68k, building->unit 13.5k.
- Recap title (owner 2026-11-12: "hard to tell what I am cycling through"): a title row at the top of the recap box - the current view in bold (Damage / Damage share / Hits landed / Damage per hit), 'to units|buildings · by attacking unit type · whole fight|last 60 s', and the four views as pills (current lit, click = that view; right-click still cycles; hits views hidden for old hud.json).
- upgrades without an icon (owner 2026-11-12: "some landmarks seem to give buffs ... that does not have an assigned icon, i
  think those buffs/upgrades should not have a turquoise background, but give it a more bluish background and give a better
  description ... list them and I can manually input their descriptions"): hud.js .fh-tic .ch (no icon) is blue
  (#3561a8 -> #1d3768) instead of the tech teal, label = notes "short" or the first two words of the name (14 chars, wraps).
  tools/tech_notes.py scans work/*.hud.json for upgrades without an icon, adds them to data/tech_notes.json (owner-written:
  name / short / desc / from; existing entries kept; not packaged so a new zip never overwrites it) and prints them with
  game, time, civ. hud.tech_rows applies the notes (name override, desc + "from:" on hover, row[9] = short); with no entry
  and no note the hover says "not in the game data ... describe it in data/tech_notes.json". Needs run.py again per game.
- Sacred sites in the HUD (owner 2026-11-12: "place the circles between the units and the villager / army value top middle
  box"): hud.py H.sites = holy / sacred sites from tl siteInfo + node positions, track [t, owner, [progress], [near]] (dump v19+
  SS, on change). hud.js: the centre box sits in a column (.fh-midcol) with one circle per site under it - grey = neutral,
  filled in the owner's colour = held, arc in the leading player's colour = capture / decapture progress (units unconfirmed:
  0..1, values > 1 read as percent), dashed white ring = contested (both players' capturing units near), tooltip, click = jump;
  "holds every sacred site" in the row's tooltip. 3D: the army row is placed under .fh-midcol (box + sites). 259818624 has no
  capture (checked with injected states in headless Chrome on both pages); the real progress values wait for a game with captures.
