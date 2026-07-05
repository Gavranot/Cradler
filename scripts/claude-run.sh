#!/usr/bin/env bash
# Normal-mode Claude Code: permission prompts stay ON. This is the default,
# safe way to run the agent against this repo - use claude-yolo.sh only
# after you've validated this works as expected and you explicitly want
# unattended mode.
set -euo pipefail
cd "$(dirname "$0")/.."

docker-compose --profile claude run --rm claude claude
