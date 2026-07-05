# Autonomous Optimization Brief — LLM Context-Window Problem in a Self-Maintaining E-commerce Scraper

> **For:** a capable long-horizon agent model (e.g. Claude Fable 5) running in Claude Code.
> **Mode:** long-running, multi-stage, with human checkpoints.
> **Companion file:** `html-reduction-pipeline-spec.md` (the current design hypothesis).
> Read it if present; a compact summary is in Appendix A if it is not.

---

## 0. How to run this (read first)

- You are expected to work autonomously across multiple stages, plan your own steps, and
  **check your own work**. Use sub-agents for parallel research where it saves wall-clock
  and tokens.
- **Tools you should confirm you have** before starting: web search, the **Context7 MCP**
  (for live Botasaurus / library docs), and read access to the existing codebase. If any
  are missing, say so at the first checkpoint instead of guessing.
- **Stop at every `⏸ CHECKPOINT`** and wait for human go/no-go. Do not blow through them.
  This is the main cost-control mechanism — see §6.

---

## 1. Mission

The system is a self-maintaining scraper: LLMs write the initial scraper code, and when a
site's markup changes, LLMs read the code and repair it. The **critical bottleneck is the
context window**: real e-commerce pages are 50–300 KB of HTML (~15K–75K tokens), mostly
boilerplate, and feeding them to the repair/authoring LLM is slow, expensive, truncates on
large pages, and degrades accuracy because the relevant nodes are buried.

**Your mission:** produce the best possible design (and a working, benchmarked reference
implementation) for reducing the HTML an LLM must see when authoring or repairing
extraction logic — covering both **listing** and **product-detail** pages, including
listing→detail navigation.

A starting hypothesis already exists (a 3-layer reduction pipeline; see Appendix A / the
companion spec). **Treat it as a baseline to beat, not a specification to implement.**
I am explicitly interested in what *you* come up with — challenge its assumptions,
propose alternatives, and let evidence decide.

---

## 2. System context (fixed constraints)

- **Language:** Python.
- **Fetching:** Botasaurus (Selenium-based) — you have the fully rendered post-hydration
  DOM and can execute JS in-page. Confirm exact API via Context7; do not hard-code method
  names from memory.
- **What the LLM edits:** currently whole generated scraper code files per site. The
  baseline proposes splitting into a generic runner + a small per-site extraction
  artifact (declarative spec, with a code-template escape hatch). You may keep, refine, or
  replace this — but justify it.
- **Models:** a multi-model router is available (cheap model for triage, expensive for
  authoring). Lean into two-tier designs where they help.
- **Docs:** Context7 gives live library documentation — prefer it over assumptions.

---

## 3. Your mandate and latitude

You are **not** restricted to the baseline pipeline. You are encouraged to:

- Question whether the layer boundaries are right, whether a layer is unnecessary, or
  whether a fundamentally different approach wins (e.g. DOM-diff-only repair, learned
  region models, vision-assisted localization, retrieval over a DOM index, etc.).
- Bring in techniques from research and open source — but **validate empirically**, don't
  cargo-cult. Every recommendation must be backed by either a benchmark you ran or a cited
  source.
- Propose the smallest change that captures most of the benefit, and separately, the
  ambitious version. Make the trade-off explicit.

The one thing that is **not** in scope to change: the fetching stays on Botasaurus and the
system stays in Python.

---

## 4. Method (stages)

Work in stages. Keep a running `FINDINGS.md` (append-only, terse) so context can be
reconstructed cheaply without re-reading everything.

**Stage 1 — Frame & baseline.** Read the companion spec. Restate the problem in your own
words, list the assumptions you intend to test, and define the benchmark you will use to
compare approaches (see §5). Assemble a small **corpus of real pages** (see §5) — do not
skip this; it is what makes your conclusions trustworthy.
⏸ **CHECKPOINT 1** — present your plan, assumptions-to-test, and benchmark design. Wait.

**Stage 2 — Independent research.** Investigate, at minimum: repeated-record / data-record
mining algorithms for listing pages (MDR/DEPTA lineage and modern variants); how prevalent
and reliable structured data (JSON-LD/microdata/hydration state) is across real e-commerce
sites; HTML→token reduction techniques and their measured savings; existing OSS that
already solves parts of this; and Botasaurus specifics via Context7. Summarize what's worth
adopting vs. not, with citations.
⏸ **CHECKPOINT 2** — present a short research digest + your proposed design direction(s).
Wait.

**Stage 3 — Design & prototype.** Implement a reference version of the chosen design good
enough to measure. Prioritize the highest-leverage layer first (the baseline argues that's
listing-page block mining). Instrument it for the metrics in §5.

**Stage 4 — Benchmark & iterate.** Run against the corpus. Report tokens-per-page,
reduction-caused failures, and repair success rate before/after. Iterate on the weakest
result.

**Stage 5 — Deliver.** Produce the deliverables in §7.
⏸ **CHECKPOINT 3** — final review. Wait.

---

## 5. Benchmark & corpus (how you prove it works)

Assemble a corpus of **~15–30 saved real pages** spanning several storefront platforms
(e.g. Shopify, WooCommerce, Magento, and a couple of bespoke/JS-heavy sites), split across
listing and detail pages. Save the rendered HTML so runs are deterministic and free to
repeat (don't re-fetch on every iteration — that wastes tokens and time).

Primary metrics:

- **Median & p95 tokens sent to the authoring LLM**, baseline (raw/near-raw HTML) vs. your
  design. This is the headline number.
- **Reduction-caused failures:** cases where a field could not be authored/extracted
  *because* reduction removed the needed node. This is the key risk; it must stay near
  zero.
- **First-attempt validation pass rate** and **mean repair attempts** per simulated break.
- **Structured-data skip rate:** fraction of pages fully solvable without sending HTML.
- **Cost proxy:** estimated $ per authoring call at Fable-5 pricing, before vs. after.

Report a clear before/after table. A design that cuts tokens but raises reduction-caused
failures is a regression — call it out.

---

## 6. Token & cost discipline (important)

This run itself costs money; optimize for insight per token.

- **Fetch each page once**, cache to disk, and work against the cache. Never re-fetch or
  re-read large HTML you already have.
- Keep `FINDINGS.md` terse and append-only; prefer reading it over re-deriving context.
- **Bound web research:** aim for depth over breadth — a handful of high-quality sources
  beats dozens of shallow ones. Stop searching a sub-question once it's answered.
- Don't paste large HTML into your own reasoning; work on reduced fragments and summaries.
- Use the cheap model / sub-agents for mechanical sub-tasks; reserve heavy reasoning for
  design decisions.
- Respect the checkpoints — they exist so a wrong direction is caught before it burns a
  day of compute.
- Do **not** gold-plate: a well-measured prototype beats a polished framework. Stop when
  the deliverables in §7 are met.

---

## 7. Deliverables

1. **`OPTIMIZED_DESIGN.md`** — the recommended approach, with reasoning, how it differs
   from the baseline and why, explicit trade-offs, and the caveats/failure modes you
   found. Include both a minimal version and an ambitious version.
2. **Reference implementation** — runnable Python for at least the highest-leverage
   component, with the instrumentation used to benchmark it.
3. **`BENCHMARKS.md`** — the before/after table from §5 over your corpus, plus a short
   interpretation.
4. **`FINDINGS.md`** — your research digest with citations (what you adopted and what you
   rejected, and why).
5. **A short "what surprised me / open questions" section** — where the baseline was
   wrong, and what you'd investigate next with more budget.

---

## 8. Acceptance criteria

- Median tokens-per-authoring-call materially reduced vs. baseline (state the number).
- Reduction-caused failures at or near zero on the corpus.
- Every recommendation backed by a benchmark you ran or a cited source.
- Works for both listing and detail pages, and addresses listing→detail navigation.
- Clear, honest trade-offs — no claim of a free lunch.

---

## Appendix A — Baseline hypothesis (compact)

The companion spec proposes a "reduce before you reason" cascade; each layer runs only if
the previous didn't already produce a small, high-confidence result:

- **Layer 0 — Structured-data probe:** extract JSON-LD / microdata / hydration state
  (`__NEXT_DATA__`, Apollo, etc.). If a required-field coverage check passes and values
  validate, skip HTML entirely and derive the extraction spec directly.
- **Layer 1 — Universal HTML reduction:** strip `<script>`/`<style>`/`<svg>`/comments and
  noisy attributes, **but keep `class`/`id`/`itemprop`** (needed for selectors); truncate
  long text to previews. ~10–20× reduction.
- **Layer 2 — Page-type isolation:** for **listing** pages, mine the repeated card
  structure and send **one representative card + a count** instead of the whole grid (the
  single biggest lever); for **detail** pages, locate stable anchors (itemprop, L0 values
  used as text anchors, price/add-to-cart labels) and send only the DOM neighborhoods
  around each field.
- **Then:** enforce a per-model token budget; two-tier routing (cheap model for
  classification/triage, expensive for authoring); the LLM emits a small extraction spec;
  a validation step runs selectors against the full HTML with a schema check and confidence
  score, committing on pass or looping to repair on fail.

The baseline also recommends splitting each site into a stable generic **runner** + a tiny
per-site **declarative `ExtractionSpec`** (with a `custom_parser` code-template escape
hatch), so the LLM edits a constrained artifact rather than rewriting whole files.

Known open risks the baseline flags: heuristics are themselves a maintenance surface;
structured data can be stale; readability extractors can delete product content;
infinite-scroll/virtualized listings need scroll-and-accumulate at fetch time; and
full-code generation is harder to validate than a declarative spec.

**Your job is to confirm, refute, or improve on all of the above with evidence.**
