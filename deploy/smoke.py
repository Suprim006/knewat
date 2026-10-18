"""HTTP smoke test of a running Knewat demo, stdlib only (CI image check, post-deploy check, keep-awake).

    python deploy/smoke.py http://127.0.0.1:10000                 # a local container
    python deploy/smoke.py https://knewat-demo.onrender.com --wait 600   # a fresh Render deploy (waits for it to wake)

Reads the seeded ``demo`` tenant and runs read-only Cypher against it; it writes nothing (a write attempt is sent on
purpose and must be refused). Exit 1 if a check fails. ``run(base)`` returns ``[(name, ok, detail)]``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

Result = tuple[str, bool, str]


def http(base: str, path: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(base.rstrip("/") + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jget(base: str, path: str):
    status, _, body = http(base, path)
    return status, (json.loads(body) if body[:1] in (b"{", b"[") else None)


def cypher(base: str, query: str, tenant: str = "demo", params: dict | None = None):
    body = json.dumps({"query": query, **({"params": params} if params else {})}).encode()
    status, hdr, raw = http(base, f"/api/{tenant}/cypher", "POST", body, {"content-type": "application/json"})
    return status, (json.loads(raw) if raw[:1] == b"{" else None), hdr


def wait_healthy(base: str, timeout_s: float) -> float:
    """Poll /healthz?deep=1 until 200 (a sleeping Render service takes about a minute). Returns seconds waited."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        try:
            if http(base, "/healthz?deep=1")[0] == 200:
                return time.monotonic() - t0
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise SystemExit(f"{base} was not healthy after {timeout_s:.0f} s")


def run(base: str) -> list[Result]:
    out: list[Result] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        out.append((name, bool(ok), detail))
        return bool(ok)

    check("/healthz", http(base, "/healthz")[0] == 200)
    status, _, body = http(base, "/")
    check("/ serves the View", status == 200 and b'id="root"' in body, f"{status}, {len(body)} B")
    check("SPA fallback (/cypher -> index.html)", b'id="root"' in http(base, "/cypher")[2])
    check("unknown file 404s", http(base, "/nope.js")[0] == 404)

    status, tenants = jget(base, "/api/tenants")
    names = [t["tenant"] for t in (tenants or {}).get("tenants", [])]
    check("tenants: demo present", "demo" in names, str(names))
    status, inv = jget(base, "/api/demo/inventory")
    n0, e0 = (inv or {}).get("nodes_total"), (inv or {}).get("edges_total")
    check("inventory", status == 200 and (n0 or 0) > 100 and (e0 or 0) > 100, f"{n0} nodes / {e0} edges")
    status, g = jget(base, "/api/demo/graph?limit=500")
    check("Explorer data", status == 200 and len((g or {}).get("nodes", [])) > 50)
    status, res = jget(base, "/api/results")
    check("Results data", status == 200 and bool(res))
    check("unknown tenant 404", http(base, "/api/nosuch/inventory")[0] == 404)
    check(
        "MCP is not served",
        http(base, "/mcp/t/demo", "POST", b"{}", {"content-type": "application/json"})[0] in (404, 405),
    )

    # --- the Cypher console
    status, body, _ = cypher(base, "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC")
    ok = status == 200 and body and body["columns"] == ["label", "n"] and body["row_count"] > 3
    check("cypher: node counts per label", ok, f"{status} {(body or {}).get('row_count')} rows")
    total = sum(r[1] for r in body["rows"]) if ok else None
    check("cypher: counts agree with the inventory", total == n0, f"{total} vs {n0}")
    status, body, _ = cypher(base, "MATCH p = (a)-[e]->(b) RETURN a, e, p LIMIT 1")
    row = (body or {}).get("rows", [[]])[0]
    check(
        "cypher: node, edge and path values",
        status == 200 and [v.get("_type") for v in row] == ["node", "edge", "path"],
        str([v.get("_type") for v in row]),
    )
    status, body, _ = cypher(base, "CALL db.labels() YIELD label RETURN label")
    check("cypher: CALL db.labels()", status == 200 and body["row_count"] > 3)
    status, body, _ = cypher(base, "MATCH (n) WHERE id(n) = $i RETURN id(n) AS i", params={"i": 0})
    check("cypher: parameters", status == 200 and body["rows"] == [[0]], str(body and body.get("rows")))
    status, body, _ = cypher(base, "UNWIND range(1, 900) AS i RETURN i")
    check("cypher: 500-row cap", status == 200 and body["row_count"] == 500 and body["truncated"] is True)
    for label, q in (
        ("CREATE", "CREATE (:Hacked {id: 1})"),
        ("SET", "MATCH (f:Fact) SET f.value = 'x'"),
        ("DELETE", "MATCH (n) DETACH DELETE n"),
    ):
        status, body, _ = cypher(base, q)
        check(
            f"cypher: {label} is refused", status == 400 and "read-only" in (body or {}).get("detail", ""), str(status)
        )
    status, body, _ = cypher(base, "LOAD CSV FROM 'file:///etc/passwd' AS r RETURN r")
    check("cypher: LOAD CSV is refused", status == 400, str(status))
    status, body, _ = cypher(base, "CALL dbms.listConfig()")
    check("cypher: unlisted CALL is refused", status == 400, str(status))
    status, body, _ = cypher(base, "MATCH (n RETURN n")
    check("cypher: syntax errors are a 400 with a message", status == 400 and bool((body or {}).get("detail")))
    check("cypher: unknown tenant is a 404", cypher(base, "RETURN 1", tenant="nosuch")[0] == 404)
    check("cypher: GET is 405", http(base, "/api/demo/cypher")[0] == 405)
    status, inv = jget(base, "/api/demo/inventory")
    check(
        "demo graph unchanged after the write attempts",
        (inv or {}).get("nodes_total") == n0 and (inv or {}).get("edges_total") == e0,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", help="e.g. http://127.0.0.1:10000")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for /healthz?deep=1 first")
    a = ap.parse_args()
    if a.wait:
        print(f"healthy after {wait_healthy(a.base, a.wait):.1f} s", flush=True)
    results = run(a.base)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
