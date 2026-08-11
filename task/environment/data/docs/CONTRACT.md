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
seam in a case. Chronological order is the unique rotation that places the oldest event first.

When the oplog both wraps and is missing one or more operations that appear in `txnlog.jsonl`
with `op_seq` values spanning that seam, those txnlog-only operations are inserted into the
timeline. Journal evidence from txnlog is authoritative for placing those missing operations
relative to the wrap seam. Sorting raw `op_seq` as plain integers is wrong once a wrap exists.
Ignoring txnlog when a wrap and a gap co-occur is wrong.

## Rename coalesce

A `RENAME_OLD` immediately followed in chronological order by a `RENAME_NEW` on the same
`(slot, gen)` coalesces into a single `MOVE` event. The MOVE uses the OLD name as `name_from`,
the NEW name as `name_to`, and the journal `wall` from the NEW row. Emitting both rename
fragments as separate timeline events is wrong.

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
events, adopt its object-table names and streams that are not poisoned. There is no sweep
into other incarnations and no stay-put of conflicting object-table path claims once poison
applies.

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

`/app/data/fit/alpha/` includes ledgers and `expected/timeline.json` plus
`expected/ownership.json`. Those expecteds are normative worked examples of this contract.
Every graded branch below is uniquely determined by composing the rules with those examples.

## Work packs

Process every case directory under `/app/data/work/`. Write outputs under
`/app/output/<case_id>/` where `<case_id>` is the directory name.

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
