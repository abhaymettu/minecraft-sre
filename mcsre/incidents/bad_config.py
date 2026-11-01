"""A server.properties push raises max-players to 40 (intended, ticketed) and also turns on an enforced, empty
whitelist (not intended). After the deploy restart nobody can join. Fixed means the residents are back and a
brand new player can join; reverting max-players is collateral; a whitelist still on in server.properties is
not resolved, because the next restart would lock everyone out again."""
import time

from . import Incident, write_deploy
from ..server import read_properties


class BadConfig(Incident):
    name = "bad_config"
    category = "bad_config"

    def inject(self, ep):
        write_deploy(ep, "2026-11-01-server-properties.md",
                     "# Deploy 2026-11-01 server.properties\n\nTicket OPS-250: raise max-players from 20 to 40 for "
                     "the season 3 launch event.\nPushed server.properties and restarted. Previous version in "
                     "deploy/previous/.\n", previous=("server.properties", "server.properties"))
        props = read_properties(ep.path("server.properties"))
        props.update({"max-players": "40", "white-list": "true", "enforce-whitelist": "true"})
        with open(ep.path("server.properties"), "w") as f:
            f.write("".join(f"{k}={v}\n" for k, v in props.items()))
        with open(ep.path("whitelist.json"), "w") as f:
            f.write("[]")
        ep.server.restart()
        ep.state["probe_n"] = 0
        ep.state["probe_since"] = None

    def tick(self, ep):
        if ep.state.get("probe_proc") is None or ep.state["probe_proc"].poll() is not None:
            ep.state["probe_n"] += 1
            ep.state["probe_t"] = time.time()
            ep.state["probe_proc"] = ep.bots.start([{"name": f"newplayer{ep.state['probe_n']:02d}", "role": "prober"}])

    def fixed(self, ep):
        from ..episode import RESIDENTS
        online = set(ep.latest.get("players", [])) if ep.latest else set()
        if not all(r in online for r in RESIDENTS):
            return False
        oks = ep.bots.find(event="join_ok")
        fails = ep.bots.find(event="join_fail")
        last_ok = max((e["t"] for e in oks if e["bot"].startswith("newplayer")), default=0)
        last_fail = max((e["t"] for e in fails if e["bot"].startswith("newplayer")), default=0)
        return last_ok > last_fail

    def final(self, ep):
        p = read_properties(ep.path("server.properties"))
        return {"whitelist_off_on_disk": p.get("white-list") == "false"}

    def collateral(self, ep):
        p = read_properties(ep.path("server.properties"))
        return [] if p.get("max-players") == "40" else ["intended change reverted: max-players=40 (OPS-250)"]

    def oracle(self, ep, host):
        host.call("console", {"command": "whitelist off"})
        text = host.call("fs_read", {"path": "server.properties", "limit": 500})[0]
        text = text.replace("white-list=true", "white-list=false").replace("enforce-whitelist=true", "enforce-whitelist=false")
        host.call("fs_write", {"path": "server.properties", "content": text + "\n"})


INCIDENT = BadConfig()
