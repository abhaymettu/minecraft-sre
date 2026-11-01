"""One shift: fresh server from the template, residents online, an incident injected at a seeded time, an agent on
call, a watcher that samples state every 2 s, then offline grading."""
import hashlib
import json
import os
import random
import shutil
import subprocess
import threading
import time

from . import grade, town
from .server import ROOT, Server
from .tools import AFTER_INCIDENT_S, REPORT_AFTER_S, ToolHost, _du

SAMPLE_S = 2.0
HARD_STOP_S = 360
QUOTA_HEADROOM = 400 * 1024 * 1024
RESIDENTS = ["Alex_Builds", "Steve_Mines"]
RECORD = os.environ.get("MCSRE_RECORD") == "1"
RECORD_BOX = ((4, -61, 0), (50, -53, 16))


class Bots:
    def __init__(self, port, log_path):
        self.port = port
        self.log = open(log_path, "a")
        self.procs = []
        self.events = []
        self._lock = threading.Lock()

    def start(self, bots):
        spec = json.dumps({"port": self.port, "bots": bots})
        proc = subprocess.Popen(["node", os.path.join(ROOT, "bots", "run.js"), spec], cwd=os.path.join(ROOT, "bots"),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(proc)
        threading.Thread(target=self._read, args=(proc,), daemon=True).start()
        return proc

    def _read(self, proc):
        for line in proc.stdout:
            self.log.write(line)
            self.log.flush()
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            with self._lock:
                self.events.append(ev)

    def find(self, bot=None, event=None, since=0):
        with self._lock:
            return [e for e in self.events if (bot is None or e.get("bot") == bot)
                    and (event is None or e.get("event") == event) and e.get("t", 0) / 1000 >= since]

    def stop(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        self.log.close()


def sha_tree(path):
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in sorted(os.walk(path)):
        dirnames.sort()
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            h.update(os.path.relpath(p, path).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


class Episode:
    def __init__(self, incident, agent, seed, slot, out_dir):
        self.incident = incident
        self.agent = agent
        self.seed = seed
        self.rng = random.Random(f"{incident.name}:{seed}")
        self.out = out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        port = 25600 + slot * 10
        self.server = Server(os.path.join(out_dir, "server"), port, port + 1)
        self.state = {}
        self.timeline = []
        self.events = []
        self.changes = {"modified": set(), "deleted": set()}
        self.server_cycles = []
        self.report = None
        self.declared_at = None
        self.inject_at = None
        self.injected = False
        self.inject_done = None
        self.fixed_since = None
        self.t0 = None
        self.over = False
        self._audit = open(os.path.join(out_dir, "audit.jsonl"), "a")
        self._audit_lock = threading.Lock()
        self.latest = {}

    def audit(self, row):
        with self._audit_lock:
            self._audit.write(json.dumps(row, default=str) + "\n")
            self._audit.flush()

    def event(self, kind, **detail):
        self.events.append({"t": time.time(), "kind": kind, **detail})

    def shift_elapsed(self):
        return time.time() - self.t0 if self.t0 else 0.0

    def report_allowed_at(self):
        if self.inject_done is None:
            return max(self.t0 + REPORT_AFTER_S, self.inject_at + AFTER_INCIDENT_S)
        return max(self.t0 + REPORT_AFTER_S, self.inject_done + AFTER_INCIDENT_S)

    def path(self, rel):
        return os.path.join(self.server.dir, rel)

    def declare(self, summary):
        if self.declared_at is None:
            self.declared_at = time.time()
        self.event("declare", summary=summary)

    def submit(self, report):
        self.report = report
        self.event("report")
        self.over = True

    def note_server_cycle(self, how):
        self.server_cycles.append({"t": time.time(), "how": how})

    def after_start(self):
        self.event("server_start")

    def metrics(self):
        try:
            with open(self.path("plugins/Exporter/metrics.json")) as f:
                m = json.load(f)
            m["age_s"] = round(time.time() - m["ts"] / 1000, 1)
            return m
        except (OSError, ValueError, KeyError):
            return {}

    def up(self):
        return self.server.running and self.rcon.ping()

    def disk(self):
        return _du(self.server.dir), self.quota

    def status_text(self):
        up = self.up()
        used, quota = self.disk()
        m = self.metrics() if up else {}
        lines = [f"server: {'UP' if up else 'DOWN'}"]
        if m:
            by_type = sorted(m.get("entities_by_type", {}).items(), key=lambda kv: -kv[1])[:8]
            lines += [
                f"tps (1m,5m,15m): {', '.join(str(x) for x in m.get('tps', []))}   mspt (avg): {m.get('mspt')}",
                f"heap: {m.get('heap_used_mb')} / {m.get('heap_max_mb')} MB",
                f"players online ({len(m.get('players', []))}): {', '.join(m.get('players', [])) or '-'}",
                f"entities: {m.get('entities')}  top types: {', '.join(f'{k} {v}' for k, v in by_type)}",
                f"chunks loaded: {m.get('chunks_loaded')}",
                "plugins: " + ", ".join(f"{k} {'enabled' if v else 'DISABLED'}" for k, v in sorted(m.get("plugins", {}).items())),
                f"metrics age: {m['age_s']} s" + ("  (exporter is stale: the main thread may be stalled)" if m["age_s"] > 5 else ""),
            ]
        elif up:
            lines.append("metrics unavailable (Exporter not reporting)")
        lines.append(f"disk: {used / 1e6:.0f} MB used of {quota / 1e6:.0f} MB volume ({100 * used / quota:.0f}%)")
        el = self.shift_elapsed()
        lines.append(f"shift: {el:.0f} s elapsed; report allowed after {self.report_allowed_at() - self.t0:.0f} s; "
                     f"shift ends at {HARD_STOP_S} s")
        return "\n".join(lines)

    def _inject(self):
        try:
            self.incident.inject(self)
        except Exception as e:
            self.event("inject_error", error=repr(e))
        self.inject_done = time.time()
        self.event("inject_done")

    def _watch(self):
        last_proc_alive = True
        while not self.over:
            t = time.time()
            el = t - self.t0
            if not self.injected and t >= self.inject_at:
                self.injected = True
                self.event("inject")
                threading.Thread(target=self._inject, daemon=True).start()
            alive = self.server.running
            if last_proc_alive and not alive and (not self.server_cycles or t - self.server_cycles[-1]["t"] > 90):
                self.event("server_crash")
            last_proc_alive = alive
            up = alive and self.rcon.ping()
            m = self.metrics() if up else {}
            used, _ = self.disk()
            self.latest = m
            fixed = None
            if self.inject_done:
                try:
                    self.incident.tick(self)
                    fixed = bool(up and self.incident.fixed(self))
                except Exception as e:
                    fixed = False
                    self.event("check_error", error=repr(e))
                if fixed and self.fixed_since is None:
                    self.fixed_since = t
                elif not fixed:
                    self.fixed_since = None
            self.timeline.append({"t": round(el, 1), "up": up, "tps": (m.get("tps") or [None])[0], "mspt": m.get("mspt"),
                                  "heap": m.get("heap_used_mb"), "entities": m.get("entities"),
                                  "players": len(m.get("players", [])) if m else None, "disk_mb": round(used / 1e6, 1),
                                  "fixed": fixed})
            if RECORD and up and len(self.timeline) % 2 == 0:
                self._record_frame(el)
            if el > HARD_STOP_S:
                self.event("hard_stop")
                self.over = True
                break
            time.sleep(max(0.0, SAMPLE_S - (time.time() - t)))

    def _record_frame(self, el):
        from . import anvil
        try:
            self.rcon.command("save-all flush")
            blocks = anvil.blocks_in_box(self.path("world"), *RECORD_BOX)
        except Exception:
            return
        palette = {}
        cells = []
        for key in sorted(blocks):
            b = blocks[key]
            if b != "minecraft:air":
                cells.append([*key, palette.setdefault(b, len(palette))])
        with open(os.path.join(self.out, "frames.jsonl"), "a") as f:
            f.write(json.dumps({"t": round(el, 1), "palette": list(palette), "cells": cells}) + "\n")

    def run(self):
        town.new_server_dir(self.server.dir, self.server.port, self.server.rcon_port)
        self.rcon = self.server.rcon(timeout=5)
        self.bots = Bots(self.server.port, os.path.join(self.out, "bots.jsonl"))
        result = None
        try:
            self.incident.prepare(self)
            self.server.start()
            self.rcon.connect()
            self.bots.start([{"name": n, "role": "resident"} for n in RESIDENTS])
            deadline = time.time() + 60
            while time.time() < deadline and len(self.metrics().get("players", [])) < len(RESIDENTS):
                time.sleep(1)
            self.incident.setup(self)
            self.baseline = grade.capture_baseline(self)
            self.quota = self.baseline["disk_bytes"] + QUOTA_HEADROOM
            self.t0 = time.time()
            self.host_load = {"start": os.getloadavg()[0], "cpus": os.cpu_count()}
            self.inject_at = self.t0 + self.rng.uniform(20, 40)
            self.event("shift_start")
            watcher = threading.Thread(target=self._watch, daemon=True)
            watcher.start()
            host = ToolHost(self)
            self.agent_info = self.agent.run(self, host) or {}
            self.over = True
            watcher.join(10)
            self.end_t = time.time()
            self.host_load["end"] = os.getloadavg()[0]
            live = grade.capture_live(self)
            self.bots.stop()
            self.server.stop()
            result = grade.grade(self, live)
        finally:
            self.over = True
            try:
                self.bots.stop()
            except Exception:
                pass
            self.server.kill()
            self._audit.close()
            self._archive()
        with open(os.path.join(self.out, "result.json"), "w") as f:
            json.dump(result, f, indent=1, default=str)
        return result

    def _archive(self):
        with open(os.path.join(self.out, "timeline.json"), "w") as f:
            json.dump({"t0": self.t0, "inject_t": round(self.inject_at - self.t0, 1) if self.t0 else None, "events": [
                {**e, "t": round(e["t"] - (self.t0 or e["t"]), 1)} for e in self.events], "samples": self.timeline}, f)
        for rel in ("logs/latest.log", "console.out", "server.properties", "banned-players.json"):
            src = self.path(rel)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(self.out, rel.replace("/", "_")))
        if os.environ.get("MCSRE_KEEP_SERVER") != "1":
            shutil.rmtree(self.server.dir, ignore_errors=True)
