"""Render the benchmark corpus through Botasaurus (real post-hydration DOMs).

Run INSIDE the backend container (Chromium is installed there):

    docker compose up -d backend
    docker compose exec backend python scripts/fetch_corpus.py

Output lands in backend/corpus_rendered/<site>/<page>.html (+ hydration JSON and
meta), visible on the host via the ./backend:/app volume mount. Re-runs skip
pages already on disk — delete a file to re-fetch it.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from botasaurus_driver import Driver

OUT = Path(__file__).resolve().parent.parent / "corpus_rendered"

PAGES = [
    ("allbirds/detail", "https://www.allbirds.com/products/mens-dasher-nz-natural-black-blizzard"),
    ("allbirds/listing", "https://www.allbirds.com/collections/mens-shoes"),
    ("barefootbuttons/detail", "https://barefootbuttons.com/product/v1-standard-acrylic-clear-footswitch-topper/"),
    ("barefootbuttons/listing", "https://barefootbuttons.com/shop/"),
    ("beardbrand/detail", "https://www.beardbrand.com/products/custom-mens-cologne-set"),
    ("beardbrand/listing", "https://www.beardbrand.com/collections/beard-care"),
    ("bigcommerce-demo/detail", "https://cornerstone-light-demo.mybigcommerce.com/all/smith-journal-13/"),
    ("bigcommerce-demo/listing", "https://cornerstone-light-demo.mybigcommerce.com/shop-all/"),
    ("bombas/detail", "https://bombas.com/products/men-s-solid-ankle-four-pack?variant=storm-sage-mix"),
    ("bombas/listing", "https://bombas.com/collections/mens-socks"),
    ("books-toscrape/detail", "https://books.toscrape.com/catalogue/soumission_998/index.html"),
    ("books-toscrape/listing", "https://books.toscrape.com/catalogue/category/books/fiction_10/index.html"),
    ("gymshark/detail", "https://www.gymshark.com/products/gymshark-arrival-5-shorts-black-ss22"),
    ("gymshark/listing", "https://www.gymshark.com/collections/all-products/mens"),
    ("hyva-magento/detail", "https://demo.hyva.io/default/arcade-record-cabinet.html"),
    ("hyva-magento/listing", "https://demo.hyva.io/default/accessories.html"),
    ("rothys/detail", "https://rothys.com/products/womens-pointed-toe-flat-black"),
    ("rothys/listing", "https://rothys.com/collections/womens-shoes"),
    ("vercel-commerce/detail", "https://demo.vercel.store/product/acme-cowboy-hat"),
    ("vercel-commerce/listing", "https://demo.vercel.store/search"),
    ("webscraper-io/detail", "https://webscraper.io/test-sites/e-commerce/allinone/product/60"),
    ("webscraper-io/listing", "https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops"),
]

HYDRATION_JS = """
const out = {};
for (const k of ["__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__APOLLO_STATE__"]) {
    try { if (window[k]) out[k] = JSON.stringify(window[k]).length; } catch (e) {}
}
const nd = document.getElementById("__NEXT_DATA__");
if (nd) out.__NEXT_DATA_TEXT__ = nd.textContent;
return out;
"""


def scroll_to_stabilize(driver, max_rounds: int = 8, settle_rounds: int = 2) -> int:
    """Scroll until the DOM node count stops growing (lazy-load / infinite grids)."""
    stable = 0
    last = driver.run_js("return document.getElementsByTagName('*').length")
    for _ in range(max_rounds):
        driver.scroll_to_bottom()
        driver.short_random_sleep()
        count = driver.run_js("return document.getElementsByTagName('*').length")
        if count <= last:
            stable += 1
            if stable >= settle_rounds:
                break
        else:
            stable = 0
        last = count
    return last


def make_driver() -> Driver:
    """Launch Chrome with container-safe flags and a clear failure message.

    Requires websockets<14 (pinned in requirements.txt): botasaurus-driver 4.0.7
    uses the legacy `.closed` websocket API that newer releases removed, and the
    failure surfaces as the misleading "'NoneType' object has no attribute
    'closed'". If you see that error, the image was built before the pin —
    rebuild with `docker compose up -d --build backend`.
    """
    import traceback

    import websockets

    ws_major = int(websockets.__version__.split(".")[0])
    if ws_major >= 14:
        raise SystemExit(
            f"websockets {websockets.__version__} is installed, but "
            "botasaurus-driver 4.0.7 needs websockets<14 (see requirements.txt). "
            "Rebuild the backend image: docker compose up -d --build backend")
    try:
        d = Driver(headless=True, beep=False,
                   arguments=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        d.run_js("return 1")  # prove the CDP connection is actually alive
        print("[driver] launched OK")
        return d
    except Exception:
        print(traceback.format_exc())
        raise SystemExit("Could not launch Chrome — see traceback above.")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    driver = None
    ok = failed = 0
    for key, url in PAGES:
        site, ptype = key.split("/")
        dest = OUT / site
        dest.mkdir(exist_ok=True)
        html_file = dest / f"{ptype}.html"
        if html_file.exists():
            print(f"[skip] {key} (cached)")
            ok += 1
            continue
        try:
            if driver is None:
                driver = make_driver()
            print(f"[fetch] {key} <- {url}")
            driver.get(url, bypass_cloudflare=True)
            driver.long_random_sleep()
            nodes = scroll_to_stabilize(driver)
            html = driver.page_html
            hydration = {}
            try:
                hydration = driver.run_js(HYDRATION_JS) or {}
            except Exception as e:
                print(f"  hydration capture failed: {e}")
            html_file.write_text(html)
            next_data = hydration.pop("__NEXT_DATA_TEXT__", None)
            if next_data:
                (dest / f"{ptype}.next_data.json").write_text(next_data)
            (dest / f"{ptype}.meta.json").write_text(json.dumps({
                "url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "bytes": len(html),
                "dom_nodes_after_scroll": nodes,
                "hydration_sizes": hydration,
                "renderer": "botasaurus",
            }, indent=2))
            print(f"  [ok] {len(html):,} chars, {nodes:,} nodes")
            ok += 1
            time.sleep(2)
        except Exception as e:
            print(f"  [FAIL] {key}: {type(e).__name__}: {e}")
            failed += 1
            try:
                if driver is not None:
                    driver.close()
            except Exception:
                pass
            driver = None  # fresh browser for the next page
    if driver is not None:
        driver.close()
    print(f"\nDone: {ok} ok, {failed} failed -> {OUT}")


if __name__ == "__main__":
    main()
