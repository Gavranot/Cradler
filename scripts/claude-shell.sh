#!/usr/bin/env bash
# Plain bash shell inside the claude container, for poking around, checking
# tool versions, or running `claude setup-token` / `git` manually.
set -euo pipefail
cd "$(dirname "$0")/.."

docker-compose --profile claude run --rm claude bash
