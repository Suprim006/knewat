#!/usr/bin/env bash
cd C:/Change_folder_after_HDD/wt-recall/knewat
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
LOG=C:/Users/ACER/AppData/Local/hermes/cache/scratch/recallcheck
env KNEWAT_TOOLSET=core UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m knewat.crucible.l8.recall_bench --port 6375 --label recallcheck-on --out demo_data/crucible/l8_recallcheck > $LOG/l8-on2.log 2>&1
env KNEWAT_TOOLSET=core KNEWAT_RECALL_LEXICAL_WEIGHT=0 KNEWAT_KW_BYPASS=value UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m knewat.crucible.l8.recall_bench --port 6375 --label recallcheck-posthoc-x1-off --out demo_data/crucible/l8_recallcheck > $LOG/l8-x1off.log 2>&1
echo done > $LOG/l8-phase-done.txt
