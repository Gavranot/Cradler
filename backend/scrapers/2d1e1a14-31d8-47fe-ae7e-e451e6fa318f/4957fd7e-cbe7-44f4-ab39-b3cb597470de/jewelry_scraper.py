from botasaurus import browser, AntiDetectDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import re

@browser(headless=True, block_images=True)
def scrape_jewelry_data(driver: AntiDetectDriver, data):
    """Scrape jewelry customization page for engagement ring settings"""
    
    # Navigate to URL
    driver.get(data['url'])
    driver.short_random_sleep()
    
    # Wait for page to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".item.col-md-3.col-sm-4.col-xs-6"))
        )
    except:
        print("Page loading timeout, continuing anyway...")
    
    results = []
    
    # Find all product containers
    product_containers = driver.find_elements(By.CSS_SELECTOR, ".item.col-md-3.col-sm-4.col-xs-6")
    
    print(f"Found {len(product_containers)} product containers")
    
    for container in product_containers:
        try:
            # Skip the customization container (first one)
            container_id = container.get_attribute('id')
            if container_id == 'customization':
                continue
            
            driver.short_random_sleep()
            
            # Extract diamond name (product title) with fallback
            diamond_name = None
            try:
                # Try multiple selector strategies for title
                title_elements = container.find_elements(By.CSS_SELECTOR, ".settingsProductTitle h5")
                if title_elements:
                    diamond_name = title_elements[0].text.strip()
                else:
                    # Fallback to any h5 element
                    h5_elements = container.find_elements(By.CSS_SELECTOR, "h5")
                    if h5_elements:
                        diamond_name = h5_elements[0].text.strip()
            except:
                diamond_name = None
            
            # Extract product images with fallback
            product_images = []
            try:
                # Try multiple image sources
                img_elements = container.find_elements(By.CSS_SELECTOR, "img.product-img")
                if img_elements:
                    for img in img_elements:
                        src = img.get_attribute('src')
                        if src and src.strip():
                            product_images.append(src.strip())
                        
                        # Check for additional image attributes
                        image1 = img.get_attribute('image1')
                        image2 = img.get_attribute('image2')
                        if image1 and image1.strip():
                            product_images.append(image1.strip())
                        if image2 and image2.strip():
                            product_images.append(image2.strip())
                
                # Fallback to any img tag
                if not product_images:
                    all_imgs = container.find_elements(By.CSS_SELECTOR, "img")
                    for img in all_imgs:
                        src = img.get_attribute('src')
                        if src and src.strip() and not src.endswith('/img/OVERLAY-CUSTOMIZATION.gif'):
                            product_images.append(src.strip())
            except:
                product_images = []
            
            # Remove duplicates
            product_images = list(set(product_images))
            
            # Extract pricing information with fallback
            pricing_info = {}
            try:
                # Try multiple price selector strategies
                price_elements = container.find_elements(By.CSS_SELECTOR, ".settingsProcustPrice .dw-price")
                if price_elements:
                    price_text = price_elements[0].text.strip()
                    
                    # Extract original and sale prices using regex
                    price_match = re.search(r'\$([\d,]+)', price_text)
                    sale_match = re.search(r'\$([\d,]+)(?!.*\$)', price_text)
                    
                    if price_match and sale_match:
                        original_price = price_match.group(1)
                        sale_price = sale_match.group(1)
                        pricing_info = {
                            'original_price': f"${original_price}",
                            'sale_price': f"${sale_price}",
                            'discount': True
                        }
                    elif sale_match:
                        pricing_info = {
                            'price': f"${sale_match.group(1)}",
                            'discount': False
                        }
                
                # Fallback to any price-like text
                if not pricing_info:
                    all_text = container.text
                    price_pattern = r'\$([\d,]+)'
                    prices = re.findall(price_pattern, all_text)
                    if prices:
                        pricing_info = {
                            'price': f"${prices[-1]}",
                            'discount': False
                        }
            except:
                pricing_info = {}
            
            # Skip items with missing critical fields
            if not diamond_name or not product_images:
                continue
            
            # Extract additional metadata
            metal_type = None
            diamond_type = None
            
            # Try to extract metal type from title
            if diamond_name:
                if 'White Gold' in diamond_name:
                    metal_type = 'White Gold'
                elif 'Yellow Gold' in diamond_name:
                    metal_type = 'Yellow Gold'
                elif 'Rose Gold' in diamond_name:
                    metal_type = 'Rose Gold'
                elif 'Platinum' in diamond_name:
                    metal_type = 'Platinum'
                
                # Extract diamond type
                if 'Lab Grown' in diamond_name:
                    diamond_type = 'Lab Grown'
                elif 'Natural' in diamond_name:
                    diamond_type = 'Natural'
            
            result = {
                'diamond_name': diamond_name,
                'product_images': product_images,
                'pricing_information': pricing_info,
                'metal_type': metal_type,
                'diamond_type': diamond_type,
                'container_id': container_id
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"Error processing container {container_id if 'container_id' in locals() else 'unknown'}: {str(e)}")
            continue
    
    print(f"Successfully extracted {len(results)} products")
    return results

if __name__ == "__main__":
    target_url = "https://theartofjewels.com/build_your_own.php?byosp=engagement&step=setting&dshape=round&type=ring&dshape=round"
    
    results = scrape_jewelry_data({'url': target_url})
    
    # Print results as JSON
    print(json.dumps(results, indent=2))
    
    # Save to file
    with open('jewelry_data.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nData saved to jewelry_data.json")