# 0003: Every recording uses the delta format (dump v20+), checked on one reference replay

Date: 2026-11-12

## Decision

Entity records are keyframes (E, every 60 s and an entity's first record) plus deltas (ED changed fields, EX gone);
repeated ability events are folded (ABR). Later versions (v21) add fields on top. Size and speed checks use one reference
replay: AgeIV_Replay_259818624 (Byzantine vs Malian).

## Why

v19 on the reference replay was 49.8 MB, v20 7.2 MB with the same parsed timeline. Recording speed is set by the entity reads,
not the writes, so the format costs nothing in speed.

## Consequences

- parse_log runs in delta mode when a session has ED / EX lines; a cut ED record is lost until the next keyframe.
- `tools/log_size.py` measures what each record type adds; check it after adding a field.

## Format for new records

See 0001.
