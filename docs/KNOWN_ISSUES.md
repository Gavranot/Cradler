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
| 6 | Long generation time with no progress feedback | ✅ Mitigated (polling) |

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
