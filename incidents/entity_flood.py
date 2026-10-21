"""Entity flood incident: spawns thousands of entities to cause GC pressure and TPS drop."""
import time

from server.rcon import Rcon


def inject(rcon: Rcon, entity_count=2000, entity_type="item", batch_size=50, delay=0.1):
    """Flood the server with entities via RCON summon commands.

    Items are light individually but thousands overwhelm the GC.
    The agent must clean them up without destroying player builds.
    """
    spawned = 0
    if entity_type == "item":
        cmd_tpl = 'summon minecraft:item ~ 1 ~ {Item:{id:"minecraft:cobblestone",count:1}}'
    elif entity_type == "pig":
        cmd_tpl = "summon minecraft:pig ~ 1 ~"
    else:
        cmd_tpl = f"summon minecraft:{entity_type} ~ 1 ~"

    for _ in range(0, entity_count, batch_size):
        for _ in range(min(batch_size, entity_count - spawned)):
            try:
                rcon.command(cmd_tpl)
                spawned += 1
            except Exception:
                pass
        if delay > 0:
            time.sleep(delay)

    return spawned


def inject_mixed(rcon: Rcon, items=1500, pigs=500):
    """Mixed flood: items for GC pressure, pigs for tick processing load."""
    n_items = inject(rcon, entity_count=items, entity_type="item")
    n_pigs = inject(rcon, entity_count=pigs, entity_type="pig")
    return {"items": n_items, "pigs": n_pigs, "total": n_items + n_pigs}
