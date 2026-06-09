from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
import json
import re

@browser(headless=True, block_images=True)
def scrape_data(driver: AntiDetectDriver, data):
    # Navigate to URL
    driver.get(data['url'])
    driver.short_random_sleep()
    
    results = []
    
    # Find all product containers using the table row pattern
    product_rows = driver.find_elements(By.CSS_SELECTOR, 'tr.TableListView_tr__46JVR')
    
    print(f"Found {len(product_rows)} product rows")
    
    for row in product_rows:
        try:
            # Extract price using multiple strategies
            price = None
            
            # Strategy 1: Look for price in visible table cells
            try:
                price_elements = row.find_elements(By.CSS_SELECTOR, 'td.TableListView_cell__pS7gd span')
                for element in price_elements:
                    text = element.text.strip()
                    if text.startswith('$'):
                        price = text
                        break
            except:
                pass
            
            # Strategy 2: Look for price in hidden mobile cells
            if not price:
                try:
                    price_elements = row.find_elements(By.CSS_SELECTOR, 'td.TableListView_cell__pS7gd.font-semibold.md\:hidden span')
                    for element in price_elements:
                        text = element.text.strip()
                        if text.startswith('$'):
                            price = text
                            break
                except:
                    pass
            
            # Extract carat weight using multiple strategies
            carat_weight = None
            
            # Strategy 1: Look for carat in visible table cells
            try:
                carat_elements = row.find_elements(By.CSS_SELECTOR, 'td.TableListView_cell__pS7gd')
                for element in carat_elements:
                    text = element.text.strip()
                    # Match decimal numbers (carat weights)
                    if re.match(r'^\d+\.?\d*$', text) and len(text) <= 5:  # Carat weights are typically 0.7, 1.5, etc.
                        carat_weight = text
                        break
            except:
                pass
            
            # Strategy 2: Look for carat in hidden mobile cells
            if not carat_weight:
                try:
                    carat_elements = row.find_elements(By.CSS_SELECTOR, 'td.TableListView_cell__pS7gd.md\:hidden')
                    for element in carat_elements:
                        text = element.text.strip()
                        if re.match(r'^\d+\.?\d*$', text) and len(text) <= 5:
                            carat_weight = text
                            break
                except:
                    pass
            
            # Diamond shape - hardcoded as Round from URL
            diamond_shape = "Round"
            
            # Skip items with missing critical fields
            if not price or not carat_weight:
                print(f"Skipping row - missing data: price={price}, carat={carat_weight}")
                continue
            
            result = {
                'price': price,
                'carat_weight': carat_weight,
                'diamond_shape': diamond_shape
            }
            results.append(result)
            
            driver.short_random_sleep()  # Add delay between items
            
        except Exception as e:
            print(f"Error processing row: {e}")
            continue
    
    return results

if __name__ == "__main__":
    target_url = "https://www.yadavjewelry.com/natural-loose-diamonds/0.7-20-carat/round-diamonds/excellent-cut/l-d-color/si2-fl-clarity"
    results = scrape_data({'url': target_url})
    print(json.dumps(results, indent=2))