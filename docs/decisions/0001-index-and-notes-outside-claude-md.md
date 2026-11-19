# 0001: CLAUDE.md holds rules only; the index and subsystem notes live in separate files

Date: 2026-11-13

## Decision

`CLAUDE.md` keeps the hard rule, the pipeline, conventions and pointers. The file index is `INDEX.md`, subsystem notes are
`docs/notes/<topic>.md`, choices are `docs/decisions/`. None of them is `@`-imported; Claude reads them on demand. The old
187 KB CLAUDE.md was split into docs/notes/ unchanged (convention from the owner's token-efficiency-setup).

## Why

- `CLAUDE.md` is sent with every request; at 187 KB (~45-50k tokens) it filled the context before any work and buried the
  few hard rules among superseded history.
- An `@path` import would load the files anyway.
- The index lists only files whose purpose is not clear from their name; Claude can list and search the repo itself.

## Consequences

- New findings go into the matching notes file, not CLAUDE.md. Notes are append-only history: the later entry wins.
- `.claude/hooks/index_check.py` reminds Claude to index a newly created file (it cannot write the description).
- A stale index misleads: delete lines for deleted files.

## Format for new records

Copy this file as `NNNN-short-title.md` and keep the same four headings. A few lines each is enough.
