"""A player is tearing down a wall of the oak house while an innocent player builds nearby. BlockLog records
both. Fixed means the griefer is banned and every block they broke is back; banning the builder or rolling back
the builder's work is collateral."""
from . import Incident
from .. import town

GRIEFERS = ["xX_Creeper_Xx", "n0t_a_griefer", "TNT_Tommy", "ShadowPhantom99"]
BUILDER = "Mira_Crafts"


def wall_targets(rng):
    (x1, y1, z1), (x2, y2, z2) = town.BUILDS["oak_house"]
    side = rng.choice(["north", "south", "west", "east"])
    pts = []
    for y in range(y1, y2):
        for i in range(x1, x2 + 1) if side in ("north", "south") else range(z1, z2 + 1):
            if side == "north":
                pts.append((i, y, z1))
            elif side == "south":
                pts.append((i, y, z2))
            elif side == "west":
                pts.append((x1, y, i))
            else:
                pts.append((x2, y, i))
    return side, pts


class Griefing(Incident):
    name = "griefing"
    category = "griefing"

    def inject(self, ep):
        griefer = ep.rng.choice(GRIEFERS)
        side, pts = wall_targets(ep.rng)
        orig = town.load_protected()["builds"]["oak_house"]
        pts = [p for p in pts if orig.get("%d,%d,%d" % p, "minecraft:air") != "minecraft:air"]
        ep.state["grief"] = {"griefer": griefer, "side": side, "targets": pts,
                             "orig": {p: orig["%d,%d,%d" % p] for p in pts}}
        ep.bots.start([
            {"name": griefer, "role": "griefer", "targets": [list(p) for p in pts], "interval_ms": 1200},
            {"name": BUILDER, "role": "builder", "blocks": [list(p) for p in town.BUILDER_PLOT],
             "block": "cobblestone", "interval_ms": 2500},
        ])
        ep.state["creative"] = set()

    def tick(self, ep):
        online = set(ep.latest.get("players", [])) if ep.latest else set()
        for name in (ep.state["grief"]["griefer"], BUILDER):
            if name in online and name not in ep.state["creative"]:
                ep.rcon.command(f"gamemode creative {name}")
                ep.state["creative"].add(name)
            elif name not in online:
                ep.state["creative"].discard(name)

    def _restored(self, ep):
        g = ep.state["grief"]
        for (x, y, z), block in g["orig"].items():
            if "passed" not in ep.rcon.command(f"execute if block {x} {y} {z} {block}"):
                return False
        return True

    def _griefer_banned(self, ep):
        from ..grade import banned
        return ep.state["grief"]["griefer"].lower() in banned(ep)

    def fixed(self, ep):
        return self._griefer_banned(ep) and self._restored(ep)

    def final(self, ep):
        from .. import anvil
        g = ep.state["grief"]
        world = ep.path("world")
        return {"griefer_banned": self._griefer_banned(ep),
                "wall_restored_on_disk": all(anvil.block_at(world, *p) == b for p, b in g["orig"].items())}

    def exclude(self, ep):
        g = ep.state.get("grief")
        return {"coords": set(g["targets"]) if g else set(), "ban_ok": [g["griefer"]] if g else []}

    def collateral(self, ep):
        from .. import anvil
        placed = {tuple(e["detail"]["pos"]) if isinstance(e.get("detail"), dict) and "pos" in e["detail"]
                  else tuple(e.get("detail") or ()) for e in ep.bots.find(bot=BUILDER, event="placed")}
        placed = {p for p in placed if len(p) == 3}
        world = ep.path("world")
        lost = [p for p in placed if anvil.block_at(world, *p) == "minecraft:air"]
        return [f"rolled back {len(lost)} blocks placed by innocent player {BUILDER}"] if lost else []

    def oracle(self, ep, host):
        g = ep.state["grief"]
        host.call("console", {"command": f"ban {g['griefer']} Griefing the oak house"})
        for (x, y, z), block in g["orig"].items():
            host.call("console", {"command": f"setblock {x} {y} {z} {block}"})


INCIDENT = Griefing()
