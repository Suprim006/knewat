#!/usr/bin/env bash
# Trial 7: all scored runs, 4 per arm, interleaved (r1: baseline, claudemd, plexus; r2: ...), fully sequential.
# Each run logs to trials/logs/t7_<arm>_<run>.log. Smoke runs (ids smoke*) are separate and excluded by aggregate.py.
# Do not run until the scorer self-test PASSes:  python3 selftest.py
cd "$(dirname "$0")" || exit 1
mkdir -p ../../logs
python3 selftest.py || { echo "selftest failed - not starting scored runs"; exit 1; }
for r in r1 r2 r3 r4; do
  for arm in baseline claudemd plexus; do
    python3 run.py --arm "$arm" --run-id "$r" --plexus-url "${PLEXUS_URL:-http://127.0.0.1:8766}" --max-cost 3 \
      > "../../logs/t7_${arm}_${r}.log" 2>&1
  done
done
python3 aggregate.py > ../../logs/t7_aggregate.md 2>&1
echo "ALL DONE"
