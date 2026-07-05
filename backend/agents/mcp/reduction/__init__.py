"""HTML-reduction pipeline for LLM scraper authoring/repair.

Ported from the benchmarked reference implementation (see /OPTIMIZED_DESIGN.md and
/BENCHMARKS.md at repo root: median 107K -> 1K tokens per authoring call, zero
reduction-caused failures on the 22-page corpus in /benchmarks).

Layers:
  structured.py  L0  - JSON-LD/microdata/OG probe on RAW html + DOM cross-check
  reduce.py      L1  - universal reduction (attr whitelist, chrome-drop w/ breadcrumb hoisting)
  listing.py     L2a - tag-path fingerprint grid mining -> one exemplar card + count
  detail.py      L2b - anchor-guided slicing
  pipeline.py        - classify + route + token budget -> ReducedFragment
"""
from .pipeline import ReducedFragment, build_fragment, classify_page_type  # noqa: F401
from .structured import StructuredData, cross_check, extract_structured  # noqa: F401
