# Fogline observer read (2D viewer): map geometry, gold read, food forecast, castle timing, command rings

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Map geometry (dump v7, owner 2026-10-24: "terrain doesn't move"; not yet run in the game)
Impassable terrain (cliffs, deep water: where land units can't stand) and real footprints, both pages.
- Once at start, per tile of the height grid: World_GetTerrainCellType, Terrain_GetCoverType_AsString
  (names numbered by A4D|PCV) and the distance from the tile centre to the nearest spot a villager could
  be placed (first working of World_GetSpawnablePosition / Entity_CalculatePassableSpawnPosition
  signatures; A4D|PCAPS names it). A4D|PG|row|cell:cover:d,... One hitch at load (owner: acceptable).
- A4D|S|bp|radius|collisionRadius once per blueprint (buildings, tracked map objects); A4D|BH|id|hx|hz
  heading per building once (recorded, unused: squares only).
- analyzer/mapgeo.py: blocked = spawn point moved > BLOCK_D 2.5 and not under a start object (its
  footprint + one ring; units / unsized objects: within 3); water vs cliff by cover name.
  First real v7/v8 log (replay_252595969, 2026-10-25): collision radius empty; Entity_GetRadius 2 (house,
  camps, farm), 4 (barracks / range / stable), 6 (TC, landmarks, blacksmith, market, monastery, gold /
  stone mine), 4 (small mines), 1 (berry bush); cell type empty, one cover type (tp_defcover) on that map.
  Footprint = r / 2 + 1 tiles (calibrated: adjacent houses / farms 8 apart = 2 tiles, military 3 tiles with
  centres on tile centres, TC-class 4 tiles; mines block 4x4 at the start). Centres: even sides on tile
  corners, odd on tile centres (all recorded buildings at x, z = 0 or 2 mod 4). Older logs: dots.
  Walls and aqueducts (owner 2026-10-25: not grid-tight) skip the grid and are drawn as lines (wallLines(),
  wallKind(), both pages): each piece joined to its 2 nearest pieces of the same owner and kind. Palisade =
  brown line with a player-colour outline (2 units, min 2 px, link 7); stone wall = thicker grey line, no outline
  (3.5 units, min 3 px, link 7); Byzantine aqueduct (joins cisterns) = thin grey line, 1.5 px at any zoom, no
  outline (link 12). Gates: twice the width in their wall's style, GATE_LEN 6 units along the wall.
- Viewer: "Impassable" toggle (Fogline), cached terrain layer (fights); buildings / mines / berries as
  tile squares (type mark or icon inside when > 18 px); trees stay dots.
- Gather rate: one number per villager per second; default 0.40 (owner, 2026-10-23; was 0.51). Parked:
  calibrated income per assumed villager from calm stretches of other games, minus raid losses seen
  (villagers killed / garrisoned while the observer's army is there), with an uncertainty band.
- Opponent read is gold-first (owner, 2026-10-24: one gather rate for the total bank is bad in practice,
  e.g. game1 true income/villager 0.57-0.94): implied gold = start gold + mined from mines seen (remaining
  amount at each look, minus own mining) - gold seen spent (units/buildings/landmarks), floor 0 (deficit =
  mined out of sight), stops at both Castle; gold villagers seen (now / last window); true gold under review.
  Read selector (owner, 2026-10-25): Gold (default) / Bank (rough) / Castle timing, one at a time, remembered
  in localStorage "fogline.read"; Gold disabled when the log has no mine amounts.
  "Their techs (review)" toggle (owner, 2026-10-24; hidden info, off by default): analyzer/techs_bought.py
  reads the U events (owner = executer's owner; paid = done - research time; age-ups skipped), costs from
  data/upgrades.json (aoe4world technologies + upgrades by attribName, per civ code; commit ce8f375);
  gold_est_tech = same model minus that gold (own deficit/floor). Viewer lists paid->done, name, gold.
  game1 (U events): P2 Rus bought 510 g of techs by 11:00 (survival, wheelbarrow, hardened spear, ranged
  dmg/armor); P1 OotD 575 g (survival, inspired warriors, veteran archers) + 3 outpost springalds (no
  cost entry). P2-on-P1 residual after techs (~+500 at 12-14 min) = own mining: Rus mined 0.64 g per
  villager-second on its own mine, the model subtracts 0.40, the excess is credited to P1 (shared-mine
  term). Fix offered, not built: own true gold income split over own miners.
- `analyzer/gather.py`: villager resource label from position (still + within reach of a node,
  farm or sheep; walking keeps the label 30 s). Reach distances are first guesses.
- `analyzer/counter.py`: ideal army vs the enemy army seen in the last 60 s, for the observer's
  own army value; Lanchester matchup from data/units.json (dps with bonus damage and armor,
  HP). Own civ, current age, tiers already fielded. No range, upgrades, micro.
- Maps (Fogline and fights): wheel zooms at the cursor, drag pans, double-click / Reset view returns to
  the whole map; symbols keep their screen size; Fogline army groups split as you zoom in.
  Rotation: Rotate menu (Game view 45 deg default = the in-game camera, which looks toward +x,+z;
  North up; 90 deg steps), Shift+drag turns freely, compass top right (click = north up); stored in
  localStorage "fogline.rot", shared by both pages. Map code passes (x, z) to both px and pz.
## Food forecast (analyzer/food.py; owner's definition)
Safety score of a food spot for P vs O = base + aura + arrival, each in [-1, 1]; safe when > 0.
- base (static): TC distances, (dO - dP)/(dO + dP), +0.5 within TC_COVER of P's main TC.
- aura (static radius AURA_R): army groups (scouts excluded), value-weighted, linear falloff;
  (P - O)/(P + O + AURA_V0).
- arrival (dynamic): O's main army vs P's defence (main army or main TC), (dE - dD)/(dE + dD), scaled by
  O's share of main-army value; worsens as O closes in.
Constants (TC_COVER 40, AURA_R 60, AURA_V0 200) are guesses. Observer knowledge only: opponent TC once
seen (before: mirror of own TC, labelled), army seen in the last 60 s, node amounts at last look,
consumption = gatherers seen x rate (carried forward), or measured between looks. Event when safe food
runs out within 90 s.
Active / potential (owner, 2026-10-23): they eat the safest food first unless scouted otherwise.
Active = sheep seen (last 30 s, 200 each) + carcasses within 40 of their TC + their TC berry group
(assumed at the reflection of the observer's own TC berries through the two TCs, own starting amount,
until any of it is scouted). Potential = other scouted groups that score safe, best first; "next" = the
safest. Consumption: max(food gatherers seen in 30 s, 0.5 x estimated villagers, labelled assumed),
minus those seen on farms or potential spots. Event: active runs out within 90 s, naming the next spot.
Active parts are running estimates drained by the assumed eating (sheep, carcasses, TC berries in that
order), reset by a full look (a partial look can only lower them). When active is gone the eating
spills to the safest scouted group ("current", sticky while it has food and scores safe), then the
next; per-spot assumed eating restarts at each new look. One warning per group.
Unsafe but taken: their gatherers seen (30 s) on a group scoring <= 0 -> row["risky"], "!" on the map,
one event per group. test5: two brief borderline cases only (scores -0.05 / -0.03).
Review check (Show true values / Everything only): true active food (all their sheep, carcasses at their
true TC, TC berries) and what their food gatherers really are on (berry / carcass / deer / boar / sheep /
farm), per row as row["true"]. test5: true active far above the estimate early (unseen sheep); P2 really
ate carcasses + berries while the model put "now?" on deer/boar.
test5 (P2 on P1): TC berries tracked 913/951, 753/797, 27/0 (est/true at 12:04, 13:04, 15:04).
test5 (P2 on P1, older model): TC berries projected 618 at 15:04 (true 473 at 14:00, 0 at 15:00); warning at 12:49
and 14:09: 1-2 min early (the 50% share times an overestimated villager count).
test5 check (P2 sight on P1): west berries scored unsafe (-0.06..-0.36) 5:00-9:00 while P2's army camped
there and P1 ate TC carcasses instead (+2.3..+2.6); safe once the army left (11:00-14:00, P1 gathered
them); P1's move to far-west berries at ~15:00 followed depletion of the west berries (0 left at 15:00),
not the army. No food warning fired (10-15k natural food left).
## Command rings (Fogline; owner 2026-10-25)
replay.acts(): every command with receivers; categories move / attack / gather / build / garrison (ORDER_TYPES),
queue (types 3, 16: production / research at a building), cancel (5), rally (12, 22), other. export_view maps
squads to entity ids at that second -> D.acts {p: [[t, cat, ids]]}. The receivers are ringed for ACT_S 1.5 s in
the category colour with a label ("Command rings" toggle); sight view: own player only, Everything: both.
Selection itself is not in the replay. test5: 4,205 commands (move 2,260, attack 559, queue 430, ...).
Command box under the map (owner): the latest commands (up to 5, last 20 s; within ACT_S bold, older faded):
player, time, category, receivers as icon x count per type (name when no icons), "n gone" if not in the frame.

## Castle timing (analyzer/castle.py; owner 2026-10-25)
Reference = plain landmark-cost math (owner's 1c): forward sim in 2 s steps from the implied bank:
income rate x villagers (0.40, owner: "for now"), villagers keep coming from every known TC (50 food /
20 s), Feudal landmark when affordable (unless seen / announced) + its build time, then Castle landmark
when affordable + build time (aoe4world per-civ landmark times in data/production.json: 190/220 standard,
OotD 152/176). Projected = from the implied bank as is; reference = same with the off-path spending seen
added back; delay = projected - reference (lower bound: unseen spending delays more). Off path: military
units, military / defensive buildings, walls, blacksmith, market, religious, extra TCs; on path:
villagers, houses, drop sites, farms, docks, landmarks, first TC. A military unit with none of its
producers seen implies the cheapest producer (data/production.json producedBy), unless a civ landmark can
make it. Per item: seconds = cost / income when seen. Viewer: "Their Castle timing" (projected / reached,
delay + straight-path time, off-path total, item chips, implied dashed); log lines "Castle +N s: ...".
game1: P1 sight on Rus +2:20 by 10:00 (knights, archers, stable, implied range + blacksmith); P2 sight on
OotD projected 9:37 a minute before the real 7:43 (0.40 too low for OotD, true ~0.73-0.94).
