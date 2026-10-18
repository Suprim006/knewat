"""Public-safety layer for the one-container deployment (ASGI middleware + idle sweeper).

The MCP endpoint is public ("bring your own agent"), so everything in front of it is deny-by-default:

* **Tenant policy.** Only ``team_[a-z0-9]{4,24}`` tenants can be written through MCP. ``demo`` / ``demo_*`` tenants are
  **readable and not writable**: the MCP handshake works, a ``tools/call`` of one of the :data:`OBSERVER_TOOLS` (the
  read tools) is forwarded, and every other call is refused with a tool error that says why. The real enforcement is
  the Plexus runtime, which serves ``demo*`` in audit mode ``off`` (no write of any kind, writes refused, no graph
  created; see :func:`ensure_demo_audit_off`); the allowlist here is a second gate. A demo tenant whose graph does not
  exist is refused too, so a request can not make the server create graphs. Any other tenant name is refused with 403.
* **Per-IP token bucket** (default 60 requests/min) plus a global bucket as a backstop (the client IP is only as
  trustworthy as the proxy in front, see :func:`client_ip`). Demo reads (a ``recall`` costs an embedding) also spend a
  smaller, separate bucket.
* **Request body cap** (default 512 KiB) enforced on ``Content-Length`` and while streaming.
* **Graph cap.** At most ``max_tenants`` (50) tenant graphs; a request that would create one more is refused (503).
* **Idle sweep.** :class:`IdleSweeper` deletes ``team_*`` graphs with no MCP traffic for 24 h.

No Plexus source is imported here, so this file is unit-testable without a database (graph listing and deletion are
injected callables).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, field

import anyio.to_thread

log = logging.getLogger("plexus.deploy.guard")

TENANT_PREFIX = "plexus_t_"  # graph name = TENANT_PREFIX + tenant (plexus.graph.tenancy)
TEAM_RE = re.compile(r"team_[a-z0-9]{4,24}")
DEMO_RE = re.compile(r"demo(_[a-z0-9_]*)?")
MCP_PREFIX = "/mcp/t/"
TENANT_HEADER = b"x-plexus-tenant"

# The read tools a public demo tenant may call. This is the set of tools declared ``kind="read"`` in
# ``plexus.mcp`` (``memory_sweep`` stays out: its ``dry_run`` is an argument). A test in the Plexus suite asserts
# the two lists are equal, so they can not drift; this file imports no Plexus code.
OBSERVER_TOOLS = frozenset(
    {
        "recall",
        "fact_history",
        "as_of",
        "why",
        "why_recalled",
        "who_knew",
        "knew_at",
        "ready_tasks",
        "task_status",
        "blocked_by_failure",
        "best_procedure",
        "memory_strength",
        "facts_to_verify",
        "docs_to_update",
    }
)
DEMO_AUDIT_RULE = "demo*=off"  # PLEXUS_AUDIT_MODES entry: public demo tenants write nothing, ever


def ensure_demo_audit_off(environ: MutableMapping[str, str] | None = None) -> MutableMapping[str, str]:
    """Put ``demo*=off`` first in ``PLEXUS_AUDIT_MODES`` (first match wins, so an operator can not weaken it).

    Call before the Plexus ``Runtime`` is created: it reads the variable once, at start. Idempotent.
    """
    env = os.environ if environ is None else environ
    rules = [r.strip() for r in (env.get("PLEXUS_AUDIT_MODES") or "").split(",") if r.strip()]
    if DEMO_AUDIT_RULE not in rules:
        env["PLEXUS_AUDIT_MODES"] = ",".join([DEMO_AUDIT_RULE, *rules])
    return env


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class GuardConfig:
    max_tenants: int = 50
    rate_per_min: int = 60  # per client IP, /mcp
    global_rate_per_min: int = 600  # all clients together, /mcp (backstop when the client IP is spoofable)
    api_rate_per_min: int = 300  # per client IP, /api (the read-only View API)
    demo_rate_per_min: int = 30  # per client IP, tool calls on demo tenants (a recall embeds its query)
    demo_global_rate_per_min: int = 120  # all clients together, tool calls on demo tenants
    cypher_rate_per_min: int = 20  # per client IP, POST /api/{tenant}/cypher (a query can run for seconds)
    cypher_global_rate_per_min: int = 120  # all clients together, the same route
    cypher_max_body_bytes: int = 16 * 1024
    max_body_bytes: int = 512 * 1024
    idle_hours: float = 24.0
    sweep_interval_s: float = 600.0
    ip_header: str = ""  # e.g. "cf-connecting-ip" (Render). Empty: the socket peer.
    xff_hops: int = 0  # >0: the client is the Nth entry from the right of X-Forwarded-For

    @classmethod
    def from_env(cls) -> GuardConfig:
        on_render = os.environ.get("RENDER", "").lower() == "true"
        return cls(
            max_tenants=_env_int("PLEXUS_MAX_TENANTS", 50),
            rate_per_min=_env_int("PLEXUS_RATE_PER_MIN", 60),
            global_rate_per_min=_env_int("PLEXUS_GLOBAL_RATE_PER_MIN", 600),
            api_rate_per_min=_env_int("PLEXUS_API_RATE_PER_MIN", 300),
            demo_rate_per_min=_env_int("PLEXUS_DEMO_RATE_PER_MIN", 30),
            demo_global_rate_per_min=_env_int("PLEXUS_DEMO_GLOBAL_RATE_PER_MIN", 120),
            cypher_rate_per_min=_env_int("PLEXUS_CYPHER_RATE_PER_MIN", 20),
            cypher_global_rate_per_min=_env_int("PLEXUS_CYPHER_GLOBAL_RATE_PER_MIN", 120),
            cypher_max_body_bytes=_env_int("PLEXUS_CYPHER_MAX_BODY_BYTES", 16 * 1024),
            max_body_bytes=_env_int("PLEXUS_MAX_BODY_BYTES", 512 * 1024),
            idle_hours=_env_float("PLEXUS_TEAM_IDLE_HOURS", 24.0),
            sweep_interval_s=_env_float("PLEXUS_SWEEP_INTERVAL_S", 600.0),
            # Render fronts every service with Cloudflare, which sets CF-Connecting-IP and rejects a forged one.
            ip_header=(os.environ.get("PLEXUS_CLIENT_IP_HEADER") or ("cf-connecting-ip" if on_render else "")).lower(),
            xff_hops=_env_int("PLEXUS_XFF_HOPS", 0),
        )


# ------------------------------------------------------------------------------------------ tenant policy
def classify(tenant: str) -> str:
    """``team`` (read/write), ``demo`` (read tools only) or ``deny``."""
    if TEAM_RE.fullmatch(tenant):
        return "team"
    if DEMO_RE.fullmatch(tenant):
        return "demo"
    return "deny"


def tenant_of(path: str, headers: Iterable[tuple[bytes, bytes]]) -> str | None:
    """The tenant the inner middleware will use: the first segment after ``/mcp/t/``, else ``X-Plexus-Tenant``."""
    if path.startswith(MCP_PREFIX):
        return path[len(MCP_PREFIX) :].split("/", 1)[0] or None
    for k, v in headers:
        if k.lower() == TENANT_HEADER:
            try:
                return v.decode("utf-8") or None
            except UnicodeDecodeError:
                return None
    return None


# ------------------------------------------------------------------------------------------ rate limiting
class TokenBucket:
    """Classic token bucket: ``per_min`` tokens refill continuously, capacity ``per_min``."""

    def __init__(self, per_min: int, clock: Callable[[], float] = time.monotonic):
        self.rate = per_min / 60.0
        self.cap = float(per_min)
        self.clock = clock
        self.tokens = self.cap
        self.at = clock()

    def take(self) -> float:
        """0.0 if a token was taken, else the seconds until one is available."""
        now = self.clock()
        self.tokens = min(self.cap, self.tokens + (now - self.at) * self.rate)
        self.at = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        return (1.0 - self.tokens) / self.rate if self.rate > 0 else 60.0


class RateLimiter:
    """Per-key buckets (LRU-bounded) plus an optional global bucket. Thread-safe."""

    def __init__(
        self,
        per_min: int,
        global_per_min: int | None = None,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.per_min = per_min
        self.max_keys = max_keys
        self.clock = clock
        self.buckets: OrderedDict[str, TokenBucket] = OrderedDict()
        self.global_bucket = TokenBucket(global_per_min, clock) if global_per_min else None
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """0.0 = allowed; otherwise seconds to wait (Retry-After)."""
        with self._lock:
            bucket = self.buckets.get(key)
            if bucket is None:
                bucket = self.buckets[key] = TokenBucket(self.per_min, self.clock)
                while len(self.buckets) > self.max_keys:
                    self.buckets.popitem(last=False)
            else:
                self.buckets.move_to_end(key)
            wait = bucket.take()
            if wait:
                return wait
            if self.global_bucket is not None:
                return self.global_bucket.take()  # a global refusal still costs the per-IP token: fine
            return 0.0


def client_ip(scope, cfg: GuardConfig) -> str:
    """Best-effort client address.

    ``cfg.ip_header`` wins (Render: ``CF-Connecting-IP``); else ``cfg.xff_hops`` picks the Nth entry from the right
    of ``X-Forwarded-For``; else the socket peer. Without a trusted proxy header every header is client-controlled,
    which is why the global bucket exists.
    """
    headers = {k.lower(): v for k, v in scope.get("headers", [])}
    if cfg.ip_header:
        v = headers.get(cfg.ip_header.encode())
        if v:
            return v.decode("latin-1").strip()[:64]
    if cfg.xff_hops > 0:
        parts = [p.strip() for p in headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",") if p.strip()]
        if len(parts) >= cfg.xff_hops:
            return parts[-cfg.xff_hops][:64]
    client = scope.get("client")
    return client[0] if client else "unknown"


# ------------------------------------------------------------------------------------------ graph directory
class TenantDirectory:
    """Tenant names currently present as graphs (cached a few seconds) + tenants admitted but not yet created."""

    def __init__(
        self,
        list_graphs: Callable[[], list[str]],
        max_tenants: int,
        cache_s: float = 5.0,
        pending_s: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.list_graphs = list_graphs
        self.max_tenants = max_tenants
        self.cache_s = cache_s
        self.pending_s = pending_s
        self.clock = clock
        self._known: set[str] = set()
        self._at = -1e18
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def names(self, force: bool = False) -> set[str]:
        with self._lock:
            now = self.clock()
            if force or now - self._at >= self.cache_s:
                self._known = {g[len(TENANT_PREFIX) :] for g in self.list_graphs() if g.startswith(TENANT_PREFIX)}
                self._at = now
                self._pending = {t: ts for t, ts in self._pending.items() if t not in self._known}
            return set(self._known)

    def admit(self, tenant: str) -> bool:
        """May ``tenant`` be used? Existing and recently admitted tenants always; a new one only under the cap."""
        known = self.names()
        with self._lock:
            now = self.clock()
            self._pending = {t: ts for t, ts in self._pending.items() if now - ts < self.pending_s}
            if tenant in known or tenant in self._pending:
                return True
            if len(known) + len(self._pending) >= self.max_tenants:
                return False
            self._pending[tenant] = now
            return True


# ------------------------------------------------------------------------------------------ ASGI helpers
async def reply_json(send, status: int, body: dict, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    raw = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]
            + (headers or []),
        }
    )
    await send({"type": "http.response.body", "body": raw})


class _TooLarge(Exception):
    pass


async def read_body(receive, limit: int) -> tuple[bytes, bool]:
    """Read a whole request body. Returns ``(body, disconnected)``; raises :class:`_TooLarge` past ``limit``."""
    chunks: list[bytes] = []
    size = 0
    while True:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            return b"", True
        chunk = msg.get("body", b"")
        size += len(chunk)
        if size > limit:
            raise _TooLarge
        chunks.append(chunk)
        if not msg.get("more_body"):
            return b"".join(chunks), False


def _replay(body: bytes, receive):
    sent = False

    async def _receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()  # after the body: the real disconnect

    return _receive


READ_ONLY_MESSAGE = (
    "This is a read-only demo tenant: writes are disabled; reads are allowed (recall, fact_history, as_of, why, "
    "why_recalled, who_knew, knew_at, ready_tasks, task_status, blocked_by_failure, best_procedure, memory_strength, "
    "facts_to_verify, docs_to_update). Connect to /mcp/t/team_<name> (team_ + 4 to 24 lowercase letters or digits, "
    "e.g. /mcp/t/team_alice01) to write; explore the demo data in the View."
)
NO_SUCH_DEMO_MESSAGE = (
    "This demo tenant does not exist (read-only tenants are never created by a request). Demo tenants on this "
    "deployment: see /api/tenants."
)


def _tool_error(request_id, text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": True, "resultType": "complete"},
    }


# ------------------------------------------------------------------------------------------ the middleware
class PublicGuard:
    """Wraps the MCP ASGI app (``/mcp``, ``/mcp/t/<tenant>``)."""

    def __init__(
        self,
        app,
        cfg: GuardConfig,
        directory: TenantDirectory,
        activity: ActivityLog,
        limiter: RateLimiter | None = None,
        demo_limiter: RateLimiter | None = None,
    ):
        self.app = app
        self.cfg = cfg
        self.directory = directory
        self.activity = activity
        self.limiter = limiter or RateLimiter(cfg.rate_per_min, cfg.global_rate_per_min)
        self.demo_limiter = demo_limiter or RateLimiter(cfg.demo_rate_per_min, cfg.demo_global_rate_per_min)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        wait = self.limiter.check(client_ip(scope, self.cfg))
        if wait:
            return await reply_json(
                send,
                429,
                {"error": f"rate limit exceeded: {self.cfg.rate_per_min} requests/min per client; retry later"},
                [(b"retry-after", str(max(1, int(wait + 0.999))).encode())],
            )
        tenant = tenant_of(scope["path"], scope.get("headers", []))
        if tenant is None:  # no / undecodable tenant: let the Plexus middleware give its precise 400
            return await self.app(scope, receive, send)
        kind = classify(tenant)
        if kind == "deny":
            return await reply_json(
                send,
                403,
                {
                    "error": f"tenant '{tenant[:60]}' is not available on the public deployment. Write tenants "
                    "match team_[a-z0-9]{4,24} (e.g. /mcp/t/team_alice01); demo tenants are read-only."
                },
            )
        if kind == "team":
            try:
                admitted = await anyio.to_thread.run_sync(self.directory.admit, tenant)
            except Exception:
                log.exception("graph listing failed")
                return await reply_json(send, 503, {"error": "graph database unavailable"})
            if not admitted:
                return await reply_json(
                    send,
                    503,
                    {
                        "error": f"the public deployment holds its maximum of {self.cfg.max_tenants} tenant graphs; "
                        "idle team_ graphs are removed after "
                        f"{self.cfg.idle_hours:g} h. Try again later or run Plexus locally (docker compose)."
                    },
                )
            self.activity.touch(tenant)

        method = scope["method"]
        declared = next((v for k, v in scope.get("headers", []) if k.lower() == b"content-length"), None)
        if method == "POST" or declared not in (None, b"0"):
            try:
                if declared is not None and int(declared) > self.cfg.max_body_bytes:
                    raise _TooLarge
                body, gone = await read_body(receive, self.cfg.max_body_bytes)
            except _TooLarge:
                return await reply_json(
                    send, 413, {"error": f"request body too large (limit {self.cfg.max_body_bytes} bytes)"}
                )
            except ValueError:
                return await reply_json(send, 400, {"error": "invalid Content-Length"})
            if gone:
                return None
            if kind == "demo":
                refusal = self._demo_refusal(body)
                if refusal is None and self._is_demo_read(body):
                    refusal = await self._demo_read_admission(tenant, body, client_ip(scope, self.cfg))
                if refusal is not None:
                    status, payload, *extra = refusal
                    return await reply_json(send, status, payload, extra[0] if extra else None)
            receive = _replay(body, receive)
        return await self.app(scope, receive, send)

    @staticmethod
    def _message(body: bytes):
        try:
            return json.loads(body) if body else None
        except ValueError:
            return None  # not JSON: the MCP layer produces its own parse error

    @classmethod
    def _is_demo_read(cls, body: bytes) -> bool:
        msg = cls._message(body)
        return isinstance(msg, dict) and msg.get("method") == "tools/call"

    @classmethod
    def _demo_refusal(cls, body: bytes) -> tuple[int, dict] | None:
        """For a demo tenant: ``None`` to carry on, else ``(status, JSON body)`` to answer directly.

        Batches and every ``tools/call`` that is not a plain call of an :data:`OBSERVER_TOOLS` tool are refused.
        """
        msg = cls._message(body)
        if isinstance(msg, list):
            return 400, {"error": "JSON-RPC batches are not supported on the public deployment"}
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            params = msg.get("params")
            name = params.get("name") if isinstance(params, dict) else None
            if not isinstance(name, str) or name not in OBSERVER_TOOLS:
                return 200, _tool_error(msg.get("id"), READ_ONLY_MESSAGE)
        return None

    async def _demo_read_admission(self, tenant: str, body: bytes, ip: str):
        """May this demo read go on? Needs an existing graph and a token from the demo bucket."""
        try:
            known = await anyio.to_thread.run_sync(self.directory.names)
        except Exception:
            log.exception("graph listing failed")
            return 503, {"error": "graph database unavailable"}
        if tenant not in known:
            return 200, _tool_error((self._message(body) or {}).get("id"), NO_SUCH_DEMO_MESSAGE)
        wait = self.demo_limiter.check(ip)
        if wait:
            return (
                429,
                {"error": f"rate limit exceeded: {self.cfg.demo_rate_per_min} demo reads/min per client; retry later"},
                [(b"retry-after", str(max(1, int(wait + 0.999))).encode())],
            )
        return None


class ApiRateLimit:
    """Per-IP token bucket for the read-only View API (``/api``); the SSE stream counts once, when it opens.

    ``POST`` (the Cypher console, ``/api/{tenant}/cypher``) also spends a smaller, separate bucket and has its own
    body cap, enforced on ``Content-Length`` and while streaming.
    """

    def __init__(
        self,
        app,
        cfg: GuardConfig,
        limiter: RateLimiter | None = None,
        cypher_limiter: RateLimiter | None = None,
    ):
        self.app = app
        self.cfg = cfg
        self.limiter = limiter or RateLimiter(cfg.api_rate_per_min, cfg.api_rate_per_min * 10)
        self.cypher_limiter = cypher_limiter or RateLimiter(cfg.cypher_rate_per_min, cfg.cypher_global_rate_per_min)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ip = client_ip(scope, self.cfg)
        if wait := self.limiter.check(ip):
            return await self._too_many(send, wait, "rate limit exceeded; slow down")
        if scope["method"] != "POST":
            return await self.app(scope, receive, send)
        if wait := self.cypher_limiter.check(ip):
            return await self._too_many(
                send, wait, f"rate limit exceeded: {self.cfg.cypher_rate_per_min} Cypher queries/min per client"
            )
        limit = self.cfg.cypher_max_body_bytes
        declared = dict(scope.get("headers", [])).get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > limit:
            return await reply_json(send, 413, {"detail": f"request body too large (limit {limit} bytes)"})
        try:
            body, disconnected = await read_body(receive, limit)
        except _TooLarge:
            return await reply_json(send, 413, {"detail": f"request body too large (limit {limit} bytes)"})
        if disconnected:
            return None
        return await self.app(scope, _replay(body, receive), send)

    @staticmethod
    async def _too_many(send, wait: float, detail: str) -> None:
        await reply_json(send, 429, {"detail": detail}, [(b"retry-after", str(max(1, int(wait + 0.999))).encode())])


# ------------------------------------------------------------------------------------------ idle sweep
@dataclass
class ActivityLog:
    """Last MCP use per team tenant (monotonic seconds). In memory on purpose: the database is ephemeral too."""

    clock: Callable[[], float] = time.monotonic
    last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    max_entries: int = 5000

    def touch(self, tenant: str) -> None:
        with self._lock:
            self.last[tenant] = self.clock()
            if len(self.last) > self.max_entries:  # tenants that never got a graph: drop the oldest
                for t in sorted(self.last, key=self.last.__getitem__)[: len(self.last) - self.max_entries]:
                    del self.last[t]


class IdleSweeper:
    """Deletes ``team_*`` graphs idle longer than ``idle_s``. A graph first seen without recorded activity (e.g.
    after a restart of this process while the database survived) starts its idle clock when first seen."""

    def __init__(
        self,
        activity: ActivityLog,
        list_graphs: Callable[[], list[str]],
        delete_graph: Callable[[str], None],
        idle_s: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.activity = activity
        self.list_graphs = list_graphs
        self.delete_graph = delete_graph
        self.idle_s = idle_s
        self.clock = clock

    def sweep_once(self) -> list[str]:
        now = self.clock()
        present = {g[len(TENANT_PREFIX) :] for g in self.list_graphs() if g.startswith(TENANT_PREFIX)}
        deleted: list[str] = []
        for tenant in sorted(present):
            if classify(tenant) != "team":  # demo* and anything unexpected are never swept
                continue
            with self.activity._lock:
                last = self.activity.last.setdefault(tenant, now)
            if now - last > self.idle_s:
                self.delete_graph(TENANT_PREFIX + tenant)
                deleted.append(tenant)
        with self.activity._lock:
            for tenant in list(self.activity.last):
                if tenant in deleted or (tenant not in present and now - self.activity.last[tenant] > self.idle_s):
                    del self.activity.last[tenant]
        if deleted:
            log.info("idle sweep deleted %d team graph(s): %s", len(deleted), ", ".join(deleted))
        return deleted

    def run_forever(self, interval_s: float, stop: threading.Event) -> None:
        while not stop.wait(interval_s):
            try:
                self.sweep_once()
            except Exception:
                log.exception("idle sweep failed; will retry")
