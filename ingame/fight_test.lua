-- Scripted test fight (owner 2026-11-10: calibrate the fight simulator against the game itself). Run by
-- tools/fight_tests.py in a dev skirmish (you + 1 AI, AI switched off). One test per load:
--   A4D_FT = {id = "t01", sides = {{{"unit_spearman_2_fre", 1}}, {{"unit_spearman_2_fre", 1}}}, gap = 24,
--             secs = 60, every = 0.125, jx = 0, jz = 0, up = {{}, {"upgrade_melee_damage_i"}}}
-- Squads are spawned per side in rows across the line between the starting positions (list order = front to back,
-- up to 6 a row, SPACING apart), facing the other side, then both sides attack-move at each other.
-- Lines (A4D|FT|...; t = seconds since the orders):
--   START|id|cx|cz|dx|dz|gap                     where (the axis runs from side 1 to side 2)
--   UP|side|name|ok/err                          upgrades given before the fight
--   U|squad|side|bp|entity                       each spawned squad and its (first) entity id (hits name entities)
--   S|t|squad,side,count,x,z,hp,hpmax,hx:hz,A;... every A4D_FT.every s; count 0 = dead / gone
--   FORM|t|side|x|y                              the group's formation size every second (Formation_GetDimensionsAndOffset)
--   H|t|attacker,victim,damage,hp;...            every hit (GE_DamageReceived): entity ids, damage dealt, victim HP after
--   PF / PL|t|attacker,projectile,target,x,z;... projectiles fired / landed (target 0 = ground shot at x, z)
--   CMD|side|am/fam/move|ok/err               the order given
--   CAST|t|side|ability|signature|ok/err         ability casts (C.cast, group A buff tests); AB|t|event,caster   ability events
--   END|id|t|reason                              one side gone / time; the survivors are then removed (clean next test)
--   ERR|message
-- Squads are only touched through their ids (Squad_IsValid / Squad_FromID / Squad_IsAlive): a handle to a destroyed
-- squad crashed the game in the first probe.

local function try(f, ...)
    if type(f) ~= "function" then return nil end
    local ok, v = pcall(f, ...)
    if ok then return v end
    return nil
end
local function s(v) return v == nil and "" or tostring(v) end
local function num(v) return type(v) == "number" and string.format("%.2f", v) or "" end
local function P(...) print("A4D|FT|" .. table.concat({...}, "|")) end
local C = A4D_FT or {}
local SPACING = C.spacing or 2.5
local ROW = 6

local function stop_all(reason, t)
    pcall(Rule_Remove, A4D_FT_Watch)
    pcall(Rule_RemoveGlobalEvent, A4D_FT_Hit)
    pcall(Rule_RemoveGlobalEvent, A4D_FT_Fired)
    pcall(Rule_RemoveGlobalEvent, A4D_FT_Landed)
    for _, f in ipairs(A4D_FT_AbFns or {}) do pcall(Rule_RemoveGlobalEvent, f) end
    if A4D_FT_Flush then A4D_FT_Flush() end
    P("END", s(C.id), num(t), reason)
    for k = 1, 2 do
        for _, id in ipairs((A4D_FT_IDS or {{}, {}})[k]) do
            if try(Squad_IsValid, id) == true then
                local q = try(Squad_FromID, id)
                if q ~= nil then pcall(Squad_Destroy, q) end
            end
        end
        if not C.keep then
            for _, u in ipairs((C.up or {})[k] or {}) do
                local bp = try(BP_GetUpgradeBlueprint, u)
                if bp then pcall(Player_RemoveUpgrade, A4D_FT_PL[k], bp) end
            end
        end
    end
end

-- players (AI off)
local pl = {}
for k = 1, (try(World_GetPlayerCount) or 0) do
    local p = World_GetPlayerAt(k)
    pl[#pl + 1] = p
    if try(AI_IsAIPlayer, p) then pcall(AI_Enable, p, false) end
end
-- side 1 = you (owner 2026-11-11: the test units did not always spawn on his side - player order is not "you first"):
-- the local player (Game_GetLocalPlayer), else the first human; side 2 = the other one. ME|side-1 player|how
do
    local me = try(Game_GetLocalPlayer)
    local how = "local"
    if me == nil then
        for _, p in ipairs(pl) do if try(AI_IsAIPlayer, p) == false then me = p how = "human" break end end
    end
    if me ~= nil then
        local mid = try(Player_GetID, me)
        for i, p in ipairs(pl) do
            if p == me or (mid ~= nil and try(Player_GetID, p) == mid) then
                table.remove(pl, i) table.insert(pl, 1, p) break
            end
        end
    else how = "order" end
    P("ME", s(try(Player_GetID, pl[1])), how)
end
A4D_FT_PL = pl
if #pl < 2 then P("ERR", "need 2 players") P("END", s(C.id), "0", "no players") return end

-- civ / age check (owner 2026-11-11: units spawn as the owning player's civ - French arbaletriers for a Sengoku player came out
-- as an unknown unit without Pavise; civ abilities need that civ, some an age): CIV|side|race|age|wanted; a mismatch on side 1
-- is an ERR line (the run still goes on)
for k = 1, 2 do
    local race = s(try(Player_GetRaceName, pl[k]))
    local age = s(try(Player_GetCurrentAge, pl[k]) or try(Player_GetAge, pl[k]))
    P("CIV", k, race, age, k == 1 and s(C.civ) or "")
    if k == 1 and C.civ and not race:find(C.civ, 1, true) then P("ERR", "side 1 is " .. race .. ", this test wants " .. C.civ) end
end

-- the axis: halfway between the starting positions, plus the jitter
local a, b = try(Player_GetStartingPosition, pl[1]), try(Player_GetStartingPosition, pl[2])
local cx, cz, dx, dz = 0, 0, 1, 0
if a and b then
    cx, cz = (a.x + b.x) / 2, (a.z + b.z) / 2
    local L = math.sqrt((b.x - a.x) ^ 2 + (b.z - a.z) ^ 2)
    if L > 0 then dx, dz = (b.x - a.x) / L, (b.z - a.z) / L end
end
cx, cz = cx + (C.jx or 0), cz + (C.jz or 0)
-- sacred site tests (owner 2026-11-12: "it's hard to find those events in games, so let's do the tests"): C.site = true centres
-- the test on the sacred site nearest the axis centre (the map needs sacred sites); SITE|id|x|z|bp, or ERR
A4D_FT_SITE = nil
if C.site then
    local eg = nil
    local ok1, r1 = pcall(function() return World_GetAllNeutralEntities() end)
    if ok1 and r1 ~= nil then eg = r1 end
    if eg == nil then
        pcall(function() eg = EGroup_CreateIfNotFound("a4d_ft_neutral"); EGroup_Clear(eg); World_GetAllNeutralEntities(eg) end)
    end
    local best, bd = nil, nil
    local function look(g)
        for i = 1, (g and (try(EGroup_Count, g) or 0) or 0) do
            local e = try(EGroup_GetEntityAt, g, i)
            local bp = e and try(BP_GetName, try(Entity_GetBlueprint, e)) or ""
            if string.find(bp, "holy_site", 1, true) or string.find(bp, "sacred_site", 1, true) then
                local q = try(Entity_GetPosition, e)
                if q then
                    local d = (q.x - cx) ^ 2 + (q.z - cz) ^ 2
                    if bd == nil or d < bd then best, bd = {e = e, x = q.x, z = q.z, bp = bp, id = try(Entity_GetID, e)}, d end
                end
            end
        end
    end
    -- owner 2026-11-12: run 2 found no site - a captured site belongs to the player, it is not neutral any more. The site of
    -- the first run is kept for the session (A4D_FT_SITE_ID, the Lua state lives on between runs); else the neutral objects,
    -- else both players' entities
    if A4D_FT_SITE_ID and try(Entity_IsValid, A4D_FT_SITE_ID) == true then
        local e = try(Entity_FromID, A4D_FT_SITE_ID)
        local q = e and try(Entity_GetPosition, e)
        if q then best = {e = e, x = q.x, z = q.z, bp = s(try(BP_GetName, try(Entity_GetBlueprint, e))), id = A4D_FT_SITE_ID} end
    end
    if not best then look(eg) end
    if not best then
        for k = 1, 2 do look(try(Player_GetEntities, pl[k])) end
    end
    if best then A4D_FT_SITE_ID = best.id end
    if best then
        A4D_FT_SITE = best
        cx, cz = best.x, best.z
        P("SITE", s(best.id), num(best.x), num(best.z), best.bp)
    else
        P("ERR", "no sacred site on this map")
    end
end
local gap = C.gap or 24
local px, pz = -dz, dx                       -- across the axis
P("START", s(C.id), num(cx), num(cz), num(dx), num(dz), num(gap))
local function pos(x, z) return World_Pos(x, try(World_GetHeightAt, x, z) or 0, z) end

-- clean slate (owner 2026-11-11: the AI had researched blacksmith +1 attack): every generic combat upgrade in
-- ingame/fight_clean.lua (written by tools/fight_tests.py) is removed from both players; CLEAN|side|names they had
do
    local f = loadfile and loadfile((C.clean or "") ~= "" and C.clean or "")
    if f then pcall(f) end
    for k = 1, 2 do
        local had = {}
        for _, u in ipairs(A4D_FT_CLEAN or {}) do
            local bp = try(BP_GetUpgradeBlueprint, u)
            if bp ~= nil and try(Player_HasUpgrade, pl[k], bp) == true then
                pcall(Player_RemoveUpgrade, pl[k], bp)
                had[#had + 1] = u
            end
        end
        P("CLEAN", k, #(A4D_FT_CLEAN or {}), table.concat(had, ","))
    end
end

for _, u in ipairs(C.rm or {}) do
    local bp = try(BP_GetUpgradeBlueprint, u)
    local had = bp ~= nil and try(Player_HasUpgrade, pl[1], bp) == true
    local ok = bp ~= nil and pcall(Player_RemoveUpgrade, pl[1], bp)
    P("RM", 1, u, had and "had" or "-", ok and "ok" or "err")
end
-- upgrades
for k = 1, 2 do
    for _, u in ipairs((C.up or {})[k] or {}) do
        local bp = try(BP_GetUpgradeBlueprint, u)
        local ok = bp ~= nil and pcall(Player_CompleteUpgrade, pl[k], bp)
        P("UP", k, u, ok and "ok" or "err")
    end
end

-- spawn: side 1 at -gap/2, side 2 at +gap/2 along the axis; rows across it, front row nearest the enemy
A4D_FT_IDS = {{}, {}}
A4D_FT_ENT = {}
A4D_FT_BP = {}
A4D_FT_SQ = {}
local sgs = {}
for k = 1, 2 do
    local sign = k == 1 and -1 or 1
    local list = {}
    for _, e in ipairs((C.sides or {})[k] or {}) do
        for _ = 1, e[2] do list[#list + 1] = e[1] end
    end
    sgs[k] = try(SGroup_Create, "a4d_ft_" .. k .. "_" .. math.floor((try(World_GetGameTime) or 0) * 1000))
    local face = pos(cx - sign * dx * gap, cz - sign * dz * gap)
    for i, name in ipairs(list) do
        local W = (C.rows or {})[k] or ROW          -- units per row (1 = a single-file column along the axis)
        local row, col = math.floor((i - 1) / W), (i - 1) % W
        local nrow = math.min(W, #list - row * W)
        local off = (col - (nrow - 1) / 2) * SPACING
        local along = sign * (gap / 2 + row * SPACING)
        if A4D_FT_SITE and (C.on or {})[k] then along = sign * (1.5 + row * SPACING) end   -- on the site's aura
        local at = pos(cx + dx * along + px * off, cz + dz * along + pz * off)
        local sbp = try(BP_GetSquadBlueprint, name)
        if sbp == nil then P("ERR", "no squad blueprint " .. name)
        else
            local ok, q = pcall(Squad_CreateAndSpawnToward, sbp, pl[k], 0, at, face)
            if ok and q ~= nil then
                local id = try(Squad_GetID, q)
                local e = try(Squad_GetFirstEntity, q)
                local eid = e and try(Entity_GetID, e)
                A4D_FT_IDS[k][#A4D_FT_IDS[k] + 1] = id
                if id then A4D_FT_BP[id] = name A4D_FT_SQ[id] = k end
                if eid then A4D_FT_ENT[eid] = k end
                pcall(SGroup_Add, sgs[k], q)
                P("U", s(id), k, name, s(eid), s(e and try(Entity_GetRadius, e)))  -- radius: the area-damage distance check
            else
                P("ERR", "spawn " .. name .. ": " .. s(q))
            end
        end
    end
end

-- events: buffered per game time, written when the time moves on (as dump v9)
local buf = {H = {}, PF = {}, PL = {}}
local buf_t = nil
local t0 = nil
function A4D_FT_Flush()
    if buf_t == nil then return end
    for _, k in ipairs({"H", "PF", "PL"}) do
        local b = buf[k]
        local i = 1
        while i <= #b do
            local j = math.min(#b, i + 40)
            P(k, string.format("%.3f", buf_t - (t0 or buf_t)), table.concat(b, ";", i, j))
            i = j + 1
        end
        buf[k] = {}
    end
end
local function push(k, rec)
    local t = try(World_GetGameTime) or 0
    if t ~= buf_t then A4D_FT_Flush() buf_t = t end
    buf[k][#buf[k] + 1] = rec
end
local function eid(v) local i = v ~= nil and try(Entity_GetID, v) or nil return i ~= nil and tostring(i) or "0" end
function A4D_FT_Hit(c)
    pcall(function() push("H", eid(c.attacker) .. "," .. eid(c.victim) .. "," .. num(c.damage) .. "," .. num(c.currentHealth)) end)
end
local function shot(k, c)
    pcall(function()
        local id = eid(c.target)
        local x, z = "", ""
        if id == "0" and c.target ~= nil then
            local ok, tx, tz = pcall(function() return c.target.x, c.target.z end)
            if ok and type(tx) == "number" then x, z = num(tx), num(tz) end
        end
        push(k, eid(c.attacker) .. "," .. eid(c.projectile) .. "," .. id .. "," .. x .. "," .. z)
    end)
end
function A4D_FT_Fired(c) shot("PF", c) end
function A4D_FT_Landed(c) shot("PL", c) end
if GE_DamageReceived ~= nil then pcall(Rule_AddGlobalEvent, A4D_FT_Hit, GE_DamageReceived) end
if GE_ProjectileFired ~= nil then pcall(Rule_AddGlobalEvent, A4D_FT_Fired, GE_ProjectileFired) end
if GE_ProjectileLanded ~= nil then pcall(Rule_AddGlobalEvent, A4D_FT_Landed, GE_ProjectileLanded) end

-- orders: cmd "am" = Cmd_AttackMove (default), "fam" = Cmd_FormationAttackMove (owner 2026-11-10: with the plain
-- order the probe's groups lined up along the axis, flank to flank, not facing each other), "move" = Cmd_Move for side 1
-- only (no enemy: base walking speed, no charge)
-- per side: C.orders = {"am", "hold"} overrides cmd for that side ("hold" = Cmd_HoldPosition: a target blob that
-- stays put for the splash tests); C.inv = {1} makes those sides invulnerable (the siege survives to keep shooting)
local cmd = C.cmd or "am"
-- manual tests (owner 2026-11-11: "provide the units and I press them"): C.wait = s before any order, so the owner can select
-- side 1 and use the ability himself; the AB lines record what he cast. WAIT|s line at the start.
local function give_orders()
    for k = 1, 2 do
        local sign = k == 1 and -1 or 1
        local target = pos(cx - sign * dx * gap, cz - sign * dz * gap)
        if #A4D_FT_IDS[k] > 0 then
            local o = (C.orders or {})[k] or cmd
            local ok, err
            if o == "none" then ok = true
            elseif o == "hold" then ok, err = pcall(Cmd_HoldPosition, sgs[k])
            else
                local f = o == "fam" and Cmd_FormationAttackMove or o == "move" and Cmd_Move or Cmd_AttackMove
                ok, err = pcall(f, sgs[k], target)
            end
            P("CMD", k, o, ok and "ok" or ("err " .. s(err)))
        end
    end
end
local orders_given = false
A4D_FT_GO = 0
if C.wait == "cast" or (tonumber(C.wait) or 0) > 0 then P("WAIT", s(C.wait)) else give_orders() orders_given = true end
for _, k in ipairs(C.inv or {}) do
    local ok, err = pcall(SGroup_SetInvulnerable, sgs[k], true)
    P("INV", k, ok and "ok" or ("err " .. s(err)))
end
-- C.held = player side that holds the site at the start (instant capture: the decapture tests)
if A4D_FT_SITE and C.held then
    local ok, err = pcall(Entity_InstantCaptureStrategicPoint, A4D_FT_SITE.e, pl[C.held])
    if not ok then ok, err = pcall(Entity_InstantCaptureStrategicPoint, pl[C.held], A4D_FT_SITE.e) end
    P("HELD", s(C.held), ok and "ok" or ("err " .. s(err)))
end
t0 = try(World_GetGameTime) or 0
local last_form = -1
-- C.steps = {{at = s, side = k, go = "site" / "away"}}: move a side onto the site / 40 units away from it (outward along
-- the axis) at that time; STEP|t|side|go|ok
local step_i = 1
local function steps_tick(t)
    local L = C.steps or {}
    while step_i <= #L and t >= (L[step_i].at or 0) do
        local st = L[step_i]
        local k = st.side or 1
        local sign = k == 1 and -1 or 1
        local tx, tz = cx, cz
        if st.go == "away" then tx, tz = cx + sign * dx * 40, cz + sign * dz * 40 end
        local ok, err = pcall(Cmd_Move, sgs[k], pos(tx, tz))
        P("STEP", string.format("%.3f", t), k, s(st.go), ok and "ok" or ("err " .. s(err)))
        step_i = step_i + 1
    end
end
-- site state: SS|t|owner side (0 none)|progress side1:side2|near side1:side2|secure count|gold side1:side2 (the trickle)
local function v2(f, a, b)
    if type(f) ~= "function" then return nil end
    local ok, v = pcall(f, a, b)
    if ok and v ~= nil then return v end
    ok, v = pcall(f, b, a)
    if ok then return v end
    return nil
end
local function sv(v) if v == true then return "1" elseif v == false then return "0" elseif type(v) == "number" then return string.format("%.3f", v) end return "" end
local site_next = 0
local function site_tick(t)
    if not A4D_FT_SITE or t < site_next then return end
    site_next = t + 0.5
    local e = A4D_FT_SITE.e
    local owner, prog, near, gold = 0, {}, {}, {}
    for k = 1, 2 do
        if owner == 0 and v2(Entity_IsStrategicPointCapturedBy, e, pl[k]) == true then owner = k end
        prog[k] = sv(v2(Player_GetStrategicPointCaptureProgress, pl[k], e))
        near[k] = sv(v2(Player_HasCapturingSquadNearStrategicPoint, pl[k], e))
        gold[k] = sv(try(Player_GetResource, pl[k], RT_Gold))
    end
    local pmax = 0
    for k = 1, 2 do pmax = math.max(pmax, math.abs(tonumber(prog[k]) or 0)) end
    A4D_FT_SSLAST = {owner = owner, prog = pmax}
    P("SS", string.format("%.3f", t), owner, table.concat(prog, ":"), table.concat(near, ":"),
      sv(try(Entity_GetStrategicPointSecureCount, e)), table.concat(gold, ":"))
end

-- scripted micro for side 1 (orb walking tests, owner 2026-11-10): C.kite = {mode = "afterfire", move = s} - after each
-- shot fired, move sideways for `move` s then attack again; {mode = "interrupt", wait = s} - order the attack, move away
-- `wait` s later (before the shot if the aim is longer), attack again after 1 s. Lines: KITE|t|attack/move|ok|distance
local K = C.kite
local kstate, kuntil, kfired = "attack", 0, 0
local kite_n = 0
local function sq_pos(k)
    local id = A4D_FT_IDS[k][1]
    local q = id and try(Squad_IsValid, id) == true and try(Squad_FromID, id) or nil
    return q and try(Squad_GetPosition, q) or nil
end
local function kite_order(what, t)
    -- owner 2026-11-10: the first version stepped 2 units back every move and lost the target out of range; now the
    -- archer circles the target at the same distance (one way round) and re-attacks with an attack-move at
    -- the target's current position
    local ok, err = false, "no position"
    local me, tg = sq_pos(1), sq_pos(2)
    local d = (me and tg) and math.sqrt((me.x - tg.x) ^ 2 + (me.z - tg.z) ^ 2) or nil
    if what == "attack" then
        if tg then ok, err = pcall(Cmd_AttackMove, sgs[1], pos(tg.x, tg.z)) end
    elseif me and tg and d and d > 0 then
        kite_n = kite_n + 1
        local side = 1                            -- owner: keep circling the static target one way round
        local atan2 = math.atan2 or math.atan     -- Lua 5.1 has atan2; 5.3+ takes two arguments in atan
        local ang = atan2(me.z - tg.z, me.x - tg.x) + side * 4 / d
        ok, err = pcall(Cmd_Move, sgs[1], pos(tg.x + d * math.cos(ang), tg.z + d * math.sin(ang)))
    end
    P("KITE", string.format("%.3f", t), what, ok and "ok" or ("err " .. s(err)), d and string.format("%.2f", d) or "")
end
local nfired = 0
local base_fired = A4D_FT_Fired
function A4D_FT_Fired(c)
    base_fired(c)
    local a = c.attacker ~= nil and try(Entity_GetID, c.attacker)
    if a and A4D_FT_ENT[a] == 1 then nfired = nfired + 1 end
end
if K then
    pcall(Rule_RemoveGlobalEvent, base_fired)
    if GE_ProjectileFired ~= nil then pcall(Rule_AddGlobalEvent, A4D_FT_Fired, GE_ProjectileFired) end
end
-- ability casts (owner 2026-11-11, buff test group A): C.cast = {{side = 1, ab = "longbow_rate_of_fire_ability",
-- at = 0 or "hit" (side's first damage dealt / taken), target = "self" / "pos" / "enemy", again = s (recast every s)}}.
-- The SCAR signature is unconfirmed: each form is tried in turn and the first that does not error is kept (CAST line names
-- it); GE_Ability* events, when they exist, log AB lines - the proof the cast happened.
local CASTS = C.cast or {}
local confirmed = {}
local cast_sig = nil
local first_hit = {}
local base_hit = A4D_FT_Hit
-- (first-hit tracking and the ability events also run for manual tests)
function A4D_FT_Hit(c)
    base_hit(c)
    pcall(function()
        local t = (try(World_GetGameTime) or 0) - (t0 or 0)
        for _, v in ipairs({c.attacker, c.victim}) do
            local k = v ~= nil and A4D_FT_ENT[try(Entity_GetID, v)]
            if k and not first_hit[k] then first_hit[k] = t end
        end
    end)
end
if (#CASTS > 0 or C.manual) and GE_DamageReceived ~= nil then
    pcall(Rule_RemoveGlobalEvent, base_hit)
    pcall(Rule_AddGlobalEvent, A4D_FT_Hit, GE_DamageReceived)
end
local function group_pos(k)
    local sx, sz, n = 0, 0, 0
    for _, id in ipairs(A4D_FT_IDS[k]) do
        local q = try(Squad_IsValid, id) == true and try(Squad_FromID, id) or nil
        local p = q and try(Squad_GetPosition, q)
        if p then sx, sz, n = sx + p.x, sz + p.z, n + 1 end
    end
    return n > 0 and pos(sx / n, sz / n) or nil
end
local function cast(c, t)
    local k = c.side or 1
    local abp = try(BP_GetAbilityBlueprint, c.ab)
    if abp == nil then P("CAST", string.format("%.3f", t), k, c.ab, "-", "err no ability blueprint") return end
    pcall(Player_SetAbilityAvailability, pl[k], abp, ITEM_UNLOCKED)
    local tg = nil
    if c.target == "pos" then tg = group_pos(k) elseif c.target == "enemy" then tg = sgs[3 - k] end
    -- caster group: only the squads of c.unit (owner 2026-11-11: a04 khan + horse archers crashed the game - the cast
    -- now goes to the khan alone)
    local who = sgs[k]
    if c.unit then
        A4D_FT_N = (A4D_FT_N or 0) + 1
        who = try(SGroup_Create, "a4d_ft_cast_" .. k .. "_" .. math.floor((try(World_GetGameTime) or 0) * 1000) .. "_" .. A4D_FT_N)
        for _, id in ipairs(A4D_FT_IDS[k]) do
            if A4D_FT_BP[id] == c.unit and try(Squad_IsValid, id) == true then
                local q = try(Squad_FromID, id)
                if q then pcall(SGroup_Add, who, q) end
            end
        end
    end
    P("CASTPRE", string.format("%.3f", t), k, c.ab, s(c.unit), tg and "target" or "no target")
    local forms = {
        {"sg,ab", function() return Cmd_Ability(who, abp) end},
        {"sg,ab,tg", function() return Cmd_Ability(who, abp, tg) end},
        {"sg,ab,tg,nil,true", function() return Cmd_Ability(who, abp, tg, nil, true) end},
        {"pl,sg,ab,tg", function() return Cmd_Ability(pl[k], who, abp, tg) end},
        {"pl,sg,ab,tg,nil,true", function() return Cmd_Ability(pl[k], who, abp, tg, nil, true) end},
    }
    if tg ~= nil then table.remove(forms, 1) end
    local eg = try(EGroup_Create, "a4d_ft_eg_" .. k .. "_" .. math.floor((try(World_GetGameTime) or 0) * 1000) .. "_" .. (A4D_FT_N or 0))
    local q1, e1 = nil, nil
    for _, id in ipairs(A4D_FT_IDS[k]) do
        if (not c.unit or A4D_FT_BP[id] == c.unit) and try(Squad_IsValid, id) == true then
            local q = try(Squad_FromID, id)
            local e = q and try(Squad_GetFirstEntity, q)
            if q and not q1 then q1, e1 = q, e end
            if e and eg then pcall(EGroup_Add, eg, e) end
        end
    end
    forms[#forms + 1] = {"sg,ab,sg", function() return Cmd_Ability(who, abp, who) end}
    if eg then forms[#forms + 1] = {"eg,ab", function() return Cmd_Ability(eg, abp) end} end
    if c._tries == nil and q1 then
        P("CANCAST", c.ab, "Squad_HasAbility=" .. s(try(Squad_HasAbility, q1, abp)),
          "Entity_HasAbility=" .. s(e1 and try(Entity_HasAbility, e1, abp)),
          "Squad_CanCastAbilityOnSquad=" .. s(try(Squad_CanCastAbilityOnSquad, q1, abp, q1)),
          "Squad_IsAbilityActive=" .. s(try(Squad_IsAbilityActive, q1, abp)),
          "Entity_IsAbilityActive=" .. s(e1 and try(Entity_IsAbilityActive, e1, abp)))
    end
    local errs = {}
    c._tries = (c._tries or 0) + 1
    for i, f in ipairs(forms) do
        if i >= (c._from or 1) and (cast_sig == nil or cast_sig == f[1] or c._tries > 1) then
            local ok, err = pcall(f[2])
            if ok then
                cast_sig = f[1]
                c._from = i + 1
                P("CAST", string.format("%.3f", t), k, c.ab, f[1], "ok", "try " .. c._tries)
                return
            end
            errs[#errs + 1] = f[1] .. ": " .. s(err)
        end
    end
    P("CAST", string.format("%.3f", t), k, c.ab, "-", "err " .. table.concat(errs, " / "):gsub("|", "/"))
end
local function cast_tick(t)
    for _, c in ipairs(CASTS) do
        local at
        if c.at == "hit" then at = first_hit[c.side or 1] else at = type(c.at) == "number" and c.at or 0 end
        if at ~= nil and t >= at and (c._next == nil or (c.again and t >= c._next)) then
            c._next = t + (c.again or 1e9)
            confirmed[(c.side or 1) .. ":" .. c.ab] = nil
            c._check = t + 1.5
            cast(c, t)
        elseif c._check and t >= c._check then
            c._check = nil
            local id = A4D_FT_IDS[c.side or 1][1]
            local q = id and try(Squad_IsValid, id) == true and try(Squad_FromID, id) or nil
            local abp = try(BP_GetAbilityBlueprint, c.ab)
            P("ACTIVE", string.format("%.3f", t), c.ab, s(q and abp and try(Squad_IsAbilityActive, q, abp)),
              "confirmed=" .. s(confirmed[(c.side or 1) .. ":" .. c.ab]))
            if not confirmed[(c.side or 1) .. ":" .. c.ab] and (c._tries or 0) < 5 and not c.noretry then
                P("CASTRETRY", string.format("%.3f", t), c.side or 1, c.ab)
                c._check = t + 1.5
                cast(c, t)
            end
        end
    end
end
-- ability events (owner's a05-a08 run registered only one GE_ name: one function can't take several events) - one closure
-- per event; only our casters are logged (a00-a03 logged every mill aura tick); AB|t|event,ability,caster
A4D_FT_AbFns = {}
A4D_FT_CAST1 = nil
local function ab_handler(ev)
    return function(c)
        pcall(function()
            local w = c.caster or c.executer or c.squad or c.entity
            local id = w ~= nil and (try(Entity_GetID, w) or try(Squad_GetID, w)) or nil
            local k = id and (A4D_FT_ENT[id] or A4D_FT_SQ[id])
            if not k then return end
            local an = s(c.ability ~= nil and try(BP_GetName, c.ability) or "")
            confirmed[k .. ":" .. an] = true          -- only the cast ability confirms (auras fire their own events)
            if k == 1 and A4D_FT_CAST1 == nil and not an:find("influence") and not an:find("aura") then
                A4D_FT_CAST1 = (try(World_GetGameTime) or 0) - (t0 or 0)
            end
            P("AB", string.format("%.3f", (try(World_GetGameTime) or 0) - (t0 or 0)), ev .. "," .. an .. "," .. s(id))
        end)
    end
end
if #CASTS > 0 or C.manual then
    local names = {}
    for name, v in pairs(_G) do
        if type(name) == "string" and name:sub(1, 3) == "GE_" and name:find("Abilit") and type(v) == "number" then
            local gname = "A4D_FT_Ab_" .. name
            _G[gname] = ab_handler(name)
            local ok, err = pcall(Rule_AddGlobalEvent, _G[gname], v)
            if ok then A4D_FT_AbFns[#A4D_FT_AbFns + 1] = _G[gname] names[#names + 1] = name
            else names[#names + 1] = name .. "(err " .. s(err):gsub("|", "/") .. ")" end
        end
    end
    P("ABEV", table.concat(names, ","))
end

local function kite_tick(t)
    if not K then return end
    if K.mode == "afterfire" then
        if kstate == "attack" and nfired > kfired then
            kfired = nfired kstate = "move" kuntil = t + (K.move or 0.75) kite_order("move", t)
        elseif kstate == "move" and t >= kuntil then
            kstate = "attack" kite_order("attack", t)
        end
    else
        if kstate == "attack" and t >= kuntil then
            kstate = "wait" kuntil = t + (K.wait or 0.25) kite_order("attack", t)
        elseif kstate == "wait" and t >= kuntil then
            kstate = "move" kuntil = t + 1.0 kite_order("move", t)
        elseif kstate == "move" and t >= kuntil then
            kstate = "attack" kuntil = t
        end
    end
end

function A4D_FT_Watch()
    A4D_FT_Flush()                               -- the hits / shots of the last tick
    local t = (try(World_GetGameTime) or 0) - t0
    if not orders_given then
        local go
        -- C.after = s between your first cast and the orders (owner 2026-11-11: palings take ~15 s to all go up -> 20)
        if C.wait == "cast" then go = A4D_FT_CAST1 ~= nil and t >= A4D_FT_CAST1 + (C.after or 0.5) or t >= 120 + (C.after or 0)
        else go = t >= (C.wait or 0) end
        if go then orders_given = true A4D_FT_GO = t P("GO", string.format("%.3f", t)) give_orders() end
    end
    kite_tick(t)
    cast_tick(t)
    steps_tick(t)
    site_tick(t)
    local rec, alive = {}, {0, 0}
    for k = 1, 2 do
        for _, id in ipairs(A4D_FT_IDS[k]) do
            local q = nil
            if try(Squad_IsValid, id) == true then q = try(Squad_FromID, id) end
            if q ~= nil and try(Squad_IsAlive, q) == false then q = nil end
            local n = q and (try(Squad_Count, q) or 0) or 0
            local p = n > 0 and try(Squad_GetPosition, q) or nil
            if p then
                alive[k] = alive[k] + 1
                local h = try(Squad_GetHeading, q)
                local hs = ""
                if h ~= nil then
                    local ok, hx, hz = pcall(function() return h.x, h.z end)
                    if ok and type(hx) == "number" then hs = string.format("%.2f:%.2f", hx, hz) end
                end
                rec[#rec + 1] = table.concat({s(id), k, s(n), num(p.x), num(p.z), num(try(Squad_GetHealth, q)),
                    num(try(Squad_GetHealthMax, q)), hs, (try(Squad_IsAttacking, q, 1) and "A" or "")}, ",")
            else
                rec[#rec + 1] = s(id) .. "," .. k .. ",0"
            end
        end
    end
    local i = 1
    while i <= #rec do
        local j = math.min(#rec, i + 30)
        P("S", string.format("%.3f", t), table.concat(rec, ";", i, j))
        i = j + 1
    end
    if math.floor(t) > last_form then
        last_form = math.floor(t)
        for k = 1, 2 do
            local ok, d = pcall(Formation_GetDimensionsAndOffset, sgs[k])
            if ok and d ~= nil then
                local okd, fx, fy = pcall(function() return d.x, d.y end)
                if okd then P("FORM", string.format("%.3f", t), k, num(fx), num(fy)) end
            end
        end
    end
    if C.until_neutral and A4D_FT_SSLAST and t > 2 and A4D_FT_SSLAST.owner == 0 and A4D_FT_SSLAST.prog < 0.001 then
        stop_all("site neutral", t)
        return
    end
    if cmd ~= "move" and not C.site and (alive[1] == 0 or alive[2] == 0) then
        stop_all(alive[1] == 0 and alive[2] == 0 and "both gone" or ("side " .. (alive[1] == 0 and 1 or 2) .. " gone"), t)
    elseif t >= (C.secs or 90) + (A4D_FT_GO or 0) then
        stop_all("time", t)
    end
end
Rule_AddInterval(A4D_FT_Watch, C.every or 0.125)
