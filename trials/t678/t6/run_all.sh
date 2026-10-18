#!/usr/bin/env bash
# Trial 6: all scored runs, 4 per arm, interleaved (r1: baseline, claudemd, plexus; r2: ...), sequential.
# Each run logs to ../../logs/t6_<arm>_<run>.log. NOT run by the harness builder: the orchestrator launches it.
# Pre-flight: python3 selftest.py must print PASS; Plexus server (toolset core) must be up at $PLEXUS_URL.
cd "$(dirname "$0")" || exit 1
PLEXUS_URL="${PLEXUS_URL:-http://127.0.0.1:8766}"
mkdir -p ../../logs/t6
python3 selftest.py | tail -1 | grep -q "PASS" || { echo "scorer self-test failed"; exit 1; }
for r in r1 r2 r3 r4; do
  for arm in baseline claudemd plexus; do
    python3 run.py --arm "$arm" --run-id "$r" --plexus-url "$PLEXUS_URL" --max-cost 3 \
      > "../../logs/t6_${arm}_${r}.log" 2>&1
  done
done
python3 aggregate.py > ../../logs/t6_aggregate.md
echo "ALL DONE"
