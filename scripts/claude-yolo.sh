#!/usr/bin/env bash
# Unattended Claude Code: --dangerously-skip-permissions, container-only.
#
# This is safe-ish specifically BECAUSE of the container boundary: the
# claude service has no /var/run/docker.sock, no ~/.ssh, no cloud
# credentials, and only ever sees this repo (bind-mounted at /workspace).
# It can still read/write/delete anything in this repo and run arbitrary
# commands INSIDE the container (git, npm, curl to other services on the
# default network, etc). Do not run this outside the container, and do not
# add broader mounts to this service without re-reading
# docs/claude-docker-setup.md's security section first.
set -euo pipefail
cd "$(dirname "$0")/.."

docker-compose --profile claude run --rm claude claude --dangerously-skip-permissions
