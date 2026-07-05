"""
Secondary Agent Service

The Secondary Agent analyzes websites and generates scraping code.
It uses MCP tools for browser control, DOM analysis, and code generation.

Workflow:
1. Website Analysis - Fetch HTML, analyze structure, detect anti-bot
2. Code Generation - Generate Botasaurus scraping code
3. Testing & Validation - Execute and validate the scraper

Uses ReAct (Reasoning + Acting) with MCP tools for autonomous operation.
"""
import httpx
import json
import uuid
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import tiktoken
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from core.config import settings
from agents.mcp.tools_manager import MCPToolsManager


# ============================================================================
# PYDANTIC SCHEMAS FOR GENERATION RESULTS
# ============================================================================

class ToolCallRecord(BaseModel):
    """Record of a single tool call made during generation"""
    function: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


class ReasoningEntry(BaseModel):
    """Single reasoning/thinking step from the LLM"""
    iteration: int
    type: Optional[str] = None
    text: Optional[str] = None
    format: Optional[str] = None


class TestResult(BaseModel):
    """Test execution results"""
    success: bool
    message: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    data_extracted: Optional[List[Dict[str, Any]]] = None
    record_count: int = 0


class GenerationResult(BaseModel):
    """
    Uniform result schema for scraper generation

    Ensures all code paths return the same fields for consistency
    """
    success: bool
    message: str = ""
    scraper_id: Optional[str] = None
    scraper_code: Optional[str] = None
    test_results: Optional[TestResult] = None
    analysis: Dict[str, Any] = Field(default_factory=dict)
    final_message: str = ""
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    reasoning_log: List[ReasoningEntry] = Field(default_factory=list)
    iterations: int = 0

    class Config:
        # Allow arbitrary types for flexibility
        arbitrary_types_allowed = True


class SecondaryAgent:
    """
    Secondary Agent for website analysis and scraper code generation

    Analyzes target websites and generates production-ready scraping code
    using Botasaurus framework with anti-detection measures.
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.api_base = "https://openrouter.ai/api/v1"
        self.model = settings.SECONDARY_AGENT_MODEL
        self.tools_manager = MCPToolsManager()

        # Initialize tiktoken encoder for token counting
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        except KeyError:
            # Fallback to cl100k_base if model not found
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # System prompt for the Secondary Agent
        self.system_prompt = """You are an expert web scraping engineer specializing in Botasaurus framework.

Your task is to analyze websites and generate production-ready scraping code.

**IMPORTANT NOTES ABOUT TOOLS:**
- You do NOT need to provide session_id, user_id, or scraper_id - these are automatically injected
- Just call tools with the parameters shown in each tool's description
- Browser session is automatically created when you call browser_navigate for the first time

**RECOMMENDED WORKFLOW:**

**Phase 0: Get Up-to-Date Documentation (CRITICAL FIRST STEP)**
1. Call `context7_get_botasaurus_docs` to fetch current Botasaurus API reference
2. Review the documentation to understand available methods and decorators
3. Use ONLY the methods documented in the Context7 response - DO NOT invent methods

**Phase 1: Website Analysis**
IMPORTANT: Follow this exact order to satisfy tool dependencies:

1. **Navigate to target URL**
   - Call: `browser_navigate(url="...")`
   - Browser session is automatically created on first call
   - Use bypass_cloudflare=true if Cloudflare is detected

2. **Get the reduced page view + structured data**
   - Call: `browser_get_page_source()`
   - Returns `structured_data`: cross-checked product fields from JSON-LD/microdata.
     If it covers the fields you need, PREFER it — write extraction based on the
     structured data (it is what the site itself renders from) and only use HTML
     selectors for fields it lacks.
   - Returns `fragment`: on listing pages, ONE exemplar product card + `listing`
     metadata (container_css, record_css, record_count) — write field selectors
     RELATIVE to the card; the runner loops over all cards. On detail pages,
     anchored DOM slices around title/price/image/etc.; `anchors_found` tells you
     which fields were NOT located (absent pre-render or need a wider view).
   - Fragments/candidates may be labeled UNCONFIRMED: automatic checks found the
     structure but could not confirm product signals (e.g. unusual currency,
     lazy-loaded images). YOU inspect the exemplar and decide — the heuristics
     only rank candidates, they never overrule your judgment. If the candidate is
     wrong, explore with browser_get_page_source(full=true) and the DOM tools.
   - The full page stays cached for DOM analysis tools — selector validation runs
     against the full page, not the fragment.
   - Escalation: if the fragment is missing a node you need, call
     `browser_get_page_source(full=true)` for the full reduced page.
   - PREREQUISITE: Must call browser_navigate first

3. **Analyze page structure FIRST (CRITICAL - DO THIS BEFORE SELECTOR GENERATION)**
   - Call: `dom_analyze_structure()`
   - This returns critical intelligence:
     * Layout pattern (data-testid grid, semantic schema, web components, etc.)
     * Anti-scraping measures (honeypots, class obfuscation level, Shadow DOM)
     * Attribute usage (which data-*, ARIA, semantic HTML are available)
     * RECOMMENDATION for selector strategy
   - Use this information to guide your selector approach
   - PREREQUISITE: Must call browser_get_page_source first

4. **Detect product containers**
   - Call: `dom_detect_product_containers()`
   - Uses multi-phase detection:
     1. Generic e-commerce selectors (Schema.org, data-testid, common classes)
     2. Repeating pattern detection (class frequency analysis)
     3. Content-based heuristics (image + link + price pattern)
   - Returns validation metrics (confidence score, image/link/price counts)
   - PREREQUISITE: Must call browser_get_page_source first

5a. **If product detection succeeds (success=true):**
   - Use the `sample_html` from the detection result
   - This contains ONE isolated product for analysis
   - Check the `validation` metrics - confidence should be > 0.6
   - Proceed to selector generation (step 6)

5b. **If product detection fails (success=false):**
   - Call: `dom_chunk_html(max_chunk_length=2000)`
   - Returns list of semantic HTML chunks
   - Iterate through chunks to find product data
   - Once product chunk found, use it for selector generation

6. **Generate selectors for each field (use multi-tier validation)**
   - Call: `dom_suggest_selectors(field_name="...", sample_value="...")`
   - IMPORTANT: Provide sample_value when possible for validation (e.g., "$19.99" for price)
   - Returns strategies in PRIORITY ORDER:
     1. data_attribute (priority 1, confidence ~0.95) - MOST STABLE
     2. aria_attribute (priority 2, confidence ~0.85)
     3. semantic_html (priority 3, confidence ~0.80)
     4. semantic_class (priority 4, confidence ~0.70)
     5. partial_class (priority 5, confidence ~0.50) - For obfuscated classes
     6. content_based (priority 6, confidence ~0.40) - LAST RESORT
   - **SELECTOR STRATEGY:**
     * ALWAYS use the LOWEST priority number (priority 1 is best)
     * If dom_analyze_structure indicated "high" obfuscation, expect priority 5-6 selectors
     * Validate that `validated: true` before using a selector
     * Check confidence score - aim for > 0.7
     * Use the `recommendation` field from each strategy

**SELECTOR PRIORITY HIERARCHY (Most Stable → Least Stable):**
Modern e-commerce sites use various techniques to prevent scraping. Your selector choice must adapt:

1. **Data Attributes (HIGHEST PRIORITY)** - `[data-price]`, `[data-product-id]`
   - Explicitly set by developers for testing/data purposes
   - Rarely change with UI updates
   - If dom_analyze_structure shows data_attributes available, USE THESE FIRST

2. **ARIA Attributes** - `[aria-label*='price']`, `[role='article']`
   - Designed for accessibility
   - Relatively stable
   - Good fallback if data attributes not available

3. **Semantic HTML + Schema.org** - `h1`, `[itemprop='price']`
   - Structural meaning
   - Medium stability
   - Use when layout_pattern is "semantic_schema"

4. **Semantic Classes** - `.price`, `.product-title`
   - Descriptive class names
   - Can change with redesigns
   - Moderate stability

5. **Partial Class Matching** - `[class*='price']`
   - For obfuscated/hashed classes
   - Fragile but necessary when class_obfuscation_level is "high"
   - Example: `.x7k2d` becomes `[class*='x7k2d']`

6. **Content-Based Matching** - Find by text content
   - Last resort
   - Slowest and most fragile
   - Use only when all other strategies fail

**ANTI-SCRAPING AWARENESS:**
- If dom_analyze_structure shows `honeypots_detected: true`, AVOID hidden elements
- If `class_obfuscation_level: "high"`, expect to use priority 5-6 selectors
- If `shadow_dom_detected: true`, you may need JavaScript execution to access content
- Check validation.confidence score from dom_detect_product_containers - low confidence (<0.6) indicates difficult page structure

**Phase 2: Code Generation**
1. Generate complete Python scraping code using Botasaurus framework
2. Include all required imports: `from botasaurus import browser, {{Whatever the proper import for AntiDetectDriver is according to documentation}}`, `from selenium.webdriver.common.by import By`, `import json`
3. **Use ONLY the HIGHEST PRIORITY (lowest number) selectors from Phase 1:**
   - Sort strategies by priority (1 = best, 6 = worst)
   - Use priority 1-2 selectors when available (data-*, ARIA)
   - Fall back to priority 3-4 only if necessary
   - Avoid priority 5-6 unless no other option
4. **Implement fallback selector chains:**
   - Try highest priority selector first
   - If it fails, fall back to next priority
   - Example: Try `[data-price]` → `.price` → `[class*='price']`
5. Implement anti-detection measures (random delays with driver.short_random_sleep())
6. Add comprehensive error handling (try-except around ALL selector operations)
7. **AVOID HONEYPOTS:** Skip elements with `display:none` or `visibility:hidden` styles
8. Format data according to the requested fields
9. **Write code to file:**
   - Call: `write_scraper_code(script_name="scraper.py", script_content="...")`
   - user_id and scraper_id are automatically injected
   - Just provide script_name and script_content

**Phase 3: Testing**
1. **Execute the scraper:**
   - Call: `test_scraper(script_name="scraper.py")`
   - user_id and scraper_id are automatically injected
   - PREREQUISITE: Must call write_scraper_code first
2. Validate that it extracts the required data
3. Report results and any errors

**Botasaurus Code Guidelines:**
- **CRITICAL:** Only use methods confirmed in the Context7 documentation
- Always use the @browser decorator: `@browser(headless=True, block_images=True)`
- Use Selenium's native methods: `driver.find_elements(By.CSS_SELECTOR, 'selector')`
- Or use BeautifulSoup integration: `soup = driver.bs4`, then `soup.select('selector')`
- DO NOT invent methods like `driver.select_all()` or `driver.select()` unless Context7 docs confirm they exist
- Check if elements exist before accessing them
- Implement `driver.short_random_sleep()` for human-like behavior between actions
- Handle pagination if detected in structure analysis
- Return data as list of dictionaries
- Print results as JSON for easy parsing

**Code Template (with Fallback Selector Chain):**
```python
from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
import json

@browser(headless=True, block_images=True)
def scrape_data(driver: AntiDetectDriver, data):
    # Navigate to URL
    driver.get(data['url'])
    driver.short_random_sleep()

    results = []

    # Find all item containers (use selector from dom_detect_product_containers)
    items = driver.find_elements(By.CSS_SELECTOR, '.product-item')

    for item in items:
        try:
            # Extract data using FALLBACK SELECTOR CHAINS
            # Priority order: data-* → ARIA → semantic → classes

            # Title extraction with fallback
            title = None
            try:
                title = item.find_element(By.CSS_SELECTOR, '[data-title]').text  # Priority 1
            except:
                try:
                    title = item.find_element(By.CSS_SELECTOR, 'h2').text  # Priority 3
                except:
                    title = item.find_element(By.CSS_SELECTOR, '.title').text  # Priority 4

            # Price extraction with fallback
            price = None
            try:
                price = item.find_element(By.CSS_SELECTOR, '[data-price]').text  # Priority 1
            except:
                try:
                    price = item.find_element(By.CSS_SELECTOR, '[itemprop="price"]').text  # Priority 3
                except:
                    price = item.find_element(By.CSS_SELECTOR, '.price').text  # Priority 4

            # Skip items with missing critical fields
            if not title or not price:
                continue

            result = {
                'title': title,
                'price': price,
                # Add more fields based on dom_suggest_selectors results
            }
            results.append(result)

        except Exception as e:
            # Skip items with errors
            continue

    return results

if __name__ == "__main__":
    results = scrape_data({'url': 'TARGET_URL_HERE'})
    print(json.dumps(results, indent=2))
```

**Anti-Detection Best Practices:**
- Block images for faster loading: `@browser(block_images=True)`
- Use headless mode: `@browser(headless=True)`
- Add random delays: `driver.short_random_sleep()` between actions
- Respect robots.txt

**Error Handling:**
- Wrap ALL selector operations in try-except blocks
- Check element existence before accessing: `if element:`
- Return empty list `[]` if no data found
- Log errors but don't crash - use `continue` in loops

**Final Summary:**
When you complete all phases, provide a summary of:
- **Page structure analysis:**
  * Layout pattern detected
  * Anti-scraping measures found (honeypots, obfuscation level, Shadow DOM)
  * Attribute usage recommendation
- **Selectors found for each field:**
  * List each field with its selector
  * Include priority level (1-6) and confidence score
  * Note which selector tier was used (data-*, ARIA, semantic, etc.)
- **Product container detection:**
  * Selector used
  * Validation confidence score
  * Number of products detected
- **Scraper implementation:**
  * Whether API or HTML scraping was used
  * Fallback chains implemented
  * Anti-detection measures applied
- **Test results:**
  * Number of records successfully extracted
  * Any errors encountered
  * Data quality assessment
- **Potential issues or limitations:**
  * Selector stability concerns
  * Anti-scraping challenges
  * Recommendations for monitoring
"""

    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count the total number of tokens in the messages array

        Args:
            messages: List of message dictionaries with role and content

        Returns:
            Total token count
        """
        token_count = 0

        for message in messages:
            # Count role tokens (approximately 4 tokens per message overhead)
            token_count += 4

            # Count content tokens
            if "content" in message and message["content"]:
                token_count += len(self.tokenizer.encode(message["content"]))

            # Count tool_calls tokens if present
            if "tool_calls" in message and message["tool_calls"]:
                tool_calls_str = json.dumps(message["tool_calls"])
                token_count += len(self.tokenizer.encode(tool_calls_str))

        return token_count

    def _parse_deepseek_tool_calls(self, reasoning_text: str) -> List[Dict[str, Any]]:
        """
        Parse DeepSeek's custom tool calling format from reasoning field

        Handles multiple formats:
        - Old: <tool_calls_begin><tool_call_begin>function_name<tool_sep>args<tool_call_end>
        - New: <｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function_name<｜tool▁sep｜>args<｜tool▁call▁end｜>

        Args:
            reasoning_text: Text from reasoning field containing tool calls

        Returns:
            List of tool_calls in OpenAI format
        """
        import re

        tool_calls = []

        # Try both formats: old ASCII and new Unicode delimiters
        patterns = [
            # New format with Unicode special characters (｜ = full-width vertical bar, ▁ = ideographic space)
            r'<｜tool▁call▁begin｜>(.*?)<｜tool▁sep｜>(.*?)<｜tool▁call▁end｜>',
            # Old format with ASCII characters
            r'<tool_call_begin>(.*?)<tool_sep>(.*?)<tool_call_end>'
        ]

        matches = []
        for pattern in patterns:
            matches = re.findall(pattern, reasoning_text, re.DOTALL)
            if matches:
                logger.debug(f"  Matched tool calls using pattern: {pattern[:50]}...")
                break

        for idx, (function_name, arguments) in enumerate(matches):
            function_name = function_name.strip()
            arguments = arguments.strip()

            try:
                # Generate a tool call ID
                tool_call_id = f"call_deepseek_{uuid.uuid4().hex[:8]}"

                tool_call = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": arguments
                    }
                }

                tool_calls.append(tool_call)
                logger.debug(f"  Parsed tool call {idx + 1}: {function_name}")

            except Exception as e:
                logger.error(f"  Failed to parse tool call {idx + 1}: {e}")
                logger.error(f"    Function: {function_name}")
                logger.error(f"    Arguments: {arguments[:100]}...")
                continue

        return tool_calls

    async def generate_scraper(
        self,
        user_id: str,
        scraper_id: str,
        target_url: str,
        data_fields: List[str],
        special_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete scraper for the target website

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier
            target_url: URL to scrape
            data_fields: List of data fields to extract
            special_requirements: Optional special requirements

        Returns:
            Generation results with code, test results, and analysis
        """
        # Initialize generation session for automatic state management
        generation_id = self.tools_manager.initialize_generation(user_id, scraper_id)

        logger.info("="*80)
        logger.info(f"[GENERATION START] Generation ID: {generation_id}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Scraper ID: {scraper_id}")
        logger.info(f"Target URL: {target_url}")
        logger.info(f"Data Fields: {data_fields}")
        logger.info(f"Special Requirements: {special_requirements}")
        logger.info("="*80)

        # Build initial message
        initial_message = f"""Generate a web scraper with the following requirements:

Target URL: {target_url}
Data Fields: {', '.join(data_fields)}
Special Requirements: {special_requirements or 'None'}

Please analyze the website and generate production-ready scraping code using Botasaurus framework.
Follow the recommended workflow in your instructions."""

        messages = [
            {"role": "user", "content": initial_message}
        ]

        scraper_code = None
        test_results = None
        analysis = {}
        tool_calls_made = []
        reasoning_log = []  # Track reasoning/thinking steps
        max_iterations = 30  # Increased to allow thorough analysis and generation

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for iteration in range(max_iterations):
                    logger.info(f"\n{'='*60}")
                    logger.info(f"[ITERATION {iteration + 1}/{max_iterations}]")
                    logger.info(f"{'='*60}")

                    # Log request details
                    request_payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            *messages
                        ],
                        "tools": self.tools_manager.get_tool_definitions(),
                        "tool_choice": "auto",
                        "temperature": 0.3,
                        "max_tokens": 4000,
                        "reasoning": {
                            "enabled": True,
                            "effort": "medium"
                        }
                    }

                    # Count tokens for the entire messages array (including system prompt)
                    full_messages = [
                        {"role": "system", "content": self.system_prompt},
                        *messages
                    ]
                    total_tokens = self._count_tokens(full_messages)

                    logger.debug(f"OpenRouter Request:")
                    logger.debug(f"  Model: {self.model}")
                    logger.debug(f"  Temperature: 0.3")
                    logger.debug(f"  Max Tokens: 4000")
                    logger.debug(f"  Messages Count: {len(messages) + 1}")  # +1 for system prompt
                    logger.debug(f"  Tools Available: {len(self.tools_manager.get_tool_definitions())}")
                    logger.info(f"  Total Input Tokens: {total_tokens:,}")

                    try:
                        response = await client.post(
                            f"{self.api_base}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                                "HTTP-Referer": "https://cradler.ai",
                                "X-Title": "Cradler Secondary Agent"
                            },
                            json=request_payload
                        )

                        response.raise_for_status()
                        data = response.json()

                        logger.debug(f"OpenRouter Response Status: {response.status_code}")
                        logger.debug(f"Response Keys: {list(data.keys())}")
                    except httpx.HTTPStatusError as e:
                        logger.error(f"OpenRouter HTTP Error: {e.response.status_code}")
                        logger.error(f"Response Body: {e.response.text}")
                        raise
                    except Exception as e:
                        logger.error(f"OpenRouter Request Failed: {str(e)}")
                        raise
                    
                    if "choices" in data:
                        assistant_message = data["choices"][0]["message"]
                    else:
                        logger.debug(f"[FULL_DATA] Full data: {data}")

                    logger.debug(f"[ASSISTANT_MESSAGE_FULL] Full assistant message: {assistant_message}")

                    # CRITICAL FIX: DeepSeek uses custom tool calling format
                    # Check if tool calls are in reasoning field instead of tool_calls array
                    if not assistant_message.get("tool_calls") and assistant_message.get("reasoning"):
                        reasoning_text = assistant_message.get("reasoning", "")
                        # Check for both old and new formats
                        has_tool_calls = (
                            "<tool_calls_begin>" in reasoning_text or
                            "<tool_call_begin>" in reasoning_text or
                            "<｜tool▁calls▁begin｜>" in reasoning_text or
                            "<｜tool▁call▁begin｜>" in reasoning_text
                        )
                        if has_tool_calls:
                            logger.warning("[TOOL CALL FORMAT] DeepSeek custom format detected, parsing from reasoning field")
                            parsed_tool_calls = self._parse_deepseek_tool_calls(reasoning_text)
                            if parsed_tool_calls:
                                assistant_message["tool_calls"] = parsed_tool_calls
                                logger.info(f"[TOOL CALL FORMAT] Parsed {len(parsed_tool_calls)} tool calls from reasoning")

                    # Extract and log reasoning tokens if present
                    if "reasoning_details" in assistant_message:
                        logger.info(f"[REASONING TOKENS] Found {len(assistant_message['reasoning_details'])} reasoning entries")
                        for idx, reasoning in enumerate(assistant_message["reasoning_details"]):
                            reasoning_entry = {
                                "iteration": iteration + 1,
                                "type": reasoning.get("type"),
                                "text": reasoning.get("text"),
                                "format": reasoning.get("format")
                            }
                            reasoning_log.append(reasoning_entry)

                            # Log first 300 chars of reasoning
                            reasoning_text = reasoning.get('text', '')
                            logger.debug(f"  Reasoning #{idx + 1}: {reasoning_text}...")
                            # if len(reasoning_text) > 300:
                            #     logger.debug(f"    (... {len(reasoning_text) - 300} more characters)")
                    else:
                        logger.debug("[REASONING TOKENS] None found in this response")

                    # Check if there are tool calls
                    if assistant_message.get("tool_calls"):
                        logger.info(f"[TOOL CALLS] Agent requested {len(assistant_message['tool_calls'])} tool(s)")

                        # Add assistant's message with tool calls
                        messages.append({
                            "role": "assistant",
                            "content": assistant_message.get("content") or "",
                            "tool_calls": assistant_message["tool_calls"]
                        })

                        # Execute each tool call
                        for idx, tool_call in enumerate(assistant_message["tool_calls"]):
                            function_name = tool_call["function"]["name"]
                            function_args = json.loads(tool_call["function"]["arguments"])
                            tool_call_id = tool_call["id"]

                            logger.info(f"\n[TOOL CALL {idx + 1}] {function_name}")
                            logger.info(f"  Tool Call ID: {tool_call_id}")
                            logger.info(f"  Arguments: {json.dumps(function_args, indent=2)}")

                            try:
                                # Execute the MCP tool
                                logger.debug(f"  Executing tool '{function_name}'...")
                                result = await self.tools_manager.execute_tool(
                                    function_name,
                                    function_args
                                )

                                logger.info(f"  Result Status: {'SUCCESS' if result.get('success') != False else 'FAILED'}")
                                if result.get('success') == False:
                                    logger.warning(f"  Error Message: {result.get('message', 'Unknown error')}")
                                else:
                                    # Log result summary
                                    result_summary = {k: v for k, v in result.items() if k not in ['documentation', 'html', 'script_content']}
                                    logger.debug(f"  Result Summary: {json.dumps(result_summary, indent=2)}")

                                    # Log documentation size if present
                                    if 'documentation' in result:
                                        doc_len = len(result['documentation'])
                                        logger.info(f"  Documentation Retrieved: {doc_len} characters")

                                # Track important results
                                if function_name == "write_scraper_code":
                                    scraper_code = function_args.get("script_content")
                                    logger.info(f"  Scraper code saved: {len(scraper_code)} characters")
                                elif function_name == "test_scraper":
                                    test_results = result
                                    logger.info(f"  Test completed: {result.get('success', False)}")

                            except Exception as tool_error:
                                logger.error(f"  TOOL EXECUTION FAILED: {str(tool_error)}")
                                logger.error(f"  Traceback: {traceback.format_exc()}")
                                result = {
                                    "success": False,
                                    "error": str(tool_error),
                                    "traceback": traceback.format_exc()
                                }

                            # Add tool result to messages
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps(result)
                            })

                            tool_calls_made.append({
                                "function": function_name,
                                "arguments": function_args,
                                "result": result
                            })

                        # Continue the loop to get next response
                        continue
                    else:
                        # No tool calls, check if we can actually complete
                        # DeepSeek via OpenRouter sometimes returns content: null
                        # with the real text in `reasoning` — .get(key, "") does
                        # NOT protect against an explicit null
                        final_message = (assistant_message.get("content")
                                         or assistant_message.get("reasoning")
                                         or "")

                        # CRITICAL VALIDATION: Don't end without scraper code
                        if not scraper_code:
                            logger.warning("\n" + "="*60)
                            logger.warning("[PREMATURE COMPLETION DETECTED]")
                            logger.warning("Agent returned no tool calls BUT no scraper code was generated!")
                            logger.warning(f"Current iteration: {iteration + 1}/{max_iterations}")
                            logger.warning(f"Tool calls made so far: {len(tool_calls_made)}")
                            logger.warning(f"Final message: {final_message[:200]}...")
                            logger.warning("="*60)

                            # Check if this is the LAST chance (second-to-last iteration)
                            is_last_chance = (iteration + 1 >= max_iterations - 1)

                            # Force continuation by adding a prompt
                            if iteration + 1 < max_iterations:
                                if is_last_chance:
                                    # FINAL FORCE: More aggressive with template
                                    logger.error("⚠️  [FINAL FORCE] This is your LAST iteration! You MUST generate code NOW!")
                                    messages.append({
                                        "role": "user",
                                        "content": f"""⚠️ CRITICAL: This is iteration {iteration + 1}/{max_iterations} - your FINAL chance to generate code!

You MUST immediately generate scraper code, even if incomplete. Use this minimal template if needed:

```python
from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
import json

@browser(headless=True, block_images=True)
def scrape_data(driver: AntiDetectDriver, data):
    driver.get(data['url'])
    driver.short_random_sleep()

    results = []

    # TODO: Use selectors from your analysis
    # Replace '.product' with actual container selector
    items = driver.find_elements(By.CSS_SELECTOR, '.product')

    for item in items:
        try:
            result = {{
                'title': item.find_element(By.CSS_SELECTOR, 'h2').text,
                # Add more fields as needed
            }}
            results.append(result)
        except:
            continue

    return results

if __name__ == "__main__":
    results = scrape_data({{'url': '{target_url}'}})
    print(json.dumps(results, indent=2))
```

REQUIRED ACTIONS (in this exact order):
1. Call write_scraper_code(script_name="scraper.py", script_content="<COMPLETE CODE HERE>")
2. Call test_scraper(script_name="scraper.py")

DO NOT return without calling write_scraper_code! Generate code NOW based on your analysis so far."""
                                    })
                                else:
                                    # Regular continuation message
                                    logger.info("[FORCING CONTINUATION] Adding instruction to generate code")
                                    messages.append({
                                        "role": "user",
                                        "content": "You have not yet generated and written the scraper code. Please use the tools to analyze the website, generate the code using write_scraper_code, and test it using test_scraper before completing."
                                    })
                                continue
                            else:
                                logger.error("[MAX ITERATIONS] Cannot continue, returning failure")
                                result = GenerationResult(
                                    success=False,
                                    message="Generation completed without producing scraper code after maximum iterations",
                                    scraper_id=scraper_id,
                                    scraper_code=None,
                                    test_results=None,
                                    analysis=analysis,
                                    final_message=final_message,
                                    tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_made],
                                    reasoning_log=[ReasoningEntry(**re) for re in reasoning_log],
                                    iterations=iteration + 1
                                )
                                return result.model_dump()

                        # Valid completion: we have scraper code
                        logger.info("\n" + "="*80)
                        logger.info("[GENERATION COMPLETE]")
                        logger.info(f"Total Iterations: {iteration + 1}")
                        logger.info(f"Tool Calls Made: {len(tool_calls_made)}")
                        logger.info(f"Reasoning Entries: {len(reasoning_log)}")
                        logger.info(f"Scraper Code Generated: YES")
                        logger.info(f"  Code Length: {len(scraper_code)} characters")
                        logger.info(f"Test Results Available: {'YES' if test_results else 'NO'}")
                        logger.info("="*80)

                        # Convert test_results dict to TestResult if it exists
                        test_result_obj = None
                        if test_results:
                            test_result_obj = TestResult(
                                success=test_results.get("success", False),
                                message=test_results.get("message"),
                                stdout=test_results.get("stdout"),
                                stderr=test_results.get("stderr"),
                                data_extracted=test_results.get("data_extracted"),
                                record_count=test_results.get("record_count", 0)
                            )

                        result = GenerationResult(
                            success=True,
                            message="Generation completed successfully",
                            scraper_id=scraper_id,
                            scraper_code=scraper_code,
                            test_results=test_result_obj,
                            analysis=analysis,
                            final_message=final_message,
                            tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_made],
                            reasoning_log=[ReasoningEntry(**re) for re in reasoning_log],
                            iterations=iteration + 1
                        )
                        return result.model_dump()

                # Hit max iterations
                logger.warning("\n" + "="*80)
                logger.warning("[GENERATION INCOMPLETE] Maximum iterations reached")
                logger.warning(f"Iterations Used: {max_iterations}")
                logger.warning(f"Tool Calls Made: {len(tool_calls_made)}")
                logger.warning(f"Scraper Code Generated: {'YES' if scraper_code else 'NO'}")
                logger.warning("="*80)

                # Convert test_results dict to TestResult if it exists
                test_result_obj = None
                if test_results:
                    test_result_obj = TestResult(
                        success=test_results.get("success", False),
                        message=test_results.get("message"),
                        stdout=test_results.get("stdout"),
                        stderr=test_results.get("stderr"),
                        data_extracted=test_results.get("data_extracted"),
                        record_count=test_results.get("record_count", 0)
                    )

                result = GenerationResult(
                    success=True if scraper_code else False,
                    message="Maximum iterations reached without generating code" if not scraper_code else "Maximum iterations reached",
                    scraper_id=scraper_id,
                    scraper_code=scraper_code,
                    test_results=test_result_obj,
                    analysis=analysis,
                    final_message="",
                    tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_made],
                    reasoning_log=[ReasoningEntry(**re) for re in reasoning_log],
                    iterations=max_iterations
                )
                return result.model_dump()

        except httpx.HTTPError as e:
            logger.error("\n" + "="*80)
            logger.error("[GENERATION FAILED] OpenRouter API Error")
            logger.error(f"Error Type: {type(e).__name__}")
            logger.error(f"Error Message: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"HTTP Status: {e.response.status_code}")
                logger.error(f"Response Body: {e.response.text[:500]}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error("="*80)

            # Convert test_results dict to TestResult if it exists
            test_result_obj = None
            if test_results:
                test_result_obj = TestResult(
                    success=test_results.get("success", False),
                    message=test_results.get("message"),
                    stdout=test_results.get("stdout"),
                    stderr=test_results.get("stderr"),
                    data_extracted=test_results.get("data_extracted"),
                    record_count=test_results.get("record_count", 0)
                )

            result = GenerationResult(
                success=False,
                message=f"OpenRouter API error: {str(e)}",
                scraper_id=scraper_id,
                scraper_code=scraper_code,
                test_results=test_result_obj,
                analysis=analysis,
                final_message="",
                tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_made],
                reasoning_log=[ReasoningEntry(**re) for re in reasoning_log],
                iterations=0
            )
            return result.model_dump()

        except Exception as e:
            logger.error("\n" + "="*80)
            logger.error("[GENERATION FAILED] Unexpected Error")
            logger.error(f"Error Type: {type(e).__name__}")
            logger.error(f"Error Message: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error("="*80)

            # Convert test_results dict to TestResult if it exists
            test_result_obj = None
            if test_results:
                test_result_obj = TestResult(
                    success=test_results.get("success", False),
                    message=test_results.get("message"),
                    stdout=test_results.get("stdout"),
                    stderr=test_results.get("stderr"),
                    data_extracted=test_results.get("data_extracted"),
                    record_count=test_results.get("record_count", 0)
                )

            result = GenerationResult(
                success=False,
                message=f"Agent error: {str(e)}",
                scraper_id=scraper_id,
                scraper_code=scraper_code,
                test_results=test_result_obj,
                analysis=analysis,
                final_message="",
                tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_made],
                reasoning_log=[ReasoningEntry(**re) for re in reasoning_log],
                iterations=0
            )
            return result.model_dump()
