# FINDINGS.md — HTML-Reduction Optimization Run (append-only, terse)

Format: dated, numbered findings. Never rewrite old entries; append corrections.

## 2026-07-03 — Stage 1: environment + baseline audit

### F1. Environment for this run
- Container is Node-based: **no system Python, no Chrome, no docker CLI, no sudo**.
- Bootstrapped **uv 0.11 + standalone CPython 3.12.13** (`~/.local/bin/uv`) — prototype/benchmarks run on this.
- **No Botasaurus rendering possible in this container** (no Chrome). Corpus will be fetched
  via plain HTTP (curl/httpx). Consequence: pages are pre-hydration server HTML. Acceptable
  because (a) most storefront platforms are SSR, (b) hydration blobs (`__NEXT_DATA__` etc.)
  are present in raw HTML anyway. Divergence from post-hydration DOM is a flagged limitation.
- Network OK: books.toscrape.com 200, pypi.org 200. Some sites will block (scrapingcourse.com
  returned 000) — corpus site list needs fallbacks.
- **Context7 MCP not available to me directly** (backend's client targets a compose-local
  service, not running here). Substitute: WebSearch/WebFetch for Botasaurus docs; can hit
  context7.com API via HTTP if needed.
- **OpenRouter API key present** in `/workspace/.env` → real-LLM benchmark calls are possible
  (budget-gated, will ask at checkpoints before spending).

### F2. Current production baseline (what we must beat) — from source, not docs
- Secondary Agent (`backend/agents/secondary/agent.py`): DeepSeek v3.1-terminus via OpenRouter,
  ReAct loop max 30 iterations, writes a **whole `scraper.py` per site**. Token counting via
  tiktoken exists but there is **no token budget enforcement** on tool results.
- `tools_manager._remove_boilerplate` (`backend/agents/mcp/tools_manager.py:93`) is the only
  reduction today: BS4 decompose of script/style/link/meta/noscript, nav/header/footer/aside,
  `[class*=cookie|banner|modal|popup|sidebar|menu]`, svg, comments. Claimed 40–60% char
  reduction (~2×, far from the spec's 10–20×). **The entire cleaned HTML is then returned into
  the LLM conversation** by `browser_get_page_source` (`:503-519`). This is the headline
  baseline number to measure.
- **Bug/insight: the current cleaner destroys Layer-0 sources before anything reads them.**
  It strips ALL `<script>` (including `application/ld+json`) and ALL `<meta>`/`<link>` (killing
  og:/product: meta + itemprop meta values). So JSON-LD/microdata/OpenGraph are thrown away
  today, not exploited. Any Layer-0 design must hook in BEFORE this cleaning.
- Also risky: removing `nav`/`header` kills breadcrumbs; `[class*="menu"]`/`[class*="banner"]`
  wildcard removal can nuke legit content (e.g. classes like `product-banner`).
- A proto-Layer-2a already exists: `dom_detect_product_containers`
  (`backend/agents/mcp/dom_analysis.py:718`) — 3-phase heuristic (generic selectors → class-
  frequency repeating patterns → content heuristics img+link+price), returns selector + count +
  `sample_html[:2000]`. Not MDR-grade (class-string equality only, no structural fingerprint,
  misses obfuscated/heterogeneous grids) but it's a starting point and evidence the baseline's
  Layer 2a direction was already independently reached.
- `dom_chunk_html` uses `betterhtmlchunking` as fallback. `dom_suggest_selectors` has a decent
  6-tier prioritization (data-attr > aria > itemprop > semantic class > partial class > content).
- Executor contract: generated `scraper.py` runs in subprocess, prints JSON array to stdout.
- **Maintenance Agent is an empty stub** — the "repair" half of the loop does not exist yet;
  this design effectively defines its interface.
- Model note: docs/CLAUDE.md claim differs from source in places; vault "Status and Roadmap"
  is source-verified and matches what I read.

### F3. Problem restatement (my words)
Two LLM consumers of page HTML exist (authoring now; repair once Maintenance Agent is built).
Today the authoring agent receives ~40–60%-reduced full-page HTML — typically still tens of
thousands of tokens — inside a 30-iteration ReAct loop, so a single generation can ingest the
page multiple times. The task: make the LLM's *input* per authoring/repair call a small,
sufficient fragment (target: hundreds to low-thousands of tokens) and make its *output* a small,
mechanically-validatable artifact, without ever losing a node the extraction actually needs.
The baseline 3-layer cascade (L0 structured-data skip → L1 universal strip → L2 page-type
isolation) is the hypothesis to beat/confirm.

### F4. Assumptions to test (numbered; each gets a verdict by Stage 4)
- A1: Structured data (JSON-LD/microdata/OG/hydration) fully covers required fields on a large
  fraction of real e-commerce pages (baseline implies high L0 skip rate).
- A2: Universal reduction (L1) alone achieves ~10–20× token reduction keeping class/id/itemprop.
- A3: Listing-page repeated-block mining is the single biggest lever (grid → 1 exemplar card).
- A4: Detail-page anchor slicing keeps reduction-caused failures ≈ 0.
- A5: A declarative ExtractionSpec suffices for ~90% of sites (escape hatch for the rest).
- A6: Editing a tiny spec beats rewriting scraper.py on tokens AND validation reliability.
- A7 (alternative to test): for REPAIR specifically, DOM-diff between last-good and current
  HTML may localize breakage cheaper than re-running full reduction.

### F5. Benchmark design (Stage 4 will fill the table)
- Corpus: ~20–24 saved pages, listing+detail pairs, across Shopify ×2, WooCommerce ×2,
  Magento demo, BigCommerce, books.toscrape (static control), 2 JS-heavy (Next.js/SPA),
  1–2 bespoke big-retailer if fetchable. Saved under `benchmarks/corpus/<site>/` with
  `manifest.json` (url, platform, page_type, fetch date). Fetch once, work from disk.
- Ground truth: per page, hand-verified JSON of expected field values (title, price, currency,
  image, product-url on listings; + sku/availability where present).
- Comparators: B0 = raw HTML; B1 = current prod `_remove_boilerplate`; D = new design.
- Metrics: median+p95 tokens per authoring call (tiktoken); reduction-caused failures
  (ground-truth node absent from fragment) — must be ≈0; L0 skip rate; first-attempt validation
  pass rate + mean repair attempts on simulated breaks (class renames / ancestor restructures
  applied to saved HTML); $ cost proxy at Fable-5 pricing.
- LLM-in-the-loop metrics run on a subset with real OpenRouter calls only after human approves
  spend at a checkpoint.

### F6. Validation as-is (Stage 2 codebase check)
- `test_scraper` (`backend/agents/mcp/file_system.py:185`) = run the whole generated script in a
  subprocess and hand stdout/stderr back to the LLM. **No schema check, no field-level
  validation, no golden snapshot** — "valid" means "exited 0 and printed something".
- Every test iteration **re-fetches the live site** through Botasaurus (the generated script
  fetches on run) — slow, non-deterministic, repeated bot-detection exposure, and the LLM
  re-ingests stdout each loop.
- Secondary Agent's system prompt hard-codes the 6-tier selector strategy and the tool
  workflow; the prompt itself is another consumer of reduced fragments (sample_html[:2000]
  from container detection).

## 2026-07-03 — Stage 2: research digests

### F7. Botasaurus 4.x API verification (sub-agent, vs README + driver.py source on master)
- Confirmed exactly as expected: `page_html`/`current_url`/`title` (properties);
  `run_js(script, args=None)` returns the JS value, script must contain `return`, JSON-
  serializable args/returns OK; `get(link, bypass_cloudflare=False, wait=None, timeout=60)`;
  `google_get(...)`; `scroll(selector=None, by=1000)`, `scroll_to_bottom(selector=None)`
  (no built-in infinite-scroll helper — loop it), `scroll_into_view(sel)`;
  `wait_for_element(sel, wait=Wait.SHORT)`; `select`/`select_all` → Element with `.text`,
  `.get_attribute`, `.click`, child `.select`; `short_random_sleep()`, `is_bot_detected()`,
  `detect_and_bypass_cloudflare()`; Driver kwargs headless/user_agent/proxy/block_images/beep
  all valid (plus `block_images_and_css`, `wait_for_complete_page_load`, `profile`, ...).
- **Correction found: `driver.bs4` DOES NOT EXIST in 4.x** (repo CLAUDE.md is wrong). Correct
  pattern: `from botasaurus.soupify import soupify; soup = soupify(driver)`.
- No 4.0.7 git tag exists; verified against master which matches 4.x README.
- Sources: raw.githubusercontent.com/omkarcloud/botasaurus-driver/master/README.md and
  /botasaurus_driver/driver.py; pypi.org/project/botasaurus.

### F8. Structured-data prevalence & reliability (sub-agent digest)
- WDC Oct-2024: structured data on 51% of 2.4B crawled pages; schema.org Product on ~3.31M
  hosts / ~280M URLs (~570% growth since 2017). (webdatacommons.org/structureddata/2024-12/,
  w3.org semantic-web list Jan-2025)
- Platform defaults: Shopify + WooCommerce emit JSON-LD Product (name/image/price/currency/
  availability; Woo adds sku) by default; BigCommerce/Webflow too; **Magento default themes
  ship microdata, JSON-LD needs extension**. Long-tail platform shops ⇒ JSON-LD nearly
  guaranteed; large bespoke retailers vary. (shopifyranked.com, contentgecko.io, gofishdigital)
- JSON-LD winning: 70% of annotating sites (vs microdata 46%, RDFa 3%); OG near-universal but
  carries no price/availability in core spec. sku present on 60% of Product-annotating sites
  (up from 21%). Weak fields: brand, gtin, ratings, variant data.
- Reliability: documented failure class = build-time JSON-LD drift (sale vs list price, stale
  availability, variant base-price) — Google Merchant "Mismatched price" taxonomy exists
  because it's common. schema.org has no list-vs-sale distinction (schemaorg#2712).
- Hydration blobs (__NEXT_DATA__/__NUXT__/Apollo) widely exploited by scrapers (Scrapfly
  "hidden web data"); often contain MORE than rendered. Caveat: Next 13+ App Router fragments
  into `self.__next_f.push()` streaming chunks — needs reassembly, not one JSON.parse.
- **Verdict: L0 is a high-yield fast path for core fields on most e-commerce, but every value
  must be cross-checked against the DOM (esp. price/availability); never ground truth.
  Supports A1 with the cross-check condition.**

### F9. Record-mining research (sub-agent digest)
- MDR (KDD'03): edit-distance over adjacent sibling tag sequences; DEPTA (WWW'05): + partial
  tree alignment, needs rendered bounding boxes. **On modern pages MDR scores F1=0.083**
  (NEXT-EVAL benchmark, 164 real pages, arXiv:2505.17125); DEPTA couldn't even run headless.
  REJECT as primary mechanism.
- Best classical lineage: **tag-path clustering** (TPC, WWW'09) — treat root-to-node tag paths
  as signals, cluster co-occurring repeated paths. Robust to non-contiguous records (ads
  interleaved) and obfuscated classes (tag-only paths). Modern pragmatic form = tag-path
  fingerprint hashing; this is what practical scrapers converge on.
- Neural (FreeDOM KDD'20, SimpDOM, DOM-LM) = detail-page attribute extraction, not listing
  region mining; Zyte production uses vision over screenshots (paid, closed).
- **Killer datapoint for fragment format: NEXT-EVAL shows LLM record extraction F1 = 0.957
  when DOM is flattened to XPath→text JSON vs 0.10 on raw slimmed HTML — representation
  matters more than the model.**
- OSS: **no maintained Python lib does unsupervised container detection** (scrapinghub/mdr
  archived Py2; autoscraper/mlscraper are by-example + stalled; selectorlib manual). extruct
  (Zyte) maintained, py3.12 OK — use for L0.
- Virtualized/lazy lists: unsolvable by static DOM analysis — must scroll-to-stabilize at
  fetch time (Botasaurus `scroll_to_bottom()` loop).
- **Verdict on A3: supported in principle, but implement via tag-path fingerprinting (+
  class-frequency as corroborating signal only), NOT MDR; and consider XPath→text flat
  representation for the LLM fragment.**

### F10. HTML-reduction techniques & OSS landscape (sub-agent digest)
- **HtmlRAG (WWW'25, arXiv:2411.02959): cleaning alone (strip css/js/comments/long attrs,
  merge redundant nested tags, drop empties) = ~94% token reduction**, vs markdown 90.3% /
  plain text 96.7% — cleaned HTML costs ~2-4% more than lossy text but keeps selectors.
  Confirms A2 (10-20×) is realistic. Their model-based pruning (step 2) too heavy for us.
- Independent field measurements: raw→markdown median 7.4× over 10 real pages (3×-30× spread);
  Firecrawl claims 93% fewer tokens via main-content markdown.
- OSS convergence: content scrapers → cleaned markdown (crawl4ai fit_markdown density pruning,
  Firecrawl, Jina Reader); web agents → interactive-element tree + screenshot (Skyvern,
  AgentQL). **Markdown is wrong for OUR code-gen path — it destroys the DOM that generated
  selectors must target.** Nobody ships structural dedup off-the-shelf.
- Exemplar + fan-out prior art exists: BardeenAgent (arXiv:2504.12682) scopes observation to
  first list item then loops derived selector; practitioner report 580KB→4.2KB (99.3%) via
  repeated-subtree collapse; AutoScraper (arXiv:2404.12753) top-down progressive subtree
  narrowing with step-back = anchor-slicing prior art.
- Libraries (mid-2026): selectolax 0.4.10 active py3.9-3.14 (~25× BS4 speed); lxml 6.x active;
  extruct 0.18 alive (Nov'24); trafilatura 2.1 active; readability-lxml stagnant; htmlmin
  dead; minify-html byte-level only (skip); tiktoken fine.
- **Verdicts: A2 supported (94% documented). Reject markdown for authoring path. Reject
  readability hard-deletes on shops. Build exemplar/slicing ourselves (no lib exists).**

### F11. Stage-2 synthesis → design direction (for Checkpoint 2)
Evidence-backed shape of the design:
1. Keep the layered cascade BUT: L0 must run on RAW html before any cleaning (current prod
   destroys JSON-LD/meta first — F2); L0 output always DOM-cross-checked (F8), never blind-
  trusted; deterministic spec generation from L0 only after cross-check passes.
2. L1 = HtmlRAG-style clean (selectolax/lxml): drop script(minus ld+json)/style/svg/comments,
   strip attrs except {class,id,itemprop,itemtype,role,href,src,alt,datetime,content,
   data-testid,data-product-*,aria-label}, truncate long text, merge redundant single-child
   wrappers, drop empties. Expect ~10-20× (F10). NO readability/trafilatura deletion on shops.
3. L2a listing = tag-path fingerprinting (TPC-derived, F9) over the L1 tree → container +
   record selector + ONE exemplar + count (+ 2nd exemplar iff heterogeneous). Class-frequency
   only as corroboration (obfuscation-proof). NOT MDR (F1=0.083 modern), NOT class-equality
   (current prod approach breaks on CSS modules).
4. L2b detail = anchor-guided slicing; anchors from itemprop/data-attrs + L0 values as text
   anchors; AutoScraper-style widen-on-miss escalation.
5. Fragment representation A/B to benchmark: (a) pruned exemplar HTML vs (b) flat XPath→text
   pairs (NEXT-EVAL: repr >> model, F9). Possibly hybrid: exemplar HTML + xpath skeleton.
6. Output artifact = declarative ExtractionSpec (runner + spec split per baseline §2);
   validation becomes mechanical + OFFLINE against cached golden snapshot (fixes F6 live
   re-fetch loop); custom_parser escape hatch stays.
7. Repair path (Maintenance Agent interface): golden snapshot enables (a) offline spec re-run,
   (b) DOM-diff last-good vs current to localize breakage (A7) — benchmark in Stage 4.
8. Token budget enforcement per call + two-tier routing kept from baseline.

## 2026-07-03 — Stage 3+4: corpus, implementation, benchmarks

### F12. Corpus (fetch-once, cached)
- 22 pages / 11 sites under `benchmarks/corpus/` + manifest: static ×2 (books-toscrape,
  webscraper-io), Shopify ×4 (allbirds, bombas, rothys, beardbrand), Shopify-headless
  (gymshark), Next.js (vercel-commerce), Magento/Hyvä (demo.hyva.io), BigCommerce
  (cornerstone demo), WooCommerce (barefootbuttons). Extremes: allbirds listing 3.4MB,
  rothys detail 2.8MB raw HTML.
- 3 initially mis-fetched "detail" pages (category/blog/gift-card) caught during GT
  labeling and re-fetched — lesson: validate page identity, not just HTTP 200.
- Ground truth: `benchmarks/ground_truth.json`, hand-verified; 2 labeling errors found and
  corrected during benchmarking (nav-link name; circular count band).

### F13. Reference implementation (prototype/pipeline/)
- reduce.py (L1): HtmlRAG-style clean + chrome-drop with breadcrumb hoisting. No wrapper
  merging (selector fidelity), no readability. tokens: matches/beats prod cleaner everywhere
  while keeping JSON-LD/meta/breadcrumb signal.
- listing.py (L2a): tag-path structural fingerprints (tags only, sorted child sets, depth 3)
  → same-parent groups → corroboration gate (distinct product hrefs + price/img/link ratios)
  → nested-grid descent → record selector chosen from candidates by PRECISION against the
  mined member set → container-anchored child selector.
- structured.py (L0): extruct on RAW html; JSON-LD → microdata → OG (OG only when
  og:type=product — F16); __NEXT_DATA__ parsed, other hydration size-reported; cross_check()
  guards L0 values against the page.
- detail.py (L2b): anchor-guided slicing (itemprop/data-*/L0-text-anchor/price-regex/cart-
  button), ancestor-grow to 1600 chars, container-sized anchors rejected, missing anchors
  reported honestly.
- pipeline.py: classify (structural evidence layered with cart/h1 signals) → route → budget.
- baseline.py: verbatim port of prod _remove_boilerplate as comparator B1.

### F14. Headline benchmark (22 pages; benchmarks/results.json)
- tokens per authoring call: raw median 107,494 / p95 587,150; prod cleaner median 23,098 /
  p95 256,006; **new design median 1,053 / p95 6,144** = 102× vs raw, 22× vs current prod
  at median; worst corpus page (1.12M-token allbirds listing) → 1,415 tokens.
- **Reduction-caused failures: 0/22** (every GT field either in fragment or via cross-checked
  L0). Client-rendered grids (bombas, rothys) correctly reported as no-grid fallback, not
  hallucinated.
- L0 full-skip candidates: **7/11 detail pages** (spec derivable without HTML); **0/11
  listings** had usable ItemList ⇒ A1 CONFIRMED for detail, REFUTED for listings.
- Page-type classifier: 22/22 after 3 iterations (ordering matters: ItemList → product+cart
  → grid≥8 → product+price → cart+single-h1 → URL patterns).
- A2 CONFIRMED: L1 alone 8-58× on heavy pages (less on already-lean pages — grid mining
  carries those). A3 CONFIRMED: listing exemplar is the biggest single lever (1.12M→1.4K).
  A4 CONFIRMED on corpus (0 failures). A5/A6 supported structurally (spec is the shape of
  the fragment); LLM-loop validation still simulated only.
- Repair simulation (30 mutations across 10 detail pages + 9 listing theme-redeploys):
  naive class selectors broke in 8/30 (all class-rename) — the repair scenario is real;
  **fragments remained sufficient for repair in 30/30** (27 in-fragment + 3 via untouched
  L0); **tag-only fingerprint mining re-found 9/9 grids after ALL classes were hashed**
  (worst-case theme redeploy).
- A7 (DOM-diff repair) verdict: MIXED. Line-diff of reduced HTML localizes trivially small
  repair inputs (11–176 tokens) on stable pages, but on pages with churn (gymshark, vercel)
  diffs ballooned to 6-8K tokens and frequently missed the price line (serialization line-
  instability). Needs DOM-aware diffing; recommend hybrid "diff to localize → send L2b slice
  around changed region" as future work, not v1.

### F15. Fragment representation A/B (token cost only)
- XPath→text flat view of already-reduced fragments costs ~1.07× the HTML form (path
  prefixes repeat). NEXT-EVAL's win comes from flattening RAW DOMs; on 300–1500-token
  exemplars there is no token benefit. HTML fragments stay default; accuracy A/B needs
  LLM budget (future).

### F16. Gotchas found while iterating (all fixed, all would bite production)
- cssselect does NOT support the `[attr*=x i]` case-insensitivity flag — such selectors
  silently no-op'd in try/except (image/description anchors "missing"). Python-side scan.
- Tailwind variant classes (`max-sm:min-h-86`) are invalid unescaped CSS AND volatile —
  never build selectors from tokens with `:[]/` etc. (_selector_safe).
- A class shared by ALL cards can still be non-discriminative (`transition-all` matched 29
  extra nodes) — record selectors must be precision-validated against the mined set.
- Fingerprint groups UNDERCOUNT heterogeneous grids (allbirds: 37 grouped, 66 real cards —
  badge/variant structural differences); report the selector's match count, not group size.
- og:title/og:image exist on every page — gating on og:type=product required, else listings
  grow phantom product names and misclassify.
- WooCommerce puts `instock` in a page-level wrapper class — availability anchors must
  reject container-sized matches.
- Magento listing URLs end `.html` (looks like detail); webscraper-io listing embeds a
  single Product microdata block — URL/markup signals must rank below structural evidence.

## 2026-07-03 — Stage 5: deliverables
- Fable 5 pricing (via claude-api skill, cached 2026-06): $10/MTok in, $50/MTok out;
  Haiku 4.5 $1/$5. Caveat adopted into BENCHMARKS.md: tiktoken undercounts Claude
  tokens ~15-20% ⇒ absolute $ are floors, ratios unaffected.
- Deliverables written: /workspace/OPTIMIZED_DESIGN.md (design + minimal/ambitious
  versions + integration map + surprises/open questions §7), /workspace/BENCHMARKS.md
  (before/after tables + interpretation), prototype/pipeline/ (reference impl),
  benchmarks/ (corpus, ground truth, harness, repair sim — doubles as permanent
  regression suite: reduction-caused FAILs must stay 0).
- Assumption verdicts: A1 confirmed-for-detail/refuted-for-listings; A2 confirmed;
  A3 confirmed (mechanism corrected to tag-path fingerprints); A4 confirmed on
  corpus (0 failures); A5/A6 structurally supported, LLM-loop untested (simulated
  per user decision); A7 mixed — future hybrid.

## 2026-07-03 — Post-checkpoint-3: integration + LLM benchmark round
### F17. Minimal integration (§3) applied to backend
- `backend/agents/mcp/reduction/` = ported pipeline package (structured/reduce/
  listing/detail/pipeline/tokens). requirements.txt += extruct, cssselect.
- `tools_manager.py`: GenerationSession now caches raw_html + fragment;
  `browser_get_page_source` runs L0 on RAW html then routes a fragment to the LLM
  (structured_data + cross-check + listing meta/anchors + notes; `full=true`
  escalation returns L1-reduced full page capped at 24K tokens); DOM tools keep
  parsing the L1-reduced FULL page; `_remove_boilerplate` now delegates to
  reduce.py; `dom_detect_product_containers` = fingerprint mining first, legacy
  heuristic fallback (flagged), honest no-grid message.
- Secondary Agent prompt Phase-1 rewritten (prefer structured_data; card-relative
  selectors; full=true escalation). Offline smoke test passed (imports, tool defs,
  fragment routing on corpus pages) — end-to-end test pending user compose run.
- Models now .env-configurable: PRIMARY_AGENT_MODEL / SECONDARY_AGENT_MODEL
  (config.py + compose passthrough + .env/.env.example); bench: BENCH_LLM_MODEL,
  BENCH_LLM_{INPUT,OUTPUT}_PRICE_PER_M, BENCH_BUDGET_USD.
- `backend/scripts/fetch_corpus.py` written (runs in backend container, Chromium
  present in image): scroll-to-stabilize + hydration capture + __NEXT_DATA__ dump
  → backend/corpus_rendered/.
- repo CLAUDE.md driver.bs4 claim corrected to soupify(driver).
- User decisions this round: DeepSeek stays; bench model deepseek/deepseek-v4-pro
  ($0.435/$0.87 per M, provider-dependent); LLM bench budget $10 → hard cap $8.

### F18. LLM-in-the-loop benchmark (deepseek/deepseek-v4-pro, $0.93 spent of $10)
- design arm (fragment): pass@1 16/20, pass@2 17/20, median ctx 1,072 tok, $0.045.
- fullpage arm (prod-cleaned, 48K cap): pass@1 14/20, pass@2 16/20, median ctx
  23,108 tok, ~$0.51. **Fragment ≥ fullpage on pass rate at 1/22 the context.**
- A5/A6 now empirically supported: tiny fragments do not cost authoring accuracy;
  the one fullpage-only failure was a hallucinated selector from truncated context.
- Repair: 7/8 fragment-authored specs SURVIVED class-rename mutations outright
  (semantic/meta selectors chosen thanks to structured-data hints); the 1 break
  repaired at attempt 1.
- Gotchas: OpenRouter/DeepSeek intermittently returns content:null / "" (reasoning-
  only glitch) — must retry at transport level or it contaminates pass rates;
  2 pages still empty after retries in BOTH arms (allbirds/listing, rothys/detail).
- beardbrand/detail GT price ("140") may be mislabeled (variable-price product);
  both arms failed it — relabel candidate.

### F19. In-container Chrome launch failure — root cause and fix
- Symptom: every Driver() → "AttributeError: 'NoneType' object has no attribute
  'closed'". NOT a Chrome problem: chromium launched (CDP HTTP handshake passed;
  4.0.7 auto-adds --no-sandbox under Docker).
- Root cause: botasaurus-driver 4.0.7 pins websockets>=11 UNBOUNDED but uses the
  legacy `.closed` websocket API removed in websockets 14; image resolved 16.0.
  Property getter raising AttributeError falls back to Connection.__getattr__ →
  getattr(self.target=None, 'closed') → the misleading error.
- Fix: requirements.txt pins websockets>=11,<14 (13.1 verified: legacy client with
  .closed; uvicorn[standard] 0.27 compatible). Needs image rebuild.
- Also: browser_executable_path kwarg does NOT exist in 4.0.7 (my F7 verification
  was against master/4.0.92 — version drift). Removed from browser_control helper
  and fetch script; 4.0.7 discovers `chromium` via PATH by itself.
- Kept --disable-dev-shm-usage (Docker 64MB /dev/shm genuinely crashes Chrome on
  heavy pages) via `arguments` (valid in 4.0.7).
- This bug would have broken the Secondary Agent's first in-container browse, not
  just the corpus script — production browser_control.py hardened too.

### F20. Rendered-corpus round (Botasaurus in-container, all 22 pages)
- Rendered sweep: 9/11 grids mined identically; detail fragments stay 0.5–2.4K
  tokens while rendered raws ballooned (gymshark detail 783K tok = 4× static) —
  reduction is MORE valuable post-hydration. Bombas detail L0 now cross-checks 2/2.
- **Bombas listing fixed**: gate failed because (a) geo-localized prices ("MKD
  3,100") were invisible to PRICE_RE — added ISO-4217-code price shapes; (b) images
  are viewport-virtualized (placeholders off-screen) — price signal now carries it.
  Also: styled-components mixed-case hashes ("gNMTEq") slipped past _selector_safe
  — now rejected; shared data-testid values added as top-priority selector
  candidates; bombas ends at container-anchored 'div' × 52.
- **Static bombas GT relabeled**: the pre-render page carries a REAL partial SSR
  grid (~7 cards) — the old "no_grid" label was an artifact of the price-blind
  regex. Post-fix regression: 0 FAILs, 22/22 classifier, median 996 tok.
- **Rothys listing = the one genuinely hard case**: rendered DOM still holds a
  100-item card-grid-skeleton + 75 Shoelace web-component tags with NO serialized
  shadow roots and only 3 product hrefs — catalog hydration never completed in the
  container (late/blocked API) and card content lives in closed shadow DOM that
  page_html can't serialize. Fetch-time future work: wait-for-skeleton-gone +
  shadow-piercing capture (getHTML serializableShadowRoots) — documented, deferred.

### F21. Soft gates — "heuristics may rank and compress; only the LLM may reject"
- Design principle adopted after user challenge (the MKD bug showed the hard
  corroboration gate silently withholding a real grid the LLM would have resolved
  in one glance). False-negative gates silently degrade; false positives cost the
  LLM a few hundred tokens — so gates must be permissive and ambiguity must flow
  to the model, labeled.
- mine_listing now ALWAYS returns the strongest repeated-linked-structure
  candidate: confidence="corroborated" (price/img signals confirmed) or
  "unconfirmed" (LLM must inspect exemplar and decide; header/tool response say so
  explicitly, with signal stats). Only definitional floor kept: records must carry
  ≥3 distinct links (a listing exists to link to details).
- Classification uses corroborated grids only (an unconfirmed nav rail must not
  flip a detail page to listing). PRICE_RE/CART_RE/URL patterns are now hints, and
  were broadened for regional storefronts (Cyrillic ден/МКД prices, кошничка/
  корпа/купи cart words, /proizvod/ URLs) ahead of the user's Macedonian E2E test.
- Results: static suite 0 FAILs, 22/22 classifier, median 975 / p95 2,806 tok
  (p95 improved — unconfirmed candidates are smaller than budgeted-L1 fallbacks).
  Rendered: bombas corroborated ×52; rothys emits its sl-carousel rail as a
  136-token unconfirmed candidate instead of silence — the agent decides.
- Remaining acknowledged hand-written logic: deterministic compression (L1),
  mechanical validation, budget enforcement — judgment-free by design.

### F22. E2E log analysis (user's anhoch.com run) — three bugs, one root cause chain
- Log: backend/backend_run.log (run predates the day's earlier fixes; Context7 SSE
  + synchronous-generate errors in it were already fixed).
- **Bug: Driver() under uvicorn** — botasaurus drives Chrome via its own
  run_until_complete; on uvicorn's loop thread this raises "Cannot run the event
  loop while another loop is running". Browser never opened; the "coroutine
  'start' was never awaited" RuntimeWarnings are the orphaned botasaurus start()
  coroutine (repro confirmed both). FIX: BrowserControlTool routes ALL driver ops
  through a dedicated ThreadPoolExecutor(max_workers=1) (thread affinity for the
  driver's internal loop). Pattern verified under a running loop.
- **Bug: GenerationResult ValidationError** — final DeepSeek message had
  content:null with text in `reasoning`; `.get("content", "")` doesn't guard
  explicit null → final_message=None → pydantic failure marked a SUCCESSFUL run
  failed. FIX: coalesce content → reasoning → "".
- Observation: with all browse tools down, the agent still produced a WORKING
  anhoch.com scraper blind (priors + write→test_scraper(subprocess)→read-stdout
  loop; subprocess Chrome works — no running loop there). Resilient but luck-
  dependent; 0 [REDUCTION] lines this run — pipeline unexercised. Retest needed.
- bcrypt "__about__" warning at startup: known cosmetic passlib/bcrypt-4.x issue.

### F23. E2E run 2 (anhoch.com) — reduction pipeline works in production; last-mile fix
- After the driver-thread + final_message fixes: browser opened, L0+L1 ran, and
  **L2a collapsed the listing 253,144 chars → 504-token exemplar in production**.
  The agent authored its scraper directly from the mined selectors
  (`div.grid-view-products > div.col`) and tested successfully.
- Remaining failure: executor contract expects scrapers/{u}/{s}/scraper.py but the
  agent names scripts freely (3 write_scraper_code calls: *_improved.py etc.).
  FIX: _generate_scraper_background now persists the FINAL scraper_code to
  scraper.py on success. User's existing scraper patched by copying latest script.
