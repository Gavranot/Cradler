# Logging & Observability

Cradler uses Python's standard `logging`, configured centrally in
`backend/main.py`. Logging is most detailed around the Secondary Agent's
generation workflow, since that is the hardest part of the system to debug.

## Configuration

Log level is driven by the `LOG_LEVEL` setting (`backend/core/config.py`,
overridable via env var):

```bash
LOG_LEVEL=DEBUG   # DEBUG | INFO | WARNING | ERROR | CRITICAL  (default: INFO)
```

The format includes the source location for fast navigation:

```python
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
)
```

These modules are pinned to `DEBUG` for deep visibility:
`agents.secondary.agent`, `agents.mcp.*`, `api.scrapers`.

## What gets logged

The generation pipeline emits structured, banner-delimited sections:

- **`[GENERATION START]`** — session/user/scraper IDs, target URL, data fields.
- **`[ITERATION n/max]`** — per-turn OpenRouter request/response metadata.
- **`[REASONING TOKENS]`** — the model's captured thinking for each turn.
- **`[TOOL CALL n]`** — tool name, arguments, success/failure, result summary
  (docs chars retrieved, code chars written, test outcome, etc.).
- **`[TOOLS MANAGER]`** — every tool dispatch with its arguments (DEBUG).
- **`[GENERATION COMPLETE]` / `[GENERATION FAILED]`** — final tallies, or the
  error type, HTTP status, response body, and full traceback on failure.

The same banners appear on the API side (`[SCRAPER GENERATION ENDPOINT]`,
`[UPDATE DATABASE]`), so you can trace a request end-to-end.

## Viewing logs

```bash
# Stream backend logs
docker-compose logs -f backend

# Focus on a concern
docker-compose logs -f backend | grep "GENERATION"
docker-compose logs -f backend | grep "TOOL CALL"
docker-compose logs -f backend | grep "Context7"
docker-compose logs -f backend | grep "ERROR"
```

## Debugging a failed generation

1. **Was Context7 reached?** `grep context7` — expect a resolved library ID and
   a non-trivial doc length (tens of thousands of characters).
2. **Which tools ran?** `grep "TOOL CALL"` — a healthy run progresses through
   `context7_* → browser_navigate → browser_get_page_source → dom_* →
   write_scraper_code → test_scraper`.
3. **Any hard errors?** `grep ERROR` — look for `TOOL EXECUTION FAILED`,
   `OpenRouter API Error`, or `Cannot connect to Context7`.
4. **What was the model thinking?** `grep REASONING` — reveals whether the agent
   misread the task or picked the wrong tool.
5. **Where did it stall?** `grep ITERATION` — being stuck on iteration 1 usually
   means an OpenRouter or Context7 connectivity problem.

## Error tracking

When `SENTRY_DSN` is set, Sentry captures unhandled exceptions in the FastAPI app
(see `backend/main.py`). It is optional and disabled by default in local dev.
