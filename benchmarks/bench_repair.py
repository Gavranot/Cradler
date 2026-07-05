"""Simulated-break repair benchmark (no LLM calls).

For each detail page with a visible GT price, we simulate the maintenance
scenario: the site ships a markup change that breaks an authored selector.

Mutations (applied to the RAW html):
  M1 class-rename  — every class token on the price node's element chain gets a
                     hashed suffix (simulates CSS-module/theme redeploy)
  M2 wrap          — price node wrapped in two extra <div>s (layout refactor)
  M3 tag-change    — price element's tag swapped (span→div or div→span)

Measured per mutation:
  broke        — does a naive class-based selector authored on the ORIGINAL page
                 stop matching on the mutated page? (sanity: mutations must bite)
  frag_ok      — does build_fragment(mutated) still contain the GT price, i.e.
                 the repair LLM would SEE the target? (repairability)
  frag_tokens  — cost of the repair-call input under the new design
  diff_tokens  — cost under A7 DOM-diff repair: only changed regions of the
                 reduced HTML (difflib over reduced lines, ±3 lines context)
Listings get one mutation: rename ALL class tokens on card subtrees (worst-case
theme redeploy) → does tag-only fingerprint mining still find the grid?
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "prototype"))

from lxml import html as lhtml  # noqa: E402
from pipeline.listing import PRICE_RE, mine_listing  # noqa: E402
from pipeline.pipeline import build_fragment  # noqa: E402
from pipeline.reduce import reduce_html  # noqa: E402
from pipeline.tokens import count_tokens  # noqa: E402

BENCH = Path(__file__).parent
CORPUS = BENCH / "corpus"


def norm(s: str) -> str:
    return " ".join(str(s).split()).lower()


def find_price_node(tree, variants: list[str]):
    for el in tree.iter():
        if isinstance(el.tag, str) and el.text:
            if any(norm(v) in norm(el.text) for v in variants):
                return el
    return None


def naive_selector(el) -> str | None:
    """What today's generator typically authors: class-based CSS."""
    cur = el
    while cur is not None:
        cls = (cur.get("class") or "").split()
        if cls:
            return f"{cur.tag}.{cls[0]}"
        cur = cur.getparent()
    return None


def _hash_classes(el) -> None:
    cls = el.get("class")
    if cls:
        el.set("class", " ".join(
            f"{t}-{hashlib.md5(t.encode()).hexdigest()[:5]}" for t in cls.split()))


def mutate(raw: str, variants: list[str], kind: str) -> str | None:
    tree = lhtml.fromstring(raw)
    node = find_price_node(tree, variants)
    if node is None:
        return None
    if kind == "class-rename":
        cur = node
        for _ in range(6):
            if cur is None:
                break
            _hash_classes(cur)
            cur = cur.getparent()
    elif kind == "wrap":
        parent = node.getparent()
        if parent is None:
            return None
        idx = parent.index(node)
        w1 = parent.makeelement("div", {"class": "pw-outer"})
        w2 = parent.makeelement("div", {"class": "pw-inner"})
        parent.remove(node)
        w2.append(node)
        w1.append(w2)
        parent.insert(idx, w1)
    elif kind == "tag-change":
        node.tag = "div" if node.tag != "div" else "span"
    return lhtml.tostring(tree, encoding="unicode")


def diff_fragment(orig_reduced: str, mut_reduced: str, ctx: int = 3) -> str:
    a, b = orig_reduced.splitlines(), mut_reduced.splitlines()
    out: list[str] = []
    for group in difflib.SequenceMatcher(None, a, b).get_grouped_opcodes(ctx):
        for tag_, i1, i2, j1, j2 in group:
            if tag_ != "equal":
                out.extend(b[j1:j2])
    return "\n".join(out)


def main() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    gt_all = json.loads((BENCH / "ground_truth.json").read_text())
    rows = []

    for key, gt in gt_all.items():
        if not key.endswith("/detail") or key.startswith("_"):
            continue
        price = gt.get("price")
        if not isinstance(price, list):        # not visible pre-render → skip
            continue
        site = key.split("/")[0]
        raw = (CORPUS / site / "detail.html").read_text(errors="replace")
        url = manifest[key]["url"]
        orig_reduced = reduce_html(raw).html

        tree = lhtml.fromstring(raw)
        node = find_price_node(tree, price)
        if node is None:
            rows.append((key, "-", "price node not found in raw", 0, 0, 0))
            continue
        sel = naive_selector(node)

        for kind in ("class-rename", "wrap", "tag-change"):
            mut = mutate(raw, price, kind)
            if mut is None:
                continue
            mtree = lhtml.fromstring(mut)
            try:
                still = mtree.cssselect(sel) if sel else []
            except Exception:  # noqa: BLE001
                still = []
            hits_price = any(PRICE_RE.search(" ".join(m.itertext()) or "")
                             for m in still)
            broke = not hits_price
            frag = build_fragment(mut, url, page_type="detail")
            frag_ok = any(norm(v) in norm(frag.text) for v in price)
            dtext = diff_fragment(orig_reduced, reduce_html(mut).html)
            d_ok = any(norm(v) in norm(dtext) for v in price)
            rows.append((key, kind, "broke" if broke else "survived",
                         "yes" if frag_ok else "NO",
                         frag.est_tokens,
                         f"{count_tokens(dtext):,}{'' if d_ok else ' (!miss)'}"))

    print(f"{'page':26s} {'mutation':13s} {'naive sel':9s} {'frag_ok':7s} "
          f"{'frag_tok':>8s} {'diff_tok':>10s}")
    for r in rows:
        print(f"{r[0]:26s} {r[1]:13s} {r[2]:9s} {r[3]:7s} {r[4]:>8} {r[5]:>10}")

    # listing worst-case: global class rename
    print("\nlisting theme-redeploy simulation (ALL classes hashed):")
    for key in [k for k in gt_all if k.endswith("/listing")
                and gt_all[k].get("count_band")]:
        site = key.split("/")[0]
        raw = (CORPUS / site / "listing.html").read_text(errors="replace")
        tree = lhtml.fromstring(raw)
        for el in tree.iter():
            if isinstance(el.tag, str):
                _hash_classes(el)
        mut = lhtml.tostring(tree, encoding="unicode")
        ex = mine_listing(reduce_html(mut).html)
        lo, hi = gt_all[key]["count_band"]
        ok = ex is not None and lo <= ex.record_count <= hi
        print(f"  {site:22s} {'grid re-found, count ' + str(ex.record_count) if ex else 'LOST'}"
              f"  {'OK' if ok else 'CHECK'}")


if __name__ == "__main__":
    main()
