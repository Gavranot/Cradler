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
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.product-card, .product-item, [data-product]'))
        )
    except:
        print("Products container not found within timeout")
        return []
    
    driver.short_random_sleep()
    
    results = []
    
    # Use the specific container selector that worked
    product_containers = driver.find_elements(By.CSS_SELECTOR, '.product-card')
    
    if not product_containers:
        print("No product containers found")
        return []
    
    print(f"Found {len(product_containers)} product containers")
    
    for container in product_containers:
        try:
            # Skip containers that are likely not products (empty or hidden)
            if not container.is_displayed():
                continue
                
            # Extract product title
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
                'a',
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
            
            # Extract price - more specific selectors for Anhoch
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
                'strong',
                'b',
                'span',  # Prices might be in spans
                'div'    # Or divs
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = container.find_elements(By.CSS_SELECTOR, selector)
                    for price_element in price_elements:
                        price_text = price_element.text.strip()
                        
                        # More specific price pattern matching
                        price_patterns = [
                            r'\d+[\s\u0440\u0430\u0442\u0438]*',  # Macedonian denar pattern
                            r'\d+[\s]*[MKD|ден]',  # MKD or denar
                            r'\$\d+',  # Dollar format
                            r'€\d+',   # Euro format
                            r'\d+\s*[€$]',  # Currency symbols
                            r'\d+[.,]\d+',  # Decimal numbers
                        ]
                        
                        for pattern in price_patterns:
                            matches = re.findall(pattern, price_text)
                            if matches:
                                price = price_text
                                break
                        
                        if price:
                            break
                    
                    if price:
                        break
                except:
                    continue
            
            # Alternative: Get all text and look for price patterns
            if not price:
                try:
                    container_text = container.text
                    # Look for price patterns in the entire container text
                    price_patterns = [
                        r'\d+[\s\u0440\u0430\u0442\u0438]+',  # Macedonian denar
                        r'\d+[\s]*[MKD|ден]',
                        r'\$\d+[.,]?\d*',
                        r'€\d+[.,]?\d*',
                        r'\d+[.,]\d+\s*[€$]?',
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, container_text)
                        if matches:
                            # Take the first match that looks like a reasonable price
                            for match in matches:
                                if re.search(r'\d{2,}', match):  # At least 2 digits
                                    price = match.strip()
                                    break
                            if price:
                                break
                except:
                    pass
            
            # Skip products missing critical data
            if not title:
                continue
            
            # Additional validation - ensure it looks like a graphics card
            graphics_card_indicators = ['GTX', 'RTX', 'Radeon', 'GeForce', 'GPU', 'Graphics', 'Video Card']
            is_graphics_card = any(indicator.lower() in title.lower() for indicator in graphics_card_indicators)
            
            if not is_graphics_card:
                continue  # Skip non-graphics card items
            
            result = {
                'title': title.strip(),
                'price': price.strip() if price else 'Price not found'
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