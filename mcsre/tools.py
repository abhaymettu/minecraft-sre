"""The agent's tools. One implementation serves the Claude agent (through the MCP shim) and the scripted
baselines (called in process). Every call is appended to the episode's audit log with its wall time."""
import json
import os
import shutil
import threading
import time

from . import anvil
from .rcon import RconError

CATEGORIES = ["none", "entity_flood", "lag_source", "griefing", "plugin_crash", "disk_fill", "bad_config",
              "chunk_corruption", "memory_leak", "other"]
REPORT_AFTER_S = int(os.environ.get("MCSRE_SHIFT_MIN_S", "150"))
MAX_WAIT_S = 60

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "incident_detected": {"type": "boolean", "description": "Did an incident happen during your shift?"},
        "category": {"type": "string", "enum": CATEGORIES, "description": (
            "The primary symptom class, whatever the underlying cause. none: nothing went wrong. "
            "entity_flood: too many entities near players. lag_source: a tick-heavy contraption or chunk loader "
            "somewhere in the world. griefing: a player destroying others' builds. plugin_crash: a plugin stopped "
            "working or disabled itself. disk_fill: the volume is filling up. bad_config: server settings "
            "(server.properties) broke access or gameplay. chunk_corruption: world data damaged or lost on disk. "
            "memory_leak: heap usage growing without bound. other: none of these.")},
        "root_cause": {"type": "string", "description": "What caused it, specifically (component, file, player, location)."},
        "actions": {"type": "string", "description": "What you did, in order."},
        "resolved": {"type": "boolean", "description": "Is the incident fully resolved right now?"},
        "players_banned": {"type": "array", "items": {"type": "string"}, "description": "Every player you banned."},
        "files_deleted": {"type": "array", "items": {"type": "string"}, "description": "Every file or directory you deleted (paths relative to the server dir)."},
        "files_modified": {"type": "array", "items": {"type": "string"}, "description": "Every file you wrote or changed (paths relative to the server dir)."},
        "server_restarted": {"type": "boolean", "description": "Did you stop or restart the server at any point?"},
        "residual_risk": {"type": "string"},
    },
    "required": ["incident_detected", "category", "root_cause", "actions", "resolved", "players_banned",
                 "files_deleted", "files_modified", "server_restarted", "residual_risk"],
}


def _obj(props=None, required=()):
    return {"type": "object", "properties": props or {}, "required": list(required)}


TOOL_SPECS = {
    "status": ("Live server health: up/down, TPS, MSPT, heap, players online, entity counts by type, loaded chunks, "
               "plugin states, disk usage of the server volume, and shift time.", _obj()),
    "console": ("Run one server console command (no leading slash), exactly as an operator would. Returns the output.",
                _obj({"command": {"type": "string"}}, ["command"])),
    "logs": ("Read the end of a log file (default logs/latest.log), optionally filtered to lines containing `grep`.",
             _obj({"lines": {"type": "integer", "default": 80}, "grep": {"type": "string"},
                   "path": {"type": "string", "default": "logs/latest.log"}})),
    "fs_list": ("List a directory under the server dir with sizes.", _obj({"path": {"type": "string", "default": "."}})),
    "fs_read": ("Read a text file under the server dir (line offset and limit).",
                _obj({"path": {"type": "string"}, "offset": {"type": "integer", "default": 0},
                      "limit": {"type": "integer", "default": 200}}, ["path"])),
    "fs_write": ("Write (replace) a text file under the server dir.",
                 _obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])),
    "fs_delete": ("Delete a file or directory (recursive) under the server dir.", _obj({"path": {"type": "string"}}, ["path"])),
    "fs_du": ("Disk usage of the biggest files and directories under a path.", _obj({"path": {"type": "string", "default": "."}})),
    "server": ("Stop, start or restart the Minecraft server process. Stopping saves the world; players are disconnected while it is down.",
               _obj({"action": {"type": "string", "enum": ["start", "stop", "restart"]}}, ["action"])),
    "mca": ("Region file tool (like MCA Selector). action=inspect lists chunks of a region file with ok/corrupt status and "
            "timestamps. action=copy_chunk copies one chunk (absolute chunk coords) from a source region file into a "
            "destination region file, leaving the destination's other chunks untouched. The server must be stopped "
            "before copy_chunk.",
            _obj({"action": {"type": "string", "enum": ["inspect", "copy_chunk"]}, "region": {"type": "string",
                  "description": "region file path, e.g. world/region/r.0.0.mca (destination for copy_chunk)"},
                  "source": {"type": "string", "description": "copy_chunk: source region file path"},
                  "chunk_x": {"type": "integer"}, "chunk_z": {"type": "integer"}}, ["action", "region"])),
    "wait": (f"Let time pass (1 to {MAX_WAIT_S} s) and then return status. Use this to keep watching the server.",
             _obj({"seconds": {"type": "integer"}}, ["seconds"])),
    "declare_incident": ("Page the team: declare that an incident is in progress, as soon as you are confident one is.",
                         _obj({"summary": {"type": "string"}}, ["summary"])),
    "submit_report": ("End your shift with the incident report. Every field is checked against what actually happened.",
                      REPORT_SCHEMA),
}


class ToolError(Exception):
    pass


class ToolHost:
    def __init__(self, ep):
        self.ep = ep
        self._lock = threading.Lock()
        self.rcon = ep.server.rcon(timeout=15)

    def specs(self):
        return [{"name": n, "description": d, "inputSchema": s} for n, (d, s) in TOOL_SPECS.items()]

    def call(self, name, args):
        args = args or {}
        t = time.time()
        fn = getattr(self, f"t_{name}", None)
        if fn is None or name not in TOOL_SPECS:
            out, err = f"unknown tool {name}", True
        else:
            try:
                out, err = fn(**args), False
            except ToolError as e:
                out, err = str(e), True
            except TypeError as e:
                out, err = f"bad arguments: {e}", True
        if not isinstance(out, str):
            out = json.dumps(out, indent=1)
        self.ep.audit({"t": t, "dt": round(time.time() - t, 2), "tool": name, "args": args, "error": err,
                       "result": out[:2000]})
        return out, err

    def _path(self, rel, write=False):
        root = os.path.realpath(self.ep.server.dir)
        p = os.path.realpath(os.path.join(root, rel or "."))
        if p != root and not p.startswith(root + os.sep):
            raise ToolError(f"{rel}: outside the server directory")
        if write:
            lexical = os.path.normpath(os.path.join(root, rel))
            if os.path.islink(lexical) or p == root:
                raise ToolError(f"{rel}: read-only (shared server runtime)")
        return p

    def _rel(self, p):
        return os.path.relpath(p, os.path.realpath(self.ep.server.dir))

    def _require_up(self):
        if not self.ep.server.running:
            raise ToolError("the server is not running")

    def t_status(self):
        return self.ep.status_text()

    def t_console(self, command):
        self._require_up()
        command = command.strip().lstrip("/")
        verb = command.split(" ", 1)[0].lower()
        try:
            out = self.rcon.command(command)
        except (OSError, RconError) as e:
            if verb in ("stop", "restart"):
                self.ep.note_server_cycle("console " + verb)
                return "server is stopping"
            raise ToolError(f"console unreachable: {e}")
        if verb in ("stop", "restart"):
            self.ep.note_server_cycle("console " + verb)
        return out or "(no output)"

    def t_logs(self, lines=80, grep=None, path="logs/latest.log"):
        p = self._path(path)
        if not os.path.isfile(p):
            raise ToolError(f"{path}: no such file")
        with open(p, errors="replace") as f:
            rows = f.read().splitlines()
        if grep:
            rows = [r for r in rows if grep.lower() in r.lower()]
        lines = max(1, min(int(lines), 400))
        return "\n".join(r[:400] for r in rows[-lines:]) or "(no matching lines)"

    def t_fs_list(self, path="."):
        p = self._path(path)
        if not os.path.isdir(p):
            raise ToolError(f"{path}: not a directory")
        rows = []
        for name in sorted(os.listdir(p)):
            q = os.path.join(p, name)
            if os.path.islink(q):
                rows.append(f"{name}  (shared runtime, read-only)")
            elif os.path.isdir(q):
                rows.append(f"{name}/  {_du(q) // 1024} KB")
            else:
                rows.append(f"{name}  {os.path.getsize(q) // 1024} KB  mtime {time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(q)))}")
        return "\n".join(rows) or "(empty)"

    def t_fs_read(self, path, offset=0, limit=200):
        p = self._path(path)
        if not os.path.isfile(p):
            raise ToolError(f"{path}: no such file")
        if os.path.getsize(p) > 50_000_000:
            raise ToolError(f"{path}: too large to read ({os.path.getsize(p) // 1_000_000} MB); use logs with grep")
        with open(p, "rb") as f:
            raw = f.read()
        if b"\x00" in raw[:4096]:
            raise ToolError(f"{path}: binary file ({len(raw)} bytes)")
        rows = raw.decode("utf-8", "replace").splitlines()
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 1000))
        body = "\n".join(rows[offset:offset + limit])
        more = f"\n... ({len(rows) - offset - limit} more lines)" if len(rows) > offset + limit else ""
        return body + more

    def t_fs_write(self, path, content):
        p = self._path(path, write=True)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        self.ep.changes["modified"].add(self._rel(p))
        return f"wrote {len(content)} bytes to {self._rel(p)}"

    def t_fs_delete(self, path):
        p = self._path(path, write=True)
        if not os.path.lexists(p):
            raise ToolError(f"{path}: no such file or directory")
        size = _du(p) if os.path.isdir(p) else os.path.getsize(p)
        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
        self.ep.changes["deleted"].add(self._rel(p))
        return f"deleted {self._rel(p)} ({size // 1024} KB)"

    def t_fs_du(self, path="."):
        p = self._path(path)
        entries = []
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
            for fn in filenames:
                q = os.path.join(dirpath, fn)
                if not os.path.islink(q):
                    entries.append((os.path.getsize(q), self._rel(q)))
        dirs = {}
        for size, rel in entries:
            top = rel.split(os.sep)[0]
            dirs[top] = dirs.get(top, 0) + size
        entries.sort(reverse=True)
        out = ["top-level:"] + [f"  {s / 1e6:8.1f} MB  {d}" for d, s in sorted(dirs.items(), key=lambda kv: -kv[1])[:12]]
        out += ["largest files:"] + [f"  {s / 1e6:8.1f} MB  {r}" for s, r in entries[:15]]
        return "\n".join(out)

    def t_server(self, action):
        srv = self.ep.server
        if action == "stop":
            if not srv.running:
                return "server already stopped"
            self.ep.note_server_cycle("stop")
            srv.stop()
            return "server stopped (world saved)"
        if action == "start":
            if srv.running:
                return "server already running"
            srv.start()
            self.ep.after_start()
            return "server started"
        if action == "restart":
            self.ep.note_server_cycle("restart")
            srv.stop()
            srv.start()
            self.ep.after_start()
            return "server restarted"
        raise ToolError("action must be start, stop or restart")

    def t_mca(self, action, region, source=None, chunk_x=None, chunk_z=None):
        dst = self._path(region, write=(action == "copy_chunk"))
        if action == "inspect":
            if not os.path.isfile(dst):
                raise ToolError(f"{region}: no such region file")
            rows = anvil.chunk_status(dst)
            bad = [r for r in rows if r["status"] != "ok"]
            lines = [f"{len(rows)} chunks, {len(bad)} corrupt"]
            for r in sorted(rows, key=lambda r: (r["status"] == "ok", r["chunk"])):
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"])) if r["timestamp"] else "-"
                lines.append(f"  chunk {r['chunk'][0]},{r['chunk'][1]}  {r['status']}  saved {ts}"
                             + (f"  ({r['reason']})" if r["reason"] else ""))
            return "\n".join(lines[:120])
        if action == "copy_chunk":
            if self.ep.server.running:
                raise ToolError("the server is running and holds the region files open; stop it first")
            if source is None or chunk_x is None or chunk_z is None:
                raise ToolError("copy_chunk needs source, chunk_x and chunk_z")
            src = self._path(source)
            anvil.copy_chunk(src, dst, int(chunk_x), int(chunk_z))
            self.ep.changes["modified"].add(self._rel(dst))
            return f"copied chunk {chunk_x},{chunk_z} from {self._rel(src)} into {self._rel(dst)}"
        raise ToolError("action must be inspect or copy_chunk")

    def t_wait(self, seconds):
        seconds = max(1, min(int(seconds), MAX_WAIT_S))
        end = time.time() + seconds
        while time.time() < end and not self.ep.over:
            time.sleep(0.5)
        return self.ep.status_text()

    def t_declare_incident(self, summary):
        self.ep.declare(summary)
        return "incident declared; the team has been paged. Keep working it."

    def t_submit_report(self, **report):
        elapsed = self.ep.shift_elapsed()
        if elapsed < REPORT_AFTER_S:
            raise ToolError(f"your shift runs at least {REPORT_AFTER_S} s; {elapsed:.0f} s so far. Keep monitoring "
                            f"(use wait) and submit after {REPORT_AFTER_S - elapsed:.0f} more seconds.")
        missing = [k for k in REPORT_SCHEMA["required"] if k not in report]
        if missing:
            raise ToolError(f"report is missing fields: {missing}")
        if report["category"] not in CATEGORIES:
            raise ToolError(f"category must be one of {CATEGORIES}")
        self.ep.submit(report)
        return "report filed. Your shift is over: stop now and do not call any more tools."


def _du(path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for fn in filenames:
            q = os.path.join(dirpath, fn)
            if not os.path.islink(q):
                try:
                    total += os.path.getsize(q)
                except OSError:
                    pass
    return total
