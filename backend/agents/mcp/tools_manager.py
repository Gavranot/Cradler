"""
MCP Tools Manager

Aggregates and manages all MCP tools for agent access.
Provides unified interface for browser control, network analysis, DOM analysis,
file operations, and Context7 documentation.

Implements automatic state injection - programmatically available parameters
(session_id, user_id, scraper_id) are automatically injected into tool calls.
"""
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup, Comment
from .browser_control import BrowserControlTool
from .network_analysis import NetworkAnalysisTool
from .dom_analysis import DOMAnalysisTool
from .file_system import FileSystemTool
from .context7_client import Context7Client
from .reduction import build_fragment, extract_structured, cross_check
from .reduction.listing import mine_listing
from .reduction.reduce import reduce_html
from .reduction.tokens import count_tokens

logger = logging.getLogger(__name__)


def _truncate_tokens(text: str, budget: int) -> str:
    """Hard-cap a string at ~budget tokens (escalation path safety valve)."""
    tokens = count_tokens(text)
    if tokens <= budget:
        return text
    keep = int(len(text) * budget / tokens)
    return text[:keep] + f"\n<!-- TRUNCATED at ~{budget} tokens (page had {tokens:,}) -->"


class GenerationSession:
    """
    Tracks state for a single scraper generation session

    Automatically manages browser sessions and caches data across tool calls.
    """
    def __init__(self, generation_id: str, user_id: str, scraper_id: str):
        self.generation_id = generation_id
        self.user_id = user_id
        self.scraper_id = scraper_id
        self.browser_session_id: Optional[str] = None
        self.html_content: Optional[str] = None   # L1-reduced FULL html (DOM tools)
        self.raw_html: Optional[str] = None       # untouched page source (validation)
        self.page_url: Optional[str] = None
        self.fragment = None                      # ReducedFragment routed to the LLM
        self.created_at = datetime.utcnow()

    def __repr__(self):
        return f"GenerationSession(id={self.generation_id}, user={self.user_id}, scraper={self.scraper_id})"


class MCPToolsManager:
    """
    Central manager for all MCP tools with automatic state injection

    Provides unified access to browser control, network analysis,
    DOM analysis, file system operations, and Context7 documentation for agents.

    Features:
    - Automatic browser session creation and management
    - Auto-injection of session_id, user_id, scraper_id into tool calls
    - HTML caching for DOM analysis
    - Stateful generation sessions
    """

    def __init__(self, base_scrapers_dir: str = "scrapers"):
        self.browser = BrowserControlTool()
        self.network = NetworkAnalysisTool()
        self.dom = DOMAnalysisTool()
        self.filesystem = FileSystemTool(base_scrapers_dir)
        self.context7 = Context7Client()

        # State management
        self.generation_sessions: Dict[str, GenerationSession] = {}
        self.current_generation_id: Optional[str] = None

    def initialize_generation(self, user_id: str, scraper_id: str) -> str:
        """
        Initialize a new generation session

        Args:
            user_id: User identifier
            scraper_id: Scraper identifier

        Returns:
            generation_id: Unique identifier for this generation session
        """
        generation_id = str(uuid.uuid4())
        session = GenerationSession(generation_id, user_id, scraper_id)
        self.generation_sessions[generation_id] = session
        self.current_generation_id = generation_id

        logger.info(f"[STATE] Initialized generation session: {session}")
        return generation_id

    def get_current_session(self) -> Optional[GenerationSession]:
        """Get the current generation session"""
        if self.current_generation_id:
            return self.generation_sessions.get(self.current_generation_id)
        return None

    def _remove_boilerplate(self, html: str) -> str:
        """Universal HTML reduction (Layer 1 of the reduction pipeline).

        Replaces the old BeautifulSoup cleaner, which stripped ALL <script>/<meta>
        (destroying JSON-LD/OpenGraph before Layer 0 could read them) and deleted
        breadcrumbs with the nav bar. See agents/mcp/reduction/reduce.py.
        NOTE: callers that need structured data must probe the RAW html first.
        """
        result = reduce_html(html)
        reduction_pct = 100 * (len(html) - len(result.html)) / len(html) if html else 0
        logger.info(f"[REDUCTION-L1] {len(html) - len(result.html):,} chars removed "
                    f"({reduction_pct:.1f}%)")
        return result.html

    async def _ensure_browser_session(self, session: GenerationSession) -> str:
        """
        Ensure browser session exists, create if needed

        Args:
            session: Generation session

        Returns:
            browser_session_id: Browser session identifier
        """
        if session.browser_session_id:
            return session.browser_session_id

        # Create new browser session
        browser_session_id = f"browser_{session.generation_id}"
        result = await self.browser.create_session(
            session_id=browser_session_id,
            headless=True,
            block_images=False
        )

        if result.get("success"):
            session.browser_session_id = browser_session_id
            logger.info(f"[STATE] Auto-created browser session: {browser_session_id}")
        else:
            logger.error(f"[STATE] Failed to create browser session: {result.get('message')}")
            raise Exception(f"Failed to create browser session: {result.get('message')}")

        return browser_session_id

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get OpenAI function calling definitions for all MCP tools

        NOTE: session_id, user_id, and scraper_id are automatically injected
        and do not need to be provided by the agent.

        Returns:
            List of tool definitions compatible with OpenAI/OpenRouter API
        """
        return [
            # Browser Control Tools
            {
                "type": "function",
                "function": {
                    "name": "browser_navigate",
                    "description": (
                        "Navigate to a URL in the browser. This is typically the FIRST tool you should call. "
                        "Browser session is created automatically on first use. "
                        "Use this to load the target website before analyzing its structure."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Target URL to navigate to"
                            },
                            "bypass_cloudflare": {
                                "type": "boolean",
                                "description": "Use Cloudflare bypass techniques (set to true if site uses Cloudflare)",
                                "default": False
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_get_page_source",
                    "description": (
                        "Get a REDUCED view of the current page, plus any machine-readable "
                        "product data (JSON-LD/microdata) found on it. "
                        "PREREQUISITE: Must call browser_navigate first. "
                        "\n\n"
                        "Returns:\n"
                        "- structured_data: cross-checked product fields from JSON-LD/microdata "
                        "(if present, prefer these over HTML scraping — they are what the site "
                        "itself renders from)\n"
                        "- fragment: listing pages → ONE exemplar product card + record count + "
                        "container/record selectors (write field selectors relative to the card); "
                        "detail pages → anchored DOM slices around title/price/image/etc. with "
                        "missing anchors reported\n"
                        "- notes: what reduction did, so you know what was removed\n"
                        "\n"
                        "The full page stays cached for DOM analysis tools. If the fragment lacks "
                        "a node you need, call again with full=true to get the full (reduced) page."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "full": {
                                "type": "boolean",
                                "description": "Escalation: return the full reduced page instead of the routed fragment (token-capped). Use only when the fragment is missing something.",
                                "default": False
                            }
                        },
                        "required": []
                    }
                }
            },
            # DOM Analysis Tools
            {
                "type": "function",
                "function": {
                    "name": "dom_suggest_selectors",
                    "description": (
                        "Suggest CSS selectors for a data field using multi-tier validation strategy. "
                        "PREREQUISITE: Must call browser_get_page_source first. "
                        "\n\n"
                        "Tests selectors in PRIORITY ORDER and validates each:\n"
                        "1. Data attributes (data-*) - Highest stability\n"
                        "2. ARIA attributes (aria-label, role) - High stability\n"
                        "3. Semantic HTML + Schema.org - Medium-high stability\n"
                        "4. Semantic classes (.price, .title) - Medium stability\n"
                        "5. Partial class matching ([class*='price']) - For obfuscated classes\n"
                        "6. Content-based matching - Last resort\n"
                        "\n"
                        "Returns VALIDATED strategies ranked by priority and confidence. "
                        "Each strategy includes: selector, type, priority, confidence, match count, validation status. "
                        "Call this for EACH data field you need to extract."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field_name": {
                                "type": "string",
                                "description": "Field name: price, title, image, description, rating, availability, sku, etc."
                            },
                            "sample_value": {
                                "type": "string",
                                "description": "Optional sample value to validate matches (e.g., '$19.99' for price). Highly recommended for accuracy."
                            }
                        },
                        "required": ["field_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "dom_analyze_structure",
                    "description": (
                        "Analyze page structure with anti-scraping detection and attribute usage analysis. "
                        "PREREQUISITE: Must call browser_get_page_source first. "
                        "\n\n"
                        "Detects:\n"
                        "- Layout patterns (data-testid grid, semantic schema, web components, standard grid)\n"
                        "- Anti-scraping measures (honeypots, class obfuscation level, Shadow DOM)\n"
                        "- Attribute usage (data-*, ARIA, semantic HTML availability)\n"
                        "- Lists, tables, repeating patterns\n"
                        "\n"
                        "Returns RECOMMENDATION for which selector strategy to prioritize based on page structure. "
                        "IMPORTANT: Call this BEFORE dom_suggest_selectors to understand the page's characteristics "
                        "and choose the optimal selector approach."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "dom_detect_product_containers",
                    "description": (
                        "Detect product container elements using multi-phase pattern recognition. "
                        "PREREQUISITE: Must call browser_get_page_source first. "
                        "\n\n"
                        "Strategy (in order):\n"
                        "1. Generic e-commerce selectors (Schema.org, data-testid, common classes)\n"
                        "2. Repeating pattern detection (class frequency analysis)\n"
                        "3. Content-based heuristics (elements with image + link + price)\n"
                        "\n"
                        "Returns selector with VALIDATION METRICS:\n"
                        "- Confidence score (0-1) based on image/link/price presence\n"
                        "- Match count\n"
                        "- Sample HTML of one product container\n"
                        "\n"
                        "If success=false, no patterns found - use dom_chunk_html for fallback."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "dom_chunk_html",
                    "description": (
                        "Chunk HTML semantically when product detection fails. "
                        "PREREQUISITE: Must call browser_get_page_source first. "
                        "Returns list of HTML chunks preserving DOM structure. "
                        "Use this when dom_detect_product_containers returns success=false. "
                        "Feed chunks iteratively to analyze which contains product data."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_chunk_length": {
                                "type": "integer",
                                "description": "Maximum characters per chunk (default: 2000)",
                                "default": 2000
                            }
                        },
                        "required": []
                    }
                }
            },
            # File System Tools
            {
                "type": "function",
                "function": {
                    "name": "write_scraper_code",
                    "description": (
                        "Write generated scraper code to a file in the isolated scraper directory. "
                        "Use this after you've analyzed the page and determined the selectors. "
                        "The code should be complete, executable Python using Botasaurus framework."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script_name": {
                                "type": "string",
                                "description": "Name of the script file (e.g., 'scraper.py')"
                            },
                            "script_content": {
                                "type": "string",
                                "description": "Complete Python code for the scraper with imports, decorators, and main block"
                            }
                        },
                        "required": ["script_name", "script_content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "test_scraper",
                    "description": (
                        "Execute the generated scraper to test if it works correctly. "
                        "PREREQUISITE: Must call write_scraper_code first. "
                        "Returns execution results including stdout, stderr, and extracted data. "
                        "This is the FINAL step to validate your scraper works."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script_name": {
                                "type": "string",
                                "description": "Name of the script file to execute (same as used in write_scraper_code)"
                            }
                        },
                        "required": ["script_name"]
                    }
                }
            },
            # Context7 Documentation Tools
            {
                "type": "function",
                "function": {
                    "name": "context7_get_botasaurus_docs",
                    "description": "Fetch up-to-date Botasaurus framework documentation from Context7. "
                                 "Use this to get current API references, decorator usage, driver methods, "
                                 "and best practices for Botasaurus web scraping.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Optional specific topic to focus on (e.g., 'decorators', 'driver methods', 'selectors', 'anti-detection')",
                                "default": None
                            },
                            "tokens": {
                                "type": "integer",
                                "description": "Maximum tokens of documentation to retrieve (default: 10000)",
                                "default": 10000
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "context7_get_library_docs",
                    "description": "Fetch up-to-date documentation for any library from Context7. "
                                 "First resolve the library ID, then use this to get documentation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "library_name": {
                                "type": "string",
                                "description": "Name of the library (e.g., 'BeautifulSoup', 'lxml', 'selenium')"
                            },
                            "topic": {
                                "type": "string",
                                "description": "Optional specific topic to focus on",
                                "default": None
                            },
                            "tokens": {
                                "type": "integer",
                                "description": "Maximum tokens of documentation to retrieve (default: 8000)",
                                "default": 8000
                            }
                        },
                        "required": ["library_name"]
                    }
                }
            }
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool by name with provided arguments

        Automatically injects session_id, user_id, and scraper_id based on
        current generation session state.

        Args:
            tool_name: Name of the tool function
            arguments: Tool arguments (without auto-injected params)

        Returns:
            Tool execution result
        """
        logger.debug(f"[TOOLS MANAGER] Executing tool: {tool_name}")
        logger.debug(f"[TOOLS MANAGER] Arguments (before injection): {arguments}")

        # Get current session
        session = self.get_current_session()
        if not session:
            return {
                "success": False,
                "message": "No active generation session. Call initialize_generation first."
            }

        # Browser Control Tools - Auto-inject session_id
        if tool_name == "browser_navigate":
            # Ensure browser session exists (create if needed)
            browser_session_id = await self._ensure_browser_session(session)
            logger.info(f"[STATE] Auto-injected browser_session_id: {browser_session_id}")

            return await self.browser.navigate(
                session_id=browser_session_id,
                url=arguments["url"],
                wait_for_load=True,
                bypass_cloudflare=arguments.get("bypass_cloudflare", False)
            )

        elif tool_name == "browser_get_page_source":
            if not session.browser_session_id:
                return {
                    "success": False,
                    "message": "Browser session not initialized. Call browser_navigate first."
                }

            logger.info(f"[STATE] Auto-injected browser_session_id: {session.browser_session_id}")
            result = await self.browser.get_page_source(session_id=session.browser_session_id)

            # Cache HTML for DOM analysis
            if result.get("success") and "html" in result:
                raw_html = result["html"]
                page_url = result.get("url") or session.page_url or ""

                # L0 must see the RAW html — cleaning strips JSON-LD/meta
                session.raw_html = raw_html
                session.page_url = page_url

                # L0 + L1 + L2 routing → fragment for the LLM
                fragment = build_fragment(raw_html, page_url)
                session.fragment = fragment

                # Cache the L1-reduced FULL page for DOM analysis tools
                reduced_full = reduce_html(raw_html).html
                session.html_content = reduced_full
                await self.dom.parse_html(session.browser_session_id, reduced_full)

                logger.info(
                    f"[REDUCTION] {page_url}: raw {len(raw_html):,} chars → "
                    f"fragment {fragment.est_tokens:,} tokens "
                    f"(layer={fragment.source_layer}, type={fragment.page_type})")

                # structured-data summary (only cross-check-passing values)
                sd = fragment.l0
                structured = {}
                if sd is not None and sd.product:
                    structured = {k: v for k, v in sd.product.items() if v not in (None, "", [])}
                del result["html"]
                if arguments.get("full"):
                    text = _truncate_tokens(reduced_full, 24000)
                    result["fragment"] = text
                    result["fragment_kind"] = "full-reduced (escalated)"
                else:
                    result["fragment"] = fragment.text
                    result["fragment_kind"] = f"{fragment.page_type}/{fragment.source_layer}"
                result["structured_data"] = structured
                result["structured_data_cross_check"] = fragment.l0_cross_check
                result["page_type"] = fragment.page_type
                if fragment.listing_meta:
                    result["listing"] = fragment.listing_meta
                if fragment.anchors_found:
                    result["anchors_found"] = fragment.anchors_found
                result["notes"] = fragment.notes[-6:]
                result["original_length"] = len(raw_html)

            return result

        # DOM Analysis Tools - Auto-inject session_id and use cached HTML
        elif tool_name == "dom_suggest_selectors":
            if not session.html_content:
                return {
                    "success": False,
                    "message": "HTML not cached. Call browser_get_page_source first."
                }

            logger.info(f"[STATE] Auto-injected browser_session_id: {session.browser_session_id}")
            logger.info(f"[STATE] Using cached HTML ({len(session.html_content)} chars)")

            return await self.dom.suggest_selectors_for_field(
                session_id=session.browser_session_id,
                field_name=arguments["field_name"],
                sample_value=arguments.get("sample_value")
            )

        elif tool_name == "dom_analyze_structure":
            if not session.html_content:
                return {
                    "success": False,
                    "message": "HTML not cached. Call browser_get_page_source first."
                }

            logger.info(f"[STATE] Auto-injected browser_session_id: {session.browser_session_id}")
            logger.info(f"[STATE] Using cached HTML ({len(session.html_content)} chars)")

            return await self.dom.analyze_structure(session_id=session.browser_session_id)

        elif tool_name == "dom_detect_product_containers":
            if not session.html_content:
                return {
                    "success": False,
                    "message": "HTML not cached. Call browser_get_page_source first."
                }

            logger.info(f"[STATE] Auto-injected browser_session_id: {session.browser_session_id}")
            logger.info(f"[STATE] Using cached HTML ({len(session.html_content)} chars)")

            # Primary: tag-path fingerprint mining (class-obfuscation-proof,
            # precision-checked selectors). Legacy heuristic kept as fallback.
            try:
                extract = mine_listing(session.html_content)
            except Exception as e:  # noqa: BLE001 - never let mining kill the loop
                logger.warning(f"[PRODUCT DETECTION] fingerprint mining failed: {e}")
                extract = None
            if extract is not None:
                return {
                    "success": True,
                    "method": "tag_path_fingerprint",
                    # "corroborated" = price/image signals confirmed in cards;
                    # "unconfirmed" = strongest repeated linked structure, but the
                    # agent must inspect sample_html and DECIDE whether these are
                    # product records (heuristics rank, only the LLM rejects)
                    "confidence": extract.confidence,
                    "signal_stats": extract.stats,
                    "selector": f"{extract.container_css} > {extract.record_css}",
                    "container_css": extract.container_css,
                    "record_css": extract.record_css,
                    "count": extract.record_count,
                    "sample_html": extract.exemplar_html[:4000],
                    "second_variant_html": (extract.second_exemplar_html or "")[:2000] or None,
                    "notes": extract.notes,
                }
            legacy = await self.dom.detect_product_containers(
                session_id=session.browser_session_id)
            if legacy.get("success"):
                legacy["notes"] = ["fingerprint mining found no plausible grid; "
                                   "this result is from the legacy class-frequency "
                                   "heuristic — validate before trusting"]
                return legacy
            return {
                "success": False,
                "message": ("No plausible product grid found. If this page should "
                            "have one, it is likely client-rendered — the grid may "
                            "need scrolling/waiting at fetch time."),
            }

        elif tool_name == "dom_chunk_html":
            if not session.html_content:
                return {
                    "success": False,
                    "message": "HTML not cached. Call browser_get_page_source first."
                }

            logger.info(f"[STATE] Auto-injected browser_session_id: {session.browser_session_id}")
            logger.info(f"[STATE] Using cached HTML ({len(session.html_content)} chars)")

            return await self.dom.chunk_html_for_llm(
                session_id=session.browser_session_id,
                max_chunk_length=arguments.get("max_chunk_length", 2000)
            )

        # File System Tools - Auto-inject user_id and scraper_id
        elif tool_name == "write_scraper_code":
            logger.info(f"[STATE] Auto-injected user_id: {session.user_id}")
            logger.info(f"[STATE] Auto-injected scraper_id: {session.scraper_id}")

            return await self.filesystem.write_scraper_script(
                user_id=session.user_id,
                scraper_id=session.scraper_id,
                script_name=arguments["script_name"],
                script_content=arguments["script_content"]
            )

        elif tool_name == "test_scraper":
            logger.info(f"[STATE] Auto-injected user_id: {session.user_id}")
            logger.info(f"[STATE] Auto-injected scraper_id: {session.scraper_id}")

            return await self.filesystem.execute_scraper(
                user_id=session.user_id,
                scraper_id=session.scraper_id,
                script_name=arguments["script_name"]
            )

        # Context7 Documentation - No injection needed
        elif tool_name == "context7_get_botasaurus_docs":
            return await self.context7.get_botasaurus_docs(
                topic=arguments.get("topic"),
                tokens=arguments.get("tokens", 10000)
            )

        elif tool_name == "context7_get_library_docs":
            # Resolve library ID first, then fetch docs
            library_name = arguments["library_name"]
            resolution = await self.context7.resolve_library_id(library_name)

            if not resolution.get("success"):
                return resolution

            library_id = resolution.get("library_id")
            if not library_id:
                return {
                    "success": False,
                    "message": f"Could not resolve library ID for: {library_name}"
                }

            return await self.context7.get_library_docs(
                library_id=library_id,
                topic=arguments.get("topic"),
                tokens=arguments.get("tokens", 8000)
            )

        else:
            return {
                "success": False,
                "message": f"Unknown tool: {tool_name}"
            }
