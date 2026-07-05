# Claude Code in Docker

A sandboxed way to run Claude Code (including unattended/YOLO mode) against
this repo without touching anything else on your machine.

## What this is

A new `claude` service in the root `docker-compose.yml`, built from
`infrastructure/docker/Dockerfile.claude`. It:

- Bind-mounts **only this repo** to `/workspace` — edits made inside the
  container appear on your host immediately, and vice versa.
- Persists Claude's login/config in a **named Docker volume**
  (`claude_config` → `/home/node/.claude`), so you don't log in every run.
- Runs as the image's built-in **non-root `node` user**.
- Uses your **Max subscription** (OAuth), not an API key —
  `ANTHROPIC_API_KEY` is never set anywhere in this setup.
- Does **not** mount `/var/run/docker.sock`, `~/.ssh`, cloud credential
  directories, or your home directory. It cannot control sibling containers
  or the host Docker daemon, and has no SSH/cloud credentials to exfiltrate
  even if a run went wrong.
- Is on the same Docker network as `backend`/`frontend`/`postgres`/etc
  (`cradler-network`), so it can `curl http://backend:8000/...` for testing.
  This doesn't add real exposure beyond what already exists, since those
  services are already port-mapped to your host.
- Is **profile-gated** (`profiles: ["claude"]`) — a plain `docker-compose up`
  never starts it. It only runs via the scripts below.

## Files

| File | Purpose |
|---|---|
| `infrastructure/docker/Dockerfile.claude` | Minimal `node:20-slim` image + git/ripgrep + `@anthropic-ai/claude-code` |
| `docker-compose.yml` (`claude` service + `claude_config` volume) | Wiring: bind mount, config volume, network, env |
| `.env.example` (`CLAUDE_CODE_OAUTH_TOKEN`) | Non-secret placeholder for token-based auth |
| `scripts/claude-login.sh` | First-time (or occasional) auth |
| `scripts/claude-shell.sh` | Plain bash shell in the container |
| `scripts/claude-run.sh` | Normal mode — permission prompts on |
| `scripts/claude-yolo.sh` | Unattended mode — `--dangerously-skip-permissions` |

## Logging in with your Max subscription

Two options, both avoid API keys entirely:

**1. Interactive login (simplest)**

```bash
./scripts/claude-login.sh
```

This builds the image if needed, then drops you into an interactive `claude`
session in the container. Run `/login` inside it, follow the URL on your
host browser, paste the code back. Auth is saved into the `claude_config`
volume — you won't need to do this again unless you delete that volume.

**2. Token-based login (for scripting/CI-like use)**

```bash
./scripts/claude-shell.sh
# inside the container:
claude setup-token
```

Copy the printed token into your `.env` file:

```
CLAUDE_CODE_OAUTH_TOKEN=<paste here>
```

Every future container run picks this up automatically via the
`CLAUDE_CODE_OAUTH_TOKEN` environment variable — no `/login` step needed.

## Day-to-day use

```bash
./scripts/claude-shell.sh   # bash shell — poke around, run git, check versions
./scripts/claude-run.sh     # normal Claude Code — permission prompts on (default, safe)
```

## Unattended / YOLO mode

Only after you've validated normal mode works the way you expect:

```bash
./scripts/claude-yolo.sh    # runs `claude --dangerously-skip-permissions` in the container
```

This skips Claude Code's own permission prompts, but the container boundary
still applies: no Docker socket, no SSH keys, no cloud credentials, no
access to anything outside this repo's bind mount.

## Troubleshooting

**Login "succeeds" but a fresh container says you're not logged in.**
Root cause (confirmed by testing write access directly in the built image,
not just by reading docs): Docker creates a named volume's mount point owned
by `root` when the image doesn't already have that path. Our Dockerfile
switched to the non-root `node` user without ever creating
`/home/node/.claude` first, so the mounted volume ended up owned by `root`
and `node` had no write permission to it. `/login` completes the OAuth
handshake over the network fine and prints success, but silently fails to
write credentials to disk — so every fresh container looks logged out. Fixed
in `Dockerfile.claude` by creating and `chown`-ing that directory to
`node:node` before `USER node`. (`CLAUDE_CONFIG_DIR` was an earlier, wrong
guess at the cause — left set since it's harmless, but it wasn't the fix.)
If you hit this before the fix landed, remove the stale volume so it gets
recreated with correct ownership, then log in again:
```bash
docker volume rm cradler_claude_config
docker-compose --profile claude build claude
./scripts/claude-login.sh
```

**`/login`'s pasted code is rejected, or nothing happens until you press
Enter twice.** This is a terminal/PTY issue, not a container issue — most
common when running from Git Bash (MinTTY) inside VS Code's integrated
terminal, which doesn't give Docker a real console for raw-mode input. Run
`./scripts/claude-login.sh` from a native PowerShell or cmd window instead,
or use `claude setup-token` (via `claude-shell.sh`) instead of interactive
`/login` — it's a plain prompt, not the full raw-mode chat UI, so it's less
sensitive to this.

## Security limitations of this setup (read before relying on it)

- **Bind mount = full read/write on this repo.** Inside the container,
  Claude can read, write, or delete any file under this repo, including
  `.env` (which holds real secrets like `OPENROUTER_API_KEY`,
  `JWT_SECRET_KEY`, DB passwords). The container boundary protects the rest
  of your machine, not the repo's own secrets.
- **Network access.** The container shares `cradler-network` with your other
  services, so it can reach `postgres`, `redis`, `minio`, `temporal`, and
  your `backend`/`frontend` containers by hostname, plus normal internet
  access for `npm`/`git`/the Claude API itself. If you want tighter
  isolation, remove the `networks: [default]` line from the `claude` service
  in `docker-compose.yml`.
- **No Docker socket.** Unlike the `backend` service (which mounts
  `/var/run/docker.sock` for scraper isolation), `claude` does not — it
  cannot start/stop/inspect other containers or reach the host Docker
  daemon. Don't add this without a specific reason; it's one of the more
  severe host-escape vectors available in Docker.
- **No git identity/credentials by default.** The container has git
  installed but no `~/.gitconfig` or credential helper, so commits/pushes
  from inside it won't be attributed to you and pushes to authenticated
  remotes will fail until you configure something. That's intentional —
  wiring up push credentials is a separate, explicit decision, not a default
  here.
- **YOLO mode is still code execution.** `--dangerously-skip-permissions`
  means Claude won't ask before running shell commands, editing files, etc.
  The container limits *where* that can reach, not *what* it decides to do.
  Treat it like giving a script unattended write access to this repo.

<!-- Write-access check: confirmed by Claude Code on 2026-07-03. -->

## Checklist

- [ ] `./scripts/claude-login.sh` (or `claude-shell.sh` + `claude setup-token` → `.env`)
- [ ] `./scripts/claude-run.sh` — confirm Claude starts, responds, and prompts for permission before editing/running commands
- [ ] Ask it to make a small edit, confirm the change shows up in your host editor/`git status` (proves the bind mount is live both ways)
- [ ] Once satisfied, `./scripts/claude-yolo.sh` for unattended mode
