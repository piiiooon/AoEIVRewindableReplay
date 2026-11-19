# 0002: The observer view uses only what that player could know

Date: 2026-10-23 (HUD exception 2026-11-11)

## Decision

Observer view: visible entities (the game's vis flags) and what was seen earlier, game rules / data, announcements every
player gets, assumed optimal play (labelled). Hidden data only in "Everything" and "Show true values". Exception (owner,
explicit): the observer bar / stats / fight recap (viewer/hud.js) and the 3D graph show full values for both players in every
view, like the in-game caster bar.

## Why

The core question is what one player could have known. A read built on hidden data answers a different question.

## Consequences

- Never: true banks, unseen entities, the opponent's commands or camera, parameters fitted on the same game's hidden data
  (`--fit-rate` is review-only).
- Review panels (basics, spikes, buffs, economy, techs) appear only with Show true values / Everything.
- Sight views show only the observer's own orders, cameras, rallies and production.

## Format for new records

See 0001.
