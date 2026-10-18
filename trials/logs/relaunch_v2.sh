#!/usr/bin/env bash
# Wait for each v1 resume runner to exit, then relaunch it on the fixed (v2-cost) runner until 100 turns.
cd /c/Change_folder_after_HDD/trials/prompts
relaunch() {
  arm=$1; id=$2
  until grep -q "^done:" ../logs/t12_resume_${arm}_${id}.log; do sleep 15; done
  for attempt in 1 2 3; do
    done_n=$(python3 -c "import json;print(json.load(open('../logs/t12/${arm}_${id}/state.json'))['done'])")
    [ "$done_n" -ge 100 ] && break
    env -u ANTHROPIC_API_KEY CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000 \
      python3 -u run_trial_1_2_v2.py --arm $arm --run-id $id --max-cost 40 \
      >> ../logs/t12_resume2_${arm}_${id}.log 2>> ../logs/t12_resume2_${arm}_${id}.err
  done
  echo "$arm $id finished: $(tail -n 1 ../logs/t12_resume2_${arm}_${id}.log)"
}
relaunch baseline r1 & relaunch baseline r2 & relaunch plexus r1 & relaunch plexus r2 &
wait
echo ALL_DONE
