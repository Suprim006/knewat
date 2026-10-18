"""Crucible L7 family G: multi-tenancy at scale (graph per tenant vs SQLite file per tenant vs one shared SQLite file).

    python -m plexus.crucible.l7.g run --port 6365 --scale {dev,full} --out <dir> [--parts G1,G2,G3,G4]

Tenant counts are cumulative (tenants 0..N-1 exist when N is measured). Port 6365 / container plexus-db-65 only.
G1 creation, G2 footprint, G3a product-path leakage (gate: 0), G3b raw-channel matrix, G4 latency vs N.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import redis

from plexus.crucible.l7 import common, g_gen
from plexus.crucible.l7.g_arms import (
    SHARED_TABLES,
    FArm,
    SFileArm,
    SSharedArm,
    tenant_predicate_sites,
)  # fmt: skip
from plexus.crucible.l7.g_gen import tenant_name, tenant_world
from plexus.graph.tenancy import graph_name

CONTAINER = "plexus-db-65"
SCALES = {
    "dev": {
        "ns": (1, 2, 20, 200),
        "ops": 300,
        "pairs": 50,
        "pairs_raw": 20,
        "empty": (1, 2, 20, 200),
        "mem_sample": 200,
    },
    "full-n200": {  # the registered full run's reachable levels (N = 2,000 was not reached under its memory cap)
        "ns": (1, 2, 20, 200),
        "ops": 2000,
        "pairs": 200,
        "pairs_raw": 50,
        "empty": (1, 2, 20, 200),
        "mem_sample": 200,
    },
    "full": {
        "ns": (1, 2, 20, 200, 2000),
        "ops": 2000,
        "pairs": 200,
        "pairs_raw": 50,
        "empty": (1, 2, 20, 200),
        "mem_sample": 200,
    },
}
OPS = ("q1", "q2", "q3", "q4")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _rc(host: str, port: int, **kw: Any) -> redis.Redis:
    return redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=60, **kw)


# ------------------------------------------------------------------------------------------------ server footprint
def used_memory(r: redis.Redis) -> int:
    return int(r.info("memory")["used_memory"])


SKIP_RDB = False  # --skip-rdb: no BGSAVE (a fork + copy-on-write needs memory a near-full container lacks)


def rdb_size(r: redis.Redis) -> int | None:
    """BGSAVE, wait for it, return the size of dump.rdb in the container's data dir (docker exec ls -l)."""
    if SKIP_RDB:
        return None
    try:
        r.bgsave()
    except redis.ResponseError:
        pass
    t0 = time.time()
    while time.time() - t0 < 300:
        if int(r.info("persistence")["rdb_bgsave_in_progress"]) == 0:
            break
        time.sleep(0.2)
    out = common.docker("exec", CONTAINER, "ls", "-l", "/var/lib/falkordb/data").stdout
    for ln in out.splitlines():
        parts = ln.split()
        if parts and parts[-1] == "dump.rdb":
            return int(parts[4])
    return None


def mem_usage(r: redis.Redis, key: str) -> int | None:
    v = r.execute_command("MEMORY", "USAGE", key)
    return int(v) if v is not None else None


def summ(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0}
    xs = sorted(xs)
    return {
        "n": len(xs),
        "min": xs[0],
        "p50": xs[len(xs) // 2],
        "mean": round(sum(xs) / len(xs), 1),
        "max": xs[-1],
    }


# ------------------------------------------------------------------------------------------------ G2 empty footprint
def empty_footprint(host: str, port: int, root: Path, ns: tuple[int, ...], farm: FArm) -> dict[str, Any]:
    """Schema-only tenants: F (INFO used_memory delta, MEMORY USAGE, RDB size) and S-file (file size). Then FLUSHALL."""
    r = _rc(host, port)
    r.flushall()
    base = used_memory(r)
    base_rdb = rdb_size(r)
    out: dict[str, Any] = {"f_used_memory_baseline": base, "f_rdb_baseline": base_rdb, "points": []}
    mem: list[int] = []
    sizes: list[int] = []
    sfile = SFileArm(root / "empty")
    made = 0
    for n in ns:
        while made < n:
            k = 900_000 + made
            farm.create_schema(k)
            m = mem_usage(r, graph_name(tenant_name(k)))
            if m is not None:
                mem.append(m)
            sfile.create_schema(k)
            sizes.append(sfile.file_size(k))
            made += 1
        pt: dict[str, Any] = {
            "tenants": n,
            "f_used_memory_delta_per_tenant": round((used_memory(r) - base) / n),
            "f_memory_usage_key": summ(mem),
            "s_file_bytes": summ(sizes),
        }
        if n == ns[-1]:
            rs = rdb_size(r)
            pt["f_rdb_bytes_per_tenant"] = (
                None if rs is None or base_rdb is None else round((rs - base_rdb) / n)
            )
        out["points"].append(pt)
        log(f"G2 empty N={n}: {pt}")
    sfile.close()
    r.flushall()
    farm._graphs.clear()
    return out


# ------------------------------------------------------------------------------------------------ G3b raw channels
def _auth_attacker_file() -> Any:
    deny = {sqlite3.SQLITE_ATTACH}

    def auth(action: int, a1: Any, a2: Any, db: Any, src: Any) -> int:
        return sqlite3.SQLITE_DENY if action in deny else sqlite3.SQLITE_OK

    return auth


def _auth_views(allowed_actions: set[int]) -> Any:
    def auth(action: int, a1: Any, a2: Any, db: Any, src: Any) -> int:
        if action == sqlite3.SQLITE_READ and db == "main" and src is None:
            return (
                sqlite3.SQLITE_DENY
            )  # direct read of a base table (views read it with src = the view's name)
        if action in allowed_actions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    return auth


def g3b(
    host: str, port: int, farm: FArm, sfile: SFileArm, shared: SSharedArm, pairs: list[tuple[int, int]]
) -> dict[str, Any]:
    out: dict[str, Any] = {"pairs": len(pairs)}
    r = _rc(host, port)

    def secret_in(x: Any, k: int) -> bool:
        return farm.worlds[k]["secret"] in repr(x)

    # F without ACL: the default user can name any graph key
    leaks = blocked = own = 0
    for a, b in pairs:
        wb = farm.worlds[b]
        try:
            res = (
                farm.client.graph(farm.gname(b))
                .ro_query("MATCH (f:Fact {id: $id}) RETURN f.value", {"id": wb["canary"]})
                .result_set
            )
            leaks += 1 if secret_in(res, b) else 0
        except redis.ResponseError:
            blocked += 1
        own += 1 if farm.client.graph(farm.gname(a)).ro_query("RETURN 1").result_set else 0
    out["F_no_acl"] = {"leaks": leaks, "blocked": blocked, "own_ok": own, "pairs": len(pairs)}
    # F with a per-tenant ACL user
    users = {a for a, _ in pairs}
    made: list[str] = []
    try:
        for a in sorted(users):
            u = f"l7g_{tenant_name(a)}"
            r.execute_command(
                "ACL",
                "SETUSER",
                u,
                "reset",
                "on",
                ">pw",
                f"~{graph_name(tenant_name(a))}",
                "+graph.query",
                "+graph.ro_query",
                "+graph.explain",
                "+graph.profile",
            )
            made.append(u)
        leaks = blocked = own = other = 0
        errs: dict[str, int] = {}
        conns: dict[int, redis.Redis] = {}
        for a, b in pairs:
            if a not in conns:
                conns[a] = _rc(host, port, username=f"l7g_{tenant_name(a)}", password="pw")
            c = conns[a]
            q = f"MATCH (f:Fact {{id: '{farm.worlds[b]['canary']}'}}) RETURN f.value"
            try:
                res = c.execute_command("GRAPH.RO_QUERY", farm.gname(b), q)
                leaks += 1 if secret_in(res, b) else 0
            except redis.exceptions.NoPermissionError:
                blocked += 1
            except redis.ResponseError as exc:
                other += 1
                errs[str(exc)[:60]] = errs.get(str(exc)[:60], 0) + 1
            try:  # the write command on B's key is blocked too
                c.execute_command("GRAPH.QUERY", farm.gname(b), "CREATE (:Planted)")
                leaks += 1
            except redis.exceptions.NoPermissionError:
                pass
            except redis.ResponseError:
                pass
            try:
                ok = c.execute_command("GRAPH.RO_QUERY", farm.gname(a), "RETURN 1")
                own += 1 if ok else 0
            except redis.ResponseError:
                pass
        for c in conns.values():
            c.close()
        out["F_acl"] = {
            "leaks": leaks,
            "blocked": blocked,
            "own_ok": own,
            "other_errors": other,
            "error_kinds": errs,
            "pairs": len(pairs),
        }
    finally:
        for u in made:
            try:
                r.execute_command("ACL", "DELUSER", u)
            except redis.ResponseError:
                pass
    left = [x for x in r.execute_command("ACL", "LIST") if "l7g_" in str(x)]
    out["acl_users_left_behind"] = len(left)
    # S-file: raw SQL ATTACH of B's file, without / with an authorizer denying SQLITE_ATTACH
    for label, guarded in (("S_file_no_authorizer", False), ("S_file_authorizer_denies_attach", True)):
        leaks = blocked = own = 0
        for a, b in pairs:
            c = sqlite3.connect(sfile.path(a), isolation_level=None)
            if guarded:
                c.set_authorizer(_auth_attacker_file())
            try:
                c.execute(f"ATTACH DATABASE '{sfile.path(b)}' AS other")
                rows = c.execute(
                    "SELECT value FROM other.facts WHERE id = ?", (farm.worlds[b]["canary"],)
                ).fetchall()
                leaks += 1 if secret_in(rows, b) else 0
            except sqlite3.DatabaseError:
                blocked += 1
            own += 1 if c.execute("SELECT count(*) FROM facts").fetchone()[0] else 0
            c.close()
        out[label] = {"leaks": leaks, "blocked": blocked, "own_ok": own, "pairs": len(pairs)}
    # S-shared: raw SQL without protection, and with per-tenant TEMP VIEWs + an authorizer
    leaks = blocked = own = 0
    for a, b in pairs:
        c = sqlite3.connect(shared.p, isolation_level=None)
        rows = c.execute("SELECT value FROM facts WHERE id = ?", (farm.worlds[b]["canary"],)).fetchall()
        leaks += 1 if secret_in(rows, b) else 0
        own += (
            1
            if c.execute("SELECT count(*) FROM facts WHERE tenant_id = ?", (tenant_name(a),)).fetchone()[0]
            else 0
        )
        c.close()
    out["S_shared_no_protection"] = {"leaks": leaks, "blocked": blocked, "own_ok": own, "pairs": len(pairs)}
    leaks = blocked = own = leak_unqualified = 0
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    for a, b in pairs:
        c = sqlite3.connect(shared.p, isolation_level=None)
        ta = tenant_name(a)
        for t in SHARED_TABLES:
            c.execute(f"CREATE TEMP VIEW {t} AS SELECT * FROM main.{t} WHERE tenant_id = '{ta}'")
        c.set_authorizer(_auth_views(allowed))
        cb = farm.worlds[b]["canary"]
        try:  # the attacker names the base table: denied by the authorizer
            rows = c.execute("SELECT value FROM main.facts WHERE id = ?", (cb,)).fetchall()
            leaks += 1 if secret_in(rows, b) else 0
        except sqlite3.DatabaseError:
            blocked += 1
        try:  # the attacker uses the plain name: the TEMP VIEW answers, A's rows only
            rows = c.execute("SELECT value FROM facts WHERE id = ?", (cb,)).fetchall()
            leak_unqualified += 1 if secret_in(rows, b) else 0
        except sqlite3.DatabaseError:
            pass
        try:  # and cannot replace the view
            c.execute("DROP VIEW temp.facts")
            leaks += 1
        except sqlite3.DatabaseError:
            pass
        own += 1 if c.execute("SELECT count(*) FROM facts").fetchone()[0] else 0
        c.close()
    out["S_shared_views_authorizer"] = {
        "leaks": leaks + leak_unqualified,
        "blocked": blocked,
        "own_ok": own,
        "unqualified_name_leaks": leak_unqualified,
        "pairs": len(pairs),
    }
    r.close()
    return out


# ------------------------------------------------------------------------------------------------ G4
def g4(arm: Any, label: str, n: int, ops: int, farm_worlds: dict[int, dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(common.SEED + 4000 + n)
    res: dict[str, Any] = {"arm": label, "N": n}
    before = common.process_resources()
    if label == "S-file-cached":
        t0 = time.perf_counter()
        try:
            arm.open_all(n)
        except Exception as exc:  # noqa: BLE001
            res["failure"] = (
                f"opening cached connections: {type(exc).__name__}: {exc} (after {len(arm.conns)} connections)"
            )
            return res
        res["open_all_s"] = round(time.perf_counter() - t0, 2)
    for op in OPS:
        lat: list[float] = []
        warm: list[float] = []
        cold: list[
            float
        ] = []  # first use of this (tenant, op) in this run: includes per-graph plan compilation
        seen: set[int] = set()
        wrong = errors = 0
        err_kinds: dict[str, int] = {}
        for i in range(ops):
            k = rng.randrange(n)
            fid = f"f{rng.randint(1, 99):04d}"
            w = farm_worlds[k]
            t0 = time.perf_counter()
            try:
                if op == "q4":
                    rows = arm.q4(k, f"w{label}{n}_{i}", fid)
                else:
                    rows = getattr(arm, op)(k, fid)
                dt = (time.perf_counter() - t0) * 1000
            except Exception as exc:  # noqa: BLE001
                errors += 1
                key = f"{type(exc).__name__}: {str(exc)[:60]}"
                err_kinds[key] = err_kinds.get(key, 0) + 1
                lat.append(common.TIMEOUT_MS)  # a failure is a wrong answer with the budget as latency
                continue
            lat.append(dt)
            if k not in seen:
                seen.add(k)
                cold.append(dt)
            else:
                warm.append(dt)
            got = arm.norm(op, rows)
            if op == "q1":
                ok = got == [g_gen.fact_value(w, fid)]
            elif op == "q2":
                ok = got == sorted(g_gen.decisions_on(w, fid))
            elif op == "q3":
                ok = got == sorted(g_gen.ancestors(w, fid))
            else:
                ok = got == [f"w{label}{n}_{i}"]
            wrong += 0 if ok else 1
        res[op] = {
            **common.lat_summary(lat),
            "first_use_in_run": common.lat_summary(cold),
            "repeat_use": common.lat_summary(warm),
            "wrong": wrong,
            "errors": errors,
            **({"error_kinds": err_kinds} if err_kinds else {}),
        }
    after = common.process_resources()
    res["resources_before"], res["resources_after"] = before, after
    return res


# ------------------------------------------------------------------------------------------------ driver
def run(a: argparse.Namespace) -> dict[str, Any]:
    sc = SCALES[a.scale]
    parts = {p.strip().upper() for p in a.parts.split(",")}
    doc = common.envelope("g", a.host, a.port, time.time(), " ".join(sys.argv))
    doc.update(
        {
            "scale": a.scale,
            "db_port": a.port,
            "container": CONTAINER,
            "tenants": list(sc["ns"]),
            "ops_per_type": sc["ops"],
        }
    )
    root = Path(tempfile.mkdtemp(prefix="l7g-"))
    farm = FArm(a.host, a.port)
    r = _rc(a.host, a.port)
    doc["docker_stats_start"] = common.docker_stats_once(CONTAINER)
    try:
        if "G2" in parts:
            doc["g2_empty"] = empty_footprint(a.host, a.port, root, sc["empty"], farm)
        r.flushall()
        base_mem = used_memory(r)
        base_rdb = rdb_size(r)
        doc["g2_baseline"] = {"f_used_memory": base_mem, "f_rdb": base_rdb}
        sfile = SFileArm(root / "sfile")
        shared = SSharedArm(root / "shared")
        arms = {"F": farm, "S-file": sfile, "S-shared": shared}
        g1: dict[str, dict[str, list[float]]] = {x: {"create_s": [], "load_s": []} for x in arms}
        f_mem_empty: list[int] = []
        f_mem_loaded: list[int] = []
        f_um_empty: list[
            int
        ] = []  # used_memory delta of one tenant's apply_schema (noisy: allocator, other clients)
        f_um_loaded: list[int] = []  # ... and of its bulk load
        s_empty: list[int] = []
        rng = random.Random(common.SEED + 99)
        doc["G1"], doc["G2"], doc["G3a"], doc["G3b"], doc["G4"], doc["failures"] = {}, {}, {}, {}, {}, []
        made = 0
        worlds: dict[int, dict[str, Any]] = {}
        stop: dict[str, Any] | None = None
        for n in sc["ns"]:
            if stop:
                break
            t_level = time.time()
            # ---- creation of tenants made..n-1 in every arm
            while made < n:
                k = made
                worlds[k] = tenant_world(k)
                sample_mem = made < sc["mem_sample"] or made % max(1, n // sc["mem_sample"]) == 0
                for name, arm in arms.items():
                    try:
                        if name == "F" and sample_mem:
                            um0 = used_memory(r)
                        cs = arm.create_schema(k)
                        if name == "F" and sample_mem:
                            m = mem_usage(r, farm.gname(k))
                            if m is not None:
                                f_mem_empty.append(m)
                            um1 = used_memory(r)
                            f_um_empty.append(um1 - um0)
                        if name == "S-file" and sample_mem:
                            s_empty.append(sfile.file_size(k))
                        t0 = time.perf_counter()
                        arm.load(k, worlds[k])
                        ls = time.perf_counter() - t0
                        g1[name]["create_s"].append(cs)
                        g1[name]["load_s"].append(ls)
                        if name == "F" and sample_mem:
                            m = mem_usage(r, farm.gname(k))
                            if m is not None:
                                f_mem_loaded.append(m)
                            f_um_loaded.append(used_memory(r) - um1)
                    except Exception as exc:  # noqa: BLE001
                        doc["failures"].append(
                            {
                                "arm": name,
                                "N": n,
                                "tenant": k,
                                "phase": "create/load",
                                "error": f"{type(exc).__name__}: {exc}",
                                "trace": traceback.format_exc()[-800:],
                            }
                        )
                        log(f"FAILURE creating tenant {k} in {name}: {exc}")
                        stop = {"N": n, "tenant": k, "arm": name, "error": f"{type(exc).__name__}: {exc}",
                                "tenants_created_all_arms": made,
                                "docker_stats": common.docker_stats_once(CONTAINER)}  # fmt: skip
                        break
                if stop:
                    break
                made += 1
                if made % 100 == 0:
                    log(
                        f"created {made}/{n} tenants (F p50 create {1000 * sorted(g1['F']['create_s'])[len(g1['F']['create_s']) // 2]:.0f} ms)"
                    )
            if stop:
                doc["infeasible"] = (
                    stop  # the scale that could not be reached, with the failure; nothing is capped silently
                )
                log(f"N={n} not reached: {stop['error']}")
                break
            log(f"N={n}: tenants created in {time.time() - t_level:.1f}s")
            # ---- G1 so far
            doc["G1"][str(n)] = {
                x: {
                    "create_ms": {
                        **common.lat_summary([v * 1000 for v in g1[x]["create_s"]]),
                        "total_s": round(sum(g1[x]["create_s"]), 2),
                    },
                    "load_ms": {
                        **common.lat_summary([v * 1000 for v in g1[x]["load_s"]]),
                        "total_s": round(sum(g1[x]["load_s"]), 2),
                    },
                }
                for x in arms
            }
            # ---- G2 loaded footprint at N
            f_used = used_memory(r)
            rs = rdb_size(r)
            sizes = [
                sfile.file_size(k) for k in (range(n) if n <= 200 else sorted(rng.sample(range(n), 200)))
            ]
            doc["G2"][str(n)] = {
                "F": {
                    "used_memory_delta_per_tenant": round((f_used - base_mem) / n),
                    "rdb_bytes_per_tenant": None
                    if rs is None or base_rdb is None
                    else round((rs - base_rdb) / n),
                    "memory_usage_key_empty": summ(f_mem_empty),
                    "memory_usage_key_loaded": summ(f_mem_loaded),
                    "used_memory_delta_schema_only": summ(f_um_empty),
                    "used_memory_delta_load": summ(f_um_loaded),
                    "docker_stats": common.docker_stats_once(CONTAINER),
                },
                "S-file": {
                    "file_bytes_loaded": summ(sizes),
                    "file_bytes_empty": summ(s_empty),
                    "sampled": len(sizes),
                },
                "S-shared": {
                    "file_bytes_total": shared.file_size(),
                    "file_bytes_per_tenant": round(shared.file_size() / n),
                },
            }
            # ---- G3a / G3b
            if n >= 2:
                allp = [(x, y) for x in range(n) for y in range(n) if x != y]
                prng = random.Random(common.SEED + 3000 + n)
                pairs = allp if len(allp) <= sc["pairs"] else prng.sample(allp, sc["pairs"])
                if "G3" in parts:
                    g3a: dict[str, Any] = {"pairs": len(pairs)}
                    for name, arm in arms.items():
                        t0 = time.perf_counter()
                        tot: dict[str, int] = {}
                        ctrl = 0
                        extra = 0
                        for x, y in pairs:
                            pr = arm.probe(x, y)
                            for kk, vv in pr["leaked"].items():
                                tot[kk] = tot.get(kk, 0) + vv
                            ctrl += 1 if all(pr["control"].values()) else 0
                            extra += pr.get("keyword_hits_for_foreign_secret", 0)
                        g3a[name] = {
                            "leaked_by_probe": tot,
                            "leaked_total": sum(tot.values()),
                            "controls_ok": ctrl,
                            "seconds": round(time.perf_counter() - t0, 1),
                            **({"foreign_secret_keyword_hits_all_from_A": extra} if name == "F" else {}),
                        }
                    doc["G3a"][str(n)] = g3a
                    log(
                        f"G3a N={n}: "
                        + json.dumps({k: v["leaked_total"] for k, v in g3a.items() if isinstance(v, dict)})
                    )
                    raw_pairs = pairs[: sc["pairs_raw"]]
                    doc["G3b"][str(n)] = g3b(a.host, a.port, farm, sfile, shared, raw_pairs)
                    log(f"G3b N={n} done")
            # ---- G4
            if "G4" in parts:
                doc["G4"][str(n)] = {}
                for label, arm in (
                    ("F", farm),
                    ("S-file-cached", sfile),
                    ("S-file-open", sfile),
                    ("S-shared", shared),
                ):
                    if isinstance(arm, SFileArm):
                        arm.cached = label == "S-file-cached"
                    try:
                        doc["G4"][str(n)][label] = g4(arm, label, n, sc["ops"], worlds)
                    except Exception as exc:  # noqa: BLE001
                        doc["G4"][str(n)][label] = {"failure": f"{type(exc).__name__}: {exc}"}
                        doc["failures"].append(
                            {"arm": label, "N": n, "phase": "G4", "error": f"{type(exc).__name__}: {exc}"}
                        )
                    if label == "S-file-cached":
                        sfile.close()  # release the N cached handles so the next arm's handle count is its own
                log(
                    f"G4 N={n}: "
                    + json.dumps(
                        {
                            lab: {op: v.get(op, {}).get("p50") for op in OPS}
                            for lab, v in doc["G4"][str(n)].items()
                        }
                    )
                )
            _progress(doc, a)
        doc["tenant_handling"] = tenant_predicate_sites()
        doc["worlds_check"] = {
            "tenants": made,
            "max_derived_depth": max(g_gen.max_depth(w) for w in list(worlds.values())[:50]),
            "counts_tenant0": g_gen.counts(worlds[0]),
        }
        doc["ratio_n_max_over_1"] = _ratios(doc)
        doc["docker_stats_end"] = common.docker_stats_once(CONTAINER)
        doc["not_run"] = ["F-shared (optional arm): not run"]
        for arm in (sfile, shared):
            arm.close()
        farm.close()
    finally:
        if a.flush:
            r2 = _rc(a.host, a.port)
            r2.flushall()
            doc["flushall_at_end"] = True
        shutil.rmtree(root, ignore_errors=True)
    return doc


def _ratios(doc: dict[str, Any]) -> dict[str, Any]:
    ns = sorted(int(k) for k in doc["G4"])
    if len(ns) < 2:
        return {}
    lo, hi = str(ns[0]), str(ns[-1])
    out: dict[str, Any] = {"N_hi": int(hi), "N_lo": int(lo)}
    for lab, v in doc["G4"][hi].items():
        out[lab] = {}
        for op in OPS:
            try:
                out[lab][op] = round(v[op]["p50"] / doc["G4"][lo][lab][op]["p50"], 2)
            except (KeyError, TypeError, ZeroDivisionError):
                out[lab][op] = None
    return out


def _progress(doc: dict[str, Any], a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"partial-{doc['run']['id']}.json").write_text(
        json.dumps(doc, indent=1, default=str), encoding="utf-8"
    )


def report_md(doc: dict[str, Any]) -> str:
    L = [f"# Crucible L7 family G: multi-tenancy ({doc['scale']}, run {doc['run']['id']})", ""]
    L += [
        "## G1 creation latency per tenant (ms) and totals",
        "",
        "| N | arm | create p50 | create p99 | create total s | load p50 | load p99 | load total s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, cells in doc["G1"].items():
        for arm, c in cells.items():
            L.append(
                f"| {n} | {arm} | {c['create_ms']['p50']} | {c['create_ms']['p99']} | {c['create_ms']['total_s']} | {c['load_ms']['p50']} | {c['load_ms']['p99']} | {c['load_ms']['total_s']} |"
            )
    L += ["", "## G2 footprint", ""]
    if "g2_empty" in doc:
        L += ["Empty (schema only):", ""] + [f"* {json.dumps(p)}" for p in doc["g2_empty"]["points"]] + [""]
    L += [
        "| N | F used_memory delta/tenant | F RDB/tenant | F MEMORY USAGE loaded p50 | S-file loaded p50 B | S-file empty p50 B | S-shared B/tenant |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, c in doc["G2"].items():
        L.append(
            f"| {n} | {c['F']['used_memory_delta_per_tenant']} | {c['F']['rdb_bytes_per_tenant']} | {c['F']['memory_usage_key_loaded'].get('p50')} | {c['S-file']['file_bytes_loaded'].get('p50')} | {c['S-file']['file_bytes_empty'].get('p50')} | {c['S-shared']['file_bytes_per_tenant']} |"
        )
    L += [
        "",
        "## G3a product-path leakage (leaked rows, gate = 0)",
        "",
        "| N | pairs | F | S-file | S-shared | F controls ok |",
        "|---|---|---|---|---|---|",
    ]
    for n, c in doc["G3a"].items():
        L.append(
            f"| {n} | {c['pairs']} | {c['F']['leaked_total']} | {c['S-file']['leaked_total']} | {c['S-shared']['leaked_total']} | {c['F']['controls_ok']}/{c['pairs']} |"
        )
    L += [
        "",
        "## G3b raw-channel matrix (leaks / blocked of N pairs)",
        "",
        "| N | config | leaks | blocked | own ok |",
        "|---|---|---|---|---|",
    ]
    for n, c in doc["G3b"].items():
        for k, v in c.items():
            if isinstance(v, dict) and "leaks" in v:
                L.append(f"| {n} | {k} | {v['leaks']} | {v['blocked']} | {v['own_ok']} |")
    L += [
        "",
        "## G4 latency (ms) p50 / p99 per op",
        "",
        "| N | arm | q1 | q2 | q3 | q4 | wrong+errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, cells in doc["G4"].items():
        for arm, c in cells.items():
            if "failure" in c:
                L.append(f"| {n} | {arm} | FAILED: {c['failure']} | | | | |")
                continue
            bad = sum(c[o]["wrong"] + c[o]["errors"] for o in OPS)
            L.append(
                f"| {n} | {arm} | "
                + " | ".join(f"{c[o]['p50']} / {c[o]['p99']}" for o in OPS)
                + f" | {bad} |"
            )
    L += [
        "",
        f"Ratio p50 N_max/N_min: {json.dumps(doc.get('ratio_n_max_over_1'))}",
        f"Tenant handling: {json.dumps(doc.get('tenant_handling'))}",
    ]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l7-g")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--host", default=common.DEFAULT_HOST)
    r.add_argument("--port", type=int, default=6365)
    r.add_argument("--scale", choices=sorted(SCALES), default="dev")
    r.add_argument("--out", default=str(common.DEMO))
    r.add_argument("--parts", default="G1,G2,G3,G4")
    r.add_argument("--flush", action="store_true", help="FLUSHALL plexus-db-65 at the end")
    r.add_argument(
        "--skip-rdb", action="store_true", help="never BGSAVE (RDB size per tenant is then not measured)"
    )
    a = ap.parse_args(argv)
    global SKIP_RDB
    SKIP_RDB = bool(a.skip_rdb)
    global CONTAINER
    if not 6310 <= a.port <= 6399:
        print("family G needs an agent DB port 63NN (container plexus-db-NN)", file=sys.stderr)
        return 2
    CONTAINER = f"plexus-db-{a.port % 100}"  # the slot's own container (default slot 65)
    doc = run(a)
    d = common.write(doc, Path(a.out), report_md(doc))
    log(f"wrote {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
