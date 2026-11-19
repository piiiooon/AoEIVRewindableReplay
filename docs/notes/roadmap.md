# Open items and roadmap (owner: later)

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Open items
- Fight review: check the measures on a v6 recording; odds ignore reinforcements (many upsets).
  Not built: grades, positional tags, eco upgrade cost, K-event killer credit.
- Food forecast: score constants are guesses; check against more games (spots players abandon or
  avoid should score < 0).
- Optimal-play tech timings: dropped by the owner (unfeasible); techs stay a known blind spot of the
  observer read (review toggle shows the true list).
- Unit icons: tools/icons.py embeds icons (aoe4world, game art) into a view file; never ship them.
- Food-depletion / timing-attack analysis beyond the forecast (parked).
## Roadmap (later; owner 2026-11-12: "we don't need them for now")
- Fight review: check the measures (odds, target choice, focus, overkill) on a v6+ recording; odds ignore reinforcements.
- Food forecast: the score constants (TC_COVER, AURA_R, AURA_V0) are guesses - check against more games.
- Fight engine (fightcal / fightsim) ON HOLD (owner 2026-11-12): calibration beyond the test batches (kiting, mixed armies, siege on
  a charging blob) and the measured poison / bleed (batch D) not in the engine yet. Not the fight recap (that one is recorded hits).
- Priority (owner 2026-11-12): complete the recorder first - every in-depth analysis (incl. sacred-site income / time held) comes
  after the recorder records everything necessary.
- Accepted loose ends (owner): uncompleted research clicks (H.techClicks) not drawn; the HUD's military-in-production row still
  uses the nearest-building rule; the Fogline tech list has no replay clicks. Recording speed drops to ~5x late game (entity
  reads): unavoidable.
- Buffs not modelled: enemy debuff auras, conditional auras (relics, sacred sites, "while attacking"), stacking limits; cistern
  bonus sizes. Sacred site capture progress units unconfirmed until a recording with a capture.
- A second reference replay with other civs (Mongol / Ottoman / Order of the Dragon auras, Kipchak / Zornhau bleeds untested).
- Branch `lighter-recorder` (2026-11-15, commit 039ac97): cached static reads, state models every 4 / 8 s, idle-building lane;
  late game 3.5x -> 4.25x. Kept off master until the owner has reviewed the consequences (decision 0006 on that branch).
