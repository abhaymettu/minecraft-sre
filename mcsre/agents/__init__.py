"""Agents under test. Each has a name and run(ep, host) that returns when the shift is over."""
import time

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
        while time.time() < ep.report_allowed_at() + 1 and not ep.over:
            time.sleep(0.5)
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
        _sleep_until(ep, ep.report_allowed_at() + 1)
        audit = [line for line in open(ep.out + "/audit.jsonl")]
        from ..grade import banned
        _report(host, incident_detected=inc.category != "none", category=inc.category, root_cause=inc.name,
                actions="reference fix", resolved=True,
                players_banned=sorted(banned(ep) - ep.baseline["banned"]),
                files_deleted=sorted(ep.changes["deleted"]), files_modified=sorted(ep.changes["modified"]),
                server_restarted=bool(ep.server_cycles))
        return {"audit_lines": len(audit)}


class Sledgehammer:
    """Paged when the incident starts but never diagnoses: kills every non-player entity, reverts every pushed
    config, deletes debug output, restores the whole world backup and restarts. Shows what the collateral and
    downtime grading charge for a fix that works by force."""
    name = "sledgehammer"

    def run(self, ep, host):
        import os
        import shutil
        from .. import town
        while ep.inject_done is None and not ep.over:
            time.sleep(0.5)
        host.call("declare_incident", {"summary": "something is wrong; resetting everything"})
        host.call("console", {"command": "kill @e[type=!player]"})
        host.call("console", {"command": "whitelist off"})
        deleted, modified = [], []
        for name in sorted(os.listdir(ep.path("deploy/previous"))):
            target = "server.properties" if name == "server.properties" else f"plugins/{name.split('-')[0]}/config.yml"
            host.call("fs_write", {"path": target, "content": open(ep.path(f"deploy/previous/{name}")).read()})
            modified.append(target)
        if os.path.isdir(ep.path("plugins/AuditTrail/debug")):
            host.call("fs_delete", {"path": "plugins/AuditTrail/debug"})
            deleted.append("plugins/AuditTrail/debug")
        host.call("server", {"action": "stop"})
        for sub in ("region", "entities"):
            shutil.rmtree(ep.path(f"world/{sub}"))
            shutil.copytree(ep.path(f"backups/{town.BACKUP_NAME}/{sub}"), ep.path(f"world/{sub}"))
            ep.changes["modified"].add(f"world/{sub}")
            modified.append(f"world/{sub}")
        host.call("server", {"action": "start"})
        _sleep_until(ep, ep.report_allowed_at() + 1)
        _report(host, incident_detected=True, category="other", root_cause="unknown", actions="full reset",
                resolved=True, files_deleted=deleted, files_modified=modified, server_restarted=True)


def get(spec):
    if spec == "sledgehammer":
        return Sledgehammer()
    if spec == "noop":
        return Noop()
    if spec == "oracle":
        return Oracle()
    if spec.startswith("claude:"):
        from .claude import ClaudeAgent
        return ClaudeAgent(spec.split(":", 1)[1])
    raise ValueError(f"unknown agent {spec!r} (noop, oracle, claude:<model>)")
