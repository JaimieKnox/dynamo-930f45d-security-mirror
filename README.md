# dynamo/vault-timeline

Reconstruct reincarnated host artifact timelines from a synthetic forensic vault (object table, circular oplog, txnlog gaps) under Security / Digital Forensics.

## Approach

Induce closed reconstruction rules from `/app/data/docs/CONTRACT.md` and the disclosed fit pack, then apply them to held work cases. Identity is `(slot, gen)`. Renames coalesce to MOVE. Journal wall times beat SI times. Oplog wrap seams use txnlog for gaps. Streams do not inherit across generations. Conflicting path claims poison with no revive.

## Environment

Python 3.13 slim image with pytest baked in. Case ledgers live under `/app/data/`.

## Verification

`harbor run -p . --agent oracle` must score 1.0 and `harbor run -p . --agent nop` must score 0.0. The verifier recomputes expecteds from `/tests/inputs` and byte-compares graded JSON outputs.
