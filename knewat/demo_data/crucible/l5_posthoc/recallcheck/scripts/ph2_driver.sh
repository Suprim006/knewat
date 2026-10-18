#!/usr/bin/env bash
S=C:/Users/ACER/AppData/Local/hermes/cache/scratch
LOG=$S/recallcheck
while [ ! -f $LOG/ph-done.txt ]; do sleep 10; done
cd C:/Change_folder_after_HDD/wt-recall/knewat
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
OUT=demo_data/crucible/l5_posthoc/recallcheck
common="--only forgetting --modes off,sep,sep+mult --port 6375 --embedder fastembed --out $OUT"
for N in 5 15; do
  env KNEWAT_L5_LEXICAL_WEIGHT=0 PH_KW_VALUE_ONLY=1 UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python $S/posthoc_wrapper2.py - $common --noise $N --tag recallcheck-posthoc-x4-off-n$N > $LOG/ph-x4-off-n$N.log 2>&1
done
for N in 5 15; do
  env KNEWAT_L5_LEXICAL_WEIGHT=0 PH_KW_VALUE_ONLY=1 UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python $S/posthoc_wrapper2.py MIN_POOL=0,POOL_FACTOR=2 $common --noise $N --tag recallcheck-posthoc-x5-off-n$N > $LOG/ph-x5-off-n$N.log 2>&1
done
echo done > $LOG/ph2-done.txt
