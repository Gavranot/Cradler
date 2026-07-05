# HTML Reduction Pipeline — Implementation Spec

**Audience:** Claude Code (or any engineer) implementing this inside an existing
self-maintaining e-commerce scraper.
**Stack assumed:** Python · Botasaurus (Selenium-based, JS-rendered DOM available) ·
LLM rewrites generated scraper code per site · multi-model router available.

---

## 1. Problem & goal

The self-healing loop currently feeds large HTML to an LLM so it can author or repair
scraper code. Real e-commerce pages are 50–300 KB of HTML (~15K–75K tokens), of which
typically **less than 5% is signal**. This suffocates the context window: prompts are
slow, expensive, truncate on big pages, and the model's accuracy degrades as the
relevant nodes get buried in boilerplate.

**Goal:** before any LLM call that authors/repairs extraction logic, reduce the page to
the smallest fragment that still contains everything the model needs to write correct
selectors. The LLM should almost never see raw HTML.

**Non-goals:** this spec does not cover fetching, proxying, anti-bot, scheduling, or the
data sink. It plugs *between* "page fetched by Botasaurus" and "LLM writes/repairs
extraction code."

**Design principle — reduce before you reason.** The pipeline is a cascade: each layer
runs only if the previous one didn't already produce a small-enough, high-confidence
result. Cheapest and most general work happens first.

---

## 2. The one restructuring you should do first

This is the most important recommendation in the document, so it comes before the
layers.

**Today:** the LLM rewrites a whole per-site scraper `.py` file. That couples three
concerns that change at very different rates:

1. **Orchestration** — how to fetch, paginate, navigate listing→detail (changes rarely;
   generic across sites).
2. **Extraction** — which nodes hold title/price/etc. (changes whenever the site's
   markup changes; this is the *only* thing that actually breaks).
3. **Normalization** — parsing "$1,299.00" → `1299.00` (stable, reusable).

When the LLM rewrites the entire file, it must regenerate (and you must re-validate) all
three every time only #2 broke. It also means the reduction pipeline's output doesn't
map cleanly onto "the thing the LLM produces."

**Proposed:** split each site into a stable generic **runner** plus a small per-site
**extraction spec** that is the *only* artifact the LLM writes or repairs.

```
scrapers/
  runner.py              # generic, hand-written. Fetches via Botasaurus,
                         # handles pagination + listing→detail navigation,
                         # loads an ExtractionSpec, runs it, validates, emits rows.
  specs/
    examplestore_com.py  # LLM-authored. ONLY field→selector+transform mappings.
    othershop_com.py
```

An extraction spec is intentionally tiny and declarative:

```python
# scrapers/specs/examplestore_com.py  (LLM writes/repairs ONLY this)
from pipeline.spec import ExtractionSpec, Field

SPEC = ExtractionSpec(
    page_type="product_detail",
    # selectors are CSS or XPath; transform names map to a fixed registry
    fields=[
        Field("title", css="h1[itemprop=name]", required=True),
        Field("price", css="span.price", transform="money", required=True),
        Field("currency", css="meta[itemprop=priceCurrency]", attr="content"),
        Field("images", css="ul.gallery img", attr="src", many=True),
        Field("sku", css="[itemprop=sku]"),
    ],
    # for listing pages, `record_selector` identifies one repeated card and
    # fields are evaluated *relative* to each card.
    record_selector=None,
)
```

**Why this matters for the context problem:** the LLM's job shrinks from "rewrite a
program" to "fill in a handful of selectors." Its *input* (the reduced fragment) and its
*output* (the spec) are now the same small shape, validation is mechanical, and a broken
site usually means re-deriving 1–3 `Field` selectors rather than touching code.

If you genuinely need procedural code for some sites (JS-driven price calc, weird
pagination), keep an escape hatch: a spec may name a `custom_parser` function in a
reviewed module. But treat that as the exception, not the default.

> If adopting this split is too big a change right now, the pipeline below still works —
> just have the LLM rewrite the extraction *functions* of the file in isolation, and
> feed it the reduced fragment. You lose the clean validation story but keep the token
> savings.

---

## 2.1 Template vs. declarative spec — how tight to constrain the LLM

The LLM should **edit a template, never write a scraper from scratch.** A blank page
forces it to re-derive imports, orchestration, error handling, and structure every run —
more output tokens, higher variance, and more surface to validate. Editing a template
gives smaller/predictable output, trivial diffing (you see exactly which slots changed),
and a cleaner repair loop (it edits only the broken slot instead of rewriting a working
file and risking regressions).

"Give a template to edit" and the `ExtractionSpec` split from §2 are the **same idea at
different points on a spectrum** — the question is how much editable surface you expose:

| | Editable surface | Output size | Validation | Flexibility |
|---|---|---|---|---|
| **Loose** — full code template with `# TODO: selectors` regions | whole scraper file | large | execute arbitrary code | highest |
| **Tight** — declarative `ExtractionSpec` (the default) | a few `Field(...)` lines | tiny | mechanical (run selectors + schema) | limited to selector+transform |

**Recommendation: tight by default, with an explicit escape hatch.** Use the declarative
spec for the ~90% of normal sites; drop to a reviewed code template only for sites that
need procedural logic (e.g. click a variant dropdown, then read the price). Going as
declarative as your site variety tolerates is what captures the context-window and
reliability wins.

### Default form — declarative spec (what the LLM fills in)

This is the §2 `ExtractionSpec`. The LLM sees only this file plus the reduced fragment;
it physically cannot break orchestration because it can't see it.

```python
# scrapers/specs/examplestore_com.py
from pipeline.spec import ExtractionSpec, Field

SPEC = ExtractionSpec(
    page_type="product_detail",
    fields=[
        Field("title",  css="h1[itemprop=name]", required=True),
        Field("price",  css="span.price", transform="money", required=True),
        Field("images", css="ul.gallery img", attr="src", many=True),
    ],
    record_selector=None,      # set for listing pages (selector for one card)
)
```

### Escape hatch — `custom_parser` template (for the weird ~10%)

When a site can't be expressed declaratively, the spec points at a `custom_parser` in a
reviewed module. Give the LLM this **skeleton to fill in** — the signature, the contract,
and the orchestration are fixed; it only writes the body. Everything it needs (the
rendered DOM, the driver for interaction, the L0 structured data) is handed in.

```python
# scrapers/specs/trickysite_com.py
from pipeline.spec import ExtractionSpec, ParseContext, ProductRecord

SPEC = ExtractionSpec(page_type="product_detail", custom_parser="parse")

def parse(ctx: ParseContext) -> ProductRecord:
    """LLM fills in ONLY this body. Contract:
    - ctx.soup       : parsed full DOM (bs4/selectolax) — read-only
    - ctx.driver     : Botasaurus driver, for interaction (click variants, scroll)
    - ctx.structured : L0 JSON-LD/microdata dict (may be partial/empty)
    - ctx.url        : page URL
    Must return a ProductRecord. Must NOT fetch new pages or sleep arbitrarily.
    Raise ExtractionError(field) on a field it cannot locate.
    """
    # --- LLM-authored region begins ---
    title = ctx.soup.select_one("h1").text.strip()
    ctx.driver.run_js("document.querySelector('.variant-default').click()")
    price = parse_money(ctx.soup.select_one(".price").text)
    return ProductRecord(title=title, price=price, ...)
    # --- LLM-authored region ends ---
```

Keep the custom-parser surface deliberately narrow: it receives already-fetched DOM and a
constrained driver, returns a typed record, and is **still run through the same
validation in §9**. The escape hatch adds flexibility without giving up the schema check.
Sandbox/static-lint these modules before executing (see §9 caveat).

> Because the implementing LLMs have **Context7** access to live Botasaurus docs, the
> `custom_parser` template can stay thin — the model can look up exact driver method
> names (`run_js`, `page_html`, scrolling helpers) itself rather than relying on examples
> baked into the template, which would otherwise drift as Botasaurus changes.

---

## 3. Module layout for the pipeline

```
pipeline/
  __init__.py
  fetch.py          # thin adapter over Botasaurus → RenderedPage
  structured.py     # Layer 0: JSON-LD / microdata / hydration-state extraction
  reduce.py         # Layer 1: universal HTML reduction
  classify.py       # page-type detection (listing vs detail)
  listing.py        # Layer 2a: repeated-block mining
  detail.py         # Layer 2b: anchor-guided slicing
  budget.py         # token estimation + hard-truncation
  router.py         # two-tier model selection
  spec.py           # ExtractionSpec / Field datamodel + transform registry
  validate.py       # run a spec against full HTML, check schema, score confidence
  pipeline.py       # orchestrates Layers 0→2, returns an LLMRequest
```

Core data objects (use `dataclasses` or `pydantic`):

```python
@dataclass
class RenderedPage:
    url: str
    html: str                  # post-hydration outerHTML from Selenium
    js_state: dict             # captured window.* hydration blobs (see Layer 0)
    screenshot: bytes | None   # optional, for a future vision fallback

@dataclass
class ReducedFragment:
    text: str                  # the compact HTML/markdown handed to the LLM
    page_type: str             # "listing" | "product_detail" | "unknown"
    est_tokens: int
    notes: list[str]           # what was stripped/collapsed, for debugging
    source_layer: str          # which layer produced the final fragment
```

---

## 4. Layer 0 — Structured-data probe (try to skip HTML entirely)

**File:** `pipeline/structured.py`

E-commerce pages embed machine-readable product data far more often than the general
web. If it's present and complete, you never need to reason about HTML at all — and it's
**more stable than the visual DOM** because it's what the site's own frontend renders
from.

Probe three sources, in order:

1. **JSON-LD** — `<script type="application/ld+json">` blocks with `@type` of `Product`,
   `ItemList`, `BreadcrumbList`, `Offer`.
2. **Microdata / RDFa** — `itemprop="price"`, `itemtype=".../Product"`, OpenGraph
   `og:*` / `product:*` meta tags.
3. **Hydration state** — single-page-app stores embedded in the initial document:
   `__NEXT_DATA__`, `window.__NUXT__`, `window.__INITIAL_STATE__`, Apollo
   (`__APOLLO_STATE__`), Redux dumps.

**Botasaurus advantage:** because you render with Selenium, you can read hydration state
directly from the live JS context instead of regexing it out of HTML:

```python
def capture_js_state(driver) -> dict:
    # NOTE: Botasaurus wraps Selenium with its own driver. Confirm the JS-eval
    # method name in your version — it's `driver.run_js(...)` in current
    # Botasaurus, equivalent to Selenium's `execute_script`. Use whichever your
    # driver exposes; the logic is identical.
    keys = ["__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__APOLLO_STATE__"]
    out = {}
    for k in keys:
        try:
            val = driver.run_js(f"return window.{k} ?? null;")  # or execute_script
            if val:
                out[k] = val
        except Exception:
            pass
    return out
```

Likewise, the rendered HTML is `driver.page_html` in Botasaurus (Selenium's
`page_source` if you drop to the raw WebDriver). Capture it *after* any
scroll/lazy-load interaction.

For JSON-LD / microdata, use **`extruct`** (battle-tested, parses JSON-LD, microdata,
RDFa, OpenGraph in one call) over hand-rolled parsing:

```python
import extruct
data = extruct.extract(page.html, base_url=page.url,
                       syntaxes=["json-ld", "microdata", "opengraph", "rdfa"])
```

**Coverage decision — when is it "good enough" to skip HTML?** Define a required field
set per page type and compute coverage:

```python
REQUIRED = {
    "product_detail": {"name", "price"},          # currency/sku/images are bonus
    "listing":        {"items"},                   # ItemList with ≥1 product + url
}

def coverage(extracted: dict, page_type: str) -> float:
    req = REQUIRED[page_type]
    return len(req & present_fields(extracted)) / len(req)
```

If `coverage == 1.0` **and** the values pass the same schema checks used in validation
(price parses to a number, URLs are absolute, listing has ≥ N items), short-circuit: the
LLM writes a parser for the *JSON shape* (tiny, ~hundreds of tokens) rather than for
HTML — or, better, you generate the spec deterministically from the known structure and
skip the LLM entirely for that site.

**Caveats.**
- Structured data can be **stale or partial** — sites sometimes emit JSON-LD with a list
  price while the DOM shows a sale price. That's why Layer 0 output is still run through
  the same validation/cross-check as everything else, and why coverage `< 1.0` falls
  through to the DOM layers rather than being trusted.
- Hydration blobs can be **huge** (entire catalog pages). Don't blindly forward them to
  the LLM; extract the relevant sub-object first, or treat a multi-hundred-KB blob as a
  miss and fall through.
- A few sites poison structured data with marketing fields. Keep a per-site flag to
  disable Layer 0 if it proves unreliable for that domain.

---

## 5. Layer 1 — Universal HTML reduction (page-type agnostic)

**File:** `pipeline/reduce.py`

For pages without usable structured data, shrink the DOM aggressively *before* any
page-type logic. This is a 10–20× reduction on its own and runs identically for every
page.

Use **`lxml`** (via `lxml.html`) or **`selectolax`** (lexbor backend, very fast on large
docs) for the tree surgery; reserve `BeautifulSoup` for ergonomics if preferred. Steps:

1. **Drop non-content nodes entirely:** `<script>` (except the JSON-LD already harvested
   in L0), `<style>`, `<svg>`, `<noscript>`, `<template>`, `<iframe>`, HTML comments, and
   most of `<head>`.
2. **Strip noisy attributes but keep selector-relevant ones.** Remove `style`,
   `on*` handlers, `srcset`, tracking attrs, and most `data-*`. **Keep `class`, `id`,
   `itemprop`, `role`, `href`, `src`, `alt`, and any `data-*` that looks like a stable
   hook (`data-testid`, `data-product-id`).** This is the single most important nuance:
   `class`/`id`/`itemprop` are exactly what the LLM needs to write selectors, so
   over-stripping defeats the purpose.
3. **Collapse text nodes:** truncate long text (descriptions, reviews) to a short
   preview, e.g. first ~120 chars + `…`. The LLM needs to see *that* a node holds text
   and *where* it sits, not the full paragraph.
4. **Drop obvious chrome by heuristic + (optionally) a readability pass.** Consider
   **`trafilatura`** or **`readability-lxml`** to detect and remove nav/footer/sidebar.
   Use this cautiously on e-commerce (see caveat).

Suggested signature:

```python
def reduce_html(html: str, *, text_preview: int = 120,
                keep_attrs: set[str] = DEFAULT_KEEP) -> str:
    ...
```

**Caveats.**
- **Readability extractors are tuned for articles, not shops.** `trafilatura` may delete
  a product gallery or a price box it considers "boilerplate." On listing pages it can
  nuke the entire grid. Gate readability behind page-type, or only use it to *rank*
  regions, never to hard-delete on listing pages.
- Don't strip `class`/`id` to save tokens — measure first. Attributes are cheap relative
  to the value they provide for selector authoring.
- Keep the reduction **deterministic and logged** (`ReducedFragment.notes`) so that when
  a downstream selector fails you can tell whether reduction removed the node.

---

## 6. Layer 2 — Page-type-specific isolation (the biggest lever)

**File:** `pipeline/classify.py`, then `listing.py` / `detail.py`

First classify the page. Cheap signals beat an LLM call here:
URL patterns (`/product/`, `/p/`, `/dp/`, `?sku=` vs `/category/`, `/c/`, `?page=`),
presence of `ItemList` vs `Product` in L0 data, count of repeated structurally-similar
blocks (many ⇒ listing), presence of a single `<h1>` + add-to-cart control (⇒ detail).
If still ambiguous, ask the **cheap** router model to classify from the L1-reduced
fragment.

### 6a. Listing pages → repeated-block mining

**File:** `pipeline/listing.py`

A listing page is one card structure repeated *N* times. The LLM does **not** need 60
cards — it needs **one representative card plus a count**. This is the highest-leverage
reduction in the whole pipeline: a 75K-token grid collapses to a few hundred tokens with
zero loss of the information needed to author the record selector.

Algorithm (a pragmatic take on Mining Data Records / MDR — see references):

1. Walk the L1-reduced DOM. For each element, compute a **structural fingerprint** of
   its subtree — e.g. a hash of the sequence of `(tag, sorted significant classes)` down
   to depth *d*, ignoring text and volatile attrs.
2. Group siblings under a common parent by fingerprint. A group of ≥ `MIN_RECORDS`
   (e.g. 4) siblings sharing a fingerprint, each subtree non-trivial in size, is a
   **candidate record set** (the product grid). Score candidates by
   `count × avg_subtree_size` and pick the best; that parent is the list container.
3. Emit **one exemplar** card (the first, fully intact post-L1) + the count + the CSS
   path to the container and to the card. Optionally include a second card if cards are
   heterogeneous (e.g. ad slots interleaved) so the LLM can see the variation.

```python
@dataclass
class ListingExtract:
    container_css: str
    record_css: str        # selector for one card relative to container
    exemplar_html: str     # ONE reduced card
    record_count: int
    notes: list[str]
```

The LLM then writes field selectors **relative to one card**; the runner loops
`container.select(record_css)` and applies them per card.

**Caveats.**
- **Heterogeneous grids:** sponsored cards, "you may also like" rails, and banner tiles
  share *some* structure with real products. Mitigate by choosing the *largest* uniform
  group and by validating that the chosen selector yields a plausible count and that
  every card produces a price.
- **Infinite scroll / lazy load:** with Botasaurus you control the browser — scroll to
  trigger loading (or detect the "load more" control) *before* capturing `page_source`,
  otherwise the grid is partial. This is a fetch-time concern but it directly affects
  mining quality, so document it in the runner.
- **Virtualized lists** (only visible rows in DOM) need scroll-and-accumulate at fetch
  time; mining alone won't recover off-screen rows.

### 6b. Product detail pages → anchor-guided slicing

**File:** `pipeline/detail.py`

Detail-page fields are scattered but predictable: title, price, currency, gallery,
variant selector, breadcrumbs, SKU, specs table, availability. Locate **stable anchors**
and send only the DOM neighborhood around each, dropping everything else.

Anchor sources, in priority order:
1. Semantic markup left over after L1: `itemprop=`, `meta[property^=product:]`,
   `[role]`.
2. Microdata/JSON-LD *values* from L0 used as **text anchors** — e.g. if L0 gave the
   price string, find the DOM node whose text matches it; that localizes the price box
   even when its class is obfuscated.
3. Visible-label heuristics: currency symbols / price regex, "Add to cart" / "Add to
   bag" buttons, breadcrumb separators.

For each anchor, walk up ancestors until a sensible container (a few levels, or until
the subtree exceeds a size cap), capture that subtree plus a couple of siblings, and
concatenate the slices. De-duplicate overlapping slices.

```python
@dataclass
class DetailExtract:
    slices: list[str]      # reduced HTML neighborhoods, one per field cluster
    anchors_found: dict    # field -> bool, so the LLM knows what's missing
    notes: list[str]
```

**Caveats.**
- If an anchor isn't found, **say so** in `anchors_found` rather than silently dropping —
  the LLM should know "price box not located" so it can search wider or you can fall back
  to sending more of the page.
- **Variant-dependent prices** (price changes when a size/color is selected via JS):
  Botasaurus lets you interact and re-read, but for selector authoring it's usually
  enough to capture the variant control's container so the LLM writes a selector that
  survives the JS update. Note this as a known hard case.

---

## 7. Token budget & truncation

**File:** `pipeline/budget.py`

After Layer 2, enforce a hard budget so a pathological page can never blow the context
window. Estimate tokens (use the model's tokenizer if available, else `len(text)//4` as
a fast proxy). If the fragment still exceeds the budget:

- Listing: it shouldn't (one card) — if it does, the card itself is huge; truncate text
  previews harder.
- Detail: keep the highest-priority slices (price, title, gallery) and drop low-priority
  ones (specs, reviews), recording the drop in `notes`.

Set the budget per *target model* from the router, not globally.

---

## 8. Two-tier model routing

**File:** `pipeline/router.py`

You have a router — use it to keep the expensive model's context tiny:

- **Cheap/fast model:** page-type classification (if heuristics are ambiguous), choosing
  the listing exemplar among heterogeneous candidates, and quick "does this slice contain
  the price?" checks. These run on already-reduced input.
- **Expensive model:** the actual authoring/repair of the `ExtractionSpec`, only ever on
  the final `ReducedFragment`.
- **Deterministic, no model:** when L0 coverage is 1.0, generate the spec directly.

Escalation policy: if validation (next section) fails twice after expensive-model
repair, escalate by *widening the fragment* (send more of the page / more cards) before
blaming the model — truncation is a more common failure than reasoning.

---

## 9. Validation & the repair loop

**File:** `pipeline/validate.py`

This is what makes the loop safe and is *separate from* the LLM context budget — it runs
against the **full rendered HTML**, not the reduced fragment.

1. Take the LLM-produced `ExtractionSpec`, run its selectors against the full page with
   `lxml`/`bs4`.
2. Check results against a schema (use `pydantic`):
   - `price` parses to a positive number; `currency` is a known code/symbol.
   - `title` non-empty, not the site name, within length bounds.
   - `images` are absolute URLs returning image content types (HEAD check, optional).
   - Listing: `record_count` within a plausible band and ≥ X% of cards yield a price.
3. Produce a **confidence score** per field (selector matched exactly one node, value
   passed schema, value cross-checks against L0 if L0 had it).
4. **Pass** → write the spec to `scrapers/specs/<domain>.py` (no redeploy needed if specs
   are loaded dynamically). **Fail** → return the failures to the repair step, which
   re-prompts the expensive model with the failing fields + (if escalated) a wider
   fragment.

Add a **golden-snapshot regression test**: store a known-good rendered HTML per site;
re-run specs against it in CI so a spec change can't silently break a previously working
field.

**Caveat — generated code is harder to validate than config.** This is the cost of
keeping full code generation. The §2 spec split exists precisely so validation can be
mechanical (run selectors, check schema) instead of "execute arbitrary LLM-written code
and hope." If you keep full code files, sandbox execution and at minimum static-lint the
generated module before running it.

---

## 10. End-to-end flow (orchestration)

**File:** `pipeline/pipeline.py`

```python
def build_llm_request(page: RenderedPage) -> LLMRequest | ResolvedSpec:
    # L0
    sdata = extract_structured(page)
    ptype = classify_page_type(page, sdata)
    if coverage(sdata, ptype) == 1.0 and schema_ok(sdata):
        return resolve_spec_from_structured(sdata, ptype)   # no LLM, or tiny LLM

    # L1
    reduced = reduce_html(page.html)

    # L2
    if ptype == "listing":
        frag = mine_listing(reduced)
    elif ptype == "product_detail":
        frag = slice_detail(reduced, sdata)
    else:
        frag = ReducedFragment(text=reduced, page_type="unknown", ...)

    frag = enforce_budget(frag, model=router.target_for(ptype))
    return LLMRequest(fragment=frag, page_type=ptype, hints=sdata)
```

The runner then: calls the expensive model with `LLMRequest` → gets `ExtractionSpec` →
`validate()` against full `page.html` → commit or repair.

---

## 11. Suggested build order (for incremental rollout)

1. **`spec.py` + the §2 split.** Refactor one site to runner + `ExtractionSpec`. Nothing
   else changes yet. This alone constrains what the LLM rewrites.
2. **`validate.py`.** Mechanical validation + golden snapshot for that one site.
3. **`reduce.py` (Layer 1).** Feed reduced HTML to the LLM. Measure token drop.
4. **`structured.py` (Layer 0).** Add the skip path; measure how many sites it fully
   covers.
5. **`listing.py` (block mining).** Highest leverage; do listing pages next.
6. **`detail.py` (anchor slicing).**
7. **`router.py`** two-tier wiring + budget enforcement last.

Each step is independently shippable and independently measurable
(tokens-per-page, repair success rate, validation pass rate).

---

## 12. Recommended libraries

| Purpose | Library | Note |
|---|---|---|
| JSON-LD / microdata / RDFa / OG | `extruct` | one-call structured-data extraction |
| Fast DOM surgery on large pages | `selectolax` | lexbor backend, very fast |
| General DOM / XPath | `lxml` | mature; XPath for anchor walking |
| Ergonomic parsing | `beautifulsoup4` | optional, for readability |
| Boilerplate/main-content detection | `trafilatura` or `readability-lxml` | use cautiously on shops |
| Schema validation | `pydantic` | field schemas + spec model |
| HTML→Markdown (optional) | `markdownify` | if you prefer MD fragments to HTML |
| Token estimation | model tokenizer / `tiktoken` | budget enforcement |

Fetching stays on **Botasaurus**; the pipeline consumes its rendered `page_source` and a
`js_state` dict captured via `driver.execute_script`.

---

## 13. Metrics to track (so you know it's working)

- Median & p95 **tokens per LLM authoring call**, before vs after (primary KPI).
- **Layer 0 skip rate** (% of sites fully covered by structured data).
- **Repair success rate** and **mean repair attempts** per break.
- **Validation pass rate** on first LLM attempt.
- **Reduction-caused failures**: cases where a field broke because reduction removed the
  node (watch this — it's the main risk of the approach).

---

## 14. Honest trade-offs / open questions

- **Heuristics are themselves maintenance.** You're building hand-tuned preprocessing to
  support a self-maintaining system. The defense is that reduction logic is *general*
  (block mining doesn't care what the site looks like), so it's a far smaller and more
  stable surface than per-site selectors — but it isn't free, and Layers 1–2 will need
  occasional tuning.
- **Where to draw the deterministic/LLM line on Layer 0** — generating specs purely from
  structured data is tempting but risks trusting stale JSON-LD. Decide per-site via the
  validation cross-check.
- **Vision fallback (future):** for the rare site that defeats all layers, a screenshot +
  vision model could locate fields visually, then map back to DOM nodes. Out of scope
  here, but `RenderedPage.screenshot` is reserved for it.
- **Full-code escape hatch:** confirm how many sites truly need procedural extraction. If
  it's more than a handful, the §2 split needs a cleaner `custom_parser` contract than
  sketched here.
