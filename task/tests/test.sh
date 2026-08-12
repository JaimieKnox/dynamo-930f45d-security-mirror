#!/bin/bash
# Verifier entry. Always write reward.txt. Install nothing at verify time.
# Phase A seals expectations from the independent reference engine and removes it.
# Phase B grades agent outputs with no oracle import (R181).
set -u

mkdir -p /logs/verifie
reward=/logs/verifier/reward.txt

# Isolate pytest from agent-writable trees (R193 / R210).
export PYTHONPATH=/tests
export PYTHONSAFEPATH=1
cd /tests || {
  echo 0 > "$reward"
  exit 0
}

set +e
python3 -B /tests/derive_expectations.py
phase_one=$?
set -e

# Belt-and-braces: ensure reference modules are gone even if derive crashed mid-way.
rm -f /tests/reference_engine.py /tests/wrong_models.py /tests/derive_expectations.py
find /tests -maxdepth 2 -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

if [ "$phase_one" -eq 0 ]; then
  set +e
  python3 -P -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
  rc=$?
  set -e
else
  echo "phase A failed with status $phase_one"
  rc=$phase_one
fi

if [ "$rc" -eq 0 ]; then
  echo 1 > "$reward"
else
  echo 0 > "$reward"
fi
exit 0
