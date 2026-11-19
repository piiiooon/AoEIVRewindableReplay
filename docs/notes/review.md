# Review-only analyses: villager economy, basics, spikes, three lenses, decision points

Moved from CLAUDE.md on 2026-11-13, unchanged. Entries are in the order they were written; when two disagree, the later one is current.

## Villager economy (analyzer/econ.py; owner 2026-10-25; review only)
Aggressor on map hunt -> better villager efficiency -> resource gap; forward mills / outposts / walls are the
cost. Per player every 2 s: villagers by resource (game flag) and food source by position (farm / berry / deer
/ boar / sheep / fish / other); nominal = villagers x base rate (data/econ.json: wiki base rates, read
2026-10-25: sheep / farm 0.75, berry 0.69 (Abbasid, Ayyubid, Delhi 0.8625), deer 0.825, boar 0.9, wood /
gold / stone 0.75 (Templar wood 0.63)) x gather multipliers of researched techs (aoe4world effects
food / hunt / berry / farm / wood / gold / stone; foodGatherRate applied to all food); measured = bank change
+ spent; hunt premium = deer / boar food above farm rate; map hunt > BASE_R 50 from the starting TC; net =
premium - forward drop sites - defence. Fogline: Read "Economy (review)" (enabled only with Show true values /
Everything); profile: per game + medians. game1: OotD food / gold efficiency ~1.25-1.3 (gilded villager bonus
not modelled); Rus gold efficiency 1.7 (hunting cabin passive gold).

Natural food taken (owner 2026-10-25: "how much outside resource you can take than your opponent, especially
food; the farm transition is costly"): econ.natural_food(): every drop in a berry / deer / boar / carcass /
fish amount between node snapshots, split by each player's food villager-time within REACH 8 of it in that
interval (nothing near = unattributed); region by the node's position (base < 50 from own starting TC, own
side, enemy side, enemy base). Recorded: deer and boar are eaten in place (same entity 350 -> 0); sheep turn
into a separate *_corpse carcass. Farm transition: first farm, "majority" = first time (after 3:00) farms
hold >= 50 % of food villager-time over the last minute, farms built / their cost by 10 / 15 / 20 min.
game1: Rus took 8,144 natural food (51 % outside base), no farm; OotD 3,207, first farm 6:50, majority 8:15.
Fogline econ panel: natural-food chart per player + tiles; profile: medians.
Food sources (owner 2026-10-25: Malian cow enclosures give passive food): natural + farms (farm villager-time x
farm rate) + other = gathered food minus both (passive / non-villager: Malian cattle, Mongol pastures, fishing
boats, trade, + estimate error). game1 check: other 435 / 690 of 6,829 / 8,834 food (~6-8 %, model error);
a Malian game showed ~9k other (cattle).
## Basics page (analyzer/basics.py, viewer/build_basics.py; owner 2026-10-26; review only)
Owner's rules: more gathered and no floating (unless saving for an age-up) wins; when behind, what the enemy did
differently; age-up saves allocated right (not over-rallied into wood); spending style; army value / destroyed; trades.
- gathered per resource = bank change + spent (new entities' costs + researched techs). Cancelled landmark: a second
  landmark of the same age placed while one is up, vanishing with the bank jumping back >= 60 % of its cost -> its cost
  is refunded in spent and it is not a loss (game1: HRE Meinwerk Palace placed and cancelled for Aachen Chapel).
- Floating, graded until 200 pop (owner): hard >= 500 of one resource for >= 60 s, soft >= 300 for >= 30 s; resources
  of an age-up being saved for don't count.
- Save window (owner): from the minimum of the needed bank in the 240 s before a landmark start to the start. Ideal =
  same eco villagers split so all needed resources arrive at once after covering spending meanwhile; passive income
  (no villagers on it: Rus bounty gold) counted; capped at the actual time. Also: first moment the bank covered the
  cost -> "placed N s later" (game1 Aachen: affordable 2:55, placed 3:06).
- Spending style per 30 s: saving / floating / turbo (spent >= 90 % of income, >= 50 % army, bank < 400) / spending /
  trickle (40-90 %) / banking. Thresholds are first guesses.
- Deficits: >= 60 s with my 60 s gathering rate below theirs and gap >= 100: villager split, idle, villagers lost,
  gathered per villager.
- Trades (owner: value first, minutes of income second): per death cluster with army deaths and >= 100 value lost.
- Aggression clock: natural nodes (berries, deer, sheep, carcasses, boar, gold, stone) a side's villagers stood within
  8 units of in the last 60 s; left / depletion rate over the last 60 s = minutes left.
- Overqueue (owner 2026-10-26: "more than 2 queues per production building"): stretches >= 3 s with the dump's E queue
  field (Entity_GetProductionQueueSize, likely incl. the item in production) > 2, per building; the opening TC queue
  (start < 60 s) is shown faded and kept out of the totals. game1: OotD 250 s after 1:00 (TC 188, Regnitz 62), Rus 125 s.
run.py writes views/<name>.basics.html (+ work/<name>.basics.json); --player picks my side (default player 1).
fogline-profile: metrics.basics_summary per game (METRICS_V 3 redoes cached games; overqueue share, by building and 5-min phase), "Basics (your rules)" section.
Japanese build: the basics labels are not in viewer/i18n.py yet (stay English).

## Spikes page (analyzer/spikes.py, viewer/build_spikes.py; owner 2026-11-09; review only)
First step towards per-matchup decision trees (parent = big-picture episode, children = measured details; --pro /
--ladder trees from a pro player-ID list; per-patch spike profiles - not built). Owner's rules: the tangible spike is
army value (field value; after a fight, how much remains); eco is the cause. A spike is relative: gap = my army value -
theirs; size = how far the gap moves in my favour (>= MIN_GAIN 150) against its mean in the WIN 90 s before; it ends when
caught up (gap back to that level; credited to a fight that cost the lead, else an opponent spike in between, else
their production), removed (landmark destroyed while its owner still has entities), or game end (= when a player's
lists go empty: a resignation otherwise reads as a lead). No lead within LOOK 180 s = "no army lead".
Spikes: age-ups (age change; landmark of the age before; civs without landmarks named as such), unique techs and first
unique military units (aoe4world "unique" flag: tools/update_data.py now writes it into units.json / upgrades.json).
Children: income /min (all resources over the trailing minute: eco spikes of any kind), army output /min (value as units
appear), villagers, per villager, 90 s before start vs 90 s after done; armies at the spike; idle villagers during the
build; visibility (age-ups announced, techs hidden, units seen when the opponent's vis bit was set); fights while up.
Fights by line: value engaged per line (front = melee, back = ranged, siege; units in the fight circle + 25 at its start
plus reinforcements that died), lost, left; collapse = a line lost 50 %, in order. Composition swap: the most produced
unit base per minute changes (3+ units both minutes). Rally (replay types 12 / 22, military production buildings only,
TC excluded; targets pos / entity / squad): region base (< 40 units of the TC) / thirds; army region; defensive = rally
home while the army is middle / theirs; changes reverted within 10 s dropped. Resource nodes: tracked nodes' remaining
amount (5 s), drops split by each player's gathering villagers within reach (9; gold / stone 14); groups: berry patch
(link 12), deer pack (24), sheep carcasses at one drop site (12); stints split by > 60 s without gathering; worked =
union of the intervals; end = depleted (< 2 % left) / abandoned / game end. Wood: forest patches (link 10) from trees
missing between the 60 s full snapshots (v5 dumps; game1 / test5 logs keep every tree, so untested), wood villagers
within 20. Checked on game1 (HRE vs Rus) and test5 (Byzantine vs Templar, rally from the replay file).
In the viewer (owner 2026-11-09: "combine those 3 files into one"): run.py builds basics + spikes before the viewer;
build_viewer.py --spikes work/<name>.spikes.json --report "Basics=..." --report "Spikes=..." embeds D.spikes and both
whole pages (D.reports). "Review graphs" box under the map / read panel, only with Show true values or Everything:
a menu of graphs (spikes: army + gap, income /min, army produced /min, villagers; basics: gathered, bank, army, spent,
idle villagers) on the replay's time axis with a cursor at the current time (click / drag = seek), spike / fight marks;
the spike list (parent line + details, time button = seek, highlighted while the lead stands); "Full reports" = the
basics / spikes pages in an iframe (srcdoc) whose m:ss times are turned into links that seek the replay.
The separate .basics.html / .spikes.html are still written (the viewer embeds them).

## Three lenses (analyzer/lenses.py, viewer/lens_sections.py; owner 2026-10-27)
Owner: "three types of analysis tendency: hindsight from true value, inference, foresight from true value" (foresight
from inference = tautology: inference already projects). Built in that order; rules from three podcast transcripts the
owner supplied (MSN: closing games; Myriad: Castle Age; TeamTriangle: Feudal). Basics page sections after section 8;
basics() runs lenses() (errors -> B["lensesError"], rest of the page still builds). Thirds = along the line between the
starting TCs (s < 1/3 own, > 2/3 theirs). Unit speeds measured from the log (90th pct of moves while flagged M).
- Hindsight (true): idle production (queue 0 while the bank covers the cheapest army unit / villager the player made there;
  housed apart; landmarks, scouts, monks excluded); raids / pushes (my army unit within 25 of their villager on their half,
  gaps < 15 s merged; raid < 50 % of my army value; forced idle = their idle+garrisoned villagers above their 60 s baseline,
  valued at their true income per villager; "units for villagers" = raid lost > killed + forced); landmark builds (army lost
  placed -> done); arrivals (bank, first production building / unit, military techs, first push = 50 % of army value in
  their third); dives (fight within 35 of their TC / keep / landmark while ahead; lead = gathered gap + army gap, at the fight
  and 120 s after); natural food per third (econ.natural_food with a region function); villager split at the age-up click
  + read (stone >= 3 -> 2nd TC, gold > wood -> fast Castle, else production) + what followed in 180 s.
  Gap onsets (owner 2026-10-27: "where the resource gathering rate starts to be gapped"): gathering rate over a centred 60 s
  window; a stretch = my rate below theirs >= 90 s (blips above <= 10 s ignored) with the gathered gap growing >= 300; at
  the onset's first 90 s: gap per resource, villagers and per-villager rate both sides, count effect (Nm - Nt) x rt vs
  efficiency effect Nm x (rm - rt) -> "fewer villagers" / "less per villager", and context from 1 min before (own
  villagers killed, opponent raids / pushes with forced idle, villager growth, idle, landmarks). Viewer: ↘ mark + panel row.
  game1: OotD behind from 6:00 (fewer villagers: +3 vs +7, Regnitz placed 6:33) and 13:11 (less per villager: Rus push,
  1,603 villager-s forced idle); Rus behind 3:39-6:34 (less per villager, food).
- Foresight (true): catch-up minutes (army gap minus their bank / their 60 s income); safe food = all natural food in own
  third / natural-food rate, farm risk (age 2+, <= 3 min, wood for missing farms comes later); age ETA (bank + per-resource
  income vs standard landmark cost) vs click; idle army (>= 60 s, 70 % in own third, nobody attacking, enemy not in that
  third, their income higher); age-up safety (half their army's travel time to my starting TC vs landmark build time).
- Inference (my sight on them): their split seen (last 60 s) at their age-up announcement vs true then; first farm seen vs
  true; their new food / gold spots and when I first saw them there; army seen (last 60 s) and production buildings seen
  vs true.
game1 (OotD = P1 vs Rus): OotD archery range idle 194 s with the bank to pay; Rus dived at 14:37 while ahead, lost 3,520 vs
300, lead +4,303 -> +780; OotD clicked Castle 4 s after the bank allowed, with Rus's army 37 s away and a 69 s build; OotD saw
3 of Rus's 14 new food / gold spots. No farm-switch risk in game1 / test5 (13-16k natural food per third).
Viewer link (owner 2026-10-27: "basics tied to the replay viewer"; picked: timeline marks + a panel): run.py builds the basics
page first (soft step: a failure, e.g. not 1v1, skips it and the rest still builds; a stale basics.json is deleted first),
then build_viewer.py --basics work/<name>.basics.json embeds viewer/basics_compact.compact() as D.basics. Viewer, only with
Show true values or Everything (no-maphack rule): strip under the scrubber, one lane per player (bands: floats hard / soft,
overqueue, idle army; events: raid / push / dive / trade, flagged in bold warn colour; click = seek) and a "Basics (review)"
panel above "Your army vs what you saw" (gathered, income 60 s, bank, army, villagers / idle, spending style, floating,
overqueued, saving for, catch-up minutes, safe food, idle army, raid / dive now).
fogline-profile: metrics.lens_summary (METRICS_V 4), three flag lists in the Basics section (catch-up = highest value held
two samples in a row).

Colours (owner 2026-10-26: swap deer and berry): berries green (#43a321, dark #7ccf4f; more saturated than the sage
trees) and deer pink (the old berry colour #c0528a / #d97aa8, --n-deer / --deer; boar, sheep, carcasses stay
--n-animal brown) on the Fogline map and the fights page; fogline-spawns reports: berries #2f8f5b, deer #c2417a.

## Decision points (analyzer/decisions.py; owner 2026-11-10; review only)
Per civ from pro games: situation -> what was done (read in hindsight: the decision shows only in the next RESP 150 s) ->
paid off. Situations: income gap >= max(60 /min, 10 %) held 90 s; army gap >= 300 held 60 s; enemy age-up; first sight of a
new enemy army unit type (vis bit); fight trading >= 300; merged within 60 s. Response = spending shares in the window (army
incl. production buildings + military techs / ageup = landmark placed by the window end + 60 s / boom / defence) + fights
(their side / home). Judged by the lead change (gathered + army gap) over the window and the game result (owner: ahead in
both and extending = paid off). Unit return (owner's rule 1) = (destroyed: enemy losses per fight x damage share incl.
unattributed in the denominator + counters forced: enemy spending on units with a bonus >= 50 % of their damage vs it, after
its first one, split by cost + raid forced-idle value) / cost; time on the enemy third. game1 only check so far.
data/civs.json (tools/update_data.py, from data-main civilizations/*.json + units / buildings / techs): per civ code its
description, bonuses, units per age, unique techs, landmarks. data/civ_notes.json (owner's notes, optional). Pages:
fogline-profile civcharts.py (cache profile/games/<game>__dec.json).
