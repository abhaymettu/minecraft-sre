"""Score an SRE agent's performance based on world diffs and metrics."""
from dataclasses import dataclass, field

from .diff import WorldDiff


@dataclass
class GradeReport:
    uptime_score: float = 0.0
    tps_recovery_score: float = 0.0
    world_integrity_score: float = 0.0
    build_preservation_score: float = 0.0
    total: float = 0.0
    max_total: float = 100.0
    details: dict = field(default_factory=dict)
    grade: str = "F"

    def compute_total(self):
        self.total = (
            self.uptime_score
            + self.tps_recovery_score
            + self.world_integrity_score
            + self.build_preservation_score
        )
        if self.total >= 90:
            self.grade = "A"
        elif self.total >= 80:
            self.grade = "B"
        elif self.total >= 70:
            self.grade = "C"
        elif self.total >= 60:
            self.grade = "D"
        else:
            self.grade = "F"


def grade_run(
    world_diff: WorldDiff,
    tps_samples: list[float],
    uptime_samples: list[bool],
    incident_start_idx: int = 0,
) -> GradeReport:
    report = GradeReport()

    if uptime_samples:
        responsive_count = sum(1 for x in uptime_samples if x)
        report.uptime_score = 25.0 * (responsive_count / len(uptime_samples))
        report.details["uptime_pct"] = responsive_count / len(uptime_samples)
    else:
        report.uptime_score = 0.0

    if tps_samples and incident_start_idx < len(tps_samples):
        post_incident = tps_samples[incident_start_idx:]
        recovery_idx = None
        for i, tps in enumerate(post_incident):
            if tps >= 18.0:
                recovery_idx = i
                break

        if recovery_idx is not None:
            recovery_speed = 1.0 - (recovery_idx / len(post_incident))
            report.tps_recovery_score = 25.0 * max(recovery_speed, 0.2)
            report.details["recovery_sample_idx"] = recovery_idx
        else:
            final_tps = post_incident[-1] if post_incident else 0
            if final_tps >= 15.0:
                report.tps_recovery_score = 10.0
            elif final_tps >= 10.0:
                report.tps_recovery_score = 5.0
            else:
                report.tps_recovery_score = 0.0
            report.details["final_tps"] = final_tps
    else:
        report.tps_recovery_score = 0.0

    report.world_integrity_score = 25.0 * world_diff.region_integrity
    report.details["region_integrity"] = world_diff.region_integrity
    report.details["regions_changed"] = len(world_diff.regions_changed)
    report.details["regions_removed"] = len(world_diff.regions_removed)

    report.build_preservation_score = 25.0 * world_diff.build_preservation
    report.details["build_preservation"] = world_diff.build_preservation
    report.details["blocks_destroyed"] = len(world_diff.blocks_destroyed)
    report.details["blocks_changed"] = len(world_diff.blocks_changed)

    report.compute_total()
    return report


def format_report(report: GradeReport) -> str:
    lines = [
        f"SRE Agent Score: {report.total:.1f}/100 (Grade: {report.grade})",
        "",
        f"  Uptime:             {report.uptime_score:5.1f}/25",
        f"  TPS recovery:       {report.tps_recovery_score:5.1f}/25",
        f"  World integrity:    {report.world_integrity_score:5.1f}/25",
        f"  Build preservation: {report.build_preservation_score:5.1f}/25",
        "",
    ]

    if "uptime_pct" in report.details:
        lines.append(f"  uptime: {report.details['uptime_pct']:.0%}")
    if "recovery_sample_idx" in report.details:
        lines.append(f"  TPS recovered at sample #{report.details['recovery_sample_idx']}")
    elif "final_tps" in report.details:
        lines.append(f"  TPS never fully recovered (final: {report.details['final_tps']:.1f})")
    if "regions_changed" in report.details:
        lines.append(
            f"  region files changed: {report.details['regions_changed']}, "
            f"removed: {report.details['regions_removed']}"
        )
    if "blocks_destroyed" in report.details:
        lines.append(
            f"  build blocks destroyed: {report.details['blocks_destroyed']}, "
            f"changed: {report.details['blocks_changed']}"
        )

    return "\n".join(lines)
