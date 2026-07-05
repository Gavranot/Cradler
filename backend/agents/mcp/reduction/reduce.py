"""Layer 1 — universal HTML reduction (page-type agnostic).

HtmlRAG-style cleaning (arXiv:2411.02959 measured ~94% token cut from cleaning
alone), adapted for selector authoring:

- drop non-content elements (script/style/svg/noscript/template/iframe/link/comments)
- drop <head> except <title> and product-relevant <meta> (itemprop / og: / product:)
- strip attributes to a whitelist that selectors need (class/id/itemprop/... and
  stable-looking data-*)
- truncate long text nodes to a preview
- drop empty elements (no text, no kept attrs, no children), bottom-up

Deliberately NOT done (selector fidelity): no single-child wrapper merging — the
LLM may write child combinators (`a > b`) that must hold on the full DOM; no
readability/main-content deletion — tuned for articles, deletes shop content.

Deterministic; every action class is recorded in `notes`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree, html as lhtml

DROP_TAGS = {"script", "style", "svg", "noscript", "template", "iframe", "link",
             "canvas", "video", "audio", "source", "picture"}
# <picture> children: keep the <img> inside; picture/source themselves add noise.
KEEP_PICTURE_CHILD = "img"

KEEP_ATTRS = {"class", "id", "itemprop", "itemscope", "itemtype", "role", "href",
              "src", "alt", "content", "property", "datetime", "aria-label",
              "type", "value", "name"}
DATA_ATTR_RE = re.compile(
    r"^data-(testid|test|qa|cy|track|component|product|price|sku|item|id|variant|"
    r"currency|url|title|name|hook|el|automation)", re.I)
META_KEEP_RE = re.compile(r"^(og:|product:|twitter:price|twitter:title)", re.I)

TEXT_PREVIEW = 120


@dataclass
class ReduceResult:
    html: str
    notes: list[str] = field(default_factory=list)


def _keep_attr(name: str) -> bool:
    return name in KEEP_ATTRS or bool(DATA_ATTR_RE.match(name))


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    if len(stripped) <= limit:
        return text
    return stripped[:limit] + "…"


def reduce_html(raw_html: str, *, text_preview: int = TEXT_PREVIEW) -> ReduceResult:
    notes: list[str] = []
    tree = lhtml.fromstring(raw_html)

    # 1. head: keep only <title> and product-relevant meta
    for head in tree.iter("head"):
        for child in list(head):
            if child.tag == "title":
                continue
            if child.tag == "meta":
                prop = (child.get("property") or child.get("name") or
                        child.get("itemprop") or "")
                if child.get("itemprop") or META_KEEP_RE.match(prop):
                    continue
            head.remove(child)
    notes.append("head: kept title + itemprop/og/product meta only")

    # 2. drop non-content elements (keep img inside picture)
    dropped = 0
    for tag in DROP_TAGS:
        for el in tree.iter(tag):
            if tag == "picture":
                continue
            parent = el.getparent()
            if parent is not None:
                # preserve tail text so surrounding content is not lost
                if el.tail and el.tail.strip():
                    prev = el.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or "") + el.tail
                    else:
                        parent.text = (parent.text or "") + el.tail
                parent.remove(el)
                dropped += 1
    notes.append(f"dropped {dropped} non-content elements ({', '.join(sorted(DROP_TAGS))})")

    # comments
    for c in tree.xpath("//comment()"):
        p = c.getparent()
        if p is not None:
            p.remove(c)

    # 2b. drop page chrome (nav/header/footer/aside + landmark roles), but hoist
    # breadcrumbs out first — the prod cleaner's breadcrumb-killing is a known flaw.
    breadcrumb_xpath = (
        ".//*[contains(translate(@class,'BREADCRUMB','breadcrumb'),'breadcrumb') or "
        "contains(translate(@aria-label,'BREADCRUMB','breadcrumb'),'breadcrumb') or "
        "contains(@itemtype,'BreadcrumbList')]")
    chrome_els = []
    for tag in ("nav", "header", "footer", "aside"):
        chrome_els.extend(tree.iter(tag))
    for el in tree.xpath("//*[@role='navigation' or @role='banner' or "
                         "@role='contentinfo' or @role='complementary']"):
        chrome_els.append(el)
    dropped_chrome = hoisted = 0
    for el in chrome_els:
        parent = el.getparent()
        if parent is None:  # already detached via an ancestor
            continue
        crumbs = el.xpath(breadcrumb_xpath)
        idx = parent.index(el)
        for crumb in crumbs[:1]:  # one breadcrumb trail is enough
            parent.insert(idx, crumb)
            hoisted += 1
        parent.remove(el)
        dropped_chrome += 1
    notes.append(f"dropped {dropped_chrome} chrome elements "
                 f"(nav/header/footer/aside/landmarks), hoisted {hoisted} breadcrumbs")

    # 3. attribute whitelist
    stripped_attrs = 0
    for el in tree.iter(etree.Element):
        for name in list(el.attrib):
            if not _keep_attr(name):
                del el.attrib[name]
                stripped_attrs += 1
            elif name in ("src", "href") and len(el.attrib[name]) > 300:
                el.attrib[name] = el.attrib[name][:300] + "…"
        # srcset-style megabyte attribute values are gone via whitelist already
    notes.append(f"stripped {stripped_attrs} attributes (whitelist: "
                 f"{len(KEEP_ATTRS)} names + stable data-*)")

    # 4. truncate long text nodes
    for el in tree.iter(etree.Element):
        el.text = _truncate(el.text, text_preview)
        el.tail = _truncate(el.tail, text_preview)

    # 5. drop empty elements bottom-up (keep void content tags)
    void_keep = {"img", "br", "hr", "input", "meta"}
    removed_empty = 0
    changed = True
    while changed:
        changed = False
        for el in list(tree.iter(etree.Element)):
            if el.tag in void_keep or el.tag in ("html", "body", "head", "title"):
                continue
            has_children = len(el) > 0
            has_text = bool((el.text or "").strip())
            has_attrs = bool(el.attrib)
            if not has_children and not has_text and not has_attrs:
                parent = el.getparent()
                if parent is not None:
                    if el.tail and el.tail.strip():
                        prev = el.getprevious()
                        if prev is not None:
                            prev.tail = (prev.tail or "") + el.tail
                        else:
                            parent.text = (parent.text or "") + el.tail
                    parent.remove(el)
                    removed_empty += 1
                    changed = True
    notes.append(f"removed {removed_empty} empty elements")

    out = lhtml.tostring(tree, encoding="unicode")
    # collapse whitespace runs (serialization keeps pretty-print newlines around)
    out = re.sub(r"\n\s*\n+", "\n", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return ReduceResult(html=out, notes=notes)
