# Minecraft SRE

Treat a Minecraft server like production infrastructure. An AI agent monitors JVM metrics, detects incidents, and takes remediation actions. Graded with world diffs so destructive fixes (nuke the world, wipe chunks) can't score.

## Run

```
./run.sh              # full scenario: server + bots + incident + agent + grading
./run.sh --no-bots    # skip mineflayer bots (faster startup, no Node required)
./run.sh --test       # unit tests only, no server needed
```

One command. Downloads the Paper MC server jar on first run (~40MB), then runs the full SRE scenario offline.

## What happens

1. Starts a Minecraft server with intentionally conservative JVM flags (small heap, Serial GC)
2. Places known structures via RCON (a stone platform and tower; these are the "user builds")
3. Takes a world snapshot (region file hashes + block coordinates)
4. Optionally connects mineflayer bots that wander around generating load
5. Injects an entity flood (2000 items + pigs) causing GC pressure and TPS collapse
6. Runs the SRE agent for 2 minutes: monitors TPS/memory/GC, detects the incident, remediates
7. Takes a post-incident snapshot and grades the agent by comparing world state

## Grading (0 to 100)

| Dimension (25 pts each) | What it measures |
|---|---|
| Uptime | Fraction of time server responded to RCON pings |
| TPS recovery | How quickly TPS returned above 18 after the incident |
| World integrity | Region file hashes match pre-incident snapshot |
| Build preservation | Known blocks at specific coordinates are still present |

A destructive fix (delete world, reset chunks, clear all entities including builds) zeroes world integrity and build preservation, capping the score at 50 even if TPS recovers instantly. The agent has to fix the problem without breaking anything.

## The v0 incident: entity flood

Conservative JVM flags (512MB heap, Serial GC) + 2000 spawned entities = GC pressure, long stop-the-world pauses, TPS drops below 5. The correct response: kill excess entities, leave player builds alone, optionally tune server parameters. The wrong response: restart the server with `--forceUpgrade`, delete the world folder, or kill all entities indiscriminately.

## Layout

```
server/
  rcon.py          RCON protocol client
  setup.py         Paper MC download + config
  start.py         JVM process lifecycle
bots/
  wanderer.js      mineflayer load-generation bots
incidents/
  entity_flood.py  entity flood injection via RCON
agent/
  monitor.py       TPS, memory, GC log metrics
  toolkit.py       available SRE remediation actions
  sre.py           detect-and-respond control loop
grading/
  snapshot.py      world state capture (region hashes + block reads)
  diff.py          compare two snapshots
  grade.py         score computation (the 4-dimension rubric)
scenario.py        end-to-end scenario orchestrator
tests/             unit tests (no server required)
```

## Prerequisites

- Java 17+ (for Paper MC 1.20.4)
- Python 3.10+
- Node.js 18+ (optional, for bots; use `--no-bots` without it)

## What is real vs. mocked

| Component | Status |
|---|---|
| Minecraft server (Paper MC 1.20.4) | REAL |
| JVM metrics (GC logs, heap, TPS) | REAL |
| RCON protocol | REAL |
| Entity flood incident | REAL (entities exist in the world) |
| SRE agent detection + remediation | REAL (rule-based v0; LLM agent in v1) |
| World-diff grading | REAL (SHA-256 region file comparison + coordinate block checks) |
| Bot load generation | REAL (mineflayer clients connecting to the server) |

## Limits

- v0 agent is rule-based, not LLM-driven. The toolkit and grading framework are the point; the agent intelligence comes in v1.
- One incident type (entity flood). GC tuning incidents, disk pressure, network partitions in later versions.
- Grading uses region file hashes for integrity, not deep block-level analysis. A region file that changed because the server saved entity removals scores as "changed" even though the builds are intact. Build preservation (coordinate checks) catches this, but the two scores can disagree.
