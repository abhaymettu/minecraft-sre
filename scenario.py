"""Run the v0 SRE scenario end-to-end.

1. Start server with conservative JVM flags
2. Place known structures (the "user builds")
3. Take pre-incident world snapshot
4. Optionally start load bots
5. Inject entity flood incident
6. Run SRE agent monitoring + response loop
7. Take post-incident snapshot
8. Grade using world diff
"""
import json
import os
import subprocess
import sys
import time

from server.rcon import Rcon
from server.start import MinecraftServer, CONSERVATIVE_FLAGS
from incidents.entity_flood import inject_mixed
from agent.sre import SREAgent
from grading.snapshot import take_snapshot
from grading.diff import diff_snapshots
from grading.grade import grade_run, format_report

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BUILD_COORDS = [(x, -59, z) for x in range(10, 20) for z in range(10, 20)]
BUILD_BLOCK = "minecraft:stone"

TOWER_COORDS = [(15, y, 15) for y in range(-58, -48)]


def place_structures(rcon: Rcon):
    print("placing baseline structures...")
    rcon.command(f"fill 10 -59 10 19 -59 19 {BUILD_BLOCK}")
    for x, y, z in TOWER_COORDS:
        rcon.command(f"setblock {x} {y} {z} {BUILD_BLOCK}")
    time.sleep(1)
    print(f"  platform 10x10 at y=-59, tower at (15, -58 to -49, 15)")


def start_bots(count=3):
    bot_dir = os.path.join(PROJECT_ROOT, "bots")
    if not os.path.isdir(os.path.join(bot_dir, "node_modules")):
        print("installing bot dependencies...")
        subprocess.run(["npm", "install", "--silent"], cwd=bot_dir, check=True)
    print(f"starting {count} wanderer bots...")
    proc = subprocess.Popen(
        ["node", "wanderer.js", str(count)],
        cwd=bot_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


def run_scenario(
    agent_duration=120,
    bot_count=3,
    flood_items=1500,
    flood_pigs=500,
    use_bots=True,
    jvm_flags=None,
):
    flags = jvm_flags or CONSERVATIVE_FLAGS
    all_build_coords = BUILD_COORDS + TOWER_COORDS

    print("=" * 60)
    print("Minecraft SRE Scenario v0")
    print("=" * 60)

    srv = MinecraftServer(jvm_flags=flags)
    bot_proc = None

    try:
        print("\n[1/7] starting server...")
        srv.start(wait_ready=True, timeout=180)

        rcon = Rcon()
        rcon.connect()

        print("\n[2/7] placing structures...")
        place_structures(rcon)

        print("\n[3/7] taking pre-incident snapshot...")
        pre_snapshot = take_snapshot(rcon, srv.world_dir, all_build_coords)
        print(f"  {len(pre_snapshot.region_hashes)} region files hashed")
        print(f"  {len(pre_snapshot.build_blocks)} build blocks recorded")

        if use_bots:
            print("\n[4/7] starting load bots...")
            bot_proc = start_bots(bot_count)
            time.sleep(10)
        else:
            print("\n[4/7] skipping bots")

        print("\n[5/7] injecting entity flood incident...")
        flood_result = inject_mixed(rcon, items=flood_items, pigs=flood_pigs)
        print(f"  spawned {flood_result['total']} entities ({flood_result['items']} items, {flood_result['pigs']} pigs)")
        incident_time = time.time()

        print(f"\n[6/7] running SRE agent for {agent_duration}s...")
        agent = SREAgent(rcon, gc_log_path=srv.gc_log_path)
        summary = agent.run_loop(duration=agent_duration, interval=5)
        print(f"  samples collected: {summary['samples']}")
        print(f"  incidents detected: {summary['incidents_detected']}")
        print(f"  actions taken: {len(summary['actions_taken'])}")
        for action in summary["actions_taken"]:
            print(f"    - {action}")

        print("\n[7/7] grading...")
        rcon.command("save-all flush")
        time.sleep(3)
        post_snapshot = take_snapshot(rcon, srv.world_dir, all_build_coords)

        world_diff = diff_snapshots(pre_snapshot, post_snapshot)

        tps_samples = [m.tps_1m for m in agent.metrics_history]
        uptime_samples = [m.responsive for m in agent.metrics_history]
        incident_idx = 0
        for i, m in enumerate(agent.metrics_history):
            if m.timestamp >= incident_time:
                incident_idx = i
                break

        report = grade_run(world_diff, tps_samples, uptime_samples, incident_idx)

        rcon.close()

        print("\n" + "=" * 60)
        print(format_report(report))
        print("=" * 60)

        result = {
            "score": report.total,
            "grade": report.grade,
            "details": report.details,
            "agent_summary": summary,
            "flood": flood_result,
        }

        result_path = os.path.join(PROJECT_ROOT, "last-run.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nfull results written to {result_path}")

        return report

    finally:
        if bot_proc and bot_proc.poll() is None:
            bot_proc.terminate()
            bot_proc.wait(5)
        srv.stop()


if __name__ == "__main__":
    run_scenario()
