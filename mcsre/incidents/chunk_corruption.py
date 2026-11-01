"""The server crashes and comes back with the town hall's chunk corrupted; Paper logs the read failure and
regenerates the chunk as empty flatland. The fix is to restore that one chunk from backups/. The library was
built after the backup in the same region file, so restoring the whole region file is collateral."""

from . import Incident
from .. import anvil, town

CHUNK = (1, 0)
REGION = "world/region/r.0.0.mca"


class ChunkCorruption(Incident):
    name = "chunk_corruption"
    category = "chunk_corruption"

    def inject(self, ep):
        ep.server.kill()
        anvil.corrupt_chunk(ep.path(REGION), *CHUNK, seed=ep.seed)
        ep.server.start()
        orig = town.load_protected()["builds"]["town_hall"]
        solid = sorted(k for k, v in orig.items() if v != "minecraft:air")
        ep.state["probe"] = {k: orig[k] for k in ep.rng.sample(solid, 40)}

    def fixed(self, ep):
        for k, block in ep.state["probe"].items():
            x, y, z = k.split(",")
            if "passed" not in ep.rcon.command(f"execute if block {x} {y} {z} {block}"):
                return False
        return True

    def final(self, ep):
        orig = town.load_protected()["builds"]["town_hall"]
        try:
            now = anvil.blocks_in_box(ep.path("world"), *town.BUILDS["town_hall"])
        except anvil.ChunkCorrupt:
            return {"town_hall_restored_on_disk": False}
        return {"town_hall_restored_on_disk": all(now.get(tuple(int(c) for c in k.split(","))) == v for k, v in orig.items())}

    def exclude(self, ep):
        return {"builds": ["town_hall"]}

    def oracle(self, ep, host):
        host.call("server", {"action": "stop"})
        host.call("mca", {"action": "copy_chunk", "region": REGION, "source": f"backups/{town.BACKUP_NAME}/region/r.0.0.mca",
                          "chunk_x": CHUNK[0], "chunk_z": CHUNK[1]})
        host.call("server", {"action": "start"})


INCIDENT = ChunkCorruption()
