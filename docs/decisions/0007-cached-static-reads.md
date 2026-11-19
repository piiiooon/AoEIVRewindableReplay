# 0007: Cache values that only change on known triggers in the recorder

Date: 2026-11-15

## Decision

dump.lua caches per entity id the blueprint, kind (worker / military / other), squad id and a building's position and
heading, and re-reads them only when they can change:
- an upgrade finished (GE_UpgradeComplete): every entity, for the next 2 seconds;
- the entity gained or lost a squad (Mongol buildings packing / unpacking);
- a building was under construction the second before;
- otherwise every 30 s (A4D_STATIC_EVERY), staggered by id.
Villagers' gather flags stop at the first resource type found. `record.py --full-read` reads everything every second.
State-model cadence and the building reads stay as they were (the rest of the `lighter-recorder` branch, decision 0006
there, is not on master).

## Why

Owner: keep the safe part of the lighter recorder. Checked on all 24 recorded games (work/*.timeline.json):
- 1,155 in-place blueprint changes, almost all tier upgrades (spearman_2 -> spearman_3 ...), each within 1.5 s of an
  upgrade-finished event;
- the others: palisade -> gate while the wall is still being placed (under construction), Mongol buildings packing /
  unpacking (they gain / lose a squad), Shinto landmark monk -> monk (no event; up to 30 s late);
- squad ids change only for Mongol buildings that pack again (3 cases), always with the squad gained / lost.
Unit type and building positions never changed except in those cases.

## Consequences

- Shinto landmark monks (Japanese) show the landmark-monk blueprint for up to 30 s after they become plain monks; any
  other in-place change without an upgrade event, not seen in the 24 games, would also be up to 30 s late.
- Log format unchanged (dump v21).
- Not yet run in the game with these triggers; the earlier 5 s variant (branch) recorded correctly.
