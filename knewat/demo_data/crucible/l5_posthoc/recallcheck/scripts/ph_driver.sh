#!/usr/bin/env bash
# post-hoc attribution runs (BASELINE "Recall-check addendum 1"); waits for the L6-C ON run of the main driver to finish
S=C:/Users/ACER/AppData/Local/hermes/cache/scratch
LOG=$S/recallcheck
while ! grep -q "results:" $LOG/l6c-on.log 2>/dev/null; do sleep 15; done
cd C:/Change_folder_after_HDD/wt-recall/knewat
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
OUT=demo_data/crucible/l5_posthoc/recallcheck
P="env UV_PROJECT_ENVIRONMENT=.venv-recall"
common="--only forgetting --modes off,sep,sep+mult --port 6375 --embedder fastembed --out $OUT"
ph() { # name consts lexical envs... ; N=5 and N=15
  local name=$1 consts=$2 lw=$3; shift 3
  for N in 5 15; do
    env KNEWAT_L5_LEXICAL_WEIGHT=$lw "$@" UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python $S/posthoc_wrapper.py "$consts" $common --noise $N --tag recallcheck-posthoc-$name-n$N > $LOG/ph-$name-n$N.log 2>&1
  done
}
ph x1-off  -                       0   KNEWAT_KW_BYPASS=value
ph x1-on   -                       0.5 KNEWAT_KW_BYPASS=value
ph x2-off  MAX_KEYWORDS=0          0
ph x3-off  MIN_POOL=0,POOL_FACTOR=2 0
echo PH DONE > $LOG/ph-done.txt
