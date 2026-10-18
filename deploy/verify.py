"""Local verification gate for the deployment image (docs/deploy.md records its output).

    docker build -f deploy/Dockerfile -t knewat-deploy .
    cd knewat && uv run python ../deploy/verify.py [--image knewat-deploy] [--port 18100] [--keep]

Runs the image exactly as Render does (`-m 512m --cpus 0.5 -e PORT=10000 -p 127.0.0.1:<port>:10000`), then checks boot
time, peak memory (docker stats sampled all the way + /proc VmHWM + cgroup peak), everything in `deploy/smoke.py` (the
View, the API pages, the Cypher console and its refusals), the Cypher rate limit and body cap, that a Cypher flood
leaves the View API usable, and that a restart reseeds cleanly. Exit 1 if a check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402

NAME = "knewat-deploy-test"
RESULTS: list[tuple[str, bool, str]] = []


def sh(*cmd: str, check: bool = False) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return (p.stdout + p.stderr).strip()


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""), flush=True)
    return ok


def http(base: str, path: str, method="GET", body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jget(base: str, path: str):
    status, _, body = http(base, path)
    return status, (json.loads(body) if body[:1] in (b"{", b"[") else None)


# ----------------------------------------------------------------------------------------------- memory
class Sampler(threading.Thread):
    """Polls `docker stats` for the whole run and keeps the maximum (docker's number excludes reclaimable cache)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.max_mib = 0.0
        self.samples = 0

    def run(self):
        while not self.stop.is_set():
            out = sh("docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", NAME)
            m = re.match(r"([\d.]+)(MiB|GiB|KiB)", out)
            if m:
                v = float(m.group(1)) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[m.group(2)]
                self.max_mib = max(self.max_mib, v)
                self.samples += 1


def procs() -> dict[str, tuple[float, float]]:
    """comm -> (VmRSS MiB, VmHWM MiB) of the largest process of that name (the healthcheck is a second `python`)."""
    script = (
        "for p in /proc/[0-9]*; do [ -r $p/status ] || continue; "
        "echo \"$(cat $p/comm) $(grep -E '^(VmRSS|VmHWM):' $p/status | tr -s ' ' | tr '\n' ' ')\"; done"
    )
    out: dict[str, tuple[float, float]] = {}
    for line in sh("docker", "exec", NAME, "sh", "-c", script).splitlines():
        m = re.match(r"(\S+) VmHWM:\s+(\d+) kB\s+VmRSS:\s+(\d+) kB", line)
        if m and m.group(1) not in ("sh", "grep", "cat", "tr"):
            cur = (int(m.group(3)) / 1024, int(m.group(2)) / 1024)
            if m.group(1) not in out or cur[0] > out[m.group(1)][0]:
                out[m.group(1)] = cur
    return out


def cgroup_peak_mib() -> float | None:
    for f in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
        out = sh("docker", "exec", NAME, "cat", f)
        if out.isdigit():
            return int(out) / 2**20
    return None


def snapshot(label: str, sampler: Sampler) -> dict:
    p = procs()
    rss = sum(v[0] for v in p.values())
    hwm = sum(v[1] for v in p.values())
    peak = cgroup_peak_mib()
    snap = {
        "label": label,
        "docker_stats_max_mib": round(sampler.max_mib, 1),
        "rss_now_mib": round(rss, 1),
        "rss_hwm_sum_mib": round(hwm, 1),
        "cgroup_peak_mib": None if peak is None else round(peak, 1),
        "procs": {k: f"rss {v[0]:.0f} / hwm {v[1]:.0f}" for k, v in p.items()},
    }
    print("MEM", json.dumps(snap), flush=True)
    return snap


# ----------------------------------------------------------------------------------------------- run / wait
def wait_healthy(base: str, timeout=240.0) -> float:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if http(base, "/healthz?deep=1")[0] == 200:
                return time.monotonic() - t0
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    raise SystemExit("never became healthy:\n" + sh("docker", "logs", "--tail", "40", NAME))


# ----------------------------------------------------------------------------------------------- main
def tenant_inventory(base: str, tenant: str):
    status, inv = jget(base, f"/api/{tenant}/inventory")
    return status, (inv or {}).get("nodes_total"), (inv or {}).get("edges_total")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="knewat-deploy")
    ap.add_argument("--port", type=int, default=18100)
    ap.add_argument("--keep", action="store_true", help="leave the container running")
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    report: dict = {}

    sh("docker", "rm", "-f", NAME)
    t0 = time.monotonic()
    sh("docker", "run", "-d", "--name", NAME, "-m", "512m", "--cpus", "0.5", "-e", "PORT=10000",
       "-p", f"127.0.0.1:{a.port}:10000", a.image, check=True)  # fmt: skip
    sampler = Sampler()
    sampler.start()
    try:
        wait_healthy(base)
        boot_s = time.monotonic() - t0
        report["boot_to_healthy_s"] = round(boot_s, 2)
        check("boot to healthy", boot_s < 120, f"{boot_s:.1f}s from `docker run` to /healthz?deep=1 = 200")
        m = re.search(r"boot complete in ([\d.]+)s", sh("docker", "logs", NAME))
        report["entrypoint_boot_s"] = float(m.group(1)) if m else None
        report["mem_boot"] = snapshot("just after healthy", sampler)

        st, nodes, edges = tenant_inventory(base, "demo")
        st2, nodes2, edges2 = tenant_inventory(base, "demo_scripted")
        check("both demo tenants seeded", st == st2 == 200 and nodes and nodes2, f"{nodes}/{edges}, {nodes2}/{edges2}")
        for name, ok, detail in smoke.run(base):
            check(name, ok, detail)
        sse = subprocess.run(
            ["curl", "-s", "-N", "-m", "3", f"{base}/api/demo/stream?after=0&poll_ms=500"], capture_output=True
        ).stdout.decode("utf-8", "replace")
        check(
            "Flow SSE stream delivers events", "event: toolcall" in sse, f"{sse.count('event: toolcall')} events in 3s"
        )
        report["mem_after_smoke"] = snapshot("after the smoke checks", sampler)

        # --- the Cypher console under load: a runaway query times out and the box stays up
        t1 = time.monotonic()
        status, body, _ = smoke.cypher(base, "MATCH (a),(b),(c),(d) RETURN count(*)")
        check(
            "a runaway cartesian product times out (408)", status == 408, f"{status} after {time.monotonic() - t1:.1f}s"
        )
        check("/healthz after the runaway query", http(base, "/healthz?deep=1")[0] == 200)
        report["mem_after_runaway"] = snapshot("after a runaway query", sampler)
        big = json.dumps({"query": "RETURN 1 /*" + "x" * (20 * 1024) + "*/"}).encode()
        check(
            "Cypher body cap (20 KiB -> 413)",
            http(base, "/api/demo/cypher", "POST", big, {"content-type": "application/json"})[0] == 413,
        )
        time.sleep(30)  # let the per-IP Cypher bucket (20/min) refill
        codes = [smoke.cypher(base, "RETURN 1")[0] for _ in range(40)]
        n429 = codes.count(429)
        check("Cypher rate limit triggers (20/min per IP)", n429 > 0, f"{n429}/40 got 429")
        retry = smoke.cypher(base, "RETURN 1")
        check("429 carries Retry-After", retry[0] == 429 and any(k.lower() == "retry-after" for k in retry[2]))
        check("View API unaffected by the Cypher bucket", http(base, "/api/tenants")[0] == 200)
        report["mem_after_rate"] = snapshot("after the rate-limit burst", sampler)

        # --- restart reseeds cleanly
        t2 = time.monotonic()
        sh("docker", "restart", "-t", "5", NAME)
        wait_healthy(base)
        report["restart_to_healthy_s"] = round(time.monotonic() - t2, 2)
        check(
            "restart reseeds both demo tenants",
            (tenant_inventory(base, "demo")[1:], tenant_inventory(base, "demo_scripted")[1:])
            == ((nodes, edges), (nodes2, edges2)),
            f"restart to healthy {report['restart_to_healthy_s']}s",
        )
        check("no tracebacks in logs", "Traceback" not in sh("docker", "logs", NAME))
        report["mem_after_restart"] = snapshot("after restart", sampler)

        sampler.stop.set()
        sampler.join(timeout=10)
        report["docker_stats_peak_mib"] = round(sampler.max_mib, 1)
        report["docker_stats_samples"] = sampler.samples
        print("REPORT", json.dumps(report, indent=2))
    finally:
        sampler.stop.set()
        if not a.keep:
            sh("docker", "rm", "-f", NAME)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
