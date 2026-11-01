"""Incident registry. Each incident defines how it breaks the server and how to check, from state alone,
whether it is fixed."""
class Incident:
    name = ""
    category = ""

    def prepare(self, ep):
        """Before the server starts (edit files on disk)."""

    def setup(self, ep):
        """Server up, residents online, before the shift starts."""

    def inject(self, ep):
        raise NotImplementedError

    def tick(self, ep):
        """Every sample after injection."""

    def fixed(self, ep):
        """Live predicate, polled every sample. Time to fix is when it last became true."""
        raise NotImplementedError

    def final(self, ep):
        """Offline checks after the server is stopped; every value must be true to count as resolved."""
        return {}

    def exclude(self, ep):
        """Protected things this incident damages on purpose (graded as resolution, not collateral)."""
        return {}

    def collateral(self, ep):
        return []

    def oracle(self, ep, host):
        """Reference fix with ground truth, through the same tools the agent has."""


def write_deploy(ep, name, text, previous=None):
    with open(ep.path(f"deploy/{name}"), "w") as f:
        f.write(text)
    if previous:
        src, dst = previous
        with open(ep.path(src)) as a, open(ep.path(f"deploy/previous/{dst}"), "w") as b:
            b.write(a.read())


def registry():
    from . import (bad_config, chunk_corruption, control, disk_fill, entity_flood, griefing, lag_source,
                   memory_leak, plugin_crash)
    mods = [entity_flood, lag_source, griefing, plugin_crash, disk_fill, bad_config, chunk_corruption, memory_leak, control]
    return {m.INCIDENT.name: m.INCIDENT for m in mods}
