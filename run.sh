#!/usr/bin/env bash
# Minecraft SRE scenario runner.
#   ./run.sh              full scenario (server + bots + incident + agent + grading)
#   ./run.sh --no-bots    skip mineflayer bots (faster, less realistic)
#   ./run.sh --test       run unit tests only (no server needed)
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--test" ]]; then
  exec python3 -m pytest tests/ -v 2>/dev/null || python3 -m unittest discover -s tests -v
fi

command -v java >/dev/null || { echo "java not found. Install JDK 17+." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found." >&2; exit 1; }

USE_BOTS=true
if [[ "${1:-}" == "--no-bots" ]]; then
  USE_BOTS=false
  shift
fi

if [[ "$USE_BOTS" == "true" ]]; then
  command -v node >/dev/null || { echo "node not found. Install Node.js for bot support, or use --no-bots." >&2; exit 1; }
  if [[ ! -d bots/node_modules ]]; then
    echo "installing bot dependencies..."
    (cd bots && npm install --silent)
  fi
fi

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

if [[ "$USE_BOTS" == "true" ]]; then
  exec python3 scenario.py
else
  exec python3 -c "
from scenario import run_scenario
run_scenario(use_bots=False)
"
fi
