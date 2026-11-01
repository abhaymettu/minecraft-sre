"""Write paper/tables.tex (tables and headline macros) from results/runs/*/*/result.json, and paper/figures/hero.png
from docs/hero.gif. Safe to run on a partial bench: missing agents or metrics render as n/a.

    python3 paper/make_tables.py && tectonic paper/main.tex
"""
import datetime
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcsre.leaderboard import aggregate, load  # noqa: E402

RUNS = os.path.join(ROOT, "results", "runs")
BOARD = os.path.join(ROOT, "results", "leaderboard.json")
OUT = os.path.join(ROOT, "paper", "tables.tex")
GIF = os.path.join(ROOT, "docs", "hero.gif")
PNG = os.path.join(ROOT, "paper", "figures", "hero.png")

PLANNED_AGENTS = ["claude:haiku", "claude:sonnet", "claude:opus", "claude:fable", "noop", "oracle", "sledgehammer"]
PLANNED_SEEDS = 3
BASELINES = {"noop", "oracle", "sledgehammer"}
INCIDENT_ORDER = ["entity_flood", "lag_source", "griefing", "plugin_crash", "disk_fill", "bad_config",
                  "chunk_corruption", "memory_leak", "control"]
INCIDENT_SHORT = {"entity_flood": "flood", "lag_source": "lag", "griefing": "grief", "plugin_crash": "plugin",
                  "disk_fill": "disk", "bad_config": "config", "chunk_corruption": "chunk", "memory_leak": "leak",
                  "control": "ctrl"}
COLLATERAL_KINDS = [
    ("build damaged", lambda c: c.startswith("build ")),
    ("named entity gone", lambda c: c.startswith("named entity ")),
    ("innocent player banned", lambda c: c.startswith("banned innocent player")),
    ("innocent player's blocks rolled back", lambda c: c.startswith("rolled back ")),
    ("intended change reverted", lambda c: c.startswith("intended change reverted")),
    ("backups modified or deleted", lambda c: c.startswith("backups ")),
    ("audit or block log truncated", lambda c: c.startswith("data file ")),
    ("plugin removed or disabled", lambda c: c.startswith("plugin ")),
]
NA = "n/a"


def tex(s):
    return str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def agent_tex(a):
    return r"\texttt{" + tex(a) + "}"


def pct(x):
    return NA if x is None else f"{100 * x:.0f}\\%"


def secs(x):
    return NA if x is None else f"{x:.0f}\\,s"


def kind(item):
    for label, match in COLLATERAL_KINDS:
        if match(item):
            return label
    return "other"


def main_table(table):
    lines = [r"\resizebox{\textwidth}{!}{%", r"\begin{tabular}{lrrrrrrrrr}", r"\toprule",
             r"Agent & Score & Resolved (95\% CI) & Detected & TTD & TTF & Collateral & Honesty & Diagnosis & "
             r"False alarms \\", r"\midrule"]
    for t in table:
        lo, hi = t["resolve_ci95"]
        hon = NA if t["honesty"] is None else f"{t['honesty']:.2f}"
        if t["no_report"]:
            hon += f"$^{{{t['no_report']}}}$"
        fa = f"{t['false_alarms']}/{t['controls']}" if t["controls"] else NA
        lines.append(f"{agent_tex(t['agent'])} & {t['score']:.1f} & {t['resolved']}/{t['episodes']} "
                     f"({pct(lo)}--{pct(hi)}) & {pct(t['detected_rate'])} & {secs(t['median_ttd_s'])} & "
                     f"{secs(t['median_ttf_s'])} & {pct(t['collateral_rate'])} & {hon} & "
                     f"{pct(t['diagnosis_rate'])} & {fa} \\\\")
    return lines + [r"\bottomrule", r"\end{tabular}}"]


LEADERBOARD_CAPTION = (r"Leaderboard, sorted by mean score. Resolved is $k/n$ episodes with a Wilson 95\% interval. "
              r"Detected is the share of real-incident episodes with a \texttt{declare\_incident} after injection. "
              r"TTD and TTF are medians over real-incident episodes where they are defined. Collateral is the share "
              r"of episodes with at least one collateral item. Honesty is the mean over episodes with a report; a "
              r"superscript counts episodes with no report. Diagnosis is the share of all episodes with the right "
              r"category. False alarms are pages on control episodes.")


def matrix_table(table, incidents, matrix):
    cols = [i for i in INCIDENT_ORDER if i in incidents] + sorted(set(incidents) - set(INCIDENT_ORDER))
    lines = [r"\begin{tabular}{l" + "r" * len(cols) + "}",
             r"\toprule", "Agent & " + " & ".join(INCIDENT_SHORT.get(i, tex(i)) for i in cols) + r" \\",
             r"\midrule"]
    for t in table:
        m = matrix[t["agent"]]
        cells = [f"{m[i][0]}/{m[i][1]}" if m.get(i, [0, 0])[1] else "--" for i in cols]
        lines.append(agent_tex(t["agent"]) + " & " + " & ".join(cells) + r" \\")
    legend = ", ".join(f"{INCIDENT_SHORT.get(i, i)} = \\texttt{{{tex(i)}}}" for i in cols)
    return lines + [r"\bottomrule", r"\end{tabular}"], legend


def collateral_table(table, rows):
    agents = [t["agent"] for t in table]
    counts = {a: {} for a in agents}
    for r in rows:
        for c in r["collateral"]:
            k = kind(c)
            counts[r["agent"]][k] = counts[r["agent"]].get(k, 0) + 1
    labels = [label for label, _ in COLLATERAL_KINDS] + (["other"] if any("other" in c for c in counts.values()) else [])
    short = [a.split(":", 1)[-1] for a in agents]
    lines = [r"\begin{tabular}{l" + "r" * len(agents) + "}", r"\toprule",
             "Collateral item & " + " & ".join(r"\texttt{" + tex(s) + "}" for s in short) + r" \\", r"\midrule"]
    for label in labels:
        lines.append(tex(label) + " & " + " & ".join(str(counts[a].get(label, 0)) for a in agents) + r" \\")
    lines += [r"\midrule", "Total items & " + " & ".join(str(sum(counts[a].values())) for a in agents) + r" \\",
              "Episodes & " + " & ".join(str(t["episodes"]) for t in table) + r" \\",
              r"\bottomrule", r"\end{tabular}"]
    return lines, counts


def macros(rows, table, incidents, matrix, counts):
    by = {t["agent"]: t for t in table}
    m = {}

    def frac(rs, pred=lambda r: r["resolved"]):
        return f"{sum(bool(pred(r)) for r in rs)}/{len(rs)}" if rs else NA

    def rows_of(agent, real=None):
        return [r for r in rows if r["agent"] == agent
                and (real is None or (r["category"] != "none") == real)]

    m["tablesgenerated"] = datetime.date.today().isoformat()
    m["nepisodes"] = str(len(rows))
    m["nexpected"] = str(len(PLANNED_AGENTS) * len(INCIDENT_ORDER) * PLANNED_SEEDS)
    m["nagentsseen"] = str(len(table))
    m["seedsseen"] = ", ".join(str(s) for s in sorted({r["seed"] for r in rows})) or NA
    models = [t for t in table if t["agent"] not in BASELINES]
    m["nmodelepisodes"] = str(sum(t["episodes"] for t in models))
    best = [agent_tex(t["agent"]) for t in models if round(t["score"], 1) == round(models[0]["score"], 1)]
    m["bestagent"] = (", ".join(best[:-1]) + " and " + best[-1] if len(best) > 1 else best[0]) if models else NA
    m["bestscore"] = f"{models[0]['score']:.1f}" if models else NA
    m["worstagent"] = agent_tex(models[-1]["agent"]) if models else NA
    m["worstscore"] = f"{models[-1]['score']:.1f}" if models else NA
    hons = [t["honesty"] for t in models if t["honesty"] is not None]
    m["honestymin"] = f"{min(hons):.2f}" if hons else NA
    m["honestymax"] = f"{max(hons):.2f}" if hons else NA
    m["noreport"] = str(sum(t["no_report"] for t in models))
    m["modelfalsealarms"] = (f"{sum(t['false_alarms'] for t in models)}/{sum(t['controls'] for t in models)}"
                             if models else NA)
    model_rows = [r for r in rows if r["agent"] not in BASELINES]
    m["modelresolved"] = frac(model_rows)
    m["modelcollateralrate"] = pct(sum(bool(r["collateral"]) for r in model_rows) / len(model_rows)) if model_rows else NA
    m["modelresolvedwithcollateral"] = frac([r for r in model_rows if r["resolved"]], lambda r: r["collateral"])

    for agent, key in (("noop", "noop"), ("oracle", "oracle"), ("sledgehammer", "sledge")):
        t = by.get(agent)
        m[key + "resolved"] = frac(rows_of(agent))
        m[key + "resolvedreal"] = frac(rows_of(agent, real=True))
        m[key + "resolvedcontrol"] = frac(rows_of(agent, real=False))
        m[key + "score"] = f"{t['score']:.1f}" if t else NA
        m[key + "collateralrate"] = pct(t["collateral_rate"]) if t else NA
        m[key + "collateralitems"] = str(t["collateral_items"]) if t else NA
        m[key + "honesty"] = f"{t['honesty']:.2f}" if t and t["honesty"] is not None else NA
        full = [i for i in incidents if matrix.get(agent, {}).get(i, [0, 0])[1]
                and matrix[agent][i][0] == matrix[agent][i][1]]
        seen = [i for i in incidents if matrix.get(agent, {}).get(i, [0, 0])[1]]
        m[key + "incidentsall"] = f"{len(full)} of {len(seen)}" if seen else NA
    noop_real = rows_of("noop", real=True)
    m["noopscorereal"] = f"{statistics.mean(r['score'] for r in noop_real):.1f}" if noop_real else NA
    sledge_res = [r for r in rows_of("sledgehammer") if r["resolved"]]
    m["sledgeresolvedwithcollateral"] = frac(sledge_res, lambda r: r["collateral"])

    for t in table:
        name = "score" + "".join(ch for ch in t["agent"].split(":", 1)[-1] if ch.isalpha())
        m[name] = f"{t['score']:.1f}"

    total = {}
    for c in counts.values():
        for k, v in c.items():
            total[k] = total.get(k, 0) + v
    model_total = {}
    for a, c in counts.items():
        if a not in BASELINES:
            for k, v in c.items():
                model_total[k] = model_total.get(k, 0) + v
    top = max(model_total.items(), key=lambda kv: kv[1]) if model_total else None
    m["topmodelcollateral"] = tex(top[0]) if top else NA
    m["topmodelcollateralcount"] = str(top[1]) if top else "0"
    m["modelcollateralitems"] = str(sum(model_total.values()))

    loads = [x for r in rows for x in ((r.get("host_load") or {}).get("start"), (r.get("host_load") or {}).get("end"))
             if x is not None]
    m["loadmin"] = f"{min(loads):.0f}" if loads else NA
    m["loadmax"] = f"{max(loads):.0f}" if loads else NA
    loads_start = [(r.get("host_load") or {}).get("start") for r in rows]
    loads_start = [x for x in loads_start if x is not None]
    m["loadmedian"] = f"{statistics.median(loads_start):.0f}" if loads_start else NA
    cpus = {(r.get("host_load") or {}).get("cpus") for r in rows} - {None}
    m["ncpus"] = ", ".join(str(c) for c in sorted(cpus)) or NA
    return m


def write_hero():
    from PIL import Image
    im = Image.open(GIF)
    im.seek(int(0.8 * (im.n_frames - 1)))
    os.makedirs(os.path.dirname(PNG), exist_ok=True)
    im.convert("RGB").save(PNG, optimize=True)


def main():
    rows = load(RUNS)
    table, incidents, matrix = aggregate(rows)
    if os.path.exists(BOARD):
        with open(BOARD) as f:
            n = json.load(f).get("episodes")
        if n != len(rows):
            print(f"note: results/leaderboard.json has {n} episodes, results/runs has {len(rows)}; "
                  "tables use results/runs (run `python3 -m mcsre leaderboard` to refresh the json)")
    coll, counts = collateral_table(table, rows)
    m = macros(rows, table, incidents, matrix, counts)
    out = ["% Generated by paper/make_tables.py. Do not edit by hand.", ""]
    out += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in m.items()]
    mat, legend = matrix_table(table, incidents, matrix)
    out += ["", r"\newcommand{\leaderboardcaption}{" + LEADERBOARD_CAPTION + "}",
            r"\newcommand{\matrixlegend}{" + legend + "}", ""]
    out += [r"\newcommand{\leaderboardtabular}{%"] + main_table(table) + ["}", ""]
    out += [r"\newcommand{\matrixtabular}{%"] + mat + ["}", ""]
    out += [r"\newcommand{\collateraltabular}{%"] + coll + ["}", ""]
    with open(OUT, "w") as f:
        f.write("\n".join(out) + "\n")
    write_hero()
    print(f"wrote {os.path.relpath(OUT, ROOT)} from {len(rows)} episodes ({len(table)} agents) "
          f"and {os.path.relpath(PNG, ROOT)}")


if __name__ == "__main__":
    main()
