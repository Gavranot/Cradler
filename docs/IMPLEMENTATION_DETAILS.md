# Implementation Details & Gotchas

**Last Updated:** 2025-01-13

This document contains implementation-specific details, API corrections, optimizations, and lessons learned during development.

---

## Botasaurus API Corrections

### Issue: Incorrect API Usage

The initial MCP tools used wrong Botasaurus API based on assumptions:

```python
# WRONG - Doesn't exist
from botasaurus import bt, AntiDetectDriver
user_agent = bt.UserAgents.user_agent_106  # ❌ bt.UserAgents doesn't exist
```

### Correct API

Use `botasaurus-driver` for programmatic control:

```python
# CORRECT
from botasaurus_driver import Driver

driver = Driver(
    headless=True,
    user_agent="custom_user_agent_string",  # Just a string, not bt.UserAgents
    proxy="http://proxy:port",
    block_images=False,
    beep=False
)

driver.get("https://example.com")
html = driver.page_html
driver.short_random_sleep()
driver.close()
```

### Botasaurus vs Botasaurus Driver

| Botasaurus | Botasaurus Driver |
|------------|-------------------|
| `@browser` decorator | `Driver` class |
| High-level framework | Low-level API |
| Auto lifecycle | Manual lifecycle |
| For scraper scripts | For tools/libraries |

**Why This Matters:** MCP tools need programmatic control with manual session management, which requires the Driver API.

---

## Tool Call State Management Optimization

### Problem
Secondary Agent had to manually track and pass `session_id`, `user_id`, `scraper_id` to every tool call, causing errors and context bloat.

### Solution
Implemented automatic state injection system.

#### GenerationSession Class
Tracks `generation_id`, `user_id`, `scraper_id` per generation:
- Auto-creates browser sessions
- Caches HTML for DOM tools
- Single source of truth for session state

#### Auto-Injected Parameters
- `session_id` → Browser, network, DOM tools
- `user_id` + `scraper_id` → File system tools

#### Implementation
```python
# Initialize at generation start
tools_manager.initialize_generation(user_id, scraper_id)

# Browser session auto-created on first navigate
# HTML auto-cached when browser_get_page_source called
# All state injected automatically in execute_tool()
```

#### Benefits
- ~30% reduction in tool call tokens
- Clearer agent reasoning
- Prevents ID mismatch errors
- Enforces prerequisite workflows

---

## SQLAlchemy JSONB Field Mutations

### Problem
SQLAlchemy doesn't detect in-place modifications to JSONB fields:

```python
session.messages = messages  # Change not detected!
await db.commit()  # Nothing persisted
```

### Solution
Use `flag_modified()` after modifying JSONB fields:

```python
from sqlalchemy.orm.attributes import flag_modified

session.messages = messages
flag_modified(session, "messages")  # Tell SQLAlchemy field changed
await db.commit()
```

**Why:** SQLAlchemy uses identity comparison. JSONB fields are mutable Python objects, so changes aren't auto-detected.

---

## Frontend Axios Timeout

### Problem
Primary Agent takes 10-30 seconds to respond, but frontend had 10-second timeout.

### Solution
```javascript
// frontend/src/services/api.js
timeout: 120000, // 2 minutes for agent responses
```

**Why:** Agent workflows involve multiple API calls, tool executions, and LLM processing.

---

## Foreign Key Constraint Violations

### Problem
Chat endpoint tried to set `session.scraper_id` before scraper was committed.

### Solution
Commit scraper **first**, then link:

```python
# Create scraper
new_scraper = Scraper(...)
db.add(new_scraper)

# CRITICAL: Commit first
await db.commit()
await db.refresh(new_scraper)

# NOW safe to link
session.scraper_id = new_scraper.id
```

**Why:** PostgreSQL enforces foreign key constraints immediately.

---

## Directory Isolation (Level 3 Security)

### Implementation
All scraper files stored in isolated directories:
```
backend/scrapers/{user_id}/{scraper_id}/
```

### Security Measures
- Path traversal prevention in `file_system.py`
- `_validate_path()` ensures resolved paths stay within allowed directory
- Script names validated: no `..`, `/`, or `\` characters

**Critical:** Prevents agents from accessing other users' scrapers or system files.

---

## JSONB Storage Pattern

### Decision
Store generated code, reasoning logs, metadata in `scrapers.scraping_config` JSONB field.

### Advantages
- Flexible schema (no migrations for new fields)
- All scraper data in one place
- Easy to query entire config
- Supports nested structures

### Trade-offs
- Can't easily index specific JSONB fields
- Larger row size (PostgreSQL handles well)

---

## Async/Await Throughout Backend

### Pattern
All database ops, HTTP calls, agent operations use asyncio.

### Benefits
- Non-blocking I/O during long operations (60+ sec generations)
- Scales to many concurrent requests
- FastAPI native async support

### Example
```python
async def generate_scraper(...) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(...)
```

---

## Tool Call Iteration Strategy

### Implementation
Secondary Agent uses loop with up to 15 iterations for multi-step reasoning.

### Pattern
1. Send request to LLM
2. LLM responds with tool calls
3. Execute each tool
4. Add tool results to conversation
5. Send updated conversation to LLM
6. Repeat until final message (no more tool calls)

### Iteration Budget
- Phase 1 (Analysis): ~5 iterations
- Phase 2 (Generation): ~5 iterations
- Phase 3 (Testing): ~5 iterations
- **Total: ~15 max**

### Timeout
120 seconds per HTTP request to OpenRouter.

---

## Scraper Status Lifecycle

### States
- `inactive` - Created but no code generated
- `generating` - Secondary Agent working
- `active` - Code generated and tested
- `failed` - Generation failed

### User Experience
Frontend polls status every 5 seconds and shows progress indicator.

---

## OpenRouter Reasoning Tokens

### Discovery
OpenRouter provides unified interface for reasoning tokens via `reasoning` parameter.

### Configuration
```python
"reasoning": {
    "enabled": True,
    "effort": "medium"  # Uses ~50% of max_tokens for reasoning
}
```

### Response Structure
```json
{
  "choices": [{
    "message": {
      "reasoning_details": [
        {
          "type": "reasoning.text",
          "text": "Step-by-step thinking...",
          "format": "anthropic-claude-v1"
        }
      ]
    }
  }]
}
```

### Value
Transparent insight into AI decision-making for debugging and prompt improvement.

---

## Common Pitfalls & Fixes

### 1. BCrypt Version Warning
**Issue:** `AttributeError: module 'bcrypt' has no attribute '__about__'`
**Impact:** Non-critical, doesn't affect functionality
**Fix:** Upgrade bcrypt or ignore warning

### 2. Long Generation Time Without Feedback
**Issue:** 60+ second generations with no user feedback
**Fix:** Status polling every 5 seconds in frontend ✅

### 3. Botasaurus API Mismatch
**Issue:** Agent uses non-existent methods like `driver.select_all()`
**Fix:** Update system prompt with accurate Botasaurus documentation

### 4. Session State Leakage
**Issue:** Browser sessions not properly cleaned up
**Fix:** Automatic cleanup in `tools_manager.cleanup_generation()`

---

## Performance Optimizations

### 1. HTML Caching
Cache HTML in `GenerationSession` to avoid repeated page fetches for DOM analysis tools.

### 2. Browser Session Reuse
Create browser session once, reuse across multiple tool calls in same generation.

### 3. Tool Call Batching
Where possible, combine multiple analyses in single tool call.

### 4. Reasoning Token Efficiency
Use "medium" effort (50% of tokens) instead of "high" for faster responses.

---

## Debugging Tips

### View Agent Reasoning
```bash
docker-compose logs -f backend | grep "Reasoning:"
```

### Check Tool Call Sequence
```bash
docker-compose logs -f backend | grep "Tool call:"
```

### Monitor Generation Progress
```sql
SELECT id, status, scraping_config->>'iterations'
FROM scrapers
WHERE status = 'generating';
```

### Inspect Generated Files
```bash
docker-compose exec backend ls -la /app/scrapers/USER_ID/SCRAPER_ID/
```

---

## Future Optimizations

1. **Parallel Tool Execution:** Execute independent tools concurrently
2. **Response Streaming:** Stream generation progress via WebSocket
3. **Smart Caching:** Cache DOM analysis for similar URLs
4. **Model Selection:** Use cheaper models for simple analysis tasks
5. **Tool Call Prediction:** Predict next tools to pre-warm sessions
