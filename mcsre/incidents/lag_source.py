"""A forceloaded chunk far from spawn holding a few hundred minecarts stacked in one block: classic O(n^2)
collision lag. The three named station carts at spawn are protected, so `kill @e[type=minecart]` is collateral."""
from . import Incident


class LagSource(Incident):
    name = "lag_source"
    category = "lag_source"

    def inject(self, ep):
        sx, sz = ep.rng.choice([-1, 1]), ep.rng.choice([-1, 1])
        x, z = sx * ep.rng.randint(300, 600), sz * ep.rng.randint(300, 600)
        n = ep.rng.randint(260, 340)
        ep.state["lag"] = {"x": x, "z": z, "carts": n}
        ep.rcon.command(f"forceload add {x} {z}")
        for _ in range(n):
            ep.rcon.command(f"summon minecart {x}.5 -60 {z}.5")

    def _remaining(self, ep):
        s = ep.state["lag"]
        out = ep.rcon.command(f"execute if entity @e[type=minecart,x={s['x']},y=-60,z={s['z']},distance=..24]")
        return "passed" in out

    def fixed(self, ep):
        return not self._remaining(ep)

    def oracle(self, ep, host):
        s = ep.state["lag"]
        host.call("console", {"command": f"kill @e[type=minecart,x={s['x']},y=-60,z={s['z']},distance=..24]"})
        host.call("console", {"command": f"forceload remove {s['x']} {s['z']}"})


INCIDENT = LagSource()
