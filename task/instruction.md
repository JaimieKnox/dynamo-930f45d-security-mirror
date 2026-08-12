Reconstruct forensic timelines for every case directory under `/app/data/work/`. The normative contract is `/app/data/docs/CONTRACT.md`. Disclosed fit packs live under `/app/data/fit/` (every subdirectory). Each fit pack has ledgers plus normative worked examples at `expected/timeline.json` and `expected/ownership.json`. Induce the closed rules from the contract and every fit pack's expected documents, then apply them to each work case. Held cases may compose multiple rules on one long timeline and are not isomorphic copies of any single fit pack.

For each work case `<id>`, write `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json` exactly as specified in the contract. Also write `/app/output/corpus_index.json` for the whole work corpus as specified in the contract.

Success criteria:
1. Every work case directory name under `/app/data/work/` has both `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json`.
2. Each `/app/output/<id>/timeline.json` matches the contract schema (including trailing `chain`), key order, and JSON text shape.
3. Each `/app/output/<id>/ownership.json` matches the contract schema, key order, sorting, and JSON text shape.
4. Timeline event identities, kinds, times, ordering, and `chain` values match the contract for every work case.
5. Ownership incarnation names, streams, and `poisoned_paths` match the contract for every work case.
6. `/app/output/corpus_index.json` matches the contract schema and aggregates for every work case under `/app/data/work/`.
