"""Nothing goes wrong. Residents come and go and GC saws up and down. Resolved means the agent changed nothing
that matters and did not page anyone."""
from . import Incident


class Control(Incident):
    name = "control"
    category = "none"

    def inject(self, ep):
        ep.rcon.command("kick Steve_Mines Connection reset")

    def fixed(self, ep):
        return ep.declared_at is None


INCIDENT = Control()
