"""Layer 0 — structured-data probe. Runs on RAW html (before any cleaning —
the current production cleaner destroys these sources; see FINDINGS F2).

Sources, in order of trust: JSON-LD Product/ItemList → microdata → OpenGraph.
Hydration blobs (__NEXT_DATA__ etc.) are detected and size-reported but not
deep-parsed in v1 (Next 13+ fragments them; see FINDINGS F8).

Every extracted value is meant to be DOM-cross-checked by the caller before
being trusted (build-time markup drift is a documented failure class).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import extruct

REQUIRED = {
    "detail": {"name", "price"},
    "listing": {"items"},
}

HYDRATION_MARKERS = {
    "__NEXT_DATA__": re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                re.S),
    "__next_f": re.compile(r"self\.__next_f\.push"),
    "__NUXT__": re.compile(r"window\.__NUXT__"),
    "__APOLLO_STATE__": re.compile(r"__APOLLO_STATE__"),
    "__INITIAL_STATE__": re.compile(r"window\.__INITIAL_STATE__"),
}


@dataclass
class StructuredData:
    product: dict[str, Any] = field(default_factory=dict)   # normalized detail fields
    items: list[dict[str, Any]] = field(default_factory=list)  # normalized ItemList
    sources_used: list[str] = field(default_factory=list)
    hydration: dict[str, int] = field(default_factory=dict)  # marker -> payload bytes
    raw_types_seen: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def coverage(self, page_type: str) -> float:
        req = REQUIRED.get(page_type, set())
        if not req:
            return 0.0
        if page_type == "listing":
            return 1.0 if len(self.items) >= 3 else 0.0
        present = {k for k, v in self.product.items() if v not in (None, "", [])}
        return len(req & present) / len(req)


def _walk_jsonld(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(x in ("Product", "ProductGroup", "ItemList") for x in types if x):
            out.append(node)
        for v in node.values():
            _walk_jsonld(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_jsonld(v, out)


def _first(v: Any) -> Any:
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _norm_offer(offers: Any) -> dict:
    offer = _first(offers) or {}
    if isinstance(offer, dict) and offer.get("@type") == "AggregateOffer":
        price = offer.get("lowPrice") or offer.get("price")
    else:
        price = offer.get("price") if isinstance(offer, dict) else None
    return {
        "price": price,
        "currency": offer.get("priceCurrency") if isinstance(offer, dict) else None,
        "availability": offer.get("availability") if isinstance(offer, dict) else None,
    }


def _norm_product(p: dict) -> dict:
    img = _first(p.get("image"))
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl")
    out = {
        "name": p.get("name"),
        "sku": p.get("sku") or p.get("mpn"),
        "image": img,
        "description": (p.get("description") or "")[:200] or None,
        "brand": (p.get("brand") or {}).get("name")
                 if isinstance(p.get("brand"), dict) else p.get("brand"),
        "url": p.get("url") or p.get("@id"),
    }
    out.update(_norm_offer(p.get("offers")))
    return out


def _norm_itemlist(il: dict) -> list[dict]:
    items = []
    for el in il.get("itemListElement") or []:
        node = el.get("item") if isinstance(el, dict) and "item" in el else el
        if not isinstance(node, dict):
            continue
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in [x for x in types if x]:
            items.append(_norm_product(node))
        elif node.get("url") or node.get("name"):
            items.append({"name": node.get("name"), "url": node.get("url")})
    return items


def extract_structured(raw_html: str, url: str) -> StructuredData:
    sd = StructuredData()

    try:
        data = extruct.extract(raw_html, base_url=url,
                               syntaxes=["json-ld", "microdata", "opengraph"],
                               uniform=True)
    except Exception as e:  # noqa: BLE001 - malformed embedded data must not kill the pipeline
        sd.notes.append(f"extruct failed: {type(e).__name__}: {e}")
        data = {"json-ld": [], "microdata": [], "opengraph": []}

    # ---- JSON-LD (uniform=True normalizes to same shape as microdata)
    found: list[dict] = []
    _walk_jsonld(data.get("json-ld") or [], found)
    for node in found:
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        sd.raw_types_seen.extend([x for x in types if x])
        if "ItemList" in types and not sd.items:
            sd.items = _norm_itemlist(node)
            if sd.items:
                sd.sources_used.append("json-ld:ItemList")
        elif ("Product" in types or "ProductGroup" in types) and not sd.product.get("name"):
            sd.product = _norm_product(node)
            sd.sources_used.append("json-ld:Product")

    # ---- microdata fallback
    if not sd.product.get("name"):
        md: list[dict] = []
        _walk_jsonld(data.get("microdata") or [], md)
        for node in md:
            t = node.get("@type") or ""
            if "Product" in (t if isinstance(t, list) else [t]):
                sd.product = _norm_product(node)
                sd.sources_used.append("microdata:Product")
                break

    # ---- OpenGraph fill-in (never the sole source of price)
    og = {}
    for block in data.get("opengraph") or []:
        og.update(block if isinstance(block, dict) else {})
    # og:title/og:image exist on EVERY page — only treat them as product data
    # when the page declares itself a product (else listings grow phantom names)
    if og and str(og.get("og:type", "")).lower().startswith("product"):
        sd.product.setdefault("name", og.get("og:title"))
        sd.product.setdefault("image", og.get("og:image"))
        if og.get("product:price:amount") and not sd.product.get("price"):
            sd.product["price"] = og["product:price:amount"]
            sd.product["currency"] = og.get("product:price:currency")
            sd.sources_used.append("og:product")

    # ---- hydration presence (size only in v1)
    for marker, rx in HYDRATION_MARKERS.items():
        m = rx.search(raw_html)
        if m:
            payload = m.group(1) if m.groups() else ""
            sd.hydration[marker] = len(payload)

    # __NEXT_DATA__ is one clean JSON blob — cheap to actually parse for products
    if sd.hydration.get("__NEXT_DATA__") and not sd.product.get("name"):
        try:
            m = HYDRATION_MARKERS["__NEXT_DATA__"].search(raw_html)
            blob = json.loads(m.group(1))
            found = []
            _walk_jsonld(blob, found)  # products sometimes nested as LD-shaped dicts
            if found:
                sd.product = _norm_product(found[0])
                sd.sources_used.append("__NEXT_DATA__")
        except Exception:  # noqa: BLE001
            sd.notes.append("__NEXT_DATA__ present but unparseable")

    return sd


def cross_check(sd: StructuredData, raw_html: str) -> dict[str, bool]:
    """Is each L0 value actually visible in the page? Guards against build-time
    markup drift (stale price/availability)."""
    checks: dict[str, bool] = {}
    if sd.product.get("name"):
        checks["name"] = str(sd.product["name"]).strip()[:60] in raw_html
    price = sd.product.get("price")
    if price not in (None, ""):
        p = str(price)
        variants = {p, p.rstrip("0").rstrip("."), p.replace(".", ","),
                    f"{float(p):,.2f}" if re.fullmatch(r"[\d.]+", p) else p}
        checks["price"] = any(v and v in raw_html for v in variants)
    return checks
