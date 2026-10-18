#!/usr/bin/env bash
S=C:/Users/ACER/AppData/Local/hermes/cache/scratch
LOG=$S/recallcheck
while ! grep -q "^wrote" $LOG/l8-final.log 2>/dev/null; do sleep 10; done
cd C:/Change_folder_after_HDD/wt-recall/knewat
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
for cmd in "det --port 6375" "postfix --port 6375 --kills 200" "conc --port 6375 --runs 10 --seconds 6"; do
  name=${cmd%% *}
  env UV_PROJECT_ENVIRONMENT=.venv-recall $UV run python -m knewat.crucible.l6.run $cmd > $LOG/l6-$name.log 2>&1
done
echo done > $LOG/l6-done.txt
