# MCP Tools Implementation Guide

**Last Updated:** 2025-01-13

Detailed implementation examples for all MCP (Model Context Protocol) tools used by Secondary Agent.

---

## Overview

The Secondary Agent uses 10 MCP tools to analyze websites and generate scraping code:

1. **Browser Control** (2 tools) - Navigate, get page source
2. **DOM Analysis** (4 tools) - Parse HTML, suggest selectors, detect patterns
3. **File System** (2 tools) - Write/test scraper scripts
4. **Context7 Documentation** (2 tools) - Fetch up-to-date library docs

All tools implement **Level 3 Directory Isolation** for security.

**Phase 2 (Not Implemented):**
- **Network Analysis** - Monitor traffic, detect APIs (requires CDP integration)

---

## Tool 1: Browser Control

**File:** `backend/agents/mcp/browser_control.py`

### Purpose
Launch and control browsers using Botasaurus for page analysis.

### Implementation

```python
from botasaurus_driver import Driver
from typing import Dict, Any, Optional

class BrowserControl:
    def __init__(self):
        self.sessions = {}  # session_id -> Driver instance

    def create_session(
        self,
        session_id: str,
        headless: bool = True,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        block_images: bool = False
    ) -> Dict[str, Any]:
        """Create browser session with anti-detection"""

        driver = Driver(
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            block_images=block_images,
            beep=False
        )

        self.sessions[session_id] = driver

        return {
            "session_id": session_id,
            "status": "created"
        }

    def navigate(
        self,
        session_id: str,
        url: str,
        bypass_cloudflare: bool = False
    ) -> Dict[str, Any]:
        """Navigate to URL with optional Cloudflare bypass"""

        driver = self.sessions[session_id]

        if bypass_cloudflare:
            driver.google_get(url, bypass_cloudflare=True)
        else:
            driver.get(url)

        driver.short_random_sleep()  # Anti-detection

        return {
            "status": "success",
            "url": driver.current_url,
            "title": driver.title
        }

    def screenshot(
        self,
        session_id: str,
        path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Capture screenshot for analysis"""

        driver = self.sessions[session_id]
        driver.save_screenshot()  # Saves to output/ directory

        return {
            "status": "success",
            "path": "output/screenshot.png"
        }

    def get_page_source(self, session_id: str) -> Dict[str, Any]:
        """Extract HTML source"""

        driver = self.sessions[session_id]
        html = driver.page_html

        return {
            "status": "success",
            "html": html,
            "length": len(html)
        }

    def execute_script(
        self,
        session_id: str,
        script: str
    ) -> Dict[str, Any]:
        """Execute JavaScript in browser context"""

        driver = self.sessions[session_id]
        result = driver.run_js(script)

        return {
            "status": "success",
            "result": result
        }

    def check_bot_detection(self, session_id: str) -> Dict[str, Any]:
        """Detect if bot measures triggered"""

        driver = self.sessions[session_id]
        is_detected = driver.is_bot_detected()

        return {
            "detected": is_detected,
            "current_url": driver.current_url
        }

    def close_session(self, session_id: str) -> Dict[str, Any]:
        """Close browser and cleanup"""

        driver = self.sessions.pop(session_id)
        driver.close()

        return {"status": "closed"}
```

### Key Botasaurus Methods

- `driver.get(url)` - Navigate to URL
- `driver.google_get(url, bypass_cloudflare=True)` - Navigate with Google referrer
- `driver.page_html` - Get page source
- `driver.run_js(script)` - Execute JavaScript
- `driver.short_random_sleep()` - Human-like delay
- `driver.is_bot_detected()` - Check for anti-bot measures
- `driver.save_screenshot()` - Capture screenshot
- `driver.close()` - Cleanup

---

## Tool 2: Network Analysis

**Status:** ⚠️ **NOT IMPLEMENTED - Phase 2**

**File:** `backend/agents/mcp/network_analysis.py`

### Purpose
Monitor network traffic to detect API endpoints and data sources.

**Note:** This tool is currently a skeleton. CDP (Chrome DevTools Protocol) integration is required to capture network traffic. The class structure exists but the tools are not exposed to the Secondary Agent in Phase 1.

### Implementation

```python
from typing import Dict, Any, List

class NetworkAnalysis:
    def __init__(self):
        self.sessions = {}  # session_id -> network logs

    def start_monitoring(self, session_id: str) -> Dict[str, Any]:
        """Begin capturing network traffic"""

        self.sessions[session_id] = {
            "logs": [],
            "monitoring": True
        }

        # Register CDP response handler
        # (Implementation depends on Botasaurus CDP integration)

        return {"status": "monitoring_started"}

    def get_api_calls(self, session_id: str) -> Dict[str, Any]:
        """Extract XHR/Fetch requests"""

        logs = self.sessions[session_id]["logs"]

        api_calls = [
            log for log in logs
            if log.get("type") in ["xhr", "fetch"]
        ]

        return {
            "api_calls": api_calls,
            "count": len(api_calls)
        }

    def detect_data_endpoints(self, session_id: str) -> Dict[str, Any]:
        """Find endpoints returning JSON data"""

        logs = self.sessions[session_id]["logs"]

        data_endpoints = [
            {
                "url": log["url"],
                "method": log.get("method", "GET"),
                "response_type": log.get("response_type")
            }
            for log in logs
            if log.get("response_type") == "application/json"
        ]

        return {
            "endpoints": data_endpoints,
            "count": len(data_endpoints)
        }

    def export_har(self, session_id: str) -> Dict[str, Any]:
        """Export network logs as HAR format"""

        logs = self.sessions[session_id]["logs"]

        # Convert to HAR using chrome-har library
        # har_data = convert_to_har(logs)

        return {
            "status": "exported",
            "entries": len(logs)
        }

    def detect_pagination(self, session_id: str) -> Dict[str, Any]:
        """Identify pagination patterns in requests"""

        logs = self.sessions[session_id]["logs"]

        # Look for common pagination parameters
        pagination_indicators = ["page=", "offset=", "limit=", "skip="]

        paginated_requests = [
            log for log in logs
            if any(ind in log["url"] for ind in pagination_indicators)
        ]

        return {
            "has_pagination": len(paginated_requests) > 0,
            "requests": paginated_requests
        }
```

---

## Tool 3: DOM Analysis

**File:** `backend/agents/mcp/dom_analysis.py`

### Purpose
Parse HTML structure and suggest optimal CSS selectors.

### Implementation

```python
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional

class DOMAnalysis:
    def __init__(self):
        self.html_cache = {}  # session_id -> HTML

    def suggest_selectors_for_field(
        self,
        session_id: str,
        field_name: str,
        html: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find optimal CSS selectors for specific data field"""

        if html is None:
            html = self.html_cache.get(session_id)

        soup = BeautifulSoup(html, 'lxml')

        # Field-specific patterns
        patterns = self._get_field_patterns(field_name)

        suggestions = []

        for pattern in patterns:
            elements = soup.select(pattern["selector"])

            if elements:
                suggestions.append({
                    "selector": pattern["selector"],
                    "confidence": pattern["confidence"],
                    "matches": len(elements),
                    "sample": elements[0].get_text(strip=True)[:100]
                })

        return {
            "field_name": field_name,
            "suggestions": suggestions,
            "recommended": suggestions[0] if suggestions else None
        }

    def _get_field_patterns(self, field_name: str) -> List[Dict]:
        """Get field-specific selector patterns"""

        patterns = {
            "title": [
                {"selector": "h1", "confidence": 0.9},
                {"selector": "[itemprop='name']", "confidence": 0.95},
                {"selector": ".product-title", "confidence": 0.8},
                {"selector": ".title", "confidence": 0.7}
            ],
            "price": [
                {"selector": "[itemprop='price']", "confidence": 0.95},
                {"selector": ".price", "confidence": 0.8},
                {"selector": ".product-price", "confidence": 0.85},
                {"selector": "span[class*='price']", "confidence": 0.75}
            ],
            "image": [
                {"selector": "[itemprop='image']", "confidence": 0.95},
                {"selector": ".product-image img", "confidence": 0.85},
                {"selector": "img[alt*='product']", "confidence": 0.7}
            ],
            "rating": [
                {"selector": "[itemprop='ratingValue']", "confidence": 0.95},
                {"selector": ".rating", "confidence": 0.8},
                {"selector": "[class*='star']", "confidence": 0.7}
            ]
        }

        return patterns.get(field_name.lower(), [
            {"selector": f"[data-{field_name}]", "confidence": 0.6}
        ])

    def analyze_structure(
        self,
        session_id: str,
        html: Optional[str] = None
    ) -> Dict[str, Any]:
        """Detect lists, tables, and repeating patterns"""

        if html is None:
            html = self.html_cache.get(session_id)

        soup = BeautifulSoup(html, 'lxml')

        # Detect repeating item containers
        containers = self._find_repeating_containers(soup)

        return {
            "total_elements": len(soup.find_all()),
            "containers": containers,
            "has_tables": len(soup.find_all('table')) > 0,
            "has_lists": len(soup.find_all(['ul', 'ol'])) > 0
        }

    def _find_repeating_containers(self, soup) -> List[Dict]:
        """Find elements that repeat (product cards, etc.)"""

        # Look for common container patterns
        selectors = [
            "article",
            "[class*='product']",
            "[class*='item']",
            "[class*='card']"
        ]

        containers = []

        for selector in selectors:
            elements = soup.select(selector)
            if len(elements) >= 3:  # At least 3 repeating items
                containers.append({
                    "selector": selector,
                    "count": len(elements),
                    "confidence": 0.9 if len(elements) >= 10 else 0.7
                })

        return containers

    def validate_selector(
        self,
        session_id: str,
        selector: str,
        expected_count: Optional[int] = None,
        html: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test selector accuracy"""

        if html is None:
            html = self.html_cache.get(session_id)

        soup = BeautifulSoup(html, 'lxml')
        elements = soup.select(selector)

        valid = True
        if expected_count and len(elements) != expected_count:
            valid = False

        return {
            "selector": selector,
            "valid": valid,
            "matches": len(elements),
            "expected": expected_count
        }
```

---

## Tool 4: File System

**File:** `backend/agents/mcp/file_system.py`

### Purpose
Manage scraper files with Level 3 directory isolation.

### Implementation

```python
import os
import subprocess
from pathlib import Path
from typing import Dict, Any

class FileSystem:
    def __init__(self, base_dir: str = "/app/scrapers"):
        self.base_dir = Path(base_dir)

    def _get_scraper_dir(self, user_id: str, scraper_id: str) -> Path:
        """Get isolated scraper directory"""
        return self.base_dir / user_id / scraper_id

    def _validate_path(self, path: Path) -> bool:
        """Prevent path traversal attacks"""
        resolved = path.resolve()
        return str(resolved).startswith(str(self.base_dir.resolve()))

    def create_scraper_directory(
        self,
        user_id: str,
        scraper_id: str
    ) -> Dict[str, Any]:
        """Create isolated directory for scraper"""

        scraper_dir = self._get_scraper_dir(user_id, scraper_id)

        if not self._validate_path(scraper_dir):
            raise SecurityError("Path traversal detected")

        scraper_dir.mkdir(parents=True, exist_ok=True)

        return {
            "status": "created",
            "path": str(scraper_dir)
        }

    def write_scraper_script(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str,
        script_content: str
    ) -> Dict[str, Any]:
        """Save generated scraper code"""

        # Validate script name
        if ".." in script_name or "/" in script_name or "\\" in script_name:
            raise ValueError("Invalid script name")

        scraper_dir = self._get_scraper_dir(user_id, scraper_id)
        script_path = scraper_dir / script_name

        if not self._validate_path(script_path):
            raise SecurityError("Path traversal detected")

        with open(script_path, 'w') as f:
            f.write(script_content)

        return {
            "status": "written",
            "path": str(script_path),
            "size": len(script_content)
        }

    def execute_scraper(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute scraper script with timeout"""

        scraper_dir = self._get_scraper_dir(user_id, scraper_id)
        script_path = scraper_dir / script_name

        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_name}")

        try:
            result = subprocess.run(
                ['python', str(script_path)],
                capture_output=True,
                timeout=timeout,
                text=True,
                cwd=str(scraper_dir)
            )

            return {
                "status": "success" if result.returncode == 0 else "failed",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "error": f"Script exceeded {timeout}s timeout"
            }

    def read_scraper_script(
        self,
        user_id: str,
        scraper_id: str,
        script_name: str
    ) -> Dict[str, Any]:
        """Read scraper code"""

        scraper_dir = self._get_scraper_dir(user_id, scraper_id)
        script_path = scraper_dir / script_name

        if not self._validate_path(script_path):
            raise SecurityError("Path traversal detected")

        with open(script_path, 'r') as f:
            content = f.read()

        return {
            "status": "success",
            "content": content,
            "size": len(content)
        }
```

---

## Tools Manager

**File:** `backend/agents/mcp/tools_manager.py`

### Purpose
Unified interface for all tools with automatic state injection.

### Implementation

```python
from typing import Dict, Any, List

class MCPToolsManager:
    def __init__(self):
        self.browser = BrowserControl()
        self.network = NetworkAnalysis()
        self.dom = DOMAnalysis()
        self.fs = FileSystem()
        self.sessions = {}  # generation_id -> GenerationSession

    def initialize_generation(
        self,
        user_id: str,
        scraper_id: str
    ) -> str:
        """Initialize generation session"""

        generation_id = f"{user_id}_{scraper_id}"

        self.sessions[generation_id] = GenerationSession(
            generation_id=generation_id,
            user_id=user_id,
            scraper_id=scraper_id
        )

        return generation_id

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute tool with automatic state injection"""

        # Get current generation session
        generation_id = self._get_current_generation()
        session = self.sessions[generation_id]

        # Auto-inject parameters
        if tool_name.startswith("browser_"):
            arguments["session_id"] = session.browser_session_id

        if tool_name in ["write_scraper_code", "test_scraper"]:
            arguments["user_id"] = session.user_id
            arguments["scraper_id"] = session.scraper_id

        # Route to appropriate tool
        if tool_name == "browser_navigate":
            return self.browser.navigate(**arguments)
        elif tool_name == "dom_suggest_selectors":
            return self.dom.suggest_selectors_for_field(**arguments)
        # ... other tools

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions"""

        return [
            {
                "type": "function",
                "function": {
                    "name": "browser_navigate",
                    "description": "Navigate to URL (browser session auto-created)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"}
                        },
                        "required": ["url"]
                    }
                }
            },
            # ... other 7 tools
        ]
```

---

## Security Considerations

### Path Traversal Prevention
```python
def _validate_path(self, path: Path) -> bool:
    """Ensure path stays within allowed directory"""
    resolved = path.resolve()
    return str(resolved).startswith(str(self.base_dir.resolve()))
```

### Script Name Validation
```python
if ".." in script_name or "/" in script_name or "\\" in script_name:
    raise ValueError("Invalid script name")
```

### Execution Timeout
```python
subprocess.run(..., timeout=30)  # Prevent infinite loops
```

### Resource Limits
- CPU: Containerized execution
- Memory: Docker memory limits
- Disk: Quota per user/scraper

---

## Testing Tools

### Manual Test
```python
# Initialize tools
tools_manager = MCPToolsManager()
tools_manager.initialize_generation("user123", "scraper456")

# Navigate
result = await tools_manager.execute_tool("browser_navigate", {
    "url": "https://books.toscrape.com"
})

# Analyze
result = await tools_manager.execute_tool("dom_analyze_structure", {})

# Generate code
result = await tools_manager.execute_tool("write_scraper_code", {
    "script_name": "scraper.py",
    "script_content": "from botasaurus import browser..."
})
```
