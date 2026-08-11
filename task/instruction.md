Reconstruct forensic timelines for every case directory under `/app/data/work/`. The normative contract is `/app/data/docs/CONTRACT.md`. A disclosed fit pack with worked expecteds is at `/app/data/fit/alpha/` (ledgers plus `/app/data/fit/alpha/expected/timeline.json` and `/app/data/fit/alpha/expected/ownership.json`). Induce the closed rules from that contract and fit pack, then apply them to each work case. Held cases may compose multiple rules on one timeline and are not isomorphic copies of the fit pack.

For each work case `<id>`, write `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json` exactly as specified in the contract (schemas, sort orders, identity pairing of slot with gen, rename coalesce to MOVE including across a wrap seam when adjacent in chronological order, journal wall authority, circular oplog wrap with txnlog gap fills, stream non-inheritance across gen, path poison with no revive, orphan `RENAME_NEW`, clean DELETE-then-CREATE transfers, and SI-only residual incarnations with zero journal events).

Success criteria:
1. Every work case directory name under `/app/data/work/` has both `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json`.
2. Each `/app/output/<id>/timeline.json` matches the contract schema, key order, and JSON text shape.
3. Each `/app/output/<id>/ownership.json` matches the contract schema, key order, sorting, and JSON text shape.
4. Timeline event identities, kinds, times, and ordering match the contract for every work case.
5. Ownership incarnation names, streams, and `poisoned_paths` match the contract for every work case.
