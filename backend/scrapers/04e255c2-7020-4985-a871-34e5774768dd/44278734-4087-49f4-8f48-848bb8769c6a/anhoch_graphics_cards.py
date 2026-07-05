from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import re

@browser(headless=True, block_images=True)
def scrape_anhoch_graphics_cards(driver: AntiDetectDriver, data):
    """Scrape graphics cards listings from Anhoch.com"""
    
    # Navigate to the target URL
    driver.get(data['url'])
    driver.short_random_sleep()
    
    # Wait for products to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.product-item, .product-card, [data-product], .item'))
        )
    except:
        print("Products container not found within timeout")
        return []
    
    driver.short_random_sleep()
    
    results = []
    
    # Multiple container selector strategies (priority order)
    container_selectors = [
        '.product-item',  # Common e-commerce class
        '.product-card',   # Another common pattern
        '[data-product]',  # Data attribute approach
        '.item',           # Generic item class
        '.product',        # Simple product class
        '.grid-item',      # Grid layout items
        '.col-product',    # Column-based products
        '.listing-item'    # Listing items
    ]
    
    product_containers = []
    
    # Try each container selector strategy
    for selector in container_selectors:
        containers = driver.find_elements(By.CSS_SELECTOR, selector)
        if containers:
            print(f"Found {len(containers)} products using selector: {selector}")
            product_containers = containers
            break
    
    if not product_containers:
        print("No product containers found")
        return []
    
    print(f"Processing {len(product_containers)} products...")
    
    for container in product_containers:
        try:
            # Skip containers that are likely not products (empty or hidden)
            if not container.is_displayed():
                continue
                
            # Extract product title with fallback strategies
            title = None
            title_selectors = [
                '.product-title',
                '.title',
                'h2',
                'h3',
                'h4',
                '[data-title]',
                '.name',
                '.product-name',
                'a',  # Often titles are links
                '.card-title'
            ]
            
            for selector in title_selectors:
                try:
                    title_element = container.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_element.text.strip()
                    if title_text and len(title_text) > 5:  # Reasonable title length
                        title = title_text
                        break
                except:
                    continue
            
            # Extract price with fallback strategies
            price = None
            price_selectors = [
                '.price',
                '.product-price',
                '[data-price]',
                '.amount',
                '.cost',
                '.value',
                '.current-price',
                '.price-current',
                'strong',  # Prices are often in strong tags
                'b'        # Or bold tags
            ]
            
            for selector in price_selectors:
                try:
                    price_element = container.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_element.text.strip()
                    
                    # Clean and validate price format
                    price_match = re.search(r'[\d.,]+', price_text)
                    if price_match:
                        price = price_text
                        break
                except:
                    continue
            
            # Skip products missing critical data
            if not title or not price:
                continue
            
            # Clean the data
            title = title.strip()
            price = price.strip()
            
            # Additional validation - ensure it looks like a graphics card
            graphics_card_indicators = ['GTX', 'RTX', 'Radeon', 'GeForce', 'GPU', 'Graphics', 'Video Card']
            is_graphics_card = any(indicator.lower() in title.lower() for indicator in graphics_card_indicators)
            
            if not is_graphics_card:
                continue  # Skip non-graphics card items
            
            result = {
                'title': title,
                'price': price
            }
            
            results.append(result)
            
        except Exception as e:
            # Skip problematic containers
            continue
    
    print(f"Successfully extracted {len(results)} graphics cards")
    return results

if __name__ == "__main__":
    # Target URL with filters: in-stock graphics cards, sorted by latest, max price 349,980
    target_url = "https://www.anhoch.com/categories/grafichki-karti/products?brand=&attribute=&toPrice=349980&inStockOnly=2&sort=latest&perPage=30&page=1"
    
    results = scrape_anhoch_graphics_cards({'url': target_url})
    
    # Print results as JSON for easy parsing
    print(json.dumps(results, indent=2, ensure_ascii=False))