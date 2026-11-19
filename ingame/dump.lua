-- AoE4 replay state dumper.
-- Load during replay playback (game started with -dev) from the in-game console:
--   dofile("C:/path/to/dump.lua")
-- Output goes to Documents/My Games/Age of Empires IV/warnings.log via print().
-- Stop with:  Scar_DoString("A4D_Stop()")
--
-- Line formats (fields separated by '|'):
--   A4D|CAPS|<name>=<0/1>|...                      once, which API calls work
--   A4D|P|t|pidx|name|civ|team|food|wood|gold|stone|wheelbarrow|foodUp|woodUp|goldUp|age|pop|popcap|X|res
--   A4D|E|t|pidx|<entity>;<entity>;...             chunked, max A4D_CHUNK per line
--     entity = id,bp,x,z,vismask,kind,idle,squadid,hp,flags,build,queue,target
--       squadid: the squad's ID (orders in the replay file refer to squads)
--       hp: current health; flags (squads): F/W/G/S gathering food/wood/gold/stone,
--         H in a building (garrisoned), C constructing, A attacking, M moving
--       build: construction progress 0..1 while under construction; queue: production queue size
--       target: entity id it is attacking now (units and buildings that shoot), else empty
--       vismask: bit (k-1) set if player index k (not owner) can see it
--       kind: w = worker, m = military, o = other
--       idle: 1/0 (only meaningful for squads)
--   A4D|N|t|full|<node>;<node>;...                resource nodes / wildlife (not player-owned)
--     node = id,bp,x,z,vismask,remaining ; once at the start (full=1), everything incl. trees
--   A4D|NC|t|<node>;...                            map objects that are new or changed (moved > 1,
--     visibility, remaining amount); A4D|NX|t|id;...  map objects gone
--   A4D|F|t|id,x,z,hp,target;...                  fight samples every A4D_FAST s while any unit attacks another
--     player's entity: attackers, targets and player entities within A4D_FIGHT_NEAR (x empty = gone)
--   A4D|NMODE|delta                                 nodes are written as start scan + changes
--   A4D|K|t|key=value;...                          an entity was killed (game event GE_EntityKilled);
--                                                   entity values as e<id>, squads s<id>, players p<id>
--   A4D|U|t|key=value;...                          an upgrade/technology finished (GE_UpgradeComplete)
--   A4D|H|t|attacker,victim,damage,hp;...          every hit (GE_DamageReceived; v9): entity ids (0 = none), damage,
--                                                   the victim's health after it; buffered per game time, chunked
--   A4D|PF|t|attacker,projectile,target,x,z;...    projectile fired (GE_ProjectileFired; v9): target entity id, or 0 and
--                                                   the ground position; A4D|PL|... the same when it lands
--                                                   (GE_ProjectileLanded). For splash / cleave and the fight simulator.
--   A4D|HERR|message                               a hit / projectile handler failed (first 20 only)
--   A4D|HMH|x0|z0|step|cols|rows                   terrain height grid header, once at start
--   A4D|HM|row|h,h,...                             heights along x at z = z0 + row * step
--   A4D|PCAPS / PCV / PG                           where land units can stand, once (see Pass)
--   A4D|S|bp|radius|collisionRadius                each blueprint once (buildings, resource nodes)
--   A4D|BH|id|hx|hz                                each building's heading once
--   A4D|RT|Name=id;...                             resource types (RT_* globals), once
--   P line (v8) ends with |X|Name:bank:rate;...    every resource type: bank and the game's income rate
--   A4D|SS|t|id,owner,prog,near,secure,traders;...  strategic points (sacred sites, trade posts; v19), on change: owner =
--                                                  player index holding it (0 none), prog = each player's capture progress
--                                                  (p1:p2...), near = each player has a capturing squad near it (1/0 per
--                                                  player), secure count, trader count; A4D|SSI|id|bp|sp|vp once per point
--   A4D|ED|t|player|rec;...                       v20 entity delta: between keyframes (full E lines every A4D_E_KEY s, and an
--                                                  entity's first record) only records that changed since the second before;
--                                                  the bp field is empty when the blueprint did not change
--   A4D|EX|t|player|id,id,...                      v20: entities of that player gone since the second before
--   A4D|ABR|t|event,caster,ability,target,n,first,last;...   v20: an ability event repeating within A4D_AB_REPEAT s of the
--                                                  same one (passive aura pulses: field_stone_buff_info_byz ~4 / s per
--                                                  building) is counted, not written; a run is written when it ends and every
--                                                  60 s while it lasts (n = events folded in since the AB / last ABR line)
--   A4D|AA|t|id,ability+ability / -;...           v21 active abilities per entity (toggles / timed / self-cast that are on or
--                                                  in progress: Entity_IsAbilityActive / Squad_IsDoingAbility), on change;
--                                                  A4D|AAK|bp|names once per blueprint (the abilities it has, Entity_HasAbility)
--   A4D|G|t|id,squad:squad / -;...                 v21 garrison: the squads (game ids) a building / vehicle holds, on change
--   A4D|Q|t|id,size,type,bp,bp1+bp2+...            v21: the Q record carries the whole queue (5th field)
--   A4D|VTK|path|type|value, A4D|VT|t|path=value;...   v21 win-condition script values (sacred / wonder / victory timers):
--                                                  the script tables scanned at the start and at 60 s, numbers / bools on change
--   A4D|QS|t|squad|k=v;...                         v21 squad state models (the unit key list through Squad_GetStateModel*)
--   E records (v21) end with a 14th field: heading in degrees (5 deg steps; units / buildings that report one)
--   A4D|V|21                                       dump format version (21: AA / G / full queue / VT / QS / heading;
--                                                  20: ED / EX entity deltas, ABR repeat runs - v19 on
--                                                  259818624: E 12.2 MB, 77 % of records unchanged; AB 32 MB of aura pulses;
--                                                  19: context / ability handlers registered as
--                                                  named globals (v18's closures were refused: Rule_AddGlobalEvent), SS /
--                                                  SSI strategic points, no state models on wpn_* weapon entities,
--                                                  silence via Sound_SetForceSilence; 18: events UQ UX C CS CW CX SP I BI, H + shield /
--                                                  repair, Q queue head, D destinations, B costs; ES / PS / SMK state models of every
--                                                  building, unit and player, changed keys only, see A4D_EntitySM;
--                                                  17: light view + PERF; 14: the fishing boat probe on every tile - walkable
--                                                  + boat = shallows; 13: PG cells carry a 4th field, the fishing
--                                                  boat's spawn distance on blocked tiles = water); (10: trees' remaining wood; 11: P line ends
--                                                  with SM|key:value;... player state-model values, A4D_SM; 12: ability
--                                                  events A4D|AB / A4D|ABK, the GE_* list A4D|GE)
--   A4D|NERR|message                               a node snapshot failed (retried; off after 10 in a row)
--   A4D|SPEED|old|new                              after A4D_Speed(n)
-- tools/record.py runs a copy with A4D_AUTO_SPEED / A4D_AUTO_END set: no console input after loading
--   A4D|NCAPS|<method>                             which neutral-entity lookup worked (or none)
--   A4D|APICOUNT|n, A4D|API|name,name,...           all global functions, once at start
--   A4D|IO|<type(io)>                              whether scripts can write files
-- Missing values (call unavailable) are written as empty fields.

local A4D_SRC = [==[

A4D_CHUNK = 60
-- warnings.log cuts lines at about 4,067 bytes: lines are also split by size, kept under this
A4D_LINE_MAX = 3400
-- set by tools/record.py in its temporary copy: sim rate after loading, game time to stop at
A4D_AUTO_SPEED = nil
A4D_AUTO_END = nil
A4D_LIGHT_VIEW = A4D_LIGHT_VIEW      -- record.py sets it true: cheaper frames while recording (see A4D_LightView)
A4D_TICK = 0
A4D_STOPPED = false
A4D_TREE_SLICES = A4D_TREE_SLICES or 30
A4D_FAST = A4D_FAST or 0.25          -- fight sampling interval, s
A4D_FIGHT_NEAR = A4D_FIGHT_NEAR or 30 -- units this close to an attacker are sampled too
A4D_DISCOVER = A4D_DISCOVER or 10
A4D_NODES_STARTED = false

local function try(f, ...)
    if type(f) ~= "function" then return nil end
    local ok, v = pcall(f, ...)
    if ok then return v end
    return nil
end

local function s(v)
    if v == nil then return "" end
    return tostring(v)
end

local function int(v)
    if v == nil or v ~= v then return "" end
    return string.format("%.0f", v)
end

local function num(v)
    if v == nil then return "" end
    return string.format("%.1f", v)
end

local function HasUp(player, id)
    local bp = try(BP_GetUpgradeBlueprintByPbgID, id)
    if bp == nil then return false end
    return try(Player_HasUpgrade, player, bp) == true
end

local function Level(player, ids)
    -- ids: list of {pbgid, level}, highest levels first
    for i = 1, #ids do
        if HasUp(player, ids[i][1]) then return ids[i][2] end
    end
    return 0
end

-- Upgrade pbgids taken from kuschAoe/AoE4_ReplayOverlay (OverlayDataCollector.lua)
local UP_WHEEL = {{129091,1},{181988,1},{169038,1},{205916,1}}
local UP_FOOD  = {{175042,3},{171293,3},{181876,3},{171296,2},{171292,2},{181875,2},
                  {171295,1},{128049,1},{181874,1}}
local UP_WOOD  = {{175068,3},{171837,3},{181940,3},{171838,2},{171836,2},{181939,2},
                  {169035,1},{128070,1},{181938,1}}
local UP_GOLD  = {{171824,3},{181905,3},{175058,3},{188052,3},{171823,2},{181904,2},
                  {171826,2},{2032215,2},{171822,1},{181877,1},{171825,1},{2032216,1}}

-- every resource type the game defines (RT_* globals: food, wood, gold, stone, and civ ones such as olive
-- oil or silver), found once; each second the P line ends with X|Name:bank:rate;... (rate = the game's
-- Player_GetResourceRate, units as the game reports them)
local A4D_RT = nil
local function ResTypes()
    if A4D_RT then return A4D_RT end
    A4D_RT = {}
    for k, v in pairs(_G) do
        if type(k) == "string" and string.sub(k, 1, 3) == "RT_" and type(v) == "number" then
            table.insert(A4D_RT, {string.sub(k, 4), v})
        end
    end
    table.sort(A4D_RT, function(a, b) return a[2] < b[2] end)
    local names = {}
    for i = 1, #A4D_RT do names[i] = A4D_RT[i][1] .. "=" .. A4D_RT[i][2] end
    print("A4D|RT|" .. table.concat(names, ";"))
    return A4D_RT
end
local function AllRes(player)
    local out = {}
    for _, r in ipairs(ResTypes()) do
        local b = try(Player_GetResource, player, r[2])
        local rate = try(Player_GetResourceRate, player, r[2])
        if b ~= nil or rate ~= nil then
            table.insert(out, r[1] .. ":" .. num(b) .. ":" .. (rate ~= nil and string.format("%.3f", rate) or ""))
        end
    end
    return table.concat(out, ";")
end

-- player state-model values (dump v11, owner 2026-11-11; keys from the game's own scripts, game_assets.py scar-search):
-- Ottoman vizier experience and points so far (rogue_misc.scar: imperial_council_exp_ott / total_viziers_ott; unspent
-- points = the RT_Command resource), military school limit (cardinal_scoring_functions.scar). Read for every player; a
-- key the player does not have reads nil / errors and is left out.
A4D_SM = A4D_SM or { {"f", "imperial_council_exp_ott"}, {"i", "total_viziers_ott"}, {"i", "military_school_limit_ott"} }
local function StateModel(player)
    local out = {}
    for _, kv in ipairs(A4D_SM) do
        local fn = kv[1] == "f" and Player_GetStateModelFloat or kv[1] == "i" and Player_GetStateModelInt or Player_GetStateModelBool
        local v = fn and try(fn, player, kv[2])
        if v ~= nil and type(v) ~= "table" then table.insert(out, kv[2] .. ":" .. tostring(v)) end
    end
    return table.concat(out, ";")
end

-- production-queue probe (dump v11, owner 2026-11-11: progress of the item in production - Jiangnan Tower / military school
-- spawns are production items): the first A4D_PQ_LEFT times a queue is busy, what Entity_GetProductionQueueItem /
-- ItemType return for index 0 and 1 (type and value; tables listed key=value) -> A4D|PQ|...
A4D_PQ_LEFT = 24
local function show(v)
    if type(v) ~= "table" then return type(v) .. ":" .. tostring(v) end
    local o = {}
    for k2, v2 in pairs(v) do table.insert(o, tostring(k2) .. "=" .. tostring(v2)) if #o >= 12 then break end end
    return "table{" .. table.concat(o, ",") .. "}"
end
-- state-model values of every building, unit and player (dump v18, owner 2026-11-12: "records every bit of useful
-- information" - building buffs such as Jeanne's consecration, Yorishiro, prelate inspiration, charges, auras ...).
-- Keys come from the game's state-model schemas (attrib_search.txt, 538 files), filtered of per-tick internals; the first
-- letter is the getter (b / i / f). For each blueprint the keys are probed on its first entity: a key that errors is
-- dropped for that blueprint; a key that ends in a civ tag the blueprint does not carry is skipped. Then each entity is
-- read every A4D_SM_EVERY seconds (buildings) / A4D_SM_EVERY_U (units), sliced by id, and only changed keys are written:
--   A4D|ES|t|id|key=value;...     (value 1/0 for bools; the first line of an entity holds its non-default values only;
--                                  "vet" = squad veterancy rank)
--   A4D|PS|t|player|key=value;... (player keys, changed only)
--   A4D|SMK|bp|n                  (how many keys survived the probe for a blueprint)
A4D_SMK_B = A4D_SMK_B or {
    "bUninterruptibleAttack", "bactive_daimyo_estate_retainer", "ballow_evacuation", "bberry_bush_upgraded_sul", 
    "bberry_bush_upgraded_wing_abb", "bboar_killed_sul", "bboost_active_vik", 
    "bbrewery_influence_bonus_jpn_ha_sen", "bbuild_previous_dynasty_units", "bbuilding_has_ovoo_aura_mon", 
    "bbuilding_is_packing_mon", "bchart_a_course_apply_upgrades", "bcistern_influence_bonus_active_byz", 
    "bconsecrated_by_jeanne", "bconstruct_beeskeps_vik", "bconstruct_farmstead_vik", "bconstruct_loom_vik", 
    "bconstruct_smithy_vik", "bconvert_to_archery_range", "bconvert_to_barracks", "bconvert_to_blacksmith", 
    "bconvert_to_dock", "bconvert_to_prayer_tent", "bconvert_to_siege_workshop", "bconvert_to_stable", 
    "bdaimyo_estate_constructed", "bdaimyo_influence_bonus", "bdefensive_tower_alert_eng", "bdisable_retaliate", 
    "bdistrict_improved_tax_rate_chi", "bdistrict_jiangnan_chi_ha_01", "bdistrict_spec_market_gen_gold_fre", 
    "bdropped_bounty", "bedict_influence_mon_ha_gol", "belzbach_influence_bonus_enabled_hre", 
    "bentity_state_gather_gold", "bentity_state_gather_stone", "bfish_pond_aura_active_sco", 
    "bfre_is_influenced", "bgaia_hunters_bounty_rus", "bgate_auto_mode_enabled", "bgate_locked", 
    "bgold_deposit_is_claimed", "bgrassland_selected_mounted_vil_jin", "bgreat_wall_scuttle_block_chi", 
    "bhas_khan_arrow_buff_attack_mon", "bhas_khan_arrow_buff_defense_mon", "bhas_khan_arrow_buff_speed_mon", 
    "bherded_by_scout", "bimproved_resource_deposit_abb", "binfluence_mosque_active_sul", "bis_being_carried", 
    "bis_bleeding", "bis_bleeding_secondary", "bis_bleeding_tertiary", "bis_blinded_jpn_ha_sen", "bis_carried", 
    "bis_charging", "bis_in_golden_age_influence", "bis_in_influence_hre", "bis_mengan_mouke_active", 
    "bis_packed_mon", "bis_supervised_chi", "bis_trade_tributary", "bis_tributary_farm_worked", 
    "bkingbuff_paling_eng", "blandmark_active", "blandmark_food_dropoff_imp_byz", "block_out", 
    "bmadrasa_current_acitve_income_sul", "bmatsuri_restart_sake_bonus_jpn_ha_sen", 
    "bmatsuri_sake_bonus_jpn_ha_sen", "bmatsuri_update_rate", "bmengan_mouke_list_ready", 
    "bmoving_building_destroyed", "bnetwork_of_castles_buff", "bnon_aggressive", "bovoo_active", 
    "bovoo_has_relic", "bovoo_is_claimed", "bpasture_first_sheep_spawn_mon", "bpit_mine_is_large_deposit", 
    "bpit_mine_is_tiny", "bproduction_enabled", "bproxy_active_sul", "bproxy_successful_sul", "breserved", 
    "bresource_instant_velocity_enabled", "bruinous_blinding_byz_ha_mac", "bryokan_healing_buff_jpn_ha_sen", 
    "bryokan_matsuri_bonus", "bsacred_object_buff_jpn", "bscholar_production_active_sul", 
    "bscholar_research_active_sul", "bsettlement_repaired", "bsiege_is_setup", "bstable_influence_jin", 
    "bstone_of_destiny_aura_active_sco", "bstorehouse_field_construction_failed_jpn", "btown_center_is_capital", 
    "bunits_in_queue", "bvarangian_warcamp_spawning", "bwinds_of_change_apply_upgrades", "bwithin_ortoo_aura", 
    "byatai_restart_aura", "fGaia_Wander_Distance_To_Wander_Max", "fGaia_Wander_Distance_To_Wander_Min", 
    "fMax_Followers", "fProdResource", "fRelic_Capacity", "fRelic_Count", "fTithed_Followers", 
    "fTotal_Followers", "fUI_Progress", "fUI_longhouse_decorator_progress", "fadditional_carry_gold_amount", 
    "fajmer_amir_warrior_replenish_time", "fbee_skeps_multiplier", "fbhakkar_food_generated", 
    "fbleed_duration_timer", "fbuilding_district_monastery_count_mon", "fcity_planning_health_modifier_abb", 
    "fcity_planning_workrate_modifier_abb", "fcost_reduction", "ffollower_income_multiplier", 
    "ffood_resource_total_per_minute", "fgaia_wander_delay_probability", "fgaia_wander_leash_distance", 
    "fgold_resource_total_per_minute", "fgolden_gate_caravan_count", "fguild_hall_resource_bank_fre", 
    "fgunsmith_stockpile_count_jpn", "fgunsmith_stockpile_timer_jpn", "fhre_brawl_gold_income_per_round", 
    "fhunting_cabin_base_generation_rus", "fhunting_cabin_generation_rate_rus", 
    "fhunting_cabin_nearby_gaia_population", "fhunting_cabin_rate_display_rus", "fhunting_cabin_update_rate_rus", 
    "finspire_range_hre", "fjeanne_cost_override", "fkhan_raid_timer_mon", 
    "fleader_respawn_progress_baibars_ayy", "fleader_respawn_progress_baldwin_tem", 
    "fleader_respawn_progress_general_song", "fleader_respawn_progress_han_shizhong_song", 
    "fleader_respawn_progress_henry_v_lan", "fleader_respawn_progress_naval_han_shizhong_song", 
    "fleader_respawn_progress_odo_tem", "fleader_respawn_progress_qutuz_ayy", 
    "fleader_respawn_progress_saladin_ayy", "fleader_respawn_progress_shajar_ayy", 
    "fleader_respawn_progress_shirkuh_ayy", "fleader_respawn_progress_tughtekin_ayy", 
    "fleader_respawn_progress_yue_fei_song", "flonghouse_boost_timer_vik", "fmatsuri_gather_rate", 
    "fmax_flee_time", "fmilitary_building_healing_aura_count_mon", "fmining_camp_silver_amount_mac", 
    "fnumber_horses_in_grasslands", "fopen_pit_mine_rate_modifier_mal", "fpasture_sheep_timer_mon", 
    "fproduction_speed", "frelic_gold_generation_multiplier", "frelic_total_generation_rate", 
    "fresource_depleted_delay_before_delete", "fsacred_site_gold_generation_rate", 
    "fsacred_site_total_generation_rate", "fstone_gold_piece_depleted", "fstone_resource_total_per_minute", 
    "ftax_cooldown_time_remaining_chi", "ftown_center_militarize_villagers", "funiversal_buff_count", 
    "funiversal_heal_count", "fvarangian_warcamp_spawning_timer", "fvineyard_wine_amount_byz", 
    "fvineyard_wine_rate_byz", "fvizier_exp_multiplier", "fvizier_exp_value", "fwood_resource_total_per_minute", 
    "fyatai_current_generation_rate", "fyatai_resources_collected", "fyatai_temp_rate", 
    "iability_last_issued_tick", "iavailable_horses_jin", "ibhakkar_building_count", "icampfire_count_eng", 
    "icapture_point_reward_interval", "icattle_in_ranch_mal", "icc_reward_tier2_time", "icc_reward_tier3_time", 
    "ichart_a_course_buffs_reapply", "icistern_charges", "icistern_influence_bonus_counter_armor_byz", 
    "icistern_influence_bonus_counter_production_byz", "icistern_influence_bonus_counter_research_byz", 
    "icistern_influence_bonus_level_armor_byz", "icistern_influence_bonus_level_production_byz", 
    "icistern_influence_bonus_level_research_byz", "icistern_influence_mode_byz", "icistern_network_level_byz", 
    "icistern_paid_cost_byz", "icistern_time_of_akritoi_complete", "idaimyo_estate_cost_paid", "idaimyo_level_2", 
    "idaimyo_level_3", "idistrict_spec_gold_rate_mod_pagoda_chi", "idistrict_spec_total_stables_fre", 
    "idouse_under_attack_hre", "ievacuation_state", "ifishing_boat_count_jpn", "iflame_douse_cooldown_hre", 
    "ifollower_count", "igaia_wander_delay_max", "igaia_wander_delay_min", "igather_slots_occupied", 
    "igunsmith_stockpile_timer_jpn", "ihunting_cabin_claimed_tree_count", "ihunting_cabin_range", 
    "iinfluence_counter", "ijiangnan_tower_unit_index", "ikongens_longhouse_count", "ilegacy_level", 
    "ilocal_governor_selected_tug", "imanor_villager_count", "imatsuri_yatai_count", 
    "imeditation_garden_counter", "imengan_mouke_local_count", "imengan_mouke_total_count_jin", "imerc_set_byz", 
    "imustering_hall_level_1_cost_sco", "imustering_hall_level_2_cost_sco", "imustering_hall_level_3_cost_sco", 
    "inum_garrisoned_monks", "iowned_scholars_garrisoned", "ipilgrimages", "ipopulation_cap_increase", 
    "iproduction_index", "irelic_capacity", "irelic_count", "ischolars_working_sul", 
    "isiegecamp_barrage_charges", "ispawn_count", "itime_of_festival_complete_mal", "itime_of_last_charge", 
    "itime_of_next_available_charge", "itrade_counter_abb_ha", "itrade_wing_food_charges_abb_ha", 
    "itrade_wing_javelin_charges_abb_ha", "itrade_wing_stone_charges_abb_ha", 
    "itrade_wing_swordman_charges_abb_ha", "itrade_wing_trader_charges_abb_ha", 
    "itrade_wing_villager_charges_abb_ha", "itrade_wing_wood_charges_abb_ha", "itributary_deposit_current_count", 
    "iunit_count", "iunit_recruited_count", "ivarangian_warcamp_unit_index", "ivillager_cap_increase_vik", 
    "iwolves_cap", "iwolves_current", "iyatai_berry_count", "iyatai_boar_corpse_count", "iyatai_boar_count", 
    "iyatai_deer_corpse_count", "iyatai_deer_count", "iyatai_farm_count", "iyatai_fish_count", 
    "iyatai_sheep_count"}
A4D_SMK_U = A4D_SMK_U or {
    "bUninterruptibleAttack", "bactive_in_hold", "ballow_evacuation", "barcher_is_deploying_palings", 
    "barcher_palings_deployed", "battached_animator_shield", "bberry_bush_upgraded_sul", "bboar_killed_sul", 
    "bcampfire_active_eng", "bcannon_barrage_active_fre", "bchart_a_course_apply_upgrades", "bconversion_entity", 
    "bcrossbow_second_bolt", "bcrossbow_stationary_bonus_fre", "bdebuff_cast_jpn", "bdefensive_tower_alert_eng", 
    "bdisable_retaliate", "bdistrict_spec_lancer_melee_boost_fre", "bdropping_relic", "bforce_march_active_sul", 
    "bgold_deposit_is_claimed", "bgrassland_under_construction_jin", "bhas_khan_arrow_buff_attack_mon", 
    "bhas_khan_arrow_buff_defense_mon", "bhas_khan_arrow_buff_speed_mon", "bhero_inactive", "bhit_palings_eng", 
    "bimproved_resource_deposit_abb", "bincendiary_equipped", "bis_being_carried", "bis_bleeding", 
    "bis_bleeding_secondary", "bis_bleeding_tertiary", "bis_blinded_jpn_ha_sen", "bis_bracing", "bis_burning", 
    "bis_camel_support_active_abb", "bis_carrying_entity", "bis_charging", "bis_debuffed_jpn", 
    "bis_in_golden_age_influence", "bis_in_greek_fire", "bis_in_stealth_aura_mal", "bis_inspired_hre", 
    "bis_military_school", "bis_toggled_stealth", "bis_tower_of_victory_active", "bis_unit_following", 
    "bkaburya_arrow_active_jpn", "bkhan_signal_ability_available", "blodya_apply_upgrades_rus", 
    "blodya_converting", "blongship_full_vik", "bmamluk_bow_equipped", "bmatsuri_aura_linger_jpn_ha_sen", 
    "bnaval_broadside_left_bool", "bnaval_broadside_right_bool", "bnaval_committed_fire", 
    "bnest_of_bees_fire_active_chi", "bnetwork_of_castles_buff", "bnon_aggressive", 
    "bofficial_auto_collect_tax_enabled", "bovoo_is_claimed", "bpavise_deployed", "brapid_fire_on_cooldown_chi", 
    "brelentless_attack_active", "bresearch_exit", "bruinous_blinding_byz_ha_mac", 
    "bryokan_healing_buff_jpn_ha_sen", "bsaints_armour_buff_rus", "bsaints_damage_buff_rus", "bsiege_is_setup", 
    "bsiege_tower_ramp_open", "bsnaring_shot_active_ayy", "bstealth_ended_local_knowledge", 
    "bstone_of_destiny_aura_active_sco", "bstreltsy_double_time_active_rus", "bvillager_health_jpn_ha_sen", 
    "bwinds_of_change_apply_upgrades", "bwise_elephant", "bwithin_fishpond_aura_sco", 
    "bwithin_gulyay_gorod_radius", "bwithin_ortoo_aura", "fBraceCooldown", "fRelic_Capacity", "fRelic_Count", 
    "fTithed_Followers", "fUI_Progress", "fbounty_count_mon", "fcity_planning_health_modifier_abb", 
    "fcity_planning_workrate_modifier_abb", "fcrossbowmen_attack_count_fre", "fdock_upgrade_aura", 
    "fkhan_raid_timer_mon", "fmanatarms_attack_count_chi", "fmelee_attack_count_hre", "franged_armor_resistance", 
    "frapid_fire_count_chi", "fresource_depleted_delay_before_delete", "fshouldheal", 
    "fstone_gold_piece_depleted", "fstreltsy_static_deployment_counter_rus", "ftax_amount_to_deduct_chi", 
    "funiversal_buff_count", "funiversal_heal_count", "fvizier_exp_value", "iUI_Duration", 
    "iactive_ott_aura_type", "iamir_stacks", "iamir_timer", "iberserker_rage_timer_vik", 
    "ichart_a_course_buffs_reapply", "icistern_gather_aura_overlaps", "icistern_highest_tier_within_byz", 
    "icurrent_charge_duration", "ihealing_count", "ihighland_cattle_count_sco", 
    "iholy_inspiration_time_remaining_hre", "ikhan_combat_level", "ikhan_combat_power", "inumber_daimyo_carried", 
    "inumber_of_kings_carried", "ipilgrimages", "ipopulation_cap_increase", "isaints_armour_buff_count_rus", 
    "isaints_blade_buff_count_rus", "ishinobi_attack_count_jpn_ha_sen", "ithrown_weapon_cooldown", 
    "itime_of_last_charge", "itime_of_next_available_brace", "itime_of_next_available_charge", 
    "itime_of_next_available_javelin", "itime_of_next_tax_mal", "itotal_sheep_count_mon"}
A4D_SMK_P = A4D_SMK_P or {"fimperial_council_exp_ott", 
    "bcan_capture_override", "bdisable_landmark_rebuild", "bdock_blocked", "bhas_stealthed_spies", 
    "bhorseman_champion_spawning_byz_ha_mac", "bimperial_age_wonder_constructed", 
    "bis_wonder_construction_enabled", "bplayer_can_construct_structures", 
    "briddari_champion_spawning_byz_ha_mac", "bscout_champion_spawning_byz_ha_mac", "bwonder_in_progress", 
    "fcarrying_relics", "fdock_repair_rate", "feconomy_score", "fhas_capital", "fidle_economy_pop", 
    "fjeanne_d_arc_consecration_production_cost_modifier", "fmilitary_score", "fmonk_heal_rate", 
    "fmonk_out_of_combat_heal_time", "fmonk_overheal_max", "fmonk_relic_ability_range", 
    "fmonk_relic_ability_warmup", "frelic_gold_generation_multiplier", "frelic_gold_generation_rate", 
    "frelic_gold_income_per_second", "frelic_threshold", "fsacred_site_gold_generation_multiplier", 
    "fsacred_site_gold_generation_rate", "fsacred_site_gold_income_per_second", "fsecured_relics", 
    "fsiege_repair_multiplier", "fsociety_score", "ftechnologies_researched", "ftechnology_score", 
    "ftotal_score", "fwonder_timer", "iactive_armor_timer_vik", "iactive_cistern_count_byz", 
    "iactive_damage_timer_vik", "iactive_ovoo_count", "iactive_pit_mine_count", "iactive_town_bell_unit_count", 
    "ialgebra_mil_tech_count_abb", "iamir_units_alive_sul_ha_tug", "iarmor_upgrade_vik", 
    "iarsenal_building_survivability_count_mac", "iarsenal_cavalry_damage_count_mac", 
    "iarsenal_cavalry_survivability_count_mac", "iarsenal_infantry_damage_count_mac", 
    "iarsenal_infantry_survivability_count_mac", "iarsenal_ranged_damage_count_mac", 
    "iarsenal_ranged_survivability_count_mac", "iarsenal_siege_survivability_count_mac", 
    "ibatch_production_count", "ibee_skep_max_vik", "ibee_skeps_count_vik", 
    "iblock_max_count_infantry_samurai_jpn", "ibondi_count_vik", "ibuilding_count", "ibuildings_researching_sul", 
    "icall_shield_maiden_count_vik", "icapture_point_control_timer", "icapture_point_reward_iteration", 
    "icapture_point_reward_points", "icaravan_count_jpn", "icattle_max_sco", "ichart_a_course_active_buffs", 
    "iclan_hojo_level_jpn_ha_sen", "iclan_oda_level_jpn_ha_sen", "iclan_takeda_level_jpn_ha_sen", 
    "iconstructed_town_bell_destinations", "icreated_stealth_forests_sco", "icurrent_counter", 
    "idamage_upgrade_vik", "idemilancer_spawn_lan", "ieco_techs_fre", "iemissary_cap_jin", "iemissary_count_jin", 
    "ifairy_flag_cooldown_sco", "ifairy_flag_timer_sco", "ifarmstead_count_vik", "ifarmstead_max_vik", 
    "ifish_pond_count_sco", "ifish_pond_max_sco", "iflame_douse_cooldown_base_hre", 
    "iflask_charges_available_byz", "igovernor_jalor_level_sul_ha_tug", "igrand_galley_mil_school_count_ott", 
    "igrassland_max_horses_jin", "igreat_pasture_max_horses_jin", "ihighland_cattle_count_sco", 
    "ihouse_unified_damage_max", "ijanissary_company_ott", "ijanissary_increase_ott", 
    "ijanissary_spawn_count_ott", "ijeanne_d_arc_current_consecrate_charges", 
    "ijeanne_d_arc_current_wrath_charges", "ijeanne_d_arc_max_consecrate_charges", 
    "ijeanne_d_arc_max_wrath_charges", "ikhan_edict_mon_ha_gol", "ilevy_mixed_spawn_lan", "ilist_count", 
    "ilonghouse_count_vik", "iloom_count_vik", "iloom_max_vik", "imanor_count_lan", "imanor_count_lan_2", 
    "imanor_count_lan_3", "imanorbuildlimit", "imanuscript_count_sco", "imax_horse_count_jin", 
    "imengan_mouke_active_count_jin", "imengan_mouke_keep_squad", "imengan_mouke_outpost_squad", 
    "imengan_mouke_player_cap", "imengan_mouke_total_count_jin", "imengan_mouke_tributary_squad", 
    "imerc_set_01_unlocked_byz", "imerc_set_02_unlocked_byz", "imerc_set_03_unlocked_byz", 
    "imerc_set_04_unlocked_byz", "imerc_set_05_unlocked_byz", "imilitary_school_count", 
    "imilitary_school_limit_ott", "imounted_villager_bonus_torch_damage", "imounted_villager_build_limit_jin", 
    "imounted_villager_current_count_jin", "imuster_charges", "imuster_hall_archer_count_sco", 
    "imuster_hall_cateran_count_sco", "imuster_hall_gallowglass_count_sco", "imuster_hall_mangonel_count_sco", 
    "imuster_hall_pikeman_count_sco", "imuster_hall_reivers_count_sco", "imuster_hall_tacksman_count_sco", 
    "imustering_hall_level_sco", "inew_counter", "inum_downed_leaders", "inum_food_gatherers", 
    "inum_gold_gatherers", "inum_idle_fishponds", "inum_idle_highland_cattle", "inum_idle_villagers", 
    "inum_stone_gatherers", "inum_wood_gatherers", "iovoo_limit_mon_ha_gol", "ipax_ottomana_complete_ott", 
    "ipilgrim_temporary_count_tem", "ipit_mine_count", "ipit_mine_limit_mal", "iplayer_max_age", 
    "iplayer_relic_count", "iprimary_active_saga", "isacred_grove_count_vik", "isacred_grove_limit_vik", 
    "isacred_sites_captured", "ischolar_availability_level_sul", "ischolar_count_sul", "isecondary_active_saga", 
    "ishield_maiden_count_vik", "isilk_road_requirement_tier_1_mon", "isilk_road_requirement_tier_2_mon", 
    "isilk_road_requirement_tier_3_mon", "isilk_road_requirement_tier_4_mon", "ismithy_count_vik", 
    "ismithy_max_vik", "ithree_loch_archer_count_sco", "ithree_loch_carrack_count_sco", 
    "ithree_loch_cateran_count_sco", "ithree_loch_combat_ship_count_sco", "ithree_loch_gallowglass_count_sco", 
    "ithree_loch_mangonel_count_sco", "ithree_loch_naval_count_sco", "ithree_loch_pikeman_count_sco", 
    "ithree_loch_reivers_count_sco", "ithree_loch_tacksman_count_sco", "ithree_loch_war_galley_count_sco", 
    "itime_of_festival_complete_mal", "itotal_district_tiers", "itotal_horse_count_jin", "itotal_keep_count", 
    "itotal_manor_count_lan", "itotal_mengan_mouke_emplacement_count_jin", "itotal_scholar_count_sul", 
    "itotal_viziers_ott", "itrade_outpost_max_tax_count_mal", "iupgrades_completed", "ivenetian_trader_tem", 
    "ivizier_limit_ott", "iwandering_storm_strikes", "iyeomen_spawn_lan"}
A4D_SM_EVERY = A4D_SM_EVERY or 2
A4D_SM_EVERY_U = A4D_SM_EVERY_U or 4
A4D_SM_UNITS = (A4D_SM_UNITS ~= false)
A4D_SM_CIV = {mon = 1, byz = 1, sul = 1, rus = 1, chi = 1, fre = 1, jpn = 1, abb = 1, hre = 1, eng = 1, mal = 1, ott = 1}
A4D_SM_BPKEYS = {}      -- bp -> {{getter, key}, ...} after the probe
A4D_SQ_BPKEYS = {}      -- v21: squad keys per blueprint
A4D_QSM_LAST = {}       -- v21: squad id -> {key = value string}
A4D_QS_DONE = {}        -- v21: squads read this tick
A4D_SM_SQUADS = A4D_SM_SQUADS ~= false
A4D_ESM_LAST = {}       -- id -> {key = value string}
A4D_PSM_LAST = {}       -- player index -> {key = value string}
A4D_PSM_KEYS = nil
local SMF = {}
local function SMGet(kind, c)               -- kind "E" / "P" / "S" (v21 squads), c = "b" / "i" / "f"
    local nm = (kind == "E" and "Entity" or kind == "S" and "Squad" or "Player") .. "_GetStateModel" .. (c == "b" and "Bool" or c == "i" and "Int" or "Float")
    return _G[nm]
end
local function SMStr(v)
    if type(v) == "boolean" then return v and "1" or "0" end
    if type(v) == "number" then
        if v == math.floor(v) and math.abs(v) < 1e9 then return string.format("%d", v) end
        return (string.gsub(string.format("%.3f", v), "%.?0+$", ""))
    end
    return nil
end
local function SMDefault(s) return s == "0" or s == "-0" end
local function Tokens(b)
    local t = {}
    for w in string.gmatch(string.lower(b), "[^_]+") do t[w] = true end
    return t
end
local function ProbeKeys(kind, obj, list, toks)
    local keep = {}
    for _, k in ipairs(list) do
        local c, key = string.sub(k, 1, 1), string.sub(k, 2)
        local last = string.match(key, "_([%a]+)$")
        if not (toks and last and A4D_SM_CIV[string.lower(last)] and not toks[string.lower(last)]) then
            local fn = SMGet(kind, c)
            if fn then
                local ok, v = pcall(fn, obj, key)
                if ok and v ~= nil and SMStr(v) ~= nil then table.insert(keep, {fn, key}) end
            end
        end
    end
    return keep
end
local function SMDiff(last, keys, obj, extra)
    local out = {}
    for _, kv in ipairs(keys) do
        local ok, v = pcall(kv[1], obj, kv[2])
        local sv = ok and SMStr(v) or nil
        if sv ~= nil then
            local was = last[kv[2]]
            if (was == nil and not SMDefault(sv)) or (was ~= nil and was ~= sv) then
                table.insert(out, kv[2] .. "=" .. sv)
            end
            last[kv[2]] = sv
        end
    end
    if extra then
        for k, sv in pairs(extra) do
            local was = last[k]
            if (was == nil and not SMDefault(sv)) or (was ~= nil and was ~= sv) then table.insert(out, k .. "=" .. sv) end
            last[k] = sv
        end
    end
    return out
end
local function Emit_SM(head, out)            -- keep lines under A4D_LINE_MAX
    local buf, len = {}, 0
    for _, kv in ipairs(out) do
        if len + #kv > 900 and #buf > 0 then print(head .. table.concat(buf, ";")) buf, len = {}, 0 end
        table.insert(buf, kv)
        len = len + #kv + 1
    end
    if #buf > 0 then print(head .. table.concat(buf, ";")) end
end
function A4D_EntitySM(e, bp, id, t, sq)
    if id == nil or bp == nil then return end
    local isu = sq ~= nil
    if isu and not A4D_SM_UNITS then return end
    local every = isu and A4D_SM_EVERY_U or A4D_SM_EVERY
    local last = A4D_ESM_LAST[id]
    if last ~= nil and (tonumber(id) + A4D_TICK) % every ~= 0 then return end
    local b = tostring(bp)
    if string.sub(b, 1, 4) == "wpn_" then return end        -- v19: TC / outpost arrow weapons: nothing useful, ~200 keys each
    local keys = A4D_SM_BPKEYS[b]
    if keys == nil then
        keys = ProbeKeys("E", e, isu and A4D_SMK_U or A4D_SMK_B, Tokens(b))
        A4D_SM_BPKEYS[b] = keys
        print("A4D|SMK|" .. string.gsub(b, "[|;]", "_") .. "|" .. #keys)
    end
    local extra = nil
    if isu then
        local vr = try(Squad_GetVeterancyRank, sq)
        if type(vr) == "number" then extra = {vet = SMStr(vr)} end
    end
    if #keys > 0 or extra ~= nil then
        if last == nil then last = {} A4D_ESM_LAST[id] = last end
        local out = SMDiff(last, keys, e, extra)
        if #out > 0 then Emit_SM("A4D|ES|" .. t .. "|" .. tostring(id) .. "|", out) end
    end
    -- v21: the same unit keys read through the squad (a squad's own state model can hold what the entity's does not)
    if isu and A4D_SM_SQUADS then
        local sid = try(Squad_GetGameID, sq) or try(Squad_GetID, sq)
        if sid ~= nil and not A4D_QS_DONE[sid] then
            A4D_QS_DONE[sid] = true                     -- one squad member reads it, once per tick
            local qk = A4D_SQ_BPKEYS[b]
            if qk == nil then
                qk = ProbeKeys("S", sq, A4D_SMK_U, Tokens(b))
                A4D_SQ_BPKEYS[b] = qk
                print("A4D|SMK|squad:" .. string.gsub(b, "[|;]", "_") .. "|" .. #qk)
            end
            if #qk > 0 then
                A4D_QSM_LAST[sid] = A4D_QSM_LAST[sid] or {}
                local qo = SMDiff(A4D_QSM_LAST[sid], qk, sq, nil)
                if #qo > 0 then Emit_SM("A4D|QS|" .. t .. "|" .. tostring(sid) .. "|", qo) end
            end
        end
    end
end
function A4D_PlayerSM(p, k, t)
    if A4D_TICK % A4D_SM_EVERY ~= 0 and A4D_PSM_LAST[k] ~= nil then return end
    A4D_PSM_KEYS = A4D_PSM_KEYS or {}
    local keys = A4D_PSM_KEYS[k]
    if keys == nil then
        keys = ProbeKeys("P", p, A4D_SMK_P, nil)
        A4D_PSM_KEYS[k] = keys
        print("A4D|SMK|player" .. k .. "|" .. #keys)
    end
    A4D_PSM_LAST[k] = A4D_PSM_LAST[k] or {}
    local out = SMDiff(A4D_PSM_LAST[k], keys, p, nil)
    if #out > 0 then Emit_SM("A4D|PS|" .. t .. "|" .. k .. "|", out) end
end

A4D_PQ_SEEN = {}
function A4D_ProbeQueue(e)              -- each blueprint at most twice (TCs first would use them all up)
    local id = try(Entity_GetID, e)
    local bp = try(BP_GetName, try(Entity_GetBlueprint, e))
    local n = A4D_PQ_SEEN[tostring(bp)] or 0
    if n >= 2 then return end
    A4D_PQ_SEEN[tostring(bp)] = n + 1
    A4D_PQ_LEFT = A4D_PQ_LEFT - 1
    local out = {}
    for _, i in ipairs({0, 1}) do
        local ok1, it = pcall(Entity_GetProductionQueueItem, e, i)
        local ok2, ty = pcall(Entity_GetProductionQueueItemType, e, i)
        table.insert(out, i .. ":" .. (ok1 and show(it) or ("err " .. tostring(it))) .. "/" .. (ok2 and show(ty) or ("err " .. tostring(ty))))
    end
    print("A4D|PQ|" .. tostring(id) .. "|" .. tostring(bp) .. "|" .. string.gsub(table.concat(out, ";"), "[|\n]", "_"))
end

local function Res(player, rt)
    if rt == nil then return nil end
    return try(Player_GetResource, player, rt)
end

local function Sanitize(v)
    if v == nil then return "" end
    return (string.gsub(tostring(v), "[|;,]", "_"))
end

-- neutral entities (resources, wildlife): try known lookups, keep the first that returns a group
local NODE_METHOD = nil
local function NeutralGroup()
    local tries = {
        {"World_GetAllNeutralEntities", function() return World_GetAllNeutralEntities() end},
        {"World_GetAllNeutralEntities(eg)", function()
            local eg = EGroup_CreateIfNotFound("a4d_neutral"); EGroup_Clear(eg)
            World_GetAllNeutralEntities(eg); return eg end},
        {"World_GetEntitiesNearPoint", function()
            local eg = EGroup_CreateIfNotFound("a4d_neutral"); EGroup_Clear(eg)
            World_GetEntitiesNearPoint(nil, eg, World_Pos(0, 0, 0), 2000, OT_Neutral); return eg end},
    }
    for i = 1, #tries do
        if NODE_METHOD == nil or NODE_METHOD == tries[i][1] then
            local ok, eg = pcall(tries[i][2])
            if ok and eg ~= nil then
                local okc, c = pcall(EGroup_Count, eg)
                if okc and c ~= nil and c > 0 then
                    if NODE_METHOD == nil then
                        NODE_METHOD = tries[i][1]
                        print("A4D|NCAPS|" .. NODE_METHOD)
                    end
                    return eg
                end
            end
        end
    end
    return nil
end

-- Map objects: one full scan at the start (A4D|N|t|1), then only changes, spread evenly over every
-- second (no bursts): tracked objects (gaia_* / resource_* / relics: food, mines, animals, carcasses)
-- every second (position, visibility, remaining amount); trees only checked for being chopped down,
-- A4D_TREE_SLICES slices (each tree every A4D_TREE_SLICES s); new objects (carcasses) found by
-- re-reading the neutral list every A4D_DISCOVER s, a slice per second.
A4D_NODE = {}            -- id -> {bp, tree, x, z, m (vismask), r (remaining)}
A4D_GONE = {}            -- ids seen gone (never re-added)
A4D_TREES = {}           -- tree ids, round robin
A4D_TREE_I = 1
A4D_DISC_EG, A4D_DISC_I, A4D_DISC_N = nil, 1, 0

local function Tracked(bp)
    return string.sub(bp, 1, 5) == "gaia_" or string.sub(bp, 1, 9) == "resource_"
        or string.find(bp, "relic", 1, true) ~= nil
end

local function VisMask(players, n, e)
    if type(Player_CanSeeEntity) ~= "function" then return nil end
    local m = 0
    for j = 1, n do
        if try(Player_CanSeeEntity, players[j], e) == true then m = m + 2 ^ (j - 1) end
    end
    return m
end

local function NodeRec(id, nd)
    return table.concat({s(id), Sanitize(nd.bp), num(nd.x), num(nd.z),
        nd.m ~= nil and int(nd.m) or "", num(nd.r)}, ",")
end

local function Emit(head, buf)
    local i, n = 1, #buf
    while i <= n do
        local j, len = i, #head + #buf[i]
        while j < n and j - i + 1 < A4D_CHUNK and len + 1 + #buf[j + 1] <= A4D_LINE_MAX do
            j = j + 1
            len = len + 1 + #buf[j]
        end
        print(head .. table.concat(buf, ";", i, j))
        i = j + 1
    end
end

-- read a new object; returns id and record (nil if unreadable)
-- v19 strategic points (owner 2026-11-12: sacred sites are captured by religious units from Castle (30 s), held by any
-- unit sitting on the aura (contest / pause), decapped by any unit (30 s), the 10 min sacred victory paused while
-- contested; trade posts are used by traders): found among the neutral objects (Entity_IsStrategicPoint, else the
-- blueprint name), read every second, written when anything changed. Argument order of the capture calls is not
-- known: both orders are tried (A4D|SSCAPS says which worked).
A4D_SITES = {}            -- id -> {e, bp, last}
A4D_SITE_IDS = {}
A4D_SITE_WORDS = {"holy_site", "sacred_site", "trade_post", "strategic_point", "capture_point"}
local function SiteMark(e, id, bp)
    if A4D_SITES[id] ~= nil then return end
    local sp = try(Entity_IsStrategicPoint, e)
    local hit = sp == true
    if not hit then
        for _, w in ipairs(A4D_SITE_WORDS) do
            if string.find(bp, w, 1, true) ~= nil then hit = true break end
        end
    end
    if not hit then return end
    A4D_SITES[id] = {e = e, bp = bp}
    table.insert(A4D_SITE_IDS, id)
    print("A4D|SSI|" .. s(id) .. "|" .. string.gsub(bp, "[|;,]", "_") .. "|" .. s(sp) .. "|" .. s(try(Entity_IsVictoryPoint, e)))
end
A4D_SSCAPS = {}
local function Try2(name, a, b)      -- f(a, b), else f(b, a); the working order is reported once
    local f = _G[name]
    if type(f) ~= "function" then return nil end
    local order = A4D_SSCAPS[name]
    if order ~= "ba" then
        local ok, v = pcall(f, a, b)
        if ok and v ~= nil then
            if order == nil then A4D_SSCAPS[name] = "ab" print("A4D|SSCAPS|" .. name .. "|ab|" .. type(v)) end
            return v
        end
    end
    if order ~= "ab" then
        local ok, v = pcall(f, b, a)
        if ok and v ~= nil then
            if order == nil then A4D_SSCAPS[name] = "ba" print("A4D|SSCAPS|" .. name .. "|ba|" .. type(v)) end
            return v
        end
    end
    return nil
end
local function SiteV(v)
    if v == true then return "1" elseif v == false then return "0" end
    if type(v) == "number" then return (string.gsub(string.format("%.3f", v), "%.?0+$", "")) end
    return ""
end
function A4D_SiteTick(t, players, n)
    if #A4D_SITE_IDS == 0 then return end
    local out = {}
    for _, id in ipairs(A4D_SITE_IDS) do
        local st = A4D_SITES[id]
        local e = st.e
        if type(Entity_FromID) == "function" then e = try(Entity_FromID, id) or e end
        local owner, prog, near = 0, {}, {}
        for k = 1, n do
            local p = players[k]
            if owner == 0 and Try2("Entity_IsStrategicPointCapturedBy", e, p) == true then owner = k end
            prog[k] = SiteV(Try2("Player_GetStrategicPointCaptureProgress", p, e))
            near[k] = SiteV(Try2("Player_HasCapturingSquadNearStrategicPoint", p, e))
        end
        local rec = table.concat({s(id), tostring(owner), table.concat(prog, ":"), table.concat(near, ":"),
                                  SiteV(try(Entity_GetStrategicPointSecureCount, e)),
                                  SiteV(try(Entity_GetActiveTraderCount, e))}, ",")
        if rec ~= st.last then st.last = rec table.insert(out, rec) end
    end
    if #out > 0 then Emit("A4D|SS|" .. t .. "|", out) end
end

local function Observe(e, players, n)
    local id = try(Entity_GetID, e)
    if id == nil then return nil end
    local bp = try(BP_GetName, try(Entity_GetBlueprint, e))
    if bp == nil then return nil end
    pcall(SiteMark, e, id, bp)
    local nd = {bp = bp, tree = not Tracked(bp), e = e}
    local pos = try(Entity_GetPosition, e)
    if type(pos) == "table" then nd.x = pos.x; nd.z = pos.z end
    nd.m = VisMask(players, n, e)
    if not nd.tree then nd.r = try(Entity_GetRemainingResourceDepositAmount, e) end
    if not nd.tree and A4D_SIZE[bp] == nil then pcall(A4D_SizeOf, e, bp) end
    return id, nd
end

-- the entity behind an id now, or nil if it is gone
local function Live(id, nd)
    if type(Entity_IsValid) == "function" and try(Entity_IsValid, id) ~= true then return nil end
    local e = nd.e
    if type(Entity_FromID) == "function" then e = try(Entity_FromID, id) end
    if e == nil or try(Entity_GetID, e) ~= id then return nil end
    return e
end

-- re-check one known object: changes go to ch, removals to gone. Trees don't move: only whether
-- they still stand (chopped down = gone); their visibility comes from sight radii in the analysis.
local function Check(id, nd, ch, gone, players, n)
    local e = Live(id, nd)
    local pos = e and try(Entity_GetPosition, e)
    if type(pos) ~= "table" then
        table.insert(gone, s(id)); A4D_NODE[id] = nil; A4D_GONE[id] = true; return
    end
    if nd.tree then
        -- v10 (owner 2026-11-11: chopped woodlines were not updated): a tree being cut keeps its entity until it is
        -- empty, so its remaining wood is sent too (still once per A4D_TREE_SLICES s per tree; visibility not read)
        local r = try(Entity_GetRemainingResourceDepositAmount, e)
        if r ~= nil and (nd.r == nil or math.abs(r - nd.r) >= 1) then
            nd.r = r
            table.insert(ch, NodeRec(id, nd))
        end
        return
    end
    local m = VisMask(players, n, e)
    local r = nil
    if not nd.tree then r = try(Entity_GetRemainingResourceDepositAmount, e) end
    local moved = nd.x == nil or math.abs(pos.x - nd.x) > 1 or math.abs(pos.z - nd.z) > 1
    local amount = (r == nil) ~= (nd.r == nil) or (r ~= nil and math.abs(r - nd.r) >= 1)
    if moved or m ~= nd.m or amount then
        nd.x, nd.z, nd.m, nd.r = pos.x, pos.z, m, r
        table.insert(ch, NodeRec(id, nd))
    end
end

local function NodesStart(t, players, n)
    local eg = NeutralGroup()
    if eg == nil then return false end
    local buf = {}
    for i = 1, EGroup_Count(eg) do
        local e = try(EGroup_GetEntityAt, eg, i)
        if e ~= nil then
            local id, nd = Observe(e, players, n)
            if id ~= nil and A4D_NODE[id] == nil then
                A4D_NODE[id] = nd
                if nd.tree then table.insert(A4D_TREES, id) end
                table.insert(buf, NodeRec(id, nd))
            end
        end
    end
    Emit("A4D|N|" .. t .. "|1|", buf)
    return true
end

local function NodesTick(t, players, n)
    local ch, gone = {}, {}
    for id, nd in pairs(A4D_NODE) do
        if not nd.tree then Check(id, nd, ch, gone, players, n) end
    end
    local k = math.ceil(#A4D_TREES / A4D_TREE_SLICES)
    local done = 0
    while done < k and #A4D_TREES > 0 do
        if A4D_TREE_I > #A4D_TREES then A4D_TREE_I = 1 end
        local id = A4D_TREES[A4D_TREE_I]
        local nd = A4D_NODE[id]
        if nd ~= nil then Check(id, nd, ch, gone, players, n) end
        if A4D_NODE[id] == nil then
            table.remove(A4D_TREES, A4D_TREE_I)
        else
            A4D_TREE_I = A4D_TREE_I + 1
        end
        done = done + 1
    end
    if A4D_DISC_EG == nil or A4D_TICK % A4D_DISCOVER == 0 then
        A4D_DISC_EG = NeutralGroup()
        A4D_DISC_I = 1
        A4D_DISC_N = A4D_DISC_EG ~= nil and (try(EGroup_Count, A4D_DISC_EG) or 0) or 0
    end
    if A4D_DISC_EG ~= nil then
        local last = math.min(A4D_DISC_N, A4D_DISC_I + math.ceil(A4D_DISC_N / A4D_DISCOVER) - 1)
        for i = A4D_DISC_I, last do
            local e = try(EGroup_GetEntityAt, A4D_DISC_EG, i)
            local id = e ~= nil and try(Entity_GetID, e) or nil
            if id ~= nil and A4D_NODE[id] == nil and not A4D_GONE[id] and Live(id, {e = e}) ~= nil then
                local id2, nd = Observe(e, players, n)
                if id2 ~= nil then
                    if nd.tree then nd.m = nil end
                    A4D_NODE[id2] = nd
                    if nd.tree then table.insert(A4D_TREES, id2) end
                    table.insert(ch, NodeRec(id2, nd))
                end
            end
        end
        A4D_DISC_I = last + 1
    end
    Emit("A4D|NC|" .. t .. "|", ch)
    Emit("A4D|NX|" .. t .. "|", gone)
    return true
end
A4D_NODES_OK = true
A4D_NODE_FAILS = 0

local function GameTime()
    local t = try(World_GetGameTime)
    if t == nil then return A4D_TICK end
    return t
end

function A4D_Caps()
    local names = {"World_GetGameTime","Player_GetResource","Entity_GetPosition",
                   "Player_CanSeeEntity","Entity_GetBlueprint","BP_GetName","Entity_GetID",
                   "Player_GetCurrentAge","Player_GetAge","World_GetAllNeutralEntities",
                   "World_GetEntitiesNearPoint","Squad_GetGameID","Squad_GetID",
                   "Squad_IsGatheringResourceType","Squad_IsInHoldEntity","Entity_GetHealth",
                   "Entity_GetBuildingProgress","Entity_GetProductionQueueSize",
                   "Entity_GetRemainingResourceDepositAmount","Player_GetCurrentPopulation",
                   "Entity_FromID","Entity_IsValid"}
    local t = {"A4D|CAPS"}
    for i = 1, #names do
        local present = (type(_G[names[i]]) == "function") and 1 or 0
        table.insert(t, names[i] .. "=" .. present)
    end
    table.insert(t, "RT_Food=" .. ((RT_Food ~= nil) and 1 or 0))
    print(table.concat(t, "|"))
end

-- Fights: units attacking another player's entity, their targets, and every player entity within
-- A4D_FIGHT_NEAR of an attacker form the fight set (rebuilt each second). While it is not empty,
-- A4D_Fast samples it every A4D_FAST s: A4D|F|t|id,x,z,hp,target;...
A4D_FIGHT = {}
A4D_FIGHT_N = 0
local function FightSet(pos_all, attacks)
    local set, n, cell, grid, att = {}, 0, A4D_FIGHT_NEAR, {}, {}
    for a, tg in pairs(attacks) do
        if pos_all[tg] ~= nil then table.insert(att, a); set[a] = true; set[tg] = true end
    end
    if #att > 0 then
        for id, p in pairs(pos_all) do
            local key = math.floor(p[1] / cell) .. ":" .. math.floor(p[2] / cell)
            local b = grid[key]
            if b == nil then b = {}; grid[key] = b end
            table.insert(b, id)
        end
        for _, a in ipairs(att) do
            local p = pos_all[a]
            local cx, cz = math.floor(p[1] / cell), math.floor(p[2] / cell)
            for dx = -1, 1 do
                for dz = -1, 1 do
                    local b = grid[(cx + dx) .. ":" .. (cz + dz)]
                    if b ~= nil then
                        for _, id in ipairs(b) do
                            local q = pos_all[id]
                            if (q[1] - p[1]) ^ 2 + (q[2] - p[2]) ^ 2 <= cell * cell then set[id] = true end
                        end
                    end
                end
            end
        end
    end
    for _ in pairs(set) do n = n + 1 end
    A4D_FIGHT, A4D_FIGHT_N = set, n
end

function A4D_Fast()
    if A4D_STOPPED or A4D_FIGHT_N == 0 then return end
    local ok, err = pcall(function()
        local buf = {}
        for id in pairs(A4D_FIGHT) do
            local e = nil
            if try(Entity_IsValid, id) ~= false then e = try(Entity_FromID, id) end
            local pos = e ~= nil and try(Entity_GetPosition, e) or nil
            if type(pos) == "table" then
                local target = nil
                if try(Entity_IsAttacking, e, A4D_FAST * 2) == true then
                    local te = try(Entity_GetAttackTargetEntity, e)
                    if te ~= nil then target = try(Entity_GetID, te) end
                end
                table.insert(buf, table.concat({s(id), num(pos.x), num(pos.z), int(try(Entity_GetHealth, e)), s(target)}, ","))
            else
                table.insert(buf, s(id) .. ",,,0,")       -- gone (died) since the last sample
            end
        end
        Emit("A4D|F|" .. string.format("%.2f", GameTime()) .. "|", buf)
    end)
    if not ok then print("A4D|FERR|" .. Sanitize(err)) end
end

-- v18 (bigmanjohn's recorder has these, MIT): production queue head, squad move destinations, real costs
--   A4D|Q|t|id,size,type,bp;...   queue size + the item in production (spawn / upgrade / playerupgrade / squadupgrade /
--                                 reinforce), on change
--   A4D|D|t|squad,x,z;... / squad,-   move destination set / cleared (the order arrows for the inference layer)
--   A4D|B|t|player|bp|key=value,...   what the bp costs this player (civ discounts, upgrades), first sighting and again
--                                     after any upgrade when it changed
A4D_QLAST, A4D_DLAST, A4D_BLAST, A4D_BSEEN = {}, {}, {}, {}
A4D_COST_DIRTY = false
local function ItemType(ty)
    if PITEM_Spawn ~= nil and ty == PITEM_Spawn then return "spawn" end
    if PITEM_Upgrade ~= nil and ty == PITEM_Upgrade then return "upgrade" end
    if PITEM_PlayerUpgrade ~= nil and ty == PITEM_PlayerUpgrade then return "playerupgrade" end
    if PITEM_SquadUpgrade ~= nil and ty == PITEM_SquadUpgrade then return "squadupgrade" end
    if PITEM_SquadReinforce ~= nil and ty == PITEM_SquadReinforce then return "reinforce" end
    return "?"
end
function A4D_QueueHead(e, id, size, out)
    local key = s(size) .. ",-,-"
    if size and size > 0 then
        local okB, bp = pcall(function() return BP_GetName(Entity_GetProductionQueueItem(e, 0)) end)
        local okT, ty = pcall(Entity_GetProductionQueueItemType, e, 0)
        key = s(size) .. "," .. (okT and ItemType(ty) or "?") .. "," .. (okB and Sanitize(bp) or "?")
        -- v21: the whole queue (owner 2026-11-12: production credit / progress without guessing)
        local all = {}
        for i = 0, math.min(size, 20) - 1 do
            local okI, bi = pcall(function() return BP_GetName(Entity_GetProductionQueueItem(e, i)) end)
            all[#all + 1] = okI and string.gsub(Sanitize(bi), "[+,]", "_") or "?"
        end
        key = key .. "," .. table.concat(all, "+")
    end
    if A4D_QLAST[id] ~= key then
        if not (A4D_QLAST[id] == nil and size == 0) then table.insert(out, s(id) .. "," .. key) end
        A4D_QLAST[id] = key
    end
end
A4D_DEST_OK = true
function A4D_Dest(p, out)
    if not A4D_DEST_OK then return end
    local ok, err = pcall(function()
        SGroup_ForEach(Player_GetSquads(p), function(gid, idx, sq)
            local sid = s(try(Squad_GetGameID, sq) or try(Squad_GetID, sq) or 0)
            local d = false
            if Squad_HasDestination(sq) then
                local pos = Squad_GetDestination(sq)
                d = num(pos.x) .. "," .. num(pos.z)
            end
            local prev = A4D_DLAST[sid]
            if prev ~= d and not (prev == nil and d == false) then table.insert(out, sid .. "," .. (d or "-")) end
            A4D_DLAST[sid] = d
            return false
        end)
    end)
    if not ok then A4D_DEST_OK = false print("A4D|DERR|" .. Sanitize(err)) end
end
function A4D_Cost(p, k, bp, e, sq, t)
    local key = k .. "|" .. tostring(bp)
    if A4D_BSEEN[key] then return end
    A4D_BSEEN[key] = true
    local ok, c = false, nil
    if sq ~= nil then ok, c = pcall(function() return Player_GetSquadBPCost(p, Squad_GetBlueprint(sq)) end) end
    if not ok or type(c) ~= "table" then ok, c = pcall(function() return Player_GetEntityBPCost(p, Entity_GetBlueprint(e)) end) end
    if not ok or type(c) ~= "table" then return end
    local parts = {}
    for kk, v in pairs(c) do
        if type(v) == "number" and v ~= 0 then table.insert(parts, tostring(kk) .. "=" .. num(v)) end
    end
    table.sort(parts)
    local line = table.concat(parts, ",")
    if A4D_BLAST[key] ~= line then
        A4D_BLAST[key] = line
        print("A4D|B|" .. t .. "|" .. k .. "|" .. Sanitize(bp) .. "|" .. line)
    end
end

-- v21 active abilities (owner 2026-11-12: "complete the recorder"): toggles / timed / self-cast abilities from aoe4world and the
-- game's own ability list; each blueprint is probed once (Entity_HasAbility / Squad_HasAbility), then every A4D_AA_EVERY s
-- per entity which of them are active (Entity_IsAbilityActive) or in progress (Squad_IsDoingAbility), written on change
A4D_AB_CAND = A4D_AB_CAND or {
    "abbey_of_the_isles_relic_mover_sco", "activate_akritoi_byz", "activate_ghillie_stealth_sco", "activate_stealth_mal",
    "age_up_castle", "age_up_castle_abb", "age_up_castle_mon_ha_gol", "age_up_dark_1_tem", "age_up_feudal",
    "age_up_feudal_abb", "age_up_feudal_mon_ha_gol", "age_up_imperial", "age_up_imperial_abb",
    "age_up_imperial_mon_ha_gol", "armor_1_vik", "armor_2_vik", "armor_3_vik", "auto_heal_inspire_toggle_fre",
    "baibars_relentless_barrage_ayy", "beachhead_ram_hold_unload", "beeskep_construction_cancel_vik",
    "beeskep_construction_vik", "breachhead_carrier_mon_ha_gol", "buddhist_conversion", "building_immunity_chi_ha_01",
    "buy_food", "buy_stone", "buy_wood", "call_rus_tributes_mon_ha_gol", "call_shield_maidens_vik",
    "camel_knight_charge_damage", "cancel_unpacking_building_mon", "cancel_unpacking_building_mon_ha_gol",
    "cannon_swap_byz", "cannon_swap_fre", "caracole_hre", "cataphract_trample_byz", "cheer_toggle",
    "clan_level_hojo_0_jpn_ha_sen", "clan_level_hojo_1_jpn_ha_sen", "clan_level_hojo_2_jpn_ha_sen",
    "clan_level_hojo_3_jpn_ha_sen", "clan_level_oda_0_jpn_ha_sen", "clan_level_oda_1_jpn_ha_sen",
    "clan_level_oda_2_jpn_ha_sen", "clan_level_oda_3_jpn_ha_sen", "clan_level_takeda_0_jpn_ha_sen",
    "clan_level_takeda_1_jpn_ha_sen", "clan_level_takeda_2_jpn_ha_sen", "clan_level_takeda_3_jpn_ha_sen",
    "codex_bear_saga_vik", "codex_dragon_saga_vik", "codex_falcon_saga_vik", "codex_raven_saga_vik",
    "codex_serpent_saga_vik", "codex_sheep_saga_vik", "codex_wolf_saga_vik", "combat_unit_hold_position",
    "core_auto_heal_toggle", "core_building_scuttle", "core_building_scuttle_no_enemies", "core_convert_to_gate",
    "core_convert_to_palisade_gate", "core_declare_religious_victory", "core_formation_line", "core_formation_spread",
    "core_formation_wedge", "core_gate_auto_toggle", "core_market_buy_food", "core_market_buy_food_bulk",
    "core_market_buy_merc_bulk_byz", "core_market_buy_merc_byz", "core_market_buy_stone", "core_market_buy_stone_bulk",
    "core_market_buy_wood", "core_market_buy_wood_bulk", "core_market_sell_food", "core_market_sell_food_bulk",
    "core_market_sell_merc_bulk_byz", "core_market_sell_merc_byz", "core_market_sell_stone", "core_market_sell_stone_bulk",
    "core_market_sell_wood", "core_market_sell_wood_bulk", "core_reseed_farm_auto", "core_unit_death",
    "core_xbox_auto_train_villager", "core_xbox_siege_deploy", "damage_1_vik", "damage_2_vik", "damage_3_vik",
    "deploy_campfire_eng", "deploy_palings", "deploy_palings_elite", "deploy_palings_veteran", "deploy_pavise_fre",
    "disable_breachhead_carrier_mon_ha_gol", "disable_unit_collision_song_cmp", "disable_villager_production_global_vik",
    "dummy_clan_level_hojo_1", "dummy_clan_level_hojo_2", "dummy_clan_level_hojo_3", "dummy_clan_level_oda_1",
    "dummy_clan_level_oda_2", "dummy_clan_level_oda_3", "dummy_clan_level_takeda_1", "dummy_clan_level_takeda_2",
    "dummy_clan_level_takeda_3", "elephant_trample_sul_ha_tug", "explosive_cart_self_detonate",
    "farmhouse_ungarrison_dummy_ayy", "farmstead_construction_cancel_vik", "farmstead_construction_vik",
    "festival_food_mal", "festival_military_mal", "festival_siege_mal", "fireship_self_detonate", "fish_pond_relocate_sco",
    "force_dropoff", "fortify_ribauld_fre", "galata_spawner_toggle_on_byz", "galata_spawner_toggle_on_byz_ha_mac",
    "global_return_to_work", "golden_age_passive_abb", "golden_horde_rally_mon_ha_gol", "golden_tent_castle_mon_ha_gol",
    "golden_tent_feudal_mon_ha_gol", "golden_tent_imperial_mon_ha_gol", "governor_ajmer_passive_tug",
    "governor_jalor_passive_tug", "governor_multan_passive_tug", "governor_sehwan_passive_tug", "governor_uch_passive_tug",
    "grand_galley_archer_production_ott", "grand_galley_crossbow_production_ott", "grand_galley_handcannon_production_ott",
    "grand_galley_horsearcher_production_ott", "grand_galley_horsemen_production_ott",
    "grand_galley_knight_production_ott", "grand_galley_manatarms_production_ott", "grand_galley_mehter_production_ott",
    "grand_galley_spearmen_production_ott", "grand_galley_weapon_activation_ott", "guild_hall_collect_resources_fre",
    "hippodrome_triumph_byz", "hire_ronin_all_tickets_poi", "hire_ronin_poi", "hold_return_to_work",
    "horse_archer_mounted_training_gallop_rus", "horseman_rally_mon_ha_gol", "hospitaller_master_full_heal_cru",
    "imperial_spies", "increase_armor_song_cmp", "increase_damage_song_cmp", "increase_speed_song_cmp",
    "infantry_forced_march_ayy", "infantry_forced_march_sul", "influence_auto_repair_hre",
    "jeanne_d_arc_aoe_damage_ability_fre_ha_01", "jeanne_d_arc_buyback_1_fre_ha_01", "jeanne_d_arc_buyback_2_fre_ha_01",
    "jeanne_d_arc_buyback_3_fre_ha_01", "jeanne_d_arc_buyback_4_fre_ha_01", "jeanne_d_arc_divine_restoration_fre_ha_01",
    "jeanne_d_arc_influence_building_fre_ha_01", "jeanne_d_arc_inspired_ally_fre_ha_01",
    "jeanne_d_arc_journey_of_a_hero_archer_fre_ha_01", "jeanne_d_arc_journey_of_a_hero_commander_monarch_fre_ha_01",
    "jeanne_d_arc_journey_of_a_hero_crossbow_companions_fre_ha_01",
    "jeanne_d_arc_journey_of_a_hero_gunpowder_monarch_fre_ha_01",
    "jeanne_d_arc_journey_of_a_hero_manatarms_companions_fre_ha_01",
    "jeanne_d_arc_journey_of_a_hero_womanatarms_fre_ha_01", "jeanne_d_arc_rallying_call_archers_fre_ha_01",
    "jeanne_d_arc_rallying_call_cannon_fre_ha_01", "jeanne_d_arc_rallying_call_crossbows_fre_ha_01",
    "jeanne_d_arc_rallying_call_knights_fre_ha_01", "jeanne_d_arc_rallying_call_manatarms_fre_ha_01",
    "jeanne_d_arc_rallying_call_spearmen_fre_ha_01", "jeanne_d_arc_ranged_damage_ability_fre_ha_01",
    "jeanne_d_arc_valorous_inspiration_fre_ha_01", "khan_attack_speed_signal_arrow_mon", "khan_defensive_signal_arrow_mon",
    "khan_maneuver_signal_arrow_mon", "kremlin_levy", "kremlin_levy_all_tickets", "kremlin_levy_gunner",
    "kremlin_levy_gunner_all_tickets", "lancer_charge_bonus_fre", "landmark_activate_akritoi_byz",
    "landmark_cistern_boost_byz_ha_mac", "landmark_toggle_automatic_flask_byz", "leader_armor_activated",
    "leader_attack_speed_activated", "leader_attack_speed_activated_lowcd", "leader_construction_activated",
    "leader_damage_activated", "leader_decay_armor_activated", "leader_decay_armor_activated_lowcd", "leader_falcon_sight",
    "leader_gunpowder_attack_speed_activated", "leader_healing_activated", "leader_healing_activated_lowcd",
    "leader_improved_armor_maneuver_arrow", "leader_improved_incendiary_attack_speed_arrow",
    "leader_knight_damage_move_speed_activated", "leader_knight_damage_move_speed_activated_tem",
    "leader_move_speed_activated", "leader_move_speed_activated_lowcd", "leader_production_activated",
    "leader_production_mon_activated", "leader_rally_yeomen_cmp_lan", "leader_ranged_attack_speed_activated",
    "leader_reduce_armor_activated_lowcd", "leader_siege_damage_activated", "living_off_land_vik",
    "longbow_rate_of_fire_ability", "longbow_rate_of_fire_ability_nrm", "longbow_set_up_camp", "longbow_set_up_camp_nrm",
    "longhouse_bee_skep_info_vik", "longhouse_farmstead_info_vik", "longhouse_loom_info_vik", "longhouse_smithy_info_vik",
    "loom_construction_cancel_vik", "loom_construction_vik", "mamluk_swap_to_bow_weapon", "mamluk_swap_to_sword_weapon",
    "mamluk_weapon_toggle", "mangonel_incendiary_weapon", "mangonel_swap_to_incendiary_weapon",
    "mangonel_swap_to_kinetic_weapon", "matsuri_call_yatai_jpn_ha_sen", "matsuri_call_yatai_toggle_off_jpn_ha_sen",
    "mehter_attack_buff_ott", "mehter_melee_armor_buff_ott", "mehter_ranged_armor_buff_ott",
    "militarization_vil_equip_weapons_statetree_eng", "militarization_vil_equip_weapons_statetree_nrm",
    "military_school_archer_production_ott", "military_school_crossbow_production_ott",
    "military_school_handcannon_production_ott", "military_school_horsearcher_production_ott",
    "military_school_horsemen_production_ott", "military_school_knight_production_ott",
    "military_school_manatarms_production_ott", "military_school_mehter_production_ott",
    "military_school_spearmen_production_ott", "monastery_create_relic", "monastery_relic_remove", "monk_aoe_heal",
    "monk_conversion", "monk_conversion_faith_abb", "monk_debuff_target_jpn",
    "monk_debuff_target_jpn_five_mountain_version", "monk_shinto_deposit_sacred_object_jpn", "mustering_hall_passive_sco",
    "naval_chain_shot", "naval_fairy_flag_hidden_sco", "naval_fairy_flag_sco", "naval_formation_column",
    "naval_formation_line", "naval_formation_spread", "naval_man_the_sails", "nehan_conversion",
    "no_delay_building_scuttle", "official_auto_collect_tax_toggle_chi", "official_supervise_building_target_chi",
    "outpost_glorious_charge_mon_ha_gol", "pack_building_mon", "pack_building_pasture_mon", "pack_landmark_mon",
    "pagoda_forest_conversion_jin", "pagoda_forest_conversion_jin_ring_2", "pagoda_forest_conversion_jin_ring_3",
    "pagoda_forest_conversion_jin_ring_4", "palace_of_the_sultan_elephant_spawner_toggle_on_sul",
    "passive_trait_bowman_toggle_byz_ha_mac", "passive_trait_knight_toggle_byz_ha_mac",
    "passive_trait_lodya_attack_toggle_byz_ha_mac", "passive_trait_lodya_galley_toggle_byz_ha_mac",
    "passive_trait_spearman_toggle_byz_ha_mac", "passive_trait_warrior_toggle_byz_ha_mac", "pilgrim_flask_byz",
    "pilgrim_loan_large_tem", "pilgrim_loan_medium_tem", "pilgrim_loan_small_tem", "pilgrim_target_tem",
    "place_garden_jin", "production_building_enhance_abb", "qutuz_armor_ayy", "regicide_king_sprint",
    "regicide_king_treason", "relentless_attack_cmp_tem", "saladin_armor_activated_ayy", "scholar_mapping_sul",
    "sell_food", "sell_stone", "sell_wood", "shaolin_monk_ranged_damage_reduction", "shinobi_blink_jpn",
    "shinobi_sabotage_jpn", "shinobi_spy_jpn", "shinobi_spy_jpn_ha_sen", "shirkuh_speed_activate_ayy",
    "siege_carpentry_abb_ha_01", "siege_unload_all_ott", "siege_weapon_setup_statetree", "siege_weapon_teardown_statetree",
    "sipahi_stamina_ott", "sipahi_weapon_change_ott", "smithy_construction_cancel_vik", "smithy_construction_vik",
    "snowdoun_gate_archer_spawner_toggle_sco", "snowdoun_gate_cateran_toggle_sco", "snowdoun_gate_men_at_arms_spawner_sco",
    "snowdoun_gate_pikemen_spawner_sco", "spawn_shinobi_ambush_jpn_ha_sen", "spy_first_strike_dummy_ayy",
    "spy_passive_stealth_dummy_ayy", "streltsy_double_time_ability_rus", "subutai_attack_speed_signal_arrow_mon",
    "subutai_defensive_signal_arrow_mon", "subutai_maneuver_signal_arrow_mon", "swap_to_ming_dynasty",
    "swap_to_song_dynasty", "swap_to_tang_dynasty", "swap_to_yuan_dynasty", "templar_master_attack_speed_cru",
    "templar_master_attack_speed_tem", "teuton_master_armor_cru", "the_kings_rally_cmp_tem", "toggle_automatic_flask_byz",
    "toggle_berserker_production_vik", "toggle_cistern_influence_1_byz", "toggle_cistern_influence_2_byz",
    "toggle_cistern_influence_3_byz", "toggle_cistern_influence_4_byz", "toggle_guild_hall_resource_food_fre",
    "toggle_guild_hall_resource_gold_fre", "toggle_guild_hall_resource_stone_fre", "toggle_guild_hall_resource_wood_fre",
    "toggle_jiangnan_spear", "toggle_jiangnan_xbow", "toggle_jiangnan_yuan", "toggle_jiangnan_zhuge",
    "toggle_khan_edict_1_mon_ha_gol", "toggle_khan_edict_2_mon_ha_gol", "toggle_khan_edict_3_mon_ha_gol",
    "toggle_khan_edict_4_mon_ha_gol", "toggle_khan_edict_5_mon_ha_gol", "toggle_landmark_cistern_influence_1_byz",
    "toggle_landmark_cistern_influence_2_byz", "toggle_landmark_cistern_influence_3_byz",
    "toggle_landmark_cistern_influence_4_byz", "toggle_pit_mine_resource_gold_mal", "toggle_pit_mine_resource_stone_mal",
    "toggle_retainer_production_jpn_ha_sen", "toggle_saladin_armor_ayy", "toggle_saladin_speed_ayy",
    "toggle_spawn_hold_ott", "toggle_spawn_hold_sul", "toggle_spearman_shield_wall_off_byz",
    "toggle_spearman_shield_wall_on_byz", "toggle_temple_of_the_sun_damage_chi_ha_01",
    "toggle_temple_of_the_sun_range_chi_ha_01", "toggle_temple_of_the_sun_regen_chi_ha_01",
    "toggle_temple_of_the_sun_speed_chi_ha_01", "toggle_trade_resource_food_abb", "toggle_trade_resource_food_fre",
    "toggle_trade_resource_gold_fre", "toggle_trade_resource_stone_abb", "toggle_trade_resource_stone_fre",
    "toggle_trade_resource_wood_abb", "toggle_trade_resource_wood_fre", "toggle_villager_production_hidden_vik",
    "toggle_villager_production_vik", "tophane_armory_culverine_production_ott",
    "tophane_armory_great_bombard_production_ott", "tophane_armory_mangonel_production_ott",
    "tophane_armory_ram_production_ott", "tophane_armory_springald_production_ott",
    "tophane_armory_trebuchet_production_ott", "town_center_establish_sacred_grove_dragon_vik", "town_center_town_bell",
    "trade_cart_transform_to_villager_abb_ha_01", "trade_restart", "trade_wing_trader_food_2_abb_ha",
    "trade_wing_trader_food_3_abb_ha", "trade_wing_trader_food_4_abb_ha", "trade_wing_trader_skirmisher_2_abb_ha",
    "trade_wing_trader_skirmisher_3_abb_ha", "trade_wing_trader_skirmisher_4_abb_ha", "trade_wing_trader_stone_2_abb_ha",
    "trade_wing_trader_stone_3_abb_ha", "trade_wing_trader_stone_4_abb_ha", "trade_wing_trader_swordmaster_2_abb_ha",
    "trade_wing_trader_swordmaster_3_abb_ha", "trade_wing_trader_swordmaster_4_abb_ha",
    "trade_wing_trader_trader_2_abb_ha", "trade_wing_trader_trader_3_abb_ha", "trade_wing_trader_trader_4_abb_ha",
    "trade_wing_trader_villager_2_abb_ha", "trade_wing_trader_villager_3_abb_ha", "trade_wing_trader_villager_4_abb_ha",
    "trade_wing_trader_wood_2_abb_ha", "trade_wing_trader_wood_3_abb_ha", "trade_wing_trader_wood_4_abb_ha",
    "treasure_landmark_target_jpn", "tughtekin_attack_speed_ayy", "unlock_bear_saga_vik", "unlock_dragon_saga_vik",
    "unlock_falcon_saga_vik", "unlock_raven_saga_vik", "unlock_serpent_saga_vik", "unlock_sheep_saga_vik",
    "unlock_wolf_saga_vik", "varangian_berserk_2_byz", "varangian_berserk_byz", "varangian_bowman_berserk_byz_ha_mac",
    "varangian_knight_berserk_byz_ha_mac", "varangian_warrior_berserk_byz_ha_mac", "villager_return_to_work",
    "villager_town_bell", "villager_transform_to_trade_cart_abb_ha_01", "volva_auto_boost_toggle_vik",
    "worker_elephant_production_sul_ha_tug", "zhan_ma_song_cmp",
}
A4D_AA_EVERY = A4D_AA_EVERY or 2
A4D_ABP = {}            -- ability name -> blueprint / false
A4D_AB_BP = {}          -- entity blueprint -> {{name, ability blueprint}}
A4D_AA_LAST = {}        -- id -> "a+b" / ""
local function AbilitiesOf(e, sq, b)
    local L = A4D_AB_BP[b]
    if L ~= nil then return L end
    L = {}
    for _, nm in ipairs(A4D_AB_CAND) do
        local abp = A4D_ABP[nm]
        if abp == nil then
            abp = try(BP_GetAbilityBlueprint, nm) or false
            A4D_ABP[nm] = abp
        end
        if abp then
            local has = (sq ~= nil and try(Squad_HasAbility, sq, abp)) or try(Entity_HasAbility, e, abp)
            if has == true then L[#L + 1] = {nm, abp} end
        end
    end
    A4D_AB_BP[b] = L
    if #L > 0 then
        local n = {}
        for _, x in ipairs(L) do n[#n + 1] = x[1] end
        print("A4D|AAK|" .. string.gsub(b, "[|;]", "_") .. "|" .. table.concat(n, ","))
    end
    return L
end
function A4D_ActiveAbilities(e, id, sq, bp, out)
    if id == nil or bp == nil then return end
    if A4D_AA_LAST[id] ~= nil and (tonumber(id) + A4D_TICK) % A4D_AA_EVERY ~= 0 then return end
    local L = AbilitiesOf(e, sq, tostring(bp))
    if #L == 0 then return end
    local on = {}
    for _, x in ipairs(L) do
        local a = try(Entity_IsAbilityActive, e, x[2])
        local d = sq ~= nil and try(Squad_IsDoingAbility, sq, x[2]) or nil
        if a == true or d == true then on[#on + 1] = x[1] end
    end
    local str = table.concat(on, "+")
    if A4D_AA_LAST[id] ~= str then
        if not (A4D_AA_LAST[id] == nil and str == "") then out[#out + 1] = s(id) .. "," .. (str == "" and "-" or str) end
        A4D_AA_LAST[id] = str
    end
end
-- v21 garrison: which squads a building / vehicle holds (Entity_GetSquadsHeld), on change
A4D_G_LAST = {}
function A4D_Garrison(e, id, out)
    local filled = try(Entity_GetFilledHoldSquadSlots, e)
    local was = A4D_G_LAST[id]
    if (filled == nil or filled == 0) and (was == nil or was == "") then return end
    local ids = {}
    if filled and filled > 0 then
        local g = try(Entity_GetSquadsHeld, e)
        if g == nil then
            local sg = try(SGroup_CreateIfNotFound, "a4d_held")
            if sg ~= nil then pcall(SGroup_Clear, sg) if pcall(Entity_GetSquadsHeld, e, sg) then g = sg end end
        end
        for i = 1, (g and (try(SGroup_Count, g) or 0) or 0) do
            local q = try(SGroup_GetSpawnedSquadAt, g, i)
            local sid = q and (try(Squad_GetGameID, q) or try(Squad_GetID, q))
            if sid ~= nil then ids[#ids + 1] = s(sid) end
        end
        if #ids == 0 then ids[1] = "n" .. s(filled) end   -- held, squads not readable: the count
    end
    local str = table.concat(ids, ":")
    if was ~= str then
        out[#out + 1] = s(id) .. "," .. (str == "" and "-" or str)
        A4D_G_LAST[id] = str
    end
end
-- v21 win-condition values: the script's own tables (sacred / wonder victory countdowns are not state models: the world
-- schema holds one campaign counter). Global tables whose name matches A4D_VT_RE (not ours), two levels deep, numbers and
-- booleans, up to A4D_VT_MAX paths; scanned at the start and at 60 s, read every second, written on change
A4D_VT_RE = A4D_VT_RE or {"relig", "sacred", "holy", "wonder", "victor", "conquest", "regicide", "surrender", "wincond", "annihil", "relic"}
A4D_VT_MAX = 300
A4D_VT_PATHS = nil
A4D_VT_LAST = {}
function A4D_VTScan()
    local paths, n = {}, 0
    local function want(k)
        local l = string.lower(k)
        if string.sub(l, 1, 3) == "a4d" then return false end
        for _, w in ipairs(A4D_VT_RE) do if string.find(l, w, 1, true) then return true end end
        return false
    end
    local function walk(tbl, path, depth)
        local cnt = 0
        for k, v in pairs(tbl) do
            cnt = cnt + 1
            if cnt > 200 or n >= A4D_VT_MAX then return end
            if type(k) == "string" or type(k) == "number" then
                local pth = path .. "." .. tostring(k)
                local tv = type(v)
                if tv == "number" or tv == "boolean" then
                    n = n + 1
                    paths[#paths + 1] = {tbl, k, pth}
                    print("A4D|VTK|" .. pth .. "|" .. tv .. "|" .. tostring(v))
                elseif tv == "table" and depth < 2 then
                    walk(v, pth, depth + 1)
                end
            end
        end
    end
    for k, v in pairs(_G) do
        if type(k) == "string" and type(v) == "table" and want(k) then pcall(walk, v, k, 1) end
    end
    A4D_VT_PATHS = paths
    print("A4D|VTN|" .. #paths)
end
function A4D_VTTick(t)
    if A4D_VT_PATHS == nil or A4D_TICK == 60 then pcall(A4D_VTScan) end
    local out = {}
    for _, x in ipairs(A4D_VT_PATHS or {}) do
        local ok, v = pcall(function() return x[1][x[2]] end)
        if ok then
            local sv = type(v) == "number" and string.format("%.3f", v) or tostring(v)
            if A4D_VT_LAST[x[3]] ~= sv then
                A4D_VT_LAST[x[3]] = sv
                out[#out + 1] = string.gsub(x[3], "[|;=]", "_") .. "=" .. sv
            end
        end
    end
    if #out > 0 then Emit("A4D|VT|" .. t .. "|", out) end
end
-- v21 heading in degrees (5 deg steps) for the E record
local function Heading(e, sq)
    local h = (sq ~= nil and try(Squad_GetHeading, sq)) or try(Entity_GetHeading, e)
    if type(h) ~= "table" and type(h) ~= "userdata" then return "" end
    local ok, hx, hz = pcall(function() return h.x, h.z end)
    if not ok or type(hx) ~= "number" or (hx == 0 and hz == 0) then return "" end
    local d = math.deg((math.atan2 or math.atan)(hx, hz)) % 360
    return string.format("%d", (math.floor(d / 5 + 0.5) * 5) % 360)
end

A4D_E_KEY = A4D_E_KEY or 60     -- v20: full entity keyframe every 60 s (parse_log resyncs there after a cut line)
A4D_E_LAST, A4D_E_BP = {}, {}    -- player -> {id -> record tail / bp} as last read
-- owner 2026-11-15 (decision 0007): blueprint, kind, squad id and a building's position / heading are cached per id and
-- re-read when they can change: an upgrade finished (tier upgrades swap the blueprint in place; the next 2 seconds, every
-- entity), the entity gained / lost a squad (Mongol pack / unpack: new squad id, new blueprint), a building was under
-- construction the second before (a placed palisade turning into a gate), else every A4D_STATIC_EVERY s (staggered by id).
-- record.py --full-read sets A4D_STATIC_EVERY = 1: everything every second as before.
A4D_STATIC_EVERY = A4D_STATIC_EVERY or 30
A4D_EC = {}                      -- id -> cached reads
A4D_EC_ALL = 0                   -- seconds left in which every entity re-reads (set by A4D_OnUpgrade)
function A4D_Collect()
    if A4D_STOPPED then return end
    A4D_TICK = A4D_TICK + 1
    local ecAll = A4D_EC_ALL > 0
    if ecAll then A4D_EC_ALL = A4D_EC_ALL - 1 end
    if A4D_EvFlush ~= nil then pcall(A4D_EvFlush) end   -- hits / projectiles of the last second
    if A4D_AbRepFlush ~= nil then pcall(A4D_AbRepFlush, GameTime(), A4D_TICK % 60 == 0) end   -- v20: ended / 60 s ability runs
    if A4D_AUTO_END ~= nil and GameTime() >= A4D_AUTO_END then
        A4D_Stop()
        return
    end
    local t = num(GameTime())
    if A4D_NODES_OK then
        local np = World_GetPlayerCount()
        local pl = {}
        for k = 1, np do pl[k] = World_GetPlayerAt(k) end
        local ok, res
        if not A4D_NODES_STARTED then
            ok, res = pcall(NodesStart, t, pl, np)
            if ok and res ~= false then A4D_NODES_STARTED = true end
        else
            ok, res = pcall(NodesTick, t, pl, np)
        end
        if ok and res ~= false then
            A4D_NODE_FAILS = 0
        else
            A4D_NODE_FAILS = A4D_NODE_FAILS + 1
            print("A4D|NERR|" .. Sanitize(ok and "no neutral entities found" or res))
            if A4D_NODE_FAILS >= 10 then
                A4D_NODES_OK = false
                print("A4D|NCAPS|none")
            end
        end
    end
    local n = World_GetPlayerCount()
    local players = {}
    for k = 1, n do players[k] = World_GetPlayerAt(k) end
    pcall(A4D_SiteTick, t, players, n)
    pcall(A4D_VTTick, t)
    A4D_QS_DONE = {}
    local pos_all, attacks = {}, {}      -- for the fight set: positions of player entities, attacker -> target

    for k = 1, n do
        local p = players[k]
        local nm = try(Player_GetDisplayName, p)
        if type(nm) == "table" then nm = nm.LocString end
        if nm ~= nil then nm = string.gsub(tostring(nm), "[|;,]", "_") end
        local okx, xres = pcall(AllRes, p)
        if not okx or type(xres) ~= "string" then xres = "" end
        local oks, smv = pcall(StateModel, p)
        if not oks or type(smv) ~= "string" then smv = "" end
        local line = {"A4D", "P", t, k, s(nm), s(try(Player_GetRaceName, p)),
                      s(try(Player_GetTeam, p)),
                      num(Res(p, RT_Food)), num(Res(p, RT_Wood)),
                      num(Res(p, RT_Gold)), num(Res(p, RT_Stone)),
                      Level(p, UP_WHEEL), Level(p, UP_FOOD), Level(p, UP_WOOD), Level(p, UP_GOLD),
                      s(try(Player_GetCurrentAge, p) or try(Player_GetAge, p)),
                      s(try(Player_GetCurrentPopulation, p, CT_Personnel) or try(Player_GetCurrentPopulation, p)),
                      s(try(Player_GetCurrentPopulationCap, p, CT_Personnel) or try(Player_GetCurrentPopulationCap, p)),
                      "X", xres, "SM", smv}
        print(table.concat(line, "|"))
        pcall(A4D_PlayerSM, p, k, t)

        local qout, dout, aout, gout = {}, {}, {}, {}
        local eg = Player_GetAllEntities(p)
        local cnt = EGroup_Count(eg)
        local buf, blen = {}, 0
        -- v20: keyframe (all records, E) every A4D_E_KEY s, else only changed records (ED, bp left empty when unchanged)
        local key = A4D_E_LAST[k] == nil or A4D_TICK % A4D_E_KEY == 1
        local last, lastbp, now_ = A4D_E_LAST[k] or {}, A4D_E_BP[k] or {}, {}
        local head = key and "A4D|E|" or "A4D|ED|"
        local function flush()
            if #buf > 0 then
                print(head .. t .. "|" .. k .. "|" .. table.concat(buf, ";"))
                buf, blen = {}, 0
            end
        end
        for i = 1, cnt do
            local e = try(EGroup_GetEntityAt, eg, i)
            if e ~= nil then
            local id = try(Entity_GetID, e)
            local c = id ~= nil and A4D_EC[id] or nil
            local nid = tonumber(id) or 0
            local sq = try(Entity_GetSquad, e)
            local fresh = c == nil or ecAll or c.uc == true or c.hasSq ~= (sq ~= nil)
                or (nid + A4D_TICK) % A4D_STATIC_EVERY == 0
            if c == nil then c = {} if id ~= nil then A4D_EC[id] = c end end
            c.hasSq = sq ~= nil
            local bp = c.bp
            if fresh or bp == nil then
                bp = try(BP_GetName, try(Entity_GetBlueprint, e))
                if bp ~= c.bp then c.kind, c.x, c.hd = nil, nil, nil end
                c.bp = bp
            end
            local x, z = nil, nil
            if sq == nil and not fresh and c.x ~= nil then x, z = c.x, c.z
            else
                local pos = try(Entity_GetPosition, e)
                if type(pos) == "table" then x = pos.x; z = pos.z end
                if sq == nil then c.x, c.z = x, z else c.x = nil end
            end
            local mask = 0
            local maskKnown = type(Player_CanSeeEntity) == "function"
            if maskKnown then
                for j = 1, n do
                    if j ~= k and try(Player_CanSeeEntity, players[j], e) == true then
                        mask = mask + 2 ^ (j - 1)
                    end
                end
            end
            local kind = c.kind
            if kind == nil then
                kind = "o"
                if try(Entity_IsOfType, e, "worker") == true then kind = "w"
                elseif try(Entity_IsOfType, e, "military") == true then kind = "m" end
                c.kind = kind
            end
            local idle, sqid, flags = "", nil, ""
            if sq ~= nil then
                idle = (try(Squad_IsIdle, sq) == true) and "1" or "0"
                sqid = c.sqid
                if fresh or sqid == nil then sqid = try(Squad_GetGameID, sq) or try(Squad_GetID, sq) c.sqid = sqid end
                local f = {}
                if kind == "w" then                     -- one resource type at a time: stop at the first
                    if try(Squad_IsGatheringResourceType, sq, RT_Food) == true then table.insert(f, "F")
                    elseif try(Squad_IsGatheringResourceType, sq, RT_Wood) == true then table.insert(f, "W")
                    elseif try(Squad_IsGatheringResourceType, sq, RT_Gold) == true then table.insert(f, "G")
                    elseif try(Squad_IsGatheringResourceType, sq, RT_Stone) == true then table.insert(f, "S") end
                    if try(Squad_IsConstructing, sq) == true then table.insert(f, "C") end
                end
                if try(Squad_IsInHoldEntity, sq) == true then table.insert(f, "H") end
                if try(Squad_IsAttacking, sq) == true then table.insert(f, "A") end
                if try(Squad_IsMoving, sq) == true then table.insert(f, "M") end
                flags = table.concat(f)
            end
            if kind == "o" and sq == nil then pcall(A4D_SizeOf, e, bp, id, true) end
            local hp = try(Entity_GetHealth, e)
            local build, queue = nil, nil
            if sq == nil then
                if try(Entity_IsUnderConstruction, e) == true then build = try(Entity_GetBuildingProgress, e) end
                c.uc = build ~= nil
                if try(Entity_HasProductionQueue, e) == true then queue = try(Entity_GetProductionQueueSize, e) end
                if queue and queue > 0 and A4D_PQ_LEFT > 0 then A4D_ProbeQueue(e) end
                if queue ~= nil and id ~= nil then pcall(A4D_QueueHead, e, id, queue, qout) end
            end
            pcall(A4D_EntitySM, e, bp, id, t, sq)
            pcall(A4D_ActiveAbilities, e, id, sq, bp, aout)
            if sq == nil then pcall(A4D_Garrison, e, id, gout) end
            if bp ~= nil and (sq ~= nil or kind == "o") then pcall(A4D_Cost, p, k, bp, e, sq, t) end
            local target = nil
            if try(Entity_IsAttacking, e, 1) == true then
                local te = try(Entity_GetAttackTargetEntity, e)
                if te ~= nil then target = try(Entity_GetID, te) end
            end
            if id ~= nil and x ~= nil then
                pos_all[id] = {x, z}
                if target ~= nil then attacks[id] = target end
            end
            local okh, hd = true, c.hd
            if sq ~= nil or fresh or hd == nil then
                okh, hd = pcall(Heading, e, sq)
                c.hd = (sq == nil and okh) and hd or nil
            end
            local tail = table.concat({num(x), num(z),
                maskKnown and int(mask) or "", kind, idle, s(sqid),
                int(hp), flags,
                build and string.format("%.2f", build) or "", s(queue), s(target), okh and hd or ""}, ",")
            local rec = nil
            local sb = s(bp)
            if id == nil then
                rec = s(id) .. "," .. sb .. "," .. tail
            else
                now_[id] = tail
                if key or last[id] == nil or lastbp[id] ~= sb then
                    rec = s(id) .. "," .. sb .. "," .. tail
                elseif last[id] ~= tail then
                    rec = s(id) .. ",," .. tail
                end
                lastbp[id] = sb
            end
            if rec ~= nil then
                if #buf >= A4D_CHUNK or blen + #rec + 40 > A4D_LINE_MAX then flush() end
                table.insert(buf, rec)
                blen = blen + #rec + 1
            end
            end
        end
        flush()
        if not key then                                   -- v20: gone since the second before
            local gone = {}
            for id_ in pairs(last) do
                if now_[id_] == nil then table.insert(gone, s(id_)) lastbp[id_] = nil A4D_EC[id_] = nil end
            end
            if #gone > 0 then Emit("A4D|EX|" .. t .. "|" .. k .. "|", gone) end
        else
            for id_ in pairs(lastbp) do if now_[id_] == nil then lastbp[id_] = nil A4D_EC[id_] = nil end end
        end
        A4D_E_LAST[k], A4D_E_BP[k] = now_, lastbp
        pcall(A4D_Dest, p, dout)
        if #qout > 0 then Emit("A4D|Q|" .. t .. "|", qout) end
        if #dout > 0 then Emit("A4D|D|" .. t .. "|", dout) end
        if #aout > 0 then Emit("A4D|AA|" .. t .. "|", aout) end
        if #gout > 0 then Emit("A4D|G|" .. t .. "|", gout) end
    end
    if A4D_COST_DIRTY then A4D_COST_DIRTY = false A4D_BSEEN = {} end      -- requote next second, written only if changed
    FightSet(pos_all, attacks)
end

-- game events: kills and finished upgrades, with their context table flattened
local function Ref(v)
    local id = try(Entity_GetID, v)
    if id ~= nil then return "e" .. s(id) end
    id = try(Squad_GetID, v)
    if id ~= nil then return "s" .. s(id) end
    id = try(Player_GetID, v)
    if id ~= nil then return "p" .. s(id) end
    if type(v) == "table" and type(v.x) == "number" and type(v.z) == "number" then return num(v.x) .. ":" .. num(v.z) end
    id = try(BP_GetName, v)
    if type(id) == "string" then return "b" .. id end
    return "?"
end
local function EventLine(tag, c)
    local parts = {}
    if type(c) == "table" then
        for k, v in pairs(c) do
            local tv, val = type(v), nil
            if tv == "number" or tv == "boolean" or tv == "string" then val = tostring(v)
            elseif tv == "userdata" or tv == "table" then
                val = Ref(v)
            else val = tv end
            table.insert(parts, Sanitize(tostring(k)) .. "=" .. Sanitize(val))
        end
    end
    print("A4D|" .. tag .. "|" .. num(GameTime()) .. "|" .. table.concat(parts, ";"))
end
function A4D_OnKill(c)
    local ok, err = pcall(EventLine, "K", c)
    if not ok then print("A4D|KERR|" .. Sanitize(err)) end
end
function A4D_OnUpgrade(c)
    A4D_COST_DIRTY = true
    A4D_EC_ALL = 2                  -- tier upgrades swap blueprints in place: every entity re-reads for 2 s
    local ok, err = pcall(EventLine, "U", c)
    if not ok then print("A4D|KERR|" .. Sanitize(err)) end
end

-- hits and projectiles (v9): many per second in big fights, so buffered per game time and written in chunks when the
-- time moves on (and at stop); records stay short (ids and numbers)
A4D_EV = {H = {}, PF = {}, PL = {}, AB = {}, I = {}, BI = {}}
A4D_EV_T = nil
A4D_HERR = 0
local function EvId(v)
    if v == nil then return "0" end
    local id = try(Entity_GetID, v)
    if id ~= nil then return s(id) end
    return "0"
end
function A4D_EvFlush()
    if A4D_EV_T == nil then return end
    local t = string.format("%.2f", A4D_EV_T)
    for _, k in ipairs({"H", "PF", "PL", "AB", "I", "BI"}) do
        if #A4D_EV[k] > 0 then
            Emit("A4D|" .. k .. "|" .. t .. "|", A4D_EV[k])
            A4D_EV[k] = {}
        end
    end
end
local function EvPush(k, rec)
    local t = GameTime()
    if t ~= A4D_EV_T then
        A4D_EvFlush()
        A4D_EV_T = t
    end
    local b = A4D_EV[k]
    b[#b + 1] = rec
end
local function HErr(err)
    A4D_HERR = A4D_HERR + 1
    if A4D_HERR <= 20 then print("A4D|HERR|" .. Sanitize(err)) end
end
local function d2(v)
    if type(v) == "number" then return string.format("%.2f", v) end
    return ""
end
function A4D_OnHit(c)
    local ok, err = pcall(function()
        EvPush("H", EvId(c.attacker) .. "," .. EvId(c.victim) .. "," .. d2(c.damage) .. "," .. d2(c.currentHealth)
            .. "," .. d2(c.shieldDamage) .. "," .. (c.isRepairing and "1" or "0"))      -- v18: shield damage, repair tick
    end)
    if not ok then HErr(err) end
end
local function ProjRec(c)
    local tg = c.target
    local id = EvId(tg)
    local x, z = "", ""
    if id == "0" and tg ~= nil then                     -- a ground position (table or userdata with x / z)
        local okp, px, pz = pcall(function() return tg.x, tg.z end)
        if okp and type(px) == "number" and type(pz) == "number" then x, z = num(px), num(pz) end
    end
    return EvId(c.attacker) .. "," .. EvId(c.projectile) .. "," .. id .. "," .. x .. "," .. z
end
function A4D_OnFired(c)
    local ok, err = pcall(function() EvPush("PF", ProjRec(c)) end)
    if not ok then HErr(err) end
end
function A4D_OnLanded(c)
    local ok, err = pcall(function() EvPush("PL", ProjRec(c)) end)
    if not ok then HErr(err) end
end

-- v18 (owner 2026-11-12: "add those events so it's more accurate"; the events bigmanjohn's recorder listens to, MIT):
--   A4D|UQ|t|key=value;...   GE_UpgradeStart (research queued, resources paid) - exact start instead of done - research time
--   A4D|UX|t|...             GE_UpgradeCancelled (also fires, player executer, as an upgrade completes)
--   A4D|C|t|... / CS / CW / CX   GE_ConstructionComplete / Start (foundation placed) / WorkerStart (first builder) / Cancelled
--   A4D|SP|t|...             GE_StrategicPointChanged (sacred sites, trade posts ...)
--   A4D|I|t|player,food,wood,gold,stone;...   GE_PlayerAddResource: every credit (gathering drop-off, trickle, refund)
--   A4D|BI|t|player,bp,squad,building;...     GE_BuildItemComplete: a produced squad (building = the producer if the
--                                             context names one, else 0); A4D|BIK|keys of the first contexts
A4D_PIDX = nil
local function PIdx(p)
    if A4D_PIDX == nil then
        A4D_PIDX = {}
        for k = 1, (try(World_GetPlayerCount) or 0) do
            local id = try(Player_GetID, World_GetPlayerAt(k))
            if id ~= nil then A4D_PIDX[id] = k end
        end
    end
    local id = try(Player_GetID, p)
    return id ~= nil and A4D_PIDX[id] or 0
end
local function SqId(v)
    if v == nil then return "0" end
    return s(try(Squad_GetGameID, v) or try(Squad_GetID, v) or 0)
end
A4D_CTX = {UQ = "GE_UpgradeStart", UX = "GE_UpgradeCancelled", C = "GE_ConstructionComplete", CS = "GE_ConstructionStart",
           CW = "GE_ConstructionWorkerStart", CX = "GE_ConstructionCancelled", SP = "GE_StrategicPointChanged"}
function A4D_CtxHandler(tag)
    return function(c)
        local ok, err = pcall(EventLine, tag, c)
        if not ok then print("A4D|KERR|" .. Sanitize(err)) end
        if tag == "UX" or tag == "UQ" then A4D_COST_DIRTY = true end
    end
end
function A4D_OnIncome(c)
    local ok, err = pcall(function()
        local r = c.resources
        if type(r) ~= "table" then return end
        local v, any = {}, false
        for i, nm in ipairs({"food", "wood", "gold", "stone"}) do
            local a = r[nm]
            if type(a) == "number" and a ~= 0 then v[i] = d2(a) any = true else v[i] = "0" end
        end
        if any then EvPush("I", PIdx(c.player) .. "," .. table.concat(v, ",")) end
    end)
    if not ok then HErr(err) end
end
A4D_BIK_LEFT = 3
function A4D_OnBuilt(c)
    local ok, err = pcall(function()
        if A4D_BIK_LEFT > 0 and type(c) == "table" then
            A4D_BIK_LEFT = A4D_BIK_LEFT - 1
            local ks = {}
            for k, v in pairs(c) do table.insert(ks, tostring(k) .. ":" .. type(v)) end
            print("A4D|BIK|" .. Sanitize(table.concat(ks, ",")))
        end
        local bp = try(BP_GetName, c.pbg) or "?"
        local prod = c.producer or c.building or c.entity or c.source
        EvPush("BI", PIdx(c.player) .. "," .. Sanitize(bp) .. "," .. SqId(c.spawnedSquad) .. "," .. EvId(prod))
    end)
    if not ok then HErr(err) end
end

-- ability events (dump v12, owner 2026-11-11: Prelate inspiration, berserking, palings, volley, stances ...): every global
-- event whose name has "Abilit" in it (A4D|GE lists all GE_* names once) -> A4D|AB|t|event,caster,ability,target;...
-- caster / target = entity id, or s<squad game id>; ability = blueprint name. The context's field names are not known yet:
-- the first A4D_ABK_LEFT events print every field (A4D|ABK|event|key=type:value,...)
A4D_ABK_LEFT = 16
local function AnyId(v)
    if v == nil then return "0" end
    local id = try(Entity_GetID, v)
    if id ~= nil then return s(id) end
    local sq = try(Squad_GetGameID, v) or try(Squad_GetID, v)
    if sq ~= nil then return "s" .. s(sq) end
    if type(v) == "number" then return s(v) end
    return "0"
end
local function BpName(v)
    if v == nil then return "" end
    local n = try(BP_GetName, v)
    if n ~= nil then return tostring(n) end
    if type(v) == "string" then return v end
    return ""
end
A4D_AB_REPEAT = A4D_AB_REPEAT or 1.0
A4D_ABR = {}             -- key event,caster,ability,target -> {n, first, last}
function A4D_AbRepFlush(t, all)
    local out = {}
    for key, r in pairs(A4D_ABR) do
        local ended = t - r.last > A4D_AB_REPEAT
        if r.n > 0 and (ended or all) then
            table.insert(out, key .. "," .. r.n .. "," .. string.format("%.2f", r.first) .. "," .. string.format("%.2f", r.last))
            r.n, r.first = 0, r.last
        end
        if ended then A4D_ABR[key] = nil end
    end
    if #out > 0 then Emit("A4D|ABR|" .. num(t) .. "|", out) end
end
function A4D_AbilityHandler(evname)
    local short = string.gsub(evname, "^GE_", "")
    return function(c)
        local ok, err = pcall(function()
            if A4D_ABK_LEFT > 0 and type(c) == "table" then
                A4D_ABK_LEFT = A4D_ABK_LEFT - 1
                local f = {}
                for k, v in pairs(c) do
                    local sv = (type(v) == "table" or type(v) == "userdata") and (AnyId(v) ~= "0" and AnyId(v) or BpName(v)) or tostring(v)
                    table.insert(f, tostring(k) .. "=" .. type(v) .. ":" .. string.gsub(tostring(sv), "[|;,\n]", "_"))
                end
                print("A4D|ABK|" .. short .. "|" .. table.concat(f, ","))
            end
            local caster = c.caster or c.executer or c.squad or c.entity or c.source or c.owner
            local ab = c.ability or c.abilityBlueprint or c.ability_pbg or c.blueprint or c.pbg
            local tg = c.target or c.targetEntity or c.targetSquad or c.victim
            local key = short .. "," .. AnyId(caster) .. "," .. string.gsub(BpName(ab), "[|;,]", "_") .. "," .. AnyId(tg)
            local now = GameTime()
            local r = A4D_ABR[key]
            if r ~= nil and now - r.last <= A4D_AB_REPEAT then     -- v20: a repeat: counted, written in the ABR run
                if r.n == 0 then r.first = now end
                r.n, r.last = r.n + 1, now
                return
            end
            if r ~= nil and r.n > 0 then A4D_AbRepFlush(now) end
            A4D_ABR[key] = {n = 0, first = now, last = now}
            EvPush("AB", key)
        end)
        if not ok then HErr(err) end
    end
end
A4D_AB_HANDLERS = {}

-- terrain height grid (for the camera footprint), once
local function Terrain()
    if type(World_GetHeightAt) ~= "function" or type(World_GetWidth) ~= "function" then return end
    local W, L, step = World_GetWidth(), World_GetLength(), 4
    local cols, rows = math.floor(W / step), math.floor(L / step)
    local x0, z0 = -W / 2 + step / 2, -L / 2 + step / 2
    print("A4D|HMH|" .. num(x0) .. "|" .. num(z0) .. "|" .. step .. "|" .. cols .. "|" .. rows)
    for row = 0, rows - 1 do
        local v = {}
        for c = 0, cols - 1 do v[c + 1] = num(try(World_GetHeightAt, x0 + c * step, z0 + row * step)) end
        print("A4D|HM|" .. row .. "|" .. table.concat(v, ","))
    end
end

-- where land units can stand, once (terrain doesn't change): per tile of the height grid
--   A4D|PCAPS|cell=0/1|cover=0/1|spawn=<method or none>
--   A4D|PCV|i|name                 cover type names, numbered as they first appear
--   A4D|PG|row|cell:cover:d,...     d = distance from the tile centre to the nearest position a
--     villager could be placed (World_GetSpawnablePosition & co.; 0 = standable, large = cliff/water)
local function Pos(x, z)
    local y = try(World_GetHeightAt, x, z) or 0
    if type(World_Pos) == "function" then return try(World_Pos, x, y, z) end
    return {x = x, y = y, z = z}
end
local function SpawnFn()
    local vil = nil
    local p1 = World_GetPlayerAt(1)
    local eg = try(Player_GetAllEntities, p1)
    for i = 1, (eg and try(EGroup_Count, eg) or 0) do
        local e = try(EGroup_GetEntityAt, eg, i)
        if e ~= nil and try(Entity_IsOfType, e, "worker") == true then vil = e; break end
    end
    if vil == nil then return nil end
    local bp = try(Entity_GetBlueprint, vil)
    local here = try(Entity_GetPosition, vil)
    local cands = {
        {"World_GetSpawnablePosition(pos,e)", function(q) return World_GetSpawnablePosition(q, vil) end},
        {"World_GetSpawnablePosition(pos,bp)", function(q) return World_GetSpawnablePosition(q, bp) end},
        {"Entity_CalculatePassableSpawnPosition(e,pos)", function(q) return Entity_CalculatePassableSpawnPosition(vil, q) end},
        {"Entity_CalculatePassableSpawnPosition(bp,pos)", function(q) return Entity_CalculatePassableSpawnPosition(bp, q) end},
        {"Entity_CalculatePassableSpawnPosition(pos,e)", function(q) return Entity_CalculatePassableSpawnPosition(q, vil) end},
    }
    for i = 1, #cands do
        local ok, r = pcall(cands[i][2], here)
        if ok and type(r) ~= "nil" and type(r.x) == "number" then return cands[i][1], cands[i][2] end
    end
    return nil
end
-- v13 (owner 2026-11-12: "the game should have a way to define where the water is"): tiles a villager cannot stand on are
-- probed again with a fishing boat's blueprint - a boat placeable there (distance <= 2.5) = water. Field 4 of A4D|PG cells.
-- v14: every tile is probed with the boat (a villager AND a boat placeable = shallows / ford).
A4D_BOAT_PROBE = A4D_BOAT_PROBE or false
local NAVAL_BPS = {"unit_naval_fishing_boat_2_eng", "unit_naval_fishing_boat_2_fre", "unit_naval_fishing_boat_2_hre",
    "unit_naval_fishing_boat_2_chi", "unit_naval_fishing_boat_2_abb", "unit_naval_fishing_boat_2_byz", "unit_naval_fishing_boat_lan"}
local function NavalFn()
    local nb = nil
    for i = 1, #NAVAL_BPS do
        local ok, b = pcall(BP_GetEntityBlueprint, NAVAL_BPS[i])
        if ok and b ~= nil then nb = b; break end
    end
    if nb == nil then return nil end
    local cands = {
        function(q) return World_GetSpawnablePosition(q, nb) end,
        function(q) return Entity_CalculatePassableSpawnPosition(nb, q) end,
    }
    -- v15: river2 (v14) had naval=1 but no result on any tile - the first error / result of each form is printed once
    local told = {}
    return function(q)
        for i = 1, #cands do
            local ok, r = pcall(cands[i], q)
            if not told[i] then
                told[i] = true
                print("A4D|PNAV|" .. i .. "|" .. tostring(ok) .. "|" .. Sanitize(tostring(r)) .. "|" .. type(r))
            end
            if ok and r ~= nil and type(r.x) == "number" then return r end
        end
        return nil
    end
end
local function Pass()
    if type(World_GetWidth) ~= "function" then return end
    local W, L, step = World_GetWidth(), World_GetLength(), 4
    local cols, rows = math.floor(W / step), math.floor(L / step)
    local x0, z0 = -W / 2 + step / 2, -L / 2 + step / 2
    local sname, sfn = SpawnFn()
    -- owner 2026-11-12: no boat check for now (river2: it found nothing; the 3D page's terrain method is good enough) -
    -- A4D_BOAT_PROBE = true brings it back
    local nfn = A4D_BOAT_PROBE and NavalFn() or nil
    local hasCell = type(World_GetTerrainCellType) == "function"
    local hasCover = type(Terrain_GetCoverType_AsString) == "function"
    print("A4D|PCAPS|cell=" .. (hasCell and 1 or 0) .. "|cover=" .. (hasCover and 1 or 0) .. "|spawn=" .. (sname or "none") .. "|naval=" .. (nfn and 1 or 0))
    if not (hasCell or hasCover or sfn) then return end
    local cv, ncv = {}, 0
    for row = 0, rows - 1 do
        local v = {}
        for c = 0, cols - 1 do
            local x, z = x0 + c * step, z0 + row * step
            local q = Pos(x, z)
            local cell = hasCell and try(World_GetTerrainCellType, q) or nil
            local cover = nil
            if hasCover then
                local nm = try(Terrain_GetCoverType_AsString, q)
                if nm ~= nil then
                    nm = Sanitize(nm)
                    if cv[nm] == nil then
                        ncv = ncv + 1; cv[nm] = ncv
                        print("A4D|PCV|" .. ncv .. "|" .. nm)
                    end
                    cover = cv[nm]
                end
            end
            local d = nil
            if sfn ~= nil then
                local ok, r = pcall(sfn, q)
                if ok and r ~= nil and type(r.x) == "number" then d = math.sqrt((r.x - x) ^ 2 + (r.z - z) ^ 2) end
            end
            local dn = nil
            -- v14 (owner 2026-11-12: "a check on: can a fishing boat and a villager go there?"): every tile, not only blocked
            -- ones - shallows / fords are walkable, so v13 never probed them
            if nfn ~= nil then
                local r2 = nfn(q)
                if r2 ~= nil then dn = math.sqrt((r2.x - x) ^ 2 + (r2.z - z) ^ 2) end
            end
            v[c + 1] = s(cell) .. ":" .. s(cover) .. ":" .. (d and string.format("%.0f", d) or "") .. (dn and (":" .. string.format("%.0f", dn)) or "")
        end
        print("A4D|PG|" .. row .. "|" .. table.concat(v, ","))
    end
end

-- footprints: size of each blueprint once, heading of each building once
--   A4D|S|bp|radius|collisionRadius      A4D|BH|id|heading (x,z of the facing vector)
A4D_SIZE, A4D_HEAD = {}, {}
function A4D_SizeOf(e, bp, id, building)
    if bp ~= nil and A4D_SIZE[bp] == nil then
        A4D_SIZE[bp] = true
        print("A4D|S|" .. Sanitize(bp) .. "|" .. num(try(Entity_GetRadius, e)) .. "|" .. num(try(Entity_GetCollisionRadius, e)))
    end
    if building and id ~= nil and A4D_HEAD[id] == nil then
        A4D_HEAD[id] = true
        local h = try(Entity_GetHeading, e)
        if type(h) == "table" and type(h.x) == "number" then
            print("A4D|BH|" .. s(id) .. "|" .. string.format("%.3f", h.x) .. "|" .. string.format("%.3f", h.z))
        end
    end
end

-- replay speed: A4D_Speed(32) in the console; prints the old and new rate
function A4D_Speed(n)
    local old = try(Game_GetSimRate) or try(Misc_GetSimRate)
    local ok = pcall(Game_SetSimRate, n) or pcall(Misc_SetSimRate, n)
    print("A4D|SPEED|" .. s(old) .. "|" .. s(try(Game_GetSimRate) or try(Misc_GetSimRate)) .. "|" .. (ok and "ok" or "failed"))
end

function A4D_Stop()
    if A4D_STOPPED then return end
    A4D_STOPPED = true
    Rule_Remove(A4D_Collect)
    pcall(Rule_Remove, A4D_Perf)
    if A4D_LIGHT_VIEW then pcall(Sound_SetForceSilence, false); pcall(Camera_SetInputEnabled, true) end
    pcall(Rule_Remove, A4D_Fast)
    pcall(Rule_RemoveGlobalEvent, A4D_OnKill)
    pcall(Rule_RemoveGlobalEvent, A4D_OnUpgrade)
    pcall(Rule_RemoveGlobalEvent, A4D_OnHit)
    pcall(Rule_RemoveGlobalEvent, A4D_OnFired)
    pcall(Rule_RemoveGlobalEvent, A4D_OnLanded)
    pcall(Rule_RemoveGlobalEvent, A4D_OnIncome)
    pcall(Rule_RemoveGlobalEvent, A4D_OnBuilt)
    for _, h in ipairs(A4D_AB_HANDLERS) do pcall(Rule_RemoveGlobalEvent, h) end
    pcall(A4D_EvFlush)
    if A4D_AbRepFlush ~= nil then pcall(A4D_AbRepFlush, GameTime(), true) end
    print("A4D|STOP")
end

function A4D_ApiList()
    local names = {}
    for k, v in pairs(_G) do
        if type(k) == "string" and type(v) == "function" then table.insert(names, k) end
    end
    table.sort(names)
    print("A4D|APICOUNT|" .. #names)
    for i = 1, #names, 40 do
        local chunk = {}
        for j = i, math.min(i + 39, #names) do table.insert(chunk, names[j]) end
        print("A4D|API|" .. table.concat(chunk, ","))
    end
    print("A4D|IO|" .. type(io))
end

print("A4D|V|21")
A4D_Caps()
print("A4D|NMODE|delta")
pcall(A4D_ApiList)
pcall(Terrain)
local okp, errp = pcall(Pass)
if not okp then print("A4D|PERR|" .. Sanitize(errp)) end
if type(Rule_AddGlobalEvent) == "function" then
    if GE_EntityKilled ~= nil then pcall(Rule_AddGlobalEvent, A4D_OnKill, GE_EntityKilled) end
    if GE_UpgradeComplete ~= nil then pcall(Rule_AddGlobalEvent, A4D_OnUpgrade, GE_UpgradeComplete) end
    -- v9: which of these exist is in A4D|EVCAPS
    local caps = {}
    local list = {{"GE_DamageReceived", A4D_OnHit}, {"GE_ProjectileFired", A4D_OnFired}, {"GE_ProjectileLanded", A4D_OnLanded},
                  {"GE_PlayerAddResource", A4D_OnIncome}, {"GE_BuildItemComplete", A4D_OnBuilt}}       -- v18: income, built
    -- v19: Rule_AddGlobalEvent takes only functions stored under a global name (v18's closures all came back =0,
    -- as in the fight tests): each context handler lives in A4D_Ev_<tag>
    local ctags = {}
    for tag in pairs(A4D_CTX) do table.insert(ctags, tag) end
    table.sort(ctags)
    for _, tag in ipairs(ctags) do
        local gname = "A4D_Ev_" .. tag
        _G[gname] = A4D_CtxHandler(tag)
        table.insert(list, {A4D_CTX[tag], _G[gname], gname})
    end
    for _, e in ipairs(list) do
        local ge = _G[e[1]]
        local ok, err = false, "no " .. e[1]
        if ge ~= nil then ok, err = pcall(Rule_AddGlobalEvent, e[2], ge) end
        if ok and e[3] ~= nil then table.insert(A4D_AB_HANDLERS, e[2]) end
        caps[#caps + 1] = e[1] .. "=" .. (ok and "1" or ("0(" .. Sanitize(tostring(err)) .. ")"))
    end
    -- v12: every GE_* name once; register the ability ones
    local ges = {}
    for k, v in pairs(_G) do
        if type(k) == "string" and string.sub(k, 1, 3) == "GE_" then table.insert(ges, k) end
    end
    table.sort(ges)
    print("A4D|GE|" .. table.concat(ges, ","))
    for _, k in ipairs(ges) do
        if string.find(k, "Abilit", 1, true) and type(_G[k]) == "number" then
            local gname = "A4D_Ev_" .. k
            _G[gname] = A4D_AbilityHandler(k)
            local ok, err = pcall(Rule_AddGlobalEvent, _G[gname], _G[k])
            if ok then table.insert(A4D_AB_HANDLERS, _G[gname]) end
            caps[#caps + 1] = k .. "=" .. (ok and "1" or ("0(" .. Sanitize(tostring(err)) .. ")"))
        end
    end
    print("A4D|EVCAPS|" .. table.concat(caps, "|"))
end
-- v17 (owner 2026-11-12: "why don't we remove the part that makes it slower? we don't need the visualization"): rendering
-- cannot be switched off from script, and the game advances at most one sim tick per rendered frame - so each frame is made
-- cheap instead: sound silenced, camera input off, camera parked over a map corner, zoomed in and looking straight down
-- (almost nothing to draw). Camera / sound are local, not part of the simulation, so the replay plays out the same.
-- Each call is tried separately and reported: A4D|LV|name|ok.
function A4D_LightView()
    local W, L = try(World_GetWidth) or 400, try(World_GetLength) or 400
    local corner = Pos(-W / 2 + 6, -L / 2 + 6)
    local steps = {
        {"silence", function() Sound_SetForceSilence(true) end},
        {"camInputOff", function() Camera_SetInputEnabled(false) end},
        {"camMove", function() Camera_MoveTo(corner) end},
        {"camZoom", function() Camera_SetZoomDist(1) end},
        {"camDecl", function() Camera_SetDeclination(89) end},
    }
    for i = 1, #steps do
        local ok, e = pcall(steps[i][2])
        print("A4D|LV|" .. steps[i][1] .. "|" .. (ok and "ok" or Sanitize(tostring(e))))
    end
end
-- speed check: rendered frames and wall frames every 10 game seconds (record.py turns them into fps / speed)
A4D_PERF_NEXT = 0
function A4D_Perf()
    local t = GameTime() or 0
    if t < A4D_PERF_NEXT then return end
    A4D_PERF_NEXT = t + 10
    print("A4D|PERF|" .. num(t) .. "|" .. s(try(Game_GetRenderFrameCount)) .. "|" .. s(try(Game_GetAppFrameNumber)))
end
Rule_AddInterval(A4D_Collect, 1)
Rule_AddInterval(A4D_Fast, A4D_FAST)
pcall(Rule_AddInterval, A4D_Perf, 1)
if A4D_LIGHT_VIEW then pcall(A4D_LightView) end
print("A4D|READY|" .. num(GameTime()))
if A4D_AUTO_SPEED ~= nil then A4D_Speed(A4D_AUTO_SPEED) end

]==]
-- typed into a UI console: hand the code to the game's script state; already in it (or no
-- Scar_DoString): run it here, in the caller's environment
if type(Scar_DoString) == "function" then
    Scar_DoString(A4D_SRC)
else
    assert(load(A4D_SRC, "dump.lua", "t", _ENV))()
end
