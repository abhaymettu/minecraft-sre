"""Server metrics collection: TPS, memory, GC log analysis."""
import os
import re
import time
from dataclasses import dataclass, field

from server.rcon import Rcon


@dataclass
class ServerMetrics:
    timestamp: float = 0.0
    tps_1m: float = 20.0
    tps_5m: float = 20.0
    tps_15m: float = 20.0
    memory_used_mb: int = 0
    memory_max_mb: int = 0
    online_players: int = 0
    responsive: bool = True


@dataclass
class GCEvent:
    timestamp: float = 0.0
    pause_ms: float = 0.0
    heap_before_mb: int = 0
    heap_after_mb: int = 0
    heap_max_mb: int = 0
    cause: str = ""


TPS_RE = re.compile(r"[\d.]+")
GC_PAUSE_RE = re.compile(
    r"\[([^\]]+)\].*Pause\s+\w+.*?(\d+)M->(\d+)M\((\d+)M\)\s+([\d.]+)ms"
)


class Monitor:
    def __init__(self, rcon: Rcon, gc_log_path: str = None):
        self.rcon = rcon
        self.gc_log_path = gc_log_path
        self._gc_offset = 0

    def collect(self) -> ServerMetrics:
        m = ServerMetrics(timestamp=time.time())
        try:
            tps_raw = self.rcon.command("tps")
            nums = TPS_RE.findall(tps_raw)
            if len(nums) >= 3:
                m.tps_1m = min(float(nums[-3]), 20.0)
                m.tps_5m = min(float(nums[-2]), 20.0)
                m.tps_15m = min(float(nums[-1]), 20.0)
        except Exception:
            m.responsive = False

        try:
            mem_raw = self.rcon.command("gc")
            mem_nums = re.findall(r"(\d+)\s*MB", mem_raw)
            if len(mem_nums) >= 2:
                m.memory_used_mb = int(mem_nums[0])
                m.memory_max_mb = int(mem_nums[1])
        except Exception:
            pass

        try:
            list_raw = self.rcon.command("list")
            count_match = re.search(r"(\d+)", list_raw)
            if count_match:
                m.online_players = int(count_match.group(1))
        except Exception:
            pass

        return m

    def read_gc_events(self) -> list[GCEvent]:
        if not self.gc_log_path or not os.path.exists(self.gc_log_path):
            return []

        events = []
        with open(self.gc_log_path) as f:
            f.seek(self._gc_offset)
            for line in f:
                match = GC_PAUSE_RE.search(line)
                if match:
                    events.append(GCEvent(
                        timestamp=time.time(),
                        heap_before_mb=int(match.group(2)),
                        heap_after_mb=int(match.group(3)),
                        heap_max_mb=int(match.group(4)),
                        pause_ms=float(match.group(5)),
                    ))
            self._gc_offset = f.tell()

        return events

    def detect_incident(self, metrics: ServerMetrics, gc_events: list[GCEvent]) -> dict | None:
        if not metrics.responsive:
            return {"type": "server_unresponsive", "severity": "critical"}

        if metrics.tps_1m < 10:
            incident = {"type": "severe_lag", "severity": "critical", "tps": metrics.tps_1m}
            long_pauses = [e for e in gc_events if e.pause_ms > 200]
            if long_pauses:
                incident["gc_pressure"] = True
                incident["worst_pause_ms"] = max(e.pause_ms for e in long_pauses)
            return incident

        if metrics.tps_1m < 15:
            return {"type": "degraded_performance", "severity": "warning", "tps": metrics.tps_1m}

        if metrics.memory_max_mb > 0:
            usage_pct = metrics.memory_used_mb / metrics.memory_max_mb
            if usage_pct > 0.9:
                return {"type": "memory_pressure", "severity": "warning", "usage_pct": usage_pct}

        return None
