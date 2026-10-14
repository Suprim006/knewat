"""Local verification gate for the deployment image (docs/deploy.md records its output).

    docker build -f deploy/Dockerfile -t plexus-deploy .
    cd plexus && uv run python ../deploy/verify.py [--image plexus-deploy] [--port 18100] [--keep]

Runs the image exactly as the spec says (`-m 512m --cpus 0.5 -e PORT=10000 -p 127.0.0.1:<port>:10000`), then checks:
boot time, peak RSS (docker stats sampled all the way + /proc VmHWM + cgroup peak), the View's API pages for the demo
tenant, the static View, a full MCP session on a team_ tenant (start_session, assert_fact, recall), the read-only demo
tenants, forbidden tenants, the body cap, the rate limit, and that a restart reseeds cleanly. Exit 1 if a check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

NAME = "plexus-deploy-test"
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


# ----------------------------------------------------------------------------------------------- MCP
async def mcp_session(url: str, agent: str) -> dict:
    from mcp import Client

    out: dict = {}
    async with Client(url) as c:
        tools = await c.list_tools()
        out["tools"] = len(tools.tools)
        s = await c.call_tool("start_session", {"agent_id": agent, "agent_role": "verifier"})
        out["start_session"] = (not s.is_error, json.loads(s.content[0].text) if not s.is_error else s.content[0].text)
        f = await c.call_tool(
            "assert_fact",
            {"agent_id": agent, "subject": "deploy", "predicate": "ram_limit", "value": "512 MB on Render Free"},
        )
        out["assert_fact"] = (not f.is_error, json.loads(f.content[0].text) if not f.is_error else f.content[0].text)
        t0 = time.monotonic()
        r = await c.call_tool(
            "recall", {"agent_id": agent, "query": "how much memory does the deployment have", "k": 3}
        )
        out["recall_s"] = round(time.monotonic() - t0, 2)
        out["recall"] = (not r.is_error, json.loads(r.content[0].text) if not r.is_error else r.content[0].text)
    return out


async def one_agent(base: str, i: int) -> int:
    """A busy agent on its own team tenant: 5 assert_fact + 3 recall (every recall embeds the query)."""
    from mcp import Client

    n = 0
    async with Client(f"{base}/mcp/t/team_load{i:02d}") as c:
        await c.call_tool("start_session", {"agent_id": f"load-{i}", "agent_role": "load"})
        for j in range(5):
            r = await c.call_tool(
                "assert_fact",
                {
                    "agent_id": f"load-{i}",
                    "subject": f"svc{j}",
                    "predicate": "owner",
                    "value": f"team {i} owns service {j}",
                },
            )
            n += not r.is_error
        for q in ("who owns service 3", "which team owns svc5", "ownership of services"):
            r = await c.call_tool("recall", {"agent_id": f"load-{i}", "query": q, "k": 5})
            n += not r.is_error
    return n


async def load(base: str, agents: int) -> list[int]:
    return list(await asyncio.gather(*(one_agent(base, i) for i in range(1, agents + 1))))


async def demo_attempt(url: str) -> dict:
    from mcp import Client

    async with Client(url) as c:
        tools = await c.list_tools()
        r = await c.call_tool("assert_fact", {"agent_id": "intruder", "subject": "x", "predicate": "y", "value": "z"})
        return {"tools": len(tools.tools), "is_error": r.is_error, "text": r.content[0].text if r.content else ""}


def tenant_inventory(base: str, tenant: str):
    status, inv = jget(base, f"/api/{tenant}/inventory")
    return status, (inv or {}).get("nodes_total"), (inv or {}).get("edges_total")


# ----------------------------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="plexus-deploy")
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
        logs = sh("docker", "logs", NAME)
        m = re.search(r"boot complete in ([\d.]+)s", logs)
        report["entrypoint_boot_s"] = float(m.group(1)) if m else None
        report["mem_boot"] = snapshot("just after healthy", sampler)
        time.sleep(25)  # let the embedder prewarm finish
        report["mem_idle"] = snapshot("idle, model prewarmed", sampler)

        # --- the static View
        status, hdr, body = http(base, "/")
        html = body.decode("utf-8", "replace")
        check(
            "/ serves the View",
            status == 200 and '<div id="root"' in html and "/assets/" in html,
            f"{status}, {len(body)} B",
        )
        asset = re.search(r'(?:src|href)="(/assets/[^"]+\.js)"', html)
        check(
            "hashed JS asset served",
            bool(asset) and http(base, asset.group(1))[0] == 200,
            asset.group(1) if asset else "",
        )
        check("SPA fallback (/explorer -> index.html)", b'id="root"' in http(base, "/explorer")[2])
        check("unknown file 404s", http(base, "/nope.js")[0] == 404)
        check("/healthz", http(base, "/healthz")[0] == 200)

        # --- the API pages for the `demo` tenant
        status, tenants = jget(base, "/api/tenants")
        names = [t["tenant"] for t in (tenants or {}).get("tenants", [])]
        check("tenants: demo + demo_scripted present", {"demo", "demo_scripted"} <= set(names), str(names))
        st, nodes, edges = tenant_inventory(base, "demo")
        check(
            "Inventory page data (demo)", st == 200 and nodes == 247 and edges == 708, f"{nodes} nodes / {edges} edges"
        )
        st, nodes2, edges2 = tenant_inventory(base, "demo_scripted")
        check("Inventory (demo_scripted)", st == 200 and nodes2 == 199 and edges2 == 581, f"{nodes2} / {edges2}")
        st, g = jget(base, "/api/demo/graph?limit=500")
        check(
            "Explorer data",
            st == 200 and len(g["nodes"]) > 50 and len(g["edges"]) > 50,
            f"{len(g['nodes'])} nodes, {len(g['edges'])} edges",
        )
        st, fl = jget(base, "/api/demo/flow?limit=1000")
        events = (fl or {}).get("events") or (fl or {}).get("calls") or []
        check("Flow data", st == 200 and len(events) > 20, f"{len(events)} tool calls")
        step_n = next((e["step_n"] for e in events if e.get("step_n")), None)
        st, step = jget(base, f"/api/demo/step/{step_n}") if step_n else (0, None)
        check("Time Machine data (step/{n})", st == 200 and bool(step), f"step {step_n}")
        dec = next((n for n in g["nodes"] if n.get("label") == "Decision"), None) if g else None
        st, why = jget(base, f"/api/demo/why/{dec['id']}") if dec else (0, None)
        check("Why data (why/{decision})", st == 200 and bool(why), f"decision {dec['id'][:8] if dec else None}")
        rid = next((n["id"] for n in g["nodes"] if n.get("label") == "Recall"), None) if g else None
        st, rc = jget(base, f"/api/demo/recall/{rid}") if rid else (0, None)
        check("Recall explanation data", st == 200 and bool(rc), f"recall {rid[:8] if rid else None}")
        st, res = jget(base, "/api/results")
        check("Results page data", st == 200 and bool(res), f"{st}")
        check("unknown tenant 404", http(base, "/api/nosuch/inventory")[0] == 404)

        # --- MCP: a write tenant
        url = f"{base}/mcp/t/team_test01"
        try:
            sess = asyncio.run(mcp_session(url, "verify-agent"))
            ok = sess["start_session"][0] and sess["assert_fact"][0] and sess["recall"][0]
            facts = sess["recall"][1].get("facts", []) if sess["recall"][0] else []
            check(
                "MCP team_test01: start_session + assert_fact + recall",
                ok and any("512" in f.get("value", "") for f in facts),
                f"{sess['tools']} tools; first recall {sess['recall_s']}s; {len(facts)} fact(s)",
            )
            report["first_recall_s"] = sess["recall_s"]
        except Exception as exc:  # noqa: BLE001
            check("MCP team_test01: start_session + assert_fact + recall", False, repr(exc)[:300])
        report["mem_after_recall"] = snapshot("after MCP recall", sampler)
        st, tn = jget(base, "/api/tenants")
        check("team_test01 graph now listed", "team_test01" in [t["tenant"] for t in tn["tenants"]])
        st, n_team, _ = tenant_inventory(base, "team_test01")
        check("team_test01 has data (Session/Fact/ToolCall)", st == 200 and (n_team or 0) > 3, f"{n_team} nodes")

        # --- load: several agents at once (each call embeds on 0.5 CPU)
        t_load = time.monotonic()
        try:
            ok_calls = asyncio.run(load(base, 4))
            check(
                "4 concurrent agents x (5 assert_fact + 3 recall)",
                all(n == 8 for n in ok_calls),
                f"{ok_calls}, {time.monotonic() - t_load:.1f}s",
            )
        except Exception as exc:  # noqa: BLE001
            check("4 concurrent agents x (5 assert_fact + 3 recall)", False, repr(exc)[:300])
        report["load_s"] = round(time.monotonic() - t_load, 1)
        report["mem_after_load"] = snapshot("after 4 concurrent agents", sampler)
        time.sleep(50)  # the per-IP bucket (60/min) is nearly empty after the burst: let it refill for the next checks

        # --- MCP: read-only + forbidden
        try:
            d = asyncio.run(demo_attempt(f"{base}/mcp/t/demo"))
            check(
                "write to /mcp/t/demo rejected with a clear message",
                d["is_error"] and "read-only" in d["text"],
                d["text"][:90],
            )
        except Exception as exc:  # noqa: BLE001
            check("write to /mcp/t/demo rejected with a clear message", False, repr(exc)[:300])
        st, n_after, e_after = tenant_inventory(base, "demo")
        check("demo graph unchanged after the attempt", (n_after, e_after) == (247, 708), f"{n_after}/{e_after}")
        init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode()
        hdrs = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        for t in ("acme", "team_x", "default"):
            check(f"forbidden tenant {t}", http(base, f"/mcp/t/{t}", "POST", init, hdrs)[0] == 403)
        big = b"x" * (600 * 1024)
        check("body cap (600 KiB -> 413)", http(base, "/mcp/t/team_test01", "POST", big, hdrs)[0] == 413)
        report["mem_before_rate"] = snapshot("before rate-limit burst", sampler)

        # --- rate limit
        codes = []
        for _ in range(90):
            codes.append(http(base, "/mcp/t/team_test01", "POST", b"{}", hdrs)[0])
        n429 = codes.count(429)
        first = codes.index(429) + 1 if n429 else None
        check(
            "rate limit triggers (60/min per IP)", n429 > 0, f"{n429}/90 got 429; first at request {first} of the burst"
        )
        retry = http(base, "/mcp/t/team_test01", "POST", b"{}", hdrs)
        check("429 carries Retry-After", retry[0] == 429 and any(k.lower() == "retry-after" for k in retry[1]))
        st = http(base, "/api/tenants")[0]
        check("View API unaffected by the MCP bucket", st == 200)
        report["mem_after_rate"] = snapshot("after rate-limit burst", sampler)

        # --- restart reseeds cleanly
        t1 = time.monotonic()
        sh("docker", "restart", "-t", "5", NAME)
        wait_healthy(base)
        report["restart_to_healthy_s"] = round(time.monotonic() - t1, 2)
        st, n1, e1 = tenant_inventory(base, "demo")
        st2, n2, e2 = tenant_inventory(base, "demo_scripted")
        check(
            "restart reseeds both demo tenants",
            (n1, e1, n2, e2) == (247, 708, 199, 581),
            f"restart to healthy {report['restart_to_healthy_s']}s",
        )
        tn = jget(base, "/api/tenants")[1]
        check("restart wipes team_ graphs (ephemeral)", "team_test01" not in [t["tenant"] for t in tn["tenants"]])
        logs = sh("docker", "logs", NAME)
        check("no tracebacks in logs", "Traceback" not in logs, "")
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
