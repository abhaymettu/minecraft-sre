"""Minimal stdio MCP server that forwards tools/list and tools/call to the episode bridge (MCSRE_BRIDGE)."""
import json
import os
import sys
import urllib.request

BRIDGE = os.environ["MCSRE_BRIDGE"]


def bridge(method, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BRIDGE, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        mid, method = msg.get("id"), msg.get("method")
        if mid is None:
            continue
        if method == "initialize":
            reply(mid, {"protocolVersion": msg["params"].get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}}, "serverInfo": {"name": "sre", "version": "1.0"}})
        elif method == "tools/list":
            reply(mid, {"tools": bridge("GET")["tools"]})
        elif method == "tools/call":
            p = msg["params"]
            try:
                out = bridge("POST", {"name": p["name"], "arguments": p.get("arguments") or {}})
                reply(mid, {"content": [{"type": "text", "text": out["text"]}], "isError": out["is_error"]})
            except Exception as e:
                reply(mid, {"content": [{"type": "text", "text": f"tool bridge error: {e}"}], "isError": True})
        else:
            reply(mid, {})


if __name__ == "__main__":
    main()
