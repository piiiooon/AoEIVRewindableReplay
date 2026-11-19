# 0004: Complete the recorder before deeper analysis; fight engine on hold

Date: 2026-11-12

## Decision

The recorder (ingame/dump.lua) is completed first, so non-graphical features never need a re-recording. Analyses that
depend on it (sacred-site income / time held, etc.) come after. fightcal / fightsim calibration is on hold.

## Why

Owner: every in-depth analysis needs the recorder to record everything necessary; re-recording each replay is the slow step.

## Consequences

- New data needs go into dump.lua (pcall'd, mock harness updated) before analysis code.
- Parked work is listed in `docs/notes/roadmap.md`.

## Format for new records

See 0001.
