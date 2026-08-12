Reconstruct forensic timelines for every case directory under `/app/data/work/`. The normative contract is `/app/data/docs/CONTRACT.md`. A disclosed fit pack is at `/app/data/fit/alpha/` with ledgers, normative worked examples under `/app/data/fit/alpha/expected/` (`timeline.json` and `ownership.json`), and `/app/data/fit/alpha/smoke_digests.json`. An optional fit-smoke helper package is shipped under `/app/engine/` (orchestration in `pipeline.py`, with a thin `starter.py` re-export). The expected documents illustrate the contract on the fit ledgers. The smoke digests are sha256 of the JSON text that helper emits for those fit ledgers and only check that the helper still reproduces its fit calibration. Induce the closed rules from the contract and fit expecteds, then apply them to each work case. Held cases may compose multiple rules on one long timeline and are not isomorphic copies of the fit pack.

For each work case `<id>`, write `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json` exactly as specified in the contract. Also write `/app/output/corpus_index.json` for the whole work corpus as specified in the contract.

Success criteria:
1. Every work case directory name under `/app/data/work/` has both `/app/output/<id>/timeline.json` and `/app/output/<id>/ownership.json`.
2. Each `/app/output/<id>/timeline.json` matches the contract schema, key order, and JSON text shape.
3. Each `/app/output/<id>/ownership.json` matches the contract schema, key order, sorting, and JSON text shape.
4. Timeline event identities, kinds, times, and ordering match the contract for every work case.
5. Ownership incarnation names, streams, and `poisoned_paths` match the contract for every work case.
6. `/app/output/corpus_index.json` matches the contract schema and aggregates for every work case under `/app/data/work/`.
