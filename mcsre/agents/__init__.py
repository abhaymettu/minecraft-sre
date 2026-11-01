"""Agents under test. Each has a name and run(ep, host) that returns when the shift is over."""
import time

from ..tools import REPORT_AFTER_S


def _sleep_until(ep, t):
    while time.time() < t and not ep.over:
        time.sleep(0.5)


def _report(host, **kw):
    base = {"incident_detected": False, "category": "none", "root_cause": "", "actions": "", "resolved": True,
            "players_banned": [], "files_deleted": [], "files_modified": [], "server_restarted": False,
            "residual_risk": ""}
    base.update(kw)
    host.call("submit_report", base)


class Noop:
    """Watches and reports nothing. Proves each checker fails when nobody acts."""
    name = "noop"

    def run(self, ep, host):
        _sleep_until(ep, ep.t0 + REPORT_AFTER_S + 1)
        _report(host, resolved=False)


class Oracle:
    """Knows the incident and the ground truth and applies the reference fix through the agent's own tools.
    Proves each incident is solvable within the shift."""
    name = "oracle"

    def run(self, ep, host):
        _sleep_until(ep, ep.inject_at)
        while ep.inject_done is None and not ep.over:
            time.sleep(0.5)
        inc = ep.incident
        if inc.category != "none":
            host.call("declare_incident", {"summary": f"oracle: {inc.name}"})
        inc.oracle(ep, host)
        _sleep_until(ep, ep.t0 + REPORT_AFTER_S + 1)
        audit = [line for line in open(ep.out + "/audit.jsonl")]
        from ..grade import banned
        _report(host, incident_detected=inc.category != "none", category=inc.category, root_cause=inc.name,
                actions="reference fix", resolved=True,
                players_banned=sorted(banned(ep) - ep.baseline["banned"]),
                files_deleted=sorted(ep.changes["deleted"]), files_modified=sorted(ep.changes["modified"]),
                server_restarted=bool(ep.server_cycles))
        return {"audit_lines": len(audit)}


def get(spec):
    if spec == "noop":
        return Noop()
    if spec == "oracle":
        return Oracle()
    if spec.startswith("claude:"):
        from .claude import ClaudeAgent
        return ClaudeAgent(spec.split(":", 1)[1])
    raise ValueError(f"unknown agent {spec!r} (noop, oracle, claude:<model>)")
