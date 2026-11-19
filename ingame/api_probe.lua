-- Lists the game's scripting API so the dump can be extended without guessing names.
-- During a replay (game started with -dev), in the console:
--   dofile("C:/aoe4/ingame/api_probe.lua")
-- Output: A4D|API lines in warnings.log (function names, 40 per line) and one A4D|IO line.

Scar_DoString([==[
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
]==])
