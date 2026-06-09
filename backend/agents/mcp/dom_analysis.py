"""
DOM Analysis MCP Tool

Analyzes HTML structure and finds optimal selectors for data extraction.
Integrates with BeautifulSoup for parsing and selector generation.
"""
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

try:
    from betterhtmlchunking import DomRepresentation
    from betterhtmlchunking.main import ReprLengthComparisionBy
    CHUNKING_AVAILABLE = True
except ImportError:
    CHUNKING_AVAILABLE = False
    logger.warning("[DOM ANALYSIS] betterhtmlchunking not available, chunking fallback disabled")


class DOMAnalysisTool:
    """
    MCP Tool for DOM analysis and selector generation

    Uses BeautifulSoup to parse HTML and generate optimal selectors.
    """

    def __init__(self):
        self.cached_soups: Dict[str, BeautifulSoup] = {}

    async def parse_html(
        self,
        session_id: str,
        html: str
    ) -> Dict[str, Any]:
        """
        Parse HTML and cache for analysis

        Args:
            session_id: Session identifier
            html: HTML content to parse

        Returns:
            Parse status and basic stats
        """
        try:
            soup = BeautifulSoup(html, 'lxml')
            self.cached_soups[session_id] = soup

            return {
                "success": True,
                "session_id": session_id,
                "elements_count": len(soup.find_all()),
                "message": "HTML parsed successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to parse HTML: {str(e)}"
            }

    async def find_selectors_by_text(
        self,
        session_id: str,
        target_text: str,
        fuzzy: bool = False
    ) -> Dict[str, Any]:
        """
        Find elements containing specific text and generate selectors

        Args:
            session_id: Session identifier
            target_text: Text to search for
            fuzzy: Use fuzzy matching

        Returns:
            List of selectors for matching elements
        """
        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        soup = self.cached_soups[session_id]
        selectors = []

        # Find elements containing the text
        if fuzzy:
            elements = soup.find_all(string=re.compile(re.escape(target_text), re.I))
        else:
            elements = soup.find_all(string=lambda text: target_text in text if text else False)

        for elem_text in elements[:10]:  # Limit to first 10 matches
            parent = elem_text.parent
            selector = self._generate_css_selector(parent)
            selectors.append({
                "selector": selector,
                "xpath": self._generate_xpath(parent),
                "tag": parent.name,
                "text": elem_text.strip()[:100]
            })

        return {
            "success": True,
            "session_id": session_id,
            "target_text": target_text,
            "selectors": selectors,
            "count": len(selectors)
        }

    async def suggest_selectors_for_field(
        self,
        session_id: str,
        field_name: str,
        sample_value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggest selectors for a data field using multi-tier validation strategy

        Tests selectors in priority order and validates each:
        1. Data attributes (highest stability)
        2. ARIA attributes
        3. Semantic HTML + Schema.org
        4. Semantic classes
        5. Partial class matching (obfuscated classes)
        6. Content-based matching (fallback)

        Args:
            session_id: Session identifier
            field_name: Field name (e.g., "price", "title", "image")
            sample_value: Optional sample value to validate matches

        Returns:
            List of validated selector strategies ranked by priority and confidence
        """
        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        soup = self.cached_soups[session_id]
        strategies = []

        # Field-specific selector patterns (organized by tier)
        field_patterns = self._get_field_patterns(field_name.lower())

        # TIER 1: Data attributes (priority 1, highest stability)
        for data_attr in field_patterns.get("data_attrs", []):
            selector = f"[data-{data_attr}]"
            strategy = self._validate_selector(soup, selector, "data_attribute", 1, 0.95, sample_value, field_name)
            if strategy:
                strategies.append(strategy)

        # TIER 2: ARIA attributes (priority 2)
        for aria_pattern in field_patterns.get("aria_patterns", []):
            selector = f"[aria-label*='{aria_pattern}' i]"
            strategy = self._validate_selector(soup, selector, "aria_attribute", 2, 0.85, sample_value, field_name)
            if strategy:
                strategies.append(strategy)

        # TIER 3: Semantic HTML + Schema.org (priority 3)
        for semantic_selector in field_patterns.get("semantic_selectors", []):
            strategy = self._validate_selector(soup, semantic_selector, "semantic_html", 3, 0.80, sample_value, field_name)
            if strategy:
                strategies.append(strategy)

        # TIER 4: Semantic classes (priority 4)
        for class_name in field_patterns.get("semantic_classes", []):
            selector = f".{class_name}"
            strategy = self._validate_selector(soup, selector, "semantic_class", 4, 0.70, sample_value, field_name)
            if strategy:
                strategies.append(strategy)

        # TIER 5: Partial class matching for obfuscated classes (priority 5)
        for class_pattern in field_patterns.get("class_patterns", []):
            selector = f"[class*='{class_pattern}' i]"
            strategy = self._validate_selector(soup, selector, "partial_class", 5, 0.50, sample_value, field_name)
            if strategy:
                strategies.append(strategy)

        # TIER 6: Content-based matching (priority 6, last resort)
        if sample_value:
            content_strategies = self._find_by_content(soup, sample_value, field_name)
            strategies.extend(content_strategies)

        # Sort by priority (lower = better), then confidence
        strategies.sort(key=lambda x: (x["priority"], -x["confidence"]))

        # Deduplicate by selector
        seen_selectors = set()
        unique_strategies = []
        for strategy in strategies:
            if strategy["selector"] not in seen_selectors:
                seen_selectors.add(strategy["selector"])
                unique_strategies.append(strategy)

        return {
            "success": True,
            "session_id": session_id,
            "field_name": field_name,
            "strategies": unique_strategies[:10],  # Top 10 strategies
            "total_found": len(unique_strategies),
            "recommendation": unique_strategies[0] if unique_strategies else None
        }

    def _get_field_patterns(self, field_name: str) -> Dict[str, List[str]]:
        """
        Get selector patterns for a specific field type

        Returns patterns organized by tier (data attributes, ARIA, semantic, etc.)
        """
        patterns = {
            "price": {
                "data_attrs": ["price", "cost", "amount", "product-price"],
                "aria_patterns": ["price", "cost"],
                "semantic_selectors": ["[itemprop='price']", "[itemprop='offers'] [itemprop='price']"],
                "semantic_classes": ["price", "product-price", "sale-price"],
                "class_patterns": ["price", "cost", "amount"]
            },
            "title": {
                "data_attrs": ["title", "name", "product-name", "product-title"],
                "aria_patterns": ["product", "name", "title"],
                "semantic_selectors": ["h1", "h2", "[itemprop='name']"],
                "semantic_classes": ["title", "product-title", "product-name", "name"],
                "class_patterns": ["title", "name", "heading"]
            },
            "image": {
                "data_attrs": ["image", "src", "product-image"],
                "aria_patterns": ["product image", "image"],
                "semantic_selectors": ["img[itemprop='image']", "img.product-image"],
                "semantic_classes": ["product-image", "image"],
                "class_patterns": ["image", "img", "photo"]
            },
            "description": {
                "data_attrs": ["description", "desc", "product-description"],
                "aria_patterns": ["description", "details"],
                "semantic_selectors": ["[itemprop='description']", "p.description"],
                "semantic_classes": ["description", "product-description", "details"],
                "class_patterns": ["description", "desc", "detail"]
            },
            "rating": {
                "data_attrs": ["rating", "stars", "score"],
                "aria_patterns": ["rating", "stars", "score"],
                "semantic_selectors": ["[itemprop='ratingValue']", "[itemprop='aggregateRating']"],
                "semantic_classes": ["rating", "stars", "score", "review-rating"],
                "class_patterns": ["rating", "star", "review"]
            },
            "availability": {
                "data_attrs": ["availability", "stock", "in-stock"],
                "aria_patterns": ["availability", "stock"],
                "semantic_selectors": ["[itemprop='availability']"],
                "semantic_classes": ["availability", "stock", "in-stock"],
                "class_patterns": ["availability", "stock"]
            },
            "sku": {
                "data_attrs": ["sku", "product-id", "item-id"],
                "aria_patterns": ["sku", "product id"],
                "semantic_selectors": ["[itemprop='sku']"],
                "semantic_classes": ["sku", "product-id"],
                "class_patterns": ["sku", "id"]
            }
        }

        return patterns.get(field_name, {
            "data_attrs": [field_name],
            "aria_patterns": [field_name],
            "semantic_selectors": [],
            "semantic_classes": [field_name],
            "class_patterns": [field_name]
        })

    def _validate_selector(
        self,
        soup: BeautifulSoup,
        selector: str,
        selector_type: str,
        priority: int,
        base_confidence: float,
        sample_value: Optional[str],
        field_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Test a selector and validate it returns expected content

        Returns strategy dict if valid, None if invalid
        """
        try:
            elements = soup.select(selector)
            match_count = len(elements)

            if match_count == 0:
                return None

            # Get sample content
            first_elem = elements[0]
            sample_text = first_elem.get_text(strip=True)[:100]

            # Validate content if sample value provided
            validated = True
            if sample_value:
                # Check if any element contains the sample value
                validated = any(sample_value.lower() in elem.get_text().lower() for elem in elements[:5])

            # Content heuristics for specific field types
            content_confidence_boost = 0.0
            if field_name == "price" and re.search(r'[$€£¥]\s*\d+', sample_text):
                content_confidence_boost = 0.1
            elif field_name == "title" and len(sample_text) > 10:
                content_confidence_boost = 0.05
            elif field_name == "image" and first_elem.name == "img":
                content_confidence_boost = 0.1

            final_confidence = min(1.0, base_confidence + content_confidence_boost)

            # Penalize if too many matches (likely not specific enough)
            if match_count > 50:
                final_confidence *= 0.8

            return {
                "selector": selector,
                "type": selector_type,
                "priority": priority,
                "confidence": final_confidence,
                "matches": match_count,
                "validated": validated,
                "sample": sample_text,
                "element_type": first_elem.name
            }

        except Exception as e:
            logger.debug(f"[SELECTOR VALIDATION] Selector '{selector}' failed: {e}")
            return None

    def _find_by_content(
        self,
        soup: BeautifulSoup,
        sample_value: str,
        field_name: str
    ) -> List[Dict[str, Any]]:
        """
        Find elements by content matching (last resort, priority 6)

        Returns list of content-based strategies
        """
        strategies = []

        # Find elements containing the sample value
        elements = soup.find_all(string=lambda text: sample_value.lower() in text.lower() if text else False)

        for elem_text in elements[:5]:  # Limit to 5 matches
            parent = elem_text.parent
            if parent:
                selector = self._generate_css_selector(parent)
                strategies.append({
                    "selector": selector,
                    "type": "content_based",
                    "priority": 6,
                    "confidence": 0.40,
                    "matches": 1,
                    "validated": True,
                    "sample": str(elem_text)[:100],
                    "element_type": parent.name
                })

        return strategies

    async def analyze_structure(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Analyze overall page structure with anti-scraping and layout pattern detection

        Detects:
        - Layout patterns (grid, semantic schema, infinite scroll, web components)
        - Anti-scraping measures (honeypots, class obfuscation, shadow DOM)
        - Attribute usage (data-*, ARIA, semantic HTML)
        - Lists, tables, repeating patterns

        Args:
            session_id: Session identifier

        Returns:
            Comprehensive structural analysis of the page
        """
        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        soup = self.cached_soups[session_id]

        # Basic structure
        analysis = {
            "lists": {
                "ul": len(soup.find_all("ul")),
                "ol": len(soup.find_all("ol"))
            },
            "tables": len(soup.find_all("table")),
            "forms": len(soup.find_all("form")),
            "potential_items": []
        }

        # Layout pattern detection
        analysis["layout_pattern"] = self._detect_layout_pattern(soup)

        # Anti-scraping detection
        analysis["anti_scraping"] = self._detect_anti_scraping(soup)

        # Attribute usage analysis
        analysis["attribute_usage"] = self._analyze_attribute_usage(soup)

        # Look for repeating patterns (product cards, list items)
        common_item_classes = ["product", "item", "card", "listing"]
        for class_name in common_item_classes:
            items = soup.find_all(class_=re.compile(class_name, re.I))
            if len(items) > 1:
                analysis["potential_items"].append({
                    "pattern": class_name,
                    "count": len(items),
                    "selector": f"[class*='{class_name}']"
                })

        return {
            "success": True,
            "session_id": session_id,
            "analysis": analysis
        }

    def _detect_layout_pattern(self, soup: BeautifulSoup) -> str:
        """
        Detect which e-commerce layout pattern the site uses

        Returns: "data_testid_grid" | "semantic_schema" | "web_components" | "standard_grid" | "unknown"
        """
        # Pattern 1: Grid layout with data-testid
        testid_products = soup.find_all(attrs={"data-testid": re.compile("product|item", re.I)})
        if len(testid_products) > 5:
            logger.debug(f"[LAYOUT] Detected data-testid grid ({len(testid_products)} items)")
            return "data_testid_grid"

        # Pattern 2: Semantic schema.org markup
        schema_products = soup.find_all(attrs={"itemtype": re.compile("Product", re.I)})
        if len(schema_products) > 5:
            logger.debug(f"[LAYOUT] Detected semantic schema.org ({len(schema_products)} items)")
            return "semantic_schema"

        # Pattern 3: Web components (custom elements with hyphens)
        custom_elements = soup.find_all(lambda tag: '-' in tag.name)
        if len(custom_elements) > 10:
            logger.debug(f"[LAYOUT] Detected web components ({len(custom_elements)} custom elements)")
            return "web_components"

        # Pattern 4: Standard grid with common classes
        grid_products = soup.find_all(class_=re.compile("product|item", re.I))
        if len(grid_products) > 5:
            logger.debug(f"[LAYOUT] Detected standard grid ({len(grid_products)} items)")
            return "standard_grid"

        logger.debug("[LAYOUT] Unknown layout pattern")
        return "unknown"

    def _detect_anti_scraping(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Detect anti-scraping measures

        Returns:
        {
            "honeypots_detected": bool,
            "honeypot_count": int,
            "class_obfuscation_level": "low" | "medium" | "high",
            "shadow_dom_detected": bool,
            "custom_element_count": int
        }
        """
        # Honeypot detection: hidden elements with product-like attributes
        honeypots = []
        all_elements = soup.find_all(True)  # All elements

        for elem in all_elements:
            style = elem.get('style', '')
            classes = ' '.join(elem.get('class', []))

            # Check if hidden
            is_hidden = (
                'display:none' in style or
                'display: none' in style or
                'visibility:hidden' in style or
                'hidden' in classes.lower()
            )

            # Check if has product-like attributes
            has_product_attrs = (
                'product' in classes.lower() or
                'item' in classes.lower() or
                elem.find('a') is not None
            )

            if is_hidden and has_product_attrs:
                honeypots.append(elem)

        # Class obfuscation detection
        obfuscation_level = self._detect_class_obfuscation(soup)

        # Shadow DOM detection (custom elements)
        custom_elements = soup.find_all(lambda tag: '-' in tag.name)

        result = {
            "honeypots_detected": len(honeypots) > 0,
            "honeypot_count": len(honeypots),
            "class_obfuscation_level": obfuscation_level,
            "shadow_dom_detected": len(custom_elements) > 0,
            "custom_element_count": len(custom_elements)
        }

        if result["honeypots_detected"]:
            logger.warning(f"[ANTI-SCRAPING] Detected {len(honeypots)} potential honeypots")
        if result["shadow_dom_detected"]:
            logger.info(f"[ANTI-SCRAPING] Detected {len(custom_elements)} custom elements (Shadow DOM)")

        return result

    def _detect_class_obfuscation(self, soup: BeautifulSoup) -> str:
        """
        Detect class name obfuscation level

        Returns: "low" | "medium" | "high"
        """
        all_classes = []

        for elem in soup.find_all(class_=True):
            all_classes.extend(elem.get('class', []))

        if not all_classes:
            return "low"

        # Analyze class patterns
        obfuscated_count = 0
        total_count = len(all_classes)

        for class_name in all_classes:
            # Patterns indicating obfuscation:
            # - Very short random strings (x7k2d, a3f)
            # - Hash-like strings (module__xyz__123abc)
            # - All lowercase alphanumeric with no dashes/underscores

            is_obfuscated = (
                # Short random (< 6 chars, all lowercase alphanumeric)
                (len(class_name) < 6 and re.match(r'^[a-z0-9]+$', class_name)) or
                # Hash pattern (contains double underscores)
                '__' in class_name or
                # CSS modules pattern
                re.match(r'^[a-zA-Z]+_[a-zA-Z0-9]{5,}$', class_name)
            )

            if is_obfuscated:
                obfuscated_count += 1

        obfuscation_ratio = obfuscated_count / total_count if total_count > 0 else 0

        if obfuscation_ratio > 0.6:
            logger.warning(f"[OBFUSCATION] High class obfuscation detected ({obfuscation_ratio:.0%})")
            return "high"
        elif obfuscation_ratio > 0.3:
            logger.info(f"[OBFUSCATION] Medium class obfuscation detected ({obfuscation_ratio:.0%})")
            return "medium"
        else:
            logger.debug(f"[OBFUSCATION] Low class obfuscation detected ({obfuscation_ratio:.0%})")
            return "low"

    def _analyze_attribute_usage(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Analyze which types of attributes are available for selector construction

        Returns:
        {
            "data_attributes": ["data-testid", "data-product-id", ...],
            "data_attribute_count": int,
            "aria_attributes": ["aria-label", "aria-describedby", ...],
            "aria_attribute_count": int,
            "semantic_html_usage": bool,
            "role_attributes": ["button", "article", ...],
            "recommendation": "data_attributes" | "aria_attributes" | "semantic_html" | "classes"
        }
        """
        # Find all data-* attributes
        data_attrs = set()
        aria_attrs = set()
        role_values = set()

        for elem in soup.find_all(True):
            for attr in elem.attrs.keys():
                if attr.startswith('data-'):
                    data_attrs.add(attr)
                elif attr.startswith('aria-'):
                    aria_attrs.add(attr)
                elif attr == 'role':
                    role_values.add(elem.get('role'))

        # Check semantic HTML usage
        semantic_tags = ['article', 'section', 'nav', 'main', 'aside', 'header', 'footer']
        semantic_count = sum(len(soup.find_all(tag)) for tag in semantic_tags)
        semantic_html_usage = semantic_count > 5

        # Determine recommendation
        if len(data_attrs) > 3:
            recommendation = "data_attributes"
        elif len(aria_attrs) > 3:
            recommendation = "aria_attributes"
        elif semantic_html_usage:
            recommendation = "semantic_html"
        else:
            recommendation = "classes"

        result = {
            "data_attributes": sorted(list(data_attrs)),
            "data_attribute_count": len(data_attrs),
            "aria_attributes": sorted(list(aria_attrs)),
            "aria_attribute_count": len(aria_attrs),
            "semantic_html_usage": semantic_html_usage,
            "role_attributes": sorted(list(role_values)),
            "recommendation": recommendation
        }

        logger.info(f"[ATTRIBUTES] Recommendation: {recommendation} "
                   f"(data: {len(data_attrs)}, ARIA: {len(aria_attrs)}, semantic: {semantic_html_usage})")

        return result

    def _generate_css_selector(self, element) -> str:
        """Generate CSS selector for an element"""
        if not element or not hasattr(element, 'name'):
            return ""

        # Try ID first
        if element.get('id'):
            return f"#{element['id']}"

        # Try unique class combination
        if element.get('class'):
            classes = '.'.join(element['class'])
            return f"{element.name}.{classes}"

        # Use tag name with nth-of-type
        return f"{element.name}"

    def _generate_xpath(self, element) -> str:
        """Generate XPath for an element"""
        if not element or not hasattr(element, 'name'):
            return ""

        # Simple XPath generation
        if element.get('id'):
            return f"//*[@id='{element['id']}']"

        if element.get('class'):
            classes = ' '.join(element['class'])
            return f"//{element.name}[@class='{classes}']"

        return f"//{element.name}"

    async def validate_selector(
        self,
        session_id: str,
        selector: str,
        selector_type: str = "css"
    ) -> Dict[str, Any]:
        """
        Validate a selector and count matches

        Args:
            session_id: Session identifier
            selector: Selector to validate
            selector_type: "css" or "xpath"

        Returns:
            Validation results with match count
        """
        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        soup = self.cached_soups[session_id]

        try:
            if selector_type == "css":
                matches = soup.select(selector)
            else:
                # XPath not directly supported by BeautifulSoup
                return {
                    "success": False,
                    "message": "XPath validation not yet implemented"
                }

            return {
                "success": True,
                "session_id": session_id,
                "selector": selector,
                "valid": len(matches) > 0,
                "match_count": len(matches),
                "sample_content": str(matches[0])[:200] if matches else None
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Selector validation failed: {str(e)}"
            }

    async def detect_product_containers(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Detect product container patterns using multi-phase strategy

        Strategy:
        1. Try generic e-commerce selectors (Schema.org, data attributes, common classes)
        2. Try repeating pattern detection (class frequency analysis)
        3. Content-based heuristic detection (image + link + price pattern)
        4. Return None if no patterns found (triggers fallback chunking)

        Args:
            session_id: Session identifier

        Returns:
            {
                "success": True,
                "selector": ".product-card",
                "count": 24,
                "sample_html": "<div class='product-card'>...</div>",
                "validation": {
                    "has_images": 24,
                    "has_links": 24,
                    "has_prices": 22,
                    "confidence": 0.92
                }
            }
            OR
            {
                "success": False,
                "message": "No product patterns detected"
            }
        """
        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        soup = self.cached_soups[session_id]

        # Phase 1: Try generic e-commerce selectors
        generic_selectors = [
            '[itemtype*="Product"]',           # Schema.org microdata
            '[itemscope][itemtype*="product"]',
            '[data-testid*="product" i]',      # Case-insensitive test IDs
            '[data-product-id]',
            '[data-component*="product" i]',
            '.product-card', '.product-item', '.product',
            'article[class*="product" i]',
            '[class*="productCard" i]',
            '[class*="product-tile" i]'
        ]

        logger.debug("[PRODUCT DETECTION] Phase 1: Trying generic selectors...")
        for selector in generic_selectors:
            try:
                elements = soup.select(selector)
                count = len(elements)

                # Valid product grid: 3-100 items
                if 3 <= count <= 100:
                    # Validate with content heuristics
                    validation = self._validate_product_containers(elements)

                    if validation["confidence"] > 0.6:
                        sample_html = str(elements[0])
                        logger.info(f"[PRODUCT DETECTION] ✓ Found pattern: {selector} ({count} items, "
                                   f"confidence: {validation['confidence']:.2f})")

                        return {
                            "success": True,
                            "method": "generic_selector",
                            "selector": selector,
                            "count": count,
                            "sample_html": sample_html[:2000],
                            "validation": validation
                        }
            except Exception as e:
                logger.debug(f"[PRODUCT DETECTION] Selector '{selector}' failed: {e}")
                continue

        # Phase 2: Repeating pattern detection with validation
        logger.debug("[PRODUCT DETECTION] Phase 2: Analyzing repeating patterns...")

        # Find all elements with classes
        elements_with_classes = soup.find_all(class_=True)

        # Count class combinations
        class_frequency = {}
        for elem in elements_with_classes:
            # Get class string (sorted for consistency)
            classes = ' '.join(sorted(elem.get('class', [])))
            if classes:
                if classes not in class_frequency:
                    class_frequency[classes] = []
                class_frequency[classes].append(elem)

        # Find patterns with 3-100 occurrences
        for classes, elements in class_frequency.items():
            count = len(elements)

            if 3 <= count <= 100:
                # Validate with content heuristics
                validation = self._validate_product_containers(elements)

                if validation["confidence"] > 0.6:
                    # Generate selector from classes
                    class_list = classes.split()
                    selector = '.' + '.'.join(class_list)
                    sample_html = str(elements[0])

                    logger.info(f"[PRODUCT DETECTION] ✓ Found repeating pattern: {selector} ({count} items, "
                               f"confidence: {validation['confidence']:.2f})")

                    return {
                        "success": True,
                        "method": "repeating_pattern",
                        "selector": selector,
                        "count": count,
                        "sample_html": sample_html[:2000],
                        "validation": validation
                    }

        # Phase 3: Content-based detection (find elements with image + link + price)
        logger.debug("[PRODUCT DETECTION] Phase 3: Content-based heuristic detection...")

        content_based_containers = self._find_containers_by_content(soup)
        if content_based_containers:
            elements = content_based_containers
            count = len(elements)
            validation = self._validate_product_containers(elements)

            # Try to generate a common selector
            selector = self._find_common_selector(elements)

            logger.info(f"[PRODUCT DETECTION] ✓ Found content-based pattern: {selector} ({count} items, "
                       f"confidence: {validation['confidence']:.2f})")

            return {
                "success": True,
                "method": "content_heuristic",
                "selector": selector,
                "count": count,
                "sample_html": str(elements[0])[:2000],
                "validation": validation
            }

        # Phase 4: No patterns found
        logger.warning("[PRODUCT DETECTION] ✗ No product patterns detected, will use fallback chunking")

        return {
            "success": False,
            "message": "No product container patterns detected"
        }

    def _validate_product_containers(self, elements: List) -> Dict[str, Any]:
        """
        Validate that elements look like product containers

        Checks for:
        - Images
        - Links
        - Price patterns ($, €, etc.)

        Returns confidence score based on how many elements pass validation
        """
        has_images = 0
        has_links = 0
        has_prices = 0

        price_pattern = re.compile(r'[$€£¥]\s*\d+[\.,]\d{0,2}')

        for elem in elements[:20]:  # Check first 20 elements
            if elem.find('img'):
                has_images += 1
            if elem.find('a'):
                has_links += 1
            if price_pattern.search(elem.get_text()):
                has_prices += 1

        total_checked = min(len(elements), 20)

        # Calculate confidence based on presence of key elements
        image_ratio = has_images / total_checked if total_checked > 0 else 0
        link_ratio = has_links / total_checked if total_checked > 0 else 0
        price_ratio = has_prices / total_checked if total_checked > 0 else 0

        # Confidence formula: weighted average (images and links are most important)
        confidence = (image_ratio * 0.4) + (link_ratio * 0.4) + (price_ratio * 0.2)

        return {
            "has_images": has_images,
            "has_links": has_links,
            "has_prices": has_prices,
            "total_checked": total_checked,
            "confidence": confidence
        }

    def _find_containers_by_content(self, soup: BeautifulSoup) -> Optional[List]:
        """
        Find product containers using content-based heuristics

        Returns elements that contain: image + link + likely price text
        """
        candidates = []

        # Look at all div, article, li elements
        for container_tag in ['div', 'article', 'li']:
            elements = soup.find_all(container_tag)

            for elem in elements:
                # Must have image
                if not elem.find('img'):
                    continue

                # Must have link
                if not elem.find('a'):
                    continue

                # Should have reasonable text length (products have descriptions)
                text = elem.get_text(strip=True)
                if not (20 < len(text) < 500):
                    continue

                # Check for price pattern
                price_pattern = re.compile(r'[$€£¥]\s*\d+[\.,]\d{0,2}')
                if price_pattern.search(text):
                    candidates.append(elem)

        # Filter to find repeating patterns
        if not candidates:
            return None

        # Group by tag and similar class patterns
        tag_groups = {}
        for elem in candidates:
            tag = elem.name
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append(elem)

        # Return largest group with 3+ items
        for tag, elements in tag_groups.items():
            if len(elements) >= 3:
                return elements[:100]  # Limit to 100

        return None

    def _find_common_selector(self, elements: List) -> str:
        """
        Find a common CSS selector that matches all elements

        Returns the most specific common selector
        """
        if not elements:
            return ""

        # Try common class patterns
        first_elem = elements[0]

        # Check if all elements share a class
        if first_elem.get('class'):
            first_classes = set(first_elem.get('class', []))

            for elem in elements[1:]:
                elem_classes = set(elem.get('class', []))
                first_classes = first_classes.intersection(elem_classes)

            if first_classes:
                # Found common classes
                return '.' + '.'.join(sorted(first_classes))

        # Fallback: just use tag name
        return first_elem.name

    async def chunk_html_for_llm(
        self,
        session_id: str,
        max_chunk_length: int = 2000
    ) -> Dict[str, Any]:
        """
        Chunk HTML semantically using betterhtmlchunking

        Used as fallback when product detection fails.
        Chunks preserve DOM structure for better LLM understanding.

        Args:
            session_id: Session identifier
            max_chunk_length: Maximum characters per chunk (default: 2000)

        Returns:
            {
                "success": True,
                "chunks": [
                    {
                        "index": 0,
                        "html": "<div>...</div>",
                        "text_preview": "Product preview...",
                        "length": 1847
                    },
                    ...
                ],
                "total_chunks": 12
            }
        """
        if not CHUNKING_AVAILABLE:
            return {
                "success": False,
                "message": "betterhtmlchunking library not installed. Install with: pip install betterhtmlchunking"
            }

        if session_id not in self.cached_soups:
            return {
                "success": False,
                "message": f"No parsed HTML for session {session_id}"
            }

        # Get HTML from cached soup
        soup = self.cached_soups[session_id]
        html_content = str(soup)

        try:
            # Use betterhtmlchunking for semantic splitting
            dom_repr = DomRepresentation(
                website_code=html_content,
                max_node_repr_length=max_chunk_length,
                repr_length_compared_by=ReprLengthComparisionBy.TEXT_LENGTH  # Chunk by visible text
            )

            html_chunks = dom_repr.get_chunked_html()
            plain_chunks = dom_repr.get_chunked_text()

            # Build chunk metadata
            chunks = []
            for idx, (html_chunk, text_chunk) in enumerate(zip(html_chunks, plain_chunks)):
                chunks.append({
                    "index": idx,
                    "html": html_chunk,
                    "text_preview": text_chunk[:200],  # First 200 chars
                    "length": len(html_chunk)
                })

            logger.info(f"[CHUNKING] Split HTML into {len(chunks)} semantic chunks")

            return {
                "success": True,
                "chunks": chunks,
                "total_chunks": len(chunks)
            }

        except Exception as e:
            logger.error(f"[CHUNKING] Failed to chunk HTML: {str(e)}")
            return {
                "success": False,
                "message": f"Chunking failed: {str(e)}"
            }
