# HANDOFF — Reduction Pipeline: Bug-fix Round → Spec Split

**Audience:** the next Claude session working on Cradler. Read this first, then
`FINDINGS.md` (F1–F23, terse, append-only — append, never rewrite) and
`OPTIMIZED_DESIGN.md`. Project memory: `reduction-pipeline-project.md` in the
memory dir. The Obsidian vault (MCP) holds the codebase knowledge graph — start
at `00-Home/Home.md`; note the vault predates this project's changes (see
Backlog #1).

## 1. Where the project stands (2026-07-05)

The HTML-reduction pipeline is designed, benchmarked, integrated, and
**verified end-to-end in production**: chat → generate → test → run works on
anhoch.com (Macedonian storefront) — the listing collapsed 253,144 chars →
504-token exemplar (L2a), the agent authored its scraper from the mined
selectors, tested it, and the executor ran it.

Key numbers (static 22-page corpus, `benchmarks/`): median 107,494 → ~1,000
tokens/authoring call (102× vs raw, 22× vs old prod cleaner), **0
reduction-caused failures**, 22/22 page-type classification. Real-LLM benchmark
(deepseek-v4-pro): fragment arm 16/20 pass@1 vs 14/20 for full page at 1/22nd
context; 7/8 fragment-authored specs survived class-rename mutations.

## 2. Map of artifacts

| Path | What |
|---|---|
| `OPTIMIZED_DESIGN.md` | The design; §3 minimal (DONE), §4 ambitious (NEXT), §6 integration map, §7 open questions |
| `BENCHMARKS.md` | All measured results + LLM addendum |
| `FINDINGS.md` | F1–F23 research + debugging trail with citations |
| `prototype/pipeline/` | Reference implementation (uv, py3.12) — source of truth for pipeline code |
| `backend/agents/mcp/reduction/` | The SAME modules ported into the backend — **keep in sync with prototype/ when editing either** |
| `benchmarks/` | corpus (static), ground_truth.json, run_bench.py (regression), bench_repair.py, bench_llm.py |
| `backend/corpus_rendered/` | Botasaurus-rendered corpus (22 pages, real post-hydration DOMs) |
| `backend/scripts/fetch_corpus.py` | re-renders corpus (runs INSIDE backend container) |

## 3. Invariants and decisions — do not regress these

1. **"Heuristics may rank and compress; only the LLM may reject."** User-set
   design principle. Miner candidates that fail corroboration flow to the agent
   labeled `unconfirmed` with stats + a decide-yourself header. Never add a hard
   gate that silently withholds content from the LLM. (F21)
2. **Regression invariant:** `cd benchmarks && uv run --project ../prototype
   python run_bench.py` must report `reduction-caused FAILs: 0` after ANY
   heuristic change.
3. **L0 runs on RAW html before any cleaning**, and its values are never
   trusted without DOM cross-check. (F2, F8)
4. **Executor contract:** `scrapers/{user_id}/{scraper_id}/scraper.py`, prints
   JSON array to stdout. Generation background task persists final code there.
5. **websockets>=11,<14 pin** in backend requirements — botasaurus-driver 4.0.7
   uses the legacy `.closed` API. Unpinning breaks Chrome with a misleading
   `'NoneType' object has no attribute 'closed'`. (F19)
6. **All Botasaurus Driver work must run on the dedicated worker thread**
   (`BrowserControlTool._in_driver_thread`) — Driver uses run_until_complete,
   illegal on uvicorn's loop. New driver calls must follow the pattern. (F22)
7. Models are `.env`-configurable: `PRIMARY_AGENT_MODEL`, `SECONDARY_AGENT_MODEL`
   (compose passthrough exists), bench via `BENCH_LLM_*`. User benchmarks
   DeepSeek variants; don't hardcode model IDs anywhere new.

## 4. Environment facts (the Claude container)

- Node container: **no docker CLI, no sudo, no Chrome, no system Python**. Use
  `uv` (`~/.local/bin/uv`, py3.12 installed). `PYTHONDONTWRITEBYTECODE=1` +
  tempfile cfile for py_compile (repo dirs are root-owned → pycache writes fail).
- Compose services reachable by hostname when the stack is up: `backend:8000`
  (health: `/health`), `context7:3000`, `postgres:5432`, etc. Obsidian MCP runs
  on the HOST: `host.docker.internal:3002` (moved from 3001 — it clashed with
  Context7's published host port; `.mcp.json` updated).
- You cannot exec into containers. Backend code is volume-mounted with uvicorn
  `--reload` → Python edits apply instantly. `.env` changes need
  `docker compose up -d` (recreate; plain `restart` does NOT re-read env).
  `requirements.txt`/Dockerfile changes need `--build`. Ask the USER to run
  docker commands; to read container logs have them run:
  `docker compose logs backend --no-color > backend/backend_run.log`
- Some repo files are root-owned (created by containers) — if a Write/cp fails
  with permission denied, give the user a `docker compose exec backend ...`
  one-liner instead.
- OpenRouter key lives in `/workspace/.env`. Budget style: ask before spending;
  previous approval was $10, ~$1 used (bench_llm.py has a hard cap via
  `BENCH_BUDGET_USD`).

## 5. NEXT: bug-fix round (do these first)

0. **Commit the work.** Two days of changes are uncommitted (pipeline,
   integration, 6 bug fixes, benchmarks, docs). Propose logical chunks to the
   user before committing.
1. **Update the Obsidian vault** — notes are stale vs. reality: no note for the
   reduction layer; Secondary Agent/MCP notes describe the old cleaner; Gotcha
   notes should gain: websockets pin, driver-thread rule, Context7 SSE parsing,
   generate-is-now-async, scraper.py persistence. Also fix repo docs
   (`IMPLEMENTATION_STATUS.md` "current focus" is stale).
2. **`POST /api/scrapers/{id}/test` returns mock data** (`api/scrapers/__init__.py`
   ~:209) — wire it to the executor or remove it from the UI.
3. **OpenRouter empty-content replies** (content:null, text in `reasoning`) —
   coalescing fixed in agent.py + bench_llm.py, but consider provider pinning /
   retry in `SecondaryAgent` HTTP calls too (2 corpus pages still die on it in
   benchmarks: allbirds/listing, rothys/detail). (F18)
4. **Stale per-scraper scripts accumulate** in `scrapers/{u}/{s}/` (agent names
   files freely; only scraper.py is canonical). Consider cleanup on successful
   generation.
5. **beardbrand/detail ground truth** is a suspected mislabel (configurable-price
   product) — relabel like bombas price (`visible: false`), re-run bench. (F18)
6. **rothys listing** = known-hard: closed shadow DOM (Shoelace) + catalog
   hydration stalls in-container. Fetch-time future work (skeleton-gone wait +
   shadow-piercing serialization). Documented, not urgent. (F20)
7. Cosmetic: bcrypt `__about__` startup warning (passlib vs bcrypt 4.x, known).

## 6. THEN: the spec split (OPTIMIZED_DESIGN §4, baseline spec §2)

The output-side milestone: the LLM stops rewriting whole `scraper.py` files and
instead authors a tiny declarative `ExtractionSpec`; a generic runner executes
it. Build order (each step shippable + measurable):

1. `pipeline/spec.py` — `ExtractionSpec`/`Field` datamodel + transform registry
   (money/int/strip/abs-url...; note MKD/`ден.` prices exist — see PRICE_RE).
2. Generic `runner.py` — loads a spec, fetches via Botasaurus (driver-thread
   rule!), applies `container_css`/`record_css` from listing_meta (records =
   direct children; dedupe nested matches), emits the JSON-array stdout contract
   so the executor is untouched.
3. `validate.py` — run spec against FULL cached HTML; pydantic schema checks
   (price parses positive, title non-empty/≠site-name, listing count in band,
   ≥60% cards yield price — the checks in `benchmarks/run_bench.py` are the
   template); confidence per field; golden snapshot per site (kills the
   test-loop's live re-fetch).
4. Rewire Secondary Agent: fragment in → spec out (bench_llm.py's prompts are a
   working draft of exactly this); `custom_parser` escape hatch for procedural
   sites (sandbox/lint before exec).
5. **Maintenance Agent v1** (`backend/agents/maintenance/` is an EMPTY stub):
   scheduled re-fetch → validate spec → on failure build repair request =
   fragment + failing fields + last-good values as anchors → escalate widen →
   full → human. Auto-deploy on validation pass (PRD wants >90% confidence gate).
6. Two-tier routing + deterministic no-LLM path when L0 coverage=1.0 and
   cross-check passes (7/11 detail pages on corpus).

Evidence the design works: bench_llm.py already made deepseek author validated
spec-shaped JSON from fragments at 16/20 pass@1, and 7/8 of those specs
survived simulated site mutations. The spec split productionizes that flow.

## 7. User context & working style

- User is technical, hands-on, runs docker/frontend on Windows host (WSL2);
  container-side work is yours, host commands are theirs (give one-liners).
- They challenge design decisions and are usually right to — engage, don't
  defend. The soft-gate principle came from such a challenge.
- DeepSeek is the model family of choice (cost). Keep everything model-agnostic.
- Checkpoint discipline from the original brief (`docs/FABLE5~1.MD`): present
  plans before big builds; benchmarks/evidence for every recommendation.
