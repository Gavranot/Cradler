"""Benchmark harness: B0 (raw) vs B1 (current prod cleaner) vs D (new pipeline).

Metrics per §5 of the brief:
  - tokens per authoring call (median/p95)
  - reduction-caused failures: GT value neither in fragment nor via validated L0
  - L0 skip candidates (coverage==1.0 and cross-check passes)
  - listing selector generalization (record_css against FULL page: count band,
    price coverage, sample-name coverage)
  - page-type classifier accuracy
Run:  uv run --project ../prototype python run_bench.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "prototype"))

from lxml import html as lhtml  # noqa: E402
from pipeline.baseline import remove_boilerplate_prod  # noqa: E402
from pipeline.pipeline import build_fragment, classify_page_type  # noqa: E402
from pipeline.reduce import reduce_html  # noqa: E402
from pipeline.structured import extract_structured, cross_check  # noqa: E402
from pipeline.tokens import count_tokens  # noqa: E402
from pipeline.listing import PRICE_RE  # noqa: E402

BENCH = Path(__file__).parent
CORPUS = BENCH / "corpus"


def norm(s: str) -> str:
    return " ".join(str(s).split()).replace("’", "'").replace("&quot;", '"').lower()


def contains(hay: str, needle: str) -> bool:
    return norm(needle) in norm(hay)


def check_detail(gt: dict, frag, l0_prod: dict, l0_ok: dict) -> dict:
    out = {}
    for fld in ("title", "price", "image_hint", "sku"):
        spec = gt.get(fld)
        if spec is None:
            continue
        if isinstance(spec, dict):
            if not spec.get("visible", True):
                out[fld] = "n/a (not in pre-render HTML)"
                continue
            variants = [spec["value"]]
        elif isinstance(spec, list):
            variants = spec
        else:
            variants = [spec]
        in_frag = any(contains(frag.text, v) for v in variants)
        via_l0 = False
        if fld == "title" and l0_prod.get("name"):
            via_l0 = any(contains(str(l0_prod["name"]), v) or contains(v, str(l0_prod["name"]))
                         for v in variants) and l0_ok.get("name", False)
        if fld == "price" and l0_prod.get("price") is not None:
            via_l0 = any(str(l0_prod["price"]).rstrip("0").rstrip(".") in v
                         for v in variants) and l0_ok.get("price", False)
        if fld == "image_hint" and l0_prod.get("image"):
            via_l0 = contains(str(l0_prod["image"]), variants[0])
        if fld == "sku" and l0_prod.get("sku"):
            via_l0 = any(contains(str(l0_prod["sku"]), v) for v in variants)
        out[fld] = "frag" if in_frag else ("l0" if via_l0 else "FAIL")
    return out


def check_listing(gt: dict, frag, raw_html: str) -> dict:
    if gt.get("expected_outcome") == "no_grid":
        # acceptable outcomes: fell back to budgeted L1, OR surfaced a candidate
        # explicitly labeled unconfirmed for the LLM to judge. Only a candidate
        # presented as corroborated is a hallucination.
        conf = (frag.listing_meta or {}).get("confidence")
        ok = frag.source_layer != "L2a" or conf == "unconfirmed"
        return {"no_grid_reported": "ok" if ok
                else f"FAIL (grid presented as corroborated: {conf})"}
    out = {}
    meta = frag.listing_meta
    if not meta:
        return {"grid": "FAIL (no grid mined)"}
    tree = lhtml.fromstring(raw_html)
    # runner contract: records are DIRECT CHILDREN of the container matching
    # record_css; fall back to page-global descendant search if that resolves
    # nothing (container path drift)
    try:
        records = tree.cssselect(f"{meta['container_css']} > {meta['record_css']}")
        if not records:
            records = tree.cssselect(meta["record_css"])
    except Exception as e:  # noqa: BLE001
        return {"grid": f"FAIL (selector invalid: {e})"}
    lo, hi = gt["count_band"]
    out["count"] = (f"ok ({len(records)})" if lo <= len(records) <= hi
                    else f"FAIL ({len(records)} not in [{lo},{hi}])")
    with_price = sum(1 for r in records[:50]
                     if PRICE_RE.search(" ".join(r.itertext())[:2000]))
    denom = min(len(records), 50) or 1
    out["price_coverage"] = (f"ok ({with_price}/{denom})"
                             if with_price / denom >= 0.6
                             else f"WEAK ({with_price}/{denom})")
    # names may live in attributes (title=, alt=, aria-label) — match serialized HTML
    missing = [n for n in gt["sample_names"]
               if not any(contains(lhtml.tostring(r, encoding="unicode"), n)
                          for r in records)]
    out["sample_names_covered"] = "ok" if not missing else f"FAIL missing {missing}"
    out["exemplar_authorable"] = ("ok" if (contains(frag.text, gt["price_marker"])
                                           and "href" in frag.text
                                           and "img" in frag.text)
                                  else "FAIL (exemplar lacks price/link/img)")
    return out


def main() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    gt_all = json.loads((BENCH / "ground_truth.json").read_text())
    results = {}
    rows = []
    for key in sorted(k for k, v in manifest.items()
                      if isinstance(v, dict) and v.get("ok")):
        site, ptype = key.split("/")
        raw = (CORPUS / site / f"{ptype}.html").read_text(errors="replace")
        url = manifest[key]["url"]

        t0 = count_tokens(raw)
        t1 = count_tokens(remove_boilerplate_prod(raw))

        start = time.perf_counter()
        frag = build_fragment(raw, url, page_type=ptype)
        elapsed = time.perf_counter() - start

        # classifier measured separately (build_fragment got the true type)
        sd = extract_structured(raw, url)
        predicted = classify_page_type(url, sd, reduce_html(raw).html)

        l0_prod = frag.l0.product if frag.l0 else {}
        l0_ok = frag.l0_cross_check
        gt = gt_all.get(key, {})
        checks = (check_detail(gt, frag, l0_prod, l0_ok) if ptype == "detail"
                  else check_listing(gt, frag, raw))

        l0_cov = frag.l0.coverage(ptype) if frag.l0 else 0.0
        l0_skip = l0_cov == 1.0 and all(l0_ok.values()) and bool(l0_ok)

        results[key] = {
            "tokens": {"raw": t0, "prod": t1, "design": frag.est_tokens},
            "source_layer": frag.source_layer,
            "classifier": {"predicted": predicted, "actual": ptype},
            "l0": {"coverage": l0_cov, "cross_check": l0_ok, "skip_candidate": l0_skip,
                   "sources": frag.l0.sources_used if frag.l0 else []},
            "checks": checks,
            "seconds": round(elapsed, 2),
        }
        fails = [f"{k}={v}" for k, v in checks.items() if str(v).startswith("FAIL")]
        rows.append((key, t0, t1, frag.est_tokens, frag.source_layer,
                     "OK" if not fails else "; ".join(fails)))

    print(f"{'page':30s} {'raw':>9} {'prod':>9} {'design':>7} {'layer':12s} verdict")
    for key, t0, t1, td, layer, verdict in rows:
        print(f"{key:30s} {t0:>9,} {t1:>9,} {td:>7,} {layer:12s} {verdict}")

    for label, idx in [("raw (B0)", 1), ("prod (B1)", 2), ("design (D)", 3)]:
        vals = sorted(r[idx] for r in rows)
        med = statistics.median(vals)
        p95 = vals[min(len(vals) - 1, int(round(0.95 * len(vals))) - 1)]
        print(f"{label:12s} median={med:>9,.0f}  p95={p95:>9,}")

    cls_ok = sum(1 for r in results.values()
                 if r["classifier"]["predicted"] == r["classifier"]["actual"])
    skip = sum(1 for k, r in results.items()
               if r["l0"]["skip_candidate"] and k.endswith("/detail"))
    n_detail = sum(1 for k in results if k.endswith("/detail"))
    hard_fails = sum(1 for r in results.values()
                     for v in r["checks"].values() if str(v).startswith("FAIL"))
    print(f"\nclassifier: {cls_ok}/{len(results)} correct")
    print(f"L0 full-skip candidates (detail): {skip}/{n_detail}")
    print(f"reduction-caused FAILs: {hard_fails}")

    (BENCH / "results.json").write_text(json.dumps(results, indent=1))
    print(f"\nresults → {BENCH / 'results.json'}")


if __name__ == "__main__":
    main()
