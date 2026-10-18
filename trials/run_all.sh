#!/usr/bin/env bash
# Full battery. Trials 3/4: one chain per arm (3 in parallel), r1..r4 sequential.
# Trials 1/2: two chains per arm (4 in parallel), each doing two runs. Re-running is safe:
# t12 runs resume from their last completed turn; t34 runs restart cleanly.
cd "$(dirname "$0")/prompts" || exit 1
mkdir -p ../logs
for arm in baseline claudemd knewat; do
  ( for r in r1 r2 r3 r4; do python run_trial_3_4_v2.py --arm "$arm" --run-id "$r"; done ) \
    > "../logs/t34_${arm}.log" 2>&1 &
done
for arm in baseline knewat; do
  ( python run_trial_1_2_v2.py --arm "$arm" --run-id r1; python run_trial_1_2_v2.py --arm "$arm" --run-id r3 ) \
    > "../logs/t12_${arm}_a.log" 2>&1 &
  ( python run_trial_1_2_v2.py --arm "$arm" --run-id r2; python run_trial_1_2_v2.py --arm "$arm" --run-id r4 ) \
    > "../logs/t12_${arm}_b.log" 2>&1 &
done
wait
echo "ALL DONE"
