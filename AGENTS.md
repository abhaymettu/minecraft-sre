# AGENTS.md

Notes for coding agents working on this repo.

## What this is

A benchmark. An agent is put on call for a Paper 1.20.4 Minecraft server, an incident is injected, and the episode
is graded from world files and server state. The agent's own words count only in the honesty check, which compares
each claim in its report with the audit log and the final state.

## Layout

- `mcsre/episode.py` runs one shift: fresh server from the template, residents online, seeded injection time,
  a watcher sampling every 2 s, offline grading at the end.
- `mcsre/tools.py` holds every tool an agent can call. The Claude agent reaches them through `mcp_shim.py` (stdio
  MCP) and `bridge.py` (127.0.0.1 HTTP). Baselines call `ToolHost.call` in process. Every call lands in `audit.jsonl`.
- `mcsre/incidents/<name>.py` defines one incident each: `inject`, `tick`, `fixed` (live predicate that sets time to
  fix), `final` (offline checks), `exclude` and `collateral`, plus `oracle` (reference fix).
- `mcsre/grade.py` scores collateral, honesty, timings and the composite score. `mcsre/leaderboard.py` aggregates.
- `mcsre/town.py` builds the template world once into `.cache/template` and lists what is protected.
- `mcsre/anvil.py` reads and edits region files (no server needed).
- `plugins/src/` holds five small Paper plugins compiled with javac at setup. `bots/run.js` drives the mineflayer bots.

## Commands

```sh
python3 -m mcsre setup                       # Paper jar, plugins, template town (once, about 2 min)
python3 -m unittest                           # unit tests, no server
python3 -m mcsre run --agent oracle --incident griefing --seed 0
python3 -m mcsre bench --agents noop,oracle --seeds 0 --jobs 3 --out runs/validate
python3 -m mcsre leaderboard
```

`MCSRE_SHIFT_MIN_S=60` shortens shifts for quick checks. `MCSRE_KEEP_SERVER=1` keeps the episode's server dir.
`MCSRE_RECORD=1` records world frames for `mcsre replay`.

## Rules for changes

- A new incident must pass with `oracle` and fail with `noop` before it goes in. Run both on at least one seed.
- Grade from state. Never add a check that reads the agent's transcript.
- Fix predicates must not depend on tick time or TPS: host load moves those. Use entities, blocks, files, bans.
- Keep everything on 127.0.0.1. Servers bind `server-ip=127.0.0.1`; the Docker image publishes no ports.
- No em dashes in code, comments or docs.
