-- Fight probe (owner 2026-11-10): do the game's spawn / command / formation calls work from our console?
-- Run by tools/fight_probe.py in a dev skirmish (you + 1 AI). Prints A4D|FP|... lines into warnings.log:
--   A4D|FP|FN|name=0/1,...              which of the calls exist
--   A4D|FP|AI|k|off/failed              the AI switched off
--   A4D|FP|BP|name|ok/none              squad blueprint lookups
--   A4D|FP|SPAWN|player|bp|ok/err|squad id / error
--   A4D|FP|CMD|name|ok/err              attack-move orders (first working variant)
--   A4D|FP|FORM|...                     formation calls (what they return)
--   A4D|FP|S|t|squad,side,count,x,z,hp,hpmax,heading,A;...  the spawned squads every A4D_FP_EVERY s (default 0.125 = every tick) for A4D_FP_SECS
--   A4D|FP|H|t|attacker,victim,damage,hp-after   hits (GE_DamageReceived), first 300
--   A4D|FP|END
-- Set by fight_probe.py before loading: A4D_FP_BP (squad blueprint name or nil = try a list), A4D_FP_N (squads a side),
-- A4D_FP_GAP (map units between the two groups), A4D_FP_SECS.

local function try(f, ...)
    if type(f) ~= "function" then return nil end
    local ok, v = pcall(f, ...)
    if ok then return v end
    return nil
end
local function s(v) return v == nil and "" or tostring(v) end
local function num(v) return type(v) == "number" and string.format("%.1f", v) or "" end
local function P(...) print("A4D|FP|" .. table.concat({...}, "|")) end

local names = {"Squad_CreateAndSpawnToward", "Squad_CreateAndSpawnTowardCheat", "BP_GetSquadBlueprint", "SGroup_Create",
    "SGroup_Add", "Cmd_AttackMove", "Cmd_FormationAttackMove", "Cmd_Move", "Formation_GetDimensionsAndOffset",
    "Squad_SetMovingFormationOverride", "Squad_SetIdleFormationOverride", "Squad_GetPosition", "Squad_GetID",
    "Squad_GetGameID", "Squad_EntityAt", "Squad_Count", "Entity_GetHealth", "Entity_GetPosition", "Entity_GetID",
    "World_Pos", "World_GetHeightAt", "Player_GetStartingPosition", "AI_Enable", "AI_IsAIPlayer",
    "LocalCommand_SquadSetCombatStance", "Squad_IsAttacking"}
local have = {}
for _, n in ipairs(names) do have[#have + 1] = n .. "=" .. (type(_G[n]) == "function" and "1" or "0") end
P("FN", table.concat(have, ","))

-- players: me (not AI) and the other; the AI switched off
local np = try(World_GetPlayerCount) or 0
local pl = {}
for k = 1, np do
    local p = World_GetPlayerAt(k)
    pl[#pl + 1] = p
    if try(AI_IsAIPlayer, p) then
        P("AI", k, (pcall(AI_Enable, p, false) and "off" or "failed"))
    end
end
if #pl < 2 then P("ERR", "need 2 players") P("END") return end

-- where: halfway between the two starting positions (else the map centre), the groups A4D_FP_GAP apart
local function pos(x, z) local y = try(World_GetHeightAt, x, z) or 0 return World_Pos(x, y, z) end
local a, b = try(Player_GetStartingPosition, pl[1]), try(Player_GetStartingPosition, pl[2])
local cx, cz = 0, 0
local dx, dz = 1, 0
if a and b then
    cx, cz = (a.x + b.x) / 2, (a.z + b.z) / 2
    local L = math.sqrt((b.x - a.x) ^ 2 + (b.z - a.z) ^ 2)
    if L > 0 then dx, dz = (b.x - a.x) / L, (b.z - a.z) / L end
end
local gap = A4D_FP_GAP or 24
local pa, pb = pos(cx - dx * gap / 2, cz - dz * gap / 2), pos(cx + dx * gap / 2, cz + dz * gap / 2)
P("WHERE", num(cx), num(cz), num(dx), num(dz), gap)

-- a squad blueprint
local tries = A4D_FP_BP and {A4D_FP_BP} or {"unit_spearman_2_fre", "unit_spearman_1_fre", "unit_spearman_2_eng",
    "unit_spearman_1_eng", "unit_spearman_2_hre", "unit_spearman_2", "unit_spearman_1"}
local sbp, sbpname
for _, n in ipairs(tries) do
    local bp = try(BP_GetSquadBlueprint, n)
    P("BP", n, bp ~= nil and "ok" or "none")
    if bp ~= nil and sbp == nil then sbp, sbpname = bp, n end
end
if sbp == nil then P("ERR", "no squad blueprint found") P("END") return end

-- spawn A4D_FP_N squads a side, facing each other
local sq = {}
local ids = {{}, {}}      -- squad ids per side: the watch re-finds squads by id
local function spawn(p, at, toward, k)
    local variants = {
        {"Squad_CreateAndSpawnToward", function() return Squad_CreateAndSpawnToward(sbp, p, 0, at, toward) end},
        {"Squad_CreateAndSpawnTowardCheat", function() return Squad_CreateAndSpawnTowardCheat(sbp, p, 0, at, toward) end},
    }
    for _, v in ipairs(variants) do
        if type(_G[v[1]]) == "function" then
            local ok, r = pcall(v[2])
            if ok and r ~= nil then
                local id = try(Squad_GetID, r) or try(Squad_GetGameID, r)
                P("SPAWN", k, sbpname, v[1], "ok", s(id))
                return r
            end
            P("SPAWN", k, sbpname, v[1], "err", s(r))
        end
    end
end
for k, side in ipairs({{pl[1], pa, pb}, {pl[2], pb, pa}}) do
    sq[k] = {}
    for i = 1, (A4D_FP_N or 3) do
        local r = spawn(side[1], side[2], side[3], k)
        if r then sq[k][#sq[k] + 1] = r end
        if r then ids[k][#ids[k] + 1] = try(Squad_GetID, r) end
    end
end

-- attack-move both groups at each other: first variant that works
for k, target in ipairs({pb, pa}) do
    local sg = try(SGroup_Create, "a4d_fp_" .. k .. "_" .. math.floor((try(World_GetGameTime) or 0) * 1000))
    for _, q in ipairs(sq[k]) do pcall(SGroup_Add, sg, q) end
    local done = false
    for _, v in ipairs({
        {"Cmd_AttackMove(sg,pos)", function() Cmd_AttackMove(sg, target) end},
        {"Cmd_AttackMove(sg,pos,false)", function() Cmd_AttackMove(sg, target, false) end},
        {"Cmd_FormationAttackMove(sg,pos)", function() Cmd_FormationAttackMove(sg, target) end},
    }) do
        if not done then
            local ok, err = pcall(v[2])
            P("CMD", k, v[1], ok and "ok" or "err", ok and "" or s(err))
            done = ok
        end
    end
    local ok, r1, r2, r3 = pcall(Formation_GetDimensionsAndOffset, sg)
    P("FORM", k, ok and "ok" or "err", s(r1), type(r1) == "table" and table.concat((function()
        local t = {} for kk, vv in pairs(r1) do t[#t + 1] = tostring(kk) .. "=" .. tostring(vv) end return t end)(), ";") or "",
        s(r2), s(r3))
end

-- watch them for A4D_FP_SECS
local t0 = try(World_GetGameTime) or 0
function A4D_FP_Watch()
    -- per squad (Squad_EntityAt doesn't exist in this build): position, health, max health, heading, attacking
    local t = try(World_GetGameTime) or 0
    local rec, alive = {}, 0
    for k = 1, 2 do
        for _, id in ipairs(ids[k]) do
            local q = nil
            if id ~= nil and try(Squad_IsValid, id) == true then q = try(Squad_FromID, id) end
            if q ~= nil and try(Squad_IsAlive, q) == false then q = nil end
            local n = q and (try(Squad_Count, q) or 0) or 0
            local p = n > 0 and try(Squad_GetPosition, q) or nil
            local h = n > 0 and try(Squad_GetHeading, q) or nil
            local hs = ""
            if type(h) == "table" or type(h) == "userdata" then
                local ok, hx, hz = pcall(function() return h.x, h.z end)
                if ok then hs = num(hx) .. ":" .. num(hz) end
            end
            if p then alive = alive + 1 end
            local px, pz = "", ""
            if p then px, pz = num(p.x), num(p.z) end
            if n > 0 then
                rec[#rec + 1] = table.concat({s(id), k, s(n), px, pz, num(try(Squad_GetHealth, q)),
                    num(try(Squad_GetHealthMax, q)), hs, (try(Squad_IsAttacking, q, 1) and "A" or "")}, ",")
            else
                rec[#rec + 1] = s(id) .. "," .. k .. ",0"
            end
        end
    end
    P("S", string.format("%.2f", t - t0), table.concat(rec, ";"))
    if t - t0 >= (A4D_FP_SECS or 30) or alive == 0 then
        pcall(Rule_Remove, A4D_FP_Watch)
        pcall(Rule_RemoveGlobalEvent, A4D_FP_Hit)
        P("END")
    end
end
-- hits during the probe (the dump v9 event): first 300, to see that they fire and what they carry
A4D_FP_NH = 0
function A4D_FP_Hit(c)
    if A4D_FP_NH >= 300 then return end
    A4D_FP_NH = A4D_FP_NH + 1
    local function id(v) local i = try(Entity_GetID, v) return i ~= nil and tostring(i) or "0" end
    local ok, err = pcall(function()
        P("H", string.format("%.2f", (try(World_GetGameTime) or 0) - t0), id(c.attacker), id(c.victim), num(c.damage),
          num(c.currentHealth))
    end)
    if not ok then P("HERR", s(err)) end
end
if not A4D_FP_HITS then P("EV", "GE_DamageReceived", "not listened (A4D_FP_HITS off)")
elseif GE_DamageReceived ~= nil then P("EV", "GE_DamageReceived", pcall(Rule_AddGlobalEvent, A4D_FP_Hit, GE_DamageReceived) and "ok" or "err")
else P("EV", "GE_DamageReceived", "missing") end
Rule_AddInterval(A4D_FP_Watch, A4D_FP_EVERY or 0.125)   -- 0.125 s = every sim tick
