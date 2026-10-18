"""Tiny MCP streamable-HTTP client for Plexus (stdlib only). Adapted from
plexus-repo-workflow/scripts/plexus_mcp.py: explicit base url, timeouts, no hermes naming.
Used by the trial-7 runner for the non-LLM ci-bot and for the end-of-run audit dump."""
import json
import urllib.request


class Plexus:
    def __init__(self, tenant: str, url: str = "http://127.0.0.1:8766", agent_id: str = "ci-bot"):
        self.base = f"{url.rstrip('/')}/mcp/t/{tenant}"
        self.sid = None
        self.agent_id = agent_id
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": agent_id, "version": "1"}})
        self._rpc("notifications/initialized", {}, notify=True)

    def _rpc(self, method, params=None, notify=False):
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = 1
        if params is not None:
            body["params"] = params
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.sid:
            h["mcp-session-id"] = self.sid
        req = urllib.request.Request(self.base, data=json.dumps(body).encode(), headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.sid = r.headers.get("mcp-session-id") or self.sid
            raw = r.read().decode()
        if notify:
            return None
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        return json.loads(raw) if raw.strip() else None

    def call(self, tool, **args):
        args.setdefault("agent_id", self.agent_id)
        res = self._rpc("tools/call", {"name": tool, "arguments": args}).get("result", {})
        if res.get("isError"):
            return {"error": res["content"][0]["text"][:500]}
        return res.get("structuredContent") or json.loads(res["content"][0]["text"])
