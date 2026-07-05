"""Alternative fragment representation: flat XPath→text/attr pairs.

Motivated by NEXT-EVAL (arXiv:2505.17125): LLM record-extraction F1 jumped
0.10 → 0.957 when the DOM was flattened to XPath→text JSON instead of raw HTML.
This renders an already-reduced fragment (exemplar card / detail slice) as
compact path→value lines so we can compare token cost. Accuracy A/B against
exemplar-HTML requires LLM calls — future budgeted work.
"""
from __future__ import annotations

from lxml import etree, html as lhtml

KEEP = ("itemprop", "data-testid", "id", "href", "src", "alt", "content",
        "aria-label", "class")


def render_xpath_view(fragment_html: str) -> str:
    tree = lhtml.fromstring(fragment_html)
    lines: list[str] = []

    def path_of(el) -> str:
        parts = []
        cur = el
        while cur is not None and isinstance(cur.tag, str):
            parent = cur.getparent()
            if parent is not None:
                same = [s for s in parent if s.tag == cur.tag]
                idx = f"[{same.index(cur) + 1}]" if len(same) > 1 else ""
            else:
                idx = ""
            parts.append(f"{cur.tag}{idx}")
            cur = parent
        return "/" + "/".join(reversed(parts))

    for el in tree.iter(etree.Element):
        text = (el.text or "").strip()
        attrs = {k: v for k, v in el.attrib.items() if k in KEEP and v}
        if not text and not attrs:
            continue
        p = path_of(el)
        if text:
            lines.append(f"{p} :: {text[:80]}")
        for k, v in attrs.items():
            if k == "class":
                v = " ".join(v.split()[:4])
            lines.append(f"{p} @{k} = {v[:80]}")
    return "\n".join(lines)
