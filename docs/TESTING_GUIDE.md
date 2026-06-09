# Secondary Agent Testing Guide

This guide explains how to trigger and test the Secondary Agent for scraper code generation, both via API and through the application.

---

## Prerequisites

1. **Backend Running:** `docker-compose up backend`
2. **OpenRouter API Key:** Set in `.env` file
3. **User Account:** Register and get JWT token

---

## Method 1: Testing via API (curl)

This is the **currently working method** since the frontend doesn't have the generate button yet.

### Step 1: Register/Login to Get JWT Token

```bash
# Register new user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPassword123!"
  }'

# Login to get access token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPassword123!"
  }'
```

**Save the `access_token` from the response.**

### Step 2: Create a Scraper

```bash
curl -X POST http://localhost:8000/api/scrapers \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Books to Scrape Test",
    "target_url": "https://books.toscrape.com/"
  }'
```

**Save the scraper `id` from the response.**

### Step 3: Update Scraper with Data Fields

```bash
curl -X PUT http://localhost:8000/api/scrapers/SCRAPER_ID \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scraping_config": {
      "data_fields": ["title", "price", "rating", "availability"],
      "special_requirements": "Extract all books from the first page"
    }
  }'
```

### Step 4: Trigger Secondary Agent Code Generation

```bash
curl -X POST http://localhost:8000/api/scrapers/SCRAPER_ID/generate \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**This will take 30-60 seconds to complete.**

Expected response:
```json
{
  "scraper_id": "uuid-here",
  "status": "active",
  "message": "Code generation completed",
  "result": {
    "success": true,
    "scraper_code": "from botasaurus import browser...",
    "test_results": {...},
    "reasoning_log": [...],
    "tool_calls": [...],
    "iterations": 5
  }
}
```

### Step 5: View Generated Scraper

```bash
curl -X GET http://localhost:8000/api/scrapers/SCRAPER_ID \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Look for:
- `scraping_config.generated_code` - The Python scraper code
- `scraping_config.reasoning_log` - AI's thinking process
- `scraping_config.test_results` - Execution results
- `scraping_config.tool_calls` - MCP tools used

### Step 6: View Generated Code File

The code is also saved to disk:

```bash
# From your local machine
cat backend/scrapers/USER_ID/SCRAPER_ID/*.py

# Or from inside Docker container
docker-compose exec backend cat /app/scrapers/USER_ID/SCRAPER_ID/*.py
```

---

## Method 2: Testing via Frontend (Needs Implementation)

**Status:** ❌ Not yet implemented

Once the generate button is added to the frontend, the workflow will be:

### Future Workflow:

1. **Login to app:** Navigate to `http://localhost:3000`
2. **Go to Scrapers page:** Click "Scrapers" in nav
3. **Create new scraper:** Click "New Scraper" button
   - Enter name
   - Enter target URL
   - Specify data fields (title, price, etc.)
4. **View scraper details:** Click on the scraper
5. **Click "Generate Code" button:** (NEEDS TO BE ADDED)
   - Shows loading spinner
   - Polls backend for status
   - Displays progress if WebSocket implemented
6. **View generated code:** Code viewer tab (NEEDS TO BE ADDED)
7. **View reasoning log:** Reasoning tab shows AI's thinking (NEEDS TO BE ADDED)
8. **Test scraper:** Click "Run Test" to execute

### What Frontend Needs:

#### 1. Add Generate Method to Scraper Service

File: `frontend/src/services/scraper.js`

```javascript
/**
 * Generate scraper code via Secondary Agent
 * @param {string} scraperId - Scraper ID
 * @returns {Promise<Object>} Generation result
 */
async generateScraperCode(scraperId) {
  try {
    const response = await api.post(`/scrapers/${scraperId}/generate`)
    return response
  } catch (error) {
    throw error.response?.data?.detail || 'Failed to generate scraper code'
  }
}
```

#### 2. Add Generate Button to Scraper Detail Page

File: `frontend/src/views/ScraperDetail.vue`

```vue
<template>
  <!-- Add button next to "Run Now" button -->
  <v-btn
    color="primary"
    @click="handleGenerateCode"
    :loading="generating"
    v-if="scraperStore.currentScraper.status !== 'active'"
  >
    <v-icon start>mdi-robot</v-icon>
    Generate Code
  </v-btn>
</template>

<script setup>
const generating = ref(false)

const handleGenerateCode = async () => {
  try {
    generating.value = true
    const result = await scraperService.generateScraperCode(scraperId)

    // Show success message
    // Refresh scraper to see generated code
    await scraperStore.fetchScraper(scraperId)
  } catch (error) {
    console.error('Generation failed:', error)
  } finally {
    generating.value = false
  }
}
</script>
```

#### 3. Create Code Viewer Component

File: `frontend/src/components/CodeViewer.vue`

```vue
<template>
  <v-card>
    <v-card-title>Generated Code</v-card-title>
    <v-card-text>
      <pre><code class="language-python">{{ code }}</code></pre>
      <v-btn @click="copyToClipboard">Copy Code</v-btn>
    </v-card-text>
  </v-card>
</template>

<script setup>
const props = defineProps(['code'])

const copyToClipboard = () => {
  navigator.clipboard.writeText(props.code)
}
</script>
```

#### 4. Create Reasoning Log Viewer Component

File: `frontend/src/components/ReasoningLog.vue`

```vue
<template>
  <v-card>
    <v-card-title>AI Reasoning Log</v-card-title>
    <v-card-text>
      <v-expansion-panels>
        <v-expansion-panel
          v-for="(entry, index) in reasoningLog"
          :key="index"
        >
          <v-expansion-panel-title>
            Iteration {{ entry.iteration }} - {{ entry.type }}
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            {{ entry.text }}
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>
  </v-card>
</template>

<script setup>
const props = defineProps(['reasoningLog'])
</script>
```

---

## Method 3: Testing via Primary Agent (Future)

**Status:** ❌ Partially implemented (needs integration)

Once Primary Agent is fully integrated:

1. **Open chat interface:** Navigate to Chat page
2. **Send message:** "Create a scraper for https://books.toscrape.com to extract title, price, and rating"
3. **Primary Agent responds:**
   - Parses intent
   - Creates scraper via API
   - Triggers Secondary Agent
   - Returns scraper ID
4. **View scraper:** Link to scraper detail page
5. **Monitor generation:** Real-time updates via chat

---

## Understanding the Generation Process

### What Happens During Generation:

#### Phase 1: Website Analysis (Iterations 1-5)
- Agent navigates to target URL
- Extracts HTML structure
- Analyzes DOM patterns
- Identifies repeating elements
- Suggests CSS selectors for each data field
- Checks for API endpoints

**Example Tool Calls:**
```json
[
  {"function": "browser_navigate", "url": "https://books.toscrape.com"},
  {"function": "browser_get_page_source"},
  {"function": "dom_analyze_structure"},
  {"function": "dom_suggest_selectors", "field_name": "title"},
  {"function": "dom_suggest_selectors", "field_name": "price"},
  {"function": "network_detect_data_endpoints"}
]
```

#### Phase 2: Code Generation (Iterations 6-10)
- Agent writes Botasaurus scraper code
- Uses selectors discovered in Phase 1
- Implements anti-detection measures
- Adds error handling
- Writes code to file system

**Example Tool Call:**
```json
{
  "function": "write_scraper_code",
  "script_name": "books_scraper.py",
  "script_content": "from botasaurus import browser..."
}
```

#### Phase 3: Testing (Iterations 11-15)
- Agent executes generated scraper
- Validates output
- Reports results
- Provides final summary

**Example Tool Call:**
```json
{
  "function": "test_scraper",
  "script_name": "books_scraper.py"
}
```

### Reasoning Tokens

With reasoning tokens enabled, you'll see the AI's internal thought process:

```json
{
  "reasoning_log": [
    {
      "iteration": 1,
      "type": "reasoning.text",
      "text": "I need to first navigate to the target URL and analyze the page structure. Let me start by using the browser_navigate tool...",
      "format": "anthropic-claude-v1"
    },
    {
      "iteration": 2,
      "type": "reasoning.text",
      "text": "The page has loaded. Now I'll get the HTML source to analyze the DOM structure. I can see this is a book listing page...",
      "format": "anthropic-claude-v1"
    }
  ]
}
```

---

## Monitoring Generation Progress

### Via Docker Logs (Real-time)

```bash
docker-compose logs -f backend
```

Look for:
```
[Iteration 1] Reasoning: I need to first navigate to the target URL...
[Iteration 2] Reasoning: The page has loaded. Now I'll get the HTML...
```

### Via Database Query

```sql
SELECT
  id,
  name,
  status,
  scraping_config->>'iterations' as iterations,
  scraping_config->>'final_message' as final_message
FROM scrapers
WHERE user_id = 'YOUR_USER_ID'
ORDER BY updated_at DESC;
```

### Via API Polling

```bash
# Poll scraper status every 5 seconds
while true; do
  curl -s http://localhost:8000/api/scrapers/SCRAPER_ID \
    -H "Authorization: Bearer YOUR_TOKEN" \
    | jq '.status'
  sleep 5
done
```

Wait for status to change from `"generating"` to `"active"` or `"failed"`.

---

## Expected Output Structure

### Generated Code File

Location: `backend/scrapers/{user_id}/{scraper_id}/scraper_name.py`

```python
from botasaurus import browser, AntiDetectDriver
import json

@browser(
    headless=True,
    block_images=True
)
def scrape_books(driver: AntiDetectDriver, data):
    driver.get(data['url'])
    driver.short_random_sleep()

    results = []
    items = driver.find_elements('css selector', 'article.product_pod')

    for item in items:
        result = {
            'title': item.find_element('css selector', 'h3 a').get_attribute('title'),
            'price': item.find_element('css selector', '.price_color').text,
            # ... more fields
        }
        results.append(result)

    return results

if __name__ == "__main__":
    data = {'url': 'https://books.toscrape.com/'}
    results = scrape_books(data)
    print(json.dumps(results, indent=2))
```

### Database Record

```json
{
  "id": "uuid-here",
  "name": "Books to Scrape Test",
  "target_url": "https://books.toscrape.com/",
  "status": "active",
  "scraping_config": {
    "data_fields": ["title", "price", "rating"],
    "generated_code": "from botasaurus import browser...",
    "reasoning_log": [...],
    "test_results": {
      "success": true,
      "records_scraped": 20,
      "execution_time": 3.5
    },
    "tool_calls": [...],
    "iterations": 8,
    "generation_completed_at": "2025-01-13T14:45:39.000Z"
  }
}
```

---

## Troubleshooting

### Generation Fails with 401 Unauthorized

**Cause:** OpenRouter API key not set or invalid

**Fix:**
```bash
# Check .env file
cat .env | grep OPENROUTER_API_KEY

# If missing, add it:
echo "OPENROUTER_API_KEY=your_key_here" >> .env

# Rebuild backend container
docker-compose up -d --build backend
```

### Generation Takes Too Long (>120 seconds)

**Cause:** Timeout in HTTP client

**Fix:** Increase timeout in `agent.py`:
```python
async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minutes
```

### Generated Code Uses Wrong Botasaurus API

**Cause:** Agent doesn't know correct Botasaurus methods

**Fix:** Update system prompt in `backend/agents/secondary/agent.py` with accurate API documentation from Botasaurus GitHub/docs.

### No Reasoning Tokens in Response

**Cause:** Model doesn't support reasoning or OpenRouter doesn't return them

**Check:** Verify response structure in logs. DeepSeek v3.2 should support reasoning tokens.

### File Not Found When Viewing Generated Code

**Cause:** Docker volume not mounted correctly

**Fix:** Check `docker-compose.yml` has:
```yaml
volumes:
  - ./backend:/app
```

---

## Next Steps After Testing

1. **Improve Generated Code Quality**
   - Update system prompt with correct Botasaurus API
   - Add more examples to prompt
   - Test with diverse websites

2. **Add Frontend Integration**
   - Implement generate button
   - Add code viewer
   - Show reasoning log

3. **Build Scraper Executor**
   - Execute generated scripts
   - Store results in MinIO
   - Return data to user

4. **Integrate Primary Agent**
   - Parse chat intents
   - Auto-create scrapers
   - Trigger Secondary Agent from chat

---

## Example End-to-End Test

Here's a complete working example using Books to Scrape:

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPassword123!"}' \
  | jq -r '.access_token')

# 2. Create scraper
SCRAPER_ID=$(curl -s -X POST http://localhost:8000/api/scrapers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Books Scraper",
    "target_url": "https://books.toscrape.com/"
  }' | jq -r '.id')

# 3. Update config
curl -X PUT "http://localhost:8000/api/scrapers/$SCRAPER_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scraping_config": {
      "data_fields": ["title", "price", "rating", "availability"]
    }
  }'

# 4. Generate code
curl -X POST "http://localhost:8000/api/scrapers/$SCRAPER_ID/generate" \
  -H "Authorization: Bearer $TOKEN"

# 5. Wait for completion (poll every 5 seconds)
while true; do
  STATUS=$(curl -s "http://localhost:8000/api/scrapers/$SCRAPER_ID" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" != "generating" ]; then
    break
  fi
  sleep 5
done

# 6. View results
curl -s "http://localhost:8000/api/scrapers/$SCRAPER_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.scraping_config.generated_code'
```

Save this as `test_secondary_agent.sh` and run with `bash test_secondary_agent.sh`.
