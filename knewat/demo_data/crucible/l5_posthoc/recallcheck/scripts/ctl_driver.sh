#!/usr/bin/env bash
# control: the published code (main tip 1ddeb13) through the same L5b harness, on the same DB, today
cd C:/Change_folder_after_HDD/wt-recall-ctl/plexus
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
OUT=C:/Users/ACER/AppData/Local/hermes/cache/scratch/ctl_out
LOG=C:/Users/ACER/AppData/Local/hermes/cache/scratch/recallcheck
mkdir -p $OUT
env UV_PROJECT_ENVIRONMENT=.venv-ctl $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 5 --tag recallcheck-ctl-main-n5 --port 6375 --embedder fastembed --out $OUT > $LOG/ctl-n5.log 2>&1
env UV_PROJECT_ENVIRONMENT=.venv-ctl $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 15 --tag recallcheck-ctl-main-n15 --port 6375 --embedder fastembed --out $OUT > $LOG/ctl-n15.log 2>&1
env UV_PROJECT_ENVIRONMENT=.venv-ctl $UV run python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --noise 5 --burst --tag recallcheck-ctl-main-n5-burst --port 6375 --embedder fastembed --out $OUT > $LOG/ctl-burst.log 2>&1
env UV_PROJECT_ENVIRONMENT=.venv-ctl $UV run python -m plexus.crucible.l5 --only hub --tag recallcheck-ctl-main-hub --port 6375 --embedder fastembed --out $OUT > $LOG/ctl-hub.log 2>&1
echo CTL DONE > $LOG/ctl-done.txt
