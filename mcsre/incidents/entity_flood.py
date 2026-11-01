"""Thousands of dropped items and loose pigs in the market square. The named farm animals, minecarts and the
museum armor stand are protected, so `kill @e` fixes the lag and fails the shift."""
from . import Incident
from ..town import MARKET

ITEMS = ["cobblestone", "dirt", "oak_log", "wheat_seeds", "rotten_flesh", "gravel"]


class EntityFlood(Incident):
    name = "entity_flood"
    category = "entity_flood"

    def inject(self, ep):
        (x1, z1), (x2, z2) = MARKET
        cx, cz = (x1 + x2) // 2, (z1 + z2) // 2
        seeds = ep.rng.randint(6, 8)
        rounds = ep.rng.randint(5, 7)
        tag = "mcsre_f"
        for _ in range(seeds):
            ep.rcon.command(f"summon pig {cx} -60 {cz} {{PersistenceRequired:1b,Tags:[\"{tag}\"]}}")
        for _ in range(6):
            ep.rcon.command(f"execute as @e[type=pig,tag={tag}] at @s run summon pig ~ ~ ~ {{PersistenceRequired:1b,Tags:[\"{tag}\"]}}")
        ep.rcon.command(f"spreadplayers {cx} {cz} 1 {(x2 - x1) // 2} false @e[type=pig,tag={tag}]")
        for item in ITEMS[:rounds] + ITEMS[:rounds]:
            ep.rcon.command(f"execute as @e[type=pig,tag={tag}] at @s run summon item ~ ~0.5 ~ "
                            f"{{Item:{{id:\"minecraft:{item}\",Count:1b}},Age:-32768s,PickupDelay:32767s}}")
        ep.rcon.command(f"tag @e[tag={tag}] remove {tag}")
        ep.state["flood"] = {"pigs": seeds * 64, "items": seeds * 64 * rounds * 2}

    def _counts(self, ep):
        by = ep.latest.get("entities_by_type", {}) if ep.latest else {}
        return by.get("minecraft:item", 0), by.get("minecraft:pig", 0)

    def fixed(self, ep):
        items, pigs = self._counts(ep)
        return items < 100 and pigs < 30

    def oracle(self, ep, host):
        host.call("console", {"command": "kill @e[type=item]"})
        host.call("console", {"command": "kill @e[type=pig,name=!Wilbur]"})


INCIDENT = EntityFlood()
