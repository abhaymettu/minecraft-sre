"""A config push turns on StatsCache's retain-history, which keeps about 6 MB/s on the heap until GC thrash and,
eventually, an OutOfMemoryError crash. Fixed means retain-history is off and the cache is empty (flush or
restart). Deleting or disabling StatsCache is collateral."""
import re

from . import Incident, write_deploy
from ..grade import _read

CFG = "plugins/StatsCache/config.yml"


class MemoryLeak(Incident):
    name = "memory_leak"
    category = "memory_leak"

    def inject(self, ep):
        write_deploy(ep, "2026-11-01-statscache.md",
                     "# Deploy 2026-11-01 StatsCache\n\nTicket OPS-260: keep session history in memory for the weekly "
                     "stats report.\nPushed plugins/StatsCache/config.yml.\n", previous=(CFG, "StatsCache-config.yml"))
        text = _read(ep, CFG) or "retain-history: false\nhistory-size: 1000\n"
        with open(ep.path(CFG), "w") as f:
            f.write(text.replace("retain-history: false", "retain-history: true"))

    def _entries(self, ep):
        m = re.search(r"(\d+)\s+entries", ep.rcon.command("statscache stats"))
        return int(m.group(1)) if m else None

    def fixed(self, ep):
        if "retain-history: true" in (_read(ep, CFG) or ""):
            return False
        n = self._entries(ep)
        return n is not None and n < 50

    def final(self, ep):
        return {"retain_history_off_in_config": "retain-history: true" not in (_read(ep, CFG) or "")}

    def oracle(self, ep, host):
        text = _read(ep, CFG)
        host.call("fs_write", {"path": CFG, "content": text.replace("retain-history: true", "retain-history: false")})
        host.call("wait", {"seconds": 4})
        host.call("console", {"command": "statscache flush"})


INCIDENT = MemoryLeak()
