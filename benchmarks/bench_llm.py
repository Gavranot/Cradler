"""LLM-in-the-loop benchmark: does the reduced fragment actually let a model
author a working ExtractionSpec — and at what pass rate vs the full page?

Arms (same model, same prompt shape, same validator):
  design    — routed fragment (L0 structured hint + exemplar/slices)  [new pipeline]
  fullpage  — prod-cleaned full HTML, token-capped                    [status quo]

Per page: up to MAX_ATTEMPTS; attempt 2+ receives the mechanical validation
errors as feedback (mirrors the production repair loop). Validation always runs
against the FULL raw HTML. A repair phase then mutates each detail page
(class-rename on the price chain) and asks the model to fix the previously
authored spec from a fresh fragment.

Cost discipline: spend is metered against BENCH_BUDGET_USD (hard stop, graceful).
Config via env: BENCH_LLM_MODEL, BENCH_LLM_INPUT_PRICE_PER_M,
BENCH_LLM_OUTPUT_PRICE_PER_M, BENCH_BUDGET_USD, OPENROUTER_API_KEY.

Run:  uv run --project ../prototype python bench_llm.py [--limit N] [--arm design|fullpage|both]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "prototype"))
sys.path.insert(0, str(Path(__file__).parent))

import httpx  # noqa: E402
from lxml import html as lhtml  # noqa: E402

from pipeline.baseline import remove_boilerplate_prod  # noqa: E402
from pipeline.listing import PRICE_RE  # noqa: E402
from pipeline.pipeline import build_fragment  # noqa: E402
from pipeline.tokens import count_tokens  # noqa: E402
from bench_repair import mutate  # noqa: E402

BENCH = Path(__file__).parent
CORPUS = BENCH / "corpus"

# ---------------- config ----------------


def _load_env() -> None:
    env = Path("/workspace/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
MODEL = os.environ.get("BENCH_LLM_MODEL", "deepseek/deepseek-v4-pro")
IN_PRICE = float(os.environ.get("BENCH_LLM_INPUT_PRICE_PER_M", "0.435"))
OUT_PRICE = float(os.environ.get("BENCH_LLM_OUTPUT_PRICE_PER_M", "0.87"))
BUDGET = float(os.environ.get("BENCH_BUDGET_USD", "8.0"))
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
FULLPAGE_CAP = 48_000  # tokens
MAX_ATTEMPTS = 2

spent_usd = 0.0
calls_made = 0


class BudgetExceeded(RuntimeError):
    pass


def llm(messages: list[dict], max_tokens: int = 1500) -> str:
    global spent_usd, calls_made
    if spent_usd >= BUDGET:
        raise BudgetExceeded(f"spent ${spent_usd:.2f} >= budget ${BUDGET}")
    for attempt in range(3):
        try:
            r = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": MODEL, "messages": messages,
                      "temperature": 0, "max_tokens": max_tokens},
                timeout=180,
            )
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            usage = data.get("usage", {})
            spent_usd += (usage.get("prompt_tokens", 0) * IN_PRICE
                          + usage.get("completion_tokens", 0) * OUT_PRICE) / 1e6
            calls_made += 1
            # some providers return content: null / "" (reasoning-only glitch).
            # That's a transport artifact, not a model answer — retry, don't
            # let it burn one of the page's authoring attempts.
            content = data["choices"][0]["message"].get("content") or ""
            if content.strip():
                return content
            if attempt < 2:
                time.sleep(2)
                continue
            return ""
        except (httpx.HTTPStatusError, httpx.TransportError, KeyError) as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------------- prompts ----------------

DETAIL_SYS = (
    "You are a web-scraping engineer. Given page context, output ONLY a JSON "
    "object (no prose, no code fences):\n"
    '{"fields": [{"name": "<field>", "css": "<selector>", "attr": "<attribute '
    'or omit for text>"}]}\n'
    "Required field names: title, price, image. Selectors must work with "
    "lxml.cssselect (no :has, no jQuery extensions). Prefer stable hooks "
    "(itemprop, data-*, ids, semantic classes)."
)

LISTING_SYS = (
    "You are a web-scraping engineer. Given page context from a product LISTING "
    "page, output ONLY a JSON object (no prose, no code fences):\n"
    '{"record_selector": "<css matching each product card on the page>", '
    '"fields": [{"name": "name", "css": "<relative to card>"}, '
    '{"name": "price", "css": "<relative>"}, '
    '{"name": "url", "css": "<relative>", "attr": "href"}]}\n'
    "Selectors must work with lxml.cssselect (no :has, no jQuery extensions)."
)


def detail_user(context: str, structured: dict) -> str:
    sd = ""
    if structured:
        sd = ("\nMachine-readable data found on the page (cross-checked, use as "
              f"ground truth for values): {json.dumps(structured)[:600]}\n")
    return f"Author the extraction spec for this product detail page.{sd}\n{context}"


def listing_user(context: str) -> str:
    return f"Author the extraction spec for this listing page.\n{context}"


# ---------------- validation (against FULL raw html) ----------------


def norm(s: str) -> str:
    return " ".join(str(s).split()).replace("’", "'").replace("&quot;", '"').lower()


def sel(root, css: str):
    try:
        return root.cssselect(css)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"invalid selector {css!r}: {e}") from e


def value_of(el, attr: str | None) -> str:
    if attr:
        return el.get(attr) or ""
    return " ".join(el.itertext())


def validate_detail(spec: dict, raw: str, gt: dict) -> list[str]:
    errors: list[str] = []
    tree = lhtml.fromstring(raw)
    fields = {f.get("name"): f for f in spec.get("fields", []) if isinstance(f, dict)}
    for name in ("title", "price", "image"):
        gt_key = "image_hint" if name == "image" else name
        gt_spec = gt.get(gt_key)
        if gt_spec is None or (isinstance(gt_spec, dict) and not gt_spec.get("visible", True)):
            continue  # field not verifiable pre-render — don't penalize either arm
        f = fields.get(name)
        if not f or not f.get("css"):
            errors.append(f"{name}: no selector provided")
            continue
        try:
            els = sel(tree, f["css"])
        except ValueError as e:
            errors.append(f"{name}: {e}")
            continue
        if not els:
            errors.append(f"{name}: selector {f['css']!r} matches nothing")
            continue
        variants = gt_spec if isinstance(gt_spec, list) else [gt_spec]
        vals = [norm(value_of(el, f.get("attr"))) for el in els[:5]]
        if name == "image":
            ok = any(norm(gt_spec) in norm(el.get("src") or el.get("content")
                                           or el.get("href") or value_of(el, f.get("attr")))
                     for el in els[:5])
        else:
            ok = any(any(norm(v) in val for v in variants) for val in vals)
        if not ok:
            errors.append(f"{name}: matched nodes do not contain expected value "
                          f"(got {vals[0][:60]!r})")
    return errors


def validate_listing(spec: dict, raw: str, gt: dict) -> list[str]:
    errors: list[str] = []
    tree = lhtml.fromstring(raw)
    rs = spec.get("record_selector")
    if not rs:
        return ["record_selector missing"]
    try:
        records = sel(tree, rs)
    except ValueError as e:
        return [str(e)]
    lo, hi = gt["count_band"]
    if not (lo <= len(records) <= hi):
        errors.append(f"record_selector matches {len(records)} records, expected {lo}-{hi}")
        return errors
    missing = [n for n in gt["sample_names"]
               if not any(norm(n) in norm(lhtml.tostring(r, encoding="unicode"))
                          for r in records)]
    if missing:
        errors.append(f"records do not cover known products: {missing}")
    fields = {f.get("name"): f for f in spec.get("fields", []) if isinstance(f, dict)}
    for name in ("name", "price", "url"):
        f = fields.get(name)
        if not f or not f.get("css"):
            errors.append(f"{name}: no relative selector")
            continue
        try:
            hits = sum(1 for r in records[:20]
                       if any(value_of(el, f.get("attr")).strip()
                              for el in r.cssselect(f["css"])))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: invalid selector: {e}")
            continue
        denom = min(len(records), 20)
        if hits / denom < 0.6:
            errors.append(f"{name}: relative selector yields values on only "
                          f"{hits}/{denom} cards")
    return errors


# ---------------- contexts per arm ----------------


def context_design(raw: str, url: str, ptype: str) -> tuple[str, dict]:
    frag = build_fragment(raw, url, page_type=ptype)
    structured = {}
    if frag.l0 is not None and frag.l0.product and ptype == "detail":
        checked = frag.l0_cross_check
        structured = {k: v for k, v in frag.l0.product.items()
                      if v not in (None, "", []) and checked.get(k, True)}
    header = ""
    if frag.listing_meta:
        header = (f"Mined grid: container `{frag.listing_meta['container_css']}`, "
                  f"record `{frag.listing_meta['record_css']}`, "
                  f"{frag.listing_meta['record_count']} records. One exemplar card:\n")
    return header + frag.text, structured


def context_fullpage(raw: str) -> str:
    cleaned = remove_boilerplate_prod(raw)
    t = count_tokens(cleaned)
    if t > FULLPAGE_CAP:
        cleaned = cleaned[: int(len(cleaned) * FULLPAGE_CAP / t)]
    return cleaned


# ---------------- main loops ----------------


def author(page_key: str, arm: str, raw: str, url: str, gt: dict) -> dict:
    ptype = "detail" if page_key.endswith("/detail") else "listing"
    if arm == "design":
        context, structured = context_design(raw, url, ptype)
    else:
        context, structured = context_fullpage(raw), {}
    sys_p = DETAIL_SYS if ptype == "detail" else LISTING_SYS
    user_p = detail_user(context, structured) if ptype == "detail" else listing_user(context)
    messages = [{"role": "system", "content": sys_p},
                {"role": "user", "content": user_p}]
    ctx_tokens = count_tokens(user_p)
    result = {"context_tokens": ctx_tokens, "attempts": 0, "passed": False,
              "errors": [], "spec": None}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        reply = llm(messages)
        spec = parse_json(reply)
        if spec is None:
            errors = ["reply was not valid JSON"]
        else:
            validate = validate_detail if ptype == "detail" else validate_listing
            errors = validate(spec, raw, gt)
        result["spec"] = spec
        result["errors"] = errors
        result.setdefault("error_history", []).append(errors)
        if not errors:
            result["passed"] = True
            break
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content":
                      "Validation against the full page failed:\n- "
                      + "\n- ".join(errors)
                      + "\nFix the spec. Output ONLY the corrected JSON."}]
    return result


def repair(page_key: str, raw: str, url: str, gt: dict, old_spec: dict) -> dict | None:
    price = gt.get("price")
    if not isinstance(price, list):
        return None
    mutated = mutate(raw, price, "class-rename")
    if mutated is None:
        return None
    # sanity: does the old spec still pass on the mutated page?
    if not validate_detail(old_spec, mutated, gt):
        return {"skipped": "spec survived mutation (no repair needed)"}
    context, structured = context_design(mutated, url, "detail")
    messages = [
        {"role": "system", "content": DETAIL_SYS},
        {"role": "user", "content":
         f"A previously working extraction spec broke after a site update.\n"
         f"Old spec: {json.dumps(old_spec)[:800]}\n"
         f"Repair it for the CURRENT page below. Output ONLY the corrected JSON."
         + ("\nMachine-readable data (cross-checked): "
            + json.dumps(structured)[:600] if structured else "")
         + f"\n{context}"},
    ]
    out = {"attempts": 0, "passed": False, "context_tokens": count_tokens(messages[1]["content"])}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out["attempts"] = attempt
        reply = llm(messages)
        spec = parse_json(reply)
        errors = ["not JSON"] if spec is None else validate_detail(spec, mutated, gt)
        if not errors:
            out["passed"] = True
            break
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "Still failing:\n- " + "\n- ".join(errors)
                      + "\nOutput ONLY the corrected JSON."}]
        out["errors"] = errors
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--arm", choices=["design", "fullpage", "both"], default="both")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("OPENROUTER_API_KEY not set")
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    gt_all = json.loads((BENCH / "ground_truth.json").read_text())
    pages = [k for k in sorted(gt_all) if not k.startswith("_")
             and gt_all[k].get("expected_outcome") != "no_grid"]
    if args.limit:
        pages = pages[: args.limit]
    arms = ["design", "fullpage"] if args.arm == "both" else [args.arm]

    results: dict = {"model": MODEL, "arms": {a: {} for a in arms}, "repair": {}}
    try:
        for arm in arms:
            for key in pages:
                site, ptype = key.split("/")
                raw = (CORPUS / site / f"{ptype}.html").read_text(errors="replace")
                url = manifest[key]["url"]
                r = author(key, arm, raw, url, gt_all[key])
                results["arms"][arm][key] = r
                status = "PASS" if r["passed"] else "FAIL"
                print(f"[{arm:8s}] {key:28s} {status} attempts={r['attempts']} "
                      f"ctx={r['context_tokens']:>6,}tok  spent=${spent_usd:.3f}")
        # repair phase — design arm, detail pages whose authoring passed
        for key in pages:
            if not key.endswith("/detail"):
                continue
            base = results["arms"].get("design", {}).get(key)
            if not base or not base["passed"]:
                continue
            site = key.split("/")[0]
            raw = (CORPUS / site / "detail.html").read_text(errors="replace")
            r = repair(key, raw, manifest[key]["url"], gt_all[key], base["spec"])
            if r is None:
                continue
            results["repair"][key] = r
            if "skipped" in r:
                print(f"[repair  ] {key:28s} SKIP ({r['skipped']})")
            else:
                print(f"[repair  ] {key:28s} {'PASS' if r['passed'] else 'FAIL'} "
                      f"attempts={r['attempts']}  spent=${spent_usd:.3f}")
    except BudgetExceeded as e:
        print(f"\n!! budget stop: {e}")

    # summary
    print(f"\n=== {MODEL} | {calls_made} calls | ${spent_usd:.3f} spent ===")
    for arm in arms:
        rs = list(results["arms"][arm].values())
        if not rs:
            continue
        p1 = sum(1 for r in rs if r["passed"] and r["attempts"] == 1)
        p2 = sum(1 for r in rs if r["passed"])
        ctx = [r["context_tokens"] for r in rs]
        att = [r["attempts"] for r in rs if r["passed"]]
        print(f"{arm:9s} pass@1 {p1}/{len(rs)}  pass@{MAX_ATTEMPTS} {p2}/{len(rs)}  "
              f"median ctx {statistics.median(ctx):,.0f} tok  "
              f"mean attempts (passed) {statistics.mean(att) if att else 0:.2f}")
    reps = [r for r in results["repair"].values() if "skipped" not in r]
    if reps:
        print(f"repair    pass {sum(1 for r in reps if r['passed'])}/{len(reps)}  "
              f"mean attempts {statistics.mean(r['attempts'] for r in reps):.2f}")
    results["spent_usd"] = round(spent_usd, 4)
    results["calls"] = calls_made
    (BENCH / "results_llm.json").write_text(json.dumps(results, indent=1))
    print(f"→ {BENCH / 'results_llm.json'}")


if __name__ == "__main__":
    main()
