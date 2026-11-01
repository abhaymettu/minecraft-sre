"""mcsre: setup | run | bench | leaderboard | replay"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

from .server import ROOT


def cmd_setup(args):
    from . import town
    bots = os.path.join(ROOT, "bots")
    if not os.path.isdir(os.path.join(bots, "node_modules")):
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=bots, check=True)
    town.build_template(force=args.force)
    print("template ready:", town.TEMPLATE_DIR)


def episode_dir(out, agent, incident, seed):
    return os.path.join(out, agent.replace(":", "-"), f"{incident}-s{seed}")


def cmd_run(args):
    from . import agents, town
    from .episode import Episode
    from .incidents import registry
    town.build_template()
    inc = registry()[args.incident]
    out = args.dir or episode_dir(args.out, args.agent, args.incident, args.seed)
    if os.path.exists(os.path.join(out, "result.json")) and not args.force:
        print(f"skip (done): {out}")
        return
    if os.path.exists(out):
        import shutil
        shutil.rmtree(out)
    res = Episode(inc, agents.get(args.agent), args.seed, args.slot, out).run()
    print(summary_line(res))


def summary_line(r):
    ttd = f"{r['time_to_detect_s']:.0f}s" if r["time_to_detect_s"] is not None else "-"
    ttf = f"{r['time_to_fix_s']:.0f}s" if r["time_to_fix_s"] is not None else "-"
    hon = f"{r['honesty']:.2f}" if r["honesty"] is not None else "no report"
    return (f"{r['agent']:<16} {r['incident']:<17} s{r['seed']}  resolved={str(r['resolved']):<5} detect={ttd:<5} "
            f"fix={ttf:<5} collateral={len(r['collateral'])} down={r['downtime_s']:.0f}s honesty={hon} score={r['score']}")


def cmd_bench(args):
    from .incidents import registry
    incidents = list(registry()) if args.incidents == "all" else args.incidents.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    jobs = [(a, i, s) for s in seeds for a in args.agents.split(",") for i in incidents]
    todo = [j for j in jobs if not os.path.exists(os.path.join(episode_dir(args.out, *j), "result.json"))]
    print(f"{len(jobs)} episodes, {len(jobs) - len(todo)} already done, {len(todo)} to run with {args.jobs} workers")
    q = queue.Queue()
    for j in todo:
        q.put(j)
    lock = threading.Lock()

    def worker(slot):
        while True:
            try:
                agent, inc, seed = q.get_nowait()
            except queue.Empty:
                return
            d = episode_dir(args.out, agent, inc, seed)
            os.makedirs(d, exist_ok=True)
            t = time.time()
            with open(d + ".harness.log", "w") as log:
                rc = subprocess.run([sys.executable, "-m", "mcsre", "run", "--agent", agent, "--incident", inc,
                                     "--seed", str(seed), "--slot", str(slot), "--dir", d, "--force"],
                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
            with lock:
                rp = os.path.join(d, "result.json")
                if rc == 0 and os.path.exists(rp):
                    print(summary_line(json.load(open(rp))), f"({time.time() - t:.0f}s)", flush=True)
                else:
                    print(f"FAILED {agent} {inc} s{seed} rc={rc}, see {d}.harness.log", flush=True)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(args.jobs)]
    for th in threads:
        th.start()
        time.sleep(5)
    for th in threads:
        th.join()


def cmd_demo(args):
    from . import town
    town.build_template()
    os.environ["MCSRE_SHIFT_MIN_S"] = "60"
    out = os.path.join(ROOT, "runs", "demo")
    print(f"demo: incident {args.incident}, a do-nothing agent and the reference fix, side by side (about 2 minutes)")
    cmd_bench(argparse.Namespace(agents="noop,oracle", incidents=args.incident, seeds="0", jobs=2, out=out))
    print(f"\nper-episode audit logs, timelines and grades: {out}")


def cmd_leaderboard(args):
    from .leaderboard import write
    print(write(args.out, args.md))


def cmd_replay(args):
    from .replay import render
    print(render(args.episode, args.gif))


def main(argv=None):
    p = argparse.ArgumentParser(prog="mcsre")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="download Paper, build plugins and the template town")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_setup)
    r = sub.add_parser("run", help="run one episode")
    r.add_argument("--agent", default="oracle")
    r.add_argument("--incident", default="entity_flood")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--slot", type=int, default=0)
    r.add_argument("--out", default=os.path.join(ROOT, "runs"))
    r.add_argument("--dir")
    r.add_argument("--force", action="store_true")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("bench", help="run agents x incidents x seeds (resumable)")
    b.add_argument("--agents", default="noop,oracle")
    b.add_argument("--incidents", default="all")
    b.add_argument("--seeds", default="0,1,2")
    b.add_argument("--jobs", type=int, default=3)
    b.add_argument("--out", default=os.path.join(ROOT, "results", "runs"))
    b.set_defaults(fn=cmd_bench)
    d = sub.add_parser("demo", help="quick start: noop vs oracle on one incident")
    d.add_argument("--incident", default="chunk_corruption")
    d.set_defaults(fn=cmd_demo)
    lb = sub.add_parser("leaderboard", help="aggregate result.json files into a table")
    lb.add_argument("--out", default=os.path.join(ROOT, "results", "runs"))
    lb.add_argument("--md", default=os.path.join(ROOT, "results", "LEADERBOARD.md"))
    lb.set_defaults(fn=cmd_leaderboard)
    rp = sub.add_parser("replay", help="render an episode to a GIF")
    rp.add_argument("episode")
    rp.add_argument("--gif", default=None)
    rp.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
