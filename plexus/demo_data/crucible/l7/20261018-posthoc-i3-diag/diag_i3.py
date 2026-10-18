"""POST-HOC diagnostic (not a registered run): I3 F-multi with per-kill read-back of acknowledged
close-outs and
INFO persistence before each kill. Same logic as l7.i.run_i3_arm; port 6392 / plexus-db-92 only."""

import json
import random
import shutil
import sys
import tempfile
import threading
import time
import uuid

import redis

from plexus.crucible.l7 import common, i

PORT = 6392
host = "127.0.0.1"
arm_name = "F-multi"
kills = int(sys.argv[1]) if len(sys.argv) > 1 else 20
container = common.container_for_port(PORT)
assert container == "plexus-db-92"
root = tempfile.mkdtemp(prefix="l7i-diag-")
run = uuid.uuid4().hex[:6]
arm = i.new_world(arm_name, host, PORT, root, run)
rng = random.Random(common.SEED + 300 + 1)
intents, acked, lock = {}, {}, threading.Lock()
prefix = i.SLUG[arm_name] + run
checked_ok = set()
rows = []
for k in range(kills):
    stop = threading.Event()
    ready = threading.Barrier(5)

    def work(w, k=k, stop=stop, ready=ready):
        a = None
        try:
            a = i.make_arm(arm_name, host, PORT, arm.tenant, root)
            a.connect()
        except Exception:
            pass
        try:
            ready.wait(120)
        except threading.BrokenBarrierError:
            return
        if a is None:
            return
        n = 0
        while not stop.is_set():
            co = f"{prefix}k{k}w{w}.{n}"
            n += 1
            try:
                task, v = a.new_task(co)
                with lock:
                    intents[co] = {"task": task, "v": v}
                ok = a.closeout(co, task, v, v)
                with lock:
                    acked[co] = ok
            except Exception:
                return

    ths = [threading.Thread(target=work, args=(w,), daemon=True) for w in range(4)]
    for t in ths:
        t.start()
    ready.wait(120)
    time.sleep(rng.uniform(0.4, 1.6))
    pers = {}
    try:
        r = redis.Redis(host=host, port=PORT, socket_timeout=3)
        inf = r.info("persistence")
        pers = {
            x: inf.get(x)
            for x in (
                "aof_delayed_fsync",
                "aof_pending_bio_fsync",
                "aof_buffer_length",
                "aof_pending_rewrite",
                "aof_rewrite_in_progress",
                "aof_last_write_status",
                "aof_current_size",
            )
        }
        r.close()
    except Exception as e:
        pers = {"err": type(e).__name__}
    acked_before = len(acked)
    t_kill = time.time()
    common.docker("kill", "-s", "KILL", container)
    stop.set()
    for t in ths:
        t.join(90)
    common.docker("start", container)
    rec = i.recover(host, PORT, container, arm.gname)
    arm.connect()
    states, items = arm.states(prefix, intents)
    new_acked = [co for co in acked if co not in checked_ok]
    lost = [co for co in new_acked if states.get(co) != "complete"]
    for co in new_acked:
        if states.get(co) == "complete":
            checked_ok.add(co)
    rows.append(
        {
            "k": k,
            "acked_this_kill": len(new_acked),
            "lost_acked_this_kill": len(lost),
            "lost_states": {s: sum(1 for co in lost if states.get(co) == s) for s in ("partial", "absent")},
            "pers_before_kill": pers,
            "ready_s": rec["ready_after_s"],
            "up": rec["up"],
        }
    )
    print(time.strftime("%H:%M:%S"), json.dumps(rows[-1]), flush=True)
    for co in lost:
        checked_ok.add(co)  # count each lost co once
arm.close()
arm.drop()
shutil.rmtree(root, ignore_errors=True)
print("TOTAL lost acked:", sum(r["lost_acked_this_kill"] for r in rows), "acked:", len(acked))
json.dump(rows, open("C:/tmp/l7i/diag_i3.json", "w"), indent=1)
