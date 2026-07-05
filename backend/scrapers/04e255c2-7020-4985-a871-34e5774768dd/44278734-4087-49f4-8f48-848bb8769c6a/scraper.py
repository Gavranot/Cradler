from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json


@browser(headless=True, block_images=True, lang="mk-MK")
def scrape_anhoch_graphics_cards(driver: AntiDetectDriver, data):
    """
    Scrape graphics cards listings from Anhoch.com.
    Extracts product titles and prices from the first page of filtered results.
    """
    url = data.get(
        "url",
        "https://www.anhoch.com/categories/grafichki-karti/products?"
        "brand=&attribute=&toPrice=349980&inStockOnly=2&sort=latest&perPage=30&page=1",
    )

    # Navigate to the page
    driver.get(url)

    # Wait for product cards to be present (more reliable than fixed sleep)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.grid-view-products > div.col .product-card")
            )
        )
    except Exception:
        # Continue anyway - try to scrape what we can
        pass

    # Human-like delay
    driver.short_random_sleep()

    results = []

    # Find all product cards within the grid view container.
    # The record selector is `div.col` (30 records per page, corroborated detection).
    items = driver.find_elements(
        By.CSS_SELECTOR,
        "div.grid-view-products > div.col",
    )

    for item in items:
        try:
            # ---------- TITLE EXTRACTION (with fallback chain) ----------
            # Priority 1: Anchor `.product-name` -> h6 (most stable for this site)
            # Priority 2: Anchor `.product-name` text directly
            # Priority 3: h6 inside card
            # Priority 4: h2 fallback
            title = None
            try:
                title_el = item.find_element(
                    By.CSS_SELECTOR, "a.product-name h6"
                )
                title = title_el.get_attribute("textContent") or title_el.text
            except Exception:
                try:
                    title_el = item.find_element(
                        By.CSS_SELECTOR, "a.product-name"
                    )
                    title = title_el.get_attribute("textContent") or title_el.text
                except Exception:
                    try:
                        title_el = item.find_element(By.CSS_SELECTOR, "h6")
                        title = title_el.get_attribute("textContent") or title_el.text
                    except Exception:
                        try:
                            title_el = item.find_element(By.CSS_SELECTOR, "h2")
                            title = (
                                title_el.get_attribute("textContent") or title_el.text
                            )
                        except Exception:
                            title = None

            # ---------- PRICE EXTRACTION (with fallback chain) ----------
            # We want the canonical price in the bottom card section,
            # NOT the `product-price-clone` in the middle section.
            # Priority 1: div.product-card-bottom > div.product-price
            # Priority 2: div.product-price:not(.product-price-clone)
            # Priority 3: [class*='price' i] last resort
            price = None
            try:
                price_el = item.find_element(
                    By.CSS_SELECTOR,
                    "div.product-card-bottom div.product-price",
                )
                price = price_el.get_attribute("textContent") or price_el.text
            except Exception:
                try:
                    price_el = item.find_element(
                        By.CSS_SELECTOR,
                        "div.product-price:not(.product-price-clone)",
                    )
                    price = price_el.get_attribute("textContent") or price_el.text
                except Exception:
                    try:
                        price_el = item.find_element(
                            By.CSS_SELECTOR, "[class*='price' i]"
                        )
                        price = (
                            price_el.get_attribute("textContent") or price_el.text
                        )
                    except Exception:
                        price = None

            # Clean text values
            if title:
                title = " ".join(title.split()).strip()
            if price:
                price = " ".join(price.split()).strip()

            # Skip items missing critical fields or honeypot/empty entries
            if not title or not price:
                continue

            results.append(
                {
                    "title": title,
                    "price": price,
                }
            )

        except Exception:
            # Skip individual item errors but keep going
            continue

    return results


if __name__ == "__main__":
    target_url = (
        "https://www.anhoch.com/categories/grafichki-karti/products?"
        "brand=&attribute=&toPrice=349980&inStockOnly=2&sort=latest&perPage=30&page=1"
    )

    # Botasaurus returns (result, output_filename) when run as a task
    outcome = scrape_anhoch_graphics_cards({"url": target_url})
    scraped = outcome[0] if isinstance(outcome, tuple) else outcome
    scraped = scraped or []

    print(f"\n=== Scraped {len(scraped)} graphics cards ===\n")
    print(json.dumps(scraped, indent=2, ensure_ascii=False))
