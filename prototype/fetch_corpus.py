"""One-time corpus fetcher. Fetches listing+detail pairs from candidate sites,
saves raw HTML to benchmarks/corpus/<site>/, records a manifest. Never re-fetches
a file that already exists on disk (cost discipline: fetch once, work from cache).

Detail URLs are auto-discovered from the fetched listing via a per-site regex.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

CORPUS = Path(__file__).parent.parent / "benchmarks" / "corpus"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# slug, platform-guess, listing URL, regex to find a product link in the listing
SITES = [
    ("books-toscrape", "static", "https://books.toscrape.com/catalogue/category/books/fiction_10/index.html",
     r'href="(\.\./\.\./\.\./[a-z0-9-]+_\d+/index\.html)"'),
    ("webscraper-io", "static", "https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops",
     r'href="(/test-sites/e-commerce/allinone/product/\d+)"'),
    ("magento-demo", "magento", "https://magento.softwaretestingboard.com/gear/bags.html",
     r'href="(https://magento\.softwaretestingboard\.com/[a-z0-9-]+\.html)"[^>]*class="product-item-link"'),
    ("allbirds", "shopify", "https://www.allbirds.com/collections/mens-shoes",
     r'href="(/products/[a-z0-9-]+)"'),
    ("bombas", "shopify", "https://bombas.com/collections/mens-socks",
     r'href="(/products/[a-z0-9-]+[^"]*)"'),
    ("rothys", "shopify", "https://rothys.com/collections/womens-shoes",
     r'href="(/products/[a-z0-9-]+)"'),
    ("gymshark", "shopify-headless", "https://www.gymshark.com/collections/all-products/mens",
     r'href="(/products/[a-z0-9-]+)"'),
    ("vercel-commerce", "nextjs", "https://demo.vercel.store/search",
     r'href="(/product/[a-z0-9-]+)"'),
    ("bigcommerce-demo", "bigcommerce", "https://cornerstone-light-demo.mybigcommerce.com/shop-all/",
     r'href="(https://cornerstone-light-demo\.mybigcommerce\.com/[a-z0-9-]+/)"[^>]*>'),
    ("barefootbuttons", "woocommerce", "https://barefootbuttons.com/product-category/version-1/",
     r'href="(https://barefootbuttons\.com/product/[a-z0-9-]+/)"'),
    ("beardbrand", "shopify", "https://www.beardbrand.com/collections/beard-care",
     r'href="(/products/[a-z0-9-]+)"'),
    ("woo-demo", "woocommerce", "https://themes.woocommerce.com/storefront/product-category/clothing/",
     r'href="(https://themes\.woocommerce\.com/storefront/product/[a-z0-9-]+/)"'),
]

PLATFORM_MARKERS = {
    "shopify": ["cdn.shopify.com", "Shopify.theme"],
    "woocommerce": ["woocommerce", "wp-content"],
    "magento": ["Magento", "mage/"],
    "nextjs": ["__NEXT_DATA__", "__next_f"],
    "nuxt": ["__NUXT__"],
    "bigcommerce": ["bigcommerce", "stencil"],
}


def detect_platforms(html: str) -> list[str]:
    return [name for name, markers in PLATFORM_MARKERS.items()
            if any(m in html for m in markers)]


def fetch(client: httpx.Client, url: str) -> tuple[int, str]:
    r = client.get(url, headers=HEADERS, follow_redirects=True, timeout=25)
    return r.status_code, r.text


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    manifest_path = CORPUS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    with httpx.Client(http2=True) as client:
        for slug, platform, listing_url, product_re in SITES:
            site_dir = CORPUS / slug
            site_dir.mkdir(exist_ok=True)
            listing_file = site_dir / "listing.html"
            detail_file = site_dir / "detail.html"

            try:
                if listing_file.exists():
                    html = listing_file.read_text(errors="replace")
                    print(f"[skip] {slug}/listing cached ({len(html):,} chars)")
                else:
                    status, html = fetch(client, listing_url)
                    if status != 200 or len(html) < 5000:
                        print(f"[FAIL] {slug}/listing HTTP {status}, {len(html):,} chars")
                        manifest[f"{slug}/listing"] = {"url": listing_url, "status": status,
                                                       "ok": False}
                        continue
                    listing_file.write_text(html)
                    manifest[f"{slug}/listing"] = {
                        "url": listing_url, "status": status, "ok": True,
                        "bytes": len(html), "platform_declared": platform,
                        "platform_detected": detect_platforms(html),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "page_type": "listing",
                    }
                    print(f"[ok]   {slug}/listing {len(html):,} chars "
                          f"{detect_platforms(html)}")
                    time.sleep(1.5)

                if detail_file.exists():
                    print(f"[skip] {slug}/detail cached")
                    continue
                m = re.search(product_re, html)
                if not m:
                    print(f"[FAIL] {slug}/detail: no product link matched")
                    manifest[f"{slug}/detail"] = {"ok": False, "reason": "no link match"}
                    continue
                detail_url = urljoin(listing_url, m.group(1))
                status, dhtml = fetch(client, detail_url)
                if status != 200 or len(dhtml) < 5000:
                    print(f"[FAIL] {slug}/detail HTTP {status}, {len(dhtml):,} chars")
                    manifest[f"{slug}/detail"] = {"url": detail_url, "status": status,
                                                  "ok": False}
                    continue
                detail_file.write_text(dhtml)
                manifest[f"{slug}/detail"] = {
                    "url": detail_url, "status": status, "ok": True,
                    "bytes": len(dhtml), "platform_declared": platform,
                    "platform_detected": detect_platforms(dhtml),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "page_type": "detail",
                }
                print(f"[ok]   {slug}/detail {len(dhtml):,} chars")
                time.sleep(1.5)
            except Exception as e:  # noqa: BLE001 - corpus fetch is best-effort per site
                print(f"[FAIL] {slug}: {type(e).__name__}: {e}")
                manifest[f"{slug}/error"] = {"error": str(e)}

    manifest_path.write_text(json.dumps(manifest, indent=2))
    ok = sum(1 for v in manifest.values() if isinstance(v, dict) and v.get("ok"))
    print(f"\nManifest: {ok} pages cached OK → {manifest_path}")


if __name__ == "__main__":
    sys.exit(main())
