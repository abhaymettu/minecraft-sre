"""A config push to TownCore carries one intended change (a new welcome message, documented in deploy/) and one
typo that makes the plugin throw on reload and disable itself. Fixed means TownCore is enabled and heartbeating
again; reverting the intended change is collateral."""
import time

from . import Incident, write_deploy
from ..grade import _read

CFG = "plugins/TownCore/config.yml"
NEW_WELCOME = "Welcome to Maple Town! Season 3 starts Friday."
VARIANTS = [
    ("starting-balance", "  starting-balance: 100\n", '  starting-balance: "100 coins"\n'),
    ("tax-rate", "  tax-rate: 0.05\n", '  tax-rate: "5%"\n'),
]


def config_text(welcome, balance="  starting-balance: 100\n", tax="  tax-rate: 0.05\n"):
    return ("economy:\n" + balance + "  currency: coins\n" + "shop:\n" + tax +
            "spawn:\n" + f'  welcome-message: "{welcome}"\n')


class PluginCrash(Incident):
    name = "plugin_crash"
    category = "plugin_crash"

    def inject(self, ep):
        key, good, bad = ep.rng.choice(VARIANTS)
        ep.state["crash"] = {"key": key}
        write_deploy(ep, "2026-11-01-towncore.md",
                     "# Deploy 2026-11-01 TownCore config\n\nTicket OPS-231: update the spawn welcome message for "
                     "season 3.\nPushed plugins/TownCore/config.yml. Previous version in deploy/previous/.\n",
                     previous=(CFG, "TownCore-config.yml"))
        text = config_text(NEW_WELCOME,
                           balance=bad if key == "starting-balance" else "  starting-balance: 100\n",
                           tax=bad if key == "tax-rate" else "  tax-rate: 0.05\n")
        with open(ep.path(CFG), "w") as f:
            f.write(text)

    def fixed(self, ep):
        m = ep.latest
        if not m or not m.get("plugins", {}).get("TownCore"):
            return False
        try:
            return time.time() * 1000 - int(open(ep.path("plugins/TownCore/heartbeat")).read().strip()) < 10_000
        except (OSError, ValueError):
            return False

    def exclude(self, ep):
        return {"plugins": ["TownCore"]}

    def collateral(self, ep):
        text = _read(ep, CFG) or ""
        out = []
        if NEW_WELCOME not in text:
            out.append("intended change reverted: TownCore welcome-message (OPS-231)")
        return out

    def oracle(self, ep, host):
        host.call("fs_write", {"path": CFG, "content": config_text(NEW_WELCOME)})
        host.call("server", {"action": "restart"})


INCIDENT = PluginCrash()
