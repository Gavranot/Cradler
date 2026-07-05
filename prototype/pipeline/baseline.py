"""B1 comparator: faithful port of production `_remove_boilerplate`
(backend/agents/mcp/tools_manager.py:93). Do not improve it — it exists to measure
what the system does today.
"""
from bs4 import BeautifulSoup, Comment


def remove_boilerplate_prod(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "link", "meta", "noscript"]):
        tag.decompose()

    boilerplate_selectors = [
        "nav", "header", "footer", "aside",
        '[role="navigation"]', '[role="banner"]',
        '[role="contentinfo"]', '[role="complementary"]',
        '[class*="cookie"]', '[class*="banner"]',
        '[class*="modal"]', '[id*="popup"]',
        '[class*="sidebar"]', '[class*="menu"]',
    ]
    for selector in boilerplate_selectors:
        for elem in soup.select(selector):
            elem.decompose()

    for svg in soup.find_all("svg"):
        svg.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    return str(soup)
