Reconstruct forensic timelines for every case directory under `/app/data/work/`. The normative contract is `/app/data/docs/CONTRACT.md`. A disclosed fit pack with worked expecteds is at `/app/data/fit/alpha/` (ledgers plus `expected/timeline.json` and `expected/ownership.json`). Induce the closed rules from that contract and fit pack, then apply them to each work case.

For each work case `<id>`, write `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json` exactly as specified in the contract (schemas, sort orders, identity pairing of slot with gen, rename coalesce to MOVE, journal wall authority, circular oplog wrap with txnlog gap fills, stream non-inheritance across gen, and path poison with no revive).

Success criteria:
1. Every work case directory name under `/app/data/work/` has both output files under `/app/output/<id>/`.
2. Each `timeline.json` matches the contract schema, key order, and JSON text shape.
3. Each `ownership.json` matches the contract schema, key order, sorting, and JSON text shape.
4. Timeline event identities, kinds, times, and ordering match the contract for every work case.
5. Ownership incarnation names, streams, and `poisoned_paths` match the contract for every work case.
