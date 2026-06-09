from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import re
import time

@browser(headless=True, block_images=True)
def scrape_anhoch_graphics_cards(driver: AntiDetectDriver, data):
    """Scrape graphics cards from Anhoch website"""
    
    # Navigate to the target URL
    driver.get(data['url'])
    
    # Wait for page to load completely
    driver.short_random_sleep()
    
    # Wait for product cards to be present
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.product-card')))
    
    # Additional wait for dynamic content
    time.sleep(3)
    
    results = []
    
    # Find all product containers
    product_cards = driver.find_elements(By.CSS_SELECTOR, '.product-card')
    
    print(f"Found {len(product_cards)} product cards")
    
    for i, card in enumerate(product_cards):
        try:
            # Extract product title
            title_element = card.find_element(By.CSS_SELECTOR, 'a.product-name h6')
            title = title_element.text.strip()
            
            # Try multiple price selectors
            price_selectors = [
                '.product-price',
                '.product-price-clone',
                '.product-card-bottom .product-price'
            ]
            
            price_text = ""
            for selector in price_selectors:
                try:
                    price_element = card.find_element(By.CSS_SELECTOR, selector)
                    if price_element.text.strip():
                        price_text = price_element.text.strip()
                        break
                except:
                    continue
            
            # Clean price - extract numbers only
            price_match = re.search(r'([\d.,]+)', price_text)
            price = price_match.group(1) if price_match else price_text
            
            result = {
                'title': title,
                'price': price,
                'price_full': price_text
            }
            results.append(result)
            
            print(f"Product {i+1}: {title} - {price_text}")
            
        except Exception as e:
            # Skip products with missing data
            print(f"Error extracting product {i+1}: {e}")
            continue
    
    return results

if __name__ == "__main__":
    # Target URL for graphics cards
    url = "https://www.anhoch.com/categories/grafichki-karti/products?brand=&attribute=&toPrice=284980&inStockOnly=2&sort=latest&PerPage=30&page=1"
    
    # Execute the scraper
    results = scrape_anhoch_graphics_cards({'url': url})
    
    # Print results as JSON
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Print summary
    print(f"\nExtracted {len(results)} products")