# OPTIMIZED_DESIGN.md — HTML Reduction for LLM Scraper Authoring & Repair

**Status:** benchmarked reference implementation in `prototype/pipeline/`;
corpus + harness in `benchmarks/`. Headline: median tokens per authoring call
**107,494 → 1,053** (102× vs raw, 22× vs the current production cleaner) with
**zero reduction-caused failures** on a 22-page real-world corpus. Numbers and
method: `BENCHMARKS.md`. Research trail with citations: `FINDINGS.md`.

---

## 1. The recommended design in one page

Keep the baseline's "reduce before you reason" cascade — it survived contact with
evidence — but with five corrections that the evidence forced:

```
RenderedPage (Botasaurus: page_html + hydration blobs via run_js)
   │
   ├─ L0  structured.py   on RAW html: extruct (JSON-LD → microdata → OG[type=product])
   │                      + __NEXT_DATA__ parse + hydration presence report.
   │                      EVERY value cross-checked against the page before use.
   │                      coverage==1.0 + cross-check pass ⇒ spec derivable with
   │                      little or no LLM  (7/11 detail pages on the corpus)
   │
   ├─ classify            ordered signals: ItemList → Product+add-to-cart →
   │                      mined-grid≥8 → Product+price → cart+single-h1 → URL regex
   │                      (22/22 on corpus; cheap-model tiebreak reserved for "unknown")
   │
   ├─ L1  reduce.py       HtmlRAG-style clean: drop scripts/styles/svg/comments,
   │                      whitelist attrs {class,id,itemprop,role,href,src,alt,
   │                      content,aria-label,data-testid,data-product-*,...},
   │                      truncate text >120ch, drop empties, drop chrome
   │                      (nav/header/footer/aside) WITH breadcrumb hoisting.
   │                      NO wrapper merging (selector fidelity), NO readability.
   │
   ├─ L2a listing.py      tag-path structural fingerprinting (tags only, depth 3,
   │                      order-insensitive child sets) → same-parent groups →
   │                      corroboration gate (≥4 distinct product hrefs + price/img
   │                      ratios) → nested-grid descent → record selector chosen by
   │                      PRECISION against the mined set, anchored container > child.
   │                      Emit: ONE exemplar card + count + container/record selectors.
   │
   ├─ L2b detail.py       anchor-guided slicing: itemprop/data-* probes,
   │                      case-insensitive class scans, L0 values as text anchors,
   │                      price-regex + add-to-cart fallbacks; ancestor-grow to
   │                      1600 chars; container-sized anchors rejected; missing
   │                      anchors reported honestly in `anchors_found`.
   │
   └─ budget              hard per-model token cap; pathological/unknown pages get
                          budget-truncated L1 with an explicit note, never silence.
```

The LLM's **output** artifact changes with it (baseline §2, adopted): a generic
runner + tiny per-site declarative `ExtractionSpec`, with a `custom_parser`
escape hatch. Validation runs the spec against the **full cached HTML** (golden
snapshot) — mechanical, offline, deterministic.

## 2. Where this differs from the baseline spec, and the evidence

| # | Baseline said | We do instead | Evidence |
|---|---|---|---|
| 1 | L0 as first cascade layer (implied on fetched HTML) | L0 **must run on raw HTML before any cleaning**, and its values are **never trusted without a DOM cross-check** | Production code today strips `<script>`/`<meta>` first — JSON-LD/OG destroyed before anything reads them (F2). Corpus caught: JSON-LD for a *different product* (Rothy's gift-card upsell), price in cents (Bombas 3100), price missing (Woo variants). Google Merchant maintains an error taxonomy for exactly this drift (F8). |
| 2 | Listing mining "MDR lineage" | **Tag-path structural fingerprints** (TPC-derived), tags only; classes used only afterwards, precision-validated, for the human-quality selector | MDR scores F1=0.083 on modern pages (NEXT-EVAL, arXiv:2505.17125); no maintained OSS exists; class-equality (today's `dom_detect_product_containers`) dies on CSS-modules/Tailwind. Our fingerprints re-found 9/9 grids after ALL classes were hashed (F9, F14). |
| 3 | Layer-1 may use readability/trafilatura to drop chrome | **Rejected.** Deterministic chrome-drop (nav/header/footer/aside) with **breadcrumb hoisting** instead | Readability tools are article-tuned and delete shop content (F10); the prod cleaner's blanket nav/header removal kills breadcrumbs — hoisting keeps them at ~zero cost (F13). |
| 4 | (not considered) | **Fragment representation stays HTML**; flat XPath→text was tested and rejected for this pipeline | XPath view costs 1.07× MORE tokens on already-reduced fragments; NEXT-EVAL's giant win applies to flattening RAW DOMs, not 300–1500-token exemplars (F15). Accuracy A/B would need LLM budget — future work. |
| 5 | (not considered) | **Repair path defined**: golden snapshot + re-run spec offline; DOM-diff localization demoted to future hybrid | Today's test loop re-fetches the live site every iteration (F6). Line-diff repair (A7) produced 11–176-token repair inputs on stable pages but 6–8K + missed targets on churny ones — needs DOM-aware diffing before it's trustworthy (F14). |

Confirmed as-is from the baseline: the cascade ordering, the runner/spec split
(§2), exemplar-card mining as the single biggest lever (A3: 1.12M→1.4K tokens on
the worst page), per-model token budgets, two-tier routing, and the escape-hatch
philosophy.

## 3. Minimal version (ship this first)

Smallest change capturing most of the win, all inside the existing MCP-tools
layer — **no architecture change, no spec split yet**:

1. **Fix the destruction bug**: run the L0 probe (`extruct` + `__NEXT_DATA__`)
   on raw HTML *before* `_remove_boilerplate`, attach the cross-checked result to
   the generation session, and expose it to the agent as a tool result.
2. **Replace `_remove_boilerplate` with `reduce.py`** (equal or better everywhere,
   keeps breadcrumbs/meta signal — drop-in, measured).
3. **Replace `dom_detect_product_containers`' detection core with `listing.py`**
   (fingerprint mining + corroboration gate + precision-checked selectors). The
   tool's response shape stays the same (`selector`, `count`, `sample_html`).
4. **Change `browser_get_page_source` to return the routed fragment** (exemplar
   or slices + notes) instead of the full cleaned HTML, with a `full=true`
   escape parameter for the agent's widen-on-miss escalation.

Expected effect (measured on corpus): the agent's page-context tokens drop from
median ~23K to ~1K per read, with zero loss of authorable fields.

## 4. Ambitious version

Everything in §3 plus:

5. **Runner + `ExtractionSpec` split** (baseline §2/§2.1 as written, tight-by-
   default). The Secondary Agent authors a spec, not a program; `scraper.py`
   becomes a generic runner loading `specs/<domain>.py`. The executor contract
   (JSON array on stdout) is unchanged, so `ScraperExecutor` needs no changes.
6. **Mechanical validation + golden snapshots** (`validate.py`): run the spec
   against the full cached HTML; pydantic schema checks (price parses positive,
   title non-empty/≠site-name, listing count in band, ≥60% cards yield price —
   the same checks our benchmark harness already implements); confidence score
   per field; L0 cross-check where available. Store one known-good rendered HTML
   per site for offline regression — this also kills the test-loop's live
   re-fetch on every iteration (F6).
7. **Maintenance Agent v1** (currently an empty stub): scheduled re-run of the
   spec against a fresh fetch → validation failures produce a repair request =
   the same `build_fragment` output + the failing fields + the last-good values
   as text anchors. Escalation: widen fragment → full budgeted L1 → human flag.
   Auto-deploy on validation pass (the confidence score exists for the >90%
   gate in the PRD).
8. **Two-tier routing**: Haiku-class model for classification tie-breaks and
   exemplar choice among heterogeneous candidates; the expensive model only ever
   sees the final fragment. Deterministic no-LLM path when L0 coverage is 1.0
   and cross-check passes (7/11 detail pages on the corpus).
9. **Fetch-time completeness** (needs Botasaurus, verified API): loop
   `scroll_to_bottom()` until node-count stabilizes before `page_html`; capture
   hydration state via `run_js("return window.__NEXT_DATA__ ?? null")`;
   `wait_for_element` on the mined record selector for re-validation runs.
   This is what turns the two "client-rendered grid" corpus failures into
   successes in production.

## 5. Failure modes & honest trade-offs

- **Client-rendered pages are a fetch-time problem, not a reduction problem.**
  Plain-HTTP HTML for Bombas/Rothy's listings simply lacks the grid. The pipeline
  detects and *reports* this ("no plausible grid — client-rendered?") instead of
  hallucinating; production must render (§4.9). Until then, such sites fail
  loudly, which is the correct behavior.
- **Fingerprint groups undercount heterogeneous grids** (Allbirds: 37 grouped vs
  66 real cards with badge variants). Mitigated: the emitted selector is
  precision-checked and its own match count is reported; validation counts on the
  full page anyway. Residual risk: a grid whose cards are structurally wild
  enough that no single selector covers them — the second-exemplar channel and
  the escape hatch exist for this.
- **Anchors genuinely absent ≠ reduction failure.** Currency/sku are missing
  from many shops' DOMs entirely. `anchors_found` reports this so the LLM (and
  the validator) treat the field as unavailable rather than searching forever.
- **Heuristics are a maintenance surface** (baseline's own caveat stands). The
  defense holds up empirically: every heuristic here is site-agnostic (structure,
  not appearance), and the corpus harness doubles as a regression suite — run it
  after any heuristic change (`reduction-caused FAILs` must stay 0).
- **The cross-check can be fooled by JSON-in-HTML** (Bombas' cent-price "3100"
  matched inside a script blob). v2 should cross-check against *visible text*
  of the rendered DOM, not raw HTML. Noted in FINDINGS (F8/F14); low severity
  because validation re-checks against extraction results anyway.
- **Cost of the spec split**: one-time refactor of generation prompts + the
  runner, and `custom_parser` sites need sandboxing/lint (baseline §9 caveat
  adopted unchanged). Corpus suggests the declarative form covers all 11 sites;
  the true custom-parser rate will only be known in production.

## 6. Integration map (Cradler-specific)

| Pipeline piece | Lands in | Replaces / feeds |
|---|---|---|
| `reduce.py` (L1) | `backend/agents/mcp/tools_manager.py` | `_remove_boilerplate` |
| `structured.py` (L0) | new `backend/agents/mcp/structured_data.py`, wired in `browser_get_page_source` **before** cleaning | (nothing — data is destroyed today) |
| `listing.py` (L2a) | `backend/agents/mcp/dom_analysis.py` | detection core of `dom_detect_product_containers` |
| `detail.py` (L2b) | `backend/agents/mcp/dom_analysis.py` | new tool `dom_slice_detail`, deprecates `dom_chunk_html` as primary fallback |
| `pipeline.py` + budget | `tools_manager.execute_tool("browser_get_page_source")` | full-HTML return |
| spec/runner/validate (§4) | `backend/scrapers/{templates,validators}` (currently empty dirs) + `pipeline/spec.py` | whole-file codegen |
| Maintenance v1 (§4.7) | `backend/agents/maintenance/` (currently empty) | — |
| Corpus + harness | `benchmarks/` | permanent regression suite |

Also fix while there: repo `CLAUDE.md` documents `driver.bs4`, which does not
exist in Botasaurus 4.x — the correct pattern is
`from botasaurus.soupify import soupify; soup = soupify(driver)` (verified
against driver.py source, F7).

## 7. What surprised me / open questions

**Surprises:**
1. **The current cleaner destroys the highest-value data on the page.** Stripping
   all `<script>`/`<meta>` deletes JSON-LD and OpenGraph before any tool reads
   them — the single most consequential finding, and invisible until you look for
   what *isn't* there.
2. **MDR — the canonical citation for listing mining — is dead on modern HTML**
   (F1=0.083). The living idea is tag-path fingerprinting, which then survived a
   total class-obliteration test 9/9. I expected to need classes as signal;
   pure structure was strictly more robust.
3. **Listings never carry usable ItemList markup** (0/11) while detail pages
   usually carry full Product markup (7/11 → 100% of platform-hosted shops).
   The baseline's Layer-0 skip is real but detail-only.
4. **Structured data lies in specific, recurring ways** — cents vs dollars,
   list-vs-sale price, *other products'* JSON-LD on the page. "Cross-check, never
   trust" went from caution to hard requirement within one corpus.
5. **The XPath→text representation did not transfer** — a headline research
   result (F1 0.10→0.957) that evaporates once the input is already a reduced
   exemplar. A good reminder that published wins are conditional on their
   baseline.
6. **Every selector-hygiene bug I hit was a modern-CSS artifact** — Tailwind
   variant classes that are invalid CSS, utility classes shared but not
   discriminative, cssselect silently lacking the `i` flag. Selector *emission*
   needs as much engineering care as region *detection*.

**Open questions (next budget):**
- **LLM-in-the-loop A/B** (the metric we simulated): first-attempt validation
  pass rate and mean repair attempts, fragment vs full-page, exemplar-HTML vs
  XPath-view, cheap-vs-expensive model on the reduced fragment. All harness
  pieces exist; needs API spend approval and model choice.
- **DOM-aware diff repair**: line-diff was too brittle; a tree-diff (e.g.
  operating on the reduced DOM, emitting changed subtrees + their L2b slices)
  might make repair calls ~100 tokens routinely. Worth a day once Maintenance
  Agent v1 exists.
- **Post-hydration corpus**: re-fetch the corpus through Botasaurus (compose
  route already designed) and re-run the harness — validates L2a/L2b on real
  rendered DOMs and turns the two known-failure listings into test cases.
- **Custom-parser rate in production**: the corpus says 0/11 need procedural
  extraction; the PRD's variant-dependent-price case will be the first real test.
- **`__next_f` (Next 13+ App Router) reassembly**: hydration data is fragmented
  across streamed chunks now; parsing it is doable but was out of scope (F8).
  Matters as headless storefronts grow.
