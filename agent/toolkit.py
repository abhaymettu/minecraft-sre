"""SRE remediation actions available to the agent."""
import re
import time

from server.rcon import Rcon


class SREToolkit:
    def __init__(self, rcon: Rcon):
        self.rcon = rcon
        self.actions_log = []

    def _log(self, action, result):
        self.actions_log.append({
            "timestamp": time.time(),
            "action": action,
            "result": result,
        })

    def kill_entities(self, entity_type: str) -> int:
        selector = f"@e[type=minecraft:{entity_type}]"
        resp = self.rcon.command(f"kill {selector}")
        match = re.search(r"Killed (\d+)", resp)
        killed = int(match.group(1)) if match else 0
        self._log(f"kill_{entity_type}", {"killed": killed})
        return killed

    def kill_items(self) -> int:
        return self.kill_entities("item")

    def set_view_distance(self, distance: int) -> str:
        resp = self.rcon.command(f"gamerule viewDistance {distance}")
        self._log("set_view_distance", {"distance": distance, "response": resp})
        return resp

    def set_simulation_distance(self, distance: int) -> str:
        resp = self.rcon.command(f"gamerule simulationDistance {distance}")
        self._log("set_simulation_distance", {"distance": distance, "response": resp})
        return resp

    def save_world(self) -> str:
        resp = self.rcon.command("save-all flush")
        self._log("save_world", {"response": resp})
        return resp

    def set_gamerule(self, rule: str, value: str) -> str:
        resp = self.rcon.command(f"gamerule {rule} {value}")
        self._log("set_gamerule", {"rule": rule, "value": value, "response": resp})
        return resp

    def get_entity_count(self, entity_type: str = None) -> str:
        if entity_type:
            selector = f"@e[type=minecraft:{entity_type}]"
        else:
            selector = "@e[type=!minecraft:player]"
        resp = self.rcon.command(f"execute if entity {selector}")
        return resp

    def execute_command(self, cmd: str) -> str:
        resp = self.rcon.command(cmd)
        self._log("execute_command", {"cmd": cmd, "response": resp})
        return resp
