#!/usr/bin/env bash
# One-time (or occasional) auth for the claude sidecar container.
#
# Auth is persisted in the `claude_config` named volume, mounted at
# /home/node/.claude inside the container - so you only need to do this
# once per volume, not once per container restart.
#
# Two ways to authenticate with a Max subscription (no API key involved):
#   1. Interactive /login  - opens a URL you visit on the host, paste the
#      code back into the container. Works every time, no setup.
#   2. Token-based         - run `claude setup-token` once to mint a
#      long-lived OAuth token, then paste it into .env as
#      CLAUDE_CODE_OAUTH_TOKEN so future containers need no interactive step.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Building claude image (if needed)..."
docker-compose --profile claude build claude

echo
echo "Starting an interactive Claude Code session in the container."
echo "  - For interactive login: once the REPL starts, run  /login"
echo "  - For a reusable token instead: exit this and run"
echo "      docker-compose --profile claude run --rm claude claude setup-token"
echo "    then copy the printed token into .env as CLAUDE_CODE_OAUTH_TOKEN."
echo

docker-compose --profile claude run --rm claude claude
