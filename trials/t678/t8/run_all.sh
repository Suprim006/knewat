#!/usr/bin/env bash
# Trial 8: all scored runs. 4 per arm, interleaved (r1: baseline, claudemd, plexus; r2: ...), sequential.
# DO NOT run without the orchestrator's go-ahead. Needs the Plexus server on :8766 (toolset core).
# Selftest first: the scorer must PASS before any paid run.
cd "$(dirname "$0")" || exit 1
mkdir -p ../../logs
python3 selftest.py || { echo "scorer self-test FAILED"; exit 1; }
for r in r1 r2 r3 r4; do
  for arm in baseline claudemd plexus; do
    python3 run.py --arm "$arm" --run-id "$r" --plexus-url "${PLEXUS_URL:-http://127.0.0.1:8766}" --max-cost 3 \
      > "../../logs/t8_${arm}_${r}.log" 2>&1
  done
done
echo "ALL DONE"
python3 aggregate.py
