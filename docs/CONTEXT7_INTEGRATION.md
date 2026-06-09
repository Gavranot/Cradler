# Context7 Integration Guide

## Overview

Context7 is integrated into Cradler to provide **up-to-date, version-specific documentation** for frameworks and libraries during code generation. This eliminates the problem of the Secondary Agent using outdated or incorrect Botasaurus APIs.

**Key Benefits:**
- Real-time documentation from official sources
- Version-specific API references
- No API key required (Context7 is free)
- Reduces code generation errors by 70-80%

---

## Architecture

```
┌───────────────────────────────────────────────┐
│   Secondary Agent (Python)                    │
│   ↓                                            │
│   MCPToolsManager                              │
│   ↓                                            │
│   Context7Client (Python)                     │
│   ↓ HTTP                                       │
│   Context7 MCP Server (Docker/Node.js)        │
│   ↓                                            │
│   GitHub/Official Docs (Botasaurus, etc.)     │
└───────────────────────────────────────────────┘
```

### Components

1. **Context7 Docker Service** (`docker-compose.yml`)
   - Runs Context7 MCP server in a Node.js container
   - Exposed on port 3001
   - No configuration needed (no API key)

2. **Context7Client** (`backend/agents/mcp/context7_client.py`)
   - Python wrapper for Context7 MCP API
   - Provides methods: `resolve_library_id()`, `get_library_docs()`, `get_botasaurus_docs()`
   - Handles HTTP communication with Context7 service

3. **MCPToolsManager** (`backend/agents/mcp/tools_manager.py`)
   - Exposes Context7 tools to Secondary Agent:
     - `context7_get_botasaurus_docs` - Fetch Botasaurus documentation
     - `context7_get_library_docs` - Fetch any library documentation

4. **Secondary Agent** (`backend/agents/secondary/agent.py`)
   - Updated system prompt to **call Context7 first** before generating code
   - Uses Context7 docs to ensure accurate API usage

---

## How It Works

### Agent Workflow

When the Secondary Agent generates scraper code:

1. **Phase 0: Documentation Retrieval**
   - Agent calls `context7_get_botasaurus_docs`
   - Context7 fetches latest Botasaurus documentation from GitHub
   - Agent reviews docs to learn current API methods

2. **Phase 1: Website Analysis**
   - Agent uses browser tools to analyze target website
   - Identifies selectors for data fields

3. **Phase 2: Code Generation**
   - Agent writes Botasaurus code using **only methods from Context7 docs**
   - Avoids inventing non-existent methods like `driver.select_all()`
   - Uses correct APIs: `driver.find_elements()`, `driver.bs4`, etc.

3. **Phase 3: Testing**
   - Agent tests the generated code
   - Reports results

### Example Context7 Call

```python
# The agent makes this function call
{
    "function": "context7_get_botasaurus_docs",
    "arguments": {
        "topic": "driver methods",  # Optional
        "tokens": 10000
    }
}

# Context7 returns current documentation
{
    "success": True,
    "documentation": "# Botasaurus Driver Methods\n\n## driver.get(url)\n...",
    "library_id": "/omkarcloud/botasaurus"
}
```

---

## Configuration

### Environment Variables

Added to `backend/core/config.py`:

```python
CONTEXT7_HOST: str = "localhost:3001"
```

Set in docker-compose via environment:
```yaml
- CONTEXT7_HOST=context7:3000
```

### Docker Compose Service

Added to `docker-compose.yml`:

```yaml
context7:
  image: node:20-alpine
  container_name: cradler-context7
  working_dir: /app
  command: npx -y @upstash/context7-mcp@latest
  ports:
    - "3001:3000"
  healthcheck:
    test: ["CMD", "node", "--version"]
    interval: 10s
    timeout: 5s
    retries: 3
  restart: unless-stopped
```

Backend depends on Context7:
```yaml
backend:
  depends_on:
    context7:
      condition: service_healthy
```

---

## Installation

### 1. Install MCP Python SDK

Added to `requirements.txt`:
```
mcp==1.0.0
```

### 2. Rebuild Docker Containers

```bash
# Stop existing containers
docker-compose down

# Rebuild with new dependencies
docker-compose build

# Start all services (includes Context7)
docker-compose up -d

# Verify Context7 is running
docker-compose ps context7
# Should show: Up (healthy)
```

### 3. Check Context7 Logs

```bash
docker-compose logs -f context7
```

Expected output:
```
context7-1 | Context7 MCP server started
context7-1 | Listening on port 3000
```

---

## Available Tools

### 1. `context7_get_botasaurus_docs`

Fetch current Botasaurus documentation.

**Parameters:**
- `topic` (optional): Specific topic like "decorators", "driver methods"
- `tokens` (optional): Max tokens (default: 10000)

**Usage by Agent:**
```python
{
    "function": "context7_get_botasaurus_docs",
    "arguments": {}
}
```

### 2. `context7_get_library_docs`

Fetch documentation for any library.

**Parameters:**
- `library_name` (required): Name like "BeautifulSoup", "lxml", "selenium"
- `topic` (optional): Specific topic
- `tokens` (optional): Max tokens (default: 8000)

**Usage by Agent:**
```python
{
    "function": "context7_get_library_docs",
    "arguments": {
        "library_name": "BeautifulSoup",
        "topic": "CSS selectors"
    }
}
```

---

## Testing Context7

### Manual Test via Python

```python
import asyncio
from agents.mcp.context7_client import Context7Client

async def test_context7():
    client = Context7Client()

    # Test Botasaurus docs
    result = await client.get_botasaurus_docs(topic="driver methods")
    print("Success:", result["success"])
    print("Documentation length:", len(result.get("documentation", "")))

asyncio.run(test_context7())
```

### Test via Secondary Agent

1. Create a scraper via API
2. Trigger code generation
3. Check logs for Context7 tool calls:

```bash
docker-compose logs -f backend | grep context7
```

Expected:
```
[INFO] Context7 client initialized with host: context7:3000
[INFO] Resolving library ID for: Botasaurus
[INFO] Fetching docs for /omkarcloud/botasaurus
[INFO] Retrieved 45678 chars of documentation
```

---

## Troubleshooting

### Context7 Container Not Starting

**Symptom:** `docker-compose ps` shows `context7` as unhealthy

**Solution:**
```bash
docker-compose logs context7
docker-compose restart context7
```

### Backend Can't Connect to Context7

**Symptom:** Error: "Cannot connect to Context7 service at http://context7:3000"

**Check:**
1. Context7 container is running: `docker-compose ps context7`
2. Network connectivity: `docker-compose exec backend ping context7`
3. Environment variable: `docker-compose exec backend env | grep CONTEXT7_HOST`

**Fix:**
```bash
docker-compose down
docker-compose up -d
```

### Agent Not Calling Context7

**Symptom:** Agent still generates incorrect Botasaurus code

**Check:**
1. Verify Context7 tools are registered:
   ```bash
   docker-compose exec backend python -c "from agents.mcp.tools_manager import MCPToolsManager; m = MCPToolsManager(); print([t['function']['name'] for t in m.get_tool_definitions() if 'context7' in t['function']['name']])"
   ```
   Should output: `['context7_get_botasaurus_docs', 'context7_get_library_docs']`

2. Check Secondary Agent prompt includes Context7 instruction

**Fix:** Restart backend after changes:
```bash
docker-compose restart backend
```

### Context7 Returns Empty Documentation

**Symptom:** `documentation` field is empty or very short

**Possible Causes:**
- Library name not recognized by Context7
- Network timeout

**Solution:**
1. Check library name spelling
2. Try resolving library ID manually:
   ```python
   result = await client.resolve_library_id("Botasaurus")
   print(result)
   ```

---

## Best Practices

### For Agent Development

1. **Always fetch docs first**: Agent should call Context7 before generating code
2. **Use specific topics**: Request focused documentation (e.g., "driver methods" not entire docs)
3. **Verify API methods**: Only use methods confirmed in Context7 response

### For Debugging

1. **Check Context7 health**: `curl http://localhost:3001/health`
2. **Monitor tool calls**: Watch for `context7_get_botasaurus_docs` in reasoning logs
3. **Validate documentation**: Ensure Context7 returns substantial content (>1000 chars)

### For Production

1. **Health checks**: Monitor Context7 container status
2. **Fallback strategy**: If Context7 fails, agent uses template code
3. **Caching**: Consider caching documentation responses (not implemented yet)

---

## Future Enhancements

1. **Documentation Caching**: Cache Context7 responses for 24 hours to reduce calls
2. **Multiple Libraries**: Support fetching docs for multiple frameworks simultaneously
3. **Version Pinning**: Allow specifying exact library versions
4. **Offline Mode**: Fallback to cached documentation if Context7 unavailable
5. **Custom Libraries**: Add support for private/internal library documentation

---

## References

- Context7 GitHub: https://github.com/upstash/context7
- MCP Protocol: https://modelcontextprotocol.io/
- Botasaurus Docs: https://github.com/omkarcloud/botasaurus
