# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

---

## Project Overview

**Cradler** is an AI-powered web scraping SaaS that automatically generates, deploys, and maintains custom scrapers through agentic workflows.

**Core Value:**
- Zero-code scraper creation via AI agents
- Self-maintaining scrapers with automatic repair
- E-commerce data extraction focus
- Enterprise-ready infrastructure

---

## Technology Stack

### Backend (Python)
- **Framework:** FastAPI + asyncio/uvicorn
- **Language:** Python 3.11+
- **Agent Orchestration:** Custom implementation (no framework)
- **LLM Provider:** OpenRouter (follows OpenAI API patterns)
- **Scraping Engine:** Botasaurus (built on Selenium)
- **Parsing:** BeautifulSoup4 / lxml
- **Job Queue:** Temporal
- **Database:** PostgreSQL 15+ with pgvector
- **Cache:** Redis
- **Storage:** MinIO (S3-compatible, local dev)
- **Monitoring:** Sentry

### Frontend (JavaScript)
- **Framework:** Vue 3 + Composition API
- **UI Library:** Vuetify 3
- **State Management:** Pinia
- **Router:** Vue Router 4
- **HTTP Client:** Axios

---

## System Architecture

Four main agent services:

1. **Primary Agent** - User chat interaction, requirements gathering
2. **Secondary Agent** - Website analysis, code generation
3. **Scraper Executor** - Scheduled and on-demand execution
4. **Maintenance Agent** - Change detection, auto-repair

Shared data layer: PostgreSQL + pgvector + Redis + S3

---

## Agent System Design

### Primary Agent
- Parses user intent from natural language
- Validates target URL, checks robots.txt
- Generates structured requirements
- Creates specification documents

### Secondary Agent
- Analyzes HTML structure and network requests
- Detects anti-bot measures
- Generates Botasaurus code with anti-detection
- Implements error handling
- Creates and validates tests

### Maintenance Agent
- Monitors via SHA-256 hash comparison
- Categorizes changes (minor/major/breaking)
- Auto-deploys fixes when confidence > 90%
- Flags complex issues for review

---

## Agent Prompt Strategy

**Methodology:** ReAct (Reasoning + Acting) + Plan and Execute

**Flow:**
1. Observe current state/problem
2. Plan approach
3. Execute actions using MCP tools
4. Reflect and adjust

**No RAG initially** - may add SCRAPING.md knowledge base later

---

## MCP Tools System

**Level 3 Directory Isolation** - Agents only execute within project directory.

**10 Tools Available (Phase 1):**
1. `browser_navigate` - Navigate to URLs
2. `browser_get_page_source` - Extract HTML
3. `dom_analyze_structure` - Parse HTML patterns & anti-scraping detection
4. `dom_suggest_selectors` - Generate CSS selectors
5. `dom_detect_product_containers` - Find repeating elements
6. `dom_chunk_html` - Split HTML for analysis
7. `write_scraper_code` - Save generated code
8. `test_scraper` - Execute and validate
9. `context7_get_botasaurus_docs` - Fetch Botasaurus docs
10. `context7_get_library_docs` - Fetch any library docs

**Phase 2 (Not Implemented):**
- Network analysis tools (requires CDP integration)

**Details:** See `docs/MCP_TOOLS_GUIDE.md`

---

## Botasaurus Key Methods

**Navigation:**
- `driver.get(url)` - Navigate
- `driver.google_get(url)` - Google referrer
- `driver.page_html` - Get HTML

**Interaction:**
- `driver.click(selector)`
- `driver.type(selector, text)`
- `driver.scroll(selector)`

**Data Extraction:**
- `driver.text(selector)`
- `driver.links(selector)`
- `soupify(driver)` - BeautifulSoup integration (`from botasaurus.soupify import soupify`; `driver.bs4` does NOT exist in 4.x)

**Anti-Detection:**
- `driver.short_random_sleep()` - Human-like delays
- `driver.is_bot_detected()` - Check detection
- Auto Cloudflare bypass

**JavaScript:**
- `driver.run_js(script)` - Execute JS
- `driver.execute_file(filename)` - Run JS files

**Use `botasaurus-driver` for MCP tools (not `@browser` decorator)**

---

## Key API Endpoints

```
# Auth
POST /api/auth/register
POST /api/auth/login

# Scrapers
POST   /api/scrapers
GET    /api/scrapers
GET    /api/scrapers/{id}
PUT    /api/scrapers/{id}
POST   /api/scrapers/{id}/generate  # Trigger Secondary Agent
POST   /api/scrapers/{id}/run
GET    /api/scrapers/{id}/runs

# Chat
POST /api/chat/message
GET  /api/chat/sessions

# Data
GET /api/data/runs/{run_id}
GET /api/data/export/{run_id}
```

---

## Project Structure

```
backend/
├── api/          # FastAPI endpoints
├── agents/       # Primary, Secondary, Maintenance
├── core/         # Database, queue, storage
├── scrapers/     # Executor, templates, validators
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── views/
│   ├── stores/
│   └── services/
└── public/
```

---

## Development Priorities

**MVP Build Order:**
1. Auth + basic CRUD ✅
2. Primary Agent (chat) ✅
3. Dashboard + chat UI ✅
4. Secondary Agent (code gen) ✅
5. Scheduler + executor ❌
6. Data export (JSON/CSV) ❌
7. Iterate on agent intelligence
8. Self-healing maintenance ❌

**Current Focus:** Scraper Executor implementation

---

## Security

- Encrypt scraper code/credentials at rest
- Isolate execution environments (containers)
- Rate limit per user and domain
- Validate robots.txt
- Audit log all operations
- Directory isolation: `scrapers/{user_id}/{scraper_id}/`

---

## Data Output (E-commerce)

**Fields:**
- Product title, SKU, ID
- Pricing (current, original, discount)
- Images (URLs, alt text)
- Description
- Reviews (rating, count, text)
- Availability/stock
- Variants (size, color)

**Formats:** JSON, CSV, Webhooks (future), DB write (future)

---

## Billing Model

**Free Tier:**
- 3 scrapers
- Daily runs
- 100 records/run

**Pro Tier:**
- $1.40/compute hour
- Unlimited scrapers
- Scheduled + on-demand
- Auto-maintenance

---

## MVP Scope

**Phase 1 (Current):**
- User auth ✅
- Chat scraper creation ✅
- Generic HTML scraping ✅
- Basic scheduling (daily) ❌
- JSON/CSV export ❌
- Dashboard ✅
- Free tier ✅

**Deferred:**
- Platform templates
- Proxy integration
- RAG/vector search
- Advanced scheduling
- Webhooks

---

## Development Environment

**Local Setup:**
- Docker Compose for all services
- MinIO for S3 (no remote S3)
- PostgreSQL + pgvector locally
- Redis locally
- Temporal locally

**Cloud Target:** GCP

**Testing:** Iterate on coverage (not comprehensive upfront)

---

## Data Storage

**Scraped Data:**
- S3/MinIO only (not PostgreSQL)
- JSON/CSV files with URLs in `scraping_runs.output_url`
- 120-day retention
- Auto cleanup

**Database:**
- Metadata only (users, scrapers, runs)
- Redis for queue/cache
- No vector search in MVP

---

## Performance Targets

- API response: <200ms (p95)
- Scraper creation: <2 min
- Concurrent scrapers: 10k-100k
- Data accuracy: >95%
- Uptime: 99.9%
- Auto-maintenance success: >70%
- Scraper lifespan: >30 days

---

## Key Documentation Files

These files contain detailed implementation information:

- `docs/PRD.md` - Product requirements, tech stack details
- `docs/IMPLEMENTATION_STATUS.md` - Component completion tracking, known issues
- `docs/TESTING_GUIDE.md` - Testing Secondary Agent via API
- `docs/DATABASE_SCHEMA.md` - Database schemas and models
- `docs/MCP_TOOLS_GUIDE.md` - MCP tools implementation examples
- `docs/IMPLEMENTATION_DETAILS.md` - Gotchas, API corrections, optimizations

---

## Current Project Status

Component-level status is tracked in a single, code-accurate place rather than
duplicated here (which previously caused drift). See:

- **`docs/IMPLEMENTATION_STATUS.md`** — what is built vs. partial vs. planned.
- **`docs/KNOWN_ISSUES.md`** — notable problems solved and their fixes (DeepSeek
  tool-call parsing, Context7 transport quirks, bcrypt warning, etc.).

**One-line summary:** the core MVP loop works end to end — chat → generate → test →
execute → store. The Scraper Executor *is* implemented; Temporal scheduling, the
Maintenance Agent, and the data-export/admin APIs are not yet wired.

---

## Testing

**Via Frontend:**
1. Navigate to `http://localhost:3000`
2. Login
3. Go to Chat → "I want to scrape https://books.toscrape.com"
4. Follow prompts
5. Go to Scrapers → Click scraper → **Click "Generate Code"**
6. View code and reasoning logs in tabs

**Via API:**
See `docs/TESTING_GUIDE.md` for curl examples

---

## Important Implementation Notes

### JSONB Field Updates
```python
from sqlalchemy.orm.attributes import flag_modified
session.messages = messages
flag_modified(session, "messages")  # CRITICAL
await db.commit()
```

### Foreign Key Order
```python
# Commit scraper FIRST
await db.commit()
await db.refresh(new_scraper)
# THEN link to session
session.scraper_id = new_scraper.id
```

### Botasaurus for MCP Tools
```python
# Use Driver class (not @browser decorator)
from botasaurus_driver import Driver
driver = Driver(headless=True, user_agent="string")
```

### Axios Timeout
```javascript
// frontend/src/services/api.js
timeout: 120000, // 2 minutes for agents
```

---

**For detailed implementation specifics, database schemas, MCP tool examples, and troubleshooting, refer to the documentation files listed above.**
