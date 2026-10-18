#!/usr/bin/env bash
# recall-check driver: sequential, logs to $LOGDIR. Inline env only.
set -u
cd C:/Change_folder_after_HDD/wt-recall/plexus
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
PORT=6375
LOGDIR=C:/Users/ACER/AppData/Local/hermes/cache/scratch/recallcheck
mkdir -p "$LOGDIR"
run() { # name, then command...
  local name=$1; shift
  echo "=== $(date +%H:%M:%S) START $name" | tee -a "$LOGDIR/driver.log"
  "$@" > "$LOGDIR/$name.log" 2>&1
  echo "=== $(date +%H:%M:%S) END $name rc=$?" | tee -a "$LOGDIR/driver.log"
}
PY="env UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python"

# 1. no-LLM recall bench (L8), ON = shipped default (env unset), OFF = 0
run l8-on  env PLEXUS_TOOLSET=core UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l8.recall_bench --port $PORT --label recallcheck-on  --out demo_data/crucible/l8_recallcheck
run l8-off env PLEXUS_TOOLSET=core PLEXUS_RECALL_LEXICAL_WEIGHT=0 UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l8.recall_bench --port $PORT --label recallcheck-off --out demo_data/crucible/l8_recallcheck

# 2. L5b + hub, OFF then ON
for W in off on; do
  if [ $W = on ]; then LW=0.5; else LW=0; fi
  run l5-$W-n5     env PLEXUS_L5_LEXICAL_WEIGHT=$LW UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 5  --tag recallcheck-$W-n5       --port $PORT --embedder fastembed
  run l5-$W-n15    env PLEXUS_L5_LEXICAL_WEIGHT=$LW UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 15 --tag recallcheck-$W-n15      --port $PORT --embedder fastembed
  run l5-$W-burst  env PLEXUS_L5_LEXICAL_WEIGHT=$LW UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 5 --burst --tag recallcheck-$W-n5-burst --port $PORT --embedder fastembed
  run l5-$W-hub    env PLEXUS_L5_LEXICAL_WEIGHT=$LW UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l5 --only hub --tag recallcheck-$W-hub --port $PORT --embedder fastembed
done

# 3. L6-C, OFF then ON (all five arms, hash embedder as published)
run l6c-off env PLEXUS_RECALL_LEXICAL_WEIGHT=0 UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l6.run_c --port $PORT --scale 1.0 --tag recallcheck-off
run l6c-on  env UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m plexus.crucible.l6.run_c --port $PORT --scale 1.0 --tag recallcheck-on

echo "=== PHASE1 DONE $(date +%H:%M:%S)" | tee -a "$LOGDIR/driver.log"
