"""Layer 2b — product-detail pages: anchor-guided DOM slicing.

Locate stable anchors for each field of interest, then emit only the DOM
neighborhoods around them. Anchors, in priority order:

  1. semantic markup surviving L1: [itemprop], meta[property^=og:/product:]
  2. stable data-* hooks (data-testid/product/price/sku)
  3. L0 values used as TEXT anchors (finds the price box even with hashed classes)
  4. visible-label heuristics: price regex, add-to-cart button, <h1>

Missing anchors are reported in `anchors_found`, never silently dropped
(AutoScraper-style widen-on-miss escalation is the caller's job).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree, html as lhtml

from .listing import PRICE_RE, _css_path  # shared heuristics

SLICE_CHAR_CAP = 1600          # stop ancestor-walk when subtree exceeds this
MAX_SLICES_PER_FIELD = 2

# ("css", selector) entries use cssselect; ("attr", attr_name_prefix, substring)
# entries do a case-insensitive python-side scan (cssselect lacks the `i` flag).
ANCHOR_FIELDS = {
    "title": {
        "find": [("css", "h1"), ("css", "[itemprop='name']"),
                 ("attr", "data-", "title"), ("attr", "data-", "name")],
    },
    "price": {
        "find": [("css", "[itemprop='price']"), ("attr", "data-", "price"),
                 ("attr", "class", "price")],
        "text_re": PRICE_RE,
    },
    "currency": {"find": [("css", "[itemprop='priceCurrency']"),
                          ("attr", "class", "currency")]},
    "image": {
        "find": [("css", "[itemprop='image']"), ("attr", "data-", "image"),
                 ("imgin", "class", "gallery"), ("imgin", "class", "product"),
                 ("css", "main img")],
    },
    "sku": {"find": [("css", "[itemprop='sku']"), ("attr", "data-", "sku"),
                     ("attr", "class", "sku")]},
    "availability": {
        "find": [("css", "[itemprop='availability']"), ("attr", "class", "stock"),
                 ("attr", "class", "availability")],
        "button_text": re.compile(r"add to (cart|bag|basket)|buy now|sold out", re.I),
    },
    "description": {"find": [("css", "[itemprop='description']"),
                             ("attr", "class", "description"),
                             ("attr", "id", "description")]},
}


def _attr_scan(tree: etree._Element, attr: str, substring: str,
               img_inside: bool = False) -> list[etree._Element]:
    """Case-insensitive `[attr*=substring]` without cssselect's missing `i` flag.
    attr='data-' matches ANY data-* attribute name; img_inside returns the first
    <img> inside each hit instead of the hit itself."""
    sub = substring.lower()
    out = []
    for el in tree.iter(etree.Element):
        for name, value in el.attrib.items():
            if attr == "data-":
                if name.startswith("data-") and sub in (name + value).lower():
                    out.append(el)
                    break
            elif name == attr and sub in value.lower():
                out.append(el)
                break
    if img_inside:
        imgs = []
        for el in out:
            imgs.extend(el.iter("img"))
        return imgs[:3]
    return out


@dataclass
class DetailExtract:
    slices: list[str]                       # reduced-HTML neighborhoods
    anchors_found: dict[str, bool]
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n<!-- slice -->\n".join(self.slices)


def _grow(el: etree._Element, cap: int = SLICE_CHAR_CAP) -> etree._Element:
    """Walk up ancestors while the subtree stays under the size cap."""
    cur = el
    while True:
        parent = cur.getparent()
        if parent is None or parent.tag in ("body", "html"):
            return cur
        if len(lhtml.tostring(parent, encoding="unicode")) > cap:
            return cur
        cur = parent


def _find_text_anchor(tree: etree._Element, value: str) -> etree._Element | None:
    """Find the deepest element whose own text contains `value`."""
    if not value or len(value) < 2:
        return None
    hits = [el for el in tree.iter(etree.Element)
            if value in (el.text or "") or value in (el.tail or "")]
    return hits[0] if hits else None


def slice_detail(reduced_html: str, l0_values: dict | None = None) -> DetailExtract:
    tree = lhtml.fromstring(reduced_html)
    l0_values = l0_values or {}
    chosen: dict[str, list[etree._Element]] = {}
    anchors_found: dict[str, bool] = {}
    notes: list[str] = []

    for fname, spec in ANCHOR_FIELDS.items():
        found: list[etree._Element] = []
        for probe in spec.get("find", []):
            kind = probe[0]
            if kind == "css":
                try:
                    found.extend(tree.cssselect(probe[1]))
                except Exception:  # noqa: BLE001 - invalid dynamic selector variants
                    continue
            elif kind == "attr":
                found.extend(_attr_scan(tree, probe[1], probe[2]))
            elif kind == "imgin":
                found.extend(_attr_scan(tree, probe[1], probe[2], img_inside=True))
            # an "anchor" bigger than 2 slice-caps is a page-level container that
            # happens to match (e.g. WooCommerce's `instock` wrapper class), not a
            # field node — drop it and let the next probe try
            found = [el for el in found
                     if len(lhtml.tostring(el, encoding="unicode")) <= SLICE_CHAR_CAP * 2]
            if found:
                break
        # L0 value as text anchor (localizes fields with obfuscated classes)
        if not found and fname in ("title", "price", "sku"):
            v = l0_values.get("name" if fname == "title" else fname)
            el = _find_text_anchor(tree, str(v)[:60]) if v else None
            if el is not None:
                found = [el]
                notes.append(f"{fname}: located via L0 text anchor")
        # visible-label fallbacks
        if not found and "text_re" in spec:
            rx = spec["text_re"]
            found = [el for el in tree.iter(etree.Element)
                     if rx.search(el.text or "")][:3]
        if not found and "button_text" in spec:
            rx = spec["button_text"]
            found = [el for el in tree.iter("button", "a")
                     if rx.search(" ".join(el.itertext())[:100] or "")][:2]

        anchors_found[fname] = bool(found)
        chosen[fname] = found[:MAX_SLICES_PER_FIELD]

    # grow each anchor into a neighborhood, then dedupe by containment
    grown: list[etree._Element] = []
    for els in chosen.values():
        for el in els:
            grown.append(_grow(el))
    unique: list[etree._Element] = []
    for el in grown:
        if any(other is not el and other in el.iterancestors() or other is el
               for other in unique):
            continue
        # also skip if el CONTAINS an already-kept slice's ancestor... keep outermost:
        unique = [u for u in unique if el not in u.iterancestors()]
        unique.append(el)
    # de-dup exact repeats while preserving document order
    seen: set[int] = set()
    ordered: list[etree._Element] = []
    for el in tree.iter(etree.Element):
        if any(el is u for u in unique) and id(el) not in seen:
            seen.add(id(el))
            ordered.append(el)

    slices = []
    for el in ordered:
        s = lhtml.tostring(el, encoding="unicode")
        anchor_path = _css_path(el, tree)
        slices.append(f"<!-- @ {anchor_path} -->\n{s}")

    missing = [f for f, ok in anchors_found.items() if not ok]
    if missing:
        notes.append(f"anchors NOT found: {', '.join(missing)}")
    return DetailExtract(slices=slices, anchors_found=anchors_found, notes=notes)
