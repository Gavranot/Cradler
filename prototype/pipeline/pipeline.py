"""End-to-end orchestration: raw HTML → ReducedFragment for the authoring LLM.

Cascade: L0 structured probe (on RAW html) → page-type classification →
L1 universal reduction → L2a exemplar mining / L2b anchor slicing →
token budget enforcement. Every layer's contribution is recorded in `notes`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .detail import slice_detail
from .listing import mine_listing
from .reduce import reduce_html
from .structured import StructuredData, cross_check, extract_structured
from .tokens import count_tokens

DEFAULT_BUDGET = 6000          # tokens; per-model override belongs to the router

LISTING_URL_RE = re.compile(r"/(collections|category|categories|shop|search|c|"
                            r"kategorija|kategoria|prodavnica)/|"
                            r"product-category|[?&]page=", re.I)
DETAIL_URL_RE = re.compile(r"/(product|products|item|p|dp|proizvod|produkt|artikl)/"
                           r"|\.html$|[?&]sku=", re.I)
# classification HINT (misses fall through to 'unknown' → cheap-model tiebreak):
# includes common South-Slavic storefront phrasings
CART_RE = re.compile(r"add to (cart|bag|basket)|buy now|"
                     r"кошничка|корпа|купи|kosnicka|korpa|kupi|dodaj", re.I)


@dataclass
class ReducedFragment:
    text: str
    page_type: str                 # "listing" | "detail" | "unknown"
    est_tokens: int
    source_layer: str              # "L0" | "L2a" | "L2b" | "L1-budgeted"
    l0: StructuredData | None = None
    l0_cross_check: dict[str, bool] = field(default_factory=dict)
    listing_meta: dict = field(default_factory=dict)
    anchors_found: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def classify_page_type(url: str, sd: StructuredData, reduced_html: str) -> str:
    """Cheap signals only; an ambiguous page goes to the cheap router model
    (out of scope here — we return 'unknown')."""
    if sd.items:
        return "listing"
    cart = bool(CART_RE.search(reduced_html))
    # strongest detail signal: this page IS a product (markup) and SELLS it (cart).
    # Checked before grid mining because detail pages carry ≥8-card related-product
    # rails; checked with cart because listings sometimes embed one stray Product
    # markup block (featured item).
    if sd.product.get("name") and cart:
        return "detail"
    # only CORROBORATED grids are classification evidence — an unconfirmed
    # candidate (nav rail, footer columns) must not flip a detail page to listing
    ex = mine_listing(reduced_html)
    if ex is not None and ex.confidence == "corroborated" and ex.record_count >= 8:
        return "listing"
    if sd.product.get("name") and sd.product.get("price") is not None:
        return "detail"
    # no structured data at all (e.g. BigCommerce Cornerstone): cart + a single
    # h1 is the classic product-detail shape
    if cart and reduced_html.count("<h1") == 1:
        return "detail"
    if LISTING_URL_RE.search(url):
        return "listing"
    if DETAIL_URL_RE.search(url):
        return "detail"
    return "unknown"


def _truncate_to_budget(text: str, budget: int, notes: list[str]) -> str:
    t = count_tokens(text)
    if t <= budget:
        return text
    keep_chars = int(len(text) * budget / t)
    notes.append(f"HARD TRUNCATION {t}→~{budget} tokens (pathological page)")
    return text[:keep_chars]


def build_fragment(raw_html: str, url: str, *, page_type: str | None = None,
                   budget: int = DEFAULT_BUDGET) -> ReducedFragment:
    notes: list[str] = []

    # L0 — on raw html, before any cleaning
    sd = extract_structured(raw_html, url)
    xcheck = cross_check(sd, raw_html)

    # L1
    reduced = reduce_html(raw_html)
    notes.extend(f"L1: {n}" for n in reduced.notes)

    ptype = page_type or classify_page_type(url, sd, reduced.html)

    # L2
    if ptype == "listing":
        ex = mine_listing(reduced.html)
        if ex is not None:
            if ex.confidence == "corroborated":
                header = (f"<!-- listing: {ex.record_count} records match "
                          f"`{ex.record_css}` inside `{ex.container_css}`. "
                          f"ONE exemplar card follows; write field selectors "
                          f"relative to the card. -->\n")
            else:
                header = (
                    f"<!-- listing candidate (UNCONFIRMED): the strongest repeated "
                    f"linked structure on this page is {ex.record_count} × "
                    f"`{ex.record_css}` inside `{ex.container_css}`, but automatic "
                    f"checks could not confirm product signals "
                    f"(price_ratio={ex.stats.get('price_ratio', 0):.2f}, "
                    f"img_ratio={ex.stats.get('img_ratio', 0):.2f}). "
                    f"YOU decide: inspect the exemplar below — if these are product "
                    f"records, author selectors relative to the card; if not, call "
                    f"browser_get_page_source(full=true) to explore the page "
                    f"yourself. -->\n")
            text = header + ex.exemplar_html
            if ex.second_exemplar_html:
                text += "\n<!-- structural variant card: -->\n" + ex.second_exemplar_html
            notes.extend(f"L2a: {n}" for n in ex.notes)
            text = _truncate_to_budget(text, budget, notes)
            return ReducedFragment(
                text=text, page_type=ptype, est_tokens=count_tokens(text),
                source_layer="L2a", l0=sd, l0_cross_check=xcheck,
                listing_meta={"container_css": ex.container_css,
                              "record_css": ex.record_css,
                              "record_count": ex.record_count,
                              "confidence": ex.confidence,
                              "stats": ex.stats},
                notes=notes)
        notes.append("L2a: no repeated linked structure found at all "
                     "(client-rendered listing?) — falling back to budgeted L1")
    elif ptype == "detail":
        ex = slice_detail(reduced.html, sd.product)
        if ex.slices:
            found = ", ".join(f for f, ok in ex.anchors_found.items() if ok)
            missing = ", ".join(f for f, ok in ex.anchors_found.items() if not ok)
            header = (f"<!-- detail page. anchored slices for: {found or 'none'}. "
                      f"NOT located: {missing or 'none'} (absent pre-render or "
                      f"needs wider fragment). -->\n")
            text = header + ex.text
            notes.extend(f"L2b: {n}" for n in ex.notes)
            text = _truncate_to_budget(text, budget, notes)
            return ReducedFragment(
                text=text, page_type=ptype, est_tokens=count_tokens(text),
                source_layer="L2b", l0=sd, l0_cross_check=xcheck,
                anchors_found=ex.anchors_found, notes=notes)
        notes.append("L2b: no anchors at all — falling back to budgeted L1")

    text = _truncate_to_budget(reduced.html, budget, notes)
    return ReducedFragment(text=text, page_type=ptype, est_tokens=count_tokens(text),
                           source_layer="L1-budgeted", l0=sd, l0_cross_check=xcheck,
                           notes=notes)
