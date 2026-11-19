"""Scripted test fights for calibrating the fight simulator (owner 2026-11-10). Each test spawns two armies on open
ground halfway between the starting positions, both attack-move at each other, and the game records them every
tick (0.125 s) with every hit and projectile (ingame/fight_test.lua). One mechanic at a time first, then mixed
armies; each test runs --repeat times with small random offsets (the game's own spread).

    python tools/fight_tests.py                 # list the tests and which are done
    python tools/fight_tests.py --all           # run every test not done yet (Ctrl+C stops; done runs are kept)
    python tools/fight_tests.py --only t07 t08  # these tests
    python tools/fight_tests.py --redo t07      # again (overwrites)
    python tools/fight_tests.py --repeat 5      # runs per test (default 3)
    python tools/fight_tests.py --pending       # every buff test not done yet (groups A, D, S), one skirmish per civ
    python tools/fight_tests.py --buffs DS      # groups D and S, one skirmish per civ

Before: the game in dev mode in a skirmish (fogline-spawns: python launch.py --replay <file>, quit the replay, start a
skirmish: you + 1 AI on Dry Arabia or another open map). The AI is switched off; everything spawned is removed after
each run. Output: logs/fighttests/<test>_r<k>.txt. Send the folder.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "ingame" / "fight_test.lua"
OUT = ROOT / "logs" / "fighttests"

SP, HO, AR, XB, MA = "unit_spearman_2_fre", "unit_horseman_2_fre", "unit_archer_2_fre", "unit_crossbowman_3_eng", \
    "unit_manatarms_3_fre"
KN = "unit_knight_3_eng"
# (id, name, side 1, side 2, gap, secs, upgrades side 1, upgrades side 2, measures[, order])
# order: "am" attack-move (default), "fam" formation attack-move, "move" plain move of side 1 (side 2 empty)
TESTS = [
    ("t00", "spear walk (no enemy)", [(SP, 1)], [], 60, 20, [], [], "base walking speed (no charge)", "move"),
    ("t00b", "knight walk (no enemy)", [(KN, 1)], [], 60, 20, [], [], "base walking speed (no charge)", "move"),
    ("t01", "spear 1v1", [(SP, 1)], [(SP, 1)], 24, 60, [], [], "melee hit timing, damage, approach speed"),
    ("t02", "spear vs horseman", [(SP, 1)], [(HO, 1)], 24, 60, [], [], "bonus damage, cavalry speed"),
    ("t03", "archer 1v1", [(AR, 1)], [(AR, 1)], 40, 60, [], [], "ranged timing, projectile travel, range"),
    ("t04", "archer vs spear", [(AR, 1)], [(SP, 1)], 40, 60, [], [], "shots before contact, ranged in melee"),
    ("t05", "crossbow vs MAA", [(XB, 1)], [(MA, 1)], 40, 60, [], [], "armour, bonus vs heavy"),
    ("t06", "knight vs spear", [(KN, 1)], [(SP, 1)], 24, 60, [], [], "charge, bonus vs cavalry"),
    ("t07", "spear 10v10", [(SP, 10)], [(SP, 10)], 24, 90, [], [], "melee crowding, collision size, formation"),
    ("t07f", "spear 10v10, formation attack-move", [(SP, 10)], [(SP, 10)], 24, 90, [], [],
     "formation facing (owner: plain attack-move met flank to flank)", "fam"),
    ("t08", "archers vs spears 10v10", [(AR, 10)], [(SP, 10)], 40, 90, [], [], "ranged vs melee approach, overkill"),
    ("t09", "knights vs archers 5v10", [(KN, 5)], [(AR, 10)], 40, 90, [], [], "cavalry dive, target choice"),
    ("t10", "MAA vs spears 6v12", [(MA, 6)], [(SP, 12)], 24, 90, [], [], "armour at scale, surround"),
    ("t11", "mangonel vs spear blob", [("unit_mangonel_3_fre", 1)], [(SP, 12)], 48, 90, [], [], "splash radius, falloff"),
    ("t12", "nest of bees vs spear blob", [("unit_nest_of_bees_4_chi", 1)], [(SP, 12)], 48, 90, [], [], "rocket splash"),
    ("t13", "springald vs knights", [("unit_springald_3_fre", 1)], [(KN, 4)], 48, 90, [], [], "pierce line"),
    ("t14", "ribauldequin vs spears", [("unit_ribauldequin_4_fre", 1)], [(SP, 12)], 24, 90, [], [], "burst spread"),
    ("t15", "cannon vs spear blob", [("unit_cannon_4_fre", 1)], [(SP, 12)], 48, 90, [], [], "small splash"),
    ("t16", "bed crossbow vs spears", [("unit_bedcrossbow_3_jin", 1)], [(SP, 12)], 48, 90, [], [], "odd hitbox"),
    # splash re-runs (owner's batch 1: the spear blob killed the siege within 5-14 s): siege invulnerable, the blob holds
    # position in tight rows within range; time-limited
    ("t11s", "mangonel vs held blob", [("unit_mangonel_3_fre", 1)], [(SP, 18)], 26, 40, [], [], "splash radius, falloff",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    ("t12s", "nest of bees vs held blob", [("unit_nest_of_bees_4_chi", 1)], [(SP, 18)], 26, 40, [], [], "rocket splash",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    ("t13s", "springald vs held knights", [("unit_springald_3_fre", 1)], [(KN, 12)], 26, 40, [], [], "pierce line",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 2.2}),
    ("t14s", "ribauldequin vs held blob", [("unit_ribauldequin_4_fre", 1)], [(SP, 18)], 12, 30, [], [], "burst spread",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    ("t15s", "cannon vs held blob", [("unit_cannon_4_fre", 1)], [(SP, 18)], 30, 40, [], [], "small splash",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    ("t15b", "bombard vs held blob", [("unit_bombard_4_eng", 1)], [(SP, 18)], 30, 40, [], [], "small splash",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    ("t16s", "bed crossbow vs held blob", [("unit_bedcrossbow_3_jin", 1)], [(SP, 18)], 26, 40, [], [], "odd hitbox",
     "am", {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}),
    # ---- batch 2 (owner 2026-11-10)
    # pierce to maximum range: one bolt down a single-file column along the line of fire
    ("p01", "springald down a knight column", [("unit_springald_3_fre", 1)], [(KN, 10)], 22, 40, [], [],
     "pierce: targets per bolt along the line", "am", {"orders": ["am", "hold"], "inv": [1], "rows": [6, 1], "spacing": 2.4}),
    ("p02", "bed crossbow down a spear column", [("unit_bedcrossbow_3_jin", 1)], [(SP, 12)], 22, 40, [], [],
     "pierce: targets per bolt along the line", "am", {"orders": ["am", "hold"], "inv": [1], "rows": [6, 1], "spacing": 1.8}),
    # orb walking: the archer's shots vs a held spearman with scripted moves
    ("o01", "archer, move right after each shot (0.5 s)", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "moving after release: shots lost?", "am", {"orders": ["am", "hold"], "kite": {"mode": "afterfire", "move": 0.5}}),
    ("o02", "archer, move right after each shot (1.0 s)", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "moving after release: shots lost?", "am", {"orders": ["am", "hold"], "kite": {"mode": "afterfire", "move": 1.0}}),
    ("o03", "archer, attack then move after 0.125 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "move during aim cancels the shot?", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 0.125}}),
    ("o04", "archer, attack then move after 0.25 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "move during aim cancels the shot?", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 0.25}}),
    ("o05", "archer, attack then move after 0.5 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "move during aim cancels the shot?", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 0.5}}),
    # owner's run: moving 0.125-0.5 s after the attack order fired nothing - find where the shot gets out
    ("o07", "archer, attack then move after 0.625 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "standing time a shot needs", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 0.625}}),
    ("o08", "archer, attack then move after 0.75 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "standing time a shot needs", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 0.75}}),
    ("o09", "archer, attack then move after 1.0 s", [(AR, 1)], [(SP, 1)], 18, 30, [], [],
     "standing time a shot needs", "am", {"orders": ["am", "hold"], "kite": {"mode": "interrupt", "wait": 1.0}}),
    ("o06", "crossbow, move right after each shot (0.5 s)", [(XB, 1)], [(SP, 1)], 18, 30, [], [],
     "moving after release, slower weapon", "am", {"orders": ["am", "hold"], "kite": {"mode": "afterfire", "move": 0.5}}),
    # charge damage on targets that don't brace
    ("c01", "knight into held archer", [(KN, 1)], [(AR, 1)], 30, 30, [], [], "charge damage, first hit",
     "am", {"orders": ["am", "hold"]}),
    ("c02", "knight into held MAA", [(KN, 1)], [(MA, 1)], 30, 30, [], [], "charge damage vs armour",
     "am", {"orders": ["am", "hold"]}),
    ("c03", "horseman into held archer", [(HO, 1)], [(AR, 1)], 30, 30, [], [], "charge damage, light cavalry",
     "am", {"orders": ["am", "hold"]}),
    # more matchups
    ("m01", "horseman vs knight", [(HO, 1)], [(KN, 1)], 30, 60, [], [], "cavalry vs cavalry"),
    ("m02", "knights 5v5", [(KN, 5)], [(KN, 5)], 30, 90, [], [], "cavalry crowding"),
    ("m03", "elephant vs spears 1v6", [("unit_war_elephant_3_sul", 1)], [(SP, 6)], 30, 90, [], [], "elephant hits"),
    ("m04", "villagers fight back 6 vs 2 spears", [("unit_villager_1_fre", 6)], [(SP, 2)], 24, 60, [], [],
     "villager combat"),
    # walking speed of siege (base for the Greased Axles pair)
    ("w01", "mangonel walk (no enemy)", [("unit_mangonel_3_fre", 1)], [], 40, 25, [], [], "siege walk speed", "move"),
    ("t17", "mixed 5v5", [(SP, 3), (AR, 2)], [(MA, 2), (XB, 1), (HO, 2)], 32, 90, [], [], "mixed, small"),
    ("t18", "mixed 15v15", [(SP, 8), (AR, 7)], [(MA, 6), (XB, 4), (HO, 5)], 36, 120, [], [], "mixed, medium"),
    ("t19", "mixed 30v30", [(SP, 12), (MA, 4), (AR, 14)], [(KN, 6), (SP, 8), (XB, 10), (AR, 6)], 40, 150, [], [],
     "mixed, large"),
    ("t20", "archers 10v10, side 1 ranged dmg I+II", [(AR, 10)], [(AR, 10)], 40, 90,
     ["upgrade_ranged_damage_i", "upgrade_ranged_damage_ii"], [], "blacksmith attack"),
    ("t21", "spears 10v10, side 1 melee armour I+II", [(SP, 10)], [(SP, 10)], 24, 90,
     ["upgrade_melee_armor_i", "upgrade_melee_armor_ii"], [], "blacksmith armour"),
]


UP_MIRROR = [  # (unit, upgrade): 1v1 mirror, side 1 upgraded - every stat difference shows both ways
    (SP, "upgrade_melee_damage_i"), (SP, "upgrade_melee_armor_i"), (SP, "upgrade_manatarms_elite_army_tactics"),
    (MA, "upgrade_manatarms_elite_army_tactics"), (AR, "upgrade_ranged_damage_i"), (AR, "upgrade_ranged_armor_i"),
    (AR, "upgrade_ranged_incendiary"), (KN, "upgrade_tech_university_biology"), (HO, "upgrade_cavalry_bloodline_fre"),
    (XB, "upgrade_ranged_damage_i"), (KN, "upgrade_melee_armor_i")]
UP_SIEGE = [  # (siege, upgrade, target): siege invulnerable on a held blob, upgraded vs t11s / t13s-style baselines
    ("unit_mangonel_3_fre", "upgrade_siege_adjustable_crossbar", SP),
    ("unit_springald_3_fre", "upgrade_siege_roller_trigger", KN),
    ("unit_cannon_4_fre", "upgrade_siege_chemistry", SP)]
UP_WALK = [("unit_mangonel_3_fre", "upgrade_siege_weapon_speed"), ("unit_mangonel_3_fre", "upgrade_siege_works")]
for i, (u, up) in enumerate(UP_MIRROR, 1):
    TESTS.append((f"u{i:02d}", f"{u[5:]} mirror, side 1 {up[8:]}", [(u, 1)], [(u, 1)], 24 if "archer" not in u
                  and "crossbow" not in u else 36, 60, [up], [], f"upgrade effect: {up}"))
for i, (u, up, tg) in enumerate(UP_SIEGE, 1):
    for on in (True, False):
        TESTS.append((f"us{i:02d}{'' if on else 'b'}", f"{u[5:]} on held blob, {up[8:] if on else 'baseline'}",
                      [(u, 1)], [(tg, 18)], 26, 40, [up] if on else [], [], f"upgrade effect: {up}", "am",
                      {"orders": ["am", "hold"], "inv": [1], "spacing": 1.8}))
for i, (u, up) in enumerate(UP_WALK, 1):
    TESTS.append((f"uw{i:02d}", f"{u[5:]} walk, {up[8:]}", [(u, 1)], [], 40, 25, [up], [],
                  f"upgrade effect: {up} (vs w01)", "move"))
BATCH2 = ("p", "o", "c", "m", "w", "u")

# ---- buff tests, group A: ordered abilities (owner 2026-11-11; Dry Arabia 2p, middle cleared). Each pair = the same fight
# with and without the cast, side 1 casts; values to check from logs/buff_scout.txt (game files) in the measures text.
# a00 is the probe: does Cmd_Ability work from the console at all (CAST line names the signature that worked)?
LB, MAA_E = "unit_archer_3_eng", "unit_manatarms_3_eng"
BUFF_A = [
    ("a00", "probe: longbows Arrow Volley at 0 s, no enemy", [(LB, 3)], [], 40, 15, ["upgrade_ranged_longbow_arrow_volley_eng"], [],
     "cast works? CAST / AB lines", "move", {"cast": [{"side": 1, "ab": "longbow_rate_of_fire_ability", "at": 0, "target": "self"}]}),
    ("a01", "Arrow Volley: 5 longbows vs held MAA", [(LB, 5)], [(MAA_E, 6)], 22, 30, ["upgrade_ranged_longbow_arrow_volley_eng"], [],
     "reload -1 s for 6 s (files: 1, 6; recharge 45)", "am",
     {"orders": ["am", "hold"], "cast": [{"side": 1, "ab": "longbow_rate_of_fire_ability", "at": "hit", "target": "self"}]}),
    ("a01b", "baseline: 5 longbows vs held MAA", [(LB, 5)], [(MAA_E, 6)], 22, 30, [], [], "no cast", "am", {"orders": ["am", "hold"]}),
    ("a02", "Fortitude: 3 sipahi vs 3 sipahi", [("unit_horseman_2_ott", 3)], [("unit_horseman_2_ott", 3)], 24, 60, [], [],
     "+40 % attack speed, +50 % damage taken, 10 s (files: 40, 50, 10; recharge 50)", "am",
     {"cast": [{"side": 1, "ab": "sipahi_stamina_ott", "at": "hit", "target": "self"}]}),
    # Mehter (owner 2026-11-11: three toggleable auras - attack speed / melee armour / ranged armour): side 1's mehter
    # toggles one, side 2 has no mehter; a03z = mehter untoggled (its state as spawned), a03n = no mehter at all
    ("a03n", "baseline: 6 spears vs 6 spears, no mehter", [("unit_spearman_2_ott", 6)], [("unit_spearman_2_ott", 6)], 24, 60, [], [],
     "spear swing 1.875 s, 8 per hit", "am"),
    ("a03z", "mehter untoggled + 6 spears vs 6 spears", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [("unit_spearman_2_ott", 6)], 24, 60, [], [], "which drum is on as spawned (swing / damage taken vs a03n)", "am"),
    ("a03a", "mehter attack drum + 6 spears vs 6 spears", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [("unit_spearman_2_ott", 6)], 24, 60, [], [], "+15 % attack speed, radius 24", "am",
     {"cast": [{"side": 1, "ab": "mehter_attack_buff_ott", "at": 0, "target": "self", "unit": "unit_mehter_2_ott"}]}),
    ("a03m", "mehter melee-armour drum + 6 spears vs 6 spears", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [("unit_spearman_2_ott", 6)], 24, 60, [], [], "+2 melee armour (spear hits 8 -> 6)", "am",
     {"cast": [{"side": 1, "ab": "mehter_melee_armor_buff_ott", "at": 0, "target": "self", "unit": "unit_mehter_2_ott"}]}),
    ("a03r", "mehter ranged-armour drum + 6 spears vs 6 archers", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [(AR, 6)], 30, 40, [], [], "+1 ranged armour (files; owner's list +2): arrows 5 -> 4", "am",
     {"orders": ["none", "am"], "cast": [{"side": 1, "ab": "mehter_ranged_armor_buff_ott", "at": 0, "target": "self", "unit": "unit_mehter_2_ott"}]}),
    ("a03rb", "baseline: mehter untoggled + 6 spears vs 6 archers", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [(AR, 6)], 30, 40, [], [], "arrows 5 per hit", "am", {"orders": ["none", "am"]}),
    # a04 / a04q crashed the game (owner 2026-11-11): the khan spawns fine (a04p), the position-targeted cast crashes ->
    # position targets are out until another form is found
    ("a04p", "probe: khan spawn only, no cast", [("unit_khan_2_mon", 1)], [], 40, 10, [], [], "does spawning a khan crash?", "move"),
    ("a05", "Body of Iron: shaolin monk vs 4 archers", [("unit_monk_shaolin_3_chi_ha_01", 1)], [(AR, 4)], 30, 40, [], [],
     "-50 % ranged damage for 15 s (recharge 90)", "am",
     {"orders": ["am", "hold"], "cast": [{"side": 1, "ab": "shaolin_monk_ranged_damage_reduction", "at": "hit", "target": "self"}]}),
    ("a05b", "baseline: shaolin monk vs 4 archers", [("unit_monk_shaolin_3_chi_ha_01", 1)], [(AR, 4)], 30, 40, [], [], "no cast", "am",
     {"orders": ["am", "hold"]}),
    ("a06", "Pavise: 4 crossbows vs 6 archers", [("unit_crossbowman_3_fre", 4)], [(AR, 6)], 34, 40, [], [],
     "+5 ranged armour, +1 range, 30 s (recharge 60)", "am",
     {"orders": ["none", "am"], "cast": [{"side": 1, "ab": "deploy_pavise_fre", "at": 1, "target": "self"}]}),
    ("a06b", "baseline: 4 crossbows vs 6 archers", [("unit_crossbowman_3_fre", 4)], [(AR, 6)], 34, 40, [], [], "no cast", "am",
     {"orders": ["none", "am"]}),
    ("a07", "Palings: 5 longbows vs 3 knights", [(LB, 5)], [(KN, 3)], 36, 40, ["upgrade_ranged_palings_eng"], [],
     "stun 2.5 s, 19 damage to a charging knight (recharge 30)", "am",
     {"orders": ["none", "am"], "cast": [{"side": 1, "ab": "deploy_palings", "at": 1, "target": "self"}]}),
    ("a07b", "baseline: 5 longbows vs 3 knights", [(LB, 5)], [(KN, 3)], 36, 40, [], [], "no cast", "am", {"orders": ["none", "am"]}),
    ("a08", "Forced March: 6 spears walk", [("unit_spearman_2_sul", 6)], [], 60, 20, ["upgrade_landmark_force_march_sul"], [],
     "+100 % speed, 10 s (recharge 75); run 1 without the tech: no effect", "move",
     {"cast": [{"side": 1, "ab": "infantry_forced_march_sul", "at": 1, "target": "self"}]}),
]
# manual versions (owner 2026-11-11: "provide the units and I press them"): side 1 = your player; nothing moves for `wait` s
# while you select side 1 and use the ability (or toggle the drum); the run records your casts (AB lines) and their effect.
BUFF_AM = [
    ("a06m", "MANUAL Pavise: 4 crossbows vs 6 archers", [("unit_crossbowman_3_fre", 4)], [(AR, 6)], 34, 50, [], [],
     "+5 ranged armour, +1 range, 30 s (compare a06b)", "am",
     {"orders": ["none", "am"], "wait": "cast", "manual": "select the 4 crossbows (your side) and press Deploy Pavise - nothing moves until your cast is recorded (2 min max), so wait out a cooldown first"}),
    ("a07m", "MANUAL Palings: 5 longbows vs 3 knights", [(LB, 5)], [(KN, 3)], 36, 50, ["upgrade_ranged_palings_eng"], [],
     "stun 2.5 s, 19 damage (compare a07b)", "am",
     {"orders": ["none", "am"], "wait": "cast", "after": 20, "manual": "select the 5 longbows and press Place Palings (facing the knights) - the knights start 20 s after your cast is recorded (2 min max), so wait out a cooldown first"}),
    ("a03mm", "MANUAL Mehter melee-armour drum + 6 spears vs 6 spears", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [("unit_spearman_2_ott", 6)], 24, 70, [], [], "+2 melee armour: hits on side 1 8 -> 6 (compare a03z)", "am",
     {"wait": 10, "manual": "select the mehter and turn on the melee-armour drum (only that one)"}),
    ("a03rm", "MANUAL Mehter ranged-armour drum + 6 spears vs 6 archers", [("unit_mehter_2_ott", 1), ("unit_spearman_2_ott", 6)],
     [(AR, 6)], 30, 50, [], [], "+1 ranged armour: arrows 5 -> 4 / 10 -> 9 (compare a03rb)", "am",
     {"orders": ["none", "am"], "wait": 10, "manual": "select the mehter and turn on the ranged-armour drum (only that one)"}),
    ("a04m", "MANUAL Khan attack-speed arrow: khan + 6 horse archers each", [("unit_khan_2_mon", 1), ("unit_horsearcher_2_mon", 6)],
     [("unit_khan_2_mon", 1), ("unit_horsearcher_2_mon", 6)], 40, 70, [], [], "+50 % attack speed, 5 s, radius 35", "am",
     {"wait": 10, "manual": "once the fight starts, fire the Khan's attack-speed signal arrow onto your horse archers"}),
]
TESTS += BUFF_A + BUFF_AM

# group D: damage over time (owner 2026-11-12: "it's hard to find those events in games, so let's do the tests"). Each
# attacker against held men-at-arms (side 2 hold: the ticks stand out against the hits). Measures: tick damage, interval,
# count, stacking / reset, and who the game names as the attacker of a tick (259818624: the victim's latest attacker)
MA_T = "unit_manatarms_3_eng"
BUFF_D = [
    ("d01", "Mansa poison: 1 mansa javelineer vs 1 held MAA", [("unit_mansa_javelin_3_mal", 1)], [(MA_T, 1)], 20, 30, [], [],
     "hit, then 1 at +2 / +4 / +6 s", "am", {"orders": ["am", "hold"]}),
    ("d02", "Mansa poison stacking: 3 mansa vs 1 held MAA", [("unit_mansa_javelin_3_mal", 3)], [(MA_T, 1)], 20, 30, [], [],
     "3 stacks of 1 every 2 s?", "am", {"orders": ["am", "hold"]}),
    ("d03", "tick attacker naming: 2 mansa + 3 spearmen (the javelins land first) vs 1 held MAA",
     [("unit_mansa_javelin_3_mal", 2), ("unit_spearman_3_mal", 3)], [(MA_T, 1)], 20, 40, [], [],
     "mansa ticks after a spearman's hit - named after the spearman?", "am", {"orders": ["am", "hold"]}),
    # owner 2026-11-12: the first run's Poisoned Arrows (granted right before the spawn) did not reach the archers and stayed
    # into the baseline -> baseline first with the upgrade removed, the poison test after a prep run that grants it
    ("d04b", "baseline: 3 Malian archers vs 1 held MAA", [("unit_archer_3_mal", 3)], [(MA_T, 1)], 26, 30, [], [],
     "no ticks", "am", {"orders": ["am", "hold"], "rm": ["upgrade_archer_poison_arrow_mal"]}),
    ("d04", "Poisoned Arrows: 3 Malian archers vs 1 held MAA", [("unit_archer_3_mal", 3)], [(MA_T, 1)], 26, 30,
     ["upgrade_archer_poison_arrow_mal"], [], "3 over 6 s per arrow, stacking", "am", {"orders": ["am", "hold"], "pregrant": True}),
    ("d05", "Kipchak bleed: 1 kipchak vs 1 held MAA", [("unit_kipchak_3_mon_ha_gol", 1)], [(MA_T, 1)], 26, 30, [], [],
     "2 / s for 6 s, armour-free", "am", {"orders": ["am", "hold"]}),
    ("d06", "Kipchak bleed stacking: 3 kipchaks vs 1 held MAA", [("unit_kipchak_3_mon_ha_gol", 3)], [(MA_T, 1)], 26, 30, [], [],
     "no stacking, reset by any kipchak hit", "am", {"orders": ["am", "hold"]}),
    ("d05d", "Kipchak bleed duration: 1 kipchak hits for 4 s, then walks away", [("unit_kipchak_3_mon_ha_gol", 1)], [(MA_T, 1)],
     26, 20, [], [], "ticks after the last hit = the bleed's length (6 s?)", "am",
     {"orders": ["am", "hold"], "steps": [{"at": 4, "side": 1, "go": "away"}]}),
    ("d07", "Kipchak Triple Shot: 1 kipchak vs 3 held MAA", [("unit_kipchak_3_mon_ha_gol", 1)], [(MA_T, 3)], 26, 30,
     ["upgrade_mangudai_triple_shot_mon_ha_gol"], [], "side arrows bleed 0.6 / s for 6 s (upgrade name a guess)", "am",
     {"orders": ["am", "hold"]}),
    ("d08", "Zornhau: 2 gilded landsknechts vs 1 held MAA", [("unit_landsknecht_3_hre_ha_01", 2)], [(MA_T, 1)], 20, 30,
     ["upgrade_zornhau_hre_ha_01"], [], "2 / s for 10 s per hit", "am", {"orders": ["am", "hold"]}),
    ("d08d", "Zornhau duration: 1 gilded landsknecht hits for 4 s, then walks away", [("unit_landsknecht_3_hre_ha_01", 1)],
     [(MA_T, 1)], 20, 25, ["upgrade_zornhau_hre_ha_01"], [], "ticks after the last hit = the bleed's length (10 s?)", "am",
     {"orders": ["am", "hold"], "steps": [{"at": 4, "side": 1, "go": "away"}]}),
    ("d08b", "baseline: 2 gilded landsknechts vs 1 held MAA", [("unit_landsknecht_3_hre_ha_01", 2)], [(MA_T, 1)], 20, 30, [], [],
     "no ticks", "am", {"orders": ["am", "hold"]}),
]
# group S: sacred sites (a map with sacred sites, starting age Castle; English: monk = unit_monk_3_eng). The test centres on the
# site nearest the middle; SS lines every 0.5 s: owner, capture progress, capturing units near, secure count, gold
MONK, SPR = "unit_monk_3_eng", "unit_spearman_2_eng"
BUFF_S = [
    ("s01", "capture: a monk on the site", [(MONK, 1)], [], 12, 50, [], [],
     "30 s to capture; progress values / units; owner; gold trickle after", "am",
     {"site": True, "on": [True, False], "orders": ["none", "none"]}),
    ("s02", "contest: monk capturing, an enemy spearman arrives at 10 s, leaves at 20 s", [(MONK, 1)], [(SPR, 1)], 30, 50, [], [],
     "progress stops while contested, resumes after", "am",
     {"site": True, "on": [True, False], "orders": ["none", "none"],
      "steps": [{"at": 10, "side": 2, "go": "site"}, {"at": 20, "side": 2, "go": "away"}]}),
    ("s03", "monk leaves at 15 s (half captured)", [(MONK, 1)], [], 12, 45, [], [],
     "progress empties at the same rate", "am",
     {"site": True, "on": [True, False], "orders": ["none", "none"], "steps": [{"at": 15, "side": 1, "go": "away"}]}),
    ("s04", "decapture: site held by side 1, an enemy spearman on it", [], [(SPR, 1)], 12, 45, [], [],
     "30 s to neutral; side 1's gold trickle stops", "am",
     {"site": True, "held": 1, "on": [False, True], "orders": ["none", "none"]}),
    ("s05", "decapture contested: held by side 1, enemy spearman on it, a side 1 spearman arrives at 10 s", [(SPR, 1)],
     [(SPR, 1)], 30, 45, [], [], "decapture pauses while contested", "am",
     {"site": True, "held": 1, "on": [False, True], "orders": ["none", "none"], "steps": [{"at": 10, "side": 1, "go": "site"}]}),
]
TESTS += BUFF_D + BUFF_S

# civ of side 1 per buff test (owner 2026-11-11: spawned units belong to the player's civ - a Sengoku player's "French
# arbaletriers" were an unknown unit with no Pavise). The game's race names (Player_GetRaceName); start the skirmish as that civ
# with starting age Castle (III). Tests of one civ run together; the script asks before each civ.
CIV_OF = {"a00": "english", "a01": "english", "a01b": "english", "a07": "english", "a07b": "english", "a07m": "english",
          "a02": "ottoman", "a03n": "ottoman", "a03z": "ottoman", "a03a": "ottoman", "a03m": "ottoman", "a03r": "ottoman",
          "a03rb": "ottoman", "a03mm": "ottoman", "a03rm": "ottoman",
          "a04p": "mongol", "a04m": "mongol", "a05": "chinese_ha_01", "a05b": "chinese_ha_01",
          "a06": "french", "a06b": "french", "a06m": "french", "a08": "sultanate",
          "d01": "malian", "d02": "malian", "d03": "malian", "d04": "malian", "d04b": "malian",
          "d05": "mongol_ha_gol", "d06": "mongol_ha_gol", "d07": "mongol_ha_gol", "d08": "hre_ha_01", "d08b": "hre_ha_01",
          "d05d": "mongol_ha_gol", "d08d": "hre_ha_01",
          "s01": "english", "s02": "english", "s03": "english", "s04": "english", "s05": "english"}
CIV_NAME = {"english": "English", "ottoman": "Ottomans", "mongol": "Mongols", "chinese_ha_01": "Zhu Xi's Legacy",
            "french": "French", "sultanate": "Delhi Sultanate", "malian": "Malians", "mongol_ha_gol": "Golden Horde",
            "hre_ha_01": "Order of the Dragon"}


def civ_of(t):
    return CIV_OF.get(t[0])


CLEAN_LUA = ROOT / "ingame" / "fight_clean.lua"


def write_clean():
    """owner 2026-11-11: the AI researched blacksmith +1 attack while the stage was set up - side 2 won. Every generic (not
    unique) upgrade with a combat effect in data/upgrades.json is removed from both players before each test (fight_test.lua
    loads this file; CLEAN lines name the ones a player had); wing / landmark add-ons are left alone."""
    U = json.loads((ROOT / "data" / "upgrades.json").read_text(encoding="utf-8"))["upgrades"]
    props = {"meleeAttack", "rangedAttack", "siegeAttack", "fireAttack", "meleeArmor", "rangedArmor", "fireArmor", "hitpoints",
             "attackSpeed", "moveSpeed", "maxRange", "healingRate", "rangedResistance"}
    keep = sorted(k for k, v in U.items() if not any(e.get("unique") for e in v) and not k.startswith("upgrade_add_")
                  and any(f.get("property") in props for e in v for f in e.get("effects", [])))
    CLEAN_LUA.write_text("A4D_FT_CLEAN = {\n" + "".join(f'  "{k}",\n' for k in keep) + "}\n", encoding="utf-8")
    return len(keep)


def lua_config(t, k, rng):
    tid, _, s1, s2, gap, secs, u1, u2 = t[:8]
    order = t[9] if len(t) > 9 else "am"
    ex = t[10] if len(t) > 10 else {}
    jx, jz = rng.uniform(-3, 3), rng.uniform(-3, 3)
    side = lambda lst: "{" + ",".join(f'{{"{bp}",{n}}}' for bp, n in lst) + "}"
    ups = lambda lst: "{" + ",".join(f'"{u}"' for u in lst) + "}"
    g = gap + rng.uniform(-2, 2)
    return (f'A4D_FT={{id="{tid}_r{k}",sides={{{side(s1)},{side(s2)}}},gap={g:.2f},secs={secs},every=0.125,'
            f'jx={jx:.2f},jz={jz:.2f},up={{{ups(u1)},{ups(u2)}}},cmd="{order}",clean="{CLEAN_LUA.as_posix()}"'
            + (',orders={' + ",".join(f'"{o}"' for o in ex["orders"]) + '}' if ex.get("orders") else "")
            + (',inv={' + ",".join(str(v) for v in ex["inv"]) + '}' if ex.get("inv") else "")
            + (f',spacing={ex["spacing"]}' if ex.get("spacing") else "")
            + (',rows={' + ",".join(str(v) for v in ex["rows"]) + '}' if ex.get("rows") else "")
            + (',kite={' + ",".join(f'{k}={json.dumps(v)}' for k, v in ex["kite"].items()) + '}' if ex.get("kite") else "")
            + ((f',wait="{ex["wait"]}"' if isinstance(ex["wait"], str) else f',wait={ex["wait"]}') if ex.get("wait") else "")
            + (f',civ="{civ_of(t)}"' if civ_of(t) else "")
            + (',manual=true' if ex.get("manual") else "")
            + (f',after={ex["after"]}' if ex.get("after") else "")
            + (',site=true' if ex.get("site") else "")
            + (',keep=true' if ex.get("keep") else "")
            + (',until_neutral=true' if ex.get("until_neutral") else "")
            + (',rm={' + ",".join(f'"{u}"' for u in ex["rm"]) + '}' if ex.get("rm") else "")
            + (f',held={ex["held"]}' if ex.get("held") else "")
            + (',on={' + ",".join("true" if v else "false" for v in ex["on"]) + '}' if ex.get("on") else "")
            + (',steps={' + ",".join("{" + ",".join(f"{k}={json.dumps(v)}" for k, v in st.items()) + "}" for st in ex["steps"]) + '}'
               if ex.get("steps") else "")
            + (',cast={' + ",".join("{" + ",".join(f"{k}={json.dumps(v)}" for k, v in c.items()) + "}" for c in ex["cast"]) + '}'
               if ex.get("cast") else "")
            + '} ')


def out_file(tid, k):
    return OUT / f"{tid}_r{k}.txt"


def run_one(gl, log, t, k, rng):
    start = len(log.lines)
    con = gl.Console(log, gl.game_window())
    con.open_front(say=print)
    try:
        con.run(lua_config(t, k, rng) + f'local f,e=loadfile("{LUA.as_posix()}") if not f then error(e) end f()',
                timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"  console: {e}")
    con.close()
    ex = t[10] if len(t) > 10 else {}
    if ex.get("manual"):
        w = ex.get("wait", 0)
        print(f"  >>> YOUR TURN: {ex['manual']}" + ("" if w == "cast" else f" (orders start in {w} s)"))
    end = time.time() + t[5] + 90
    tag = f"A4D|FT|END|{t[0]}_r{k}|"
    while time.time() < end and not any(tag in l for l in log.lines[start:]):
        log.poll()
        time.sleep(0.3)
    block = [l[l.find("A4D|FT|"):] for l in log.lines[start:] if "A4D|FT|" in l]
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"id": t[0], "name": t[1], "side1": t[2], "side2": t[3], "gap": t[4], "secs": t[5], "up1": t[6],
            "up2": t[7], "measures": t[8], "order": t[9] if len(t) > 9 else "am", "run": k}
    out_file(t[0], k).write_text("# " + json.dumps(meta) + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    endl = next((l for l in block if l.startswith("A4D|FT|END|")), None)
    nh = sum(l.count(";") + 1 for l in block if l.startswith("A4D|FT|H|"))
    errs = [l for l in block if l.startswith("A4D|FT|ERR")]
    for l in block:
        if l.startswith(("A4D|FT|CAST|", "A4D|FT|CASTPRE|", "A4D|FT|ABEV|", "A4D|FT|ERR", "A4D|FT|CIV|1", "A4D|FT|SITE|", "A4D|FT|HELD|")):
            print("   ", l[7:220])
    print(f"  {out_file(t[0], k).name}: {endl or 'no END line'}; {nh} hits" + (f"; errors: {errs[:3]}" if errs else ""))
    time.sleep(3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--redo", nargs="*")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--batch2", action="store_true", help="only the batch-2 tests (p / o / c / m / w / u ids)")
    ap.add_argument("--buffs", help="buff test groups, one or more letters: A (ids a..), D (damage over time), S (sacred sites); "
                                    "e.g. --buffs DS")
    ap.add_argument("--plan", action="store_true", help="only print which skirmishes / tests the command would run (no game needed)")
    ap.add_argument("--pending", action="store_true",
                    help="every buff test (groups A, D, S) not done yet, one skirmish per civ (owner 2026-11-12)")
    ap.add_argument("--no-prompt", action="store_true", help="don't stop to ask for the civ of the next tests")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if not (a.all or a.only or a.redo or a.batch2 or a.buffs or a.pending):
        for t in TESTS:
            done = sum(1 for k in range(1, a.repeat + 1) if out_file(t[0], k).exists())
            print(f"{t[0]}  {done}/{a.repeat}  {t[1]:40s} {t[8]}")
        print("\npython tools/fight_tests.py --all | --only t01 t02 | --redo t07")
        return
    pick = set(a.only or []) | set(a.redo or [])
    if a.batch2:
        pick |= {t[0] for t in TESTS if t[0].startswith(BATCH2)}
    letters = set((a.buffs or "").lower()) | (set("ads") if a.pending else set())
    if letters:
        pick |= {t[0] for t in TESTS if t[0][0] in letters and t[0][1:2].isdigit()}
    todo = [t for t in TESTS if not pick or t[0] in pick]

    def pending(t):
        return any(not out_file(t[0], k).exists() or (a.redo and t[0] in a.redo) for k in range(1, a.repeat + 1))

    todo = [t for t in todo if pending(t)]
    # owner 2026-11-12: one skirmish per civ, whatever the test type - all of a civ's tests together, the civs in list order
    order = {c: i for i, c in enumerate(dict.fromkeys(civ_of(t) for t in todo))}
    todo.sort(key=lambda t: order[civ_of(t)])          # stable: the list order within a civ
    by_civ = {}
    for t in todo:
        by_civ.setdefault(civ_of(t), []).append(t)
    is_site = lambda t: t[0].startswith("s") and t[0][1:].isdigit()  # noqa: E731
    print(f"\n{len(todo)} tests in {len(by_civ)} skirmish(es):")
    for c, L in by_civ.items():
        print(f"  {CIV_NAME.get(c, c) if c else 'any civ'}: {' '.join(t[0] for t in L)}"
              + ("  (map WITH sacred sites)" if any(is_site(t) for t in L) else ""))
    if a.plan or not todo:
        return
    sys.path.insert(0, str(ROOT / "tools"))
    import gamelink as gl                       # Windows only
    if gl.game_pid() is None:
        sys.exit("the game isn't running (dev mode skirmish needed)")
    log = gl.LogTail(gl.WARNINGS)
    try:
        log.offset = gl.WARNINGS.stat().st_size
    except OSError:
        pass
    print(f"  {write_clean()} generic combat upgrades will be removed from both players before each test")
    rng = random.Random(a.seed)
    cur = None
    for t in todo:
        if civ_of(t) != cur and civ_of(t) and not a.no_prompt:
            cur = civ_of(t)
            site = any(is_site(x) for x in by_civ[cur])       # one map for every test of this civ
            input(f"\n== next: {CIV_NAME.get(cur, cur)} ({' '.join(x[0] for x in by_civ[cur])}). Start a skirmish as "
                  f"{CIV_NAME.get(cur, cur)} (you) + 1 AI, "
                  + ("a 2p map WITH SACRED SITES" if site else "Dry Arabia 2p")
                  + ", starting age Castle (III), clear the middle, then press Enter here ")
        prepped = False
        for k in range(1, a.repeat + 1):
            if out_file(t[0], k).exists() and not (a.redo and t[0] in a.redo):
                continue
            ex = t[10] if len(t) > 10 else {}
            if ex.get("pregrant"):          # every run: each run removes its upgrades at the end
                # grant the upgrades in a run with no units and keep them, so they are in effect when the test spawns
                prep = (t[0] + "prep", "prep: grant " + ", ".join(t[6]), [], [], t[4], 2, t[6], t[7], "-", "am", {"keep": True})
                print(f"{t[0]} prep run (upgrades granted ahead of the spawn)")
                run_one(gl, log, prep, k, rng)
            if ex.get("site") and not ex.get("held"):
                # owner 2026-11-12: a capture test needs a neutral site - the last run's monk is removed with its units; an
                # enemy spearman stands on the site until it is neutral again (up to 90 s), then it is removed too
                reset = (t[0] + "reset", "reset: decapture the site", [], [(SPR, 1)], 12, 90, [], [], "-", "am",
                         {"site": True, "on": [False, True], "orders": ["none", "none"], "until_neutral": True})
                print(f"{t[0]} reset run (enemy spearman on the site until it is neutral)")
                run_one(gl, log, reset, k, rng)
            print(f"{t[0]} {t[1]} - run {k}")
            run_one(gl, log, t, k, rng)
    print(f"\nDone: {OUT} (send the folder)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
