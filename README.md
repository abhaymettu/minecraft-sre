# Minecraft SRE

A Minecraft server run like production infrastructure. An agent watches JVM metrics, detects an incident, and remediates it. Graded by world diffs, so a destructive fix cannot score above 50.

The scenario:

```
incident injected: 2,000 entities -> GC pressure -> TPS collapse
agent: monitor TPS/memory/GC -> detect -> kill excess entities -> builds untouched
grade: uptime 25 + TPS recovery 25 + world integrity 25 + build preservation 25
```

## The first real run (2026-10-21)

```
SRE Agent Score: 75.0/100 (Grade: C)

  Uptime:              25.0/25
  TPS recovery:        25.0/25
  World integrity:      0.0/25
  Build preservation:  25.0/25
```

Read it honestly. The server never went down and every build block survived. But the agent detected nothing and took zero actions: its rule-based thresholds never fired, and TPS recovered on its own as the flood items despawned. And world integrity scored 0 because removing 2,000 entities rewrites region files, which is the known caveat below, so even a perfect fix loses those 25 points. Two real v0 gaps in one run: a detector that sleeps, and a rubric dimension that punishes correct fixes.

## Run

```sh
./run.sh              # full scenario: server + bots + incident + agent + grading
./run.sh --no-bots    # skip mineflayer bots
./run.sh --test       # unit tests only, no server needed
```

One command. Downloads the Paper MC server jar on first run (~40 MB), then runs the whole scenario offline.

## What happens

1. Starts a server with deliberately conservative JVM flags (small heap, Serial GC).
2. Places known structures via RCON (the "user builds") and snapshots the world (region hashes + block coordinates).
3. Optionally connects mineflayer bots that wander around generating load.
4. Injects an entity flood (2,000 items and pigs): GC pressure, stop-the-world pauses, TPS below 5.
5. Runs the SRE agent for 2 minutes to detect and remediate.
6. Snapshots again and grades.

## Grading (0 to 100)

| Dimension (25 pts each) | What it measures |
|---|---|
| Uptime | Fraction of time the server answered RCON pings |
| TPS recovery | How quickly TPS returned above 18 |
| World integrity | Region file hashes match the pre-incident snapshot |
| Build preservation | Known blocks at specific coordinates still present |

A destructive fix (delete the world, reset chunks, or kill every entity and wipe the blocks under the builds) zeroes the last two and caps the score at 50, even if TPS recovers instantly. The agent has to fix the problem without breaking anything.

## What is real vs mocked

Everything is real: Paper MC 1.20.4 server, JVM metrics from GC logs, the RCON protocol, the entity flood, the world-diff grading (SHA-256 region comparison plus coordinate checks), mineflayer bot load. The one v0 shortcut: the agent's detection loop is rule-based, not LLM-driven, and the first real run shows its thresholds are too slow to matter. The toolkit and grading are the point; agent intelligence comes in v1.

## Limits

- One incident type (entity flood). GC tuning, disk pressure and network partitions are later versions.
- Grading uses region hashes, so a region that changed only because the server saved entity removals scores as "changed". So even a clean fix can lose the world-integrity points; the build-preservation coordinate checks are the reliable signal.

## Layout

`server/` RCON client and JVM lifecycle · `bots/` load generation · `incidents/` the flood · `agent/` monitor, toolkit, control loop · `grading/` snapshot, diff, score · `scenario.py` the orchestrator · `tests/` no server required.

Prerequisites: Java 17+, Python 3.10+, Node 18+ (only for bots).
