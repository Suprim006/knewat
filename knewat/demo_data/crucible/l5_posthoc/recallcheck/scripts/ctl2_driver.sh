cd C:/Change_folder_after_HDD/wt-recall-ctl2/plexus
UV=C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe
OUT=C:/Users/ACER/AppData/Local/hermes/cache/scratch/ctl_out
LOG=C:/Users/ACER/AppData/Local/hermes/cache/scratch/recallcheck
for N in 5 15; do
env UV_PROJECT_ENVIRONMENT=.venv-ctl2 $UV run python -m plexus.crucible.l5 --only forgetting --noise $N --tag recallcheck-ctl-p12-n$N --port 6375 --embedder fastembed --out $OUT > $LOG/ctl2-n$N.log 2>&1
done
echo done > $LOG/ctl2-done.txt
