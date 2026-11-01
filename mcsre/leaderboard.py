"""Aggregate result.json files into results/LEADERBOARD.md and results/leaderboard.json."""
import glob
import json
import math
import os
import statistics

from .grade import score


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def load(out):
    rows = []
    for p in sorted(glob.glob(os.path.join(out, "*", "*", "result.json"))):
        with open(p) as f:
            r = json.load(f)
        if r:
            r["score"] = score(r)
            r["_dir"] = os.path.relpath(os.path.dirname(p), out)
            rows.append(r)
    return rows


def aggregate(rows):
    by = {}
    for r in rows:
        by.setdefault(r["agent"], []).append(r)
    table = []
    for agent, rs in by.items():
        n = len(rs)
        k = sum(r["resolved"] for r in rs)
        lo, hi = wilson(k, n)
        real = [r for r in rs if r["category"] != "none"]
        ctrl = [r for r in rs if r["category"] == "none"]
        reports = [r for r in rs if r["honesty"] is not None]
        table.append({
            "agent": agent, "episodes": n, "resolved": k, "resolve_rate": k / n, "resolve_ci95": [lo, hi],
            "score": statistics.mean(r["score"] for r in rs),
            "median_ttd_s": _med(r["time_to_detect_s"] for r in real),
            "detected_rate": sum(r["time_to_detect_s"] is not None for r in real) / len(real) if real else None,
            "median_ttf_s": _med(r["time_to_fix_s"] for r in real),
            "collateral_rate": sum(bool(r["collateral"]) for r in rs) / n,
            "collateral_items": sum(len(r["collateral"]) for r in rs),
            "mean_downtime_s": statistics.mean(r["downtime_s"] for r in rs),
            "honesty": statistics.mean(r["honesty"] for r in reports) if reports else None,
            "no_report": n - len(reports),
            "diagnosis_rate": sum(r["diagnosis_correct"] for r in rs) / n,
            "false_alarms": sum(r["false_alarm"] for r in ctrl), "controls": len(ctrl),
            "cost_usd_list_price": sum((r.get("agent_info") or {}).get("cost_usd_list_price") or 0 for r in rs),
        })
    table.sort(key=lambda t: -t["score"])
    incidents = sorted({r["incident"] for r in rows})
    matrix = {a: {i: [sum(r["resolved"] for r in rs if r["incident"] == i), sum(r["incident"] == i for r in rs)]
                  for i in incidents} for a, rs in by.items()}
    return table, incidents, matrix


def _fmt_s(x):
    return "-" if x is None else f"{x:.0f} s"


def _pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def write(out, md_path):
    rows = load(out)
    table, incidents, matrix = aggregate(rows)
    lines = ["| Agent | Score | Resolved (95% CI) | Detected | Median time to detect | Median time to fix | "
             "Episodes with collateral | Downtime / ep | Report honesty | Diagnosis | False alarms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for t in table:
        lo, hi = t["resolve_ci95"]
        hon = "-" if t["honesty"] is None else f"{t['honesty']:.2f}" + (f" ({t['no_report']} no report)" if t["no_report"] else "")
        lines.append(f"| {t['agent']} | {t['score']:.1f} | {t['resolved']}/{t['episodes']} ({_pct(lo)} to {_pct(hi)}) | "
                     f"{_pct(t['detected_rate'])} | {_fmt_s(t['median_ttd_s'])} | {_fmt_s(t['median_ttf_s'])} | "
                     f"{_pct(t['collateral_rate'])} ({t['collateral_items']} items) | {t['mean_downtime_s']:.0f} s | {hon} | "
                     f"{_pct(t['diagnosis_rate'])} | {t['false_alarms']}/{t['controls']} |")
    lines += ["", "Resolved per incident (resolved/episodes):", "",
              "| Agent | " + " | ".join(incidents) + " |", "|---|" + "---:|" * len(incidents)]
    for t in table:
        m = matrix[t["agent"]]
        lines.append(f"| {t['agent']} | " + " | ".join(f"{m[i][0]}/{m[i][1]}" if m[i][1] else "-" for i in incidents) + " |")
    md = "\n".join(lines) + "\n"
    with open(md_path, "w") as f:
        f.write(md)
    with open(os.path.join(os.path.dirname(md_path), "leaderboard.json"), "w") as f:
        json.dump({"agents": table, "matrix": matrix, "episodes": len(rows)}, f, indent=1)
    return md
