-- Offline test harness for dump.lua: mocks the subset of the game's scripting API it uses.
-- Usage: lua mock_harness.lua dump.lua [full|minimal] [ticks]
local script, mode, ticks = arg[1], arg[2] or "full", tonumber(arg[3] or "3")

if mode ~= "noscar" then function Scar_DoString(src) assert(load(src))() end end
local rules = {}
events = {}
function Rule_AddInterval(f, iv) table.insert(rules, {f = f, iv = iv}) end
function Rule_Remove(f) for i = #rules, 1, -1 do if rules[i].f == f then table.remove(rules, i) end end end

local now = 0
local players = {
  {name = "Alice", civ = "english", team = 0, res = {100, 200, 50, 0}},
  {name = "Bob",   civ = "chinese", team = 1, res = {300, 150, 0, 100}},
}
local ents = {
  [1] = {{id = 11, bp = "unit_villager_1_eng", x = 10, z = 20, w = true},
         {id = 12, bp = "unit_spearman_1_eng", x = 50, z = 60, m = true}},
  [2] = {{id = 21, bp = "unit_villager_1_chi", x = 200, z = 210, w = true},
         {id = 22, bp = "building_town_center_chi", x = 205, z = 205}},
}
RT_Food, RT_Wood, RT_Gold, RT_Stone = 1, 2, 3, 4

function World_GetPlayerCount() return #players end
function World_GetPlayerAt(i) return players[i] end
function Player_GetDisplayName(p) return {LocString = p.name} end
function Player_GetRaceName(p) return p.civ end
function Player_GetTeam(p) return p.team end
function BP_GetUpgradeBlueprintByPbgID(id) return id end
function Player_HasUpgrade(_, id) return id == 129091 end
function Player_GetAllEntities(p)
  for i, q in ipairs(players) do if q == p then return ents[i] end end
end
function EGroup_GetEntityAt(g, i) if g[i] == nil then error("Invalid index " .. i) end return g[i] end
function EGroup_Count(g) return #g + 1 end  -- one stale index, as seen in game
function Entity_IsOfType(e, t) return (t == "worker" and e.w) or (t == "military" and e.m) or false end
function Entity_GetSquad(e) if e.w or e.m then return e end end
function Squad_IsIdle(sq) return sq.id == 12 end

if mode == "full" or mode == "noscar" then
  function World_GetGameTime() return now end
  function Player_GetResource(p, rt) return p.res[rt] end
  function Entity_GetID(e) return assert(e.id) end
  function Entity_GetBlueprint(e) return e.bp end
  function BP_GetName(bp) return bp end
  function Entity_GetPosition(e) return {x = e.x, y = 0, z = e.z} end
  function Player_CanSeeEntity(p, e) return p.name == "Alice" and e.id == 21 end
  function Squad_GetGameID(sq) return 500 + sq.id end
  function Squad_IsGatheringResourceType(sq, rt) return sq.w and rt == RT_Wood end
  function Squad_IsMoving(sq) return sq.m == true end
  function Entity_GetHealth(e) return 87.5 end
  function Entity_HasProductionQueue(e) return e.bp:find("town_center") ~= nil end
  function Entity_GetProductionQueueSize(e) return 2 end
  function Entity_IsUnderConstruction(e) return false end
  function Player_GetCurrentPopulation(p) return 7 end
  function Game_GetSimRate() return 8 end
  function Game_SetSimRate(n) end
  function Entity_GetRemainingResourceDepositAmount(e) return e.amt or 1234 end
  function Player_GetCurrentAge(p) return now >= 3 and p.name == "Bob" and 2 or 1 end
  gaia = {{id = 91, bp = "birch_med_wild", x = 1, z = 2}, {id = 92, bp = "resource_gold_deposit", x = 120, z = 130, amt = 1234},
          {id = 93, bp = "gaia_huntable_deer", x = 30, z = 40, amt = 350},
          {id = 95, bp = "holy_site", x = -60, z = 10, prog = {}, near = {}}}       -- v19: a sacred site
  -- strategic points: (entity, player) for the owner, (player, entity) for the rest - Try2 must find both orders
  function Entity_IsStrategicPoint(e) return e.bp == "holy_site" end
  function Entity_IsVictoryPoint(e) assert(e.bp) return e.bp == "holy_site" end
  function Entity_IsStrategicPointCapturedBy(e, p) assert(e.bp and p.name) return e.owner == p.name end
  function Player_GetStrategicPointCaptureProgress(p, e) assert(p.name and e.bp) return e.prog[p.name] or 0 end
  function Player_HasCapturingSquadNearStrategicPoint(p, e) assert(p.name and e.bp) return e.near[p.name] == true end
  function Entity_GetStrategicPointSecureCount(e) assert(e.bp) return 0 end
  function World_GetAllNeutralEntities() local g = {} for i, v in ipairs(gaia) do g[i] = v end return g end
  function Entity_FromID(id) for _, v in ipairs(gaia) do if v.id == id then return v end end
    for _, l in pairs(ents) do for _, v in ipairs(l) do if v.id == id then return v end end end end
  function Entity_IsValid(id) return Entity_FromID(id) ~= nil end
  function Entity_IsAttacking(e, _) return e.m == true end
  function Entity_GetAttackTargetEntity(e) return ents[2][1] end
  function Player_GetID(p) assert(p.name and p.civ); return 1000 end
  function World_GetWidth() return 16 end
  function World_GetLength() return 8 end
  function World_GetHeightAt(x, z) return 10 + x / 10 end
  function World_Pos(x, y, z) return {x = x, y = y, z = z} end
  RT_Food, RT_Wood, RT_Gold, RT_Stone, RT_OliveOil = 0, 1, 2, 3, 7
  function Player_GetResourceRate(p, rt) return 0.5 + rt end
  function World_GetTerrainCellType(q) return q.x > 4 and 3 or 0 end
  function Terrain_GetCoverType_AsString(q) return q.x > 4 and "deep_water" or "grass" end
  function World_GetSpawnablePosition(q, e) assert(e.id) if q.x > 4 then return {x = 2, y = 0, z = q.z} end return {x = q.x, y = 0, z = q.z} end
  function Entity_GetRadius(e) return e.bp:find("town_center") and 12.7 or 2.1 end
  function Entity_GetCollisionRadius(e) return 9 end
  function Entity_GetHeading(e) return {x = 0, y = 0, z = 1} end
  -- v21: abilities (the spearman has Trample, active from 3 s), garrison (the TC holds the villager from 2 s), a win-condition
  -- table whose timer runs from 4 s, squad headings, a squad state value
  function BP_GetAbilityBlueprint(nm) if nm == "cataphract_trample_byz" or nm == "activate_stealth_mal" then return nm end end
  function Entity_HasAbility(e, abp) return e.m == true and abp == "cataphract_trample_byz" end
  function Squad_HasAbility(sq, abp) return sq.m == true and abp == "cataphract_trample_byz" end
  function Entity_IsAbilityActive(e, abp) return now >= 3 end
  function Squad_IsDoingAbility() return false end
  function Entity_GetFilledHoldSquadSlots(e) if e.bp:find("town_center") and now >= 2 then return 1 end return 0 end
  function Entity_GetSquadsHeld(e) return {ents[2][1]} end
  function SGroup_Count(g) return #g end
  function SGroup_GetSpawnedSquadAt(g, i) return g[i] end
  ReligiousVictory = {timer = 600, active = false, players = {[1] = {sites = 0}}}
  function Squad_GetHeading(sq) return {x = 1, y = 0, z = 0} end
  function Squad_GetStateModelInt(sq, key) if key == "is_bracing" then return now >= 3 and 1 or 0 end error("no key") end
  GE_EntityKilled, GE_UpgradeComplete, GE_DamageReceived, GE_ProjectileFired, GE_ProjectileLanded = 1, 2, 3, 4, 5
  -- v19: the events dump v18 / v19 listen to (fake ids)
  GE_UpgradeStart, GE_ConstructionStart, GE_StrategicPointChanged, GE_PlayerAddResource = 7, 8, 9, 10
  GE_BuildItemComplete, GE_AbilityExecuted = 11, 12
  -- like the game: a handler must be a function stored under a global name (v18's closures were refused)
  function Rule_AddGlobalEvent(f, ge)
    local named = false
    for k, v in pairs(_G) do if v == f and type(k) == "string" then named = true break end end
    if not named then error("Rule_AddGlobalEvent: function is not a global") end
    events[ge] = f
  end
  function Rule_RemoveGlobalEvent(f) for k, g in pairs(events) do if g == f then events[k] = nil end end end
else
  -- some calls exist but throw, the rest are absent
  function Player_GetResource() error("not allowed") end
end

local function site() for _, v in ipairs(gaia or {}) do if v.id == 95 then return v end end end
dofile(script)
if A4D_Speed then A4D_Speed(32) end
for i = 1, ticks do
  for q = 1, 4 do          -- quarter seconds: 0.25 s rules every step, 1 s rules on the second
    now = now + 0.25
    for _, r in ipairs({table.unpack(rules)}) do
      if r.iv < 1 or q == 4 then r.f() end
    end
  end
  if i == 2 and gaia then   -- the deer dies (carcass appears), the mine is mined
    gaia[2].amt = 1200
    table.remove(gaia, 3)
    table.insert(gaia, {id = 94, bp = "gaia_food_deer_corpse", x = 31, z = 41, amt = 300})
  end
  if i == 5 and gaia then table.remove(gaia, 1) end   -- the tree is chopped down
  if i == 5 then table.remove(ents[1], 1) end          -- v20: Alice's villager dies (EX line)
  if i == 3 then ents[2][1].x = 52 end                 -- the villager walks next to the spearman
  if i >= 4 and ReligiousVictory then ReligiousVictory.active = true ReligiousVictory.timer = 600 - (i - 3) end   -- v21
  if i == 3 and gaia then                               -- v19: Alice's monk starts capturing the site, Bob contests it
    site().prog.Alice = 0.25
    site().near.Alice = true
    site().near.Bob = true
  end
  if i == 4 and gaia then site().owner = "Alice" site().prog.Alice = 1 site().near.Bob = nil end
  if i == 3 and events[7] then                          -- v19: context / buffered events through the named handlers
    events[7]({executer = ents[2][2], upgrade = "upgrade_wheelbarrow"})
    events[8]({entity = ents[2][2], player = players[2]})
    events[9]({entity = site(), player = players[1]})
    events[10]({player = players[1], resources = {food = 0, wood = 10, gold = 0, stone = 0}})
    events[11]({spawnedSquad = ents[1][2], pbg = "unit_spearman_1_eng", player = players[1]})
    events[12]({caster = ents[1][2], ability = "ability_test"})
    -- v20: an aura pulsing 3 more times in the same second (folded into one ABR run)
    for _ = 1, 3 do events[12]({caster = ents[2][2], ability = "aura_pulse", target = ents[2][2]}) end
  end
  if i == 4 and events[12] then events[12]({caster = ents[2][2], ability = "aura_pulse", target = ents[2][2]})
  end
  if i == 4 and events[3] then                          -- v9: two hits in one tick, a ground shot fired and landed
    events[3]({attacker = ents[1][2], victim = ents[2][1], damage = 8, currentHealth = 42})
    events[3]({attacker = ents[1][2], victim = ents[2][1], damage = 8.5, currentHealth = 33.5})
    events[4]({attacker = ents[1][2], projectile = ents[1][1], target = {x = 12.5, z = 7}})
    now = now + 0.25
    events[5]({attacker = ents[1][2], projectile = ents[1][1], target = ents[2][1]})
  end
end
if events[1] then events[1]({victim = ents[2][1], killer = ents[1][2], pos = {x = 3.5, z = 4}}) end
if events[2] then events[2]({player = players[1], upgrade = "upgrade_wheelbarrow"}) end
A4D_Stop()
