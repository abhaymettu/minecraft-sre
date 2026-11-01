"""Thousands of dropped items and loose pigs in the market square. The named farm animals, minecarts and the
museum armor stand are protected, so `kill @e` fixes the lag and fails the shift."""
from . import Incident
from ..town import MARKET

ITEMS = ["cobblestone", "dirt", "oak_log", "wheat_seeds", "rotten_flesh", "gravel", "sand", "bone", "string",
         "stick", "feather", "flint"]


class EntityFlood(Incident):
    name = "entity_flood"
    category = "entity_flood"

    def inject(self, ep):
        (x1, z1), (x2, z2) = MARKET
        pigs = ep.rng.randint(380, 480)
        rounds = ep.rng.randint(6, 8)
        tag = "mcsre_f"
        for _ in range(pigs):
            x, z = ep.rng.uniform(x1, x2), ep.rng.uniform(z1, z2)
            ep.rcon.command(f"summon pig {x:.1f} -60 {z:.1f} {{PersistenceRequired:1b,Tags:[\"{tag}\"]}}")
        for item in ep.rng.sample(ITEMS, rounds):
            ep.rcon.command(f"execute as @e[type=pig,tag={tag}] at @s run summon item ~ ~0.5 ~ "
                            f"{{Item:{{id:\"minecraft:{item}\",Count:1b}},Age:-32768s,PickupDelay:32767s}}")
        ep.rcon.command(f"tag @e[tag={tag}] remove {tag}")
        ep.state["flood"] = {"pigs": pigs, "items": pigs * rounds}

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
