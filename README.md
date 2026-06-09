<div align="center">

# 🕷️ Cradler

**An AI agent platform that writes, runs, and maintains web scrapers from a chat message.**

Describe what you want in plain English. Cradler's agents analyze the target site,
generate production Botasaurus code, test it, and run it — no scraper code written
by hand.

![Status](https://img.shields.io/badge/status-work_in_progress-yellow)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/vue-3-4FC08D?logo=vuedotjs&logoColor=white)

[Architecture](#architecture) · [How it works](#how-it-works) · [Quick start](#quick-start) · [Documentation](#documentation)

</div>

---

> **Project status:** Active portfolio / MVP. The core loop — *chat → generate →
> test → execute → store* — works end to end. Some surrounding features
> (scheduled runs, self-healing, data export) are scaffolded but not yet complete.
> See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for an
> honest, code-accurate breakdown.

## What it does

Traditional scraping means writing and babysitting brittle, site-specific code.
Cradler replaces that with autonomous agents:

- 🤖 **Zero-code creation** — describe the data you want in a chat; agents handle the rest.
- 🧠 **Autonomous code generation** — a ReAct agent analyzes the DOM, picks selectors, writes [Botasaurus](https://github.com/omkarcloud/botasaurus) code, and tests it before saving.
- 📚 **Always-current APIs** — agents fetch live library docs via [Context7](https://github.com/upstash/context7) so they don't hallucinate non-existent methods.
- 🛡️ **Anti-bot evasion** — Botasaurus provides automatic Cloudflare bypass and human-like behavior.
- 🔒 **Isolated execution** — each scraper runs in its own sandboxed directory (`scrapers/{user_id}/{scraper_id}/`).
- 📊 **E-commerce focus** — tuned for products, prices, images, reviews, and stock.

## Architecture

Cradler is a multi-agent system over a shared data layer.

```
                          ┌──────────────────────────┐
                          │   Vue 3 + Vuetify SPA     │
                          │  (chat · scrapers · code) │
                          └────────────┬─────────────┘
                                       │ REST (JWT)
                          ┌────────────▼─────────────┐
                          │      FastAPI backend      │
                          │  auth · scrapers · chat   │
                          └──┬──────────┬─────────┬───┘
                  ┌──────────▼──┐  ┌────▼─────┐  ┌▼──────────────┐
                  │ Primary     │  │ Secondary│  │ Scraper       │
                  │ Agent       │  │ Agent    │  │ Executor      │
                  │ (chat /     │  │ (code    │  │ (subprocess + │
                  │ intent)     │  │  gen)    │  │  result store)│
                  └──────┬──────┘  └────┬─────┘  └──────┬────────┘
                         │              │ MCP tools     │
                         │      ┌───────▼────────┐      │
                         │      │ Browser · DOM  │      │
                         │      │ FileSystem ·   │      │
                         │      │ Context7 docs  │      │
                         │      └────────────────┘      │
        ┌────────────────▼──────────────────────────────▼─────────────────┐
        │  PostgreSQL + pgvector   ·   Redis   ·   MinIO (S3)   ·   Temporal │
        └──────────────────────────────────────────────────────────────────┘
```

### The agents

| Agent | Model | Responsibility |
|-------|-------|----------------|
| **Primary** | `deepseek/deepseek-v3.2-exp` | Conversational requirements gathering; validates the URL + robots.txt and creates the scraper record. |
| **Secondary** | `deepseek/deepseek-v3.1-terminus` | Autonomously analyzes the site, generates Botasaurus code, and tests it — a ReAct loop (up to 15 iterations) driven by MCP tools. |
| **Maintenance** | — | *(Planned)* Detects page changes via hashing and auto-repairs broken scrapers. |

LLMs are accessed through **OpenRouter** (OpenAI-compatible API). The agent
orchestration is a custom implementation — no agent framework.

### MCP tools (10)

The Secondary Agent acts through a custom Model-Context-Protocol tool layer:

- **Browser:** `browser_navigate`, `browser_get_page_source`
- **DOM analysis:** `dom_analyze_structure`, `dom_suggest_selectors`, `dom_detect_product_containers`, `dom_chunk_html`
- **File system:** `write_scraper_code`, `test_scraper` *(directory-isolated)*
- **Documentation:** `context7_get_botasaurus_docs`, `context7_get_library_docs`

Full reference: [`docs/MCP_TOOLS_GUIDE.md`](docs/MCP_TOOLS_GUIDE.md).

## How it works

```
User: "Scrape book titles, prices and ratings from books.toscrape.com"
                          │
   1. Primary Agent  ─────┤  validates URL + robots.txt, gathers fields,
                          │  creates a Scraper record
                          ▼
   2. Secondary Agent ────┤  Phase 0: fetch current Botasaurus docs (Context7)
                          │  Phase 1: navigate + analyze DOM, suggest selectors
                          │  Phase 2: write Botasaurus code
                          │  Phase 3: execute test run, iterate on failure
                          ▼
   3. Scraper Executor ───┤  runs the script (subprocess, timeout-bounded),
                          │  parses JSON output
                          ▼
   4. Storage ───────────┤  uploads results to MinIO, records the run + a
                          │  presigned URL in PostgreSQL
                          ▼
   5. Frontend ──────────┘  live generation progress, generated code, AI
                             reasoning log, and run history
```

## Tech stack

**Backend** — Python 3.11+ · FastAPI · async SQLAlchemy · PostgreSQL 17 + pgvector ·
Redis · MinIO (S3) · Botasaurus + BeautifulSoup · OpenRouter (DeepSeek) · Temporal
*(provisioned, not yet wired)* · Sentry *(optional)*

**Frontend** — Vue 3 (Composition API) · Vuetify 3 · Pinia · Vue Router · Vite · Axios

**Infrastructure** — Docker Compose for the full local stack; GCP as the cloud target.

## Quick start

### Prerequisites
- Docker & Docker Compose
- An [OpenRouter](https://openrouter.ai/) API key
- *(For local dev outside Docker)* Python 3.11+ and Node.js 20+

### 1. Configure environment

```bash
cp .env.example .env
```

Set at least these in `.env`:

```env
OPENROUTER_API_KEY=your_api_key_here
JWT_SECRET_KEY=change_this_to_a_long_random_string
```

### 2. Launch the stack

```bash
docker-compose up -d
```

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:3000 | Vue SPA |
| Backend API | http://localhost:8000 | FastAPI |
| API docs (Swagger) | http://localhost:8000/docs | Auto-generated |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Temporal UI | http://localhost:8233 | |
| PostgreSQL | `localhost:5433` | host port 5433 → container 5432 |

### 3. Run migrations

```bash
docker-compose exec backend alembic upgrade head
# or, from backend/ locally:  python migrate.py upgrade
```

### 4. Try it

Open http://localhost:3000, register, then go to **Chat** and say:

> *"I want to scrape https://books.toscrape.com for book titles, prices and ratings."*

Follow the prompts, open the scraper from **Scrapers**, click **Generate Code**, and
watch the agent work — generated Python and the AI's reasoning log appear in tabs.

API-only walkthrough: [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md).

## Local development

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Database migrations (Alembic)

```bash
python migrate.py upgrade            # apply all
python migrate.py downgrade          # roll back one
python migrate.py current            # show current revision
python migrate.py revision "message" # autogenerate a new migration
```

Details: [`backend/alembic/README.md`](backend/alembic/README.md).

## Project structure

```
Cradler/
├── backend/
│   ├── api/            # FastAPI routers: auth, scrapers, chat, data, admin
│   ├── agents/
│   │   ├── primary/    # chat + requirements gathering
│   │   ├── secondary/  # autonomous code generation
│   │   ├── maintenance/# (planned) self-healing
│   │   └── mcp/        # MCP tool layer: browser, dom, file_system, context7
│   ├── core/           # config, database, security, storage (MinIO), queue
│   ├── scrapers/       # executor + (planned) templates, validators
│   └── alembic/        # database migrations
├── frontend/
│   └── src/            # views, components, Pinia stores, Axios services, router
├── infrastructure/
│   └── docker/         # backend/frontend Dockerfiles, Temporal config
├── docs/               # architecture, API, schema, known issues (see below)
└── docker-compose.yml  # full local stack
```

## Documentation

| Document | What's inside |
|----------|---------------|
| [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) | Code-accurate map of what's built vs. planned |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements & vision |
| [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) | Tables, models, relationships |
| [`docs/MCP_TOOLS_GUIDE.md`](docs/MCP_TOOLS_GUIDE.md) | MCP tool implementations & examples |
| [`docs/CONTEXT7_INTEGRATION.md`](docs/CONTEXT7_INTEGRATION.md) | Live-docs integration for the agents |
| [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md) | Testing the agents via API/UI |
| [`docs/LOGGING.md`](docs/LOGGING.md) | Logging configuration & debugging workflow |
| [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) | Notable problems solved & their fixes |
| [`docs/IMPLEMENTATION_DETAILS.md`](docs/IMPLEMENTATION_DETAILS.md) | Gotchas, API corrections, optimizations |

## Configuration reference

Key environment variables (full list in [`.env.example`](.env.example)):

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | LLM access (required) |
| `JWT_SECRET_KEY` | Token signing (required) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Object storage |
| `TEMPORAL_HOST` | Temporal server (reserved for scheduled runs) |
| `MAX_SCRAPER_EXECUTION_TIME` | Per-run timeout (seconds) |
| `SENTRY_DSN` | Optional error tracking |

## Roadmap

- [ ] Temporal-backed scheduled & retried runs (currently FastAPI background tasks)
- [ ] Maintenance Agent — change detection + auto-repair
- [ ] Data export API (JSON / CSV from MinIO)
- [ ] WebSocket streaming of generation progress
- [ ] Automated test suite for agents and API
- [ ] *(Phase 2)* proxy rotation, vector search / RAG, platform templates

## License

Released under the [MIT License](LICENSE).

---

<div align="center">
<sub>Built as a portfolio project to explore autonomous, self-maintaining agent systems.</sub>
</div>
