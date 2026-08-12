# Vault timeline contract

Reconstruct host artifact timelines from a synthetic forensic vault. Each case directory
contains three JSONL ledgers: `objects.jsonl`, `oplog.jsonl`, and `txnlog.jsonl`.

## Identity

Every object incarnation is the pair `(slot, gen)`. A slot number alone is never an identity.
Two rows that share `slot` but differ in `gen` are distinct incarnations and must never merge.

## Ledgers

`objects.jsonl` is the end-state object table. Fields: `slot`, `gen`, `names` (array of path
strings), `streams` (object map of stream name to content hash), `si_mtime`, `si_ctime`,
`si_btime` (integer SI times).

`oplog.jsonl` is a circular operation journal. Fields: `op_seq` (unsigned integer that wraps),
`slot`, `gen`, `kind`, `wall` (journal wall time), `name`, `stream`, `content`.
`kind` is one of `CREATE`, `WRITE`, `DELETE`, `RENAME_OLD`, `RENAME_NEW`, `LINK`,
`CREATE_STREAM`, `DELETE_STREAM`.

`txnlog.jsonl` is a short transactional gap log with the same field set as oplog rows plus
`txn_id`. It may contain operations that are missing from the oplog window.

## Chronological order

Oplog `op_seq` values increase until they wrap back to a low value. There is at most one wrap
seam in a case. Chronological order is the unique circular rotation that starts at the oldest
oplog event. Oldest means the minimum `(wall, op_seq, slot, gen)` among oplog rows. Later events
follow by ascending `(op_seq - start) mod 65536`.

When the oplog both wraps and is missing one or more operations that appear in `txnlog.jsonl`,
those txnlog-only operations are inserted into that same rotated order by their `op_seq`
distance from `start`. Journal evidence from txnlog is authoritative for placing those missing
operations. Sorting raw `op_seq` as plain integers is wrong once a wrap exists. Ignoring txnlog
when a wrap and a gap co-occur is wrong.

## Rename coalesce

A `RENAME_OLD` immediately followed in chronological order by a `RENAME_NEW` on the same
`(slot, gen)` coalesces into a single `MOVE` event, including when that adjacent pair
straddles the single oplog wrap seam. Coalesce is evaluated only after the full
chronological merge of the rotated oplog with txnlog-only inserts. When the two halves
of an adjacent pair come from different ledgers (one oplog row and one txnlog-only
insert) they still coalesce into MOVE. Ledger origin must not block coalesce. The MOVE
uses the OLD name as `name_from`, the NEW name as `name_to`, and the journal `wall`
from the NEW row. Emitting both rename fragments as separate timeline events is wrong.

A `RENAME_NEW` that is not preceded by a matching `RENAME_OLD` on the same incarnation is a
standalone `RENAME_NEW` event.

## Time authority

When an operation has journal evidence (it appears in the ordered oplog or as an inserted
txnlog-only row), that row's `wall` is the event time. Object-table SI times are authoritative
only for residual end-state facts that have no journal evidence. Preferring SI times for
journalled operations is wrong.

If an incarnation has at least one journalled event, ownership names and streams come only
from those journalled events (and the poison rules below). Object-table rows for that
incarnation do not add unmatched names or streams. If an incarnation has zero journalled
events (SI-only residual), adopt its object-table names and streams that are not already
in `poisoned_paths`. No-revive applies to residual object-table adoption: never adopt a
name that is already poisoned, even when that name appears only on an SI-only row.
Streams on SI-only residuals are still adopted when not otherwise forbidden. There is no
sweep into other incarnations and no stay-put of conflicting object-table path claims once
poison applies.

## Streams and generation boundaries

Named streams are bound to an incarnation. A new `gen` in a reused `slot` starts with no
streams. Streams from a prior generation are not inherited, even when stream names overlap.
Only `CREATE_STREAM` / `WRITE` / `CREATE` content on that incarnation populate its streams.

## Path claims and poison

Ownership names come from journalled `CREATE`, `LINK`, and coalesced `MOVE` / standalone
`RENAME_NEW` targets on that incarnation, minus later `DELETE` or MOVE-away of that name.

A clean transfer is a coalesced MOVE of a path from one incarnation to another, or a DELETE
of the path on the prior holder before another incarnation claims it.

If two or more distinct incarnations claim the same path without a clean transfer between
those claims, the path becomes poisoned at the first such conflict. A poisoned path is omitted
from every incarnation's `names` list and is listed once in `poisoned_paths`. After poison,
later claims must not revive the path into any incarnation's `names` (no revive).

## Fit pack

`/app/data/fit/alpha/` includes ledgers and `/app/data/fit/alpha/smoke_digests.json`.
Those smoke digests are sha256 hashes of the JSON text produced by the shipped partial helper
multi-module engine package (`/app/engine/`, orchestration via `pipeline.py`, thin `starter.py`
re-export) on the fit ledgers. They are a non-normative smoke check for that fit smoke scaffold
only. They are not graded normative expected timeline or ownership documents for work cases.
Graded behavior is uniquely determined by the end-state invariants in this contract together with
the fit ledger topology (identity, schemas, serialization, ownership/poison/stream invariants,
wrap oldest-first, MOVE coalesce adjacency, corpus_index schema).

The shipped engine package is a partial helper and fit-smoke-calibrated relative to this
contract. Passing fit smoke does not imply a correct work-case reconstruction.

## Work packs

Process every case directory under `/app/data/work/`. Write outputs under
`/app/output/<case_id>/` where `<case_id>` is the directory name.

Also write `/app/output/corpus_index.json` aggregating every work case (see Output schemas).

## Output schemas

`timeline.json` is a JSON array of event objects sorted by `time` ascending, then `op_seq`
ascending, then `event_id` ascending. Each event has:

- `event_id` (string): `"{slot}:{gen}:{op_seq}:{kind}"` for non-MOVE events, and
  `"{slot}:{gen}:{op_seq_new}:MOVE"` for coalesced MOVE (use the NEW row's `op_seq`)
- `slot` (integer)
- `gen` (integer)
- `kind` (string)
- `time` (integer)
- `op_seq` (integer)
- `name` (string or null): primary name for non-MOVE events
- `name_from` (string or null): set only for MOVE
- `name_to` (string or null): set only for MOVE
- `stream` (string or null)
- `content` (string or null)

Serialize with UTF-8, `ensure_ascii` false, 2-space indent, trailing newline, and object key
order exactly as listed above for each event.

`ownership.json` is a JSON object:

- `incarnations`: array sorted by `slot` ascending then `gen` ascending. Each item:
  - `id` (string): `"{slot}:{gen}"`
  - `slot` (integer)
  - `gen` (integer)
  - `names` (array of strings, sorted ascending): non-poisoned names only
  - `streams` (object): stream name to content hash, keys sorted ascending in serialization
- `poisoned_paths` (array of strings, sorted ascending)

Serialize with UTF-8, `ensure_ascii` false, 2-space indent, trailing newline. Top-level key
order is `incarnations` then `poisoned_paths`. Incarnation object key order is
`id`, `slot`, `gen`, `names`, `streams`.

`corpus_index.json` is a JSON object aggregating every work case under `/app/data/work/`:

- `case_ids` (array of strings, sorted ascending): work case directory names
- `poisoned_paths` (array of strings, sorted ascending): union of `poisoned_paths` across cases
- `incarnation_count` (integer): sum of incarnation array lengths across cases
- `move_event_count` (integer): sum of timeline events with `kind` equal to `MOVE` across cases

Serialize with UTF-8, `ensure_ascii` false, 2-space indent, trailing newline. Top-level key
order is `case_ids`, `poisoned_paths`, `incarnation_count`, `move_event_count`.
