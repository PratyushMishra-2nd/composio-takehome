"""Minimal client for Composio's MCP server (https://connect.composio.dev/mcp).

Auth: COMPOSIO_API_KEY from the environment or .env, sent as a Bearer token.
Usage as a library:  from composio_mcp import call;  call("COMPOSIO_SEARCH_TOOLS", {...})
Usage from shell:    python agent/composio_mcp.py COMPOSIO_SEARCH_TOOLS '{"queries":[...]}'
"""
import json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://connect.composio.dev/mcp"


def _key():
    k = os.environ.get("COMPOSIO_API_KEY")
    if not k and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("COMPOSIO_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        sys.exit("COMPOSIO_API_KEY not set (env or .env)")
    return k


_session = {}


def _post(payload, timeout=180):
    headers = {"Authorization": f"Bearer {_key()}", "content-type": "application/json",
               "accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
    if "id" in _session:
        headers["Mcp-Session-Id"] = _session["id"]
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            _session["id"] = sid
        body = r.read().decode("utf-8", "replace")
    msgs = [json.loads(l[5:].strip()) for l in body.splitlines() if l.startswith("data:")] or ([json.loads(body)] if body.strip() else [])
    return msgs[-1] if msgs else {}


def _init():
    if "ready" not in _session:
        _post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "composio-takehome", "version": "1.0"}}})
        _session["ready"] = True


def call(tool, args, timeout=180):
    """Call an MCP tool; returns the parsed JSON of its first text content block (or the raw result)."""
    _init()
    res = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}, timeout)
    if "error" in res:
        raise RuntimeError(res["error"])
    content = res.get("result", {}).get("content", [])
    text = next((c["text"] for c in content if c.get("type") == "text"), None)
    try:
        return json.loads(text) if text else res.get("result")
    except json.JSONDecodeError:
        return text


if __name__ == "__main__":
    out = call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
    print(json.dumps(out, indent=2, ensure_ascii=False)[:6000])
