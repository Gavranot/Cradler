# Implementation Status

A factual map of what is actually built in the codebase versus what is planned.
Use this as the roadmap; it is kept in sync with the code, not with aspirations.

**Snapshot:** The core MVP loop works end to end — a user chats to create a
scraper, the Secondary Agent autonomously generates and tests Botasaurus code, and
the executor runs it and stores results in object storage.

---

## ✅ Implemented

### Backend infrastructure
- **Database** (`backend/core/database/`) — async SQLAlchemy + asyncpg over
  PostgreSQL with pgvector. Models: `User`, `Scraper`, `ScrapingRun`,
  `ScraperTemplate`, `ScrapingKnowledge` (1536-dim embedding + ivfflat index),
  `ChatSession`. Alembic migrations in `backend/alembic/versions/`.
- **Auth** (`backend/api/auth/`) — JWT (HS256) auth, bcrypt password hashing.
  `POST /register`, `POST /login`, `GET /me`, `POST /logout`.
- **Config & security** (`backend/core/config.py`, `core/security.py`) — Pydantic
  settings, token creation/verification, password hashing.
- **Object storage** (`backend/core/storage/minio_client.py`) — MinIO/S3 client:
  JSON upload, bucket auto-creation, presigned URL generation.

### API
- **Scrapers** (`backend/api/scrapers/`) — full CRUD plus `POST /{id}/generate`
  (runs Secondary Agent), `POST /{id}/run` (background execution), `POST /{id}/test`
  (real one-off execution, nothing persisted), `GET /{id}/runs`, `GET /{id}/runs/{run_id}`.
- **Chat** (`backend/api/chat/`) — session create/list/get/delete and
  `POST /sessions/{id}/messages` wired to the Primary Agent.

### Agents
- **Primary Agent** (`backend/agents/primary/agent.py`) — conversational
  requirements gathering on `deepseek/deepseek-v3.2-exp`. Tools: `validate_url`
  (incl. robots.txt check), `create_scraper`. Multi-turn function calling.
- **Secondary Agent** (`backend/agents/secondary/agent.py`) — autonomous
  analysis → generation → testing on `deepseek/deepseek-v3.1-terminus`, ReAct
  loop (up to 15 iterations), reasoning-token capture, tool-call tracking,
  DeepSeek tool-format parser, and a completion guard. See
  [KNOWN_ISSUES.md](./KNOWN_ISSUES.md).

### MCP tools (`backend/agents/mcp/`) — 10 tools
Browser: `browser_navigate`, `browser_get_page_source`. DOM:
`dom_analyze_structure`, `dom_suggest_selectors`, `dom_detect_product_containers`,
`dom_chunk_html`. File system: `write_scraper_code`, `test_scraper` (Level-3
directory isolation under `scrapers/{user_id}/{scraper_id}/`). Docs:
`context7_get_botasaurus_docs`, `context7_get_library_docs`. The tools manager
auto-injects session/user/scraper IDs, caches the browser session, and strips HTML
boilerplate to cut token usage. See [MCP_TOOLS_GUIDE.md](./MCP_TOOLS_GUIDE.md).

### Scraper Executor (`backend/scrapers/executor/scraper_executor.py`)
Runs a generated script as a subprocess with a configurable timeout, parses JSON
output, uploads results to MinIO (`runs/{run_id}.json`), generates a presigned URL,
and records execution metadata. Invoked by `POST /scrapers/{id}/run` as a FastAPI
background task.

### Frontend (`frontend/`) — Vue 3 + Vuetify 3 SPA
Auth (login/register), chat-driven scraper creation, scraper list, and a detail
view with generate/run/delete actions, 5-second status polling during generation,
a syntax-highlighted `CodeViewer`, and a `ReasoningLogViewer`. Pinia stores and an
Axios service layer (120s timeout, JWT interceptor, 401→login redirect).

---

## 🟡 Partial

- **Primary Agent** — works for the create-scraper flow; advanced intent
  classification and strict robots.txt enforcement are basic.
- **Dashboard view** — placeholder; the functional surfaces are Chat, Scrapers,
  and ScraperDetail.

---

## ❌ Not yet implemented

- **Temporal integration** — configured in `docker-compose`/settings, but there
  are no workers or workflows. Execution currently uses FastAPI background tasks,
  so scheduled/cron runs are not active. (`backend/core/queue/` is a stub.)
- **Maintenance Agent** (`backend/agents/maintenance/`) — stub. No change
  detection or auto-repair yet.
- **Data export API** (`backend/api/data/`) — endpoints are stubs.
- **Admin API** (`backend/api/admin/`) — endpoints are stubs.
- **Scraper templates / validators** (`backend/scrapers/templates`, `validators`)
  — stubs.
- **WebSocket real-time updates** — generation progress is polled, not streamed.

### Deferred (Phase 2)
Proxy rotation, vector search / RAG over `scraping_knowledge`, platform-specific
templates (Shopify/WooCommerce/etc.).

---

## Testing status

Validated manually: registration/login, chat-driven scraper creation, Secondary
Agent generation against `books.toscrape.com`, reasoning capture, generated-code
persistence, and execution → MinIO storage. There is no automated test suite yet;
adding unit/integration coverage for the agents and API is the main testing debt.
See [TESTING_GUIDE.md](./TESTING_GUIDE.md) for manual API/UI walkthroughs.

## Update 2026-07-05 — Reduction Pipeline integrated; full loop E2E-verified

- **Reduction Pipeline** (`backend/agents/mcp/reduction/`) — ✅ built, integrated,
  and verified end-to-end on a real site (anhoch.com: listing collapsed
  253,144 chars → 504-token fragment; agent authored from the mined selectors).
  The authoring LLM now sees ~1K-token routed fragments + cross-checked
  structured data instead of full pages (102× vs raw on the 22-page benchmark
  corpus, 0 reduction-caused failures). Design/benchmarks/trail:
  `OPTIMIZED_DESIGN.md`, `BENCHMARKS.md`, `FINDINGS.md` at repo root.
- `/generate` is now genuinely asynchronous (BackgroundTasks + status polling);
  final code is persisted to the executor contract path `scraper.py`.
- Stability fixes: websockets<14 pin (botasaurus 4.0.7), all Driver work on a
  dedicated thread, Context7 SSE parsing, DeepSeek `content:null` guard —
  details in `KNOWN_ISSUES.md` #7–#12.
- Agent models are env-configurable: `PRIMARY_AGENT_MODEL`,
  `SECONDARY_AGENT_MODEL` (+ `BENCH_LLM_*` for the benchmark suite).
- **Next planned work:** bug-fix backlog, then the spec split (generic runner +
  declarative ExtractionSpec) and Maintenance Agent v1 — see `HANDOFF.md`.

## Update 2026-07-05 (later) — bug-fix round

- `POST /scrapers/{id}/test` now really executes the scraper
  (`scraper_executor.test_scraper`: same subprocess as `/run`, but no
  ScrapingRun record / MinIO upload; returns up to `sample_size` records
  inline). Mock data removed.
- Executor subprocess calls moved off the event loop (`asyncio.to_thread`) —
  a running scrape used to block the entire API for its duration.
- Secondary Agent OpenRouter calls retry transient failures (empty messages,
  429/5xx, `choices`-less bodies): 3 attempts, linear backoff
  (`_chat_completion` in `agents/secondary/agent.py`).
- Successful generation now deletes the agent's other `*.py` drafts in
  `scrapers/{user_id}/{scraper_id}/` — only `scraper.py` is canonical.
- Benchmark ground truth: `beardbrand/detail` price relabeled
  `visible: false` (only in JSON-LD/analytics blobs). Regression suite:
  0 reduction-caused FAILs, 22/22 classifier, median 975 tokens.
