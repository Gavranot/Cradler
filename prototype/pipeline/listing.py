"""Layer 2a — listing-page repeated-record mining via tag-path fingerprinting.

Descended from Tag-Path Clustering (Miao et al., WWW 2009) rather than MDR
(F1=0.083 on modern pages, NEXT-EVAL arXiv:2505.17125). Fingerprints use TAG
STRUCTURE ONLY — robust to obfuscated/hashed class names; classes are used
afterwards, only to build a human-quality CSS selector for the mined container.

Output: the container, a record selector, ONE exemplar card (+ a second iff the
group is structurally heterogeneous), and the record count. The LLM never sees
the other N-1 cards.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from lxml import etree, html as lhtml

MIN_RECORDS = 4
MAX_FP_DEPTH = 3
MIN_CARD_CHARS = 150          # menus/toolbars are smaller than product cards
# RANKING HINT, not a gate (see mine_listing): symbol-prefixed, ISO-4217-code-
# prefixed (geo-localized shops: "MKD 3,100" / Cyrillic "МКД"), and symbol/word-
# suffixed price shapes ("1.200 ден")
PRICE_RE = re.compile(
    r"[$€£¥]\s*\d{1,6}(?:[.,]\d{2,3})?"
    r"|\b(?:[A-Z]{3}|МКД|РСД|ЛВ)\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\b"
    r"|\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\s*(?:€|zł|kr|ден|лв|дин)\.?")


@dataclass
class ListingExtract:
    container_css: str
    record_css: str
    exemplar_html: str
    record_count: int
    second_exemplar_html: str | None = None
    # "corroborated": cards show price/image signals — very likely a product grid.
    # "unconfirmed": strongest repeated linked structure on the page, but the
    # cheap signals couldn't confirm it — the LLM must inspect and decide.
    confidence: str = "corroborated"
    stats: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _fingerprint(el: etree._Element, depth: int = MAX_FP_DEPTH) -> tuple:
    """Structural fingerprint: tag + sorted child fingerprints down to `depth`.

    Sorted (not sequenced) child sets tolerate reordered/optional sub-elements
    (badges, sale flags) that vary between cards of the same grid.
    """
    if depth == 0:
        return (el.tag,)
    return (el.tag, tuple(sorted(_fingerprint(c, depth - 1) for c in el
                                 if isinstance(c.tag, str))))


def _subtree_chars(el: etree._Element) -> int:
    return len(lhtml.tostring(el, encoding="unicode"))


def _stable_classes(elements: list[etree._Element]) -> list[str]:
    """Class tokens shared by ALL elements, longest/most specific first."""
    common: set[str] | None = None
    for el in elements:
        toks = set((el.get("class") or "").split())
        common = toks if common is None else common & toks
    if not common:
        return []
    return sorted(common, key=lambda t: (-len(t), t))


def _looks_obfuscated(token: str) -> bool:
    if "__" in token or re.fullmatch(r"css-[a-z0-9]+", token):
        return True
    # short lowercase hash with digits (CSS modules: "x7k2d")
    if re.fullmatch(r"[a-z0-9]{1,6}", token) and re.search(r"\d", token):
        return True
    # short mixed-case random with no separators (styled-components/emotion
    # generated names: "gNMTEq", "kLgRZs") — real class names of that length
    # are either single words or use -/_ separators
    return bool(re.fullmatch(r"[A-Za-z]{4,8}", token)
                and re.search(r"[a-z][A-Z]", token))


def _selector_safe(token: str) -> bool:
    """Usable in a CSS selector without escaping AND plausibly stable.
    Tailwind variant classes (`max-sm:min-h-86`, `lg:w-1/2`) are both unsafe
    and volatile — never build selectors from them."""
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", token)) \
        and not _looks_obfuscated(token)


def _css_path(el: etree._Element, root: etree._Element) -> str:
    """Short, stable CSS path root→el: prefer id, else tag(+first stable class)."""
    parts: list[str] = []
    cur = el
    while cur is not None and cur is not root:
        if cur.get("id"):
            i = cur.get("id")
            parts.append(f"#{i}" if _selector_safe(i) else f"[id='{i}']")
            break
        tok = next((t for t in (cur.get("class") or "").split()
                    if _selector_safe(t)), None)
        parts.append(f"{cur.tag}.{tok}" if tok else str(cur.tag))
        cur = cur.getparent()
    return " > ".join(reversed(parts)) or str(el.tag)


def _score_group(members: list[etree._Element]) -> tuple[float, dict]:
    n = len(members)
    sizes = [_subtree_chars(m) for m in members[:20]]
    avg_size = sum(sizes) / len(sizes)
    sample = members[:20]
    with_link = sum(1 for m in sample if m.tag == "a" or m.xpath(".//a[@href]"))
    with_img = sum(1 for m in sample if m.tag == "img" or m.xpath(".//img"))
    with_price = sum(1 for m in sample
                     if PRICE_RE.search(" ".join(m.itertext())[:2000] or ""))
    hrefs = set()
    for m in sample:
        for a in ([m] if m.tag == "a" else m.xpath(".//a[@href]")):
            if a.get("href"):
                hrefs.add(a.get("href"))
    k = len(sample)
    corroboration = 0.5 * (with_link / k) + 0.3 * (with_img / k) + 0.2 * (with_price / k)
    score = n * avg_size * (0.25 + corroboration)
    return score, {"count": n, "avg_chars": int(avg_size),
                   "link_ratio": with_link / k, "img_ratio": with_img / k,
                   "price_ratio": with_price / k, "distinct_hrefs": len(hrefs)}


def _plausible_grid(stats: dict) -> bool:
    """Corroboration gate: a real product grid links to DISTINCT product pages and
    almost always shows prices. Kills mini-carts, nav rails, and menu groups."""
    if stats["distinct_hrefs"] < MIN_RECORDS:
        return False
    if stats["price_ratio"] >= 0.4:
        return True
    # priceless grids exist (lookbooks); accept only with strong img+link signal
    return stats["img_ratio"] >= 0.8 and stats["link_ratio"] >= 0.9 and stats["count"] >= 8


def _find_best_group(
    root: etree._Element,
) -> tuple[etree._Element, list[etree._Element], dict, str] | None:
    """Rank candidate record groups. Corroborated candidates win; the strongest
    UNCONFIRMED candidate is still returned (labeled) rather than discarded —
    heuristics here rank and compress, only the LLM may reject.
    """
    best_ok: tuple | None = None
    best_weak: tuple | None = None
    for parent in root.iter(etree.Element):
        kids = [c for c in parent if isinstance(c.tag, str)]
        if len(kids) < MIN_RECORDS:
            continue
        groups: dict[tuple, list[etree._Element]] = {}
        for c in kids:
            groups.setdefault(_fingerprint(c), []).append(c)
        for fp, members in groups.items():
            if len(members) < MIN_RECORDS:
                continue
            if _subtree_chars(members[0]) < MIN_CARD_CHARS:
                continue
            score, stats = _score_group(members)
            # definitional floor, not judgment: listing records exist to link to
            # detail pages — repeated blocks with no distinct links are chrome
            if stats["link_ratio"] < 0.5 or stats["distinct_hrefs"] < 3:
                continue
            if _plausible_grid(stats):
                if best_ok is None or score > best_ok[0]:
                    best_ok = (score, parent, members, stats)
            elif best_weak is None or score > best_weak[0]:
                best_weak = (score, parent, members, stats)
    if best_ok is not None:
        return best_ok[1], best_ok[2], best_ok[3], "corroborated"
    if best_weak is not None:
        return best_weak[1], best_weak[2], best_weak[3], "unconfirmed"
    return None


def mine_listing(reduced_html: str) -> ListingExtract | None:
    tree = lhtml.fromstring(reduced_html)
    notes: list[str] = []

    found = _find_best_group(tree)
    if found is None:
        return None
    container, members, stats, confidence = found

    # Nested-grid descent: sites that render N repeated SECTIONS each holding
    # cards (e.g. featured-collection mounts) make the section group win on mass.
    # If a member's subtree itself contains a qualifying group, descend and
    # re-aggregate the inner records across ALL outer members.
    for _ in range(2):  # at most two levels of descent
        inner = _find_best_group(members[0])
        if inner is None:
            break
        _, inner_members, inner_stats, _inner_conf = inner
        inner_fp = _fingerprint(inner_members[0])
        all_inner = [el for m in members for el in m.iter(etree.Element)
                     if isinstance(el.tag, str) and _fingerprint(el) == inner_fp]
        if len(all_inner) <= len(members):
            break
        notes.append(f"descended into nested grid: {len(members)} sections → "
                     f"{len(all_inner)} records")
        container = members[0].getparent() if len(members) == 1 else container
        members = all_inner
        _, stats = _score_group(members)
        confidence = "corroborated" if _plausible_grid(stats) else "unconfirmed"

    if confidence == "unconfirmed":
        weak = [s for s, r in (("price", stats["price_ratio"]),
                               ("image", stats["img_ratio"])) if r < 0.4]
        notes.append(
            f"UNCONFIRMED candidate: repeated linked structure ×{stats['count']}, "
            f"but no {'/'.join(weak) or 'product'} signals detected in the cards. "
            "Inspect the exemplar and decide whether these are product records.")

    # record selector: try candidates and VALIDATE precision against the mined
    # member set (a shared utility class like `transition-all` can also match
    # unrelated nodes — shared is necessary, discriminative is required).
    container_css = _css_path(container, tree)
    tag = str(members[0].tag)
    candidates: list[str] = []
    # a data-testid/data-test/data-qa value shared by every card is the most
    # deploy-stable hook there is — try it before any class
    for attr in ("data-testid", "data-test", "data-qa", "data-component"):
        vals = {m.get(attr) for m in members}
        if len(vals) == 1 and next(iter(vals)):
            candidates.append(f'{tag}[{attr}="{next(iter(vals))}"]')
    classes = [c for c in _stable_classes(members) if _selector_safe(c)]
    candidates += [f"{tag}.{c}" for c in classes[:4]]
    if len(classes) >= 2:
        candidates.append(f"{tag}.{classes[0]}.{classes[1]}")
    candidates.append(tag)  # direct-child tag fallback

    member_set = set(map(id, members))
    record_css, best_extra = None, None
    for cand in candidates:
        try:
            matches = tree.cssselect(f"{container_css} > {cand}")
        except Exception:  # noqa: BLE001
            continue
        hit = sum(1 for m in matches if id(m) in member_set)
        extra = len(matches) - hit
        if hit == len(members) and (best_extra is None or extra < best_extra):
            record_css, best_extra = cand, extra
            if extra == 0:
                break
    final_count = stats["count"]
    if record_css is None:
        record_css = tag
        notes.append("no precise candidate — tag fallback (runner must validate per-card)")
    else:
        # the selector may legitimately match MORE than the fingerprint group:
        # structural variants of the same card (badges, sale flags) are still
        # records. Report the selector's match count, keep group size in notes.
        try:
            final_count = len(tree.cssselect(f"{container_css} > {record_css}"))
        except Exception:  # noqa: BLE001
            pass
        notes.append(f"record selector '{record_css}': matches {final_count} "
                     f"(fingerprint group {len(members)})")

    # heterogeneity: if >1 fingerprint variant among ALL same-parent siblings that
    # match record_css loosely, expose a second exemplar
    second = None
    variant_fps = Counter(_fingerprint(m) for m in members)
    if len(variant_fps) > 1:
        rare_fp = variant_fps.most_common()[-1][0]
        second = next(m for m in members if _fingerprint(m) == rare_fp)
        notes.append(f"heterogeneous group ({len(variant_fps)} structural variants) — "
                     "second exemplar included")

    exemplar = lhtml.tostring(members[0], encoding="unicode")
    return ListingExtract(
        container_css=container_css,
        record_css=record_css,
        exemplar_html=exemplar,
        record_count=final_count,
        second_exemplar_html=(lhtml.tostring(second, encoding="unicode")
                              if second is not None else None),
        confidence=confidence,
        stats=stats,
        notes=notes + [f"stats: {stats}"],
    )
