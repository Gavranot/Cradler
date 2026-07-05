# BENCHMARKS.md — HTML-Reduction Pipeline, before/after

Corpus: 22 saved real pages (11 sites × listing+detail) across static, Shopify ×4,
Shopify-headless, Next.js, Magento (Hyvä), BigCommerce, WooCommerce. Fetched once
(2026-07-03, plain HTTP per project decision — pre-render HTML), cached under
`benchmarks/corpus/`, deterministic. Harness: `benchmarks/run_bench.py` (tokens +
ground-truth checks) and `benchmarks/bench_repair.py` (simulated breaks). Raw
per-page output: `benchmarks/results.json`.

Comparators:
- **B0** — raw HTML (what a naive implementation sends).
- **B1** — current production cleaner (`_remove_boilerplate`, faithful port).
- **D** — new pipeline (L0 structured probe → L1 reduce → L2a exemplar mining /
  L2b anchor slicing → token budget).

## Headline: tokens per authoring call (tiktoken cl100k)

| Metric | B0 raw | B1 current prod | D new design | D vs B0 | D vs B1 |
|---|---:|---:|---:|---:|---:|
| median | 107,494 | 23,098 | **1,053** | **102×** | **22×** |
| p95 | 587,150 | 256,006 | **6,144** | 96× | 42× |
| worst page (allbirds listing) | 1,123,440 | 451,914 | **1,415** | 794× | 319× |

Per-page table: run `uv run --project ../prototype python run_bench.py` in
`benchmarks/` or see `results.json`. Detail pages land at 576–2,806 tokens
(median 1,303); mined listings at 307–1,415 (median 565); the two client-rendered
listings (bombas, rothys) fall back to budget-capped L1 at ≤6,328 tokens with an
explicit "no grid — client-rendered" note rather than a hallucinated grid.

## Reduction-caused failures (the key risk metric)

**0 / 22 pages.** Every ground-truth field (title, price, image, sku where
pre-render-visible) is either present in the fragment handed to the LLM or covered
by cross-checked structured data. Two early GT labeling errors (a nav link
mistaken for a card; a circular count band) were found and corrected — documented
in `ground_truth.json`.

## Layer contribution

| Stat | Value | Meaning |
|---|---|---|
| L0 full-skip candidates | **7/11 detail pages** | JSON-LD/microdata covers name+price AND cross-checks against the DOM → spec derivable with no HTML and (optionally) no LLM |
| L0 on listings | **0/11** | No usable ItemList anywhere — the baseline's "skip HTML" path is a detail-page-only lever |
| L2a mined grids | 9/9 minable listings | exemplar+count, 100% price/img/link corroboration, selectors precision-checked |
| Page-type classifier | 22/22 | ordered signals: ItemList → product+cart → grid≥8 → product+price → cart+single-h1 → URL |

## Repair simulation (no LLM; 30 mutations + 9 theme-redeploys)

Mutations per detail page: class-rename on the price node chain, wrapper-div
insertion, tag swap. A naive class-based selector (what today's generator writes)
broke in 8/30 cases — all class-renames — confirming the repair scenario is real.

| Metric | Result |
|---|---|
| Fragment still localizes the price post-mutation | 27/30 in-fragment + 3/3 via L0 (JSON-LD untouched by DOM mutations) = **30/30 repairable** |
| Repair-call input size | 576–2,806 tokens (same as authoring) |
| Listing grids re-found after ALL classes hashed (worst-case theme redeploy) | **9/9** — tag-only structural fingerprints are class-obfuscation-proof |
| A7 DOM-diff repair (line-diff of reduced HTML) | Mixed: 11–176 tokens when pages are stable, but 6–8K tokens + missed targets on churny pages. Needs DOM-aware diffing; recommended as future hybrid (diff to localize → L2b slice around change), not v1. |

## Cost proxy (Claude Fable 5 pricing: $10/MTok input, June 2026)

Input-side cost of ONE authoring call carrying the page context:

| | B0 raw | B1 prod | D design |
|---|---:|---:|---:|
| median page | $1.07 | $0.23 | **$0.011** |
| p95 page | $5.87 | $2.56 | **$0.061** |

Two amplifiers make real savings larger than one-call arithmetic: (1) the
authoring loop is a ReAct conversation of up to 30 iterations — page context is
re-read (re-billed, 0.1× if cached) on every subsequent turn, so oversized context
multiplies; (2) cheap-model triage (Haiku 4.5, $1/MTok) becomes viable for
classification/exemplar-choice once fragments are small.

**Caveats, honestly stated:**
- Token counts are tiktoken (cl100k) — Anthropic documents that it undercounts
  Claude tokens by ~15–20%, so absolute $ figures are floors; all ratios are
  unaffected (numerator and denominator scale together).
- Corpus is pre-render HTML (no Chrome in the dev container). Post-hydration DOMs
  are larger, which should *increase* B0/B1 and favor D further — but L2a/L2b were
  only validated on SSR DOMs; the two client-rendered listings demonstrate the
  failure mode is detected, not silently wrong.
- First-attempt validation pass rate and mean repair attempts with a real LLM
  were initially simulated only; they have since been measured — see the
  **Addendum** below (fragment arm ≥ full-page arm at 1/22nd the context).

## Interpretation (three sentences)

The single biggest lever is exactly where the baseline spec predicted — listing
grids collapse ~100–800× to one exemplar card — but the mechanism had to change
(tag-path structural fingerprints; MDR-style and class-equality approaches both
fail on modern markup). The second lever the current codebase actively destroys
today: JSON-LD/microdata covers most detail pages fully, but only if probed
before cleaning and always cross-checked against the DOM (we caught stale prices,
cent-denominated prices, and a gift-card JSON-LD on a shoe page). Universal
cleaning alone (L1) is worth 8–58× on heavy pages and is the floor the budgeted
fallback stands on when a page defeats both L0 and L2.

---

## Addendum (2026-07-03): LLM-in-the-loop results — deepseek/deepseek-v4-pro

The metric that was previously simulated, now measured with real authoring calls
(`benchmarks/bench_llm.py`, budget-capped; $0.93 total spent across all runs of a
$10 approval). Both arms use the same model, prompts, 2-attempt repair loop, and
mechanical validator (selectors run against FULL raw HTML, checked against ground
truth). 20 pages (the 2 client-rendered listings excluded — nothing to author).

| Arm | pass@1 | pass@2 | median context | arm cost (20 pages) |
|---|---|---|---:|---:|
| **design (fragment)** | **16/20** | **17/20** | **1,072 tok** | **$0.045** |
| fullpage (prod-cleaned, 48K cap) | 14/20 | 16/20 | 23,108 tok | ~$0.51 |

**The fragment arm matches-or-beats the full page on pass rate at 1/22nd the
context and ~1/11th the cost.** Mean attempts among passing pages: 1.06 (design)
vs 1.12 (fullpage).

Failure breakdown (important for honesty):
- 2 pages failed in BOTH arms with empty-content replies from the provider even
  after retries (allbirds/listing, rothys/detail) — an OpenRouter/DeepSeek
  transport artifact, symmetric across arms, not a reduction issue.
- beardbrand/detail failed in both arms (fragment: model trusted an
  `[itemprop=price]` that isn't in the DOM; fullpage: empty replies). Suspected
  ground-truth quirk (variable-price product) — worth relabeling.
- vercel-commerce/detail failed ONLY in the fullpage arm (hallucinated selector
  from the truncated 18K context) — the failure mode the reduction exists to
  prevent.

**Repair phase** (class-rename mutation on the price node chain, design arm):
7/8 authored specs *survived the mutation without repair* — the model, fed the
reduced fragment + structured-data hints, chose semantic/meta selectors that
don't depend on volatile classes. The 1 spec that did break was repaired on the
first attempt. This is the self-healing story working as designed.

Reproduce / rerun with another model:
`BENCH_LLM_MODEL=<openrouter-id> uv run --project ../prototype python bench_llm.py`
(prices via BENCH_LLM_{INPUT,OUTPUT}_PRICE_PER_M, cap via BENCH_BUDGET_USD).
