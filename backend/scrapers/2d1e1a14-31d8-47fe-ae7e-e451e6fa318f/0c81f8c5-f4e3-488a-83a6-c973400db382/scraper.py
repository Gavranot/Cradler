from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
import json

@browser(headless=True, block_images=True)
def scrape_data(driver: AntiDetectDriver, data):
    # Navigate to URL
    driver.get(data['url'])
    driver.short_random_sleep()

    results = []

    # Find all product containers using the specific class selector
    product_cards = driver.find_elements(By.CSS_SELECTOR, 'div.styles_productCardRoot__DaYPT')
    
    print(f"Found {len(product_cards)} product cards")
    
    for card in product_cards:
        try:
            # Extract price
            price_element = card.find_element(By.CSS_SELECTOR, 'p._text_bevez_41._shared_bevez_6._bold_bevez_47.styles_price__H8qdh')
            price = price_element.text.strip()
            
            # Extract title from the URL path
            link_element = card.find_element(By.CSS_SELECTOR, 'a.styles_unstyledLink__DsttP')
            href = link_element.get_attribute('href')
            
            # Extract product title from URL
            # URL format: /products/username-product-title/
            title = "Unknown Title"
            if href:
                # Remove domain and get path
                path = href.split('depop.com')[-1] if 'depop.com' in href else href
                # Extract product name from URL path
                parts = path.split('/')
                if len(parts) >= 4 and parts[1] == 'products':
                    # The product title is in the format: username-product-title
                    product_slug = parts[2]
                    # Remove username part (everything before the first dash)
                    title_parts = product_slug.split('-')[1:]  # Skip username
                    title = ' '.join(title_parts).replace('-', ' ').title()
            
            result = {
                'title': title,
                'price': price
            }
            results.append(result)
            
        except Exception as e:
            # Skip items with missing data
            print(f"Error extracting product data: {e}")
            continue

    return results

if __name__ == "__main__":
    results = scrape_data({'url': 'https://www.depop.com/category/womens/tops/?moduleOrigin=meganav'})
    print(json.dumps(results, indent=2))