# Known Issues & Solutions

This document collects non-obvious problems encountered while building Cradler and
the solutions that were implemented. It is the single source of truth for the
"gotchas" that previously lived in scattered root-level markdown files.

| # | Issue | Status |
|---|-------|--------|
| 1 | DeepSeek emits a non-standard tool-calling format | ✅ Solved (parser) |
| 2 | Secondary Agent completes without producing code | ✅ Solved (completion guard) |
| 3 | Agent generated non-existent Botasaurus API calls | ✅ Solved (Context7) |
| 4 | Context7 MCP transport quirks (healthcheck, headers, text responses) | ✅ Solved |
| 5 | bcrypt version warning on startup | ⚠️ Cosmetic |
| 6 | Long generation time with no progress feedback | ✅ Solved (background task + polling, see #12) |
| 7 | websockets ≥14 breaks botasaurus-driver 4.0.7 | ✅ Solved (pin <14) |
| 8 | Botasaurus Driver vs uvicorn event loop | ✅ Solved (dedicated driver thread) |
| 9 | Context7 SSE-framed MCP responses | ✅ Solved (dual-format parser) |
| 10 | DeepSeek `content: null` final messages | ✅ Solved (coalesce) |
| 11 | Script name vs executor contract | ✅ Solved (persist scraper.py) |
| 12 | `/generate` blocked despite 202 | ✅ Solved (BackgroundTasks) |
| 13 | Primary Agent sometimes replies without calling `create_scraper` | ✅ Solved (glitch retry + prompt) |

---

## 1. DeepSeek's non-standard tool-calling format

**Symptom:** The Secondary Agent would finish on iteration 1 having done no work.
The scraper was marked `active` but no code was generated.

**Root cause:** DeepSeek models on OpenRouter do **not** return the OpenAI-standard
`tool_calls` array. Instead they embed tool calls as delimited text inside the
`reasoning` field. The delimiters also differ between model versions:

```text
# DeepSeek v3.2 (ASCII delimiters)
<tool_calls_begin><tool_call_begin>browser_navigate<tool_sep>{"url": "..."}<tool_call_end><tool_calls_end>

# DeepSeek v3.1 Terminus (Unicode delimiters)
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>browser_navigate<｜tool▁sep｜>{"url": "..."}<｜tool▁call▁end｜><｜tool▁calls▁end｜>
```

The Unicode variant uses U+FF5C (full-width vertical bar `｜`) and U+2581
(lower one-eighth block `▁`).

Because the standard SDK check `if message.get("tool_calls"):` was `False`, the
agent assumed the model was done.

**Solution:** A universal parser in `backend/agents/secondary/agent.py`
(`_parse_deepseek_tool_calls`) detects either delimiter set in the `reasoning`
field, extracts the calls via regex, and rewrites them into the OpenAI-compatible
`tool_calls` shape so the rest of the agent loop works unchanged.

```python
def _parse_deepseek_tool_calls(self, reasoning_text: str) -> List[Dict[str, Any]]:
    patterns = [
        r'<｜tool▁call▁begin｜>(.*?)<｜tool▁sep｜>(.*?)<｜tool▁call▁end｜>',  # Unicode
        r'<tool_call_begin>(.*?)<tool_sep>(.*?)<tool_call_end>',            # ASCII
    ]
    matches = []
    for pattern in patterns:
        matches = re.findall(pattern, reasoning_text, re.DOTALL)
        if matches:
            break
    return [
        {
            "id": f"call_deepseek_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {"name": name.strip(), "arguments": args.strip()},
        }
        for name, args in matches
    ]
```

Detection runs only when `tool_calls` is absent but `reasoning` contains a
`...tool...begin...` marker, so it is a no-op for models that behave correctly.

**Alternatives considered (and rejected for now):** switching to
`anthropic/claude-3.5-sonnet` or `openai/gpt-4-turbo` for native function calling.
These work flawlessly but cost ~10–20× more than DeepSeek. The parser keeps the
cheaper model viable; swapping `self.model` is a one-line change if quality ever
demands it.

---

## 2. Premature completion without code

**Symptom:** Even after the parser fix, the agent could return `success=True` with
`scraper_code=None`, corrupting the DB into an `active` scraper that had no code.

**Root cause:** The loop treated "no tool calls this turn" as "done", regardless of
whether any code had actually been written.

**Solution:** A completion guard in the agent loop. Before accepting a no-tool-call
turn as final, it checks whether `scraper_code` exists:

- If code exists → genuine completion, return success.
- If not, and iterations remain → inject a user message instructing the agent to
  call `write_scraper_code` / `test_scraper`, then `continue`.
- If not, and iterations are exhausted → return `success=False` and mark the
  scraper `failed` (never a corrupt `active`-with-no-code state).

This guarantees the database only ever shows `active` for scrapers that truly have
generated, tested code.

---

## 3. Agent invented non-existent Botasaurus APIs

**Symptom:** Generated scrapers called methods like `driver.select_all()` that do
not exist in Botasaurus, so they failed at runtime.

**Root cause:** The LLM's training data did not match the installed Botasaurus
version's real API surface.

**Solution:** Context7 MCP integration. The Secondary Agent now runs a "Phase 0"
that fetches up-to-date Botasaurus (and any other library) documentation before
writing code, and is instructed to use only methods confirmed in those docs. See
[CONTEXT7_INTEGRATION.md](./CONTEXT7_INTEGRATION.md) for the full integration guide.

Tools exposed to the agent: `context7_get_botasaurus_docs`,
`context7_get_library_docs`.

---

## 4. Context7 MCP transport quirks

Getting the Python client to talk to the Context7 MCP server (run as a Node.js
container) surfaced several non-obvious issues:

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container stuck `unhealthy` | Context7 exposes no `/health` endpoint | Healthcheck uses `nc -z localhost 3000` (port probe) instead of an HTTP check |
| HTTP `406 Not Acceptable` | MCP HTTP transport requires SSE negotiation | Send `Accept: application/json, text/event-stream` |
| "Failed to parse library resolution response" | Context7 returns formatted **text**, not JSON | Parse responses with regex to extract library IDs |
| Frequent `404` on tool calls | MCP session expired | Store `Mcp-Session-Id` from init, auto-retry/re-init on 404 |
| pip dependency conflicts | `mcp==1.0.0` needs newer httpx/pydantic/fastapi | Bumped httpx→0.27.2, pydantic→2.10.5, fastapi→0.115.12 |

The MCP HTTP transport contract the client implements:

- Endpoint: `http://context7:3000/mcp`
- Protocol version: `2025-06-18` (sent as `MCP-Protocol-Version` header)
- Initialize a session first, then include `Mcp-Session-Id` on every later request.

---

## 5. bcrypt version warning

**Symptom:** On startup: `AttributeError: module 'bcrypt' has no attribute '__about__'`.

**Impact:** Cosmetic only — password hashing/verification work correctly. It is a
known incompatibility between `passlib` and newer `bcrypt` builds.

**Workaround:** Ignore, or pin `bcrypt` to a version `passlib` introspects cleanly.

---

## 6. Long generation time with no feedback

**Symptom:** Code generation takes 60+ seconds; early UI gave no progress signal.

**Mitigation:** The Axios client timeout was raised to 120s, and `ScraperDetail.vue`
polls scraper status every 5 seconds during generation, auto-switching to the
generated-code tab on completion. A WebSocket streaming upgrade remains a future
enhancement.

## 7. websockets ≥14 breaks botasaurus-driver 4.0.7 (2026-07-05)

**Symptom:** every `Driver()` launch dies with
`AttributeError: 'NoneType' object has no attribute 'closed'` — nothing in the
message mentions the real culprit.

**Root cause:** `botasaurus-driver==4.0.7` declares `websockets>=11` unbounded,
but its CDP layer uses the legacy `.closed` API removed in websockets 14. An
unpinned image build resolves 16.x; the failed property lookup falls through to
`Connection.__getattr__` on a `None` target. Chrome itself launches fine.

**Solution:** `requirements.txt` pins `websockets>=11,<14` (13.1 verified).
Needs an image rebuild when changed. `scripts/fetch_corpus.py` checks the
installed version at startup and reports "rebuild" instead of the cryptic error.

## 8. Botasaurus Driver cannot run on uvicorn's event loop (2026-07-05)

**Symptom:** `Cannot run the event loop while another loop is running` on
browser session creation, plus stray `RuntimeWarning: coroutine 'start' was
never awaited` — the browser never opens, while `test_scraper` (subprocess)
works fine.

**Root cause:** `Driver` drives Chrome via its own asyncio loop
(`run_until_complete`) — illegal on the thread already running FastAPI's loop.
The orphaned internal `start()` coroutine produces the RuntimeWarnings.

**Solution:** `BrowserControlTool` confines ALL driver work (including property
reads like `page_html`/`current_url`, which run JS internally) to a dedicated
`ThreadPoolExecutor(max_workers=1)` via `_in_driver_thread(...)`. Any new
driver call must use the same pattern.

## 9. Context7 answers SSE frames, not plain JSON (2026-07-05)

**Symptom:** `MCP initialization error: Expecting value: line 1 column 1` on
every startup, although doc fetches sometimes still worked.

**Root cause:** with the (required) `Accept: application/json, text/event-stream`
header, Context7 2.3.0 replies SSE-framed (`event: message\ndata: {...}`) at
least for `initialize`; the client parsed everything with `response.json()`.
The session ID was captured from headers *before* the parse crash, which is why
later tool calls could still succeed.

**Solution:** `_parse_mcp_response()` in `context7_client.py` handles both SSE
and plain-JSON bodies; used by `_initialize` and `_call_mcp_tool`.

## 10. DeepSeek returns `content: null` on final messages (2026-07-05)

**Symptom:** a fully successful generation (code written, tested) marked FAILED
with `ValidationError: final_message — Input should be a valid string`.

**Root cause:** DeepSeek via OpenRouter sometimes returns the assistant message
with `content: null` and the actual text in `reasoning`. `.get("content", "")`
does not guard against an explicit null.

**Solution:** coalesce `content → reasoning → ""` in `agents/secondary/agent.py`
(and transport-level retry on empty replies in `benchmarks/bench_llm.py`).

## 11. Generated script name vs executor contract (2026-07-05)

**Symptom:** `/run` failed with `Scraper script not found: .../scraper.py`
although generation succeeded.

**Root cause:** the agent names its working scripts freely
(`anhoch_scraper.py`, `*_improved.py`), but `ScraperExecutor` runs exactly
`scrapers/{user_id}/{scraper_id}/scraper.py`. Nothing bridged the two.

**Solution:** `_generate_scraper_background` persists the final
`scraper_code` to `scraper.py` on every successful generation.

## 12. `/generate` blocked despite 202 (2026-07-05 — resolved)

Issue 6's root cause is now fixed properly: generation runs in a real
`BackgroundTasks` task (same pattern as `/run`, own DB session). The endpoint
returns immediately; the existing 5s status polling drives the UI. The old
behavior (agent loop awaited inline) made the frontend time out at 2 minutes
while the backend kept working.

## 13. Primary Agent replies without calling `create_scraper` (2026-07-05)

**Symptom:** the user confirms scraper creation in chat; the agent answers
(sometimes even claims success) but the backend never receives a
`create_scraper` tool call.

**Root causes (two, compounding):**
1. Reasoning models (DeepSeek, MiniMax M3) intermittently emit the tool call
   as *text* (`<｜tool▁calls▁begin｜>`, `<minimax:tool_call>`, ...) in
   `content`/`reasoning` instead of the structured `tool_calls` array — the
   same failure class as issues #2 and #10, but `PrimaryAgent` had none of the
   Secondary Agent's defenses (no parser, no null-coalesce, no retry).
2. The prompt's example flow narrated `*create_scraper*` as text and never
   forbade claiming success without acting, so the model sometimes imitated
   the narration instead of calling the tool.

**Solution (`agents/primary/agent.py`):**
- `_chat_completion(...)`: up to 3 attempts with backoff on retryable HTTP
  status, timeouts, choices-less bodies, empty messages, and — key here —
  replies where tool-call *marker syntax* appears in text without structured
  `tool_calls` (the model decided to act; a resample usually yields the
  structured call). Falls back to the degraded text reply rather than a 500.
- Final `message` coalesces `content → reasoning → ""`.
- Prompt hardened: "actions happen ONLY through tool calls", call
  `create_scraper` in the same turn as the user's confirmation, never claim
  success without a successful tool result; examples no longer narrate
  `*create_scraper*` as prose.
