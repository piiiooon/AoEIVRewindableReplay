# 0005: The 3D scene is mirrored once at the world group; models are used as exported

Date: 2026-11-12

## Decision

Everything is placed in game coordinates inside a three.js group `world` with scale.x = -1. Model exports and stamp
placements are already in game (left-handed) space and are used untouched (`--mirror-models` exists but is off).

## Why

The game's world is left-handed (seen from above: x right, z up, as the 2D pages draw it); three.js is right-handed, so the
first 3D page was the mirror image of the game. Converting the meshes too (p43) moved buildings off their slabs (p44).

## Consequences

- Camera state stays in game space; place() / groundAt() negate x.
- Weapon hand = +x in game space; shields / extras at -x.

## Format for new records

See 0001.
