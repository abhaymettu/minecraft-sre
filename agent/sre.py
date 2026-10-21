"""SRE agent: monitors the server and responds to incidents."""
import time

from server.rcon import Rcon
from .monitor import Monitor, ServerMetrics, GCEvent
from .toolkit import SREToolkit


class SREAgent:
    def __init__(self, rcon: Rcon, gc_log_path: str = None):
        self.rcon = rcon
        self.monitor = Monitor(rcon, gc_log_path)
        self.toolkit = SREToolkit(rcon)
        self.event_log = []
        self.metrics_history = []

    def _log_event(self, event_type, detail):
        entry = {"timestamp": time.time(), "type": event_type, "detail": detail}
        self.event_log.append(entry)

    def observe(self) -> tuple[ServerMetrics, list[GCEvent]]:
        metrics = self.monitor.collect()
        gc_events = self.monitor.read_gc_events()
        self.metrics_history.append(metrics)
        return metrics, gc_events

    def respond(self, incident: dict) -> list[str]:
        """Choose and execute remediation actions based on the incident."""
        actions_taken = []

        if incident["type"] == "server_unresponsive":
            self._log_event("alert", "server unresponsive, cannot remediate via RCON")
            return ["alert_unresponsive"]

        if incident.get("gc_pressure") or incident["type"] == "memory_pressure":
            killed = self.toolkit.kill_items()
            actions_taken.append(f"killed {killed} item entities")
            self._log_event("remediate", f"killed {killed} items (GC pressure)")

            killed_pigs = self.toolkit.kill_entities("pig")
            if killed_pigs > 100:
                actions_taken.append(f"killed {killed_pigs} pig entities")
                self._log_event("remediate", f"killed {killed_pigs} pigs (excess)")

        elif incident["type"] in ("severe_lag", "degraded_performance"):
            killed = self.toolkit.kill_items()
            actions_taken.append(f"killed {killed} item entities")
            self._log_event("remediate", f"killed {killed} items (lag)")

            if incident.get("tps", 20) < 10:
                self.toolkit.set_view_distance(4)
                actions_taken.append("reduced view distance to 4")
                self._log_event("remediate", "reduced view distance")

        self.toolkit.save_world()
        actions_taken.append("triggered world save")

        return actions_taken

    def run_loop(self, duration=120, interval=5, on_incident=None):
        """Run the monitoring loop for a fixed duration.

        Returns a summary of what happened.
        """
        start = time.time()
        incidents_detected = 0
        actions_total = []

        while time.time() - start < duration:
            metrics, gc_events = self.observe()
            incident = self.monitor.detect_incident(metrics, gc_events)

            if incident:
                incidents_detected += 1
                self._log_event("incident_detected", incident)
                if on_incident:
                    on_incident(incident)
                actions = self.respond(incident)
                actions_total.extend(actions)
                time.sleep(interval * 2)
            else:
                time.sleep(interval)

        return {
            "duration_s": time.time() - start,
            "samples": len(self.metrics_history),
            "incidents_detected": incidents_detected,
            "actions_taken": actions_total,
            "final_tps": self.metrics_history[-1].tps_1m if self.metrics_history else None,
            "event_log": self.event_log,
        }
